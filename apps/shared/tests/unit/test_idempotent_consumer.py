"""Feature 024 T019 -- idempotent consumer, after repair.

Each test here fails against the pre-repair ``IdempotentConsumer``:

* ``test_handle_is_actually_awaited``  -- old code created the coroutine and dropped it
* ``test_duplicate_is_delivered_once``  -- old code never called ``idempotency_key``
* ``test_failure_releases_the_claim``   -- old code had no dedup to release
* ``test_failure_without_sink_is_loud`` -- old code swallowed the missing ``produce``

The consumer is built without a live broker: construction bypasses ``Consumer(...)``
and installs the dedup/quarantine wiring directly, so these are hermetic.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from events import event_envelope_pb2 as pb  # noqa: E402
from events.dlq import QuarantineStore  # noqa: E402
from events.kafka import (  # noqa: E402
    Envelope,
    IdempotentConsumer,
    InMemoryDeduplicator,
)


def envelope(event_id: str) -> Envelope:
    return pb.EventEnvelope(event_id=event_id, event_type="observation.created", tenant_id="t1")


def make(handler, *, quarantine=None, failure_publish=None):
    """Build a real IdempotentConsumer subclass without a broker."""

    class _C(IdempotentConsumer):
        def __init__(self):  # noqa: D107 - bypasses Consumer(...)
            self._dedup = InMemoryDeduplicator()
            self._quarantine = quarantine
            self._failure_publish = failure_publish
            self.processed = 0
            self.duplicates = 0
            self.quarantined = 0
            self.seen: list[str] = []

        def idempotency_key(self, envelope: Envelope) -> str:
            return envelope.event_id

        async def handle(self, envelope: Envelope, raw: bytes) -> None:
            self.seen.append(envelope.event_id)
            await handler(envelope, raw)

    return _C()


async def record(_envelope, _raw) -> None:
    return None


def boom(_envelope, _raw) -> None:
    raise RuntimeError("parser exploded")


@pytest.mark.asyncio
async def test_handle_is_actually_awaited():
    """Pre-repair, run_loop called handle() without await: the coroutine was created
    and immediately discarded, so observed state was always empty."""
    c = make(record)
    result = await c._process(envelope("evt-a"), b"{}")
    assert c.seen == ["evt-a"]
    assert result is True
    assert c.processed == 1


@pytest.mark.asyncio
async def test_duplicate_is_delivered_once():
    c = make(record)
    env = envelope("evt-dup")

    assert await c._process(env, b"{}") is True
    assert await c._process(env, b"{}") is False
    assert await c._process(env, b"{}") is False

    assert c.seen == ["evt-dup"]
    assert c.processed == 1
    assert c.duplicates == 2


@pytest.mark.asyncio
async def test_distinct_events_are_not_deduplicated():
    c = make(record)
    for i in range(5):
        assert await c._process(envelope(f"evt-{i}"), b"{}") is True
    assert len(c.seen) == 5
    assert c.duplicates == 0


@pytest.mark.asyncio
async def test_failure_quarantines_and_does_not_commit():
    """A failed record returns None so the caller withholds the commit, and it is
    preserved for replay rather than vanishing."""
    store = QuarantineStore()
    c = make(boom, quarantine=store)

    assert await c._process(envelope("evt-x"), b'{"bad":1}') is None
    assert c.processed == 0
    assert c.quarantined == 1
    assert len(store.list()) == 1
    record_id = store.list()[0]["record_id"]
    assert store.replay(record_id) == b'{"bad":1}'


@pytest.mark.asyncio
async def test_failure_releases_the_claim():
    """A retry after a transient failure must be able to succeed. If the claim were
    retained, the redelivery would be swallowed as a duplicate -- which makes a
    permanent poison-pill look like healthy at-least-once."""
    attempts = {"n": 0}

    async def flaky(_envelope, _raw):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("transient")

    c = make(flaky, quarantine=QuarantineStore())
    env = envelope("evt-retry")

    assert await c._process(env, b"{}") is None
    assert await c._process(env, b"{}") is True
    assert attempts["n"] == 2
    assert c.processed == 1


@pytest.mark.asyncio
async def test_failure_publishes_to_wire_when_a_publisher_is_injected():
    seen: list[tuple] = []
    c = make(boom, failure_publish=lambda topic, raw, key: seen.append((topic, raw, key)))
    assert await c._process(envelope("evt-p"), b"raw") is None
    assert seen and seen[0][1] == b"raw"


@pytest.mark.asyncio
async def test_failure_without_sink_is_loud():
    """No publisher and no local store: raise. Pre-repair this became a silent None,
    which is exactly how failures disappeared."""
    c = make(boom)
    with pytest.raises(RuntimeError, match="parser exploded"):
        await c._process(envelope("evt-loud"), b"raw")


@pytest.mark.asyncio
async def test_deduplicator_claim_is_once():
    d = InMemoryDeduplicator()
    assert await d.claim("k") is True
    assert await d.claim("k") is False
    await d.release("k")
    assert await d.claim("k") is True
