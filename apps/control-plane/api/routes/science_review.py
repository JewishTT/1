"""Science review API (T137, US7; contracts/science-api.md).

Base path ``/api/science/review``. Ladder position is machine-checked from the
recorded artifact ledger (FR-013): calibration report, null-model ref,
robustness report, and reproduction re-run each count toward the top rung.
Comments and status transitions are append-only ReviewEvents.
"""

from __future__ import annotations

from typing import Annotated, Any

from claims.model import ClaimStatus
from claims.query import get_claim, load_claim
from claims.status import transition_status
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from review.events import change_status, comment_on_claim
from review.ladder import LadderGates, ladder_position, top_rung

from api.auth import TenantContext, resolve_tenant
from api.routes.science_claims import _store as _claims_store
from api.routes.science_robustness import _registry, _reports

router = APIRouter(prefix="/api/science/review", tags=["science"])

_events: list[dict[str, Any]] = []
_null_refs: dict[str, str] = {}


class CommentRequest(BaseModel):
    actor: str
    body: str


class StatusChangeRequest(BaseModel):
    actor: str
    to_status: str
    comment: str | None = None


class LadderRequest(BaseModel):
    null_ref: str = ""


def _gates(claim_id: str) -> dict[str, bool]:
    record = get_claim(_claims_store, claim_id)
    calibrated = bool((record or {}).get("distribution", {}).get("calibration_ref"))
    robustness = any(report.get("claim_ref") == claim_id for report in _reports.values())
    reproduction = any(claim_id in run.output_refs for run in _registry.list())
    return {
        "calibrated": calibrated,
        "null_model": claim_id in _null_refs,
        "robustness": robustness,
        "reproduction": reproduction,
    }


@router.get("/{claim_id}")
async def get_review(claim_id: str) -> dict[str, Any]:
    record = get_claim(_claims_store, claim_id)
    if record is None:
        raise HTTPException(status_code=404, detail="claim not found")
    claim = load_claim(record)
    gates = _gates(claim_id)
    position = ladder_position(claim, LadderGates(**gates))
    if position is None or position < top_rung():
        review_state = "review_pending"
    elif claim.status is ClaimStatus.CONFIRMED:
        review_state = "confirmed"
    else:
        review_state = "in_review"
    return {
        "claim_id": claim_id,
        "statement": claim.statement,
        "status": claim.status.value,
        "model_id": claim.model_id,
        "distribution_ref": claim.distribution.calibration_ref,
        "gates": gates,
        "ladder_position": position,
        "top_rung": top_rung(),
        "review_state": review_state,
        "events": [e for e in _events if e["claim_id"] == claim_id],
    }


@router.post("/{claim_id}/comment")
async def post_comment(
    claim_id: str,
    body: CommentRequest,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict[str, Any]:
    if get_claim(_claims_store, claim_id) is None:
        raise HTTPException(status_code=404, detail="claim not found")
    try:
        event = comment_on_claim(claim_id, actor=body.actor, body=body.body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    payload = event.to_ref()
    _events.append(payload)
    return payload


@router.post("/{claim_id}/status")
async def post_status(
    claim_id: str,
    body: StatusChangeRequest,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict[str, Any]:
    record = get_claim(_claims_store, claim_id)
    if record is None:
        raise HTTPException(status_code=404, detail="claim not found")
    claim = load_claim(record)
    try:
        to_status = ClaimStatus(body.to_status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": "unknown_status"}) from exc
    event = change_status(
        claim_id,
        actor=body.actor,
        to_status=to_status,
        from_status=claim.status,
        comment=body.comment,
    )
    try:
        transition_status(
            claim,
            to_status,
            actor=body.actor,
            store=_claims_store,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": "illegal_transition", "message": str(exc)}) from exc
    payload = event.to_ref()
    _events.append(payload)
    return payload


@router.post("/{claim_id}/ladder")
async def post_ladder(claim_id: str, body: LadderRequest) -> dict[str, Any]:
    record = get_claim(_claims_store, claim_id)
    if record is None:
        raise HTTPException(status_code=404, detail="claim not found")
    if not body.null_ref:
        raise HTTPException(status_code=422, detail={"error": "missing_null_ref"})
    _null_refs[claim_id] = body.null_ref
    return {"claim_id": claim_id, "null_ref": body.null_ref, "gates": _gates(claim_id)}