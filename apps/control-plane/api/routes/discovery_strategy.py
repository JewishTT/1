"""Tenant-scoped preview API for the Context-to-Discovery compiler.

This endpoint plans bounded public-search tasks. It does not dispatch them: the
existing Dispatcher remains responsible for policy, durable budget reservation,
source capability resolution and Redpanda emission.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from api.auth import TenantContext, require_analyst
from db.schema import Investigation as InvestigationRow
from db.session import make_session_factory
from context_discovery import (
    DEFAULT_FACETS,
    ContextDiscoveryCompiler,
    EntitySeed,
    EvidenceFacet,
    ResearchContext,
)

router = APIRouter(prefix="/discovery", tags=["discovery"])


class EntitySeedInput(BaseModel):
    ref: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    aliases: list[str] = Field(default_factory=list, max_length=32)
    domains: list[str] = Field(default_factory=list, max_length=32)
    kind: str = "organization"


class DiscoveryPlanRequest(BaseModel):
    """A natural-language brief plus optional explicit public entity anchors."""

    investigation_id: str = Field(min_length=1, max_length=64)
    context_text: str = Field(min_length=1, max_length=12_000)
    entities: list[EntitySeedInput] = Field(default_factory=list, max_length=32)
    facets: list[EvidenceFacet] = Field(default_factory=lambda: list(DEFAULT_FACETS))
    time_from: str | None = None
    time_to: str | None = None
    max_queries: int = Field(default=64, ge=1, le=128)


@router.post("/plan")
async def create_discovery_plan(
    body: DiscoveryPlanRequest,
    ctx: TenantContext = Depends(require_analyst),
) -> dict[str, Any]:
    """Compile a case-scoped discovery strategy without executing network work."""
    session_factory = make_session_factory()
    async with session_factory() as session:
        investigation = (
            await session.execute(
                select(InvestigationRow).where(
                    InvestigationRow.investigation_id == body.investigation_id,
                    InvestigationRow.tenant_id == ctx.tenant_id,
                )
            )
        ).scalar_one_or_none()
    if investigation is None:
        raise HTTPException(status_code=404, detail="investigation not found")

    state = str(getattr(investigation.state, "value", investigation.state)).upper()
    if state not in {"DRAFT", "PLANNING", "RUNNING"}:
        raise HTTPException(
            status_code=409,
            detail=f"investigation does not accept discovery planning in state {state}",
        )

    scope = investigation.scope if isinstance(investigation.scope, dict) else {}
    allowed_sources = scope.get("allowed_source_ids")
    if isinstance(allowed_sources, list) and allowed_sources:
        allowed = {str(value) for value in allowed_sources}
        if not allowed.intersection({"searxng", "searxng.search", "discovery"}):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "source_outside_scope",
                    "source_id": "searxng.search",
                    "allowed_source_ids": sorted(allowed),
                },
            )

    try:
        context = ResearchContext(
            tenant_id=ctx.tenant_id,
            investigation_id=body.investigation_id,
            context_text=body.context_text,
            entities=tuple(
                EntitySeed(
                    ref=item.ref,
                    name=item.name,
                    aliases=tuple(item.aliases),
                    domains=tuple(item.domains),
                    kind=item.kind,
                )
                for item in body.entities
            ),
            facets=tuple(body.facets),
            time_from=body.time_from,
            time_to=body.time_to,
            max_queries=body.max_queries,
        )
        plan = ContextDiscoveryCompiler().compile(context)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_discovery_context", "detail": str(exc)},
        ) from exc

    return {
        **plan.as_dict(context=context),
        "execution": {
            "dispatched": False,
            "next_step": "Pass each dispatch_task through the configured Dispatcher; do not publish directly to Redpanda.",
            "budget_reservation_required": True,
            "source_policy_required": True,
        },
    }
