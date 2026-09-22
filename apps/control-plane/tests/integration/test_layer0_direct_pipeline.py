"""Hermetic Layer-0 nervous system test (feature 010, slice 1).

Proves the full altitude-0 circle **without any live stack** (no Postgres /
MinIO / Kafka): enqueue → dispatch (acquisition.request emitted) → fetch
(local HTTP server) → gate (content-addressed memory store + lifecycle) →
route (content router) → interpretation → fabric append → search projection.

This is the direct pipeline that feature 010 is about: every organ existed as
isolated contracts, but nothing assembled them into a machine. Same code runs
against the live stack (PgPostgres frontier, MinIO, Redpanda) — see
``test_end_to_end_pipeline`` for that variant.
"""

from __future__ import annotations

import http.server
import sys
import threading
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apps" / "config"))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apps" / "shared"))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apps" / "control-plane"))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apps" / "interpretation"))

import pytest
from events.content_router import ContentRouter
from events.observation_gate import ObservationGate
from storage.memory import MemoryObjectStore

from services.acquisition_loop import AcquisitionLoop
from services.frontier import Frontier, FrontierItem
from services.layer0_pipeline import Layer0Pipeline

pytestmark = pytest.mark.integration


class AsyncMemoryFrontier:
    """Async adapter over the synchronous in-memory ``Frontier``."""

    def __init__(self) -> None:
        self._sync = Frontier()

    async def enqueue(self, item: FrontierItem) -> bool:
        return self._sync.enqueue(item)

    async def pop_next(
        self,
        *,
        tenant_id: str | None = None,
        partition: str | None = None,
        now: float | None = None,
    ) -> FrontierItem | None:
        return self._sync.pop_next(tenant_id=tenant_id, now=now)

    async def complete(
        self,
        frontier_id: str,
        *,
        digest: str | None = None,
        etag: str | None = None,
        status: str = "completed",
    ) -> None:
        self._sync.complete(frontier_id)

    async def fail_retry(
        self, frontier_id: str, *, max_retries: int | None = None, cooldown_s: float | None = None
    ) -> None:
        self._sync.fail_retry(frontier_id)

    async def last_digest(self, frontier_id: str, uri: str | None = None) -> str | None:
        return None


class FakeProducer:
    """Captures produced envelopes for assertion (hermetic transport)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []  # (topic, key)

    def produce(self, topic: str, envelope, *, key: str | None = None) -> None:
        self.calls.append((topic, key or ""))


class _Handler(http.server.BaseHTTPRequestHandler):
    BODY = b"<html><head><title>acme corp</title></head><body>John Smith j.smith@acme.test +1 555 000 1111</body></html>"

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(self.BODY)))
        self.end_headers()
        self.wfile.write(self.BODY)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def local_server() -> str:
    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/page"
    finally:
        server.shutdown()


class RecorderFabric:
    """FabricHook recorder: asserts append discipline without a real store."""

    def __init__(self) -> None:
        self.appended: list[dict] = []

    def ingest(
        self, *, entity_id: str, kind: str, payload: dict, observation_id: str, tenant_id: str
    ) -> bool:
        self.appended.append(
            {
                "entity_id": entity_id,
                "kind": kind,
                "payload": payload,
                "observation_id": observation_id,
                "tenant_id": tenant_id,
            }
        )
        return True


class RecorderSearch:
    def __init__(self) -> None:
        self.indexed: list[dict] = []

    def index(self, *, observation_id: str, doc_id: str, body: dict, tenant_id: str) -> None:
        self.indexed.append(
            {
                "observation_id": observation_id,
                "doc_id": doc_id,
                "body": dict(body),
                "tenant_id": tenant_id,
            }
        )


class RecorderLake:
    """LakeHook recorder (slice 3) — proves observation rows reach the lake."""

    def __init__(self) -> None:
        self.appended: list[dict] = []

    async def append(self, **row) -> bool:
        self.appended.append(dict(row))
        return bool(row.get("sha256"))


async def test_direct_pipeline_end_to_end(local_server: str) -> None:
    tenant = f"t-{uuid.uuid4().hex[:8]}"
    producer = FakeProducer()
    frontier = AsyncMemoryFrontier()
    store = MemoryObjectStore()
    gate = ObservationGate(store, ContentRouter(), producer)
    loop = AcquisitionLoop(frontier, gate)  # type: ignore[arg-type]
    fabric = RecorderFabric()
    search = RecorderSearch()
    lake = RecorderLake()

    pipeline = Layer0Pipeline(
        loop,
        gate,
        interpret=None,  # hermetic: interpretation wired in the second test
        fabric=fabric,
        search=search,
        lake=lake,
        frontier=frontier,  # type: ignore[arg-type]
    )

    await frontier.enqueue(
        FrontierItem(
            frontier_id="F-1",
            uri=local_server,
            tenant_id=tenant,
            host_key="127.0.0.1",
            priority=1.0,
        )
    )

    tick = await pipeline.pump_one(tenant_id=tenant)
    assert tick is not None
    assert tick.ok, [s.__dict__ for s in tick.stages]
    assert tick.lifecycle == "created"
    assert tick.observation_id.startswith("OBS-")

    # The whole circle: gate stored wire, lifecycle emitted
    assert store.count() == 1
    produced_topics = {t for t, _ in producer.calls}
    assert "observation" in produced_topics  # gate emits observation.created

    # Lake persisted a row for the fresh observation (slice 3)
    assert lake.appended and lake.appended[0]["tenant_id"] == tenant
    assert lake.appended[0]["observation_id"] == tick.observation_id
    assert tick.stage_result("lake") is not None and tick.stage_result("lake").ok

    # Frontier consumed exactly one item, now done
    assert frontier._sync.ready_count(tenant_id=tenant) == 0

    await loop.aclose()


async def test_direct_pipeline_with_interpretation_and_index(local_server: str) -> None:
    """Full nerve system: fetch → gate → interpret → fabric → search index."""
    tenant = f"t-{uuid.uuid4().hex[:8]}"
    producer = FakeProducer()
    frontier = AsyncMemoryFrontier()
    store = MemoryObjectStore()
    gate = ObservationGate(store, ContentRouter(), producer)
    loop = AcquisitionLoop(frontier, gate)  # type: ignore[arg-type]
    fabric = RecorderFabric()
    search = RecorderSearch()

    from pipeline import InterpretationPipeline  # interpretation app (shared-importable)

    interpret = InterpretationPipeline()

    def _hook(
        *, observation_id: str, body: bytes, content_type: str | None, tenant_id: str
    ) -> list[dict]:
        result = interpret.run(observation_id, body, content_type, tenant_id=tenant_id)
        # Without a dataset boundary (FR-001) interpretation yields *candidates*,
        # not durable statements — the fabric consumes those candidates directly.
        seen: dict[str, dict] = {}
        for cand in result.candidates:
            if cand.kind in seen:
                continue
            seen[cand.kind] = {
                "entity_id": cand.key,
                "kind": cand.kind,
                "payload": {"value": cand.value, "observed": True},
            }
        return list(seen.values())

    pipeline = Layer0Pipeline(
        loop,
        gate,
        interpret=_hook,
        fabric=fabric,
        search=search,
        frontier=frontier,  # type: ignore[arg-type]
    )

    await frontier.enqueue(
        FrontierItem(
            frontier_id="F-2",
            uri=local_server,
            tenant_id=tenant,
            host_key="127.0.0.1",
            priority=1.0,
        )
    )

    tick = await pipeline.pump_one(tenant_id=tenant)
    assert tick is not None and tick.ok
    assert tick.stage_result("gate") is not None and tick.stage_result("gate").ok
    route_stage = tick.stage_result("route")
    assert route_stage is not None and "text/html" in route_stage.detail

    # Interpretation ran → entity candidates appended to the fabric
    assert fabric.appended, "interpretation must surface candidates into the fabric"
    assert fabric.appended[0]["tenant_id"] == tenant
    assert fabric.appended[0]["observation_id"] == tick.observation_id

    # Search document projected
    assert search.indexed and search.indexed[0]["doc_id"] == f"obs-{tick.observation_id}"
    assert search.indexed[0]["body"]["uri"] == local_server

    await loop.aclose()


async def test_seed_web_discovery_enqueues_frontier() -> None:
    """Entity → web-search → frontier: the outbound half of the nervous system.

    An atomic entity (FIO + phone + email in the UI) fans out to search queries,
    providers return hits, entity-relevance ranks them, and the pipeline enqueues
    the winner into the frontier — ready for ``pump_one`` to fetch/interpret.
    """
    from websearch.providers import MemorySearchProvider

    tenant = f"t-{uuid.uuid4().hex[:8]}"
    frontier = AsyncMemoryFrontier()

    corpus = {
        "http://acme.test/jane": {
            "title": "Jane Doe — index",
            "snippet": "contact via jane@acme.test",
            "terms": "jane doe",
        },
        "http://acme.test/official": {
            "title": "ACME — officers",
            "snippet": "Jane Doe, phone 5550001122",
            "terms": "jane doe acme",
        },
        "http://spam.test/other": {"title": "unrelated", "snippet": "shoes", "terms": "shoes"},
    }
    # pipeline needs a loop/gate; seed only reads the frontier, so a stub loop is fine.
    gate = ObservationGate(MemoryObjectStore(), ContentRouter(), FakeProducer())
    loop = AcquisitionLoop(frontier, gate)  # type: ignore[arg-type]
    pipeline = Layer0Pipeline(loop, gate, frontier=frontier)  # type: ignore[arg-type]

    enqueued = await pipeline.seed(
        identifiers={
            "full_name": "Jane Doe",
            "phone": "+1 555 000 1122",
            "email": "jane@acme.test",
        },
        tenant_id=tenant,
        investigation_id="inv-web-1",
        providers=[MemorySearchProvider(corpus)],
        top_k=5,
    )

    assert enqueued, "web search must surface entity-relevant URLs"
    assert "http://acme.test/official" in enqueued  # exact phone+email evidence ranks top
    assert all("acme.test" in u or "spam.test" in u for u in enqueued)
    # frontier now holds the candidates for the fetch/gate/interpret circle
    assert frontier._sync.ready_count(tenant_id=tenant) == len(enqueued)

    await loop.aclose()


async def test_direct_pipeline_reobservation_is_noop(local_server: str) -> None:
    """Three-way split (R-08): unchanged re-observation must NOT re-interpret."""
    tenant = f"t-{uuid.uuid4().hex[:8]}"
    frontier = AsyncMemoryFrontier()
    store = MemoryObjectStore()
    gate = ObservationGate(store, ContentRouter(), FakeProducer())
    loop = AcquisitionLoop(frontier, gate)  # type: ignore[arg-type]
    fabric = RecorderFabric()
    search = RecorderSearch()

    from pipeline import InterpretationPipeline

    interpret = InterpretationPipeline()

    def _hook(
        *, observation_id: str, body: bytes, content_type: str | None, tenant_id: str
    ) -> list[dict]:
        result = interpret.run(observation_id, body, content_type, tenant_id=tenant_id)
        seen: dict[str, dict] = {}
        for cand in result.candidates:
            if cand.kind in seen:
                continue
            seen[cand.kind] = {
                "entity_id": cand.key,
                "kind": cand.kind,
                "payload": {"value": cand.value, "observed": True},
            }
        return list(seen.values())

    pipeline = Layer0Pipeline(
        loop, gate, interpret=_hook, fabric=fabric, search=search, frontier=frontier
    )  # type: ignore[arg-type]

    await frontier.enqueue(
        FrontierItem(
            frontier_id="F-3",
            uri=local_server,
            tenant_id=tenant,
            host_key="127.0.0.1",
            priority=1.0,
        )
    )
    first = await pipeline.pump_one(tenant_id=tenant)
    assert first is not None and first.lifecycle == "created"
    written = store.count()

    # Re-observation with identical bytes on the same URl → PgFrontier-equivalent
    # digest checkpoint is None here so the gate classifies by stored-before (duplicate).
    tick_dup = await pipeline.pump_one(
        tenant_id=tenant,
        injected=FrontierItem(
            frontier_id="F-3b",
            uri=local_server,
            tenant_id=tenant,
            host_key="127.0.0.1",
            priority=1.0,
        ),
    )
    assert tick_dup is not None and tick_dup.lifecycle in ("duplicate", "unchanged")
    assert store.count() == written  # same digest → no new blob
    assert fabric.appended and len(search.indexed) == 1  # no reinterpretation

    await loop.aclose()
