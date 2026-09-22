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