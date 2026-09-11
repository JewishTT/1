"""Science causal API (T112, US3; contracts/science-api.md).

Base path ``/api/science/causal``. All classification funnels through the
shared scope guard first (T111): any person-sensitive outcome is refused
as ``422 scope_refused`` before computation. Model registration validates
scope declarations at creation time (FR-007).
"""

from __future__ import annotations

from typing import Any

from causal.infer import classify
from causal.model import CausalModel
from claims.model import EvidenceDirection, EvidenceLink
from errors import ScopeBoundaryError
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from store import ScienceStore

router = APIRouter(prefix="/api/science/causal", tags=["science"])

_store = ScienceStore()
_models: dict[str, CausalModel] = {}


class ClassifyRequest(BaseModel):
    outcome_attribute: str
    evidence: list[dict[str, Any]] = []
    model_id: str | None = None
    possible_confounders: list[str] = []


class RegisterModelRequest(BaseModel):
    model_id: str
    graph: dict[str, list[str]]
    confounders: list[str] = []
    assumptions: list[str] = []
    scope_decl: list[str] = []


def _evidence_from(body: ClassifyRequest) -> list[EvidenceLink]:
    return [
        EvidenceLink(
            link_id=str(item["link_id"]),
            observation_id=str(item["observation_id"]),
            raw_sha256=str(item.get("raw_sha256", "") or f"sha256:{item['observation_id']}"),
            direction=EvidenceDirection(item["direction"]),
            weight=float(item.get("weight", 0.5)),
        )
        for item in body.evidence
    ]


@router.post("/classify")
async def post_classify(body: ClassifyRequest) -> dict[str, Any]:
    model = _models.get(body.model_id) if body.model_id else None
    if body.model_id and model is None:
        raise HTTPException(status_code=404, detail="model not found")
    try:
        conclusion = classify(
            _evidence_from(body),
            model,
            outcome_attribute=body.outcome_attribute,
            possible_confounders=body.possible_confounders,
            producer=None,
            store=_store,
        )
    except ScopeBoundaryError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "scope_refused", "policy": "contracts/scope-boundary.md"},
        ) from exc
    return conclusion.to_ref()


@router.post("/models")
async def post_model(body: RegisterModelRequest) -> dict[str, Any]:
    try:
        model = CausalModel(
            model_id=body.model_id,
            graph=body.graph,
            confounders=body.confounders,
            assumptions=body.assumptions,
            scope_decl=set(body.scope_decl),
        )
    except ScopeBoundaryError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "scope_refused", "policy": "contracts/scope-boundary.md"},
        ) from exc
    _models[model.model_id] = model
    return {"model_id": model.model_id, "scope_decl": sorted(model.scope_decl)}


@router.get("/models/{model_id}")
async def get_model(model_id: str) -> dict[str, Any]:
    model = _models.get(model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="model not found")
    return {
        "model_id": model.model_id,
        "graph": model.graph,
        "confounders": model.confounders,
        "assumptions": model.assumptions,
        "scope_decl": sorted(model.scope_decl),
    }


@router.get("/models")
async def list_models() -> dict[str, Any]:
    return {"models": [{"model_id": m.model_id, "scope_decl": sorted(m.scope_decl)} for m in _models.values()]}