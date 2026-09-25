"""Durable outbox persistence for materialization launches."""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.schema import MaterializationOutbox


class SqlMaterializationOutbox:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def outbox_id(*, tenant_id: str, run_id: str) -> str:
        return "outbox-" + hashlib.sha256(f"{tenant_id}\x00{run_id}".encode()).hexdigest()[:56]

    async def get(self, *, tenant_id: str, run_id: str) -> MaterializationOutbox | None:
        result = await self.session.execute(
            select(MaterializationOutbox).where(
                MaterializationOutbox.tenant_id == tenant_id,
                MaterializationOutbox.run_id == run_id,
            )
        )
        return result.scalar_one_or_none()

    async def enqueue(
        self, *, tenant_id: str, entity_id: str, run_id: str, workflow_id: str, identity: dict[str, Any]
    ) -> MaterializationOutbox:
        existing = await self.session.execute(
            select(MaterializationOutbox).where(
                MaterializationOutbox.tenant_id == tenant_id,
                MaterializationOutbox.run_id == run_id,
            )
        )
        row = existing.scalar_one_or_none()
        if row is not None:
            return row
        row = MaterializationOutbox(
            outbox_id=self.outbox_id(tenant_id=tenant_id, run_id=run_id),
            tenant_id=tenant_id, entity_id=entity_id, run_id=run_id,
            workflow_id=workflow_id, identity=identity, status="PENDING",
            attempts=0, last_error="",
        )
        self.session.add(row)
        await self.session.commit()
        return row

    async def claim_ready(self, *, limit: int = 20) -> list[MaterializationOutbox]:
        result = await self.session.execute(
            select(MaterializationOutbox)
            .where(MaterializationOutbox.status.in_(("PENDING", "FAILED")))
            .order_by(MaterializationOutbox.available_at, MaterializationOutbox.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        rows = list(result.scalars().all())
        for row in rows:
            row.status = "DISPATCHING"
            row.attempts += 1
        await self.session.commit()
        return rows

    async def dispatched(self, row: MaterializationOutbox) -> None:
        row.status = "DISPATCHED"
        row.last_error = ""
        await self.session.commit()

    async def failed(self, row: MaterializationOutbox, reason: str, *, backoff_seconds: int = 5) -> None:
        row.status = "FAILED"
        row.last_error = str(reason)[:4000]
        row.available_at = datetime.now(UTC) + timedelta(seconds=backoff_seconds)
        await self.session.commit()


__all__ = ["SqlMaterializationOutbox"]
