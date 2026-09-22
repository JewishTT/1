"""Series → ClickHouse lifecycle projector (FR-006, 011).

The full lifecycle time-series of an atomic entity is a *projection* (block I):
it never mutates the delimiter stream (L0), it is deterministically rebuildable
from it (I-12), and it is materialized into ClickHouse as a ReplacingMergeTree
whose rows carry a monotone ``version`` equal to the source timestamp.

ReplacingMergeTree(version) semantic: rows with the same (pk) are collapsed on
merge (background), and query-time ``FINAL`` returns the true latest state —
so a replayed / re-fetched SourceRecording row idempotently converges to the
*canonical* SeriesRow. This is exactly the "honest rebuild" contract: the
projection is NEVER the source of truth, the stream is.

Storage is behind a tiny protocol so tests run on an in-memory table while
production talks to ClickHouse. Empty/None metric values are stored as NULL
(I-3 honesty: we never fabricate numbers).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from domain.temporal_metrics import temporal_metrics


@dataclass(frozen=True)
class SeriesRow:
    """One materialized row of an entity's life-series (replaces-on-version)."""

    tenant_id: str
    entity_id: str
    key: str
    ts: datetime
    metric_name: str
    metric_value: float | None
    series_hash: str
    source_provenance: str  # e.g. CAFEBABE@observation_id (I-12 required)

    @property
    def pk(self) -> tuple[str, str, str, str, str]:
        """ReplacingMergeTree ORDER BY key: (tenant, entity, key, metric, ts)."""
        return (self.tenant_id, self.entity_id, self.key, self.metric_name, self.ts.isoformat())


class SeriesTable(Protocol):
    def upsert(self, rows: list[SeriesRow]) -> int: ...

    def canonical(self, *, entity_id: str, key: str, tenant_id: str = "default") -> list[SeriesRow]: ...


class MemorySeriesTable:
    """In-memory ReplacingMergeTree-equivalent for tests and pilot."""

    def __init__(self) -> None:
        self._rows: dict[tuple, SeriesRow] = {}

    def upsert(self, rows: list[SeriesRow]) -> int:
        previous = len(self._rows)
        for r in rows:
            self._rows[r.pk] = r
        return len(self._rows) - previous

    def canonical(self, *, entity_id: str, key: str, tenant_id: str = "default") -> list[SeriesRow]:
        out = [
            r
            for r in self._rows.values()
            if r.entity_id == entity_id and r.key == key and r.tenant_id == tenant_id
        ]
        return sorted(out, key=lambda r: r.ts)


SeriesTableDDL = """
CREATE TABLE IF NOT EXISTS entity_series
(
    tenant_id        LowCardinality(String),
    entity_id        String,
    key              String,
    ts               DateTime64(6),
    metric_name      LowCardinality(String),
    metric_value     Nullable(Float64),
    series_hash      String,
    source_provenance String
)
ENGINE = ReplacingMergeTree(ts)
PARTITION BY toYYYYMM(ts)
ORDER BY (tenant_id, entity_id, key, metric_name, ts);
"""
# ReplacingMergeTree(ts): the ts is the *version* — replaying a row with the
# same pk converges to the newest, so re-fetches are idempotent (SC-004).


class SeriesProjector:
    """Deterministic projector: stream events (or folded Series) → SeriesRow.

    The projector must be a pure function of its input: given the same
    underlying observations it always reaches the same canonical life-series.
    If the hosting app has ClickHouse it binds the DDL above; otherwise the
    caller passes a MemorySeriesTable (pilot/tests).
    """

    def __init__(self, table: SeriesTable, tenant_id: str = "default") -> None:
        self._table = table
        self._tenant = tenant_id

    def project_series(
        self,
        *,
        entity_id: str,
        key: str,
        timestamps: list[datetime],
        series_hash: str,
        source_provenance: str,
    ) -> list[SeriesRow]:
        metrics = temporal_metrics(timestamps)
        rows: list[SeriesRow] = []
        for name, value in metrics.items():
            rows.append(
                SeriesRow(
                    tenant_id=self._tenant,
                    entity_id=entity_id,
                    key=key,
                    ts=timestamps[-1] if timestamps else datetime.now(timezone.utc),
                    metric_name=name,
                    metric_value=float(value) if value is not None else None,
                    series_hash=series_hash,
                    source_provenance=source_provenance,
                )
            )
        self._table.upsert(rows)
        return rows

    def canonical(self, *, entity_id: str, key: str) -> list[SeriesRow]:
        return self._table.canonical(entity_id=entity_id, key=key, tenant_id=self._tenant)


__all__ = ["MemorySeriesTable", "SeriesProjector", "SeriesRow", "SeriesTable", "SeriesTableDDL"]