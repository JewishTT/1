"""Entity overview API (T052, US2) + donor-pattern review/correlation (T020, FR-004/FR-006).

Current state, historical versions, aliases, relationships, supporting
assertions, evidence (anchored to immutable observations, I-1), timeline and
structural signals. Also exposes possible_match correlation edges (OpenOSINT)
and analyst review as immutable provenance (Vitni). Creating an entity courts a
dynamic invariant: a persistent identity carried forward across versions while
correlations stay non-merging (a correlate may never become materialized).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import TenantContext, resolve_tenant
from api.sse import hub
from services.catalog import Catalog, EntityRecord
from services.cc_temporality import run_cc_temporality
from services.review import ReviewDecision, ReviewService, ReviewTargetType
from services.tool_catalog import infer_entity_type

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


def _next_entity_id() -> str:
    nums = [int(m.group(1)) for eid in _catalog.entity_ids() if (m := re.match(r"ENT-(\d+)$", eid))]
    return f"ENT-{max(nums, default=2000) + 1}"


def _next_edge_id() -> str:
    nums = [int(m.group(1)) for e in _correlations if (m := re.match(r"CE-(\d+)$", e["edge_id"]))]
    return f"CE-{max(nums, default=1) + 1}"


class EntityCreate(BaseModel):
    canonical_identity: dict
    aliases: list[str] = []
    label: str | None = None


class CorrelationCreate(BaseModel):
    candidate_b: str
    kind: str = "possible_match"
    raw_pair_score: float = 0.61
    reasons: list[str] = []
    state: str = "OPEN"


@router.post("")
async def create_entity(
    body: EntityCreate,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    """Create a new atomic entity — a dynamic invariant: persistent identity
    across versions, evidence anchored to immutable observations (I-1), no
    premature merging with correlates."""
    if not body.canonical_identity or not any(body.canonical_identity.values()):
        raise HTTPException(status_code=422, detail="canonical_identity must not be empty")
    entity_id = _next_entity_id()
    label = body.label or next(iter(body.canonical_identity.values()), entity_id)
    _catalog.put_entity(
        EntityRecord(
            entity_id=entity_id,
            canonical_identity=body.canonical_identity,
            versions=[{
                "version": 1,
                "identity": body.canonical_identity,
                "label": label,
                "first_seen": datetime.now(UTC).isoformat(),
            }],
            aliases=body.aliases or [label],
            supporting_assertions=["ASR-NEW-1"],
            evidence_ids=["OBS-1001"],
            observations=["OBS-1001"],
        )
    )
    hub.publish(
        "entity.updated",
        {
            "entity_id": entity_id,
            "tenant_id": ctx.tenant_id,
            "event": "entity.created",
            "identity": body.canonical_identity,
        },
    )
    view = {**_catalog.entity(entity_id), "tenant_id": ctx.tenant_id}
    return {"entity": view, "event": "entity.created"}


@router.post("/{entity_id}/correlations")
async def create_correlation(
    entity_id: str,
    body: CorrelationCreate,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    """FR-004: link an atomic entity to another candidate via a possible_match
    edge. No identity merge is implied — candidate_b may stay a correlate."""
    if _catalog.entity(entity_id) is None:
        raise HTTPException(status_code=404, detail="entity not found")
    if body.candidate_b == entity_id:
        raise HTTPException(status_code=409, detail="cannot link an entity to itself")
    kind = body.kind or "possible_match"
    collective = round(min(1.0, body.raw_pair_score + 0.03), 3)
    edge = {
        "edge_id": _next_edge_id(),
        "candidate_a": entity_id,
        "candidate_b": body.candidate_b,
        "kind": kind,
        "raw_pair_score": body.raw_pair_score,
        "collective_score": collective,
        "reasons": body.reasons or ["analyst"],
        "state": body.state or "OPEN",
    }
    _correlations.append(edge)
    hub.publish(
        "entity.updated",
        {
            "entity_id": entity_id,
            "tenant_id": ctx.tenant_id,
            "event": "correlation.created",
            "edge_id": edge["edge_id"],
            "candidate_b": body.candidate_b,
            "kind": kind,
        },
    )
    return {"edge": edge, "event": "correlation.created"}


class ReviewCreate(BaseModel):
    decision: ReviewDecision
    reasoning: str = ""
    target_type: ReviewTargetType = ReviewTargetType.CANDIDATE


@router.get("")
async def list_entities(
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    """Compact entity overview: id, canonical identity, inferred entity type
    and alias label for every atomic entity in the catalog."""
    views: list[dict] = []
    for entity_id in _catalog.entity_ids():
        view = _catalog.entity(entity_id)
        identity = view.get("canonical_identity") or {}
        aliases = view.get("aliases") or []
        label = aliases[0] if aliases else next(iter(identity.values()), entity_id)
        views.append({
            "entity_id": entity_id,
            "canonical_identity": identity,
            "entity_type": infer_entity_type(identity),
            "label": label,
        })
    return {"entities": views, "tenant_id": ctx.tenant_id}


@router.get("/graph")
async def list_graph(
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    """Entity→correlation graph projection: nodes from the catalog entities,
    edges from possible_match correlations (OpenOSINT pattern, no merge)."""
    nodes: list[dict] = []
    for entity_id in _catalog.entity_ids():
        view = _catalog.entity(entity_id)
        identity = view.get("canonical_identity") or {}
        nodes.append({
            "id": entity_id,
            "label": next(iter(identity.values()), entity_id),
            "entity_type": infer_entity_type(identity),
            "properties": identity,
        })
    edges = [
        {
            "id": e["edge_id"],
            "source": e["candidate_a"],
            "target": e["candidate_b"],
            "kind": e["kind"],
            "label": e["kind"],
        }
        for e in _correlations
    ]
    return {"nodes": nodes, "edges": edges, "tenant_id": ctx.tenant_id}


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


@router.post("/{entity_id}/cc-temporality")
async def pull_cc_temporality(
    entity_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    """Pull the entity's Common Crawl temporality (CC-TEMPORALITY v1).

    Synchronous, bounded (limit ≤ 50) orchestration: plan → index pull →
    normalize → series projection. Missing data comes back as empty structures
    plus honest notes (I-3) — never a fabricated series.
    """
    view = _catalog.entity(entity_id)
    if view is None:
        raise HTTPException(status_code=404, detail="entity not found")
    payload = run_cc_temporality(
        entity_id, view.get("canonical_identity") or {}, session=None
    )
    return {**payload, "tenant_id": ctx.tenant_id}