"""Connector + recon plan API (T026, FR-008/FR-009, SpiderFoot/reNgine pattern)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import TenantContext, resolve_tenant
from services.source_registry import (
    Connector,
    ConnectorRegistry,
    ReconPlanService,
)

router = APIRouter(prefix="/connectors", tags=["connectors"])

_connectors = ConnectorRegistry()
_plans = ReconPlanService()


class ConnectorCreate(BaseModel):
    name: str
    source_types: list[str] = Field(default_factory=list)
    policy_id: str = "policies/default"
    version: str = "1.0"


class ReconPlanCreate(BaseModel):
    investigation_id: str
    strategy: dict = Field(default_factory=dict)


class HelloConnector:
    """Hermetic AcquisitionWorker-compliant connector used by the smoke path.

    capabilities/estimate/acquire satisfy the AcquisitionWorker contract; the
    real acquisition layer injects production connectors behind the same surface.
    """

    def capabilities(self) -> dict:
        return {"source_types": ["HTTP"], "content_types": ["text/html"]}

    def estimate(self, task: dict) -> dict:
        return {
            "expected_cost": 0.01,
            "expected_duration_ms": 100,
            "expected_bytes": 1024,
            "duplicate_risk": 0.1,
        }

    def acquire(self, task: dict) -> dict:
        return {"outcome": "observation_created", "observation_id": "OBS-smoke"}


def _as_connector(name: str, body: ConnectorCreate, tenant_id: str) -> Connector:
    return Connector(
        name=name,
        tenant_id=tenant_id,
        source_types=body.source_types,
        capabilities={"source_types": body.source_types, "content_types": ["text/html"]},
        policy_id=body.policy_id,
        version=body.version,
        impl=HelloConnector(),
    )


@router.post("/register")
async def register_connector(
    body: ConnectorCreate,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    try:
        connector = _connectors.register(_as_connector(body.name, body, ctx.tenant_id))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"connector": connector.to_dict(), "event": "connector.registered"}


@router.post("/{name}/activate")
async def activate_connector(
    name: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    try:
        connector = _connectors.activate(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="connector not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"connector": connector.to_dict(), "event": "connector.status_changed"}


@router.get("")
async def list_connectors(ctx: Annotated[TenantContext, Depends(resolve_tenant)]) -> dict:
    return {"connectors": [c.to_dict() for c in _connectors.list(ctx.tenant_id)]}


@router.get("/recon-plans")
async def list_recon_plans(ctx: Annotated[TenantContext, Depends(resolve_tenant)]) -> dict:
    return {"plans": [p.to_dict() for p in _plans.list(ctx.tenant_id)]}


@router.post("/{name}/recon-plans")
async def create_recon_plan(
    name: str,
    body: ReconPlanCreate,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    if _connectors.get(name) is None:
        raise HTTPException(status_code=404, detail="connector not found")
    plan = _plans.create(
        investigation_id=body.investigation_id,
        tenant_id=ctx.tenant_id,
        strategy={**body.strategy, "connector": name},
    )
    return {"plan": plan.to_dict(), "event": "recon.plan_started"}