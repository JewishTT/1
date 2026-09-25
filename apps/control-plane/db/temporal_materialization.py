"""SQLAlchemy persistence adapter for temporal materialization projections."""

from __future__ import annotations

import hashlib
from typing import Any

from domain.temporal_materialization import TemporalHistory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.schema import (
    MaterializationRunState,
    TemporalHistoryHead,
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

    @staticmethod
    def revision_storage_id(revision_id: str, projection_generation: int) -> str:
        """Namespace a semantic revision id by its publication generation."""
        return f"{revision_id}-g{projection_generation}"

    @staticmethod
    def audit_id(*, run_id: str, integrity_fingerprint: str) -> str:
        material = f"{run_id}:{integrity_fingerprint}".encode()
        return "audit-" + hashlib.sha256(material).hexdigest()[:48]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _head(self, *, tenant_id: str, entity_id: str) -> TemporalHistoryHead:
        result = await self.session.execute(
            select(TemporalHistoryHead)
            .where(
                TemporalHistoryHead.tenant_id == tenant_id,
                TemporalHistoryHead.entity_id == entity_id,
            )
            .with_for_update()
        )
        head = result.scalar_one_or_none()
        if head is None:
            head = TemporalHistoryHead(
                tenant_id=tenant_id,
                entity_id=entity_id,
                projection_generation=0,
            )
            self.session.add(head)
            await self.session.flush()
        return head

    async def publish(
        self, history: TemporalHistory, *, run_id: str, reason: str = "materialized"
    ) -> str:
        publication = history.publication
        head = await self._head(tenant_id=history.tenant_id, entity_id=history.entity_id)
        if publication.projection_generation <= head.projection_generation:
            existing = await self.session.execute(
                select(TemporalHistoryPublication).where(
                    TemporalHistoryPublication.tenant_id == history.tenant_id,
                    TemporalHistoryPublication.entity_id == history.entity_id,
                    TemporalHistoryPublication.integrity_fingerprint
                    == publication.integrity_fingerprint,
                )
            )
            prior = existing.scalar_one_or_none()
            if prior is not None:
                return str(prior.publication_id)
            raise ValueError("stale projection generation")
        existing_run = await self.session.execute(
            select(TemporalMaterializationRun).where(
                TemporalMaterializationRun.run_id == run_id,
                TemporalMaterializationRun.tenant_id == history.tenant_id,
                TemporalMaterializationRun.entity_id == history.entity_id,
            )
        )
        prior = existing_run.scalar_one_or_none()
        if prior is not None:
            if prior.integrity_fingerprint != publication.integrity_fingerprint:
                raise ValueError("run_id already published with a different fingerprint")
            return str((prior.payload or {}).get("publication_id", publication.publication_id))
        existing_publication = await self.session.execute(
            select(TemporalHistoryPublication).where(
                TemporalHistoryPublication.tenant_id == history.tenant_id,
                TemporalHistoryPublication.entity_id == history.entity_id,
                TemporalHistoryPublication.integrity_fingerprint
                == publication.integrity_fingerprint,
            )
        )
        prior_publication = existing_publication.scalar_one_or_none()
        if prior_publication is not None:
            # The fingerprint is the immutable content identity. A later run
            # carrying identical evidence reuses that publication instead of
            # colliding on publication/revision/audit primary keys.
            return str(prior_publication.publication_id)
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
                    revision_id=self.revision_storage_id(
                        revision.revision_id, publication.projection_generation
                    ),
                    tenant_id=history.tenant_id,
                    entity_id=history.entity_id,
                    source_cut_id=revision.source_cut_id,
                    revision_number=revision.revision_number,
                    projection_generation=publication.projection_generation,
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
                audit_id=self.audit_id(
                    run_id=run_id, integrity_fingerprint=publication.integrity_fingerprint
                ),
                tenant_id=history.tenant_id,
                entity_id=history.entity_id,
                run_id=run_id,
                action="publication.promoted",
                reason=reason,
                payload={"publication_id": publication.publication_id},
            )
        )
        head.projection_generation = publication.projection_generation
        head.publication_id = publication.publication_id
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
            .with_for_update()
        )
        row = result.scalar_one_or_none()
        return dict(row.payload) if row and row.payload else None
