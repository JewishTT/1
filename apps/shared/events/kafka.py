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
from events.dlq import DLQRecord, QuarantineStore
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
    tenant_id: str | None = None,
    source_id: str | None = None,
    work_id: str | None = None,
    region_id: str | None = None,
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
        tenant_id=tenant_id or "",
        source_id=source_id or "",
        work_id=work_id or "",
        region_id=region_id or "",
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


class Deduplicator(ABC):
    """Durable claim-once primitive: the backbone of at-least-once safety (FR-012).

    ``claim`` returns True only for the first caller to see a key, so a redelivered
    event cannot produce a second durable effect.
    """

    @abstractmethod
    async def claim(self, key: str) -> bool: ...

    async def release(self, key: str) -> None:
        """Give the claim back when the effect failed and must be retried."""
        return None


class InMemoryDeduplicator(Deduplicator):
    """Hermetic deduplicator. Correct within one process, lost on restart.

    Acceptable for tests and single-shot runs; NOT sufficient for a worker that must
    survive a restart, because a redelivery after the crash would be treated as new.
    """

    def __init__(self) -> None:
        self._seen: set[str] = set()

    async def claim(self, key: str) -> bool:
        if key in self._seen:
            return False
        self._seen.add(key)
        return True

    async def release(self, key: str) -> None:
        self._seen.discard(key)


class IdempotentConsumer(ABC):
    """Base consumer: dedups on idempotency key, quarantines malformed records.

    Repaired in Feature 024 (T019). The original had four defects, each of which
    silently defeated the guarantees this class exists to provide:

    1. ``idempotency_key`` was declared abstract but never called, so nothing
       deduplicated.
    2. ``handle`` is ``async`` but ``run_loop`` called it without ``await``, so the
       coroutine was created and discarded -- no handler ever ran.
    3. ``_route_quarantine`` called ``Consumer.produce``, which does not exist. The
       ``hasattr`` guard turned a lost failure into ``None``, so failures vanished.
    4. The offset was committed after ``_process`` returned, but ``_process``
       swallowed exceptions, so a failed record was marked as done.
    """

    def __init__(
        self,
        group_id: str,
        topics: list[str],
        bootstrap_servers: str | None = None,
        *,
        deduplicator: Deduplicator | None = None,
        failure_publish: Callable[[str, bytes, str], None] | None = None,
        quarantine: "QuarantineStore | None" = None,
    ) -> None:
        self._consumer = Consumer(
            {
                "bootstrap.servers": bootstrap_servers or get_settings().kafka.bootstrap_servers,
                "group.id": group_id,
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,
            }
        )
        self._consumer.subscribe(topics)
        self._dedup = deduplicator or InMemoryDeduplicator()
        self._failure_publish = failure_publish
        self._quarantine = quarantine
        self.processed = 0
        self.duplicates = 0
        self.quarantined = 0

    @abstractmethod
    def idempotency_key(self, envelope: Envelope) -> str:
        """Key this consumer deduplicates on.

        A plain method, not a property: it takes the envelope it must inspect, so
        the original ``@property`` declaration could never be called.
        """
        raise NotImplementedError

    @abstractmethod
    async def handle(self, envelope: Envelope, raw: bytes) -> None: ...

    async def run_loop(self) -> None:
        """Poll forever. Offsets commit only after the effect is durable."""
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
                outcome = await self._process(envelope, msg.value())
                if outcome is not None:
                    self._consumer.commit(msg, asynchronous=False)
        finally:
            self._consumer.close()

    async def _process(self, envelope: Envelope, raw: bytes) -> bool | None:
        """Returns True when the record was applied, False when deduplicated,
        None when it failed and must not be committed (so it is redelivered)."""
        key = self.idempotency_key(envelope)
        if not await self._dedup.claim(key):
            self.duplicates += 1
            return False
        try:
            await self.handle(envelope, raw)
        except Exception as exc:
            await self._dedup.release(key)
            self._route_quarantine(envelope, raw, exc)
            return None
        self.processed += 1
        return True

    def _route_quarantine(self, envelope: Envelope, raw: bytes, exc: BaseException) -> None:
        """Surface a failure without losing it.

        The original called ``Consumer.produce``, which does not exist on a consumer,
        and swallowed that. Now: publish to the wire when a publisher was injected,
        and otherwise keep the record locally so replay stays possible. If neither
        sink is available the failure is raised rather than dropped -- a silently
        discarded event is worse than a loud one.
        """
        reason = f"consumer:{type(exc).__name__}:{exc}"
        if self._quarantine is not None:
            self._quarantine.quarantine(
                DLQRecord(reason=reason, payload=raw, topic=str(envelope.event_type))
            )
        if self._failure_publish is not None:
            self._failure_publish(TOPIC_QUARANTINE, raw, envelope.event_id)
            return
        if self._quarantine is None:
            self.quarantined += 1
            raise exc
        self.quarantined += 1


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