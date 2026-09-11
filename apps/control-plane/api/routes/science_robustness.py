"""Science robustness + experiments API (T132, US6; contracts/science-api.md).

Base path ``/api/science``. Robustness runs the three declared perturbation
families and reports flip rates + noise regions (FR-011); when a conclusion
flips in a relevant region the claim is downgraded to ``UNCERTAIN``. The
experiment registry records runs (FR-012) and ``reproduce`` re-checks pinned
seeds/versions within tolerance, logging a reproduction event (SC-007).
"""

from __future__ import annotations

from typing import Any

from claims.model import ClaimStatus, EvidenceDirection, EvidenceLink
from claims.query import get_claim, load_claim
from claims.status import transition_status
from errors import ReproductionError
from experiments.registry import ExperimentRegistry
from experiments.reproduction import reproduce
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from robustness.perturb import PerturbationGrid
from robustness.report import RobustnessReport, analyze_robustness

from api.routes.science_claims import _store as _claims_store

router = APIRouter(prefix="/api/science", tags=["science"])

_reports: dict[str, dict[str, Any]] = {}
_registry = ExperimentRegistry()


class EvidenceLinkBody(BaseModel):
    link_id: str
    observation_id: str
    raw_sha256: str
    direction: str
    weight: float
    attached_at: str | None = None


class RobustnessRequest(BaseModel):
    claim_id: str
    evidence: list[EvidenceLinkBody] = []
    missing_fraction: tuple[float, ...] = (0.2,)
    label_flip: tuple[float, ...] = (0.1,)
    biased_subsample: tuple[float, ...] = (0.5, 0.7)
    seed: int = 7


class RecordExperimentRequest(BaseModel):
    input_refs: list[str]
    output_refs: list[str]
    seed: int
    pipeline_version: str
    dependency_freeze: dict[str, str] = {}
    tolerance: float = 1e-6


class ReproduceRequest(BaseModel):
    run_id: str


def _to_evidence_links(items: list[EvidenceLinkBody]) -> list[EvidenceLink]:
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


def _downgrade_if_flipped(claim_id: str, report: RobustnessReport) -> bool:
    if not any(region["flipped"] for region in report.noise_regions):
        return False
    record = get_claim(_claims_store, claim_id)
    if record is None:
        return False
    claim = load_claim(record)
    if claim.status is ClaimStatus.UNCERTAIN:
        return False
    transition_status(
        claim,
        ClaimStatus.UNCERTAIN,
        actor="science.robustness",
        store=_claims_store,
    )
    return True


@router.post("/robustness")
async def post_robustness(body: RobustnessRequest) -> dict[str, Any]:
    evidence = _to_evidence_links(body.evidence)
    if not evidence:
        raise HTTPException(status_code=422, detail={"error": "no_evidence", "message": "robustness needs evidence to perturb"})
    report = analyze_robustness(
        body.claim_id,
        evidence,
        perturbations=PerturbationGrid(
            missing_fraction=body.missing_fraction,
            label_flip=body.label_flip,
            biased_subsample=body.biased_subsample,
            seed=body.seed,
        ),
    )
    downgraded = _downgrade_if_flipped(body.claim_id, report)
    payload = report.as_dict()
    _reports[payload["report_id"]] = payload
    payload["downgraded_to_uncertain"] = downgraded
    return payload


@router.get("/robustness")
async def list_robustness() -> dict[str, Any]:
    return {"reports": list(_reports.values())}


@router.get("/robustness/{report_id}")
async def get_robustness(report_id: str) -> dict[str, Any]:
    report = _reports.get(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    return report


@router.post("/experiments")
async def post_experiment(body: RecordExperimentRequest) -> dict[str, Any]:
    run = _registry.record_run(
        input_refs=body.input_refs,
        output_refs=body.output_refs,
        seed=body.seed,
        pipeline_version=body.pipeline_version,
        dependency_freeze=body.dependency_freeze,
        tolerance=body.tolerance,
    )
    return {
        "run_id": run.run_id,
        "input_refs": run.input_refs,
        "output_refs": run.output_refs,
        "seed": run.seed,
        "pipeline_version": run.pipeline_version,
        "tolerance": run.tolerance,
    }


@router.get("/experiments")
async def list_experiments() -> dict[str, Any]:
    return {
        "runs": [
            {
                "run_id": run.run_id,
                "seed": run.seed,
                "pipeline_version": run.pipeline_version,
                "tolerance": run.tolerance,
                "reproductions": run.reproductions,
            }
            for run in _registry.list()
        ]
    }


@router.post("/experiments/reproduce")
async def post_reproduce(body: ReproduceRequest) -> dict[str, Any]:
    try:
        result = reproduce(body.run_id, registry=_registry)
    except ReproductionError as exc:
        raise HTTPException(status_code=404, detail={"error": "run_not_found", "message": str(exc)}) from exc
    return result.as_dict()