"""Server-Sent-Events hub + streaming endpoint (UI reactivity).

The pipeline writes to the catalog and then calls ``hub.publish(...)``; every
connected browser replays a bounded backlog and then live events. Event wire
format (one SSE event per publish):

    event: <event_type>
    data: {"typed": json}

A connection may race events produced after replay but before the listener is
registered — the backlog is bounded (``_MAX_BACKLOG``) and replay is
best-effort; the platform publishes every mutation so a missed event is not
data loss, just a slightly stale view (eventual consistency is acceptable for
the UI; the catalog remains the source of truth, I-12).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections import deque
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

router = APIRouter(prefix="/api/v1", tags=["realtime"])

_MAX_BACKLOG = 200
_HEARTBEAT_SECONDS = 15.0


class PublishBody(BaseModel):
    event_type: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)


class _EventHub:
    def __init__(self) -> None:
        self._backlog: deque[tuple[str, dict[str, Any]]] = deque(maxlen=_MAX_BACKLOG)
        self._subscribers: set[asyncio.Queue[tuple[str, dict[str, Any]]]] = set()

    def publish(self, event_type: str, payload: dict[str, Any]) -> int:
        """Fan-out one event to every live subscriber; safe from any context."""
        self._backlog.append((event_type, payload))
        for queue in list(self._subscribers):
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait((event_type, payload))
        return len(self._subscribers)

    def backlog(self) -> list[tuple[str, dict[str, Any]]]:
        return list(self._backlog)

    def subscribe(self) -> asyncio.Queue[tuple[str, dict[str, Any]]]:
        queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue(maxsize=_MAX_BACKLOG)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[tuple[str, dict[str, Any]]]) -> None:
        self._subscribers.discard(queue)


hub = _EventHub()


def _render(event_type: str, payload: dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


@router.get("/stream", response_class=StreamingResponse)
async def stream(request: Request, replay_only: bool = False) -> AsyncIterator[str]:
    """SSE stream: bounded backlog replay -> live events -> heartbeats.

    ``replay_only`` re-emits the backlog and closes (deterministic resync for
    test clients; browsers normally leave it off for the live channel).
    """
    queue = hub.subscribe()
    try:
        events = hub.backlog()
        yield f"event: __resume__\ndata: {{\"replayed\": {len(events)}}}\n\n"
        for event_type, payload in events:
            yield _render(event_type, payload)
        if replay_only:
            return
        while True:
            if await request.is_disconnected():
                return
            try:
                event_type, payload = await asyncio.wait_for(
                    queue.get(), timeout=_HEARTBEAT_SECONDS
                )
            except TimeoutError:
                yield ": ping\n\n"
            else:
                yield _render(event_type, payload)
            if await request.is_disconnected():
                return
    finally:
        hub.unsubscribe(queue)


@router.post("/publish")
async def publish(body: PublishBody) -> dict[str, Any]:
    if not body.payload:
        raise HTTPException(status_code=422, detail="payload must be a non-empty object")
    delivered = hub.publish(body.event_type, body.payload)
    return {"published": True, "delivered": delivered}


__all__ = ["hub", "publish", "router", "stream"]