"""Tenant-scoped quarantine API.

The durable quarantine repository is not wired to the control plane yet. Fail
closed with 503 instead of exposing process-local records, inventing an empty
queue, or deleting a preserved payload during a fake re-evaluation.
"""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException

from api.auth import TenantContext, resolve_tenant

router = APIRouter(prefix="/dlq", tags=["dlq"])


def _unavailable() -> NoReturn:
    raise HTTPException(
        status_code=503,
        detail="tenant-scoped durable quarantine storage is not configured",
    )


@router.get("")
async def list_quarantine(
    topic: str | None = None,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    _unavailable()


@router.get("/{record_id}")
async def get_quarantined(
    record_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    _unavailable()


@router.post("/{record_id}/replay")
async def replay_record(
    record_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    _unavailable()


@router.post("/{record_id}/re-evaluate")
async def re_evaluate(
    record_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    _unavailable()
