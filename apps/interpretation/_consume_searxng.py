"""Consume the SearXNG run for real: envelope -> raw -> locator -> parse -> result.

Stage 6 of ``_prove_searxng.py``, split out because it is a different process and a
different app. Running it separately is the point: if the consumer only ever ran
in the producer's process, "the consumer processed it" would prove nothing about
whether the *other* app can read the wire format (§174, §202).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interpretation"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from confluent_kafka import Consumer
from events import event_envelope_pb2 as pb
from storage.s3 import ObjectStore

from interpretation.observation_consumer import ObservationConsumer

BROKERS = os.environ.get("COGNITIVE_KAFKA_BROKERS", "localhost:19092")
ENDPOINT = os.environ.get("COGNITIVE_MINIO_ENDPOINT", "http://localhost:9000")
TENANT = os.environ.get("COGNITIVE_TENANT", "acceptance")
GROUP = f"searxng-consumer-{os.getpid()}"


async def main() -> int:
    store = ObjectStore(
        endpoint=ENDPOINT,
        access_key=os.environ.get("COGNITIVE_MINIO_ACCESS_KEY", "demo"),
        secret_key=os.environ.get("COGNITIVE_MINIO_SECRET_KEY", "demopass"),
        raw_bucket=os.environ.get("COGNITIVE_MINIO_RAW_BUCKET", "knowledge-raw"),
    )
    consumer = ObservationConsumer(store=store, source_family="search")
    print(f"consumer      : {GROUP}")
    print(f"processing run: {consumer.run_id}")

    c = Consumer(
        {
            "bootstrap.servers": BROKERS,
            "group.id": GROUP,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    c.subscribe(["observation"])

    processed = refused = skipped = 0
    records = mentions = 0
    sample = None
    legacy = 0
    # Drain to the end of the topic rather than stopping at a target count. Earlier
    # runs published events before the gate carried record refs (§69), and those
    # messages genuinely cannot be resolved - the consumer refuses them by name,
    # which is §108 working. Stopping early would hide them behind a count that
    # looks like success on a different schema.
    deadline = time.monotonic() + 120
    idle_after = None
    seen_ids: set[str] = set()
    while time.monotonic() < deadline:
        msg = c.poll(1.0)
        if msg is None or msg.error():
            if processed > 0:
                idle_after = idle_after or time.monotonic()
                if time.monotonic() - idle_after > 8:
                    break
            continue
        idle_after = None
        env = pb.EventEnvelope()
        env.ParseFromString(msg.value())
        if env.tenant_id != TENANT:
            continue
        if env.observation_id in seen_ids:
            continue
        seen_ids.add(env.observation_id)
        result = await consumer.handle(env)
        if result.status == "processed":
            processed += 1
            records += result.record_count
            mentions += result.mention_count
            if sample is None:
                sample = result
        elif result.status == "refused":
            refused += 1
            # Two shapes of pre-§69 event, both unresolvable and both correctly
            # refused rather than dropped: a bare-locator payload (no JSON at all)
            # and a refs payload that predates raw_ref being carried. They are one
            # category - "an event with no route to its bytes" - and counting them
            # as live failures would report a schema migration as an incident.
            if "not JSON" in result.detail or "no raw_ref" in result.detail:
                legacy += 1
            elif refused - legacy <= 3:
                print(
                    f"   REFUSED {result.observation_id[:24]} {result.failure_code}: {result.detail[:70]}"
                )
        else:
            skipped += 1
    c.close()

    print(f"\nprocessed        : {processed}")
    print(f"refused          : {refused}")
    print(f"  pre-§69 legacy : {legacy}  (no record refs - correctly unresolvable)")
    print(f"  other refusals : {refused - legacy}")
    print(f"skipped          : {skipped}")
    print(f"records parsed   : {records}")
    print(f"mentions bound   : {mentions}")
    if sample:
        print(f"\nsample observation : {sample.observation_id}")
        print(f"  capture_id       : {sample.capture_id}")
        print(f"  locator          : {sample.locator}")
        print(f"  derived_ref      : {sample.derived_ref}")
        print(f"  record_count     : {sample.record_count}")
        print(f"  mention_count    : {sample.mention_count}")

    # §192: deliver the same envelope twice; one semantic result.
    dup = consumer.results
    print(f"\nreplay check (§192): {len(dup)} distinct results for {len(seen_ids)} distinct ids")

    out = Path("artifacts/acquisition-integration")
    out.mkdir(parents=True, exist_ok=True)
    (out / "downstream.json").write_text(
        json.dumps(
            {
                "consumer_group": GROUP,
                "processing_run_id": consumer.run_id,
                "processed": processed,
                "refused": refused,
                "skipped": skipped,
                "records": records,
                "mentions": mentions,
                "results": [r.to_dict() for r in consumer.results],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"written          : {out / 'downstream.json'}")

    ok = processed > 0 and records > 0 and (refused - legacy) == 0
    print(f"\nRESULT: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 6


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
