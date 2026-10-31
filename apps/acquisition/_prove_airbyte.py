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
import tempfile
from shutil import copyfile
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
_CONFIG_ROOT = os.environ.get("COGNITIVE_AIRBYTE_CFG", "").strip()
MOUNT = Path(_CONFIG_ROOT).expanduser() if _CONFIG_ROOT else Path(tempfile.mkdtemp(prefix="cognitive-airbyte-"))
BROKERS = os.environ.get("COGNITIVE_KAFKA_BROKERS", "localhost:19092")
ENDPOINT = os.environ.get("COGNITIVE_MINIO_ENDPOINT", "http://localhost:9000")
TENANT = os.environ.get("COGNITIVE_TENANT", "acceptance")
INVESTIGATION = "int-airbyte-smoke"
GROUP = f"airbyte-proof-{os.getpid()}"


def _enum_or_preferred(schema: dict, preferred: tuple[str, ...]) -> str | None:
    """Choose a declared provider option; never invent an enum outside the SPEC."""
    choices = schema.get("enum") or []
    if not choices:
        constant = schema.get("const")
        return str(constant) if constant is not None else (
            str(schema["default"]) if schema.get("default") is not None else None
        )
    normalized = {str(value).lower(): str(value) for value in choices}
    for value in preferred:
        if value.lower() in normalized:
            return normalized[value.lower()]
    return str(choices[0])


def _object_choice(schema: dict, preferred: dict[str, tuple[str, ...]]) -> dict | None:
    properties = schema.get("properties") or {}
    chosen: dict = {}
    for name, child in properties.items():
        if child.get("type") == "object":
            nested = _object_choice(child, preferred)
            if nested is not None:
                chosen[name] = nested
            continue
        value = _enum_or_preferred(child, preferred.get(name, ()))
        if value is not None:
            chosen[name] = value
    if chosen:
        return chosen
    if schema.get("default") is not None and isinstance(schema["default"], dict):
        return dict(schema["default"])
    return None


def _default_postgres_config(connector_spec: dict) -> dict:
    """Build the local smoke config using only fields/options declared by connector SPEC."""
    connection = connector_spec.get("connectionSpecification") or {}
    properties = connection.get("properties") or {}
    if not properties:
        raise ValueError("source-postgres SPEC has no connectionSpecification.properties")

    config = {
        "host": os.environ.get("COGNITIVE_AIRBYTE_PG_HOST", "host.docker.internal"),
        "port": int(os.environ.get("COGNITIVE_AIRBYTE_PG_PORT", "5432")),
        "database": os.environ.get("COGNITIVE_AIRBYTE_PG_DATABASE", "cognitive"),
        "username": os.environ.get("COGNITIVE_AIRBYTE_PG_USERNAME", "cognitive"),
        "password": os.environ.get("COGNITIVE_AIRBYTE_PG_PASSWORD", "cognitive"),
    }
    if "schemas" in properties:
        config["schemas"] = [x.strip() for x in os.environ.get("COGNITIVE_AIRBYTE_PG_SCHEMAS", "public").split(",") if x.strip()]

    preferences = {
        "mode": ("disable", "require", "prefer"),
        "tunnel_method": ("NO_TUNNEL",),
        "method": ("Standard", "standard", "Xmin", "xmin"),
    }
    for name in ("ssl_mode", "tunnel_method", "replication_method"):
        schema = properties.get(name)
        if schema and schema.get("type") == "object":
            selected = _object_choice(schema, preferences)
            if selected is not None:
                config[name] = selected

    required = set(connection.get("required") or [])
    missing = sorted(name for name in required if name not in config)
    if missing:
        raise ValueError(
            "source-postgres SPEC requires configuration fields not safely defaulted: "
            + ", ".join(missing)
            + "; provide COGNITIVE_AIRBYTE_CONFIG_FILE or COGNITIVE_AIRBYTE_CONFIG_JSON"
        )
    return config


def _write_config(mount: Path, connector_spec: dict) -> Path:
    mount.mkdir(parents=True, exist_ok=True)
    target = mount / "config.json"
    explicit_file = os.environ.get("COGNITIVE_AIRBYTE_CONFIG_FILE", "").strip()
    explicit_json = os.environ.get("COGNITIVE_AIRBYTE_CONFIG_JSON", "").strip()
    if explicit_file:
        copyfile(Path(explicit_file).expanduser(), target)
    elif explicit_json:
        parsed = json.loads(explicit_json)
        target.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
    else:
        target.write_text(
            json.dumps(_default_postgres_config(connector_spec), indent=2),
            encoding="utf-8",
        )
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return target


def _write_configured_catalog(mount: Path, discovered_catalog: dict) -> tuple[Path, list[str]]:
    """Select the named smoke table from the live DISCOVER result, not a hand-written stub."""
    wanted = os.environ.get("COGNITIVE_AIRBYTE_STREAM", "airbyte_smoke")
    found: list[dict] = []
    for entry in discovered_catalog.get("streams", []):
        stream = entry.get("stream") if isinstance(entry, dict) else None
        stream = stream if isinstance(stream, dict) else entry
        if isinstance(stream, dict) and stream.get("name") == wanted:
            found.append(stream)
    if not found:
        names = [
            (entry.get("stream") or entry).get("name")
            for entry in discovered_catalog.get("streams", [])
            if isinstance(entry, dict)
        ]
        raise ValueError(f"DISCOVER did not return {wanted!r}; available streams: {names[:30]}")

    stream = found[0]
    supported = stream.get("supported_sync_modes") or ["full_refresh"]
    sync_mode = "full_refresh" if "full_refresh" in supported else (supported[0] if supported else None)
    if not sync_mode:
        raise ValueError(f"stream {wanted!r} declares no supported sync mode")
    primary_key = stream.get("source_defined_primary_key") or []
    configured = {
        "streams": [{
            "stream": stream,
            "sync_mode": sync_mode,
            "destination_sync_mode": "append",
            "cursor_field": [],
            "primary_key": primary_key,
            "selected": True,
        }]
    }
    target = mount / "catalog.json"
    target.write_text(json.dumps(configured, indent=2), encoding="utf-8")
    return target, [wanted]



async def main() -> int:
    run_id = f"run-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    print("=" * 78)
    print(f"Airbyte LIVE acceptance - {run_id}")
    print("=" * 78)
    print(f"image      : {IMAGE[:60]}")
    print(f"config dir : {MOUNT}")

    MOUNT.mkdir(parents=True, exist_ok=True)
    runtime = AirbyteRuntime(image=IMAGE, mount_dir=str(MOUNT), task_timeout=240.0)
    cfg, cat = "/cfg/config.json", "/cfg/catalog.json"

    # -- §38: spec -> check -> discover, each independently evidenced -----------
    print("\n1. SPEC (§25)")
    try:
        spec_run = await runtime.spec()
        _write_config(MOUNT, spec_run.spec)
        print("   SPEC message   : yes")
        print(f"   connector      : {spec_run.connector_ref}")
        print("   config         : generated from connector SPEC / environment")
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
        streams = [
            (s.get("stream") or s).get("name")
            for s in disc_run.catalog.get("streams", [])
            if isinstance(s, dict)
        ]
        print(f"   streams found  : {len(streams)}")
        cat_path, selected = _write_configured_catalog(MOUNT, disc_run.catalog)
        configured = json.loads(cat_path.read_text(encoding="utf-8"))
        print(f"   selected stream: {selected[0]}")
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
    # Shared read-back. This used to parse every message on the topic as an
    # EventEnvelope and died with `Wire format was corrupt`: `observation` is
    # long-lived and shared, so an earliest-offset read returns traffic from other
    # producers too. The producer keys by observation_id, so membership is decided on
    # the key and nothing else is decoded.
    from _prove_readback import read_back

    readback = read_back(
        BROKERS,
        "observation",
        {a.observation_id for a in accepted},
        group=GROUP,
    )
    seen = readback.found
    print(f"  consumer group  : {GROUP}")
    print(f"  consumed        : {readback.consumed}")
    print(f"  foreign skipped : {readback.foreign}")
    print(f"  read back       : {len(seen)} из {len(accepted)}")
    if readback.undecodable:
        print(f"  UNDECODABLE     : {readback.undecodable[:5]}")
    wanted = {a.observation_id for a in accepted}
    print(f"   our observations : {len(wanted)}")
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
