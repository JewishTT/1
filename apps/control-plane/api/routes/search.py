"""Search plane endpoints (T051, US2).

Lexical/semantic/hybrid search with metadata/temporal/source/investigation
filters. Backend selection is invisible to the caller: every result carries a
uniform evidence chain resolving to immutable observations (I-1).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import TenantContext, resolve_tenant
from services.query_planner import BackendHit, MemoryBackend, QueryFilters, QueryPlanner

router = APIRouter(prefix="/search", tags=["search"])

# Hermetic fixture corpus so the smoke path is alive without external backends.
_FIXTURE_DOCS = MemoryBackend(
    name="search",
    docs=[
        BackendHit(doc_id="OBS-1001", kind="observation", score=0.9, observation_id="OBS-1001",
                   source_id="src-a", payload={"text": "Yard account transfers detected", "investigation_id": "INV-DEMO"}),
        BackendHit(doc_id="ENT-2001", kind="entity", score=0.7, observation_id="OBS-1001",
                   source_id="src-a", payload={"text": "suspicious account Yard", "investigation_id": "INV-DEMO"}),
        BackendHit(doc_id="DOC-3001", kind="document", score=0.4, observation_id="OBS-1002",
                   source_id="src-b", payload={"text": "unrelated weather report", "investigation_id": "INV-DEMO"}),
    ],
)

_OBSERVATIONS = {
    "OBS-1001": {"observation_id": "OBS-1001", "uri": "http://fixtures.local/report.html", "content_hash": "sha256:aa"},
    "OBS-1002": {"observation_id": "OBS-1002", "uri": "http://fixtures.local/weather.html", "content_hash": "sha256:bb"},
}

# A single shared planner for the quickstart/smoke path.
_planner = QueryPlanner(backends={"search": _FIXTURE_DOCS}, observations=_OBSERVATIONS)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    mode: str = "hybrid"  # lexical | semantic | hybrid
    temporal_from: str | None = None
    temporal_to: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    investigation_id: str | None = None
    limit: int = 20


@router.get("")
async def search(
    q: str,
    mode: str = "hybrid",
    source_ids: str | None = None,
    investigation_id: str | None = None,
    limit: int = 20,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    if not q:
        raise HTTPException(status_code=422, detail="query required")
    filters = QueryFilters(
        source_ids=frozenset(s for s in (source_ids or "").split(",") if s),
        investigation_id=investigation_id,
    )
    planner = _planner
    plan = planner.plan(q, filters=filters)
    results = await planner.execute(plan, limit=limit)
    return {"query": q, "mode": mode, "tenant_id": ctx.tenant_id, "results": [r.__dict__ for r in results]}


@router.post("")
async def search_body(
    body: SearchRequest,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    filters = QueryFilters(
        temporal_from=body.temporal_from,
        temporal_to=body.temporal_to,
        source_ids=frozenset(body.source_ids),
        investigation_id=body.investigation_id,
    )
    plan = _planner.plan(body.query, filters=filters)
    results = await _planner.execute(plan, limit=body.limit)
    return {"query": body.query, "mode": body.mode, "tenant_id": ctx.tenant_id, "results": [r.__dict__ for r in results]}