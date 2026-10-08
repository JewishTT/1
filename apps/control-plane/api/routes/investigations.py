"""Investigation API routes (T024, FR-003, US1).

create/update/pause/resume/archive; emits ``investigation.created|.started|.updated``
events. Investigations are persisted to PostgreSQL through
:class:`db.investigation_store.SqlInvestigationRepository`.

The repository is a real dependency rather than a module-level ``dict``. The dict made
``GET /investigations`` answer from whatever one process happened to have created, lost
every investigation on restart while its context survived in the database, and forced
``api/routes/entities.py`` to query the ``investigations`` table directly because the
in-memory copy was not trustworthy as a source of scope. The dict remains only as the
degradation when no database session can be opened, so a developer running without
PostgreSQL still gets a working smoke path -- and a single-process answer, which is all it
ever was.

Creating an investigation also creates its durable ``InvestigationContext``. That was the
first manual step in the loop -- an analyst had to POST the question to a second endpoint
before anything was recorded durably -- and it meant a context could exist without an
investigation and an investigation could exist without a context. The context is what the
research loop iterates over, so an investigation that has none is not a live investigation.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from security import SecurityBlocked, validate_seed_url
from sqlalchemy import update

from api.auth import TenantContext, resolve_tenant
from cp_domain.investigation import (
    Investigation,
    InvestigationInvalidTransition,
    InvestigationState,
    InvestigationValidationError,
)
from db.schema import Investigation as InvestigationRow

router = APIRouter(prefix="/investigations", tags=["investigations"])

#: Degradation-only store for a process with no database. Never the authority: it is
#: process-local by construction, which is the defect it exists to tolerate.
_repo: dict[str, Investigation] = {}


async def investigation_repository() -> AsyncIterator[Any]:
    """Yield a durable investigation repository, or the in-memory fallback.

    The two phases are separate ``try`` blocks on purpose. FastAPI throws an endpoint's
    exception *into* this generator to close it, so a handler that spans the ``yield`` would
    catch the endpoint's own 422 and try to yield a second time -- which a generator may not
    do, and which surfaces as ``RuntimeError: generator didn't stop after athrow()`` on
    every request that legitimately fails. Here the session is opened *before* the yield and
    any endpoint failure runs the ``finally`` without being caught.
    """
    session = None
    try:
        from db.investigation_store import SqlInvestigationRepository
        from db.session import make_session_factory

        session = make_session_factory()()
        repository = SqlInvestigationRepository(session)
    except Exception:  # noqa: BLE001 - no database configured or reachable
        # Falls back rather than failing: the alternative is a 503 on every investigation
        # endpoint whenever PostgreSQL is unavailable, which turns a degradation into an
        # outage of the whole API. The in-memory path is honest about what it is.
        yield None
        return
    try:
        yield repository
    finally:
        await session.close()


class InvestigationCreate(BaseModel):
    name: str
    objective: dict = Field(default_factory=dict)
    seeds: list[str] = Field(default_factory=list)
    scope: dict = Field(default_factory=dict)
    policy_id: str | None = None
    # The natural-language question the investigation exists to answer. Optional: an
    # investigation may be opened before the analyst knows how to phrase it, and an empty
    # question is stored as an empty question rather than silently defaulting to the title.
    question: str = ""


class InvestigationUpdate(BaseModel):
    objective: dict | None = None
    scope: dict | None = None
    policy_id: str | None = None
    # ``question`` is deliberately NOT updatable here. The context is content-addressed and
    # immutable, so a changed question is a different context, not an edit -- and
    # investigation-context lookups are keyed by investigation_id, which would then resolve
    # to one of two contexts arbitrarily. Amending the framing of a live investigation needs
    # a context revision that supersedes the prior one; that operation does not exist yet,
    # and faking it with a second row would be worse than not offering it.


def _evented(state: InvestigationState) -> str:
    return {
        InvestigationState.DRAFT: "investigation.updated",
        InvestigationState.PLANNING: "investigation.started",
        InvestigationState.RUNNING: "investigation.started",
        InvestigationState.PAUSED: "investigation.paused",
        InvestigationState.COMPLETED: "investigation.completed",
        InvestigationState.ARCHIVED: "investigation.archived",
    }[state]


async def ensure_durable_context(
    investigation_id: str,
    tenant_id: str,
    *,
    title: str,
    question: str = "",
) -> str:
    """Return the context id for this investigation, creating it if absent.

    Idempotent on purpose. Calling it twice must not create a second context: the context id
    is content-addressed, but a second write with a *different* question is a different
    context, so a duplicate call after the analyst edits the question would fork the
    investigation's state. The first context wins and the caller is told which one.

    Fails loudly. A context that was not persisted is a context the research loop cannot
    iterate over, and returning a fabricated id would hide that until the first ingest.
    """
    from domain.investigation_context import InvestigationContext

    from context_engine.postgres_store import PostgresContextStore
    from db.session import make_session_factory

    store = PostgresContextStore(tenant_id=tenant_id, connection_factory=make_session_factory())

    async with store._session() as conn:
        from sqlalchemy import text

        found = await conn.execute(
            text("SELECT context_id FROM investigation_contexts WHERE investigation_id = :inv"),
            {"inv": investigation_id},
        )
        row = found.mappings().first()
    if row is not None:
        return str(row["context_id"])

    context = InvestigationContext(
        tenant_id=tenant_id,
        investigation_id=investigation_id,
        title=title,
        question=question,
        scope_refs=(investigation_id,),
    )
    try:
        await store.put_context(context)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"context could not be persisted for {investigation_id}: {exc}",
        ) from exc
    return context.context_id


@router.post("")
async def create_investigation(
    body: InvestigationCreate,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
    repo: Annotated[Any, Depends(investigation_repository)] = None,
) -> dict:
    # FR-029 fail-closed: reject forbidden/invalid seed URLs before any fetch.
    for seed in body.seeds or ["http://fixtures.local/sitemap.xml"]:
        try:
            validate_seed_url(seed)
        except SecurityBlocked as exc:
            raise HTTPException(status_code=422, detail=f"seed rejected: {exc}") from exc

    inv = Investigation(
        investigation_id="INV-" + uuid.uuid4().hex[:12],
        name=body.name,
        tenant_id=ctx.tenant_id,
        objective=body.objective,
        seeds=body.seeds or ["http://fixtures.local/sitemap.xml"],
        scope=body.scope or {"source_classes": ["HTTP", "RSS"], "time_range": {}},
        policy_id=body.policy_id or "policies/default",
        state=InvestigationState.RUNNING,
    )
    try:
        inv.validate()
    except InvestigationValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if repo is not None:
        await repo.create(inv)
    else:
        _repo[inv.investigation_id] = inv

    # The investigation's context is durable from birth. If this fails the whole request
    # fails: an investigation whose context is missing is an investigation the loop cannot
    # advance, and a half-created pair is worse than a rejected request.
    context_id = await ensure_durable_context(
        inv.investigation_id,
        inv.tenant_id,
        title=inv.name,
        question=body.question,
    )

    # Emit investigation.created (protobuf envelope produced by event layer on real impl).
    #
    # The workflow is started here, not by a caller: before this, an investigation was a
    # durable row that nothing ever ran, and the acquire loop that was written to advance it
    # had no production caller. Failures are reported in the response rather than raised --
    # the row is durable and a workflow can be started later by
    # ``services.investigation_scheduler.recover_unstarted``, so a Temporal outage must not
    # fail the creation.
    scheduler: dict[str, Any] = {}
    try:
        from services.investigation_scheduler import start_investigation

        outcome = await start_investigation(inv.investigation_id)
        scheduler = outcome.as_dict()
    except Exception as exc:  # noqa: BLE001 - a scheduling failure is not a creation failure
        scheduler = {"started": False, "reason": f"scheduler_error:{type(exc).__name__}"}

    return {
        "investigation_id": inv.investigation_id,
        "context_id": context_id,
        "name": inv.name,
        "state": inv.state.value,
        "event": "investigation.created",
        "tenant_id": inv.tenant_id,
        "question": body.question,
        "workflow": scheduler,
    }


@router.get("")
async def list_investigations(
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
    repo: Annotated[Any, Depends(investigation_repository)] = None,
) -> dict:
    if repo is not None:
        items = await repo.list_for_tenant(ctx.tenant_id)
    else:
        items = [i for i in _repo.values() if i.tenant_id == ctx.tenant_id]
    return {"investigations": [_serialize(i) for i in items]}


@router.get("/{investigation_id}")
async def get_investigation(
    investigation_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
    repo: Annotated[Any, Depends(investigation_repository)] = None,
) -> dict:
    inv = await _get_or_404(investigation_id, ctx.tenant_id, repo)
    return _serialize(inv)


@router.patch("/{investigation_id}")
async def update_investigation(
    investigation_id: str,
    body: InvestigationUpdate,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
    repo: Annotated[Any, Depends(investigation_repository)] = None,
) -> dict:
    inv = await _get_or_404(investigation_id, ctx.tenant_id, repo)
    if body.objective is not None:
        inv.objective = body.objective
    if body.scope is not None:
        inv.scope = body.scope
    if body.policy_id is not None:
        inv.policy_id = body.policy_id
    # Objective, scope and policy are not the state, so ``save_state`` would silently drop
    # them. The durable write has to carry the whole record.
    if repo is not None:
        await repo.session.execute(
            update(InvestigationRow)
            .where(
                InvestigationRow.investigation_id == investigation_id,
                InvestigationRow.tenant_id == ctx.tenant_id,
            )
            .values(
                objective=dict(inv.objective or {}),
                scope=dict(inv.scope or {}),
                policy_id=inv.policy_id,
            )
        )
        await repo.session.commit()
    else:
        _repo[inv.investigation_id] = inv
    return _serialize(inv)


@router.post("/{investigation_id}/pause")
async def pause_investigation(
    investigation_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
    repo: Annotated[Any, Depends(investigation_repository)] = None,
) -> dict:
    inv = await _get_or_404(investigation_id, ctx.tenant_id, repo)
    _safe_transition(inv, InvestigationState.PAUSED)
    await _persist(inv, repo)
    return _serialize(inv)


@router.post("/{investigation_id}/resume")
async def resume_investigation(
    investigation_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
    repo: Annotated[Any, Depends(investigation_repository)] = None,
) -> dict:
    inv = await _get_or_404(investigation_id, ctx.tenant_id, repo)
    _safe_transition(inv, InvestigationState.RUNNING)
    await _persist(inv, repo)
    return _serialize(inv)


@router.post("/{investigation_id}/complete")
async def complete_investigation(
    investigation_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
    repo: Annotated[Any, Depends(investigation_repository)] = None,
) -> dict:
    inv = await _get_or_404(investigation_id, ctx.tenant_id, repo)
    _safe_transition(inv, InvestigationState.COMPLETED)
    await _persist(inv, repo)
    return _serialize(inv)


@router.post("/{investigation_id}/archive")
async def archive_investigation(
    investigation_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
    repo: Annotated[Any, Depends(investigation_repository)] = None,
) -> dict:
    inv = await _get_or_404(investigation_id, ctx.tenant_id, repo)
    _safe_transition(inv, InvestigationState.ARCHIVED)
    await _persist(inv, repo)
    return _serialize(inv)


async def _load(investigation_id: str, tenant_id: str, repo: Any) -> Investigation | None:
    """Read one investigation, from the repository when there is one.

    The in-memory path still checks the tenant. A process-local dict is not a security
    boundary, but a fallback that dropped the check would return another tenant's
    investigation in exactly the deployments least able to be audited.
    """
    if repo is not None:
        return await repo.get(investigation_id, tenant_id=tenant_id)
    inv = _repo.get(investigation_id)
    if inv is None or inv.tenant_id != tenant_id:
        return None
    return inv


async def _persist(inv: Investigation, repo: Any) -> None:
    """Write a mutated investigation back through whichever store is in use."""
    if repo is None:
        _repo[inv.investigation_id] = inv
        return
    await repo.save_state(
        inv.investigation_id, tenant_id=inv.tenant_id, state=inv.state
    )


async def _get_or_404(
    investigation_id: str, tenant_id: str, repo: Any = None
) -> Investigation:
    inv = await _load(investigation_id, tenant_id, repo)
    if inv is None:
        raise HTTPException(status_code=404, detail="investigation not found")
    return inv


def _safe_transition(inv: Investigation, target: InvestigationState) -> None:
    try:
        inv.transition(target)
    except InvestigationInvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _serialize(inv: Investigation) -> dict:
    return {
        "investigation_id": inv.investigation_id,
        "name": inv.name,
        "tenant_id": inv.tenant_id,
        "objective": inv.objective,
        "seeds": inv.seeds,
        "scope": inv.scope,
        "policy_id": inv.policy_id,
        "state": inv.state.value,
        "created_at": inv.created_at.isoformat(),
    }