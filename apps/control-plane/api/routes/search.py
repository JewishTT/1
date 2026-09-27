"""Search plane endpoints (T026/T051, US2).

Lexical/structural search with metadata/temporal/source/investigation filters,
answered by the two real backends in ``services.search_backends``. Backend
selection is invisible to the caller: every result carries a uniform evidence
chain resolving to immutable observations (I-1).

Three response shapes, and the difference between them is the whole point
(Constitution Invariant 9):

``200`` with results
    the query was answered;
``200`` with ``results: []`` **and** a non-empty ``degraded_backends``
    the query was answered, but one backend did not contribute -- the empty set
    is a real answer from the backends that did;
``503``
    *every* backend failed, raised by ``QueryPlanner`` as
    ``AllBackendsFailed``. Never ``200 {"results": []}``, because a caller cannot
    tell "nothing matched" from "everything is down" and would read the second as
    the first.

``degraded_backends`` is non-empty if and only if a selected backend failed.
``QueryPlanner`` attaches that list to every result it returns; the one case it
cannot express is a partial outage whose surviving backends all found nothing,
which is why ``services.search_backends.degradations`` also reads what the
backends themselves raised. The verdict on whether such a failure was
recoverable stays with the planner.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.auth import TenantContext, resolve_tenant
from services.query_planner import AllBackendsFailed, QueryFilters, QueryPlanner
from services.search_backends import (
    MAX_LIMIT,
    build_query_planner,
    degradations,
    parse_instant,
)

router = APIRouter(prefix="/search", tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    mode: str = "hybrid"  # lexical | semantic | hybrid
    temporal_from: str | None = None
    temporal_to: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    investigation_id: str | None = None
    limit: int = Field(default=20, ge=1, le=MAX_LIMIT)


def _filters(
    *,
    source_ids: list[str] | frozenset[str],
    investigation_id: str | None,
    temporal_from: str | None,
    temporal_to: str | None,
) -> QueryFilters:
    """Build the planner's filters, refusing a temporal bound we cannot read.

    The backends fail a bound closed -- a document it cannot place in time is not
    returned when a window was asked for -- so an unparsable bound would answer
    every query with an empty set and name no reason. It is a caller error, said
    so here.
    """
    for name, value in (("temporal_from", temporal_from), ("temporal_to", temporal_to)):
        if value is not None and parse_instant(value) is None:
            raise HTTPException(
                status_code=422, detail=f"{name} is not an ISO-8601 instant: {value!r}"
            )
    return QueryFilters(
        temporal_from=temporal_from,
        temporal_to=temporal_to,
        source_ids=frozenset(source_ids),
        investigation_id=investigation_id,
    )


async def _answer(
    planner: QueryPlanner,
    *,
    query: str,
    mode: str,
    tenant_id: str,
    filters: QueryFilters,
    limit: int,
) -> Any:
    plan = planner.plan(query, filters=filters)
    try:
        results = await planner.execute(plan, limit=limit)
    except AllBackendsFailed as exc:
        # A total outage, not an empty answer. The degraded list is the planner's
        # own, so every named backend and error is the one it decided on.
        return JSONResponse(
            status_code=503,
            content={
                "error": "all_backends_failed",
                "query": query,
                "mode": mode,
                "tenant_id": tenant_id,
                "results": [],
                "degraded_backends": exc.degraded_backends,
            },
        )
    return {
        "query": query,
        "mode": mode,
        "tenant_id": tenant_id,
        "results": [r.__dict__ for r in results],
        "degraded_backends": degradations(planner, results),
    }


@router.get("")
async def search(
    q: str,
    mode: str = "hybrid",
    source_ids: str | None = None,
    investigation_id: str | None = None,
    temporal_from: str | None = None,
    temporal_to: str | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 20,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> Any:
    if not q:
        raise HTTPException(status_code=422, detail="query required")
    filters = _filters(
        source_ids=[s for s in (source_ids or "").split(",") if s],
        investigation_id=investigation_id,
        temporal_from=temporal_from,
        temporal_to=temporal_to,
    )
    return await _answer(
        build_query_planner(ctx.tenant_id),
        query=q,
        mode=mode,
        tenant_id=ctx.tenant_id,
        filters=filters,
        limit=limit,
    )


@router.post("")
async def search_body(
    body: SearchRequest,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> Any:
    filters = _filters(
        source_ids=body.source_ids,
        investigation_id=body.investigation_id,
        temporal_from=body.temporal_from,
        temporal_to=body.temporal_to,
    )
    return await _answer(
        build_query_planner(ctx.tenant_id),
        query=body.query,
        mode=body.mode,
        tenant_id=ctx.tenant_id,
        filters=filters,
        limit=body.limit,
    )
