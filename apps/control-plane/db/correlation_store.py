"""Durable persistence for possible_match correlation edges (FR-004, I-2).

The gap this module closes: ``POST /entities/{id}/correlations`` answered ``200`` with
an edge object whose id had been minted from a repository method that did not exist, and
nothing was written. The route's own comment claimed the edges were "persisted through the
admission/review store", but that store is an in-memory stand-in (``services/review.py``),
so the edge existed only in the response body. ``GET /entities/{id}/correlations`` called
the same missing method and raised ``AttributeError``, which surfaced as a 500 -- the create
looked successful and the read looked broken.

``correlation_edges`` has been declared in ``db/schema.py`` and in the migration history
all along, with the invariant that matters: a correlation is a *possible match*, never a
merge. Keeping the row here means "the correlate stayed separate" is checkable after a
restart, which is the whole point of I-2.

The repository is async and takes the caller's session, matching ``investigation_store``
and the entity-stream store, so a correlation write can share a transaction with the
review or event that explains it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.schema import CorrelationEdge as EdgeRow
from db.schema import CorrelationEdgeState


def _as_list(value: Any) -> list[Any]:
    """A JSONB column as a list, whatever the driver handed back."""
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, Mapping):
        return [dict(value)]
    return []


def _as_edge(row: EdgeRow) -> dict[str, Any]:
    state = row.state
    return {
        "edge_id": row.edge_id,
        "candidate_a": row.candidate_a,
        "candidate_b": row.candidate_b,
        "kind": row.kind,
        "raw_pair_score": row.raw_pair_score,
        "collective_score": row.collective_score,
        "reasons": _as_list(row.reasons),
        "state": state.value if isinstance(state, CorrelationEdgeState) else str(state or ""),
        "tenant_id": row.tenant_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


class SqlCorrelationRepository:
    """Reads and writes ``correlation_edges`` through the caller's session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        tenant_id: str,
        edge_id: str,
        candidate_a: str,
        candidate_b: str,
        kind: str = "possible_match",
        raw_pair_score: float = 0.0,
        collective_score: float | None = None,
        reasons: list[str] | None = None,
        state: str = CorrelationEdgeState.OPEN.value,
    ) -> dict[str, Any]:
        row = EdgeRow(
            edge_id=edge_id,
            tenant_id=tenant_id,
            candidate_a=candidate_a,
            candidate_b=candidate_b,
            kind=kind,
            raw_pair_score=raw_pair_score,
            collective_score=collective_score,
            reasons=list(reasons or []),
            state=CorrelationEdgeState(state),
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return _as_edge(row)

    async def correlations_for_entity(
        self, *, tenant_id: str, entity_id: str
    ) -> list[dict[str, Any]]:
        """Edges with the entity on either end, newest first. Tenant-scoped."""
        statement = (
            select(EdgeRow)
            .where(
                EdgeRow.tenant_id == tenant_id,
                (EdgeRow.candidate_a == entity_id) | (EdgeRow.candidate_b == entity_id),
            )
            .order_by(EdgeRow.created_at.desc(), EdgeRow.edge_id.desc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [_as_edge(row) for row in rows]

    async def all_edge_ids(self) -> list[str]:
        """Every edge id in the database.

        ``edge_id`` is the primary key, so numbering is global -- reading only the
        current tenant's ids handed two tenants the same ``CE-1`` and the second insert
        failed on the primary key, exactly as ``ENT-`` ids did before they were minted
        globally.
        """
        rows = (await self._session.execute(select(EdgeRow.edge_id))).scalars().all()
        return list(rows)
