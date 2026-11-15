"""Economic intelligence API; consumes the foundational Intelligence read model."""
from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder

from api.auth import TenantContext, require_analyst
from economics.service import ECONOMIC_PURPOSE, load_economic_context
from services.intelligence_access import intelligence_port
from services.intelligence_reader import (
    IntelligenceEvidenceUnavailable,
    IntelligenceReadDenied,
    IntelligenceSnapshotBudgetExceeded,
    IntelligenceSubjectNotFound,
)
from shared.contracts.intelligence_feed import IntelligenceQuery

router = APIRouter(prefix="/economics", tags=["economics-silo"])


@router.get("/subjects/{subject_ref}")
async def get_economic_context(
    subject_ref: str,
    ctx: Annotated[TenantContext, Depends(require_analyst)],
    max_hops: int = Query(default=2, ge=0, le=8),
) -> dict:
    """Resolve the subject and its evidenced relationships through Intelligence only."""
    try:
        reader = await intelligence_port(ctx, purpose=ECONOMIC_PURPOSE)
        query = IntelligenceQuery(
            tenant_id=ctx.tenant_id,
            subject_ref=subject_ref,
            purpose=ECONOMIC_PURPOSE,
            max_hops=max_hops,
        )
        snapshot, subjects = await load_economic_context(reader, query)
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
    return jsonable_encoder({
        "snapshot_id": snapshot.snapshot_id,
        "tenant_id": snapshot.tenant_id,
        "subject_entity_id": snapshot.subject_entity_id,
        "subjects": [asdict(subject) for subject in subjects],
        "relations": [asdict(relation) for relation in snapshot.relations],
        "source": "intelligence_read_port",
        "financial_flow_ledger": "not_yet_wired",
    })

