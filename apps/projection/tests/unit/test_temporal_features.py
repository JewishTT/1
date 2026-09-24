"""Temporal feature projection tests."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "shared"))

from domain.dynamics import StreamRecord
from domain.temporal_materialization import materialize_history
from projection.temporal_materialization.features import (
    MemoryTemporalFeatureTable,
    project_features,
)


def test_feature_projection_is_aligned_and_generation_replaced() -> None:
    t0 = datetime(2024, 1, 1, tzinfo=UTC)
    records = [
        StreamRecord(
            entity_id="e1",
            kind="fact",
            ts=t0,
            tenant_id="t1",
            payload={"event_at": t0.isoformat()},
            sequence=1,
        )
    ]
    table = MemoryTemporalFeatureTable()
    first = project_features(materialize_history(records, tenant_id="t1", entity_id="e1"), table)
    assert len(first) == 1
    second_records = records + [
        StreamRecord(
            entity_id="e1",
            kind="fact",
            ts=t0 + timedelta(days=15),
            tenant_id="t1",
            payload={"event_at": (t0 + timedelta(days=15)).isoformat()},
            sequence=2,
        )
    ]
    second = project_features(
        materialize_history(
            second_records, tenant_id="t1", entity_id="e1", projection_generation=2
        ),
        table,
    )
    assert [
        row.projection_generation for row in table.canonical(tenant_id="t1", entity_id="e1")
    ] == [2, 2, 2]
    assert second[0].available is True


def test_operations_can_resume_failed_run() -> None:
    from projection.temporal_materialization.operations import MaterializationOperations

    ops = MaterializationOperations()
    ops.start("r1", tenant_id="a", entity_id="e")
    ops.mark("r1", "FAILED", reason="interrupted")
    resumed = ops.resume("r1", tenant_id="a")
    assert resumed is not None and resumed["status"] == "QUEUED"
    assert ops.resume("r1", tenant_id="b") is None
    from projection.temporal_materialization.operations import MaterializationOperations

    ops = MaterializationOperations(max_retries=1)
    assert ops.start("r1", tenant_id="a", entity_id="e")["status"] == "QUEUED"
    assert ops.mark("r1", "FAILED", reason="x")["retry_count"] == 1
    assert ops.mark("r1", "FAILED", reason="x")["status"] == "QUARANTINED"
    assert ops.get("r1", tenant_id="b") is None
    assert ops.health(tenant_id="a")[0]["status"] == "QUARANTINED"
    assert ops.audit("r1", tenant_id="a")
    assert ops.audit("r1", tenant_id="b") == []


def test_reconcile_reports_missing_and_extra() -> None:
    from projection.temporal_materialization.operations import reconcile_fingerprints

    result = reconcile_fingerprints({"a", "b"}, {"a", "c"})
    assert result["ok"] is False
    assert result["missing"] == ["b"] and result["extra"] == ["c"]
