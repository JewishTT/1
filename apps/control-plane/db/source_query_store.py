"""Durable SQL access to the multi-route source query set (feature 015, US2).

The planner in :mod:`acquisition.source_query_set` is pure and deterministic.
This repository persists its output so a run can report *which* routes it
executed and which it could not, and so frontier entries can reference a stable
query identity across runs (FR-006, FR-007).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.schema import SourceQuery as SourceQueryRow
from db.schema import SourceQuerySet as SourceQuerySetRow

__all__ = ["SqlSourceQueryStore", "surface_digest"]


def surface_digest(surface: Any) -> str:
    """Stable digest of the search surface a plan was derived from.

    Stored so a stored plan can later be checked against the surface that would
    now produce it, without re-running the planner.
    """
    payload = surface.as_dict() if hasattr(surface, "as_dict") else dict(surface)
    material = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(material.encode()).hexdigest()


def _to_row(query_set: Any, *, tenant_id: str, digest: str) -> SourceQuerySetRow:
    return SourceQuerySetRow(
        query_set_id=query_set.query_set_id,
        tenant_id=tenant_id,
        entity_id=query_set.entity_id,
        identity_fingerprint=query_set.identity_fingerprint,
        surface_digest=digest,
        query_count=len(query_set.queries),
        executable_count=query_set.executable_count,
        unsupported_count=query_set.unsupported_count,
    )


def _query_rows(query_set: Any, *, tenant_id: str) -> list[SourceQueryRow]:
    return [
        SourceQueryRow(
            query_id=query.query_id,
            query_set_id=query_set.query_set_id,
            tenant_id=tenant_id,
            entity_id=query_set.entity_id,
            ordinal=query.ordinal,
            route_kind=query.route_kind,
            query_value=query.query_value,
            match_type=query.match_type,
            surt_prefix=query.surt_prefix,
            provider=query.provider,
            executable=query.executable,
            unsupported_reason=query.unsupported_reason,
            origin_refs=list(query.origin_refs),
        )
        for query in query_set.queries
    ]


class SqlSourceQueryStore:
    """Tenant-scoped persistence for query sets and their routes."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_set(
        self, *, tenant_id: str, entity_id: str
    ) -> SourceQuerySetRow | None:
        result = await self.session.execute(
            select(SourceQuerySetRow).where(
                SourceQuerySetRow.tenant_id == tenant_id,
                SourceQuerySetRow.entity_id == entity_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_queries(
        self, *, tenant_id: str, entity_id: str
    ) -> tuple[SourceQueryRow, ...]:
        """Return every stored route, executable or declared-unsupported."""
        result = await self.session.execute(
            select(SourceQueryRow)
            .where(
                SourceQueryRow.tenant_id == tenant_id,
                SourceQueryRow.entity_id == entity_id,
            )
            .order_by(SourceQueryRow.ordinal)
        )
        return tuple(result.scalars().all())

    async def get_executable(
        self, *, tenant_id: str, entity_id: str
    ) -> tuple[SourceQueryRow, ...]:
        """Return only routes a provider can execute (FR-001)."""
        result = await self.session.execute(
            select(SourceQueryRow)
            .where(
                SourceQueryRow.tenant_id == tenant_id,
                SourceQueryRow.entity_id == entity_id,
                SourceQueryRow.executable.is_(True),
            )
            .order_by(SourceQueryRow.ordinal)
        )
        return tuple(result.scalars().all())

    async def get_unsupported(
        self, *, tenant_id: str, entity_id: str
    ) -> tuple[SourceQueryRow, ...]:
        """Return declared-unsupported routes with their reasons (FR-004)."""
        result = await self.session.execute(
            select(SourceQueryRow)
            .where(
                SourceQueryRow.tenant_id == tenant_id,
                SourceQueryRow.entity_id == entity_id,
                SourceQueryRow.executable.is_(False),
            )
            .order_by(SourceQueryRow.ordinal)
        )
        return tuple(result.scalars().all())

    async def persist(
        self, *, tenant_id: str, surface: Any, query_set: Any
    ) -> SourceQuerySetRow:
        """Persist a plan idempotently.

        Re-planning the same identity is a no-op: the existing rows are returned
        rather than duplicated, so a retried run cannot fork the route set.
        """
        existing = await self.get_set(tenant_id=tenant_id, entity_id=query_set.entity_id)
        if existing is not None:
            return existing

        row = _to_row(query_set, tenant_id=tenant_id, digest=surface_digest(surface))
        self.session.add(row)
        for query_row in _query_rows(query_set, tenant_id=tenant_id):
            self.session.add(query_row)
        try:
            await self.session.commit()
        except IntegrityError:
            # Another writer planned the same identity concurrently.
            await self.session.rollback()
            found = await self.get_set(tenant_id=tenant_id, entity_id=query_set.entity_id)
            if found is None:
                raise
            return found
        return row
