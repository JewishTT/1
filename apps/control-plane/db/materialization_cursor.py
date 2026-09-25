"""Durable checkpoints for Common Crawl materialization work items."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.schema import MaterializationCursor


class SqlMaterializationCursorRepository:
    """Tenant-scoped idempotent cursor updates for Temporal retries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def cursor_id(*, tenant_id: str, entity_id: str, run_id: str, crawl: str, page: int) -> str:
        material = f"{tenant_id}\x00{entity_id}\x00{run_id}\x00{crawl}\x00{page}"
        return "cursor-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:64]

    async def get(
        self, *, tenant_id: str, entity_id: str, run_id: str, crawl: str, page: int
    ) -> MaterializationCursor | None:
        result = await self.session.execute(
            select(MaterializationCursor).where(
                MaterializationCursor.tenant_id == tenant_id,
                MaterializationCursor.entity_id == entity_id,
                MaterializationCursor.run_id == run_id,
                MaterializationCursor.crawl == crawl,
                MaterializationCursor.page == page,
            )
        )
        return result.scalar_one_or_none()

    async def ensure(
        self, *, tenant_id: str, entity_id: str, run_id: str, crawl: str, page: int
    ) -> MaterializationCursor:
        existing = await self.get(
            tenant_id=tenant_id, entity_id=entity_id, run_id=run_id, crawl=crawl, page=page
        )
        if existing is not None:
            return existing
        row = MaterializationCursor(
            cursor_id=self.cursor_id(
                tenant_id=tenant_id, entity_id=entity_id, run_id=run_id, crawl=crawl, page=page
            ),
            tenant_id=tenant_id,
            entity_id=entity_id,
            run_id=run_id,
            crawl=crawl,
            page=page,
            status="PENDING",
            last_error="",
        )
        self.session.add(row)
        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            existing = await self.get(
                tenant_id=tenant_id, entity_id=entity_id, run_id=run_id, crawl=crawl, page=page
            )
            if existing is None:
                raise
            return existing
        return row

    async def prepare(
        self,
        row: MaterializationCursor,
        *,
        result_payload: dict[str, Any],
    ) -> MaterializationCursor:
        """Persist deterministic work output before the external side effect.

        A retry can then replay the exact same records even if the process died
        after the cursor commit but before the WARC/entity-stream transaction.
        """
        row.status = "PROCESSING"
        row.last_error = ""
        row.result_payload = result_payload
        await self.session.commit()
        return row

    async def complete(
        self, row: MaterializationCursor, *, result_payload: dict[str, Any] | None = None
    ) -> MaterializationCursor:
        row.status = "COMPLETED"
        row.last_error = ""
        if result_payload is not None:
            row.result_payload = result_payload
        row.completed_at = datetime.now(UTC)
        await self.session.flush()
        return row

    async def fail(self, row: MaterializationCursor, reason: str) -> MaterializationCursor:
        row.status = "FAILED"
        row.last_error = str(reason)[:4000]
        await self.session.flush()
        return row

    async def is_completed(
        self, *, tenant_id: str, entity_id: str, run_id: str, crawl: str, page: int
    ) -> bool:
        row = await self.get(
            tenant_id=tenant_id, entity_id=entity_id, run_id=run_id, crawl=crawl, page=page
        )
        return row is not None and row.status == "COMPLETED"

    async def counts(self, *, tenant_id: str, entity_id: str, run_id: str) -> dict[str, int]:
        result = await self.session.execute(
            select(MaterializationCursor.status).where(
                MaterializationCursor.tenant_id == tenant_id,
                MaterializationCursor.entity_id == entity_id,
                MaterializationCursor.run_id == run_id,
            )
        )
        counts: dict[str, int] = {}
        for status in result.scalars().all():
            counts[str(status)] = counts.get(str(status), 0) + 1
        return counts


__all__ = ["SqlMaterializationCursorRepository"]
