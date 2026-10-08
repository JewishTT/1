"""Durable persistence for investigations.

The gap: ``api/routes/investigations.py`` kept investigations in a module-level
``dict[str, Investigation]``. The ``investigations`` table existed, and one PoW demo
script wrote to it, but the API never did. Three consequences, all of them silent:

* ``GET /investigations`` returned whatever *this process* had created, so a multi-worker
  deployment answered from a different set per worker.
* A restart lost every investigation while its context -- written to PostgreSQL by
  ``ensure_durable_context`` -- survived. The pair was half-durable: the context outlived
  the investigation it belonged to.
* ``api/routes/entities.py`` already had to read the ``investigations`` table directly to
  scope an investigation's graph, with a comment explaining it could not use the in-memory
  repo. That raw query exists because this module did not.

The repository is async and takes the caller's session, matching the other stores in
``db/``, so an investigation write and the context write that follows it can share one
transaction.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cp_domain.investigation import (
    Investigation,
    InvestigationInvalidTransition,
    InvestigationState,
)
from db.schema import Investigation as InvestigationRow


def _to_row(tenant_id: str, investigation: Investigation) -> InvestigationRow:
    return InvestigationRow(
        investigation_id=investigation.investigation_id,
        name=investigation.name,
        tenant_id=tenant_id,
        objective=dict(investigation.objective or {}),
        seeds=list(investigation.seeds or []),
        scope=dict(investigation.scope or {}),
        policy_id=investigation.policy_id,
        state=investigation.state.value,
        created_at=investigation.created_at,
        updated_at=investigation.updated_at,
    )


def _as_mapping(value: Any) -> dict[str, Any]:
    """A JSONB column as a dict, whatever the driver handed back and whatever it holds.

    ``asyncpg`` returns ``jsonb`` as ``str`` whenever a statement carries a parameter --
    the same driver behaviour the context store normalises for itself. Reading it straight
    into ``dict(...)`` raised ``ValueError: dictionary update sequence element #0 has
    length 1``, naming neither the column nor the driver.

    A value that is not a mapping becomes ``{}`` rather than raising. The column carries no
    CHECK, and a row written by an older path with a JSON array where a mapping belongs made
    the entire list endpoint fail -- one malformed row taking out every investigation, so
    the operator could not see the malformed row either. The scope of such a row is unusable
    by definition, and an empty scope is the honest rendering of that.
    """
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _as_sequence(value: Any) -> list[str]:
    """A JSONB array column as a list, tolerating the same string form."""
    if value is None:
        return []
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except ValueError:
            return []
        value = decoded
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return [str(value)]


def _from_row(row: InvestigationRow) -> Investigation:
    return Investigation(
        investigation_id=row.investigation_id,
        name=row.name,
        tenant_id=row.tenant_id,
        objective=_as_mapping(row.objective),
        seeds=_as_sequence(row.seeds),
        scope=_as_mapping(row.scope),
        policy_id=row.policy_id,
        state=InvestigationState(row.state)
        if not isinstance(row.state, InvestigationState)
        else row.state,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlInvestigationRepository:
    """Investigation persistence over the existing ``investigations`` table.

    Tenant-scoped on every read, including ``get``. A cross-tenant read returns ``None``
    rather than the row: the row is addressed by an id the caller supplied, and returning
    it would let one tenant name another's investigation.

    **Every method commits its own unit of work.** The session is injected and closed by the
    caller, so a method that only flushed left its write to be rolled back when the session
    closed. The API's dependency does exactly that -- it cannot know whether a route changed
    anything -- and the result was a ``POST /investigations`` returning ``200`` with an
    ``investigation_id`` that was not in the database: the half-durable state this
    repository exists to remove.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _commit(self) -> None:
        await self.session.commit()

    async def create(self, investigation: Investigation) -> Investigation:
        self.session.add(_to_row(investigation.tenant_id, investigation))
        await self.session.flush()
        await self._commit()
        return investigation

    async def get(
        self, investigation_id: str, *, tenant_id: str
    ) -> Investigation | None:
        if not investigation_id or not tenant_id:
            return None
        result = await self.session.execute(
            select(InvestigationRow).where(
                InvestigationRow.investigation_id == investigation_id,
                InvestigationRow.tenant_id == tenant_id,
            )
        )
        row = result.scalar_one_or_none()
        return _from_row(row) if row is not None else None

    async def list_for_tenant(
        self, tenant_id: str, *, limit: int = 500, offset: int = 0
    ) -> list[Investigation]:
        if not tenant_id:
            return []
        result = await self.session.execute(
            select(InvestigationRow)
            .where(InvestigationRow.tenant_id == tenant_id)
            .order_by(InvestigationRow.created_at.desc(), InvestigationRow.investigation_id)
            .limit(max(1, int(limit)))
            .offset(max(0, int(offset)))
        )
        return [_from_row(row) for row in result.scalars().all()]

    async def save_state(
        self, investigation_id: str, *, tenant_id: str, state: InvestigationState
    ) -> bool:
        """Persist a state transition. Returns whether a row was updated.

        The update is conditional on the tenant and writes only the state and the
        modification time. Overwriting the whole row would race a concurrent
        ``create``-time write of the seeds, and the transition is the only thing this
        method is asked to change.
        """
        result = await self.session.execute(
            update(InvestigationRow)
            .where(
                InvestigationRow.investigation_id == investigation_id,
                InvestigationRow.tenant_id == tenant_id,
            )
            .values(state=state.value, updated_at=datetime.now().astimezone())
        )
        changed = bool(result.rowcount)
        await self._commit()
        return changed

    async def transition(
        self, investigation_id: str, *, tenant_id: str, target: InvestigationState
    ) -> Investigation:
        """Apply a validated transition and persist it.

        The domain object validates the edge, not this method: ``Investigation.transition``
        knows which states may follow which, and a second implementation of that table in
        the persistence layer is how a stored state and an allowed state drift apart. An
        illegal edge raises :class:`InvestigationInvalidTransition` and writes nothing.
        """
        current = await self.get(investigation_id, tenant_id=tenant_id)
        if current is None:
            raise LookupError(f"investigation {investigation_id} not found")
        current.transition(target)
        await self.save_state(
            investigation_id, tenant_id=tenant_id, state=current.state
        )
        return current

    async def set_scope(
        self, investigation_id: str, *, tenant_id: str, scope: dict[str, Any]
    ) -> bool:
        """Widen or narrow an investigation's declared scope.

        Scope is what ``api/routes/entities.py`` reads to decide which entities belong to an
        investigation before any relation exists -- the normal state of a fresh
        investigation. Writing it through the repository is what lets that route stop
        querying the table itself.
        """
        result = await self.session.execute(
            update(InvestigationRow)
            .where(
                InvestigationRow.investigation_id == investigation_id,
                InvestigationRow.tenant_id == tenant_id,
            )
            .values(scope=scope, updated_at=datetime.now().astimezone())
        )
        changed = bool(result.rowcount)
        await self._commit()
        return changed

    async def exists(self, investigation_id: str, *, tenant_id: str) -> bool:
        if not investigation_id or not tenant_id:
            return False
        result = await self.session.execute(
            select(InvestigationRow.investigation_id).where(
                InvestigationRow.investigation_id == investigation_id,
                InvestigationRow.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none() is not None


__all__ = [
    "InvestigationInvalidTransition",
    "SqlInvestigationRepository",
    "_from_row",
    "_to_row",
]
