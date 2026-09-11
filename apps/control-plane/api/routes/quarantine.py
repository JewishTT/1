"""Dead-letter quarantine + replay/re-evaluation API (T065, FR-023, US3).

Preserved rejected candidates can be listed and replayed; replay keeps the
original payload byte-for-byte so re-evaluation is faithful to the poison
message that produced the failure.
"""

from __future__ import annotations

import base64
from typing import Annotated

from events.dlq import DLQRecord, QuarantineStore
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import TenantContext, resolve_tenant

router = APIRouter(prefix="/dlq", tags=["dlq"])

_store = QuarantineStore()
# Seed one preserved rejection so the smoke path has content.
_store.quarantine(
    DLQRecord(reason="parse-failure", payload=b"malformed candidate", topic="cognitive-events--t-default-tenant")
)


class ReplayResponse(BaseModel):
    record_id: str
    base64_payload: str
    replayed_from_quarantine: bool


@router.get("")
async def list_quarantine(
    topic: str | None = None,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    return {"tenant_id": ctx.tenant_id, "records": _store.list(topic)}


@router.get("/{record_id}", response_model=ReplayResponse)
async def get_quarantined(record_id: str, ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None) -> ReplayResponse:
    record = _store.get(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="record not found")
    return ReplayResponse(record_id=record.record_id, base64_payload=base64.b64encode(record.payload).decode(), replayed_from_quarantine=True)


@router.post("/{record_id}/replay", response_model=ReplayResponse)
async def replay_record(record_id: str, ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None) -> ReplayResponse:
    payload = _store.replay(record_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="record not found")
    return ReplayResponse(record_id=record_id, base64_payload=base64.b64encode(payload).decode(), replayed_from_quarantine=True)


@router.post("/{record_id}/re-evaluate")
async def re_evaluate(record_id: str, ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None) -> dict:
    record = _store.get(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="record not found")
    mark = "rejected" if "malformed" in record.reason else "accepted"
    _store.purge(record_id)
    return {"record_id": record_id, "re_evaluated": mark, "tenant_id": ctx.tenant_id}