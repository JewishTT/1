"""Kill-chain emulation API for the CI/SpecOps department (027, US2, T021).

Lists ATT&CK plans loaded whole from the donor libraries, launches an operation
against an authorized lab target under the rules-of-engagement gate, and reports
live per-ability planned-vs-executed state. The RoE gate is enforced here, before
the engine runs: a launch without a confirmed, unexpired sign-off is a 409.

Named-absence (§99): when the donor plan libraries are not present, `GET /plans`
returns an empty list and a `missing[]` entry naming what would close it — never
a fabricated plan.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import TenantContext, resolve_tenant

try:
    from specops.emulation import REGISTRY as EMULATION
    from specops.roe.gate import REGISTRY as ROE, RoEError
except Exception:  # pragma: no cover - import boundary
    EMULATION = None  # type: ignore[assignment]
    ROE = None  # type: ignore[assignment]
    RoEError = Exception  # type: ignore[assignment,misc]

router = APIRouter(prefix="/specops/emulation", tags=["specops-emulation"])

_PLANS_MISSING = "GET /specops/emulation/plans (donor plan libraries not loaded — ael / adversary_emulation_library absent)"


def _envelope(**extra):
    return {
        "served": ["/specops/emulation"],
        "missing": [],
        "scope": "tenant-wide",
        **extra,
    }


class LaunchBody(BaseModel):
    plan_id: str
    lab_fixture: str
    roe_id: str


def _plan_view(plan):
    return {
        "plan_id": plan.plan_id,
        "name": plan.name,
        "source_donor": plan.source_donor,
        "target_techniques": list(plan.target_techniques),
        "lab_fixture": plan.lab_fixture,
    }


def _op_view(op):
    return {
        "operation_id": op.operation_id,
        "plan_id": op.plan_id,
        "lab_fixture": op.lab_fixture,
        "roe_status": "confirmed",
        "state": op.state,
        "abilities": op.abilities,
        "started_at": op.started_at,
        "halted_reason": op.halted_reason,
    }


@router.get("/plans")
async def list_plans(ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None) -> dict:
    if EMULATION is None:  # pragma: no cover
        raise HTTPException(status_code=503, detail="specops emulation unavailable")
    plans = [_plan_view(p) for p in EMULATION.plans()]
    return _envelope(plans=plans, missing=[] if plans else [_PLANS_MISSING])


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: str, ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None) -> dict:
    if EMULATION is None:  # pragma: no cover
        raise HTTPException(status_code=503, detail="specops emulation unavailable")
    plan = EMULATION.plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="plan not found")
    return _envelope(
        plan={
            "plan_id": plan.plan_id,
            "abilities": [
                {
                    "ability_id": a.ability_id,
                    "technique": a.technique,
                    "tactic": a.tactic,
                    "executor": a.executor,
                    "expected_telemetry": list(a.expected_telemetry),
                }
                for a in plan.abilities
            ],
            "expected_telemetry": [t for a in plan.abilities for t in a.expected_telemetry],
            "lab_fixture": plan.lab_fixture,
        }
    )


@router.post("/operations", status_code=200)
async def launch_operation(body: LaunchBody, ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None) -> dict:
    if EMULATION is None:  # pragma: no cover
        raise HTTPException(status_code=503, detail="specops emulation unavailable")
    # RoE gate FIRST: no confirmed, unexpired sign-off → refuse before the engine runs.
    roe = ROE.get(body.roe_id) if ROE is not None else None
    try:
        from specops.roe.gate import require_confirmed_roe

        require_confirmed_roe(roe)
    except RoEError as exc:
        raise HTTPException(status_code=409, detail={"error": "RoEError", "reason": exc.reason}) from exc
    plan = EMULATION.plan(body.plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="plan not found")
    op = EMULATION.create(plan, body.roe_id)
    return _envelope(operation=_op_view(op))


@router.get("/operations/{operation_id}")
async def get_operation(operation_id: str, ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None) -> dict:
    if EMULATION is None:  # pragma: no cover
        raise HTTPException(status_code=503, detail="specops emulation unavailable")
    op = EMULATION.advance(operation_id)  # deterministic stand-in for a live agent
    if op is None:
        raise HTTPException(status_code=404, detail="operation not found")
    return _envelope(operation=_op_view(op))
