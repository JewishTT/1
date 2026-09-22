"""Investigation API routes (T024, FR-003, US1).

create/update/pause/resume/archive; emits ``investigation.created|.started|.updated``
events. Uses an in-memory repo for the smoke path (DB persistence via db/schema.py
is wired in at the app layer when a DB session is present).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from security import SecurityBlocked, validate_seed_url

from api.auth import TenantContext, resolve_tenant
from cp_domain.investigation import (
    Investigation,
    InvestigationInvalidTransition,
    InvestigationState,
    InvestigationValidationError,
)

router = APIRouter(prefix="/investigations", tags=["investigations"])

# In-memory repository (smoke / quickstart path; DB-backed repo injected by app).
_repo: dict[str, Investigation] = {}


class InvestigationCreate(BaseModel):
    name: str
    objective: dict = Field(default_factory=dict)
    seeds: list[str] = Field(default_factory=list)
    scope: dict = Field(default_factory=dict)
    policy_id: str | None = None


class InvestigationUpdate(BaseModel):
    objective: dict | None = None
    scope: dict | None = None
    policy_id: str | None = None


def _evented(state: InvestigationState) -> str:
    return {
        InvestigationState.DRAFT: "investigation.updated",
        InvestigationState.PLANNING: "investigation.started",
        InvestigationState.RUNNING: "investigation.started",
        InvestigationState.PAUSED: "investigation.paused",
        InvestigationState.COMPLETED: "investigation.completed",
        InvestigationState.ARCHIVED: "investigation.archived",
    }[state]


@router.post("")
async def create_investigation(
    body: InvestigationCreate,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
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
    _repo[inv.investigation_id] = inv
    # Emit investigation.created (protobuf envelope produced by event layer on real impl).
    return {
        "investigation_id": inv.investigation_id,
        "name": inv.name,
        "state": inv.state.value,
        "event": "investigation.created",
        "tenant_id": inv.tenant_id,
    }


@router.get("")
async def list_investigations(ctx: Annotated[TenantContext, Depends(resolve_tenant)]) -> dict:
    items = [i for i in _repo.values() if i.tenant_id == ctx.tenant_id]
    return {"investigations": [_serialize(i) for i in items]}


@router.get("/{investigation_id}")
async def get_investigation(
    investigation_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    inv = _get_or_404(investigation_id, ctx.tenant_id)
    return _serialize(inv)


@router.patch("/{investigation_id}")
async def update_investigation(
    investigation_id: str,
    body: InvestigationUpdate,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    inv = _get_or_404(investigation_id, ctx.tenant_id)
    if body.objective is not None:
        inv.objective = body.objective
    if body.scope is not None:
        inv.scope = body.scope
    if body.policy_id is not None:
        inv.policy_id = body.policy_id
    return _serialize(inv)


@router.post("/{investigation_id}/pause")
async def pause_investigation(
    investigation_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    inv = _get_or_404(investigation_id, ctx.tenant_id)
    _safe_transition(inv, InvestigationState.PAUSED)
    return _serialize(inv)


@router.post("/{investigation_id}/resume")
async def resume_investigation(
    investigation_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    inv = _get_or_404(investigation_id, ctx.tenant_id)
    _safe_transition(inv, InvestigationState.RUNNING)
    return _serialize(inv)


@router.post("/{investigation_id}/complete")
async def complete_investigation(
    investigation_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    inv = _get_or_404(investigation_id, ctx.tenant_id)
    _safe_transition(inv, InvestigationState.COMPLETED)
    return _serialize(inv)


@router.post("/{investigation_id}/archive")
async def archive_investigation(
    investigation_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    inv = _get_or_404(investigation_id, ctx.tenant_id)
    _safe_transition(inv, InvestigationState.ARCHIVED)
    return _serialize(inv)


def _get_or_404(investigation_id: str, tenant_id: str) -> Investigation:
    inv = _repo.get(investigation_id)
    if inv is None or inv.tenant_id != tenant_id:
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