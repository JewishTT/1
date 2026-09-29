"""Kafka producer for the acquisition stream plane.

The event vocabulary, the topic set and the ``Producer`` protocol all existed before this
module — ``events.topics.EVENT_CATALOG`` names every stage of the pipeline and
``dispatcher.scheduler`` emits ``acquisition.request`` against it. What was missing was a
concrete producer, so the backbone had a contract and no traffic.

Three properties this module is responsible for:

Topics exist before anything is published
    Auto-creation is off in a durable backbone, so a producer that publishes to an
    undeclared topic either blocks or drops. :func:`ensure_topics` declares the full
    catalog with the configured partition count and replication factor, and reports what it
    created.

A key is mandatory on acquisition traffic
    ``acquisition.request`` is keyed by ``task_id`` so every event for one task lands on one
    partition and stays ordered. The scheduler already supplies the key; this module refuses
    to publish without one rather than falling back to round-robin, which would silently
    break the ordering guarantee for a whole task.

Publication is acknowledged, not fire-and-forget
    ``produce`` is asynchronous, so a caller that never waits believes it published what it
    did not. :meth:`KafkaProducer.flush` is explicit and :meth:`KafkaProducer.publish_sync`
    blocks on the delivery report, so a proof of collection is a proof that the bytes
    reached the broker.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

BROKER_ENV = "COGNITIVE_KAFKA_BROKERS"
DEFAULT_BROKER = "localhost:9092"
DEFAULT_PARTITIONS = 3
DEFAULT_REPLICATION = 1
PUBLISH_TIMEOUT_S = 15.0


def brokers() -> list[str]:
    import os

    raw = os.environ.get(BROKER_ENV, DEFAULT_BROKER)
    return [b.strip() for b in raw.split(",") if b.strip()]


class ProducerError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class DeliveryResult:
    """What the broker actually acknowledged."""

    topic: str
    partition: int
    offset: int
    key: str
    event_type: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "partition": self.partition,
            "offset": self.offset,
            "key": self.key,
            "event_type": self.event_type,
        }


def ensure_topics(
    topics: Sequence[str],
    *,
    partitions: int = DEFAULT_PARTITIONS,
    replication: int = DEFAULT_REPLICATION,
) -> list[str]:
    """Declare ``topics`` if absent. Returns the topics that had to be created."""
    from confluent_kafka.admin import AdminClient, NewTopic

    admin = AdminClient({"bootstrap.servers": ",".join(brokers())})
    existing = set(admin.list_topics(timeout=10).topics)
    missing = [t for t in topics if t not in existing]
    if not missing:
        return []
    futures = admin.create_topics(
        [NewTopic(t, num_partitions=partitions, replication_factor=replication) for t in missing]
    )
    for topic, future in futures.items():
        try:
            future.result(timeout=20)
        except Exception as exc:
            if "already exists" in str(exc).lower():
                continue
            raise ProducerError(
                "topic_create_failed", f"{topic}: {type(exc).__name__}: {exc}"
            ) from exc
    return sorted(missing)


def envelope_bytes(envelope: Any) -> bytes:
    """Serialise an event envelope, whatever shape it arrives in.

    The scheduler emits a protobuf ``events.EventEnvelope`` (built by
    ``events.kafka.build_envelope``), so the wire form is
    ``SerializeToString()`` — *not* a JSON mapping. Protobuf is tried first
    because a protobuf message also satisfies the duck-typed branches below
    only by accident, and a protobuf message serialised as JSON is not
    something a consumer can parse.
    """
    if isinstance(envelope, (bytes, bytearray)):
        return bytes(envelope)
    if isinstance(envelope, str):
        return envelope.encode("utf-8")
    if isinstance(envelope, Mapping):
        return json.dumps(envelope, sort_keys=True, ensure_ascii=False, default=str).encode(
            "utf-8"
        )
    serialize = getattr(envelope, "SerializeToString", None)
    if callable(serialize):
        return bytes(serialize())
    for attr in ("to_dict", "as_dict", "as_event_payload"):
        fn = getattr(envelope, attr, None)
        if callable(fn):
            return envelope_bytes(fn())
    raise ProducerError(
        "unserialisable_envelope", f"{type(envelope).__name__} has no dict form"
    )


class KafkaProducer:
    """A concrete :class:`dispatcher.scheduler.Producer`.

    Satisfies the protocol the scheduler already depends on, and adds the acknowledgement
    step that makes a publication provable.
    """

    def __init__(self, *, client: Any | None = None) -> None:
        if client is not None:
            self._client = client
        else:
            from confluent_kafka import Producer as _Producer

            self._client = _Producer(
                {
                    "bootstrap.servers": ",".join(brokers()),
                    "enable.idempotence": True,
                    "acks": "all",
                    "compression.type": "snappy",
                }
            )
        self._acked: list[DeliveryResult] = []

    @property
    def client(self) -> Any:
        return self._client

    def produce(self, topic: str, envelope: Any, *, key: str | None = None) -> None:
        """Publish to ``topic`` under ``key``. Asynchronous, like the protocol expects."""
        if not key:
            raise ProducerError(
                "missing_key",
                f"refusing to publish to {topic} without a key: unkeyed traffic would "
                "break per-task ordering",
            )
        self._client.produce(
            topic, value=envelope_bytes(envelope), key=key, on_delivery=self._on_delivery
        )

    def publish_sync(
        self, topic: str, envelope: Any, *, key: str, event_type: str = ""
    ) -> DeliveryResult:
        """Publish and block until the broker acknowledges. Returns what it acknowledged."""
        self.produce(topic, envelope, key=key)
        remaining = self.flush(PUBLISH_TIMEOUT_S)
        if remaining:
            raise ProducerError(
                "delivery_timeout",
                f"{remaining} message(s) undelivered to {topic} after {PUBLISH_TIMEOUT_S}s",
            )
        if not self._acked:
            raise ProducerError("no_delivery_report", f"no delivery report for {topic}")
        result = self._acked[-1]
        if event_type:
            object.__setattr__(result, "event_type", event_type)
        return result

    def flush(self, timeout: float = 10.0) -> int:
        self._acked.clear()
        remaining = self._client.flush(timeout)
        return int(remaining or 0)

    def drain(self) -> tuple[DeliveryResult, ...]:
        """Every delivery the broker acknowledged since the last drain.

        ``produce`` is the async surface the scheduler's ``Producer`` protocol
        declares, so a caller that drives the Dispatcher has no synchronous
        return value to read — the acknowledgement arrives in a delivery
        callback. This is where those acknowledgements become visible, which is
        what makes "the request reached the broker" checkable rather than
        assumed. Draining rather than reading in place keeps a caller from
        re-counting an offset it already consumed.
        """
        acked = tuple(self._acked)
        self._acked.clear()
        return acked

    def _on_delivery(self, err: Any, msg: Any) -> None:
        if err is not None:
            return
        self._acked.append(
            DeliveryResult(
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset(),
                key=(msg.key() or b"").decode("utf-8", "replace"),
                event_type="",
            )
        )

    def poll(self, timeout: float = 0.0) -> int:
        """Drain delivery callbacks. The confluent client requires this to be called."""
        return int(self._client.poll(timeout) or 0)
