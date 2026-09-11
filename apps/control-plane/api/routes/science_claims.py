"""Science claims + calibration API (T097, US1; contracts/science-api.md).

Base path ``/api/science`` (mounted without the ``/api/v1`` prefix, matching the
published contract). Every write path funnels through the shared fabric entry
points so the scope guard (FR-007) always runs first: person-sensitive outcomes
surface as ``422 scope_refused`` and are never computed.
"""

from __future__ import annotations

from typing import Annotated, Any

from claims.calibration import Prediction, calibrate
from claims.model import ClaimStatus, CredenceDistribution, EvidenceDirection, EvidenceLink
from claims.query import get_claim, list_claims, load_claim
from claims.registry import register_claim
from claims.status import transition_status
from errors import ProvenanceRequiredError, ScopeBoundaryError, UnknownModelError
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from store import ScienceStore

from api.auth import TenantContext, resolve_tenant

router = APIRouter(prefix="/api/science", tags=["science"])

_store = ScienceStore()

_EVENT_HANDLING = [
    ScopeBoundaryError,
    ProvenanceRequiredError,
    UnknownModelError,
    ValueError,
]


class DistributionModel(BaseModel):
    states: list[str]
    labels: list[str]
    probs: list[float]
    method: str
    calibration_ref: str | None = None


class EvidenceLinkModel(BaseModel):
    link_id: str
    observation_id: str
    raw_sha256: str
    direction: str
    weight: float


class RegisterClaimRequest(BaseModel):
    project_id: str
    statement: str
    distribution: DistributionModel
    provenance: list[EvidenceLinkModel] = Field(default_factory=list)
    producer_run: str | None = None


class StatusChangeRequest(BaseModel):
    to_status: str
    actor: str = "system"


class CalibrateRequest(BaseModel):
    model_id: str
    predictions: list[dict[str, Any]]


def _to_distribution(model: DistributionModel) -> CredenceDistribution:
    return CredenceDistribution(
        states=model.states,
        labels=model.labels,
        probs=list(model.probs),
        method=model.method,
        calibration_ref=model.calibration_ref,
    )


def _to_evidence_links(items: list[EvidenceLinkModel]) -> list[EvidenceLink]:
    return [
        EvidenceLink(
            link_id=item.link_id,
            observation_id=item.observation_id,
            raw_sha256=item.raw_sha256,
            direction=EvidenceDirection(item.direction),
            weight=item.weight,
        )
        for item in items
    ]


def _science_error(exc: ScopeBoundaryError | ProvenanceRequiredError | UnknownModelError | ValueError) -> HTTPException:
    if isinstance(exc, ScopeBoundaryError):
        return HTTPException(status_code=422, detail={"error": "scope_refused", "policy": "contracts/scope-boundary.md"})
    return HTTPException(status_code=422, detail={"error": type(exc).__name__, "message": str(exc)})


@router.post("/claims")
async def post_claim(
    body: RegisterClaimRequest,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict[str, Any]:
    try:
        claim = register_claim(
            project_id=body.project_id,
            statement=body.statement,
            distribution=_to_distribution(body.distribution),
            provenance=_to_evidence_links(body.provenance),
            producer_run=body.producer_run,
            tenant_id=ctx.tenant_id,
            producer=None,
            store=_store,
        )
    except (*_EVENT_HANDLING,) as exc:
        raise _science_error(exc) from exc
    return {"claim_id": claim.claim_id, "status": claim.status.value, "project_id": claim.project_id}


@router.get("/claims/{claim_id}")
async def get_science_claim(claim_id: str) -> dict[str, Any]:
    record = get_claim(_store, claim_id)
    if record is None:
        raise HTTPException(status_code=404, detail="claim not found")
    return record


@router.get("/claims")
async def list_science_claims(project_id: str | None = None, status: str | None = None) -> dict:
    return {"claims": list_claims(_store, project_id=project_id, status=status)}


@router.post("/claims/{claim_id}/status")
async def change_claim_status(
    claim_id: str,
    body: StatusChangeRequest,
) -> dict[str, Any]:
    record = get_claim(_store, claim_id)
    if record is None:
        raise HTTPException(status_code=404, detail="claim not found")
    claim = load_claim(record)
    try:
        transition_status(
            claim,
            ClaimStatus(body.to_status),
            actor=body.actor,
            store=_store,
        )
    except (*_EVENT_HANDLING,) as exc:
        raise _science_error(exc) from exc
    return {"claim_id": claim_id, "status": claim.status.value}


@router.post("/calibration")
async def post_calibration(
    body: CalibrateRequest,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict[str, Any]:
    predictions = [
        Prediction(confidence=float(item["confidence"]), outcome=bool(item["outcome"]))
        for item in body.predictions
    ]
    report = calibrate(body.model_id, predictions, producer=None, store=_store)
    return {
        "report_id": report.report_id,
        "model_id": report.model_id,
        "brier": report.brier,
        "ece": report.ece,
        "verdict": report.verdict.value,
        "buckets": report.buckets,
    }


@router.get("/calibration/{model_id}")
async def get_calibration(model_id: str) -> dict[str, Any]:
    record = _store.get("calibration", model_id)
    if record is None:
        # Fall back to the latest report for the model (deterministic ids key by model+data).
        matches = [r for r in _store.all("calibration") if r.get("model_id") == model_id]
        if not matches:
            raise HTTPException(status_code=404, detail="no calibration report for model")
        record = matches[-1]
    return record