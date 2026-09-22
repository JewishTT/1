"""Entity overview API (T052, US2) + donor-pattern review/correlation (T020, FR-004/FR-006).

Current state, historical versions, aliases, relationships, supporting
assertions, evidence (anchored to immutable observations, I-1), timeline and
structural signals. Also exposes possible_match correlation edges (OpenOSINT)
and analyst review as immutable provenance (Vitni).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import TenantContext, resolve_tenant
from api.sse import hub
from services.catalog import Catalog, EntityRecord
from services.review import ReviewDecision, ReviewService, ReviewTargetType

router = APIRouter(prefix="/entities", tags=["entities"])

# Hermetic catalog + review store for the smoke path (real adapters injected by the app).
_observations = {
    "OBS-1001": {"observation_id": "OBS-1001", "uri": "http://fixtures.local/report.html", "content_hash": "sha256:aa"},
}
_catalog = Catalog(observations=_observations)
_catalog.put_entity(
    EntityRecord(
        entity_id="ENT-2001",
        canonical_identity={"account": "Yard"},
        versions=[{"version": 1, "identity": {"account": "Yard"}, "first_seen": "2026-01-01T00:00:00Z"}],
        aliases=["Yard", "yard-account"],
        relationships=[{"type": "candidate_of", "target": "ENT-2002"}],
        supporting_assertions=["ASR-9001"],
        evidence_ids=["OBS-1001"],
        observations=["OBS-1001"],
        structural_signals=[{"signal": "tda_loop", "feature_id": "FEAT-42", "persistence": 2.3}],
    )
)

# possible_match edges (OpenOSINT pattern): correlation exists WITHOUT identity.
_correlations = [
    {
        "edge_id": "CE-200001",
        "candidate_a": "ENT-2001",
        "candidate_b": "ENT-2002",
        "kind": "possible_match",
        "raw_pair_score": 0.72,
        "collective_score": 0.74,
        "reasons": ["email", "handle"],
        "state": "OPEN",
    },
]

_reviews = ReviewService()


class ReviewCreate(BaseModel):
    decision: ReviewDecision
    reasoning: str = ""
    target_type: ReviewTargetType = ReviewTargetType.CANDIDATE


@router.get("/{entity_id}")
async def get_entity(
    entity_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    view = _catalog.entity(entity_id)
    if view is None:
        raise HTTPException(status_code=404, detail="entity not found")
    # Deterministic timeline clock for the temporality UI: observations are
    # anchored to the first known version's first_seen where available.
    versions = view.get("historical_versions") or []
    first_seen = versions[0].get("first_seen", "") if versions and isinstance(versions[0], dict) else ""
    enriched_timeline = []
    for entry in view.get("timeline", []):
        enriched = {**entry}
        if first_seen and "observed_at" not in enriched:
            enriched["observed_at"] = first_seen
        enriched_timeline.append(enriched)
    view = {**view, "timeline": enriched_timeline, "tenant_id": ctx.tenant_id}
    return view


@router.get("/{entity_id}/correlations")
async def get_correlations(
    entity_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    """FR-004: possible_match edges for an entity/candidate — no merge implied."""
    edges = [
        e for e in _correlations
        if e["candidate_a"] == entity_id or e["candidate_b"] == entity_id
    ]
    return {"entity_id": entity_id, "tenant_id": ctx.tenant_id, "correlations": edges}


@router.post("/{target_id}/review")
async def create_review(
    target_id: str,
    body: ReviewCreate,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    """FR-006: analyst review ACCEPT/REJECT/UNCERTAIN as immutable provenance."""
    record = _reviews.record(
        tenant_id=ctx.tenant_id,
        analyst_id=ctx.user_id,
        roles=frozenset(r.value for r in ctx.roles),
        target_type=body.target_type,
        target_id=target_id,
        decision=body.decision,
        reasoning=body.reasoning,
    )
    hub.publish(
        "entity.updated",
        {
            "entity_id": target_id,
            "tenant_id": ctx.tenant_id,
            "event": "review.recorded",
            "review_id": record.review_id,
            "decision": body.decision.value,
        },
    )
    return {"review": record.to_dict(), "event": "review.recorded"}


@router.get("/{target_id}/reviews")
async def list_reviews(
    target_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    records = _reviews.by_target(ctx.tenant_id, ReviewTargetType.CANDIDATE, target_id)
    return {"target_id": target_id, "reviews": [r.to_dict() for r in records]}