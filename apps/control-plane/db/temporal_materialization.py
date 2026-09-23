"""SQLAlchemy persistence adapter for temporal materialization projections."""

from __future__ import annotations

from typing import Any

from domain.temporal_materialization import TemporalHistory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.schema import (
    MaterializationRunState,
    TemporalHistoryPublication,
    TemporalMaterializationAudit,
    TemporalMaterializationRun,
    TemporalWindowRevision,
)


class SqlTemporalMaterializationRepository:
    """Tenant-scoped publication authority for PostgreSQL deployments.

    The caller supplies an already reconciled ``TemporalHistory``. The adapter
    persists immutable revisions/publications and returns the current head; it
    never computes semantic values or reads another tenant.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def publish(
        self, history: TemporalHistory, *, run_id: str, reason: str = "materialized"
    ) -> str:
        publication = history.publication
        run = TemporalMaterializationRun(
            run_id=run_id,
            tenant_id=history.tenant_id,
            entity_id=history.entity_id,
            source_cut_id=publication.source_cut.cut_id,
            state=MaterializationRunState.PUBLISHED,
            projection_generation=publication.projection_generation,
            integrity_fingerprint=publication.integrity_fingerprint,
            payload={"publication_id": publication.publication_id},
        )
        self.session.add(run)
        for revision in publication.revisions:
            self.session.add(
                TemporalWindowRevision(
                    revision_id=revision.revision_id,
                    tenant_id=history.tenant_id,
                    entity_id=history.entity_id,
                    source_cut_id=revision.source_cut_id,
                    revision_number=revision.revision_number,
                    window_start=revision.window.window_start,
                    window_end=revision.window.window_end,
                    lifecycle_state=revision.window.lifecycle.value,
                    payload=revision.to_dict(),
                )
            )
        self.session.add(
            TemporalHistoryPublication(
                publication_id=publication.publication_id,
                tenant_id=history.tenant_id,
                entity_id=history.entity_id,
                source_cut_id=publication.source_cut.cut_id,
                projection_generation=publication.projection_generation,
                integrity_fingerprint=publication.integrity_fingerprint,
                payload=publication.to_dict(),
            )
        )
        self.session.add(
            TemporalMaterializationAudit(
                audit_id=f"audit-{publication.integrity_fingerprint[:24]}",
                tenant_id=history.tenant_id,
                entity_id=history.entity_id,
                run_id=run_id,
                action="publication.promoted",
                reason=reason,
                payload={"publication_id": publication.publication_id},
            )
        )
        await self.session.commit()
        return publication.publication_id

    async def current(self, *, tenant_id: str, entity_id: str) -> dict[str, Any] | None:
        result = await self.session.execute(
            select(TemporalHistoryPublication)
            .where(
                TemporalHistoryPublication.tenant_id == tenant_id,
                TemporalHistoryPublication.entity_id == entity_id,
            )
            .order_by(TemporalHistoryPublication.projection_generation.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return dict(row.payload) if row and row.payload else None
