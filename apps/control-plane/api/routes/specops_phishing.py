"""Phishing / SAT API for the CI/SpecOps department (027, US3, T028).

Create a draft campaign against an approved roster, then launch it under the
rules-of-engagement gate. The gate + roster validation run server-side, so the
UI cannot bypass them: a send without a confirmed sign-off is 409 (RoEError), an
out-of-roster target is 422 (RosterError). `captured_credentials_count` is always
0 in every response — the invariant is structural, not a rendering choice (FR-006).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import TenantContext, resolve_tenant

try:
    from specops.phishing import REGISTRY as CAMPAIGNS
    from specops.phishing import launch as launch_campaign
    from specops.roe.gate import REGISTRY as ROE, RoEError, RosterError
except Exception:  # pragma: no cover - import boundary
    CAMPAIGNS = None  # type: ignore[assignment]
    launch_campaign = None  # type: ignore[assignment]
    ROE = None  # type: ignore[assignment]
    RoEError = Exception  # type: ignore[assignment,misc]
    RosterError = Exception  # type: ignore[assignment,misc]

router = APIRouter(prefix="/specops/phishing", tags=["specops-phishing"])


def _envelope(**extra):
    return {"served": ["/specops/phishing"], "missing": [], "scope": "tenant-wide", **extra}


def _campaign_view(c):
    return {
        "campaign_id": c.campaign_id,
        "state": c.state,
        "roe_status": c.roe_status,
        "roster": c.roster,
        "engagement_metrics": c.engagement,
        "attack_mapping": c.attack_mapping,
        "captured_credentials_count": 0,
    }


class CreateBody(BaseModel):
    name: str
    template_source: str
    roster: list[str]
    attack_mapping: list[str] = []


class LaunchBody(BaseModel):
    roe_id: str


@router.post("/campaigns", status_code=200)
async def create_campaign(body: CreateBody, ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None) -> dict:
    if CAMPAIGNS is None:  # pragma: no cover
        raise HTTPException(status_code=503, detail="specops phishing unavailable")
    if not body.roster:
        raise HTTPException(status_code=422, detail="roster is empty")
    c = CAMPAIGNS.create(
        name=body.name,
        template_source=body.template_source,
        roster=body.roster,
        attack_mapping=body.attack_mapping,
    )
    return _envelope(campaign=_campaign_view(c))


@router.post("/campaigns/{campaign_id}/launch", status_code=200)
async def launch(body_roe: LaunchBody, campaign_id: str, ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None) -> dict:
    if CAMPAIGNS is None or launch_campaign is None:  # pragma: no cover
        raise HTTPException(status_code=503, detail="specops phishing unavailable")
    c = CAMPAIGNS.get(campaign_id)
    if c is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    roe = ROE.get(body_roe.roe_id) if ROE is not None else None
    try:
        launch_campaign(c, roe)
    except RoEError as exc:
        raise HTTPException(status_code=409, detail={"error": "RoEError", "reason": exc.reason}) from exc
    except RosterError as exc:
        raise HTTPException(
            status_code=422, detail={"error": "RosterError", "reason": exc.reason, "rejected_targets": exc.rejected}
        ) from exc
    return _envelope(campaign=_campaign_view(c))


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str, ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None) -> dict:
    if CAMPAIGNS is None:  # pragma: no cover
        raise HTTPException(status_code=503, detail="specops phishing unavailable")
    c = CAMPAIGNS.get(campaign_id)
    if c is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    return _envelope(campaign=_campaign_view(c))
