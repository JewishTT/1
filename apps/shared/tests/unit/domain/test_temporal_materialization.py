"""014 temporal materialization domain tests."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest

from domain.dynamics import StreamAppendRejected, StreamRecord
from domain.temporal_materialization import (
    LifecycleState,
    MaterializationError,
    materialize_history,
    window_bounds,
)

T0 = datetime(2024, 1, 1, tzinfo=UTC)
pytestmark = pytest.mark.unit


def record(
    i: int, at: datetime, *, tenant: str = "t1", entity: str = "e1", obs: str = ""
) -> StreamRecord:
    return StreamRecord(
        entity_id=entity,
        kind="fact",
        ts=at,
        tenant_id=tenant,
        payload={"event_at": at.isoformat()},
        observation_id=obs or f"obs-{i}",
        sequence=i,
    )


def test_window_bounds_half_open_and_aligned() -> None:
    start, end = window_bounds(T0 + timedelta(days=3), timedelta(days=7))
    assert start <= T0 + timedelta(days=3) < end
    assert end - start == timedelta(days=7)


def test_replay_is_deterministic_and_dedupes_exact_records() -> None:
    rows = [record(1, T0), record(2, T0 + timedelta(days=1))]
    first = materialize_history(rows + [rows[0]], tenant_id="t1", entity_id="e1")
    second = materialize_history(list(reversed(rows)), tenant_id="t1", entity_id="e1")
    assert first.publication.integrity_fingerprint == second.publication.integrity_fingerprint
    assert (
        first.publication.source_cut.source_record_ids
        == second.publication.source_cut.source_record_ids
    )
    assert first.publication.source_cut.source_record_ids != first.publication.source_cut.source_record_hashes
    assert len(first.publication.revisions) == 1


def test_dormant_gap_is_explicit_and_feature_unavailable() -> None:
    rows = [record(1, T0), record(2, T0 + timedelta(days=15))]
    history = materialize_history(rows, tenant_id="t1", entity_id="e1", window=timedelta(days=7))
    windows = [r.window for r in history.publication.revisions]
    assert len(windows) == 3
    assert windows[1].lifecycle is LifecycleState.DORMANT
    feature = history.publication.features[1]
    assert feature.available is False and feature.value is None


def test_point_in_time_returns_half_open_window() -> None:
    history = materialize_history([record(1, T0)], tenant_id="t1", entity_id="e1")
    revision = history.publication.revisions[0]
    assert history.window_at(revision.window.window_start) is revision
    assert history.window_at(revision.window.window_end) is None


def test_mixed_tenant_and_naive_timestamp_rejected() -> None:
    with pytest.raises(MaterializationError):
        materialize_history([record(1, T0, tenant="other")], tenant_id="t1", entity_id="e1")
    with pytest.raises(StreamAppendRejected):
        StreamRecord(entity_id="e1", kind="fact", ts=datetime(2024, 1, 1), tenant_id="t1")


def test_repository_publishes_once_and_rejects_cross_tenant_access() -> None:
    from domain.temporal_materialization_store import TemporalMaterializationRepository

    repo = TemporalMaterializationRepository()
    rows = [record(1, T0)]
    first = repo.materialize(rows, tenant_id="t1", entity_id="e1")
    duplicate = repo.materialize(rows, tenant_id="t1", entity_id="e1")
    assert first.changed is True and first.revision == 1
    assert duplicate.changed is False and duplicate.revision == 1
    assert repo.current(tenant_id="t2", entity_id="e1") is None
    assert repo.point_in_time(tenant_id="t1", entity_id="e1", at=T0) is not None


def test_repository_comparison_classifies_late_change() -> None:
    from domain.temporal_materialization_store import TemporalMaterializationRepository

    repo = TemporalMaterializationRepository()
    repo.materialize([record(1, T0)], tenant_id="t1", entity_id="e1")
    candidate = materialize_history(
        [record(1, T0), record(2, T0 + timedelta(days=1))], tenant_id="t1", entity_id="e1"
    )
    comparison = repo.compare(candidate)
    assert comparison["added_window_starts"] or comparison["changed_window_starts"]


def test_late_event_affects_later_windows() -> None:
    from domain.temporal_materialization import compute_affected_closure

    existing = materialize_history(
        [record(1, T0), record(2, T0 + timedelta(days=15))], tenant_id="t1", entity_id="e1"
    )
    late = record(3, T0 + timedelta(days=8))
    assert len(compute_affected_closure(late, existing=existing)) == 2


def test_contradictory_source_is_quarantined_without_replacing_head() -> None:
    from domain.temporal_materialization_store import TemporalMaterializationRepository

    repo = TemporalMaterializationRepository()
    original = repo.materialize([record(1, T0)], tenant_id="t1", entity_id="e1")
    result = repo.quarantine(
        tenant_id="t1", entity_id="e1", source_record_id="s1", reason="hash conflict"
    )
    assert result["status"] == "QUARANTINED"
    assert repo.current(tenant_id="t1", entity_id="e1") is original.history
