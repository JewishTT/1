"""Feature 023 §46/§50/§55 - the three external-tool runtimes, live, through one boundary.

    Maigret   0.6.6  (built from donors/maigret, §42 isolation)
    BBOT      3.x    (pinned image,      §47 JSON, NOT its Kafka module)
    SpiderFoot 4.0    (pinned image,      §51 CLI JSON boundary)

All three go through :class:`ExternalToolRuntime` and then the same sink, gate and
Redpanda path the other families use. That shared tail is the point: a tool that
emits observations a different way is not integrated, it is merely connected.

Targets are bounded and recorded, per O-6 - no broad reconnaissance of third
parties.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from artifact_sink import ArtifactSink  # noqa: E402
from domain.capture import CaptureTimeBasis  # noqa: E402
from events.content_router import ContentRouter  # noqa: E402
from events.kafka import IdempotentProducer  # noqa: E402
from events.observation_gate import ObservationGate  # noqa: E402
from runtime.external_tool import TOOL_DEFINITIONS, ExternalToolRuntime  # noqa: E402
from storage.s3 import ObjectStore  # noqa: E402

BROKERS = os.environ.get("COGNITIVE_KAFKA_BROKERS", "localhost:19092")
ENDPOINT = os.environ.get("COGNITIVE_MINIO_ENDPOINT", "http://localhost:9000")
TENANT = os.environ.get("COGNITIVE_TENANT", "acceptance")
INVESTIGATION = "int-tools-smoke"
OUT = Path(os.environ.get("COGNITIVE_TOOL_OUT", r"C:\Users\tim\AppData\Local\Temp\toolout"))
GROUP = f"tools-proof-{os.getpid()}"

# Bounded targets, chosen for resolvability rather than for yield. A run that
# exercises the protocol does not need a hit; §82 says site accuracy is not an
# acceptance condition for the acquisition protocol itself.
SCENARIOS = {
    "maigret": {
        "kind": "external_tool",
        "params": {"username": "test", "site": "github", "timeout": 20},
        "mount": OUT,
        "network": "bridge",
    },
    "bbot": {
        # BBOT is not an ExternalToolRuntime: it is an event-producing runtime with
        # its own provenance vocabulary, and routing it through the generic tool
        # path would flatten exactly the fields §48 asks to preserve.
        "kind": "bbot",
        "params": {"target": "example.com"},
        "mount": os.environ.get("COGNITIVE_BBOT_CACHE", ""),
        "network": "bridge",
    },
    "spiderfoot": {
        "kind": "external_tool",
        "params": {
            "target": "example.com",
            "modules": "sfp_dnsresolve",
            "types": "IP_ADDRESS",
        },
        "mount": None,
        "network": "bridge",
    },
}


async def run_one(
    name: str, producer, store, sink, run_id: str
) -> dict:
    spec = SCENARIOS[name]
    accepted: list = []
    error = ""
    run_meta: dict = {}

    if spec["kind"] == "bbot":
        from runtime.bbot import BbotRuntime

        runtime = BbotRuntime(cache_dir=spec["mount"] or None, network_policy=spec["network"])
        health = await runtime.probe()
        print(f"\n{'=' * 74}\n{name.upper()}  (BBOT {health.detail[:40]})\n{'=' * 74}")
        print(f"  runtime_ref : {runtime.runtime_ref}  ({runtime.execution_class})")
        bbot_argv = "bbot -t " + spec["params"]["target"] + " -p subdomain-enum -rf passive --json"
        print("  argv        : " + bbot_argv)
        print(f"  network     : {spec['network']} (passive modules)")
        print(f"  probe       : {'ok' if health.ready else health.detail[:70]}")
        try:
            async for artifact in runtime.acquire(
                {"target": spec["params"]["target"], "task_id": f"TSK-{name}-1",
                 "source_id": f"{name}.recon"}
            ):
                got = await sink.accept(
                    artifact,
                    tenant_id=TENANT,
                    investigation_id=INVESTIGATION,
                    work_id=f"WID-{name}-1",
                    time_basis=CaptureTimeBasis.FETCH,
                )
                accepted.append(got)
                if len(accepted) <= 4:
                    print(
                        f"    {got.locator[:44]:<44} {got.artifact.byte_length:>6}B  "
                        f"{got.artifact.metadata.get('donor_event_type')}"
                    )
        except Exception as exc:  # noqa: BLE001
            error = f"{getattr(exc, 'code', type(exc).__name__)}: {str(exc)[:150]}"
        # §28's discipline, applied to BBOT: SCAN events are run metadata.
        run_meta = {
            "scan_events": len(runtime.scan_events),
            "scan_events_are_evidence": False,
            "process_exit_code": runtime.process_run.exit_code if runtime.process_run else None,
        }
        print(f"  SCAN events : {len(runtime.scan_events)}  <- run metadata, NOT evidence (§28)")
        print(f"  observations: {len(accepted)}")
    else:
        definition = TOOL_DEFINITIONS[name]
        # Maigret writes its JSON report into the container and reaches the host
        # only through the bind mount, so the definition is told where that lands.
        if name == "maigret":
            definition = replace(definition, output_host_dir=str(spec["mount"]))
        runtime = ExternalToolRuntime(
            definition, network_policy=spec["network"], mount_dir=str(spec["mount"] or "") or None
        )
        print(f"\n{'=' * 74}\n{name.upper()}  ({definition.image.split('/')[0]})\n{'=' * 74}")
        print(f"  runtime_ref : {definition.runtime_ref}")
        print(f"  argv        : {' '.join(definition.build_argv(spec['params']))[:110]}")
        print(f"  config_dig  : {definition.config_digest(spec['params'])}")
        try:
            async for artifact in runtime.stream(
                spec["params"], task_id=f"TSK-{name}-1", source_id=f"{name}.smoke"
            ):
                got = await sink.accept(
                    artifact,
                    tenant_id=TENANT,
                    investigation_id=INVESTIGATION,
                    work_id=f"WID-{name}-1",
                    time_basis=CaptureTimeBasis.FETCH,
                )
                accepted.append(got)
                if len(accepted) <= 4:
                    print(
                        f"    {got.locator[:34]:<34} {got.artifact.byte_length:>7}B  "
                        f"{got.observation_id[:26]} -> {got.topic}"
                    )
        except Exception as exc:  # noqa: BLE001
            error = f"{getattr(exc, 'code', type(exc).__name__)}: {str(exc)[:150]}"
        run = runtime.run
        if run is not None:
            run_meta = {"exit_code": run.exit_code, "stdout_bytes": run.stdout_bytes}
            print(f"  exit_code   : {run.exit_code}")
            print(f"  stdout      : {run.stdout_bytes}B -> {run.stdout_ref.split('/')[-1]}")
            print(f"  seconds     : {run.seconds}")
        print(f"  observations: {len(accepted)}")

    if error:
        print(f"  FAILURE     : {error}")
    return {
        "tool": name,
        "kind": spec["kind"],
        "ok": bool(accepted) and not error,
        "observations": len(accepted),
        "error": error,
        "run": run_meta,
        "sample": accepted[0].to_dict() if accepted else {},
        "locators": [a.locator for a in accepted[:5]],
    }


async def main() -> int:
    run_id = f"run-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    print("=" * 74)
    print(f"External-tool LIVE acceptance - {run_id}")
    print("=" * 74)

    OUT.mkdir(parents=True, exist_ok=True)
    producer = IdempotentProducer(bootstrap_servers=BROKERS)
    store = ObjectStore(
        endpoint=ENDPOINT,
        access_key=os.environ.get("COGNITIVE_MINIO_ACCESS_KEY", "demo"),
        secret_key=os.environ.get("COGNITIVE_MINIO_SECRET_KEY", "demopass"),
        raw_bucket=os.environ.get("COGNITIVE_MINIO_RAW_BUCKET", "knowledge-raw"),
    )
    gate = ObservationGate(store=store, router=ContentRouter(), producer=producer)
    sink = ArtifactSink(gate=gate, store=store, source_family="external_tool")

    results = []
    for name in SCENARIOS:
        results.append(await run_one(name, producer, store, sink, run_id))

    producer.flush(timeout_s=60)

    print(f"\n{'=' * 74}\nREDPANDA + CONSUMER\n{'=' * 74}")
    from confluent_kafka import Consumer
    from events import event_envelope_pb2 as pb

    all_obs: list[str] = []
    for acc in sink.accepted:
        all_obs.append(acc.observation_id)
    wanted = set(all_obs)

    consumer = Consumer(
        {
            "bootstrap.servers": BROKERS,
            "group.id": GROUP,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe(["observation"])
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
                "topic": msg.topic(),
                "event_id": env.event_id,
            }
    consumer.close()
    print(f"  consumer group  : {GROUP}")
    print(f"  tool observations: {len(wanted)}")
    print(f"  read back        : {len(seen)}")

    out = Path("artifacts/acquisition-integration")
    out.mkdir(parents=True, exist_ok=True)
    (out / "external_tools.json").write_text(
        json.dumps(
            {
                "run_manifest": {
                    "integration_run_id": run_id,
                    "tenant_id": TENANT,
                    "investigation_id": INVESTIGATION,
                    "tools": {r["tool"]: r["observations"] for r in results},
                    "published": len(seen),
                    "consumer_group": GROUP,
                    "git_sha": os.popen("git rev-parse HEAD").read().strip(),
                    "targets": {
                        k: {kk: str(vv)[:80] for kk, vv in v["params"].items()}
                        for k, v in SCENARIOS.items()
                    },
                },
                "results": results,
                "readback": seen,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    green = [r for r in results if r["ok"]]
    print(f"\n{'=' * 74}")
    for r in results:
        verdict = "PASS" if r["ok"] else "FAIL: " + r["error"][:70]
        print(f"  {r['tool']:<12} {r['observations']:>3} obs   {verdict}")
    print(f"  downstream     {len(seen)}/{len(wanted)} read back")
    print(f"  artifact       {out / 'external_tools.json'}")
    print("=" * 74)
    return 0 if len(green) == len(results) else 8


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
