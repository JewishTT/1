"""Zero-layer (Collection Fabric) control surface API.

Exposes the acquisition fabric capabilities the control plane coordinates:
badge/capability engine selection (T095), re-observation dedup (T101),
entity-link modification (T094), cross-semantic search (T109), the frontier
(T119), worker-pool isolation, region backpressure (T113) and bulk historical
backfill (T108/T121). Every cross-app dependency (interpretation ``search``,
``backfill``/``historical.replay``, acquisition ``dispatcher.regional``) is
imported lazily so the API stays bootable hermetic and answers 501 when the
extra subsystem wheels are absent; under ``uv sync`` the workspace wheels are
installed and the full surface is live.
"""

from __future__ import annotations

import importlib
import json
from typing import Annotated
from urllib.parse import parse_qsl, urlsplit

from fastapi import APIRouter, Depends, HTTPException
from ids import global_id, host_partition, partition_of
from pydantic import BaseModel, Field

from api.auth import TenantContext, resolve_tenant
from badges.facade import (
    BADGE_CATALOG,
    ENGINE_ALIASES,
    BadgeFacade,
    BadgeNotFoundError,
)
from modifier.mismatch import EntityLink, badge_match, dedupe_entity_links, modify_urgency
from services.frontier import Frontier, FrontierItem
from services.reobservation import classify_reobservation, etag_equal
from services.throttle import lag_scale, rate_limiter
from services.worker_pools import WorkerKind, WorkerPoolRegistry

router = APIRouter(prefix="/fabric", tags=["fabric"])


# ---------------------------------------------------------------------------
# Cross-app lazy imports; 501 when the subsystem wheel is absent.
# ---------------------------------------------------------------------------
def _lazy(name: str):
    try:
        return importlib.import_module(name), None
    except ImportError as exc:
        return None, f"subsystem not installed: {exc}"


def _missing(module) -> HTTPException:
    return HTTPException(
        status_code=501,
        detail=f"fabric endpoint requires '{module}'; install the workspace wheel",
    )


def _default_facade() -> BadgeFacade:
    """Canonical engine surface first; overlay live adapter registry if present."""
    facade = BadgeFacade().seed_defaults()
    known = {entry.engine for entry in facade}
    try:
        from adapters.registry import REGISTRY  # type: ignore[import-not-found]
    except ImportError:
        return facade
    for source in REGISTRY:
        engine = getattr(source, "execution_class", "")
        if not engine or engine in known:
            continue
        try:
            facade.register(
                engine,
                badges=set(getattr(source, "capabilities", set())),
                source_type=getattr(source, "source_type", None),
            )
        except ValueError:
            continue
        known.add(engine)
    return facade


# Process-wide hermetic state (mirrors the collection fabric in-memory singletons).
_frontier = Frontier()
_facade: BadgeFacade = _default_facade()
_pools = WorkerPoolRegistry()


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------
class TaskSelectIn(BaseModel):
    required_badges: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)


class BadgeMatchIn(BaseModel):
    badges: list[str]
    include_aliases: bool = True


class ToolBadgeIn(BaseModel):
    token: str


class ReobserveIn(BaseModel):
    previous: dict = Field(default_factory=dict)
    observed: dict = Field(default_factory=dict)


class EtagIn(BaseModel):
    left: str | None = None
    right: str | None = None


class BadgeCompareIn(BaseModel):
    observed: dict[str, str] = Field(default_factory=dict)
    known: dict[str, str] = Field(default_factory=dict)


class LinkIn(BaseModel):
    entity: str
    identifiers: dict[str, str] = Field(default_factory=dict)
    scores: dict[str, float] = Field(default_factory=dict)
    observed_at: str = ""


class DedupeLinksIn(BaseModel):
    links: list[LinkIn] = Field(default_factory=list)
    require: str = "any"


class UrgencyIn(BaseModel):
    entity: str
    links: list[LinkIn] = Field(default_factory=list)


class SearchIn(BaseModel):
    query: str
    top_k: int = 10
    merge: str = "rrf_any"
    docs: dict[str, str] = Field(default_factory=dict)


class EnqueueIn(BaseModel):
    uri: str
    tenant_id: str = "default-tenant"
    priority: float = 0.0
    investigation_id: str | None = None
    source_id: str | None = None
    host_key: str | None = None
    partition: str = "global"


class EnqueueManyIn(BaseModel):
    items: list[EnqueueIn] = Field(default_factory=list)


class CooldownIn(BaseModel):
    frontier_id: str
    until: float


class PartitionIn(BaseModel):
    uri: str
    region_map: dict[str, str] | None = None


class PressureIn(BaseModel):
    region: str
    ready_depth: int = 0
    in_flight: int = 0
    capacity: int = 0
    oldest_age_s: float = 0.0


class RateLimitIn(BaseModel):
    queue_depth: int = 0
    max_rate_per_s: float = 10.0
    downstream_lag_s: float = 0.0


class BackfillPlanIn(BaseModel):
    cc_prefixes: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    from_ts: str = "20230101"
    to_ts: str = "20231231"
    cc_crawl: str = "CC-MAIN-2023-40"


class BackfillReplayIn(BaseModel):
    plan: BackfillPlanIn = Field(default_factory=BackfillPlanIn)
    cc_hits: dict[str, list[dict]] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Badges / engines (T095)
# ---------------------------------------------------------------------------
def _engine_summary(entry) -> dict:
    return {
        "engine": entry.engine,
        "badges": entry.badge_tokens,
        "aliases": list(entry.aliases),
        "source_type": entry.source_type,
    }


@router.get("/badges")
async def catalog_badges(ctx: Annotated[TenantContext, Depends(resolve_tenant)]) -> dict:
    return {
        "catalog": sorted(BADGE_CATALOG),
        "engines": {e.engine: e.badge_tokens for e in _facade},
        "aliases": {eng: list(aliases) for eng, aliases in ENGINE_ALIASES.items()},
    }


@router.get("/engines")
async def list_engines(ctx: Annotated[TenantContext, Depends(resolve_tenant)]) -> dict:
    return {"engines": [_engine_summary(e) for e in _facade]}


@router.get("/engines/{engine}")
async def get_engine(
    engine: str, ctx: Annotated[TenantContext, Depends(resolve_tenant)]
) -> dict:
    for entry in _facade:
        if entry.engine == engine:
            return _engine_summary(entry)
    raise HTTPException(status_code=404, detail=f"no engine '{engine}' registered")


@router.post("/engines/select")
async def select_engine(
    body: TaskSelectIn, ctx: Annotated[TenantContext, Depends(resolve_tenant)]
) -> dict:
    task = {
        "required_badges": body.required_badges,
        "required_capabilities": body.required_capabilities,
    }
    try:
        resolved = _facade.resolve_task(task)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    surface = getattr(resolved, "engine", None)
    if surface is None:
        gap = resolved
        return {
            "matched": False,
            "gap": {"required": sorted(gap.required), "missing": sorted(gap.missing)},
        }
    return _engine_summary(resolved)


@router.post("/engines/match")
async def match_engines(
    body: BadgeMatchIn, ctx: Annotated[TenantContext, Depends(resolve_tenant)]
) -> dict:
    matches = _facade.match_by_badges(body.badges, include_aliases=body.include_aliases)
    return {"matches": [_engine_summary(m) for m in matches]}


@router.post("/tool/badge")
async def resolve_badge_token(
    body: ToolBadgeIn, ctx: Annotated[TenantContext, Depends(resolve_tenant)]
) -> dict:
    try:
        canonical = _facade.badge(body.token)
    except BadgeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"unknown badge token '{body.token}'") from exc
    return {"token": body.token, "badge": canonical}


# ---------------------------------------------------------------------------
# Re-observation + ETag (T101/R-08)
# ---------------------------------------------------------------------------
@router.post("/tool/reobserve")
async def reobserve_classify(
    body: ReobserveIn, ctx: Annotated[TenantContext, Depends(resolve_tenant)]
) -> dict:
    return classify_reobservation(body.previous, body.observed)


@router.post("/tool/etag")
async def etag_compare(
    body: EtagIn, ctx: Annotated[TenantContext, Depends(resolve_tenant)]
) -> dict:
    equal = etag_equal(body.left, body.right)
    return {"left": body.left, "right": body.right, "equal": equal}


# ---------------------------------------------------------------------------
# Modifier (T094)
# ---------------------------------------------------------------------------
@router.post("/modifier/match")
async def modifier_match(
    body: BadgeCompareIn, ctx: Annotated[TenantContext, Depends(resolve_tenant)]
) -> dict:
    return badge_match(body.observed, body.known)


@router.post("/modifier/dedupe-links")
async def modifier_dedupe(
    body: DedupeLinksIn, ctx: Annotated[TenantContext, Depends(resolve_tenant)]
) -> dict:
    links = [
        EntityLink(entity=link.entity, identifiers=link.identifiers, scores=link.scores, observed_at=link.observed_at)
        for link in body.links
    ]
    groups = dedupe_entity_links(links, require=body.require)
    return {
        "groups": [
            [{"entity": g.entity, "identifiers": g.identifiers} for g in group]
            for group in groups
        ]
    }


@router.post("/modifier/urgency")
async def modifier_urgency(
    body: UrgencyIn, ctx: Annotated[TenantContext, Depends(resolve_tenant)]
) -> dict:
    links = [
        EntityLink(entity=link.entity, identifiers=link.identifiers, scores=link.scores, observed_at=link.observed_at)
        for link in body.links
    ]
    return modify_urgency(body.entity, links)


# ---------------------------------------------------------------------------
# Cross-semantic search (T109)
# ---------------------------------------------------------------------------
@router.post("/search")
async def cross_semantic_search(
    body: SearchIn, ctx: Annotated[TenantContext, Depends(resolve_tenant)]
) -> dict:
    module = _lazy("search")[0]
    if module is None:
        raise _missing("cognitive-interpretation")
    docs = body.docs or {
        "http-flagship": "plain http static fetch with etag and last-modified headers",
        "bulk-flagship": "common crawl bulk backfill replay of historical archives",
        "archival-flagship": "wayback cdx replay with range reads from warc surfaces",
    }
    retriever = module.CrossSemanticRetriever(
        [
            module.MemoryRetriever(dict(docs), capabilities={"http", "content-addressed"}),
            module.MemoryRetriever(dict(docs), capabilities={"bulk", "content-addressed"}),
            module.MemoryRetriever(dict(docs), capabilities={"warc", "archive"}),
        ]
    )
    badge = retriever.badge_for(body.query)
    hits = retriever.search(body.query, top_k=body.top_k, merge=body.merge)
    return {
        "query": body.query,
        "badge": badge,
        "hits": [
            {"doc_id": h.doc_id, "text": h.text, "score": round(h.score, 4), "backend": h.backend}
            for h in hits
        ],
    }


@router.get("/search/badge")
async def search_badge(
    q: str, ctx: Annotated[TenantContext, Depends(resolve_tenant)]
) -> dict:
    module = _lazy("search")[0]
    if module is None:
        raise _missing("cognitive-interpretation")
    resolved = module.CrossSemanticRetriever([]).badge_for(q)
    return {"query": q, "badge": resolved}


# ---------------------------------------------------------------------------
# Frontier (T119 / R-03)
# ---------------------------------------------------------------------------
def _item_summary(item: FrontierItem, *, frontier_id: str) -> dict:
    return {
        "frontier_id": frontier_id,
        "uri": item.uri,
        "tenant_id": item.tenant_id,
        "partition": item.partition,
        "priority": item.priority,
        "state": item.state,
        "retries": item.retries,
    }


@router.get("/frontier/status")
async def frontier_status(ctx: Annotated[TenantContext, Depends(resolve_tenant)]) -> dict:
    by_state: dict[str, int] = {}
    for item in _frontier._items.values():
        by_state[item.state] = by_state.get(item.state, 0) + 1
    return {
        "total": len(_frontier._items),
        "by_state": by_state,
        "leased": sum(1 for i in _frontier._items.values() if i.state == "LEASED"),
        "ready": sum(1 for i in _frontier._items.values() if i.state == "READY"),
    }


@router.post("/frontier/enqueue")
async def frontier_enqueue(
    body: EnqueueManyIn, ctx: Annotated[TenantContext, Depends(resolve_tenant)]
) -> dict:
    enqueued: list[str] = []
    duplicates: list[str] = []
    for item in body.items:
        partition = item.partition or partition_of(item.uri)
        frontier_id = global_id("frontier", partition)
        entry = FrontierItem(
            frontier_id=frontier_id,
            uri=item.uri,
            tenant_id=item.tenant_id,
            investigation_id=item.investigation_id,
            source_id=item.source_id,
            host_key=item.host_key or host_partition(item.uri)["host"],
            partition=partition,
            priority=item.priority,
        )
        (enqueued if _frontier.enqueue(entry) else duplicates).append(item.uri)
    return {
        "enqueued": enqueued,
        "duplicates": duplicates,
        "event": "frontier.enqueued",
    }


@router.post("/frontier/pop")
async def frontier_pop(
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
    tenant_id: str | None = None,
) -> dict:
    item = _frontier.pop_next(tenant_id=tenant_id)
    if item is None:
        raise HTTPException(status_code=404, detail="no ready frontier items")
    return _item_summary(item, frontier_id=item.frontier_id)


@router.post("/frontier/{frontier_id}/complete")
async def frontier_complete(
    frontier_id: str, ctx: Annotated[TenantContext, Depends(resolve_tenant)]
) -> dict:
    _frontier.complete(frontier_id)
    return {"frontier_id": frontier_id, "state": "DONE", "event": "frontier.completed"}


@router.post("/frontier/{frontier_id}/retry")
async def frontier_retry(
    frontier_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
    cooldown_s: float = 60.0,
) -> dict:
    _frontier.fail_retry(frontier_id, cooldown_s=cooldown_s)
    return {"frontier_id": frontier_id, "state": "RETRY", "event": "frontier.retried"}


@router.post("/frontier/{frontier_id}/cancel")
async def frontier_cancel(
    frontier_id: str, ctx: Annotated[TenantContext, Depends(resolve_tenant)]
) -> dict:
    _frontier.cancel(frontier_id)
    return {"frontier_id": frontier_id, "state": "CANCELLED", "event": "frontier.cancelled"}


@router.post("/frontier/cooldown")
async def frontier_cooldown(
    body: CooldownIn, ctx: Annotated[TenantContext, Depends(resolve_tenant)]
) -> dict:
    _frontier.cooldown(body.frontier_id, body.until)
    return {"frontier_id": body.frontier_id, "state": "COOLDOWN", "until": body.until}


# ---------------------------------------------------------------------------
# Worker pools (T066)
# ---------------------------------------------------------------------------
@router.get("/pools")
async def worker_pools(ctx: Annotated[TenantContext, Depends(resolve_tenant)]) -> dict:
    return {
        "pools": [
            {
                "kind": kind.value,
                "healthy": pool.healthy,
                "active": pool.active,
                "capacity": pool.capacity,
                "failures": pool.failures,
                "last_error": pool.last_error,
            }
            for kind, pool in sorted(_pools._pools.items(), key=lambda kv: kv[0].value)
        ]
    }


@router.post("/pools/{kind}/fail")
async def pool_mark_failure(
    kind: WorkerKind, ctx: Annotated[TenantContext, Depends(resolve_tenant)]
) -> dict:
    _pools.fail(kind, "manual failure injection")
    return {"kind": kind.value, "healthy": _pools.status(kind).healthy, "event": "pool.failure"}


# ---------------------------------------------------------------------------
# Partition / identifiers (T119)
# ---------------------------------------------------------------------------
@router.post("/partitions/resolve")
async def resolve_partition(
    body: PartitionIn, ctx: Annotated[TenantContext, Depends(resolve_tenant)]
) -> dict:
    host = host_partition(body.uri, region_map=body.region_map)
    return {
        "uri": body.uri,
        "host": host["host"],
        "partition": partition_of(body.uri, region_map=body.region_map),
        "sample_id": global_id("obs", host["region"]),
    }


# ---------------------------------------------------------------------------
# Region backpressure (T113)
# ---------------------------------------------------------------------------
_region_gate = None


@router.post("/backpressure/verdict")
async def backpressure_verdict(
    body: PressureIn, ctx: Annotated[TenantContext, Depends(resolve_tenant)]
) -> dict:
    global _region_gate
    module = _lazy("dispatcher.regional")[0]
    if module is None:
        raise _missing("cognitive-acquisition")
    if _region_gate is None:
        _region_gate = module.RegionBackpressure()
    pressure = module.RegionPressure(
        region=body.region,
        ready_depth=body.ready_depth,
        in_flight=body.in_flight,
        capacity=body.capacity,
        oldest_age_s=body.oldest_age_s,
    )
    _region_gate.observe(pressure)
    verdict = _region_gate.verdict(body.region)
    return {
        "region": body.region,
        "verdict": verdict.value,
        "report": _region_gate.report().get(body.region),
    }


@router.post("/throttle/rate")
async def throttle_rate(
    body: RateLimitIn, ctx: Annotated[TenantContext, Depends(resolve_tenant)]
) -> dict:
    return {
        "queue_depth": body.queue_depth,
        "downstream_lag_s": body.downstream_lag_s,
        "lag_scale": round(lag_scale(body.downstream_lag_s), 4),
        "effective_rate_per_s": round(
            rate_limiter(body.queue_depth, body.max_rate_per_s, body.downstream_lag_s), 4
        ),
    }


# ---------------------------------------------------------------------------
# Bulk historical backfill (T108/T121)
# ---------------------------------------------------------------------------
@router.post("/bulk/plan")
async def bulk_plan(body: BackfillPlanIn, ctx: Annotated[TenantContext, Depends(resolve_tenant)]) -> dict:
    module = _lazy("backfill")[0]
    if module is None:
        raise _missing("cognitive-bulk-ingestion")
    cdx_urls = [
        module.build_cdx_url(
            d, from_ts=body.from_ts, to_ts=body.to_ts, base=module.CDX_BASE
        )
        for d in body.domains
    ]
    return {
        "sources": len(body.cc_prefixes) + len(body.domains),
        "cc_prefixes": body.cc_prefixes,
        "domains": body.domains,
        "cc_crawl": body.cc_crawl,
        "cdx_urls": cdx_urls,
    }


@router.get("/bulk/cdx")
async def bulk_cdx_url(
    domain: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
    from_ts: str = "20230101",
    to_ts: str = "20231231",
) -> dict:
    module = _lazy("backfill")[0]
    if module is None:
        raise _missing("cognitive-bulk-ingestion")
    return {
        "url": module.build_cdx_url(domain, from_ts=from_ts, to_ts=to_ts, base=module.CDX_BASE),
        "surface": "wayback",
    }


class _QueueTransport:
    """Serves canned CC index NDJSON per discover call (hermetic replay)."""

    def __init__(self, hits_by_prefix: dict[str, list[dict]]) -> None:
        self._queue: list[str] = []
        for prefix, rows in hits_by_prefix.items():
            lines = "\n".join(
                json.dumps(
                    {
                        "url": row.get("url", prefix),
                        "timestamp": row.get("timestamp", "20230101000000"),
                        "status": str(row.get("status", "200")),
                        "mime": row.get("mime", "text/html"),
                        "digest": row.get("digest", "DIGEST"),
                        "filename": row.get("filename", "crawl-data/CC/sample.warc.gz"),
                        "offset": str(row.get("offset", "0")),
                        "length": str(row.get("length", "1024")),
                    }
                )
                for row in rows
            )
            self._queue.append(lines)

    async def __call__(self, index_url: str) -> str:
        page = dict(parse_qsl(urlsplit(index_url).query)).get("page")
        if page not in (None, "0") or not self._queue:
            return ""
        # Deterministic: each page-0 fetch consumes one canned prefix surface.
        if self._queue:
            return self._queue.pop(0)
        return ""


@router.post("/bulk/replay")
async def bulk_replay(
    body: BackfillReplayIn, ctx: Annotated[TenantContext, Depends(resolve_tenant)]
) -> dict:
    module = _lazy("backfill")[0]
    if module is None:
        raise _missing("cognitive-bulk-ingestion")
    replay = _lazy("historical.replay")[0]
    if replay is None:
        raise _missing("cognitive-bulk-ingestion")
    plan = module.BackfillPlan(
        cc_prefixes=body.plan.cc_prefixes,
        domains=body.plan.domains,
        from_ts=body.plan.from_ts,
        to_ts=body.plan.to_ts,
        cc_crawl=body.plan.cc_crawl,
    )
    cc = _lazy("network.commoncrawl")[0]
    sink = replay.MemoryFrontierSink()
    transport = _QueueTransport(body.cc_hits)
    client = cc.CommonCrawlClient(transport=transport)
    runner = replay.HistoricalReplay(sink, client=client)
    stats = await runner.run(plan.cc_prefixes, crawl=plan.cc_crawl)
    return {
        "plan": {
            "cc_prefixes": plan.cc_prefixes,
            "domains": plan.domains,
            "cc_crawl": plan.cc_crawl,
        },
        "stats": {
            "discovered": stats.discovered,
            "enqueued": stats.enqueued,
            "deduped": stats.deduped,
            "batches": stats.batches,
        },
        "enqueued_uris": [c.get("uri") for c in sink.enqueued],
    }