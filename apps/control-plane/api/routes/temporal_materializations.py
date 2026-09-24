from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from api.auth import TenantContext, resolve_tenant
from api.routes.entities import _materialization_operations, _resolve_temporal_run

router = APIRouter(tags=["temporal-materialization"])


@router.get("/temporal-materializations/health")
async def health(ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None) -> dict:
    return {"runs": _materialization_operations.health(tenant_id=ctx.tenant_id), "tenant_id": ctx.tenant_id}


@router.get("/temporal-materializations/{run_id}/audit")
async def audit(run_id: str, ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None) -> dict:
    return {"run_id": run_id, "entries": _materialization_operations.audit(run_id, tenant_id=ctx.tenant_id)}


@router.get("/temporal-materializations/{run_id}")
async def status(run_id: str, ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None) -> dict:
    result = _materialization_operations.get(run_id, tenant_id=ctx.tenant_id)
    if result is None:
        raise HTTPException(status_code=404, detail="materialization run not found")
    return await _resolve_temporal_run(run_id, result)
