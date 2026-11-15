"""Authenticated, read-only Intelligence snapshot API."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder

from api.auth import TenantContext, require_analyst
from services.intelligence_access import intelligence_port
from services.intelligence_reader import (
    IntelligenceEvidenceUnavailable,
    IntelligenceReadDenied,
    IntelligenceSnapshotBudgetExceeded,
    IntelligenceSubjectNotFound,
)
from shared.contracts.intelligence_feed import IntelligenceQuery

router = APIRouter(prefix="/intelligence", tags=["intelligence-silo"])
PURPOSE = "analyst_view"


@router.get("/snapshots/{subject_ref}")
async def get_snapshot(
    subject_ref: str,
    ctx: Annotated[TenantContext, Depends(require_analyst)],
    max_hops: int = Query(default=2, ge=0, le=8),
    as_of: datetime | None = None,
) -> dict:
    """Read a bounded, tenant-scoped view of one already-known entity and its evidence."""
    try:
        reader = await intelligence_port(ctx, purpose=PURPOSE)
        snapshot = await reader.get_snapshot(IntelligenceQuery(
            tenant_id=ctx.tenant_id,
            subject_ref=subject_ref,
            purpose=PURPOSE,
            max_hops=max_hops,
            as_of=as_of,
        ))
    except IntelligenceReadDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except IntelligenceSubjectNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IntelligenceEvidenceUnavailable as exc:
        raise HTTPException(status_code=409, detail={"code": "EVIDENCE_UNAVAILABLE", "message": str(exc)}) from exc
    except IntelligenceSnapshotBudgetExceeded as exc:
        raise HTTPException(status_code=413, detail={"code": "SNAPSHOT_BUDGET_EXCEEDED", "message": str(exc)}) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return jsonable_encoder(asdict(snapshot))

