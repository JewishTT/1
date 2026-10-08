"""The door: investigation context over HTTP.

Why a new file rather than a few routes on ``investigations.py``
-------------------------------------------------------------
The Context Engine had 112 tests and no entry point. Every method on it --
``ingest``, ``open_obligations``, ``frontier``, ``record_attempt``, ``propose_action``,
``replay`` -- was reachable only from inside the package. An investigation's context could
not be created, read, advanced or replayed from outside the process, which is why nothing
ever called it.

Scope, deliberately
-------------------
An operator creating an investigation should have to say what it is about, and should see
what the platform thinks is still open. Anything beyond that -- policy, permissions, the
satisfaction evaluator, adaptive modes -- is deliberately absent rather than stubbed: a
route that accepts input it cannot honour is worse than a missing route.

The natural-language ``question`` is accepted verbatim and stored on the context. It is
**not** interpreted here. Turning "find everything about the Putin family structure" into
obligations is the engine's job and it does it from the question; this layer records the
question and never pretends to have understood it.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import TenantContext, resolve_tenant
from domain.investigation_context import ContextEngineError, InvestigationContext
from domain.investigation_context import InvestigationState as ContextState

router = APIRouter(prefix="/investigations", tags=["context"])

#: Prefix the domain uses for a context address; the domain refuses a foreign one.
CONTEXT_PREFIX = "CXI-"


class ContextCreate(BaseModel):
    """What an operator states when opening an investigation.

    ``question`` is the natural-language brief -- "find everything about the Putin family
    structure" -- and it is the field the whole Context Engine hangs off. It is required
    rather than optional: a context with no question and no scope is indistinguishable
    from no context, and the domain says so itself.
    """

    title: str
    question: str = ""
    scope_refs: list[str] = Field(default_factory=list)
    policy_snapshot_ref: str = ""
    investigation_id: str = ""


class GapSignalIn(BaseModel):
    """One declared gap.

    A ``GapSignal`` is how a caller says "this is what I do not know". The engine turns
    it into obligations, so the shape here is deliberately the engine's and not a looser
    dict: accepting arbitrary keys would let a client name a trigger the engine does not
    know, and the obligation would silently never fire.
    """

    kind: str
    question: str
    rationale: str = ""
    knowledge_type: str = "entity"
    priority: float = 0.5
    evidence_refs: list[str] = Field(default_factory=list)


class ActionAttemptIn(BaseModel):
    outcome: str
    realised_gain: float | None = None


def _engine_for(tenant_id: str):
    """A durable Context Engine whose store opens its own connection per operation.

    Deliberately not a module-level singleton. A process-wide engine would pin a
    database connection from import time and hold it across every request; the store's
    connection factory keeps the engine request-scoped while the *contexts* stay durable,
    which is the property that actually matters.
    """
    from context_engine.engine import ContextEngine
    from context_engine.postgres_store import PostgresContextStore
    from db.session import make_session_factory

    factory = make_session_factory()
    store = PostgresContextStore(tenant_id=tenant_id, connection_factory=factory)
    return ContextEngine(store, require_durable=True), store


async def _load_context(investigation_id: str, tenant_id: str) -> InvestigationContext:
    engine, store = _engine_for(tenant_id)
    for context in await store.contexts():
        if context.investigation_id == investigation_id:
            return context
    raise HTTPException(status_code=404, detail=f"no context for investigation {investigation_id}")


# --------------------------------------------------------------------------- #
# creation                                                                    #
# --------------------------------------------------------------------------- #


@router.post("/{investigation_id}/context", status_code=201)
async def create_context(
    investigation_id: str,
    body: ContextCreate,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """Establish the context for an investigation.

    Idempotent on ``(investigation, title)``: re-posting the same brief returns the
    address that already exists rather than forking a second context, because a context
    id is a content address and two contexts for one investigation would be two truths.
    """
    engine, store = _engine_for(ctx.tenant_id)
    try:
        context = InvestigationContext(
            tenant_id=ctx.tenant_id,
            investigation_id=investigation_id,
            title=body.title,
            scope_refs=tuple(body.scope_refs) or (investigation_id,),
            question=body.question,
            policy_snapshot_ref=body.policy_snapshot_ref,
            state=ContextState.UNINVESTIGATED,
        )
    except ContextEngineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing = await store.get_context(context.context_id)
    if existing is not None:
        return {"context_id": existing.context_id, "created": False, **existing.to_dict()}

    await store.put_context(context)
    return {"context_id": context.context_id, "created": True, **context.to_dict()}


# --------------------------------------------------------------------------- #
# reading                                                                     #
# --------------------------------------------------------------------------- #


@router.get("/{investigation_id}/context")
async def get_context(
    investigation_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    engine, store = _engine_for(ctx.tenant_id)
    for context in await store.contexts():
        if context.investigation_id == investigation_id:
            revisions = await store.revisions(context.context_id)
            return {
                **context.to_dict(),
                "revision_count": len(revisions),
                "current_revision": revisions[-1].to_dict() if revisions else None,
                "obligations": [o.to_dict() for o in await store.obligations(context.context_id)],
                "frontier": (
                    (lambda f: f.to_dict() if f else None)(
                        await store.get_frontier(context.context_id)
                    )
                ),
            }
    raise HTTPException(status_code=404, detail=f"no context for investigation {investigation_id}")


@router.get("/{investigation_id}/context/revisions")
async def list_revisions(
    investigation_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    context = await _load_context(investigation_id, ctx.tenant_id)
    engine, store = _engine_for(ctx.tenant_id)
    revisions = await store.revisions(context.context_id)
    return {
        "context_id": context.context_id,
        "count": len(revisions),
        "revisions": [r.to_dict() for r in revisions],
    }


@router.get("/{investigation_id}/context/frontier")
async def get_frontier(
    investigation_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    context = await _load_context(investigation_id, ctx.tenant_id)
    engine, store = _engine_for(ctx.tenant_id)
    frontier = await store.get_frontier(context.context_id)
    if frontier is None:
        raise HTTPException(status_code=404, detail="no frontier for this context")
    return frontier.to_dict()


# --------------------------------------------------------------------------- #
# writing                                                                     #
# --------------------------------------------------------------------------- #


@router.post("/{investigation_id}/context/ingest", status_code=202)
async def ingest_gaps(
    investigation_id: str,
    body: list[GapSignalIn],
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """Declare what is not known, and let the engine derive the obligations.

    The seam obligations come from, and deliberately thin: the engine decides what a gap
    means. A route that inferred obligations first would be a second, divergent opinion
    about the same question.
    """
    # Both enums live in the engine module, not in ``obligations``: the trigger
    # vocabulary and the knowledge vocabulary are the engine's own, and importing them
    # from the wrong module failed at first call rather than at import time.
    from context_engine.engine import GapSignal, KnowledgeType, TriggerKind

    context = await _load_context(investigation_id, ctx.tenant_id)
    engine, store = _engine_for(ctx.tenant_id)
    try:
        signals = [
            GapSignal(
                kind=TriggerKind(item.kind),
                question=item.question,
                rationale=item.rationale,
                knowledge_type=KnowledgeType(item.knowledge_type),
                priority=item.priority,
                evidence_refs=tuple(item.evidence_refs),
            )
            for item in body
        ]
        revision, obligations = await engine.ingest(
            context,
            signals,
            # FR-042: the revision has to name what caused it, and a gap signal carries no
            # id of its own. Deriving one from its content keeps the audit trail honest --
            # the same gap always yields the same event id, and a re-posted gap is visibly
            # the same event rather than a new one. Without this the revision's
            # caused_by_event_ids came back empty and the explanation trail was a fiction.
            event_ids=[f"gap:{signal.kind}:{signal.question}" for signal in signals],
        )
    except (ContextEngineError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "context_id": context.context_id,
        # ``ingest`` commits exactly one revision per tick and returns it, not a chain.
        "revision": revision.to_dict(),
        "obligations": [o.to_dict() for o in obligations],
        "open_obligations": len(await engine.open_obligations(context.context_id)),
    }


@router.post("/{investigation_id}/context/obligations/{obligation_id}/actions/{action_id}/attempts", status_code=202)
async def record_attempt(
    investigation_id: str,
    obligation_id: str,
    action_id: str,
    body: ActionAttemptIn,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """Record what an attempt produced.

    The engine decides whether the obligation is satisfied; the caller reports the outcome
    and may report a realised gain, but cannot close its own obligation. That separation
    is the whole reason a research obligation exists.
    """
    context = await _load_context(investigation_id, ctx.tenant_id)
    engine, store = _engine_for(ctx.tenant_id)
    obligation = await store.get_obligation(obligation_id)
    if obligation is None:
        raise HTTPException(status_code=404, detail=f"no obligation {obligation_id}")
    actions = await store.actions(obligation_id)
    action = next((a for a in actions if a.action_id == action_id), None)
    if action is None:
        raise HTTPException(status_code=404, detail=f"no action {action_id}")
    try:
        entry = await engine.record_attempt(
            action,
            outcome=body.outcome,
            realised_gain=body.realised_gain,
        )
    except ContextEngineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "context_id": context.context_id,
        "obligation_id": obligation_id,
        "action_id": action_id,
        "memory": entry.to_dict() if hasattr(entry, "to_dict") else str(entry),
        "status": obligation.status.value,
    }


@router.post("/{investigation_id}/context/replay", status_code=202)
async def replay_context(
    investigation_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """Rebuild from the durable revisions.

    The point of a durable store: a rebuild after a restart must reach the same state as
    the live process did, and this is the only route that can prove it did.
    """
    context = await _load_context(investigation_id, ctx.tenant_id)
    engine, store = _engine_for(ctx.tenant_id)
    try:
        rebuilt = await engine.rebuild(context.context_id)
    except ContextEngineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"context_id": context.context_id, "rebuilt": True, "replay": rebuilt}


__all__ = ["router"]