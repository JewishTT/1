"""Rules-of-Engagement sign-off API.

The authenticated administrator is the approver. Caller-supplied identity is
never accepted as authority. The current registry remains process-local and is
explicitly tracked as an operational gap until a durable tenant-scoped store is wired.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import Role, TenantContext, resolve_tenant

try:
    from specops.roe.gate import REGISTRY, RulesOfEngagement
except Exception:  # pragma: no cover - import boundary
    REGISTRY = None
    RulesOfEngagement = None

router = APIRouter(prefix="/specops/roe", tags=["specops-roe"])

# This ownership index prevents cross-tenant reads inside the process. It is not
# durable; a process restart makes old RoE records unavailable rather than public.
_TENANT_BY_ROE_ID: dict[str, str] = {}


class RoeCreate(BaseModel):
    target_ref: str
    scope: str
    expires_at: str | None = None


class RoeView(BaseModel):
    roe_id: str
    target_ref: str
    scope: str
    approved_by: str
    signed_at: str
    expires_at: str | None
    status: str


@router.post("", response_model=RoeView)
async def record_roe(
    body: RoeCreate,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> RoeView:
    ctx.require_role(Role.ADMIN)
    if REGISTRY is None or RulesOfEngagement is None:
        raise HTTPException(status_code=503, detail="specops gate unavailable")

    expires_at = _validated_expiry(body.expires_at)
    roe = RulesOfEngagement(
        roe_id=f"roe-{uuid.uuid4().hex[:12]}",
        target_ref=body.target_ref,
        scope=body.scope,
        approved_by=ctx.user_id,
        signed_at=_now_iso(),
        expires_at=expires_at,
    )
    REGISTRY.record(roe)
    _TENANT_BY_ROE_ID[roe.roe_id] = ctx.tenant_id
    return _view(roe)


@router.get("/{roe_id}", response_model=RoeView)
async def get_roe(
    roe_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> RoeView:
    if REGISTRY is None:
        raise HTTPException(status_code=503, detail="specops gate unavailable")
    if _TENANT_BY_ROE_ID.get(roe_id) != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="rules-of-engagement not found")
    roe = REGISTRY.get(roe_id)
    if roe is None:
        raise HTTPException(status_code=404, detail="rules-of-engagement not found")
    return _view(roe)


def _validated_expiry(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=422, detail="expires_at must be a valid ISO-8601 timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HTTPException(status_code=422, detail="expires_at must include a timezone")
    if parsed <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="expires_at must be in the future")
    return parsed.astimezone(timezone.utc).isoformat()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _view(roe) -> RoeView:
    return RoeView(
        roe_id=roe.roe_id,
        target_ref=roe.target_ref,
        scope=roe.scope,
        approved_by=roe.approved_by,
        signed_at=roe.signed_at,
        expires_at=roe.expires_at,
        status=roe.status().value,
    )
