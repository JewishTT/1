"""Analytics store (T040) — in-memory ClickHouse-analog with idempotent inserts."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from domain import enforce_projection_provenance

import path_shim  # noqa: F401


@dataclass(frozen=True)
class ObservationMetric:
    projection_key: str
    source_id: str
    event_type: str
    changed: bool = False
    duplicate: bool = False
    size_bytes: int = 0
    cost_ms: float = 0.0


@dataclass
class SourceAggregate:
    source_id: str = ""
    observations: int = 0
    changed: int = 0
    duplicates: int = 0
    bytes_received: int = 0
    cost_ms: float = 0.0


class AnalyticsStore:
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], ObservationMetric] = {}
        self._per_source: defaultdict[str, SourceAggregate] = defaultdict(SourceAggregate)

    def insert_observation_metric(self, metric: ObservationMetric, provenance: dict | None = None) -> None:
        enforce_projection_provenance(provenance)
        row_key = (metric.projection_key, metric.source_id)
        if row_key in self._rows:
            return  # idempotent (I-11)
        self._rows[row_key] = metric
        agg = self._per_source[metric.source_id]
        agg.source_id = metric.source_id
        agg.observations += 1
        agg.changed += int(metric.changed)
        agg.duplicates += int(metric.duplicate)
        agg.bytes_received += metric.size_bytes
        agg.cost_ms += metric.cost_ms

    def per_source(self, source_id: str) -> SourceAggregate | None:
        agg = self._per_source.get(source_id)
        return agg if agg and agg.source_id else None

    def aggregate_all(self) -> list[SourceAggregate]:
        return sorted((a for a in self._per_source.values() if a.source_id), key=lambda a: a.source_id)

    def count(self) -> int:
        return len(self._rows)