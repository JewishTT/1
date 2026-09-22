"""End-to-end fabric pipeline on the live dev stack (I-11, US1).

Proves the whole circle against real Postgres + MinIO + Redpanda:

    PgFrontier.enqueue -> pop (lease) -> httpx fetch (local http server)
    -> ObservationGate.ingest (content-addressed MinIO + lifecycle event on
    topic "observation") -> PgFrontier.complete (last_digest recorded)

Second pass re-observes the same URI with identical bytes and must emit
``observation.unchanged`` (three-way split, R-08 / T101), and must NOT re-store
bytes (same content hash -> same S3 key).

Skipped when Postgres, MinIO, or the broker are unreachable.
"""

from __future__ import annotations

import http.server
import os
import socket
import sys
import threading
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apps" / "control-plane"))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apps" / "shared"))

import pytest
from confluent_kafka import Consumer, Producer

from db.session import create_tables, make_session_factory
from events.content_router import ContentRouter
from events.kafka import IdempotentProducer
from events.observation_gate import ObservationGate
from services.acquisition_loop import AcquisitionLoop
from services.frontier import FrontierItem, PgFrontier
from storage.s3 import ObjectStore, sha256_bytes

pytestmark = pytest.mark.integration

_PG = os.getenv("POSTGRES_DSN", "postgresql://cognitive:cognitive@localhost:5432/cognitive")
_BROKER = os.getenv("KAFKA_BOOTSTRAP", "localhost:19092")


# --- availability guards ------------------------------------------------------


def _pg_up() -> bool:
    host = _PG.split("@")[-1].split("/")[0]
    h, p = host.split(":")
    try:
        with socket.create_connection((h, int(p)), timeout=2):
            return True
    except OSError:
        return False


def _broker_up() -> bool:
    try:
        p = Producer({"bootstrap.servers": _BROKER, "socket.timeout.ms": 1000})
        return bool(p.list_topics(timeout=3).brokers)
    except Exception:
        return False


def _minio_up() -> bool:
    try:
        with socket.create_connection(("localhost", 9000), timeout=2):
            return True
    except OSError:
        return False


require_stack = pytest.mark.skipif(
    not (_pg_up() and _broker_up() and _minio_up()),
    reason="full dev stack offline (postgres+broker+minio)",
)


# --- local http fixture --------------------------------------------------------


class _Handler(http.server.BaseHTTPRequestHandler):
    BODY = b"<html><head><title>e2e</title></head><body>hello fabric</body></html>"

    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(self.BODY)))
        self.send_header("ETag", '"e2e-v1"')
        self.end_headers()
        self.wfile.write(self.BODY)

    def log_message(self, *args):  # suppress noise
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


async def _consume_event(observation_id: str, timeout: float = 20.0) -> dict | None:
    from events.event_envelope_pb2 import EventEnvelope

    group = f"e2e-{uuid.uuid4().hex[:8]}"
    c = Consumer(
        {
            "bootstrap.servers": _BROKER,
            "group.id": group,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": True,
            "session.timeout.ms": 6000,
        }
    )
    c.subscribe(["observation"])
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            msg = c.poll(1.0)
            if msg is None or msg.error():
                continue
            env = EventEnvelope()
            env.ParseFromString(msg.value())
            if env.observation_id == observation_id:
                return {
                    "event_type": env.event_type,
                    "observation_id": env.observation_id,
                    "tenant_id": env.tenant_id,
                    "payload": env.payload.decode(errors="replace"),
                }
    finally:
        c.close()
    return None


@require_stack
async def test_end_to_end_pipeline_single_item(local_server: str) -> None:
    tenant = f"e2e-{uuid.uuid4().hex[:8]}"
    ho = "127.0.0.1"

    await create_tables(_PG)
    frontier = PgFrontier(make_session_factory(_PG))
    gate = ObservationGate(
        ObjectStore(),
        ContentRouter(),
        IdempotentProducer(bootstrap_servers=_BROKER),
    )
    loop = AcquisitionLoop(frontier, gate)
    try:
        fid = f"F-{uuid.uuid4().hex[:6]}"
        # --- pass 1: created ---
        assert await frontier.enqueue(
            FrontierItem(frontier_id=fid, uri=local_server, tenant_id=tenant, host_key=ho, priority=1.0)
        ) is True
        item = await frontier.pop_next(tenant_id=tenant)
        assert item is not None and item.frontier_id == fid and item.state == "LEASED"

        res = await loop.run_item(item)
        assert res.ok, res.reason
        assert res.lifecycle == "created"
        assert res.raw_ref.startswith(f"s3://knowledge/raw/{tenant}/"), res.raw_ref
        assert res.digest == sha256_bytes(_Handler.BODY)

        ev = await _consume_event(res.observation_id)
        assert ev is not None and ev["event_type"] == "observation.created"
        assert ev["tenant_id"] == tenant
        assert ev["payload"].endswith(res.digest)
        assert await frontier.last_digest(fid) == res.digest
        assert await frontier.count(tenant_id=tenant) == 1

        # --- pass 2: unchanged (freshness reseed, identical bytes) ---
        await frontier.reschedule(fid)
        item2 = await frontier.pop_next(tenant_id=tenant)
        assert item2 is not None and item2.frontier_id == fid
        res2 = await loop.run_item(item2)
        assert res2.ok, res2.reason
        assert res2.lifecycle == "unchanged"
        # Content-addressed dedup: identical bytes -> identical S3 key.
        assert res2.raw_ref == res.raw_ref

        ev2 = await _consume_event(res2.observation_id, timeout=20.0)
        assert ev2 is not None and ev2["event_type"] == "observation.unchanged"
        assert ev2["tenant_id"] == tenant
    finally:
        await loop.aclose()


@require_stack
async def test_frontier_dedup_and_fail_retry() -> None:
    tenant = f"e2e-{uuid.uuid4().hex[:8]}"
    await create_tables(_PG)
    frontier = PgFrontier(make_session_factory(_PG))

    # Duplicate enqueue of the same tenant+uri is a no-op (unique schedule key).
    uri = f"http://example.invalid/{uuid.uuid4().hex[:6]}"
    a_id, b_id = f"A-{uuid.uuid4().hex[:6]}", f"B-{uuid.uuid4().hex[:6]}"
    assert await frontier.enqueue(FrontierItem(frontier_id=a_id, uri=uri, tenant_id=tenant, priority=0.5)) is True
    assert await frontier.enqueue(FrontierItem(frontier_id=b_id, uri=uri, tenant_id=tenant, priority=0.9)) is False

    # Highest-priority survives; heap stays size one.
    assert await frontier.count(tenant_id=tenant) == 1
    popped = await frontier.pop_next(tenant_id=tenant)
    assert popped is not None and popped.priority == pytest.approx(0.9)

    # Failure path: retries exhaust into QUARANTINED, re-schedule returns READY.
    await frontier.fail_retry(a_id, max_retries=2, cooldown_s=0)
    assert (await frontier.ready_count(tenant_id=tenant)) == 1
    await frontier.fail_retry(a_id, max_retries=2, cooldown_s=0)
    await frontier.fail_retry(a_id, max_retries=2, cooldown_s=0)
    assert (await frontier.ready_count(tenant_id=tenant)) == 0
    await frontier.reschedule(a_id, when=time.time())
    assert (await frontier.ready_count(tenant_id=tenant)) == 1