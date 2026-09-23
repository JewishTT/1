"""Hermetic EventBus protocol + MemoryEventBus (feature: nervous-system).

The control plane runs on a single deterministic event bus. Phase 1 keeps the
bus in memory (hermetic — tests and local runs never need Redpanda); phase 2
binds the same ``EventBus`` Protocol to a Redpanda adapter
(``docs/architecture/stream-processing.md``).

Bus contract:
- **append-only**: an offset, once assigned, never changes;
- **deterministic offsets**: monotone per-topic counters assigned in publish
  order — same publish sequence ⇒ same offsets;
- **deterministic replay**: ``replay(topic)`` yields records in offset order, so
  replaying ``topic + offset`` rebuilds the identical projection (I-12);
- **I-5 refs-only**: raw blobs are rejected on publish;
- **content-addressed event ids**: ``evt-<sha256(payload)>`` when the envelope
  omits one — consistent with ``domain.stream_events`` (I-11 idempotency).
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterator, Protocol

from domain import enforce_no_blobs
from events.event_envelope_pb2 import EventEnvelope
from events.topics import TOPICS

#: I-5 inline limit for ref-carrying payloads (same as the observation gate).
MAX_INLINE_REFS = 1024


def content_address(payload: bytes) -> str:
    """Deterministic content address, consistent with ``evt-<record_hash>`` (I-11)."""
    return f"evt-{hashlib.sha256(payload).hexdigest()}"


def validate_topic(topic: str) -> None:
    """Catalog gate: the bus only carries catalog topics (sorted-union invariant)."""
    if topic not in TOPICS:
        raise UnknownTopicError(topic)


class UnknownTopicError(KeyError):
    """Raised when a topic is not in the event/topic catalog (topics.py)."""


@dataclass(frozen=True)
class BusRecord:
    """One immutable bus entry at a deterministic ``(topic, offset)``."""

    topic: str
    offset: int
    key: str
    event_id: str
    envelope: bytes  # serialized EventEnvelope

    def parse(self) -> EventEnvelope:
        parsed = EventEnvelope()
        parsed.ParseFromString(self.envelope)
        return parsed


class EventBus(Protocol):
    """Transport-agnostic bus contract (MemoryEventBus, phase-2 Redpanda)."""

    def publish(
        self, topic: str, payload: EventEnvelope | bytes, *, key: str | None = None
    ) -> int: ...

    def consume(
        self, topic: str, from_offset: int = 0, *, limit: int | None = None
    ) -> list[BusRecord]: ...

    def replay(self, topic: str) -> Iterator[BusRecord]: ...

    def head_offset(self, topic: str) -> int: ...


class MemoryEventBus:
    """Append-only in-memory bus with deterministic offsets and replay.

    One logical partition per topic, keyed by ``(topic, offset)``; records are
    appended in publish order and never rewritten — a replay from any offset
    returns the identical ordered records, so projections are rebuildable (I-12).
    """

    def __init__(self) -> None:
        self._logs: dict[str, list[BusRecord]] = defaultdict(list)
        self._offsets: dict[str, int] = defaultdict(lambda: 0)

    def publish(
        self, topic: str, payload: EventEnvelope | bytes, *, key: str | None = None
    ) -> int:
        validate_topic(topic)
        envelope = EventEnvelope()
        if isinstance(payload, EventEnvelope):
            envelope.CopyFrom(payload)
        else:
            envelope.ParseFromString(payload)
        # I-5: Kafka/bus never carries raw blobs — payloads carry refs only.
        enforce_no_blobs(envelope.payload, max_inline=MAX_INLINE_REFS)
        if not envelope.event_id:
            envelope.event_id = content_address(envelope.payload)
        key = key or envelope.event_id
        offset = self._offsets[topic]
        self._logs[topic].append(
            BusRecord(
                topic=topic,
                offset=offset,
                key=key,
                event_id=envelope.event_id,
                envelope=envelope.SerializeToString(),
            )
        )
        self._offsets[topic] += 1
        return offset

    def consume(
        self, topic: str, from_offset: int = 0, *, limit: int | None = None
    ) -> list[BusRecord]:
        validate_topic(topic)
        records = [r for r in self._logs.get(topic, ()) if r.offset >= from_offset]
        return records if limit is None else records[:limit]

    def replay(self, topic: str) -> Iterator[BusRecord]:
        validate_topic(topic)
        yield from list(self._logs.get(topic, ()))

    def head_offset(self, topic: str) -> int:
        validate_topic(topic)
        return self._offsets.get(topic, 0)


__all__ = [
    "BusRecord",
    "EventBus",
    "EventEnvelope",
    "MAX_INLINE_REFS",
    "MemoryEventBus",
    "UnknownTopicError",
    "content_address",
    "validate_topic",
]