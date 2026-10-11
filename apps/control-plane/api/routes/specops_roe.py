"""Rules-of-Engagement sign-off API for the CI/SpecOps department (027, T005).

Records a supervisor sign-off and exposes the gate's verdict. The gate itself
lives in ``apps/specops/roe/gate.py`` and is the single source of truth for
"is this authorized" — this router only persists a sign-off and reads its status
back, so the emulation/phishing routers can call the same gate before any send.

Named-absence discipline (§99): a field the gate does not decide is not invented
here. Tenant isolation comes from ``resolve_tenant`` (§VII); the in-memory
registry is a wave-1 stand-in for a durable store (deferred, FR-003).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import TenantContext, resolve_tenant

# The gate package (apps/specops). Import defensively so the control plane still
# boots when the specops package is not yet on sys.path; the health note reports
# the gap rather than the API failing to start.
try:
    from specops.roe.gate import REGISTRY, RoeStatus, RulesOfEngagement
except Exception:  # pragma: no cover - import boundary
    REGISTRY = None  # type: ignore[assignment]
    RulesOfEngagement = None  # type: ignore[assignment]
    RoeStatus = None  # type: ignore[assignment]

router = APIRouter(prefix="/specops/roe", tags=["specops-roe"])


class RoeCreate(BaseModel):
    target_ref: str
    scope: str
    approved_by: str
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
    """Record a supervisor sign-off. Returns its status (confirmed / unconfirmed)."""
    if REGISTRY is None or RulesOfEngagement is None:  # pragma: no cover
        raise HTTPException(status_code=503, detail="specops gate unavailable")
    roe = RulesOfEngagement(
        roe_id=f"roe-{uuid.uuid4().hex[:12]}",
        target_ref=body.target_ref,
        scope=body.scope,
        approved_by=body.approved_by,
        signed_at=_now_iso(),
        expires_at=body.expires_at,
    )
    REGISTRY.record(roe)
    return _view(roe)


@router.get("/{roe_id}", response_model=RoeView)
async def get_roe(
    roe_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> RoeView:
    if REGISTRY is None:  # pragma: no cover
        raise HTTPException(status_code=503, detail="specops gate unavailable")
    roe = REGISTRY.get(roe_id)
    if roe is None:
        raise HTTPException(status_code=404, detail="rules-of-engagement not found")
    return _view(roe)


def _now_iso() -> str:
    from datetime import datetime, timezone

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
