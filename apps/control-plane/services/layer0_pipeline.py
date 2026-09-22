"""Layer 0 direct pipeline — the altitude-0 "nervous system" (feature 010).

The audit finding for Layer 0 was structural: *every acquisition-stage organ
exists* (discovery sources, frontier, content router, observation gate,
interpretation extractors, entity fabric, search projector) but **nothing
assembles them**. The dispatcher's ``emit_request`` built an envelope and
discarded it; no consumer daemon ran; the "pipeline" was a set of isolated
contract tests.

This module is the missing composition root. It runs the whole altitude-0
circle for one frontier item, synchronously and auditable:

    discovery seed → frontier enqueue →
    dispatch (emit `acquisition.request`) →
    fetch (worker-http) → gate.ingest (content-addressed store + lifecycle) →
    route (content router) → interpretation (parse→extract→normalize→aggregate) →
    fabric append (CRM/stream records) → search projection

Constraints honored:
- **Kafka is never the frontier queue** (I-5/R-4): items come from the
  frontier; the broker carries lifecycle/request events only.
- **Blobs stay in object storage** (I-5): payloads carry raw_refs, never bytes.
- **Idempotent by digest** (FR-007/R-8): a re-observed unchanged item is a
  no-op for every downstream stage (three-way split).
- **Nothing owns memory the gate/frontier own** (separation of concerns):
  this orchestrator composes; it does not duplicate storage semantics.

The orchestrator is intentionally protocol-based so the exact same code runs
hermetically (memory frontier + memory store + fake producer) and against the
live stack (Postgres frontier + MinIO + Redpanda/Kafka) — this is the wiring
that was missing.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4

from events.content_router import ContentRouter
from events.observation_gate import ObservationGate

from services.acquisition_loop import AcquisitionLoop
from services.frontier import FrontierItem

# Synchronous in-memory frontier + async Pg frontier share this surface.


class FrontierOps(Protocol):
    async def enqueue(self, item: FrontierItem) -> bool: ...
    async def pop_next(
        self,
        *,
        tenant_id: str | None = None,
        partition: str | None = None,
        now: float | None = None,
    ) -> FrontierItem | None: ...
    async def complete(
        self,
        frontier_id: str,
        *,
        digest: str | None = None,
        etag: str | None = None,
        status: str = "completed",
    ) -> None: ...
    async def fail_retry(
        self, frontier_id: str, *, max_retries: int | None = None, cooldown_s: float | None = None
    ) -> None: ...
    async def last_digest(self, frontier_id: str, uri: str | None = None) -> str | None: ...


class EnvelopeProducer(Protocol):
    def produce(self, topic: str, envelope, *, key: str | None = None) -> None: ...


@dataclass
class StageOutcome:
    """Per-stage result of one pipeline tick (full audit trail, I-3 honesty)."""

    stage: str
    ok: bool
    detail: str = ""
    items: list[str] = field(default_factory=list)


@dataclass
class PipelineTick:
    """One frontier item through the whole circle."""

    frontier_id: str
    uri: str
    tenant_id: str
    observation_id: str = ""
    lifecycle: str = ""
    stages: list[StageOutcome] = field(default_factory=list)
    ok: bool = False

    def stage_result(self, stage: str) -> StageOutcome | None:
        for s in self.stages:
            if s.stage == stage:
                return s
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "frontier_id": self.frontier_id,
            "uri": self.uri,
            "tenant_id": self.tenant_id,
            "observation_id": self.observation_id,
            "lifecycle": self.lifecycle,
            "ok": self.ok,
            "stages": [s.__dict__ for s in self.stages],
        }


# Downstream hooks wired to the fabric + search (interpretation results drive
# both). These are the *only* places the pipeline reaches into the entity plane.


class InterpretHook(Protocol):
    """Consume observation bytes → interpretation segments (parse→extract).

    Exposed as a plain callable so production can bind the real
    ``interpretation.pipeline.InterpretationPipeline`` wrapper and tests a
    lightweight stub. Returns interpretation candidate dicts (entity_id,
    kind, payload) — the only shape the fabric hook understands.
    """

    def __call__(
        self, *, observation_id: str, body: bytes, content_type: str | None, tenant_id: str
    ) -> list[dict]: ...


class FabricHook(Protocol):
    """Append interpretation candidates into a tenant's entity stream."""

    def ingest(
        self, *, entity_id: str, kind: str, payload: dict, observation_id: str, tenant_id: str
    ) -> bool: ...


class SearchHook(Protocol):
    """Project a searchable document from a fresh observation."""

    def index(self, *, observation_id: str, doc_id: str, body: dict, tenant_id: str) -> None: ...


class LakeHook(Protocol):
    """Persist a fresh observation row into the data-lake (slice 3)."""

    def append(self, **row: Any) -> Awaitable[bool]: ...


class Layer0Pipeline:
    """Direct pipeline: front-tier acquisition to entity-plane ingestion.

    ``pump_one`` pops one frontier item and drives it through fetch → gate →
    route → interpretation → fabric → search. ``seed`` enqueues discovery
    candidates (web-search the entity → frontier). Workers in the live stack run
    ``pump_loop``; hermetic tests drive ``pump_one`` with memory substitutes.
    """

    def __init__(
        self,
        loop: AcquisitionLoop,
        gate: ObservationGate,
        *,
        router: ContentRouter | None = None,
        interpret: InterpretHook | None = None,
        fabric: FabricHook | None = None,
        search: SearchHook | None = None,
        lake: LakeHook | None = None,
        dispatch: Callable[[FrontierItem], Awaitable[None]] | None = None,
        frontier: FrontierOps | None = None,
    ) -> None:
        self._loop = loop
        self._gate = gate
        self._router = router or ContentRouter()
        self._interpret = interpret
        self._fabric = fabric
        self._search = search
        self._lake = lake
        self._dispatch = dispatch
        self._frontier = frontier

    async def pump_one(
        self, *, tenant_id: str | None = None, injected: FrontierItem | None = None
    ) -> PipelineTick | None:
        """Run one frontier item end-to-end. Returns None when the frontier is empty."""
        origin = self._frontier or getattr(self._loop, "frontier", None)
        item = injected or await origin.pop_next(tenant_id=tenant_id)
        if item is None:
            return None
        tick = PipelineTick(frontier_id=item.frontier_id, uri=item.uri, tenant_id=item.tenant_id)

        if self._dispatch is not None:
            await self._dispatch(item)
            tick.stages.append(
                StageOutcome(stage="dispatch", ok=True, detail="acquisition.request emitted")
            )

        res = await self._loop.run_item(item)
        tick.observation_id = res.observation_id
        tick.lifecycle = res.lifecycle
        if not res.ok:
            tick.stages.append(StageOutcome(stage="fetch", ok=False, detail=res.reason))
            return tick

        tick.stages.append(
            StageOutcome(
                stage="gate",
                ok=True,
                detail=f"lifecycle={res.lifecycle} raw_ref={res.raw_ref}",
                items=[res.raw_ref],
            )
        )

        if res.lifecycle in ("duplicate", "unchanged"):
            # Three-way split (R-08): fresh bytes only get interpreted/indexed.
            tick.ok = True
            return tick

        classified = self._router.classify(res.body, url=res.uri, headers={})
        tick.stages.append(
            StageOutcome(
                stage="route",
                ok=True,
                detail=f"content_type={classified['content_type']} size={classified['size']}",
            )
        )

        if self._interpret is not None:
            mentions = self._interpret(
                observation_id=res.observation_id,
                body=res.body,
                content_type=res.content_type,
                tenant_id=res.tenant_id,
            )
            tick.stages.append(
                StageOutcome(
                    stage="interpret",
                    ok=True,
                    items=[m.get("entity_id", m.get("kind", "")) for m in mentions],
                )
            )
            if self._fabric is not None:
                for m in mentions:
                    self._fabric.ingest(
                        entity_id=m["entity_id"],
                        kind=m["kind"],
                        payload=m.get("payload", {}),
                        observation_id=res.observation_id,
                        tenant_id=res.tenant_id,
                    )
                tick.stages.append(
                    StageOutcome(
                        stage="fabric", ok=True, detail=f"{len(mentions)} records appended"
                    )
                )

        if self._search is not None:
            self._search.index(
                observation_id=res.observation_id,
                doc_id=f"obs-{res.observation_id}",
                body={
                    "uri": res.uri,
                    "raw_ref": res.raw_ref,
                    "content_type": res.content_type,
                    "fields": [],
                },
                tenant_id=res.tenant_id,
            )
            tick.stages.append(StageOutcome(stage="search", ok=True, detail="document indexed"))

        if self._lake is not None:
            ok_lake = await self._lake.append(
                observation_id=res.observation_id,
                tenant_id=res.tenant_id,
                event_id=res.observation_id,
                uri=res.uri,
                content_type=res.content_type,
                sha256=classified.get("sha256", ""),
                size_bytes=classified.get("size", 0),
                source_id=item.source_id or "",
                work_id="",
                collected_at="",
            )
            tick.stages.append(
                StageOutcome(stage="lake", ok=ok_lake, detail="observation row persisted")
            )

        tick.ok = True
        return tick

    async def seed(
        self,
        *,
        identifiers: dict[str, str],
        tenant_id: str,
        investigation_id: str = "",
        top_k: int | None = None,
        providers=None,
    ) -> list[str]:
        """Search the web for an entity and enqueue candidate URLs into the frontier.

        The missing outbound half of the nervous system: an entity created in the
        UI (FIO/phone/email/domain…) triggers web search; the ranked hits become
        Frontier items; the normal ``pump_loop`` circle then fetches/interprets/
        indexes them. Returns the enqueued URIs.

        Stream-first (feature 009): ``discovery.stream`` yields each candidate the
        moment its query returns, and we enqueue it into the frontier immediately —
        nothing is buffered until the search completes. The frontier stays the
        queue of truth (R-4): discovery only feeds it, never bypasses it. Providers
        are injectable so this runs hermetically in tests
        (``memory_providers(corpus)``) and against real search engines in
        production (Brave + Tavily by default).
        """
        origin = self._frontier or getattr(self._loop, "frontier", None)
        if origin is None:
            raise RuntimeError("seed requires a frontier (pipeline._frontier or loop.frontier)")

        from websearch.discovery import EntityWebDiscovery, default_providers

        discovery = EntityWebDiscovery(providers=providers or default_providers())
        enqueued: list[str] = []
        async for cand in discovery.stream(identifiers, tenant_id=tenant_id, top_k=top_k):
            host = cand.uri.split("://", 1)[1].split("/", 1)[0] if "://" in cand.uri else ""
            item = FrontierItem(
                frontier_id=f"W-{uuid4().hex[:8]}",
                uri=cand.uri,
                tenant_id=tenant_id,
                investigation_id=investigation_id,
                source_id="web-search",
                host_key=host,
                partition="entity",
                priority=cand.relevance,
            )
            if not await origin.enqueue(item):
                continue
            enqueued.append(cand.uri)
        return enqueued

    async def pump_loop(
        self, *, tenant_id: str | None = None, iterations: int = 10
    ) -> list[PipelineTick]:
        """Drain the frontier up to ``iterations`` ticks (worker loop body)."""
        ticks: list[PipelineTick] = []
        for _ in range(iterations):
            tick = await self.pump_one(tenant_id=tenant_id)
            if tick is None:
                break
            ticks.append(tick)
        return ticks
