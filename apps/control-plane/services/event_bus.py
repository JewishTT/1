"""Control-plane facade over the shared deterministic EventBus (nervous-system).

Composition root for the control plane's event surface:

- one shared, hermetic bus by default (``MemoryEventBus`` — tests and local
  runs never need Redpanda);
- a back-compatible ``produce(topic, envelope, key)`` surface — the same shape
  as ``events.kafka.IdempotentProducer`` and the shared ``Producer`` protocols —
  so the dispatcher / observation gate / review services emit unchanged;
- ``run_loop(bus, handlers, topics)``: consume each topic from its persisted
  cursor and dispatch records to handlers **in registration order** — the
  deterministic (single-consumer) mirror of a Kafka consumer group.

Replay guarantee: records are dispatched per-topic in offset order; a cursor
advances only after every handler for the record returns. Re-running the loop
from ``offset + 1`` rebuilds the identical downstream state (I-12).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol

from events.bus import BusRecord, EventBus, MemoryEventBus
from events.event_envelope_pb2 import EventEnvelope

BusHandler = Callable[[BusRecord], Awaitable[None]]
Handlers = Mapping[str, list[BusHandler]]


class StopEvent(Protocol):
    """Minimal stop handshake (asyncio.Event / threading.Event both satisfy)."""

    def is_set(self) -> bool: ...

    def set(self) -> None: ...


class EventBusFacade:
    """Shared bus + compat emit surface + ordered consumer-handler registry."""

    def __init__(self, bus: EventBus | None = None) -> None:
        self._bus: EventBus = bus if bus is not None else MemoryEventBus()
        self._handlers: dict[str, list[BusHandler]] = {}

    @property
    def bus(self) -> EventBus:
        return self._bus

    def produce(self, topic: str, envelope: EventEnvelope, *, key: str | None = None) -> int:
        """Back-compatible emit surface (Producer protocol shape) → offset."""
        return self._bus.publish(topic, envelope, key=key)

    def publish(self, topic: str, payload: EventEnvelope | bytes, *, key: str | None = None) -> int:
        return self._bus.publish(topic, payload, key=key)

    def register(self, topic: str, handler: BusHandler) -> None:
        """Register a consumer; handlers run in registration order per topic."""
        self._handlers.setdefault(topic, []).append(handler)

    async def run(
        self, *, topics: list[str] | None = None, stop_event: StopEvent | None = None
    ) -> dict[str, int]:
        return await run_loop(
            self._bus,
            self._handlers,
            list(topics or self._handlers),
            stop_event=stop_event,
        )


async def run_loop(
    bus: EventBus,
    handlers: Handlers,
    topics: list[str],
    *,
    stop_event: object | None = None,
    poll_interval: float = 0.01,
) -> dict[str, int]:
    """Consume ``topics`` from each cursor and dispatch in registration order.

    Handlers is an ordered mapping (insertion order in a plain dict): for every
    record, handlers of the record's topic run in registration order — the
    deterministic consumer-group equivalent. Cursors start at 0 (replay from
    the head) and may be seeded from a previous run for resumable consumers.
    Returns the final per-topic cursors.
    """
    cursors: dict[str, int] = {topic: 0 for topic in topics}
    while True:
        if stop_event is not None and stop_event.is_set():  # type: ignore[attr-defined]
            break
        pending = False
        for topic in topics:
            for record in bus.consume(topic, cursors[topic]):
                if stop_event is not None and stop_event.is_set():  # type: ignore[attr-defined]
                    return cursors
                pending = True
                for handler in handlers.get(topic, ()):
                    await handler(record)
                cursors[topic] = record.offset + 1
        if not pending:
            await asyncio.sleep(poll_interval)
    return cursors


_default_facade: EventBusFacade | None = None


def get_bus_facade() -> EventBusFacade:
    """Process-wide shared facade — the hermetic default for control-plane emits."""
    global _default_facade
    if _default_facade is None:
        _default_facade = EventBusFacade()
    return _default_facade


__all__ = [
    "BusHandler",
    "EventBusFacade",
    "Handlers",
    "get_bus_facade",
    "run_loop",
]