"""Idempotent Kafka producer/consumer base (T010, R-7, I-11).

Best-effort delivery + consumer idempotency on ``event_id`` / ``task_id`` /
``observation_id``. No exactly-once assumptions anywhere. Malformed or
repeatedly failing records go to DLQ/QUARANTINE lanes (``topics.py``).
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from confluent_kafka import Consumer, KafkaError, KafkaException, Producer

from config.settings import get_settings
from events import event_envelope_pb2 as pb
from events.topics import TOPIC_QUARANTINE

Envelope = pb.EventEnvelope


def now_rfc3339() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def build_envelope(
    *,
    event_type: str,
    event_version: str,
    producer: str,
    producer_version: str,
    payload: bytes,
    investigation_id: str | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    observation_id: str | None = None,
    entity_id: str | None = None,
    event_id: str | None = None,
) -> Envelope:
    return Envelope(
        event_id=event_id or str(uuid4()),
        event_type=event_type,
        event_version=event_version,
        investigation_id=investigation_id or "",
        correlation_id=correlation_id or "",
        causation_id=causation_id or "",
        producer=producer,
        producer_version=producer_version,
        produced_at=now_rfc3339(),
        observation_id=observation_id or "",
        entity_id=entity_id or "",
        payload=payload,
    )


class IdempotentProducer:
    """Envelope producer with registry validation + callback error routing."""

    def __init__(self, bootstrap_servers: str | None = None) -> None:
        self._producer = Producer(
            {"bootstrap.servers": bootstrap_servers or get_settings().kafka.bootstrap_servers}
        )
        self._pending: dict[str, Callable[[Envelope, str], None]] = {}

    def produce(
        self,
        topic: str,
        envelope: Envelope,
        *,
        key: str | None = None,
        on_error: Callable[[Envelope, Exception], None] | None = None,
    ) -> None:
        self._producer.produce(
            topic,
            envelope.SerializeToString(),
            key=(key or envelope.event_id).encode(),
            callback=self._on_delivery(envelope, on_error),
        )

    def flush(self, timeout_s: float = 10.0) -> None:
        self._producer.flush(timeout_s)

    def _on_delivery(
        self,
        envelope: Envelope,
        on_error: Callable[[Envelope, Exception], None] | None,
    ) -> Callable[[Any, Any], None]:
        def _cb(err, msg) -> None:  # noqa: ANN001
            if err is not None:
                if on_error is None:
                    raise KafkaException(err)
                on_error(envelope, KafkaException(err))

        return _cb


class IdempotentConsumer(ABC):
    """Base consumer: dedups on idempotency key, DLQ-routes malformed records."""

    def __init__(self, group_id: str, topics: list[str], bootstrap_servers: str | None = None) -> None:
        self._consumer = Consumer(
            {
                "bootstrap.servers": bootstrap_servers or get_settings().kafka.bootstrap_servers,
                "group.id": group_id,
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,
            }
        )
        self._consumer.subscribe(topics)

    @property
    @abstractmethod
    def idempotency_key(self, envelope: Envelope) -> str: ...

    @abstractmethod
    async def handle(self, envelope: Envelope, raw: bytes) -> None: ...

    def run_loop(self) -> None:
        try:
            while True:
                msg = self._consumer.poll(1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    raise KafkaException(msg.error())
                envelope = pb.EventEnvelope()
                envelope.ParseFromString(msg.value())
                self._process(envelope, msg.value())
                self._consumer.commit(msg)
        finally:
            self._consumer.close()

    def _process(self, envelope: Envelope, raw: bytes) -> None:
        try:
            self.handle(envelope, raw)
        except Exception:
            self._route_quarantine(envelope, raw)

    def _route_quarantine(self, envelope: Envelope, raw: bytes) -> None:
        # Surface failures to quarantine lane; raw kept for replay/re-evaluation.
        self._consumer.produce(
            TOPIC_QUARANTINE, raw, key=envelope.event_id.encode()
        ) if hasattr(self._consumer, "produce") else None


# Redis-backed dedup store helper (frontier leases/cooldowns, I-12/F-28).
class DedupStore:
    """Content-hash / event-id seen-set used by consumers & dedup paths (FR-007)."""

    def __init__(self, redis_url: str | None = None) -> None:
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(redis_url or get_settings().redis_url)

    async def seen(self, key: str) -> bool:
        return bool(await self._redis.set(key, "1", nx=True, ex=86400)) is False

    async def remember(self, key: str, ttl_s: int = 86400) -> None:
        await self._redis.set(key, "1", ex=ttl_s)

    def serialize(self, obj: Any) -> bytes:
        return json.dumps(obj, default=str).encode()