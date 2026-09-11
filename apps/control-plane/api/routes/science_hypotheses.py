"""Science hypothesis API (T106, US2; contracts/science-api.md).

Base path ``/api/science/hypotheses``. All writes funnel through the shared
fabric entry points: proposal, direction-tagged evidence, decision-gated
discard (SC-003), the read-only KL gain planner (§4), and per-project coverage.
"""

from __future__ import annotations

from typing import Any

from claims.model import DecisionRecord, EvidenceDirection, EvidenceLink
from errors import DecisionRequiredError, ScienceError
from fastapi import APIRouter, HTTPException
from hypotheses.coverage import project_coverage
from hypotheses.decide import discard_hypothesis
from hypotheses.evidence import attach_evidence
from hypotheses.gain import EvidenceOpportunity, load_hypotheses, plan_collection
from hypotheses.model import propose_hypothesis
from pydantic import BaseModel, Field
from store import ScienceStore

router = APIRouter(prefix="/api/science/hypotheses", tags=["science"])

_store = ScienceStore()


class ProposeRequest(BaseModel):
    project_id: str
    text: str


class AttachEvidenceRequest(BaseModel):
    hypothesis_id: str
    link_id: str
    observation_id: str
    direction: str
    weight: float = Field(default=0.5, ge=0.0, le=1.0)


class DiscardRequest(BaseModel):
    hypothesis_id: str
    actor: str
    reason: str


class PlanRequest(BaseModel):
    project_id: str
    budget: int = Field(default=10, ge=1)
    opportunities: list[dict[str, Any]] = Field(default_factory=list)


def _fabric_error(exc: ScienceError) -> HTTPException:
    return HTTPException(status_code=422, detail={"error": type(exc).__name__, "message": str(exc)})


@router.post("")
async def post_hypothesis(body: ProposeRequest) -> dict[str, Any]:
    h = propose_hypothesis(
        project_id=body.project_id,
        text=body.text,
        tenant_id="system",
        producer=None,
        store=_store,
    )
    return {"hypothesis_id": h.hypothesis_id, "status": h.status.value, "project_id": h.project_id}


@router.get("")
async def list_hypotheses(project_id: str | None = None) -> dict[str, Any]:
    records = _store.all("hypotheses")
    if project_id is not None:
        records = [r for r in records if r.get("project_id") == project_id]
    return {"hypotheses": records}


@router.post("/{hypothesis_id}/evidence")
async def post_evidence(hypothesis_id: str, body: AttachEvidenceRequest) -> dict[str, Any]:
    record = _store.get("hypotheses", hypothesis_id)
    if record is None:
        raise HTTPException(status_code=404, detail="hypothesis not found")
    h = next((h for h in load_hypotheses(_store, record.get("project_id", "")) if h.hypothesis_id == hypothesis_id), None)
    if h is None:
        raise HTTPException(status_code=404, detail="hypothesis not found")
    attach_evidence(
        h,
        EvidenceLink(
            link_id=body.link_id,
            observation_id=body.observation_id,
            raw_sha256=f"sha256:{body.observation_id}",
            direction=EvidenceDirection(body.direction),
            weight=body.weight,
        ),
        producer=None,
        store=_store,
    )
    return {"hypothesis_id": hypothesis_id, "evidence_links": len(h.evidence_links)}


@router.post("/{hypothesis_id}/discard")
async def post_discard(hypothesis_id: str, body: DiscardRequest) -> dict[str, Any]:
    record = _store.get("hypotheses", hypothesis_id)
    if record is None:
        raise HTTPException(status_code=404, detail="hypothesis not found")
    h = next(
        (
            h
            for h in load_hypotheses(_store, record.get("project_id", ""))
            if h.hypothesis_id == hypothesis_id
        ),
        None,
    )
    if h is None:
        raise HTTPException(status_code=404, detail="hypothesis not found")
    try:
        discard_hypothesis(
            h,
            DecisionRecord(actor=body.actor, reason=body.reason),
            producer=None,
            store=_store,
        )
    except DecisionRequiredError as exc:
        raise _fabric_error(exc) from exc
    return {"hypothesis_id": hypothesis_id, "status": "discarded"}


@router.post("/plan")
async def post_plan(body: PlanRequest) -> dict[str, Any]:
    opportunities = [
        EvidenceOpportunity(
            opportunity_id=opp.get("opportunity_id", ""),
            description=opp.get("description", ""),
            likelihoods=opp.get("likelihoods", {}),
        )
        for opp in body.opportunities
    ]
    ranked = plan_collection(
        body.project_id,
        opportunities,
        body.budget,
        hypotheses=None,
        store=_store,
    )
    return {
        "project_id": body.project_id,
        "plan": [
            {
                "opportunity_id": r.opportunity_id,
                "expected_gain": r.expected_gain,
                "discriminating_pair": r.discriminating_pair,
            }
            for r in ranked
        ],
    }


@router.get("/coverage")
async def get_coverage(project_id: str) -> dict[str, Any]:
    return project_coverage(store=_store, project_id=project_id)