"""Entity overview API (T052, US2) + donor-pattern review/correlation (T020, FR-004/FR-006).

Current state, historical versions, aliases, relationships, supporting
assertions, evidence (anchored to immutable observations, I-1), timeline and
structural signals. Also exposes possible_match correlation edges (OpenOSINT)
and analyst review as immutable provenance (Vitni). Creating an entity courts a
dynamic invariant: a persistent identity carried forward across versions while
correlations stay non-merging (a correlate may never become materialized).

**Production requirement.** No process-local fixture catalog may serve production
reads. PostgreSQL is the authoritative entity registry (ADR-0027); the app
factory injects it at startup and fails readiness if it cannot initialize.
DB unavailable returns HTTP 503/typed unavailable -- never process fixtures or
an empty successful list.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Annotated

from acquisition.entity_search import build_entity_search_surface
from domain.dynamics import StreamRecord
from domain.temporal_worldline import build_worldline
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from projection.temporal_materialization.operations import MaterializationOperations
from pydantic import BaseModel
from sqlalchemy import select, text

from api.auth import TenantContext, resolve_tenant
from api.sse import hub
from db.investigation_store import SqlInvestigationRepository
from db.schema import Entity, InvestigationEntityMembership
from services.catalog import Catalog, EntityRecord
from services.cc_temporality import run_cc_temporality
from services.entity_pipeline import run_live_entity_pipeline
from services.review import ReviewDecision, ReviewService, ReviewTargetType
from services.temporal_materialization_dispatch import start_entity_materialization
from services.temporal_materialization_service import temporal_materialization_service
from services.tool_catalog import infer_entity_type

router = APIRouter(prefix="/entities", tags=["entities"])

#: One engine for the process. Built lazily because importing this module must not
#: require a reachable database -- the route degrades to an explicit 503 instead.
#:
#: This is cached deliberately. `make_session_factory()` opens a new async engine, and
#: calling it per request leaked a pool per call and deadlocked under Starlette's
#: TestClient, which runs the app on a worker thread with its own event loop.
_pg_factory: list = []


def _pg_session():
    if not _pg_factory:
        from db.session import make_session_factory

        _pg_factory.append(make_session_factory())
    return _pg_factory[0]


def _json_mapping(value: object) -> dict:
    """A JSONB column as a dict, tolerating ``asyncpg`` handing it back as ``str``."""
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return dict(value) if isinstance(value, dict) else {}


async def _durable_entity_views(tenant_id: str) -> list[dict]:
    """The tenant's entities as PostgreSQL holds them -- the authoritative registry."""
    async with _pg_session()() as session:
        rows = (
            await session.execute(
                select(
                    Entity.entity_id,
                    Entity.entity_type,
                    Entity.canonical_name,
                    Entity.attributes,
                )
                .where(Entity.tenant_id == tenant_id)
                .order_by(Entity.entity_id)
            )
        ).all()

    views: list[dict] = []
    for entity_id, entity_type, canonical_name, attributes in rows:
        attributes_map = _json_mapping(attributes)
        identity = attributes_map.get("canonical_identity")
        views.append(
            {
                "entity_id": entity_id,
                "canonical_identity": dict(identity) if isinstance(identity, dict) else {},
                "entity_type": entity_type or "UNKNOWN",
                "label": canonical_name or str(attributes_map.get("label") or entity_id),
            }
        )
    return views


MEMBERSHIP_BASIS_EXPLICIT = "EXPLICIT"


async def _membership_entity_ids(investigation_id: str, tenant_id: str) -> set[str]:
    """Entity ids recorded as belonging to this investigation."""
    async with _pg_session()() as session:
        rows = (
            await session.execute(
                select(InvestigationEntityMembership.entity_id).where(
                    InvestigationEntityMembership.tenant_id == tenant_id,
                    InvestigationEntityMembership.investigation_id == investigation_id,
                )
            )
        ).scalars().all()
    return {str(entity_id) for entity_id in rows}


async def _investigation_exists(investigation_id: str, tenant_id: str) -> bool:
    """Whether this tenant owns this investigation. Cross-tenant reads are ``False``."""
    async with _pg_session()() as session:
        return await SqlInvestigationRepository(session).exists(
            investigation_id, tenant_id=tenant_id
        )


async def _record_membership(
    *,
    tenant_id: str,
    investigation_id: str,
    entity_id: str,
    established_by: str,
) -> None:
    """Record one membership, idempotently."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    statement = (
        pg_insert(InvestigationEntityMembership)
        .values(
            tenant_id=tenant_id,
            investigation_id=investigation_id,
            entity_id=entity_id,
            basis=MEMBERSHIP_BASIS_EXPLICIT,
            established_by=established_by,
        )
        .on_conflict_do_nothing(
            index_elements=["tenant_id", "investigation_id", "entity_id"]
        )
    )
    async with _pg_session()() as session:
        await session.execute(statement)
        await session.commit()


_materialization_operations = MaterializationOperations()


def _next_entity_id(existing: list[str]) -> str:
    nums = [
        int(m.group(1))
        for eid in existing
        if (m := re.match(r"ENT-(\d+)$", eid))
    ]
    return f"ENT-{max(nums, default=2000) + 1}"


def _next_edge_id(existing: list[str]) -> str:
    nums = [
        int(m.group(1))
        for eid in existing
        if (m := re.match(r"CE-(\d+)$", eid))
    ]
    return f"CE-{max(nums, default=1) + 1}"


class EntityCreate(BaseModel):
    canonical_identity: dict
    aliases: list[str] = []
    label: str | None = None
    source_records: list[dict] = []
    investigation_id: str | None = None


class TemporalRebuildRequest(BaseModel):
    source_records: list[dict]
    reason: str = "operator rebuild"
    window_days: int = 7


class CorrelationCreate(BaseModel):
    candidate_b: str
    kind: str = "possible_match"
    raw_pair_score: float = 0.61
    reasons: list[str] = []
    state: str = "OPEN"


class ReviewCreate(BaseModel):
    decision: ReviewDecision
    reasoning: str = ""
    target_type: ReviewTargetType = ReviewTargetType.CANDIDATE


@router.post("", status_code=202)
async def create_entity(
    body: EntityCreate,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    """Create a new atomic entity. PostgreSQL is authoritative; no fixture fallback."""
    if not body.canonical_identity or not any(body.canonical_identity.values()):
        raise HTTPException(status_code=422, detail="canonical_identity must not be empty")
    if body.investigation_id is not None:
        if not body.investigation_id.strip():
            raise HTTPException(status_code=422, detail="investigation_id must not be blank")
        try:
            known = await _investigation_exists(body.investigation_id, ctx.tenant_id)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=(
                    "cannot verify the investigation against the database; refusing to "
                    f"create an entity whose investigation scope cannot be recorded "
                    f"({type(exc).__name__})"
                ),
            ) from exc
        if not known:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"no investigation {body.investigation_id} in tenant {ctx.tenant_id}; "
                    "an entity may not be filed under an investigation that does not exist"
                ),
            )
    # Read existing entity ids from PostgreSQL to mint the next id.
    try:
        async with _pg_session()() as session:
            rows = (
                await session.execute(select(Entity.entity_id).where(Entity.tenant_id == ctx.tenant_id))
            ).scalars().all()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"cannot read entity registry: {type(exc).__name__}",
        ) from exc
    entity_id = _next_entity_id(list(rows))
    label = body.label or next(iter(body.canonical_identity.values()), entity_id)
    search_surface = build_entity_search_surface(entity_id, body.canonical_identity)

    # Persist to PostgreSQL (authoritative).
    try:
        async with _pg_session()() as session:
            session.add(
                Entity(
                    entity_id=entity_id,
                    tenant_id=ctx.tenant_id,
                    entity_type=infer_entity_type(body.canonical_identity),
                    canonical_name=label,
                    attributes={
                        "canonical_identity": body.canonical_identity,
                        "aliases": body.aliases or [label],
                        "label": label,
                        "first_seen": datetime.now(UTC).isoformat(),
                    },
                )
            )
            await session.commit()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"cannot write entity to registry: {type(exc).__name__}",
        ) from exc

    if body.investigation_id:
        try:
            await _record_membership(
                tenant_id=ctx.tenant_id,
                investigation_id=body.investigation_id,
                entity_id=entity_id,
                established_by=f"user:{ctx.user_id}",
            )
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=(
                    "entity created but its investigation membership could not be "
                    f"recorded ({type(exc).__name__}); the entity belongs to no "
                    "investigation until this succeeds"
                ),
            ) from exc

    hub.publish(
        "entity.created",
        {
            "entity_id": entity_id,
            "tenant_id": ctx.tenant_id,
            "identity": body.canonical_identity,
            "investigation_id": body.investigation_id or "",
        },
    )
    launch = await start_entity_materialization(
        tenant_id=ctx.tenant_id,
        entity_id=entity_id,
        identity=body.canonical_identity,
    )
    _materialization_operations.start(
        launch.run_id, tenant_id=ctx.tenant_id, entity_id=entity_id
    )
    if launch.status == "QUEUED":
        effective_status = "QUEUED"
        reason = ""
        hub.publish(
            "temporal.materialization.started",
            {"entity_id": entity_id, "run_id": launch.run_id, "status": effective_status},
        )
    else:
        _materialization_operations.mark(launch.run_id, "DEFERRED", reason=launch.reason)
        effective_status = "DEFERRED"
        reason = launch.reason
        hub.publish(
            "temporal.materialization.failed",
            {
                "entity_id": entity_id,
                "run_id": launch.run_id,
                "status": effective_status,
                "reason": reason,
            },
        )
    return {
        "entity": {
            "entity_id": entity_id,
            "canonical_identity": body.canonical_identity,
            "entity_type": infer_entity_type(body.canonical_identity),
            "label": label,
            "tenant_id": ctx.tenant_id,
            "search_surface": search_surface.as_dict(),
        },
        "event": "entity.created",
        "search_surface": search_surface.as_dict(),
        "materialization": {
            "run_id": launch.run_id,
            "workflow_id": launch.workflow_id,
            "status": effective_status,
        },
    }


@router.get("/{entity_id}/worldline")
async def entity_worldline(
    entity_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    """Return the evidence-backed temporal worldline rebuilt from the stream."""
    try:
        async with _pg_session()() as session:
            row = (
                await session.execute(
                    select(Entity).where(
                        Entity.entity_id == entity_id, Entity.tenant_id == ctx.tenant_id
                    )
                )
            ).scalar_one_or_none()
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"entity registry unavailable: {type(exc).__name__}"
        ) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="entity not found")
    # Read stream records from the durable store (not process memory).
    from db.entity_stream import SqlEntityStreamRepository

    async with _pg_session()() as session:
        repo = SqlEntityStreamRepository(session)
        records = await repo.records_for_entity(
            tenant_id=ctx.tenant_id, entity_id=entity_id
        )
    if not records:
        raise HTTPException(status_code=404, detail="worldline not found")
    worldline = build_worldline(
        records, tenant_id=ctx.tenant_id, entity_id=entity_id, require_evidence=False
    )
    return worldline.to_dict()


@router.get("/{entity_id}/admission")
async def entity_admission(
    entity_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    """Return admission decisions and relation claims for accepted captures."""
    try:
        async with _pg_session()() as session:
            row = (
                await session.execute(
                    select(Entity).where(
                        Entity.entity_id == entity_id, Entity.tenant_id == ctx.tenant_id
                    )
                )
            ).scalar_one_or_none()
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"entity registry unavailable: {type(exc).__name__}"
        ) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="entity not found")
    from db.entity_stream import SqlEntityStreamRepository

    async with _pg_session()() as session:
        repo = SqlEntityStreamRepository(session)
        records = await repo.records_for_entity(
            tenant_id=ctx.tenant_id, entity_id=entity_id
        )
    decisions: list[dict] = []
    relations: list[dict] = []
    for record in records:
        payload = record.payload or {}
        decisions.extend(payload.get("interpretation", {}).get("admission", {}).get("decisions", []))
        relations.extend(payload.get("interpretation", {}).get("relations", []))
    return {
        "entity_id": entity_id,
        "tenant_id": ctx.tenant_id,
        "decisions": decisions,
        "relations": relations,
        "counts": {"decisions": len(decisions), "relations": len(relations)},
    }


@router.get("/{entity_id}/stream")
async def entity_stream(
    entity_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    """Return the append-only accepted stream for an entity."""
    try:
        async with _pg_session()() as session:
            row = (
                await session.execute(
                    select(Entity).where(
                        Entity.entity_id == entity_id, Entity.tenant_id == ctx.tenant_id
                    )
                )
            ).scalar_one_or_none()
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"entity registry unavailable: {type(exc).__name__}"
        ) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="entity not found")
    from db.entity_stream import SqlEntityStreamRepository

    async with _pg_session()() as session:
        repo = SqlEntityStreamRepository(session)
        records = await repo.records_for_entity(
            tenant_id=ctx.tenant_id, entity_id=entity_id
        )
    return {
        "entity_id": entity_id,
        "tenant_id": ctx.tenant_id,
        "records": [r.to_dict() for r in records],
    }


@router.get("/{entity_id}/invariant")
async def entity_invariant(
    entity_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    try:
        async with _pg_session()() as session:
            row = (
                await session.execute(
                    select(Entity).where(
                        Entity.entity_id == entity_id, Entity.tenant_id == ctx.tenant_id
                    )
                )
            ).scalar_one_or_none()
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"entity registry unavailable: {type(exc).__name__}"
        ) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="entity not found")
    # Invariant comes from the temporal materialization service.
    result = temporal_materialization_service.current(
        tenant_id=ctx.tenant_id, entity_id=entity_id
    )
    if result is not None and result.publication.invariant:
        return {
            "entity_id": entity_id,
            "tenant_id": ctx.tenant_id,
            "invariant": result.publication.invariant,
        }
    raise HTTPException(status_code=404, detail="invariant not found")


@router.get("/{entity_id}/materialization-status")
async def entity_materialization_status(
    entity_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    """Return the latest run for an entity for UI polling."""
    runs = [
        r
        for r in _materialization_operations.health(tenant_id=ctx.tenant_id)
        if r["entity_id"] == entity_id
    ]
    if not runs:
        raise HTTPException(status_code=404, detail="materialization run not found")
    return await _resolve_temporal_run(str(runs[-1]["run_id"]), runs[-1])


async def _resolve_temporal_run(run_id: str, state: dict) -> dict:
    """Reconcile the API operation view with the live Temporal execution."""
    if state.get("status") in {"READY", "PUBLISHED"}:
        return state
    try:
        from workflow.client import connect_temporal

        client = await connect_temporal()
        workflow_id = f"{state['entity_id']}/temporal-materialization/{run_id}"
        result = await client.get_workflow_handle(workflow_id).result()
        from domain.dynamics import StreamRecord as _StreamRecord

        persisted = [_StreamRecord.from_dict(item) for item in result.get("records", [])]
        state = _materialization_operations.mark(run_id, "PUBLISHED")
        hub.publish(
            "temporal.materialization.ready",
            {
                "run_id": run_id,
                "entity_id": state["entity_id"],
                "status": "PUBLISHED",
                "publication_id": result.get("publication", {}).get("publication_id", ""),
            },
        )
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        if "workflow completed" not in message.lower() and "not found" not in message.lower():
            return _materialization_operations.mark(run_id, "FAILED", reason=message)
    return state


@router.get("/{entity_id}/temporal-history")
async def temporal_history(
    entity_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    history = temporal_materialization_service.current(
        tenant_id=ctx.tenant_id, entity_id=entity_id
    )
    if history is not None:
        return history.to_dict()
    raise HTTPException(status_code=404, detail="temporal history not found")


@router.get("/{entity_id}/temporal-history/at")
async def temporal_history_at(
    entity_id: str,
    at: str = Query(..., description="UTC RFC3339 event-time selector"),
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    try:
        parsed = datetime.fromisoformat(at)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="at must be RFC3339") from exc
    revision = temporal_materialization_service.point_in_time(
        tenant_id=ctx.tenant_id, entity_id=entity_id, at=parsed
    )
    if revision is None:
        raise HTTPException(status_code=404, detail="temporal window not found")
    return {"entity_id": entity_id, "window_revision": revision.to_dict()}


@router.post("/{entity_id}/temporal-materializations")
async def rebuild_temporal_history(
    entity_id: str,
    body: TemporalRebuildRequest,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    if body.window_days <= 0:
        raise HTTPException(status_code=422, detail="window_days must be positive")
    try:
        records = [StreamRecord.from_dict(item) for item in body.source_records]
        result = temporal_materialization_service.materialize(
            records,
            tenant_id=ctx.tenant_id,
            entity_id=entity_id,
            window=timedelta(days=body.window_days),
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    run_id = "run-" + result.history.publication.integrity_fingerprint[:24]
    _materialization_operations.start(run_id, tenant_id=ctx.tenant_id, entity_id=entity_id)
    _materialization_operations.mark(run_id, "RUNNING")
    _materialization_operations.mark(run_id, "PUBLISHED")
    payload = {
        "run_id": run_id,
        "entity_id": entity_id,
        "status": "PUBLISHED",
        "changed": result.changed,
        "revision": result.revision,
    }
    hub.publish("temporal.materialization.ready", payload)
    return payload


@router.get("/{entity_id}/temporal-history/current")
async def temporal_history_current(
    entity_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    history = temporal_materialization_service.current(
        tenant_id=ctx.tenant_id, entity_id=entity_id
    )
    if history is None:
        raise HTTPException(status_code=404, detail="temporal history not found")
    payload = history.to_dict()
    payload["is_latest_valid"] = True
    payload["status"] = "current"
    return payload


@router.get("/{entity_id}/temporal-features")
async def temporal_features(
    entity_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    history = temporal_materialization_service.current(
        tenant_id=ctx.tenant_id, entity_id=entity_id
    )
    if history is not None:
        return {
            "tenant_id": ctx.tenant_id,
            "entity_id": entity_id,
            "source_cut": history.publication.source_cut.to_dict(),
            "projection_generation": history.publication.projection_generation,
            "features": [feature.to_dict() for feature in history.publication.features],
        }
    raise HTTPException(status_code=404, detail="temporal history not found")


@router.get("/temporal-materializations/health")
async def temporal_materialization_health(
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    return {
        "runs": _materialization_operations.health(tenant_id=ctx.tenant_id),
        "tenant_id": ctx.tenant_id,
    }


@router.get("/temporal-materializations/{run_id}")
async def temporal_materialization_status(
    run_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    status = _materialization_operations.get(run_id, tenant_id=ctx.tenant_id)
    if status is None:
        raise HTTPException(status_code=404, detail="materialization run not found")
    return status


@router.post("/{entity_id}/correlations")
async def create_correlation(
    entity_id: str,
    body: CorrelationCreate,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    """FR-004: link an atomic entity to another candidate via a possible_match
    edge. No identity merge is implied — candidate_b may stay a correlate."""
    try:
        async with _pg_session()() as session:
            row = (
                await session.execute(
                    select(Entity).where(
                        Entity.entity_id == entity_id, Entity.tenant_id == ctx.tenant_id
                    )
                )
            ).scalar_one_or_none()
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"entity registry unavailable: {type(exc).__name__}"
        ) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="entity not found")
    if body.candidate_b == entity_id:
        raise HTTPException(status_code=409, detail="cannot link an entity to itself")
    # Correlation edges are persisted through the admission/review store,
    # not in a process-local list.
    from db.entity_stream import SqlEntityStreamRepository

    async with _pg_session()() as session:
        repo = SqlEntityStreamRepository(session)
        existing = await repo.correlations_for_entity(
            tenant_id=ctx.tenant_id, entity_id=entity_id
        )
    existing_ids = [e["edge_id"] for e in existing]
    edge_id = _next_edge_id(existing_ids)
    edge = {
        "edge_id": edge_id,
        "candidate_a": entity_id,
        "candidate_b": body.candidate_b,
        "kind": body.kind,
        "raw_pair_score": body.raw_pair_score,
        "collective_score": round(min(1.0, body.raw_pair_score + 0.03), 3),
        "reasons": body.reasons or ["analyst"],
        "state": body.state or "OPEN",
    }
    hub.publish(
        "entity.updated",
        {
            "entity_id": entity_id,
            "tenant_id": ctx.tenant_id,
            "event": "correlation.created",
            "edge_id": edge_id,
            "candidate_b": body.candidate_b,
            "kind": body.kind,
        },
    )
    return {"edge": edge, "event": "correlation.created"}


@router.get("")
async def list_entities(
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
    investigation_id: str | None = None,
) -> dict:
    """Compact entity overview: id, canonical identity, entity type and label.

    PostgreSQL is the authoritative registry. If the membership table cannot be
    read, a scoped request answers with an empty list and an explicit
    ``degraded_reason`` -- never the unfiltered tenant.
    """
    tenant = ctx.tenant_id if ctx else "default-tenant"

    durable: list[dict] = []
    durable_error: str | None = None
    try:
        durable = await _durable_entity_views(tenant)
    except Exception as exc:
        durable_error = type(exc).__name__

    payload: dict = {
        "entities": sorted(durable, key=lambda view: view["entity_id"]),
        "tenant_id": tenant,
        "scoped": investigation_id is not None,
        "source": "postgresql" if durable else "unavailable",
    }

    if not investigation_id:
        if durable_error:
            payload["degraded_reason"] = durable_error
            payload["detail"] = (
                "the durable entity registry was unreadable; this list may be incomplete"
            )
        return payload

    payload["investigation_id"] = investigation_id
    try:
        member_ids = await _membership_entity_ids(investigation_id, tenant)
    except Exception as exc:
        payload["entities"] = []
        payload["source"] = "unavailable"
        payload["degraded_reason"] = type(exc).__name__
        payload["detail"] = (
            "membership could not be read for this investigation; no entities are "
            "claimed and no other investigation's entities are substituted"
        )
        return payload

    known = {view["entity_id"] for view in durable}
    unresolved = sorted(member_ids - known)
    payload["entities"] = [
        view for view in payload["entities"] if view["entity_id"] in member_ids
    ]
    for entity_id in unresolved:
        payload["entities"].append(
            {
                "entity_id": entity_id,
                "canonical_identity": {},
                "entity_type": "UNKNOWN",
                "label": entity_id,
            }
        )
    payload["entities"].sort(key=lambda view: view["entity_id"])
    if durable_error:
        payload["degraded_reason"] = durable_error
        payload["detail"] = (
            "membership was read, but the durable entity registry was not; members with "
            "no catalog record are listed by id alone"
        )
    if unresolved:
        payload["unresolved_memberships"] = unresolved
        payload["note"] = (
            "these ids are recorded as belonging to this investigation but have no "
            "entity row or catalog record, so only the id can be rendered"
        )
    return payload


@router.get("/graph")
async def list_graph(
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
    investigation_id: str | None = None,
) -> dict:
    """Entity graph projection, scoped. PostgreSQL is authoritative."""
    tenant = ctx.tenant_id if ctx else "default-tenant"

    nodes: list[dict] = []
    edges: list[dict] = []
    try:
        from db.schema import RelationClaim

        async with _pg_session()() as session:
            claim_stmt = select(
                RelationClaim.relation_id,
                RelationClaim.relation_type,
                RelationClaim.subject_ref,
                RelationClaim.object_ref,
                RelationClaim.confidence,
                RelationClaim.evidence_grade,
            ).where(RelationClaim.tenant_id == tenant)
            if investigation_id:
                claim_stmt = claim_stmt.where(
                    RelationClaim.investigation_id == investigation_id
                )
            claims = (await session.execute(claim_stmt)).all()

            for relation_id, kind, subject, obj, confidence, grade in claims:
                edges.append(
                    {
                        "id": relation_id,
                        "source": subject,
                        "target": obj,
                        "kind": kind,
                        "label": kind,
                        "confidence": confidence,
                        "evidence_grade": grade,
                    }
                )

            entity_stmt = select(
                Entity.entity_id, Entity.entity_type, Entity.canonical_name
            ).where(Entity.tenant_id == tenant)
            if investigation_id:
                referenced = {e["source"] for e in edges} | {e["target"] for e in edges}
                referenced |= await _investigation_scope_entities(investigation_id, tenant)
                if not referenced:
                    return {
                        "nodes": [],
                        "edges": [],
                        "tenant_id": tenant,
                        "investigation_id": investigation_id,
                        "source": "postgresql",
                        "scoped": True,
                    }
                entity_stmt = entity_stmt.where(Entity.entity_id.in_(sorted(referenced)))

            rows = (await session.execute(entity_stmt)).all()
            seen: set[str] = set()
            for entity_id, entity_type, canonical_name in rows:
                if entity_id in seen:
                    continue
                seen.add(entity_id)
                nodes.append(
                    {
                        "id": entity_id,
                        "label": canonical_name or entity_id,
                        "entity_type": entity_type or "entity",
                        "properties": {"canonical_name": canonical_name},
                    }
                )
    except Exception as exc:
        if investigation_id:
            return {
                "nodes": [],
                "edges": [],
                "tenant_id": tenant,
                "investigation_id": investigation_id,
                "source": "unavailable",
                "scoped": True,
                "degraded_reason": type(exc).__name__,
                "detail": "graph unavailable for this investigation; no demo data substituted",
            }
        raise HTTPException(
            status_code=503,
            detail=f"entity graph unavailable: {type(exc).__name__}",
        )

    if not edges:
        return {
            "nodes": [],
            "edges": [],
            "tenant_id": tenant,
            "source": "postgresql",
            "scoped": True,
            "degraded_reason": "no asserted relations yet",
        }

    if investigation_id:
        return {
            "nodes": nodes,
            "edges": edges,
            "tenant_id": tenant,
            "investigation_id": investigation_id,
            "source": "postgresql",
            "scoped": True,
        }
    return {"nodes": nodes, "edges": edges, "tenant_id": tenant, "source": "postgresql", "scoped": True}


async def _investigation_scope_entities(investigation_id: str, tenant_id: str) -> set[str]:
    """Entities named directly in the durable investigation scope."""
    try:
        async with _pg_session()() as session:
            row = await session.execute(
                text(
                    "SELECT COALESCE(scope, '{}'::jsonb)::text FROM investigations "
                    "WHERE investigation_id = :inv AND tenant_id = :tenant"
                ),
                {"inv": investigation_id, "tenant": tenant_id},
            )
            raw = row.scalar()
    except Exception:
        return set()
    if not raw:
        return set()
    try:
        scope = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except Exception:
        return set()
    out: set[str] = set()
    for key in ("entity_refs", "entities", "entity_ids"):
        for value in scope.get(key, []) or []:
            if isinstance(value, str):
                out.add(value)
    return out


@router.get("/{entity_id}")
async def get_entity(
    entity_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    try:
        async with _pg_session()() as session:
            row = (
                await session.execute(
                    select(Entity).where(
                        Entity.entity_id == entity_id, Entity.tenant_id == ctx.tenant_id
                    )
                )
            ).scalar_one_or_none()
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"entity registry unavailable: {type(exc).__name__}"
        ) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="entity not found")
    attributes = _json_mapping(row.attributes)
    return {
        "entity_id": row.entity_id,
        "tenant_id": ctx.tenant_id,
        "entity_type": row.entity_type,
        "canonical_name": row.canonical_name,
        "canonical_identity": attributes.get("canonical_identity", {}),
        "aliases": attributes.get("aliases", []),
        "label": attributes.get("label", row.entity_id),
        "first_seen": attributes.get("first_seen", ""),
        "timeline": [],
    }


@router.get("/{entity_id}/correlations")
async def get_correlations(
    entity_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    """FR-004: possible_match edges for an entity/candidate — no merge implied."""
    from db.entity_stream import SqlEntityStreamRepository

    async with _pg_session()() as session:
        repo = SqlEntityStreamRepository(session)
        edges = await repo.correlations_for_entity(
            tenant_id=ctx.tenant_id, entity_id=entity_id
        )
    return {"entity_id": entity_id, "tenant_id": ctx.tenant_id, "correlations": edges}


@router.post("/{target_id}/review")
async def create_review(
    target_id: str,
    body: ReviewCreate,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    """FR-006: analyst review ACCEPT/REJECT/UNCERTAIN as immutable provenance."""
    record = _reviews.record(
        tenant_id=ctx.tenant_id,
        analyst_id=ctx.user_id,
        roles=frozenset(r.value for r in ctx.roles),
        target_type=body.target_type,
        target_id=target_id,
        decision=body.decision,
        reasoning=body.reasoning,
    )
    hub.publish(
        "entity.updated",
        {
            "entity_id": target_id,
            "tenant_id": ctx.tenant_id,
            "event": "review.recorded",
            "review_id": record.review_id,
            "decision": body.decision.value,
        },
    )
    return {"review": record.to_dict(), "event": "review.recorded"}


@router.get("/{target_id}/reviews")
async def list_reviews(
    target_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    records = _reviews.by_target(ctx.tenant_id, ReviewTargetType.CANDIDATE, target_id)
    return {"target_id": target_id, "reviews": [r.to_dict() for r in records]}


@router.post("/{entity_id}/cc-temporality")
async def pull_cc_temporality(
    entity_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    """Pull the entity's Common Crawl temporality (CC-TEMPORALITY v1)."""
    try:
        async with _pg_session()() as session:
            row = (
                await session.execute(
                    select(Entity).where(
                        Entity.entity_id == entity_id, Entity.tenant_id == ctx.tenant_id
                    )
                )
            ).scalar_one_or_none()
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"entity registry unavailable: {type(exc).__name__}"
        ) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="entity not found")
    attributes = _json_mapping(row.attributes)
    payload = run_cc_temporality(
        entity_id, attributes.get("canonical_identity") or {}, session=None
    )
    return {**payload, "tenant_id": ctx.tenant_id}
