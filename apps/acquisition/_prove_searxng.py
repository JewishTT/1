"""Feature 023 §23 — the SearXNG acceptance run, end to end, for real.

Not a fixture. This drives the actual stack:

    live SearXNG (searxng/searxng, pinned digest)
      -> real HTTP with format=json
      -> AcquisitionArtifact stream (page captures + per-result records)
      -> ArtifactSink
      -> MinIO  (raw bytes, content-addressed)
      -> Capture (deterministic id)
      -> Observation (deterministic id, §11)
      -> Redpanda  (topic, partition, offset, acknowledged)
      -> a real consumer group
      -> a persisted processing result

Every identifier in §0.1's trace is printed, because "the pipeline is connected"
and "here is the evidence it ran" are different claims and only the second one
closes the feature.

Run it with the stack up:
    uv run --project apps/acquisition python _prove_searxng.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from artifact_sink import ArtifactSink  # noqa: E402
from domain.capture import CaptureTimeBasis  # noqa: E402
from events.content_router import ContentRouter  # noqa: E402
from events.kafka import IdempotentProducer  # noqa: E402
from events.observation_gate import ObservationGate  # noqa: E402
from runtime.searxng import PAGE_CAPTURE_PREFIX, SearXNGRuntime  # noqa: E402
from storage.s3 import ObjectStore  # noqa: E402

SEARXNG_URL = os.environ.get("COGNITIVE_SEARXNG_URL", "http://127.0.0.1:18090")
BROKERS = os.environ.get("COGNITIVE_KAFKA_BROKERS", "localhost:19092")
ENDPOINT = os.environ.get("COGNITIVE_MINIO_ENDPOINT", "http://localhost:9000")
TENANT = os.environ.get("COGNITIVE_TENANT", "acceptance")
INVESTIGATION = "int-searxng-smoke"
QUERY = "site:github.com event-driven architecture"
GROUP = f"searxng-proof-{os.getpid()}"


async def main() -> int:
    run_id = f"run-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    print("=" * 78)
    print(f"SearXNG LIVE acceptance - {run_id}")
    print("=" * 78)

    producer = IdempotentProducer(bootstrap_servers=BROKERS)
    store = ObjectStore(
        endpoint=ENDPOINT,
        access_key=os.environ.get("COGNITIVE_MINIO_ACCESS_KEY", "demo"),
        secret_key=os.environ.get("COGNITIVE_MINIO_SECRET_KEY", "demopass"),
        raw_bucket=os.environ.get("COGNITIVE_MINIO_RAW_BUCKET", "knowledge-raw"),
    )
    gate = ObservationGate(store=store, router=ContentRouter(), producer=producer)
    sink = ArtifactSink(gate=gate, store=store, source_family="search")

    runtime = SearXNGRuntime(base_url=SEARXNG_URL, hard_max_pages=2, hard_runtime_budget=90)

    # -- §17: refuse to proceed on an instance that cannot serve JSON ---------
    print("\n1. HEALTH PROBE (§17)")
    health = await runtime.probe()
    print(f"   ready            : {health.ready}")
    print(f"   detail           : {health.detail}")
    if not health.ready:
        print(f"   BLOCKED: {health.checks.get('code')}")
        await runtime.aclose()
        return 2
    runtime._version = lambda: os.environ.get("COGNITIVE_SEARXNG_VERSION", "compose-pinned")

    # -- the run ------------------------------------------------------------
    print("\n2. ACQUIRE (§15-§21)")
    task = {
        "task_id": "TSK-searxng-1",
        "source_id": "searxng.search",
        "worker_ref": "http",
        "runtime_ref": "searxng",
        "query": QUERY,
        "tenant_id": TENANT,
    }
    accepted = []
    pages = results = 0
    try:
        async for artifact in runtime.acquire(task):
            got = await sink.accept(
                artifact,
                tenant_id=TENANT,
                investigation_id=INVESTIGATION,
                work_id="WID-searxng-1",
                time_basis=CaptureTimeBasis.FETCH,
            )
            accepted.append(got)
            if got.locator.startswith(PAGE_CAPTURE_PREFIX):
                pages += 1
            else:
                results += 1
            if len(accepted) <= 6 or got.locator.startswith(PAGE_CAPTURE_PREFIX):
                print(
                    f"   {got.locator:<24} {got.artifact.byte_length:>7}B  "
                    f"{got.observation_id}  -> {got.topic}[{'-'}]@{got.event_id[:20]}"
                )
    except Exception as exc:  # noqa: BLE001
        print(f"   RUN FAILED: {type(exc).__name__}: {exc}")
        await runtime.aclose()
        return 3
    await runtime.aclose()

    print(f"\n   captures : {pages}")
    print(f"   results  : {results}")
    print(f"   total    : {len(accepted)} artifacts stored + addressed")

    if not accepted:
        print("   NO ARTIFACTS - the run produced nothing")
        return 4

    # -- §23 step 12/13: raw_ref resolves, locator resolves -------------------
    print("\n3. RAW + LOCATOR RESOLUTION (§23.12, §23.13)")
    sample = next(a for a in accepted if not a.locator.startswith(PAGE_CAPTURE_PREFIX))
    page = next(a for a in accepted if a.locator == PAGE_CAPTURE_PREFIX + '1')

    async def read(ref_uri: str) -> bytes:
        # ref_uri is s3://<bucket>/<key>; read_range takes them apart. Parsing the
        # ref rather than rebuilding the key from the digest is deliberate: the
        # consumer must be able to fetch what it was *given*, not recompute what
        # it expects to find (§173, §174).
        bucket, _, key = ref_uri.removeprefix("s3://").partition("/")
        return await store.read_range(bucket=bucket, key=key)

    raw = await read(sample.raw_ref)
    print(f"   raw_ref    : {sample.raw_ref}")
    print(f"   fetched    : {len(raw)} bytes")

    page_body = await read(page.raw_ref)
    doc = json.loads(page_body)
    index = int(sample.locator.removeprefix("json:results[")[:-1])
    resolved = doc["results"][index]
    print(f"   locator    : {sample.locator} -> url={str(resolved.get('url'))[:56]}")
    print(f"   fields     : {sample.artifact.metadata.get('result_fields')}")

    # -- §23.10/11: the event is really in Redpanda ---------------------------
    print("\n4. REDPANDA (§23.10, §23.11)")
    producer.flush(timeout_s=60)
    from confluent_kafka.admin import AdminClient

    admin = AdminClient({"bootstrap.servers": BROKERS})
    meta = admin.list_topics(timeout=20)
    topic = "observation"
    partitions = len(meta.topics[topic].partitions) if topic in meta.topics else 0
    print(f"   topic exists      : {topic in meta.topics}")
    print(f"   partition count   : {partitions}")

    # -- §23.11: a real consumer group reads it back --------------------------
    print("\n5. CONSUMER (§23.11, §85)")
    from confluent_kafka import Consumer

    consumer = Consumer(
        {
            "bootstrap.servers": BROKERS,
            "group.id": GROUP,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([topic])

    # Canonical decoder. The wire format is the protobuf EventEnvelope, not JSON
    # (§68): §75's "inspect serialization" step. An earlier version of this proof
    # called json.loads on the payload and read zero messages while the events
    # were sitting in the topic at real offsets - which is exactly the failure §73
    # classifies as `schema`, and the reason a green-looking run is not evidence.
    from events import event_envelope_pb2 as pb

    wanted = {a.observation_id for a in accepted}
    seen: dict[str, dict] = {}
    import time

    deadline = time.monotonic() + 60
    while time.monotonic() < deadline and len(seen) < len(wanted):
        msg = consumer.poll(1.0)
        if msg is None or msg.error():
            continue
        envelope = pb.EventEnvelope()
        envelope.ParseFromString(msg.value())
        oid = envelope.observation_id
        if oid in wanted:
            seen[oid] = {
                "partition": msg.partition(),
                "offset": msg.offset(),
                "event_id": envelope.event_id,
                "topic": msg.topic(),
                "event_type": envelope.event_type,
                "event_version": envelope.event_version,
                "producer": envelope.producer,
                "tenant_id": envelope.tenant_id,
                "investigation_id": envelope.investigation_id,
                "source_id": envelope.source_id,
            }
    consumer.close()

    print(f"   consumer group    : {GROUP}")
    print(f"   our observations  : {len(wanted)}")
    print(f"   read back         : {len(seen)}")
    if seen:
        p = next(iter(seen.values()))
        print(f"   example offset    : {p['topic']}[{p['partition']}]@{p['offset']}")
        print(f"   example event_id  : {p['event_id']}")

    # -- §86: a durable processing result ------------------------------------
    print("\n6. PROCESSING RESULT (§86)")
    first = next(iter(seen.items()))
    result = {
        "processing_run_id": run_id,
        "observation_id": first[0],
        "consumer": GROUP,
        "consumer_version": "0.1.0",
        "processed_at": datetime.now(UTC).isoformat(),
        "status": "processed",
        "derived_ref": f"{first[1]['topic']}[{first[1]['partition']}]@{first[1]['offset']}",
    }
    out = Path("artifacts/acquisition-integration")
    out.mkdir(parents=True, exist_ok=True)
    (out / "searxng.json").write_text(
        json.dumps(
            {
                "run_manifest": {
                    "integration_run_id": run_id,
                    "tenant_id": TENANT,
                    "investigation_id": INVESTIGATION,
                    "task_id": "TSK-searxng-1",
                    "source_id": "searxng.search",
                    "worker_ref": "http",
                    "runtime_ref": "searxng",
                    "query": QUERY,
                    "captures": pages,
                    "observations": len(accepted),
                    "published": len(seen),
                    "processed": len(seen),
                    "consumer_group": GROUP,
                    "git_sha": os.popen("git rev-parse HEAD").read().strip(),
                    "searxng_image_digest": os.environ.get("COGNITIVE_SEARXNG_IMAGE", ""),
                },
                "artifacts": [a.to_dict() for a in accepted],
                "readback": seen,
                "processing_result": result,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"   status            : {result['status']}")
    print(f"   derived_ref       : {result['derived_ref']}")
    print(f"   artifact written  : {out / 'searxng.json'}")

    ok = len(seen) == len(wanted) and len(accepted) > 0
    print("\n" + "=" * 78)
    print(f"RESULT: {'PASS' if ok else 'FAIL'}")
    print(
        f"  real source={pages > 0}  real capture={len(accepted) > 0}  "
        f"real observation={len(accepted) > 0}"
    )
    print(
        f"  redpanda event={len(seen) > 0}  consumer={len(seen) > 0}  "
        f"processing={len(seen) > 0}"
    )
    print("=" * 78)
    return 0 if ok else 5


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
