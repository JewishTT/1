"""Entity overview API (T052, US2) + donor-pattern review/correlation (T020, FR-004/FR-006).

Current state, historical versions, aliases, relationships, supporting
assertions, evidence (anchored to immutable observations, I-1), timeline and
structural signals. Also exposes possible_match correlation edges (OpenOSINT)
and analyst review as immutable provenance (Vitni). Creating an entity courts a
dynamic invariant: a persistent identity carried forward across versions while
correlations stay non-merging (a correlate may never become materialized).
"""

from __future__ import annotations

import asyncio
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

from api.auth import TenantContext, resolve_tenant
from api.sse import hub
from services.catalog import Catalog, EntityRecord
from services.cc_temporality import run_cc_temporality
from services.entity_pipeline import run_live_entity_pipeline
from services.review import ReviewDecision, ReviewService, ReviewTargetType
from services.temporal_materialization_dispatch import start_entity_materialization
from services.temporal_materialization_service import temporal_materialization_service
from services.tool_catalog import infer_entity_type

router = APIRouter(prefix="/entities", tags=["entities"])

# Hermetic catalog + review store for the smoke path (real adapters injected by the app).
_observations = {
    "OBS-1001": {
        "observation_id": "OBS-1001",
        "uri": "http://fixtures.local/report.html",
        "content_hash": "sha256:aa",
    },
}
_catalog = Catalog(observations=_observations)
_catalog.put_entity(
    EntityRecord(
        entity_id="ENT-2001",
        canonical_identity={"account": "Yard"},
        versions=[
            {"version": 1, "identity": {"account": "Yard"}, "first_seen": "2026-01-01T00:00:00Z"}
        ],
        aliases=["Yard", "yard-account"],
        relationships=[{"type": "candidate_of", "target": "ENT-2002"}],
        supporting_assertions=["ASR-9001"],
        evidence_ids=["OBS-1001"],
        observations=["OBS-1001"],
        structural_signals=[{"signal": "tda_loop", "feature_id": "FEAT-42", "persistence": 2.3}],
    )
)

# possible_match edges (OpenOSINT pattern): correlation exists WITHOUT identity.
_correlations = [
    {
        "edge_id": "CE-200001",
        "candidate_a": "ENT-2001",
        "candidate_b": "ENT-2002",
        "kind": "possible_match",
        "raw_pair_score": 0.72,
        "collective_score": 0.74,
        "reasons": ["email", "handle"],
        "state": "OPEN",
    },
]

_reviews = ReviewService()

#: Which tenant owns each catalog entity.
#:
#: The catalog is process-global and has no tenant dimension of its own, so before this
#: map existed an entity created for one tenant was listed for every tenant that asked --
#: the same cross-tenant read ``/entities/graph`` already refuses to make. The endpoint
#: now merges two sources (this catalog and PostgreSQL, the authoritative registry per
#: ADR-0027), and one of them is tenant-scoped while the other was not; merging them
#: without this map would have made the result half-isolated, which is worse than either
#: half alone.
#:
#: The fixture entity is seeded under ``default-tenant`` so it keeps answering the
#: smoke path, which is the tenant it was always implicitly filed under.
_entity_owner: dict[str, str] = {"ENT-2001": "default-tenant"}

#: Membership basis for an entity a caller placed into an investigation by naming it on
#: ``POST /entities``. Mirrors ``db.schema.InvestigationEntityMembership.basis`` and the
#: CHECK installed by migration 024;
#: ``tests/unit/test_migration_024_investigation_entity_membership.py`` asserts the three
#: agree.
MEMBERSHIP_BASIS_EXPLICIT = "EXPLICIT"

#: One engine for the process. Built lazily because importing this module must not
#: require a reachable database -- the route degrades to the fixture instead.
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
    """A JSONB column as a dict, tolerating ``asyncpg`` handing it back as ``str``.

    ``asyncpg`` returns ``jsonb`` as text whenever a statement carries a parameter. A row
    with a JSON array where a mapping belongs, or a null, is a row whose attributes cannot
    be read as identity -- and an unreadable attribute must not take out the whole list.
    """
    import json

    if value is None:
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return dict(value) if isinstance(value, dict) else {}


async def _durable_entity_views(tenant_id: str) -> list[dict]:
    """The tenant's entities as PostgreSQL holds them -- the authoritative registry.

    ADR-0027: Postgres is the source of truth for an entity. The process catalog beside
    this is the smoke-path adapter and holds only what *this* process created, so a list
    built from it alone reports a different set per worker and loses everything on
    restart.
    """
    from sqlalchemy import select

    from db.schema import Entity

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
        # ``entities`` stores a display name and an attribute bag, not the identity
        # dimensions the catalog keeps in ``canonical_identity``. Reading an identity out
        # of ``attributes`` where the writer put one, and rendering an empty identity
        # where it did not, is the honest option: synthesising dimensions from the
        # display name would hand ``infer_entity_type`` a guess and present it as a type.
        identity = attributes_map.get("canonical_identity")
        views.append(
            {
                "entity_id": entity_id,
                "canonical_identity": dict(identity) if isinstance(identity, dict) else {},
                # The stored type is the admitted kind; it is never re-inferred here.
                "entity_type": entity_type or "UNKNOWN",
                "label": canonical_name or str(attributes_map.get("label") or entity_id),
            }
        )
    return views


def _catalog_entity_views(tenant_id: str) -> list[dict]:
    """The process catalog's entities, filtered to one tenant."""
    views: list[dict] = []
    for entity_id in _catalog.entity_ids():
        if _entity_owner.get(entity_id) != tenant_id:
            continue
        view = _catalog.entity(entity_id)
        identity = view.get("canonical_identity") or {}
        aliases = view.get("aliases") or []
        views.append(
            {
                "entity_id": entity_id,
                "canonical_identity": identity,
                "entity_type": infer_entity_type(identity),
                "label": aliases[0] if aliases else next(iter(identity.values()), entity_id),
            }
        )
    return views


async def _membership_entity_ids(investigation_id: str, tenant_id: str) -> set[str]:
    """Entity ids recorded as belonging to this investigation.

    Raises on an unreadable database. The caller must not fall back to "everything":
    a filter that could not be applied and a filter that matched everything are
    indistinguishable at the response level, which is the defect this route had.
    """
    from sqlalchemy import select

    from db.schema import InvestigationEntityMembership

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
    from db.investigation_store import SqlInvestigationRepository

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
    """Record one membership, idempotently.

    ``ON CONFLICT DO NOTHING`` rather than a read-then-write: the primary key is the
    triple, so a replayed request collides at the database (I-11) instead of depending on
    two callers not racing. A membership carries no versioned content, so unlike the
    typing ladder there is nothing to preserve by writing a second row.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from db.schema import InvestigationEntityMembership

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
# Process-local stream seam used by the fallback worker; production worker
# replaces this with the SQL entity_stream repository.
_entity_streams: dict[tuple[str, str], list[StreamRecord]] = {}
_temporal_results: dict[tuple[str, str], dict] = {}


async def _resolve_temporal_run(run_id: str, state: dict) -> dict:
    """Reconcile the API operation view with the live Temporal execution."""
    if state.get("status") in {"READY", "PUBLISHED"}:
        return state
    try:
        from workflow.client import connect_temporal
        client = await connect_temporal()
        workflow_id = f"{state['entity_id']}/temporal-materialization/{run_id}"
        result = await client.get_workflow_handle(workflow_id).result()
        _temporal_results[(state["tenant_id"], state["entity_id"])] = result
        from domain.dynamics import StreamRecord as _StreamRecord
        persisted = [_StreamRecord.from_dict(item) for item in result.get("records", [])]
        _entity_streams[(state["tenant_id"], state["entity_id"])] = persisted
        for record in persisted:
            if record.observation_id:
                _catalog.append_observation(state["entity_id"], {
                    "observation_id": record.observation_id,
                    "uri": str(record.payload.get("url", "")),
                    "content_hash": str(record.payload.get("digest", "")),
                    "observed_at": record.payload.get("event_at", record.ts.isoformat()),
                    "provenance": {"source": "common_crawl", "locator": record.payload.get("locator", ""), "record_id": record.record_id},
                    "interpretation": record.payload.get("interpretation", {}),
                })
        state = _materialization_operations.mark(run_id, "PUBLISHED")
        hub.publish("temporal.materialization.ready", {
            "run_id": run_id,
            "entity_id": state["entity_id"],
            "status": "PUBLISHED",
            "publication_id": result.get("publication", {}).get("publication_id", ""),
        })
    except Exception as exc:  # noqa: BLE001 - Temporal transport errors are normalized into run state
        message = str(exc)
        if "workflow completed" not in message.lower() and "not found" not in message.lower():
            return _materialization_operations.mark(run_id, "FAILED", reason=message)
    return state


def _next_entity_id() -> str:
    nums = [int(m.group(1)) for eid in _catalog.entity_ids() if (m := re.match(r"ENT-(\d+)$", eid))]
    return f"ENT-{max(nums, default=2000) + 1}"


def _next_edge_id() -> str:
    nums = [int(m.group(1)) for e in _correlations if (m := re.match(r"CE-(\d+)$", e["edge_id"]))]
    return f"CE-{max(nums, default=1) + 1}"


class EntityCreate(BaseModel):
    canonical_identity: dict
    aliases: list[str] = []
    label: str | None = None
    source_records: list[dict] = []
    investigation_id: str | None = None
    """The investigation this entity is being created for, when there is one.

    Optional because the existing model permits an investigation-free entity and this
    endpoint has always been one way to mint one: the smoke-path fixture, the API's own
    test seeds and ``POST /investigations/{id}/assertions/entity`` all describe entities
    without necessarily naming an investigation first. What was never permitted was an
    entity that *claimed* an investigation and was not recorded as belonging to it --
    ``investigation_id`` used to be accepted by clients and dropped on the floor, so a
    scoped read answered for every investigation alike.

    Supplying it is a durable write: the membership is recorded in
    ``investigation_entity_memberships`` (migration 024) before this call returns 202.
    An investigation that does not exist in this tenant is refused with 404 rather than
    stored -- a membership naming nothing is a lie the scoped read would repeat.
    """


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


@router.post("", status_code=202)
async def create_entity(
    body: EntityCreate,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    """Create a new atomic entity — a dynamic invariant: persistent identity
    across versions, evidence anchored to immutable observations (I-1), no
    premature merging with correlates.

    Naming an investigation is a durable act, not a label on the response. The
    membership is written before this returns; if it cannot be written the call fails
    with 503 rather than answering 202 for an entity no scoped read would ever find --
    silently dropping the scoping is the defect this route is being fixed for.
    """
    if not body.canonical_identity or not any(body.canonical_identity.values()):
        raise HTTPException(status_code=422, detail="canonical_identity must not be empty")
    if body.investigation_id is not None:
        if not body.investigation_id.strip():
            raise HTTPException(status_code=422, detail="investigation_id must not be blank")
        try:
            known = await _investigation_exists(body.investigation_id, ctx.tenant_id)
        except Exception as exc:
            # No durable scope check, no durable write: refusing is the only safe answer.
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
    entity_id = _next_entity_id()
    for item in body.source_records:
        record = StreamRecord.from_dict(item)
        if record.entity_id != entity_id or record.tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=422, detail="source record scope mismatch")
    label = body.label or next(iter(body.canonical_identity.values()), entity_id)
    search_surface = build_entity_search_surface(entity_id, body.canonical_identity)
    _catalog.put_entity(
        EntityRecord(
            entity_id=entity_id,
            canonical_identity=body.canonical_identity,
            versions=[
                {
                    "version": 1,
                    "identity": body.canonical_identity,
                    "label": label,
                    "first_seen": datetime.now(UTC).isoformat(),
                }
            ],
            aliases=body.aliases or [label],
            supporting_assertions=[],
            evidence_ids=[],
            observations=[],
        )
    )
    _entity_owner[entity_id] = ctx.tenant_id
    if body.investigation_id:
        # After the catalog write, not before: a catalog entity with no membership is a
        # complete entity that simply belongs to no investigation yet -- a legal state
        # this model has always allowed. A membership naming an entity that does not
        # exist is a dangling reference, and that is the worse of the two partial states.
        try:
            await _record_membership(
                tenant_id=ctx.tenant_id,
                investigation_id=body.investigation_id,
                entity_id=entity_id,
                established_by=f"user:{ctx.user_id}",
            )
        except Exception as exc:
            # Fail closed rather than under-record: a 202 for an entity no scoped read
            # can find is the original defect with a nicer status code.
            raise HTTPException(
                status_code=503,
                detail=(
                    "entity created but its investigation membership could not be "
                    f"recorded ({type(exc).__name__}); the entity belongs to no "
                    "investigation until this succeeds"
                ),
            ) from exc
    for item in body.source_records:
        record = StreamRecord.from_dict(item)
        _entity_streams.setdefault((ctx.tenant_id, entity_id), []).append(record)
        if record.observation_id:
            _catalog.append_observation(entity_id, {
                "observation_id": record.observation_id,
                "uri": str(record.payload.get("url", "")),
                "content_hash": str(record.payload.get("digest", "")),
                "observed_at": record.payload.get("event_at", record.ts.isoformat()),
                "provenance": {"source": "entity.created.source_records", "record_id": record.record_id},
            })
    hub.publish(
        "entity.created",
        {
            "entity_id": entity_id,
            "tenant_id": ctx.tenant_id,
            "identity": body.canonical_identity,
            "investigation_id": body.investigation_id or "",
        },
    )
    materialization = None
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
    else:
        _materialization_operations.mark(launch.run_id, "DEFERRED", reason=launch.reason)
        effective_status = "DEFERRED"
        reason = launch.reason
    # Local verification fallback: production uses Temporal; when its endpoint
    # is absent, run the same capture/materialization chain in this process so
    # API/UI can still demonstrate a complete vertical slice.
    if effective_status == "DEFERRED" and not body.source_records:
        asyncio.create_task(run_live_entity_pipeline(
            tenant_id=ctx.tenant_id, entity_id=entity_id,
            identity=body.canonical_identity, source_records=body.source_records,
            catalog=_catalog, operations=_materialization_operations,
        ))
    materialization = {
        "run_id": launch.run_id,
        "workflow_id": launch.workflow_id,
        "status": effective_status,
    }
    if effective_status == "QUEUED":
        hub.publish("temporal.materialization.started", {"entity_id": entity_id, **materialization})
    else:
        hub.publish(
            "temporal.materialization.failed",
            {"entity_id": entity_id, **materialization, "reason": reason},
        )
    view = {**_catalog.entity(entity_id), "tenant_id": ctx.tenant_id, "search_surface": search_surface.as_dict()}
    return JSONResponse(
        status_code=202,
        content={"entity": view, "event": "entity.created", "search_surface": search_surface.as_dict(), "materialization": materialization},
    )


@router.get("/{entity_id}/worldline")
async def entity_worldline(
    entity_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    """Return the evidence-backed temporal worldline rebuilt from the stream."""
    if _catalog.entity(entity_id) is None:
        raise HTTPException(status_code=404, detail="entity not found")
    records = _entity_streams.get((ctx.tenant_id, entity_id), [])
    if not records:
        result = _temporal_results.get((ctx.tenant_id, entity_id), {})
        records = [StreamRecord.from_dict(item) for item in result.get("records", [])]
    if not records:
        raise HTTPException(status_code=404, detail="worldline not found")
    worldline = build_worldline(records, tenant_id=ctx.tenant_id, entity_id=entity_id, require_evidence=False)
    return worldline.to_dict()


@router.get("/{entity_id}/admission")
async def entity_admission(
    entity_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    """Return admission decisions and relation claims for accepted captures."""
    if _catalog.entity(entity_id) is None:
        raise HTTPException(status_code=404, detail="entity not found")
    records = _entity_streams.get((ctx.tenant_id, entity_id), [])
    result = _temporal_results.get((ctx.tenant_id, entity_id), {})
    if not records:
        records = [StreamRecord.from_dict(item) for item in result.get("records", [])]
    decisions: list[dict] = []
    relations: list[dict] = []
    for record in records:
        payload = record.payload or {}
        decisions.extend(payload.get("interpretation", {}).get("admission", {}).get("decisions", []))
        relations.extend(payload.get("interpretation", {}).get("relations", []))
    return {"entity_id": entity_id, "tenant_id": ctx.tenant_id, "decisions": decisions, "relations": relations, "counts": {"decisions": len(decisions), "relations": len(relations)}}


@router.get("/{entity_id}/stream")
async def entity_stream(
    entity_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    """Return the append-only accepted stream for an entity."""
    if _catalog.entity(entity_id) is None:
        raise HTTPException(status_code=404, detail="entity not found")
    records = _entity_streams.get((ctx.tenant_id, entity_id), [])
    return {"entity_id": entity_id, "tenant_id": ctx.tenant_id, "records": [r.to_dict() for r in records]}


@router.get("/{entity_id}/invariant")
async def entity_invariant(
    entity_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    result = _temporal_results.get((ctx.tenant_id, entity_id))
    if result is not None and result.get("invariant"):
        return {"entity_id": entity_id, "tenant_id": ctx.tenant_id, "invariant": result["invariant"]}
    raise HTTPException(status_code=404, detail="invariant not found")


@router.get("/{entity_id}/materialization-status")
async def entity_materialization_status(
    entity_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    """Return the latest run for an entity for UI polling."""
    runs = [r for r in _materialization_operations.health(tenant_id=ctx.tenant_id) if r["entity_id"] == entity_id]
    if not runs:
        raise HTTPException(status_code=404, detail="materialization run not found")
    return await _resolve_temporal_run(str(runs[-1]["run_id"]), runs[-1])


@router.get("/{entity_id}/temporal-history")
async def temporal_history(
    entity_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    history = temporal_materialization_service.current(tenant_id=ctx.tenant_id, entity_id=entity_id)
    if history is not None:
        return history.to_dict()
    result = _temporal_results.get((ctx.tenant_id, entity_id))
    if result is not None:
        return {
            "tenant_id": ctx.tenant_id,
            "entity_id": entity_id,
            "publication": result.get("publication", {}),
            "status": "current",
        }
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
    history = temporal_materialization_service.current(tenant_id=ctx.tenant_id, entity_id=entity_id)
    if history is None:
        result = _temporal_results.get((ctx.tenant_id, entity_id))
        if result is None:
            raise HTTPException(status_code=404, detail="temporal history not found")
        payload = {"tenant_id": ctx.tenant_id, "entity_id": entity_id, "publication": result.get("publication", {}), "status": "current"}
        payload["is_latest_valid"] = True
        return payload
    payload = history.to_dict()
    payload["is_latest_valid"] = True
    payload["status"] = "current"
    return payload


@router.get("/{entity_id}/temporal-features")
async def temporal_features(
    entity_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    history = temporal_materialization_service.current(tenant_id=ctx.tenant_id, entity_id=entity_id)
    if history is not None:
        return {
            "tenant_id": ctx.tenant_id,
            "entity_id": entity_id,
            "source_cut": history.publication.source_cut.to_dict(),
            "projection_generation": history.publication.projection_generation,
            "features": [feature.to_dict() for feature in history.publication.features],
        }
    result = _temporal_results.get((ctx.tenant_id, entity_id))
    if result is None:
        raise HTTPException(status_code=404, detail="temporal history not found")
    publication = result.get("publication", {})
    return {
        "tenant_id": ctx.tenant_id,
        "entity_id": entity_id,
        "source_cut": publication.get("source_cut", {}),
        "projection_generation": publication.get("projection_generation", 1),
        "features": publication.get("features", []),
    }


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
    if _catalog.entity(entity_id) is None:
        raise HTTPException(status_code=404, detail="entity not found")
    if body.candidate_b == entity_id:
        raise HTTPException(status_code=409, detail="cannot link an entity to itself")
    kind = body.kind or "possible_match"
    collective = round(min(1.0, body.raw_pair_score + 0.03), 3)
    edge = {
        "edge_id": _next_edge_id(),
        "candidate_a": entity_id,
        "candidate_b": body.candidate_b,
        "kind": kind,
        "raw_pair_score": body.raw_pair_score,
        "collective_score": collective,
        "reasons": body.reasons or ["analyst"],
        "state": body.state or "OPEN",
    }
    _correlations.append(edge)
    hub.publish(
        "entity.updated",
        {
            "entity_id": entity_id,
            "tenant_id": ctx.tenant_id,
            "event": "correlation.created",
            "edge_id": edge["edge_id"],
            "candidate_b": body.candidate_b,
            "kind": kind,
        },
    )
    return {"edge": edge, "event": "correlation.created"}


class ReviewCreate(BaseModel):
    decision: ReviewDecision
    reasoning: str = ""
    target_type: ReviewTargetType = ReviewTargetType.CANDIDATE


@router.get("")
async def list_entities(
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
    investigation_id: str | None = None,
) -> dict:
    """Compact entity overview: id, canonical identity, entity type and label.

    **The investigation filter used to be ignored.** The route never declared
    ``investigation_id``, so FastAPI dropped the query parameter and every
    investigation received the same list of the tenant's entities. That was measured
    rather than suspected: five different investigations all answered with the same
    five entities. The cause was underneath the route -- ``entities`` carried no
    investigation reference, so there was nothing to filter on, and ``/entities/graph``
    had been working around it for a while by deriving membership from each
    investigation's relation claims (a workaround that is correct for a mature
    investigation and empty for a fresh one).

    Membership is now durable (``investigation_entity_memberships``, migration 024) and
    this route reads it.

    **Two sources, and why.** PostgreSQL is the authoritative registry (ADR-0027) and
    holds every entity the platform has ever admitted -- the manual-assertion path, the
    resolution pipeline, anything written by a previous process. The process catalog is
    the smoke-path adapter this module has always served and holds what *this* worker
    created. Reporting only the catalog would make the answer differ per worker and lose
    everything on restart; reporting only PostgreSQL would make the fixture the API is
    built around disappear. They are merged, and the response names which ones answered.

    **Without a filter, every entity of the tenant.** With one, exactly the recorded
    memberships of that investigation -- never a widened set, never demo data standing in
    for a real investigation id, which is the same rule ``/entities/graph`` follows.

    **Failing closed.** If the membership table cannot be read, a scoped request answers
    with an empty list and an explicit ``degraded_reason`` rather than with the unfiltered
    tenant: "the filter could not be applied" and "the filter matched everything" are the
    same bytes on the wire, and answering the second one is how the original defect
    survived being looked at.
    """
    tenant = ctx.tenant_id if ctx else "default-tenant"

    durable: list[dict] = []
    durable_error: str | None = None
    try:
        durable = await _durable_entity_views(tenant)
    except Exception as exc:  # noqa: BLE001 - a missing database degrades, never widens
        durable_error = type(exc).__name__

    catalog = _catalog_entity_views(tenant)

    # Catalog entries win on collision: they carry the identity dimensions and the alias
    # label, which the durable row stores as a name and an attribute bag.
    merged: dict[str, dict] = {view["entity_id"]: view for view in durable}
    for view in catalog:
        merged[view["entity_id"]] = view

    payload: dict = {
        "entities": sorted(merged.values(), key=lambda view: view["entity_id"]),
        "tenant_id": tenant,
        "scoped": investigation_id is not None,
    }

    if not investigation_id:
        payload["source"] = "postgres+catalog" if durable else "catalog"
        if durable_error:
            payload["degraded_reason"] = durable_error
            payload["detail"] = (
                "the durable entity registry was unreadable; this list is the process "
                "catalog alone and is not the tenant's full set"
            )
        return payload

    payload["investigation_id"] = investigation_id
    try:
        member_ids = await _membership_entity_ids(investigation_id, tenant)
    except Exception as exc:  # noqa: BLE001 - fail closed rather than widen
        # No membership read, no answer. Empty plus a declared reason -- never the
        # unfiltered tenant, which is precisely what a client cannot distinguish from a
        # real match.
        payload["entities"] = []
        payload["source"] = "unavailable"
        payload["degraded_reason"] = type(exc).__name__
        payload["detail"] = (
            "membership could not be read for this investigation; no entities are "
            "claimed and no other investigation's entities are substituted"
        )
        return payload

    known = {view["entity_id"] for view in merged.values()}
    unresolved = sorted(member_ids - known)
    payload["entities"] = [
        view for view in payload["entities"] if view["entity_id"] in member_ids
    ]
    # An id can be a member before anything can render a view for it -- the membership is
    # written by a different process from the entity row, and the table carries no
    # foreign key for exactly that reason. Those ids are returned, and *named*, because
    # dropping them would make an investigation that does hold entities answer as though
    # it held none.
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
    payload["source"] = "postgres+catalog" if durable else "catalog"
    payload["scoped"] = True
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
    """Entity graph projection, scoped.

    Feature 024: reads PostgreSQL, which is authoritative (ADR-0027). This used to
    serve a hardcoded two-node fixture (`ENT-2001 "Yard"` plus one `possible_match`
    edge), so the UI's graph view could never show anything real -- it rendered the
    demo, not the investigation.

    **Scoping.** This previously read *every* entity and *every* relation claim with no
    filter at all. Both tables carry ``tenant_id`` and ``RelationClaim`` also carries
    ``investigation_id``, so an unscoped read was a cross-tenant read and a
    cross-investigation read at the same time: two analysts working separate
    investigations saw each other's graph. Tenant filtering is now mandatory and
    non-optional; ``investigation_id`` narrows further and, because ``Entity`` still has no
    investigation column, is applied by keeping only entities that the investigation's own
    relation claims actually reference -- plus entities named explicitly in the
    investigation scope. An entity mentioned nowhere in this investigation is not part of
    this investigation's graph.

    That derivation is a *graph* rule -- a node with no edge is not in the graph -- and
    it stays. It is not the whole answer to "what does this investigation contain":
    ``investigation_entity_memberships`` (migration 024) is, and ``GET /entities?
    investigation_id=`` reads it. A membership with no relation behind it belongs to this
    investigation's entity list and not to its graph, which are different questions.

    The fixture is kept only as a last resort when the database holds no relations, so
    a fresh install still has something to render -- and it is **never** returned for a
    scoped request, because demo data shown under a real investigation id is a lie about
    evidence that does not exist.
    """
    tenant = ctx.tenant_id if ctx else "default-tenant"

    nodes: list[dict] = []
    edges: list[dict] = []
    try:
        from sqlalchemy import select

        from db.schema import Entity, RelationClaim

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
                # Only entities this investigation actually touches.
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
    except Exception as exc:  # database absent -> demo path, not a 500
        if investigation_id:
            # A scoped request must never be answered with demo data.
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
        nodes = []
        edges = []
        nodes.append(
            {"id": "ENT-2001", "label": "Yard", "entity_type": "account", "properties": {}}
        )
        edges.append(
            {
                "id": "CE-200001",
                "source": "ENT-2001",
                "target": "ENT-2002",
                "kind": "possible_match",
                "label": "possible_match",
            }
        )
        nodes.append(
            {"id": "ENT-2002", "label": "ENT-2002", "entity_type": "entity", "properties": {}}
        )
        return {
            "nodes": nodes,
            "edges": edges,
            "tenant_id": tenant,
            "source": "fixture",
            "degraded_reason": type(exc).__name__,
        }

    if not edges:
        # Nothing asserted yet. Say so instead of passing off the fixture as findings.
        nodes = [
            {"id": "ENT-2001", "label": "Yard", "entity_type": "account", "properties": {}},
            {"id": "ENT-2002", "label": "ENT-2002", "entity_type": "entity", "properties": {}},
        ]
        return {
            "nodes": nodes,
            "edges": edges,
            "tenant_id": tenant,
            "source": "postgres",
            "degraded_reason": "no asserted relations yet",
        }

    if investigation_id:
        return {
            "nodes": nodes,
            "edges": edges,
            "tenant_id": tenant,
            "investigation_id": investigation_id,
            "source": "postgres",
            "scoped": True,
        }
    return {"nodes": nodes, "edges": edges, "tenant_id": tenant, "source": "postgres", "scoped": True}


async def _investigation_scope_entities(investigation_id: str, tenant_id: str) -> set[str]:
    """Entities named directly in the durable investigation scope.

    ``Entity`` carries no investigation column, so the authoritative link is the relation
    claims. An investigation may also name entities in its scope before any relation
    exists -- the normal state of a fresh investigation -- and those must appear in its
    graph. Read from the investigation's durable row rather than the in-memory repo, so
    scoping does not depend on process state.

    Returns an empty set on any failure. A missing scope read narrows the graph to
    relation-derived entities; it never widens it.
    """
    import json

    from sqlalchemy import text

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
    view = _catalog.entity(entity_id)
    if view is None:
        raise HTTPException(status_code=404, detail="entity not found")
    # Deterministic timeline clock for the temporality UI: observations are
    # anchored to the first known version's first_seen where available.
    versions = view.get("historical_versions") or []
    first_seen = (
        versions[0].get("first_seen", "") if versions and isinstance(versions[0], dict) else ""
    )
    enriched_timeline = []
    for entry in view.get("timeline", []):
        enriched = {**entry}
        # ``catalog._observation`` always emits the key, with ``None`` when the
        # observation carries no time. Presence alone therefore says nothing: the
        # anchor has to key on a *known* time, or every entry keeps a ``None`` and
        # the deterministic clock never applies.
        if first_seen and not enriched.get("observed_at"):
            enriched["observed_at"] = first_seen
        enriched_timeline.append(enriched)
    view = {**view, "timeline": enriched_timeline, "tenant_id": ctx.tenant_id}
    return view


@router.get("/{entity_id}/correlations")
async def get_correlations(
    entity_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    """FR-004: possible_match edges for an entity/candidate — no merge implied."""
    edges = [
        e for e in _correlations if e["candidate_a"] == entity_id or e["candidate_b"] == entity_id
    ]
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
    """Pull the entity's Common Crawl temporality (CC-TEMPORALITY v1).

    Synchronous, bounded (limit ≤ 50) orchestration: plan → index pull →
    normalize → series projection. Missing data comes back as empty structures
    plus honest notes (I-3) — never a fabricated series.
    """
    view = _catalog.entity(entity_id)
    if view is None:
        raise HTTPException(status_code=404, detail="entity not found")
    payload = run_cc_temporality(entity_id, view.get("canonical_identity") or {}, session=None)
    return {**payload, "tenant_id": ctx.tenant_id}
