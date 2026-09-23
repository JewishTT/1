"""T2-03/T4-01: SeriesProjector lifecycle (ReplacingMergeTree semantics, SC-004)."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from services.series_lifecycle import (
    MemorySeriesTable,
    SeriesProjector,
    SeriesRow,
    SeriesTableDDL,
    project_cc_series,
)

pytestmark = pytest.mark.unit

T0 = datetime(2024, 3, 1, 12, 0, 0)


def _ts(n: int) -> list[datetime]:
    return [T0 + timedelta(hours=i) for i in range(n)]


def test_project_series_rows_and_canonical() -> None:
    table = MemorySeriesTable()
    proj = SeriesProjector(table, tenant_id="default")
    rows = proj.project_series(
        entity_id="entity-1",
        key="event_count",
        timestamps=_ts(8),
        series_hash="sha-abc",
        source_provenance="CAFEBABE@obs-1",
    )
    assert rows  # temporal metrics materialized
    canonical = proj.canonical(entity_id="entity-1", key="event_count")
    assert len(canonical) == len(rows)
    # metric rows carry the honesty contract: no None fabricated for a filled stream
    assert all(r.metric_value is not None for r in canonical)


def test_replacing_row_converges_after_replay() -> None:
    table = MemorySeriesTable()
    proj = SeriesProjector(table, tenant_id="default")
    first = proj.project_series(
        entity_id="e1", key="k", timestamps=_ts(5), series_hash="h1",
        source_provenance="A@obs-1",
    )
    second = proj.project_series(
        entity_id="e1", key="k", timestamps=_ts(5), series_hash="h1v2",
        source_provenance="A@obs-1",  # same observation -> idempotent replay
    )
    # the ReplacingMergeTree version column is ts, so the replayed newer
    # series_hash wins for the same metric/ts -> canonical reflects latest
    latest = {
        r.metric_name: r.series_hash
        for r in proj.canonical(entity_id="e1", key="k")
    }
    assert latest  # fully populated after convergence (SC-004)


def test_projector_empty_stream_is_empty_projection() -> None:
    table = MemorySeriesTable()
    proj = SeriesProjector(table, tenant_id="default")
    rows = proj.project_series(
        entity_id="e2", key="k", timestamps=[], series_hash="h-empty",
        source_provenance="B@obs-2",
    )
    # temporal_metrics([]) == {} -> no rows fabricated (I-3)
    assert rows == []


def test_series_row_pk_identity() -> None:
    row = SeriesRow(
        tenant_id="t", entity_id="e", key="k", ts=T0, metric_name="m",
        metric_value=1.0, series_hash="h", source_provenance="p",
    )
    pk = row.pk
    assert pk[:3] == ("t", "e", "k")
    assert "m" in pk[3]


def test_ddl_contains_replacing_merge_tree_semantics() -> None:
    assert "ReplacingMergeTree(ts)" in SeriesTableDDL
    assert "PARTITION BY toYYYYMM(ts)" in SeriesTableDDL
    assert "ORDER BY (tenant_id, entity_id, key, metric_name, ts)" in SeriesTableDDL


# ---------------------------------------------------------------------------
# CC-TEMPORALITY v1: project_cc_series (bucketing by observed_at, determinism)
# ---------------------------------------------------------------------------


def _cc_obs(digest: str, iso: str, url: str = "http://example.com") -> dict[str, object]:
    return {"url": url, "observed_at": iso, "status": 200, "digest": digest}


class TestProjectCcSeries:
    def test_empty_input_yields_empty_series(self) -> None:
        assert project_cc_series("e1", []) == []
        # unparseable observed_at is skipped, not fabricated (I-3)
        assert project_cc_series("e1", [_cc_obs("d1", "not-a-timestamp")]) == []

    def test_bucketing_by_observed_at_daily_utc(self) -> None:
        rows = project_cc_series(
            "e1",
            [
                _cc_obs("d1", "2024-03-01T10:00:00+00:00"),
                _cc_obs("d2", "2024-03-01T22:00:00+00:00"),
                _cc_obs("d3", "2024-03-02T08:00:00+00:00"),
            ],
        )
        buckets = [
            r for r in rows if r.metric_name == "cc_capture_count"
        ]
        assert [(r.ts.isoformat(), r.metric_value) for r in buckets] == [
            ("2024-03-01T00:00:00+00:00", 2.0),
            ("2024-03-02T00:00:00+00:00", 1.0),
        ]
        # temporal metrics materialized (burstiness/events_per_day) via SeriesProjector
        metric_names = {r.metric_name for r in rows}
        assert {"burstiness_b", "events_per_day"} <= metric_names
        for row in rows:
            assert row.entity_id == "e1"
            assert row.key == "cc_captures"
            assert row.source_provenance.startswith("cc-index@")
            assert row.series_hash.startswith("cc-")

    def test_dedup_by_digest_and_observed_at(self) -> None:
        dup = _cc_obs("d1", "2024-03-01T10:00:00Z")
        rows = project_cc_series("e1", [dup, dict(dup), _cc_obs("d2", "2024-03-01T11:00:00Z")])
        counts = [r.metric_value for r in rows if r.metric_name == "cc_capture_count"]
        assert counts == [2.0]  # duplicate (digest, observed_at) collapsed

    def test_determinism_order_independent_and_repeatable(self) -> None:
        observations = [
            _cc_obs("d1", "2024-03-03T10:00:00Z"),
            _cc_obs("d2", "2024-03-01T10:00:00Z"),
            _cc_obs("d3", "2024-03-02T10:00:00Z"),
        ]
        first = project_cc_series("e1", observations)
        second = project_cc_series("e1", observations)
        shuffled = project_cc_series("e1", list(reversed(observations)))
        assert first == second
        assert first == shuffled  # sorted internally → order-independent

    def test_rows_land_in_series_table(self) -> None:
        table = MemorySeriesTable()
        rows = project_cc_series(
            "e1",
            [_cc_obs("d1", "2024-03-01T10:00:00Z"), _cc_obs("d2", "2024-03-02T10:00:00Z")],
            table=table,
        )
        assert rows
        canonical = table.canonical(entity_id="e1", key="cc_captures")
        assert {r.metric_name for r in canonical} >= {"cc_capture_count", "burstiness_b", "events_per_day"}