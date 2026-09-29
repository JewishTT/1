"""PROOF: data collection over the event backbone.

Source catalogue -> tasks -> fetch -> ``observation.created`` per page -> Kafka -> consumed
back and matched against what was captured.

The acceptance criterion is not that requests succeeded. It is that an observation produced
from a real source is readable from the broker, keyed, and byte-identical in the fields that
identify it. A green run here means the backbone carries collected data.
"""

import asyncio
import json

from dispatcher.kafka_producer import KafkaProducer, ProducerError, ensure_topics
from events.topics import TOPICS, topic_for
from sources.connector import SourceConnector, plan
from sources.executor import AcquisitionError

TARGET = "example.com"
# A spread across categories, so the proof is not one lucky endpoint.
CATEGORIES = (
    "01. DNS Intelligence",
    "02. IP & Infrastructure",
    "19. Passive DNS & Certificate Monitoring",
)


def consume(topic: str, key: str, timeout_s: float = 25.0) -> list[dict]:
    """Read the topic from the beginning. Returns decoded envelopes.

    ``earliest`` is required, not a convenience: the observations were published before this
    consumer existed, so ``latest`` would position past every one of them and the proof
    would read an empty topic and call it a pass.
    """
    import os
    import time

    from confluent_kafka import Consumer

    consumer = Consumer(
        {
            "bootstrap.servers": ",".join(
                os.environ.get("COGNITIVE_KAFKA_BROKERS", "localhost:9092").split(",")
            ),
            "group.id": f"proof-{os.getpid()}-{int(time.time())}",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([topic])
    out: list[dict] = []
    deadline = time.monotonic() + timeout_s
    try:
        while time.monotonic() < deadline and len(out) < 200:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                continue
            try:
                out.append(json.loads(msg.value()))
            except Exception:
                out.append({"_raw": msg.value()[:200].decode("utf-8", "replace")})
    finally:
        consumer.close()
    return out


async def main() -> int:

    print("=" * 72)
    print("PROOF: COLLECTION OVER THE BACKBONE")
    print("=" * 72)

    print()
    print("1. ТОПИКИ")
    created = ensure_topics(TOPICS)
    obs_topic = topic_for("observation.created")
    print(f"   всего в каталоге : {len(TOPICS)}")
    print(f"   создано сейчас    : {len(created)} {created[:6]}")
    print(f"   observation.created -> {obs_topic}")

    print()
    print("2. ПЛАН СБОРА")
    tasks = plan(TARGET, categories=CATEGORIES)
    print(f"   задач             : {len(tasks)}")
    for t in tasks[:4]:
        print(f"     {t.task_id}  {t.source_name:<28} {t.category[:28]}")

    print()
    print("3. СБОР + ПУБЛИКАЦИЯ")
    connector = SourceConnector()
    producer = KafkaProducer()
    published: list[dict] = []
    try:
        for task in tasks:
            try:
                async for _capture, event in connector.collect(task):
                    result = producer.publish_sync(
                        obs_topic,
                        event,
                        key=task.task_id,
                        event_type="observation.created",
                    )
                    published.append(
                        {
                            "key": task.task_id,
                            "event": event,
                            "delivery": result.to_dict(),
                        }
                    )
                    where = f"{result.topic}[{result.partition}]@{result.offset}"
                    print(
                        f"   OK   {event['source_name']:<26} p{event['page']} "
                        f"{event['byte_length']:>7}B  "
                        f"{event['event_id']}  -> {where}"
                    )
                    break  # one page per source keeps the proof quick
            except AcquisitionError as exc:
                print(f"   FAIL {task.source_name:<26} {exc.code}")
            except ProducerError as exc:
                print(f"   PUB-FAIL {task.source_name:<26} {exc.code}: {exc.message[:60]}")
                return 2
    finally:
        await connector.aclose()

    print()
    print(f"   опубликовано наблюдений: {len(published)}")
    assert published, "nothing was published"

    print()
    print("4. ЧТЕНИЕ ОБРАТНО ИЗ БРОКЕРА")
    sample = published[0]
    got = consume(obs_topic, sample["key"], timeout_s=20.0)
    ours = [g for g in got if g.get("event_id") == sample["event"]["event_id"]]
    print(f"   прочитано сообщений : {len(got)}")
    print(f"   наше по event_id     : {len(ours)}")
    if not ours:
        print("   НАБЛЮДЕНИЕ НЕ НАЙДЕНО В БРОКЕРЕ")
        return 3
    back = ours[0]
    checks = {
        "content_digest": back["content_digest"] == sample["event"]["content_digest"],
        "source_id": back["source_id"] == sample["event"]["source_id"],
        "page": back["page"] == sample["event"]["page"],
        "byte_length": back["byte_length"] == sample["event"]["byte_length"],
    }
    identity_ok = all(checks.values())
    for name, ok in checks.items():
        print(f"   {name:<20} совпал: {ok}")
    print(f"   url                  : {str(back['url'])[:88]}")

    total_bytes = sum(p["event"]["byte_length"] for p in published)
    print()
    print("=" * 72)
    print(f"ДОКАЗАТЕЛЬСТВО: {len(published)} наблюдений, {total_bytes} байт, через Kafka")
    print(f"ИДЕНТИЧНОСТЬ НАБЛЮДЕНИЯ ПОДТВЕРЖДЕНА: {identity_ok}")
    print("=" * 72)
    return 0 if identity_ok else 4


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
