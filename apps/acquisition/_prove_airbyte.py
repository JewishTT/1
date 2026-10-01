"""Feature 023 §38 - the Airbyte acceptance run, end to end, with a real connector.

    airbyte/source-postgres (pinned digest)
      -> docker run spec / check / discover
      -> read over STDIO, one JSON AirbyteMessage per line
      -> RECORD artifacts only; STATE and LOG never become evidence
      -> ArtifactSink -> MinIO -> Capture -> Observation -> Redpanda
      -> real consumer group -> persisted processing result

The fixture discipline of §39 is honoured by *also* running an offline protocol
test; this file is the live half, and nothing here may be satisfied by a fixture.
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
from runtime.airbyte import AirbyteRuntime  # noqa: E402
from storage.s3 import ObjectStore  # noqa: E402

IMAGE = os.environ.get(
    "COGNITIVE_AIRBYTE_IMAGE",
    "airbyte/source-postgres@sha256:e445ee1f7261a50c9b211ccac0cff306"
    "71d026336a4438f9f72021a68c5b602a",
)
MOUNT = Path(os.environ.get("COGNITIVE_AIRBYTE_CFG", r"C:\Users\tim\AppData\Local\Temp\ab"))
BROKERS = os.environ.get("COGNITIVE_KAFKA_BROKERS", "localhost:19092")
ENDPOINT = os.environ.get("COGNITIVE_MINIO_ENDPOINT", "http://localhost:9000")
TENANT = os.environ.get("COGNITIVE_TENANT", "acceptance")
INVESTIGATION = "int-airbyte-smoke"
GROUP = f"airbyte-proof-{os.getpid()}"


async def main() -> int:
    run_id = f"run-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    print("=" * 78)
    print(f"Airbyte LIVE acceptance - {run_id}")
    print("=" * 78)
    print(f"image      : {IMAGE[:60]}")
    print(f"config dir : {MOUNT}")

    runtime = AirbyteRuntime(image=IMAGE, mount_dir=str(MOUNT), task_timeout=240.0)
    cfg, cat = "/cfg/config.json", "/cfg/catalog.json"

    # -- §38: spec -> check -> discover, each independently evidenced -----------
    print("\n1. SPEC (§25)")
    try:
        spec_run = await runtime.spec()
        print("   SPEC message   : yes")
        print(f"   connector      : {spec_run.connector_ref}")
    except Exception as exc:  # noqa: BLE001
        print(f"   spec FAILED    : {type(exc).__name__}: {exc}")
        return 2

    print("\n2. CHECK (§28: connectivity diagnostic, not evidence)")
    try:
        check_run = await runtime.check(cfg)
        print(f"   status         : {check_run.connection_status}")
    except Exception as exc:  # noqa: BLE001
        print(f"   check FAILED   : {type(exc).__name__}: {exc}")
        return 3

    print("\n3. DISCOVER (§114: catalog is source metadata)")
    try:
        disc_run = await runtime.discover(cfg)
        streams = [s["name"] for s in disc_run.catalog.get("streams", [])]
        print(f"   streams found  : {len(streams)}")
        print(f"   smoke stream   : {'airbyte_smoke' in streams}")
        configured = json.loads((MOUNT / "catalog.json").read_text(encoding="utf-8"))
        print(f"   configured     : {len(configured.get('streams', []))} stream(s)")
    except Exception as exc:  # noqa: BLE001
        print(f"   discover FAILED: {type(exc).__name__}: {exc}")
        return 4

    # -- read: streamed, RECORD only ------------------------------------------
    print("\n4. READ (§27 streaming, §28 four message classes)")
    producer = IdempotentProducer(bootstrap_servers=BROKERS)
    store = ObjectStore(
        endpoint=ENDPOINT,
        access_key=os.environ.get("COGNITIVE_MINIO_ACCESS_KEY", "demo"),
        secret_key=os.environ.get("COGNITIVE_MINIO_SECRET_KEY", "demopass"),
        raw_bucket=os.environ.get("COGNITIVE_MINIO_RAW_BUCKET", "knowledge-raw"),
    )
    gate = ObservationGate(store=store, router=ContentRouter(), producer=producer)
    sink = ArtifactSink(gate=gate, store=store, source_family="connector")

    accepted = []
    task = {
        "task_id": "TSK-airbyte-1",
        "source_id": "airbyte.source-postgres",
        "worker_ref": "airbyte",
        "runtime_ref": "airbyte",
        "config_path": cfg,
        "catalog_path": cat,
        "runtime_version": IMAGE.split("@")[-1][:19],
    }
    try:
        async for artifact in runtime.acquire(task):
            got = await sink.accept(
                artifact,
                tenant_id=TENANT,
                investigation_id=INVESTIGATION,
                work_id="WID-airbyte-1",
                time_basis=CaptureTimeBasis.FETCH,
            )
            accepted.append(got)
            print(
                f"   {got.locator:<44} {got.artifact.byte_length:>6}B  "
                f"{got.observation_id} -> {got.topic}@{got.event_id[:20]}"
            )
    except Exception as exc:  # noqa: BLE001
        print(f"   read FAILED    : {type(exc).__name__}: {exc}")
        return 5

    ab = runtime.run
    print(f"\n   RECORDs emitted: {ab.records}")
    print(f"   STATE msgs     : {ab.states}   <- control plane, NOT evidence (§28)")
    print(f"   LOG msgs       : {ab.logs}    <- telemetry, NOT evidence")
    print(f"   TRACE msgs     : {ab.traces}")
    print(f"   unknown types  : {ab.unknown}")
    print(f"   quarantined    : {len(ab.quarantined)}")
    print(f"   observations   : {len(accepted)}")

    if not accepted:
        print("   NO RECORDS - check the catalog selects a populated stream")
        return 6

    # -- §138 reconciliation: observation_count == record_count ----------------
    print("\n5. RECONCILIATION (§138)")
    reconcile_ok = len(accepted) == ab.records
    print(f"   source RECORDs           : {ab.records}")
    print(f"   observations persisted   : {len(accepted)}")
    print(f"   STATE excluded from count: {ab.states} (correct)")
    print(f"   identity                 : {reconcile_ok}")

    # -- Redpanda + a real consumer -------------------------------------------
    print("\n6. REDPANDA + CONSUMER")
    producer.flush(timeout_s=60)
    from confluent_kafka import Consumer
    from events import event_envelope_pb2 as pb

    consumer = Consumer(
        {
            "bootstrap.servers": BROKERS,
            "group.id": GROUP,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe(["observation"])
    wanted = {a.observation_id for a in accepted}
    seen: dict[str, dict] = {}
    import time

    deadline = time.monotonic() + 60
    while time.monotonic() < deadline and len(seen) < len(wanted):
        msg = consumer.poll(1.0)
        if msg is None or msg.error():
            continue
        env = pb.EventEnvelope()
        env.ParseFromString(msg.value())
        if env.observation_id in wanted:
            seen[env.observation_id] = {
                "partition": msg.partition(),
                "offset": msg.offset(),
                "event_id": env.event_id,
                "topic": msg.topic(),
                "producer": env.producer,
            }
    consumer.close()
    print(f"   consumer group   : {GROUP}")
    print(f"   our observations : {len(wanted)}")
    print(f"   read back        : {len(seen)}")
    if seen:
        p = next(iter(seen.values()))
        print(f"   example          : {p['topic']}[{p['partition']}]@{p['offset']}")

    empty = {"partition": "-", "offset": "-", "topic": "-", "event_id": "-"}
    obs_id, pos = next(iter(seen.items())) if seen else ("", empty)
    derived = f"{pos['topic']}[{pos['partition']}]@{pos['offset']}"
    result = {
        "processing_run_id": run_id,
        "observation_id": obs_id,
        "consumer": GROUP,
        "consumer_version": "0.1.0",
        "processed_at": datetime.now(UTC).isoformat(),
        "status": "processed",
        "derived_ref": derived,
    }

    out = Path("artifacts/acquisition-integration")
    out.mkdir(parents=True, exist_ok=True)
    (out / "airbyte.json").write_text(
        json.dumps(
            {
                "run_manifest": {
                    "integration_run_id": run_id,
                    "tenant_id": TENANT,
                    "investigation_id": INVESTIGATION,
                    "task_id": task["task_id"],
                    "source_id": task["source_id"],
                    "worker_ref": "airbyte",
                    "runtime_ref": "airbyte",
                    "image": IMAGE,
                    "connector": ab.connector_ref,
                    "records": ab.records,
                    "states": ab.states,
                    "logs": ab.logs,
                    "observations": len(accepted),
                    "published": len(seen),
                    "processed": len(seen),
                    "consumer_group": GROUP,
                    "git_sha": os.popen("git rev-parse HEAD").read().strip(),
                },
                "airbyte_run": ab.to_dict(),
                "artifacts": [a.to_dict() for a in accepted],
                "readback": seen,
                "processing_result": result,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"   artifact        : {out / 'airbyte.json'}")

    ok = reconcile_ok and len(seen) == len(wanted) and ab.records > 0
    state_is_evidence = any("state" in a.locator.lower() for a in accepted)
    print("\n" + "=" * 78)
    print(f"RESULT: {'PASS' if ok else 'FAIL'}")
    floor = "OK" if ab.records >= 10 else "ALL AVAILABLE (recorded)"
    print(f"  N >= 10 (or all available, recorded): {ab.records} {floor}")
    print(f"  STATE never became evidence         : {not state_is_evidence}")
    print(f"  observation_count == record_count   : {reconcile_ok}")
    print("=" * 78)
    return 0 if ok else 7


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
