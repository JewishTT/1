"""Tenant-scoped operator API for durable failure/quarantine records.

List and inspect resolve sidecar metadata from the tenant's immutable object-store
namespace. Original payload bytes are never returned by this API. Replay and
re-evaluation remain disabled until a policy-revalidated redrive pipeline exists.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import Role, TenantContext, resolve_tenant
from events.dlq_durable import ObjectStoreSink
from storage.s3 import ObjectStore

log = logging.getLogger(__name__)
router = APIRouter(prefix="/dlq", tags=["dlq"])


def _sink(ctx: TenantContext) -> ObjectStoreSink:
    if not ctx.tenant_id.strip():
        raise HTTPException(status_code=401, detail="authenticated tenant is required")
    try:
        return ObjectStoreSink(store=ObjectStore(), tenant_id=ctx.tenant_id)
    except Exception:
        log.exception("DLQ object-store configuration unavailable for tenant")
        raise HTTPException(
            status_code=503,
            detail="durable quarantine object storage is unavailable",
        ) from None


def _require_reader(ctx: TenantContext) -> None:
    ctx.require_role(Role.VIEWER, Role.ANALYST, Role.ADMIN)


def _require_operator(ctx: TenantContext) -> None:
    ctx.require_role(Role.ADMIN)


@router.get("")
async def list_quarantine(
    topic: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    _require_reader(ctx)
    try:
        page = await _sink(ctx).alist_page(limit=limit, cursor=cursor, topic=topic)
    except (ValueError, PermissionError):
        raise HTTPException(
            status_code=400,
            detail="invalid quarantine cursor or index metadata",
        ) from None
    except Exception:
        log.exception("DLQ index read failed for tenant")
        raise HTTPException(
            status_code=503,
            detail="durable quarantine index is unavailable",
        ) from None
    return {
        "items": page["items"],
        "next_cursor": page["next_cursor"],
        "pages_scanned": page["pages_scanned"],
        "tenant_id": ctx.tenant_id,
    }


@router.get("/{record_id}")
async def get_quarantined(
    record_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    _require_reader(ctx)
    try:
        metadata = await _sink(ctx).aget_metadata(record_id)
    except (ValueError, PermissionError):
        raise HTTPException(
            status_code=404,
            detail="quarantine record not found",
        ) from None
    except Exception:
        log.exception("DLQ metadata read failed for tenant")
        raise HTTPException(
            status_code=503,
            detail="durable quarantine index is unavailable",
        ) from None
    if metadata is None:
        raise HTTPException(status_code=404, detail="quarantine record not found")
    return {
        key: value
        for key, value in metadata.items()
        if key not in {"payload_ref", "payload_key"}
    }


@router.post("/{record_id}/replay")
async def replay_record(
    record_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    _require_operator(ctx)
    # Preserving original bytes is wired. Re-emitting them is not yet safe: it must
    # re-check case approval, scope revision, reservation and current source policy.
    raise HTTPException(
        status_code=503,
        detail="governed replay dispatch is not configured; record remains preserved",
    )


@router.post("/{record_id}/re-evaluate")
async def re_evaluate(
    record_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    _require_operator(ctx)
    raise HTTPException(
        status_code=503,
        detail="re-evaluation workflow is not configured; record remains preserved",
    )
