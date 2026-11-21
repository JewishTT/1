"""Idempotent Kafka producer/consumer base (T010, R-7, I-11).

Best-effort delivery + consumer idempotency on ``event_id`` / ``task_id`` /
``observation_id``. No exactly-once assumptions anywhere. Malformed or
repeatedly failing records go to DLQ/QUARANTINE lanes (``topics.py``).
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from confluent_kafka import Consumer, KafkaError, KafkaException, Producer

from config.kafka import redpanda_consumer_config, redpanda_producer_config
from config.settings import get_settings
from domain.observation_identity import derive_event_id
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
    """Build an envelope.

    ``event_id`` defaults to a *derived* address, not a random one. WP-C T044: this
    used to be ``str(uuid4())``, and a contract test asserted that two builds of the
    same envelope differ — which pinned the defect. Every consumer in the platform
    dedups on ``event_id``; a default that is different on every call makes that
    dedup silently useless for every producer that does not override it. A replay of
    an unchanged event now reproduces its address.

    An explicit ``event_id`` is still honoured, because the gate legitimately mints
    one from §11's six components, which is a stricter material than the default.
    """
    return Envelope(
        event_id=event_id
        or derive_event_id(
            event_type=event_type,
            event_version=event_version,
            producer=producer,
            producer_version=producer_version,
            payload=payload,
            observation_id=observation_id or "",
            entity_id=entity_id or "",
            correlation_id=correlation_id or "",
        ),
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
        # Redpanda tuning is deliberately conservative and protocol-compatible.
        # Durable semantics (acks/idempotence) take precedence over raw throughput.
        self._producer = Producer(
            self._producer_config(
                bootstrap_servers or get_settings().kafka.bootstrap_servers
            )
        )
        # librdkafka delivery callbacks run during poll/flush. Capture failures
        # here because raising inside a callback is not propagated to the caller.
        self._delivery_errors: list[str] = []

    @staticmethod
    def _producer_config(bootstrap_servers: str) -> dict[str, Any]:
        return redpanda_producer_config(bootstrap_servers, compression="zstd")

    def produce(
        self,
        topic: str,
        envelope: Envelope,
        *,
        key: str | None = None,
        on_error: Callable[[Envelope, Exception], None] | None = None,
    ) -> None:
        payload = envelope.SerializeToString()
        message_key = (key or envelope.event_id).encode()
        callback = self._on_delivery(envelope, on_error)
        # A bounded wait applies backpressure instead of losing events or growing
        # an unbounded application-side queue when broker throughput falls behind.
        deadline = time.monotonic() + 10.0
        while True:
            try:
                self._producer.produce(topic, payload, key=message_key, callback=callback)
                self._producer.poll(0)
                return
            except BufferError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Redpanda producer queue remained full for 10 seconds")
                self._producer.poll(0.1)

    def flush(self, timeout_s: float = 10.0) -> None:
        outstanding = self._producer.flush(timeout_s)
        if outstanding:
            raise TimeoutError(
                f"Redpanda producer flush timed out with {outstanding} message(s) pending"
            )
        if self._delivery_errors:
            failures = self._delivery_errors
            self._delivery_errors = []
            raise RuntimeError("Redpanda delivery failure(s): " + "; ".join(failures))

    def _on_delivery(
        self,
        envelope: Envelope,
        on_error: Callable[[Envelope, Exception], None] | None,
    ) -> Callable[[Any, Any], None]:
        def _cb(err, msg) -> None:  # noqa: ANN001
            if err is None:
                return
            failure = KafkaException(err)
            self._delivery_errors.append(f"{envelope.event_id}: {failure}")
            if on_error is not None:
                try:
                    on_error(envelope, failure)
                except Exception as callback_error:
                    self._delivery_errors.append(
                        f"{envelope.event_id}: error handler failed: {callback_error}"
                    )
        return _cb
)