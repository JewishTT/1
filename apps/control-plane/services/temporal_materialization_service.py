"""Control-plane service facade for deterministic temporal materialization."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta

from domain.dynamics import StreamRecord
from domain.temporal_materialization import MaterializationError, TemporalHistory
from domain.temporal_materialization_store import (
    MaterializationResult,
    TemporalMaterializationRepository,
)


class TemporalMaterializationService:
    def __init__(self) -> None:
        self.repository = TemporalMaterializationRepository()

    def materialize(
        self,
        records: Iterable[StreamRecord],
        *,
        tenant_id: str,
        entity_id: str,
        window: timedelta = timedelta(days=7),
    ) -> MaterializationResult:
        return self.repository.materialize(
            records, tenant_id=tenant_id, entity_id=entity_id, window=window
        )

    def current(self, *, tenant_id: str, entity_id: str) -> TemporalHistory | None:
        return self.repository.current(tenant_id=tenant_id, entity_id=entity_id)

    def point_in_time(self, *, tenant_id: str, entity_id: str, at):
        return self.repository.point_in_time(tenant_id=tenant_id, entity_id=entity_id, at=at)


temporal_materialization_service = TemporalMaterializationService()

__all__ = [
    "MaterializationError",
    "MaterializationResult",
    "TemporalMaterializationService",
    "temporal_materialization_service",
]
