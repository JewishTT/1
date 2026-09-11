"""Resolution review API (feature 005 US2): pair_candidates queue + decision endpoints.

Read-only listing of reviewable candidate pairs and human ACCEPT/REJECT/UNCERTAIN
decisions recorded as append-only provenance (FR-006, OpenOSINT review pattern).
Every decision is a ReviewRecord on a ``candidate`` target whose ``target_id`` is
the deterministic ``pair_key``; the returned ``candidate_state`` mirrors the
admission resolution vocabulary (open/accepted/rejected). Reversal of a prior
accept is expressed as a REJECT record for the same pair (supersedes, never
mutates — I-2).
"""

from __future__ import annotations

import json
from typing import Annotated

from events.kafka import build_envelope
from events.topics import topic_for
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import TenantContext, resolve_tenant
from services.review import ReviewDecision, ReviewService, ReviewTargetType

router = APIRouter(prefix="/investigations", tags=["resolutions"])

# Hermetic review store for the smoke path (DB-backed adapter injected by the app).
_reviews = ReviewService()
_producer = None


def bind_producer(producer) -> None:
    global _producer
    _producer = producer


class ResolutionDecisionCreate(BaseModel):
    pair_key: str = Field(min_length=1)
    decision: ReviewDecision = ReviewDecision.UNCERTAIN
    reasoning: str = ""
    reviewer_id: str = ""


def _serialize_pair(record: dict) -> dict:
    return {
        "pair_key": record["target_id"],
        "review_id": record["review_id"],
        "decision": record["decision"],
        "reviewer_id": record["analyst_id"],
        "reviewed_at": record["reviewed_at"],
        "reasoning": record["reasoning"],
    }


@router.get("/{investigation_id}/resolutions")
async def list_resolutions(
    investigation_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """Read-only review queue: every candidate pair record for this tenant."""
    records = [
        r.to_dict()
        for r in _reviews.all(ctx.tenant_id)
        if r.target_type == ReviewTargetType.CANDIDATE
    ]
    return {
        "investigation_id": investigation_id,
        "tenant_id": ctx.tenant_id,
        "pairs": [_serialize_pair(r) for r in records],
    }


@router.post("/{investigation_id}/resolutions/decide")
async def decide_resolution(
    investigation_id: str,
    body: ResolutionDecisionCreate,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """Record a human ACCEPT/REJECT/UNCERTAIN decision on one candidate pair.

    The decision is append-only; a REJECT on a previously accepted pair revokes
    it (reversal) without ever mutating the earlier record.
    """
    try:
        record, candidate_state = _reviews.record_candidate_review(
            tenant_id=ctx.tenant_id,
            analyst_id=ctx.user_id,
            pair_key=body.pair_key,
            decision=body.decision,
            reasoning=body.reasoning,
            roles=frozenset(r.value for r in ctx.roles),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Durable replay signal for projections (refs-only payload, I-5).
    if _producer is not None:
        envelope = build_envelope(
            event_type="resolution.candidate_decided",
            event_version="1.0",
            producer="control-plane.resolutions",
            producer_version="0.1.0",
            payload=json.dumps(record.to_dict(), default=str).encode("utf-8"),
            entity_id=body.pair_key,
            event_id=f"evt-{record.review_id}",
        )
        _producer.produce(
            topic_for("resolution.candidate_decided"),
            envelope,
            key=body.pair_key,
        )

    return {
        "investigation_id": investigation_id,
        "pair_key": body.pair_key,
        "review": record.to_dict(),
        "candidate_state": candidate_state,
        "event": "resolution.candidate_decided",
    }