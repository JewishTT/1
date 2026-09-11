"""Analytics projector → ClickHouse-analog (T040).

Observation metrics, per-source aggregates, and cost accounting land in an
analytics store (ClickHouse adapter isolated; in-memory here). Inserts are
idempotent on (projection_key, source) and carry provenance (I-11/I-12).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import path_shim  # noqa: F401

from .store import AnalyticsStore, ObservationMetric


@dataclass
class AnalyticsProjector:
    store: AnalyticsStore = field(default_factory=AnalyticsStore)
    _log: list[ObservationMetric] = field(default_factory=list, repr=False)

    def project_observation(self, *, projection_key: str, source_id: str, event_type: str,
                            changed: bool = False, duplicate: bool = False,
                            size_bytes: int = 0, cost_ms: float = 0.0,
                            provenance: dict | None = None) -> None:
        metric = ObservationMetric(
            projection_key=projection_key,
            source_id=source_id,
            event_type=event_type,
            changed=changed,
            duplicate=duplicate,
            size_bytes=size_bytes,
            cost_ms=cost_ms,
        )
        self.store.insert_observation_metric(metric, provenance=provenance)
        self._log.append(metric)

    def rebuild(self) -> AnalyticsStore:
        """Rebuild = replay the durable metric log into a fresh store (I-12)."""
        fresh = AnalyticsStore()
        for metric in sorted(self._log, key=lambda m: (m.projection_key, m.source_id)):
            fresh.insert_observation_metric(
                metric,
                provenance={"event_id": metric.event_type, "observation_id": metric.projection_key},
            )
        self.store = fresh
        return fresh