"""API tests: /api/v1/stream (SSE) + /api/v1/publish + review fan-out.

Wire format is verified through the HTTP layer with ``replay_only=true``
(deterministic resync that closes after the backlog); hub delivery semantics
are covered by direct async unit tests.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
_ROOT = Path(__file__).resolve().parents[3]
for _rel in ("science", "interpretation", "bulk-ingestion"):
    sys.path.insert(0, str(_ROOT / _rel))

import pytest
from fastapi.testclient import TestClient

import api.sse as sse_module
from api.main import app
from api.sse import _EventHub


@pytest.fixture
def client() -> TestClient:
    # in-place reset: api.routes.entities.hub shares this same object
    sse_module.hub.__init__()
    return TestClient(app)


def _sse_blocks(response) -> list[dict]:
    raw = list(response.iter_text())
    text = "\n".join(raw)
    blocks: list[dict] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block or block == ": ping":
            continue
        event, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line[len("event: "):]
            elif line.startswith("data: "):
                data = line[len("data: "):]
        blocks.append({"event": event, "data": json.loads(data) if data else None})
    return blocks


def test_empty_payload_rejected(client: TestClient) -> None:
    resp = client.post("/api/v1/publish", json={"event_type": "x", "payload": {}})
    assert resp.status_code == 422


def test_stream_replays_backlog(client: TestClient) -> None:
    client.post(
        "/api/v1/publish",
        json={"event_type": "entity.updated", "payload": {"entity_id": "E1", "n": 1}},
    )
    client.post(
        "/api/v1/publish",
        json={"event_type": "entity.updated", "payload": {"entity_id": "E2", "n": 2}},
    )

    with client.stream("GET", "/api/v1/stream?replay_only=true") as response:
        assert response.status_code == 200
        blocks = _sse_blocks(response)
    assert blocks[0]["event"] == "__resume__"
    assert blocks[0]["data"] == {"replayed": 2}
    assert [b["event"] for b in blocks[1:]] == ["entity.updated", "entity.updated"]
    assert blocks[1]["data"]["entity_id"] == "E1"
    assert blocks[2]["data"]["entity_id"] == "E2"


def test_stream_empty_backlog_replays_nothing(client: TestClient) -> None:
    with client.stream("GET", "/api/v1/stream?replay_only=true") as response:
        blocks = _sse_blocks(response)
    assert blocks[0]["event"] == "__resume__"
    assert blocks[0]["data"] == {"replayed": 0}


def test_review_publishes_entity_updated(client: TestClient) -> None:
    review = client.post(
        "/api/v1/entities/ENT-2001/review",
        json={"decision": "ACCEPT", "reasoning": "smoke", "target_type": "candidate"},
    )
    assert review.status_code == 200

    with client.stream("GET", "/api/v1/stream?replay_only=true") as response:
        blocks = _sse_blocks(response)
    events = [b["event"] for b in blocks]
    assert "entity.updated" in events
    payload = blocks[events.index("entity.updated")]["data"]
    assert payload["entity_id"] == "ENT-2001"
    assert payload["event"] == "review.recorded"


class TestEventHub:
    def test_live_event_delivery(self) -> None:
        async def scenario() -> None:
            hub = _EventHub()
            queue = hub.subscribe()
            assert hub.publish("pipeline.advance", {"batch": 7}) == 1
            event_type, payload = await asyncio.wait_for(queue.get(), timeout=0.5)
            assert (event_type, payload) == ("pipeline.advance", {"batch": 7})

        asyncio.run(scenario())

    def test_order_preserved_via_fifo(self) -> None:
        async def scenario() -> None:
            hub = _EventHub()
            queue = hub.subscribe()
            hub.publish("a", {"n": 1})
            hub.publish("b", {"n": 2})
            first = await asyncio.wait_for(queue.get(), timeout=0.5)
            second = await asyncio.wait_for(queue.get(), timeout=0.5)
            assert [first[0], second[0]] == ["a", "b"]

        asyncio.run(scenario())

    def test_unsubscribed_hub_silent(self) -> None:
        async def scenario() -> None:
            hub = _EventHub()
            queue = hub.subscribe()
            hub.publish("a", {"n": 1})  # delivered before unsubscribe
            first = await asyncio.wait_for(queue.get(), timeout=0.5)
            assert first[0] == "a"
            hub.unsubscribe(queue)
            assert hub.publish("b", {"n": 2}) == 0
            with_event = False
            try:
                await asyncio.wait_for(queue.get(), timeout=0.1)
            except TimeoutError:
                with_event = False
            assert with_event is False  # nothing further delivered

        asyncio.run(scenario())

    def test_backlog_bounded(self) -> None:
        hub = _EventHub()
        for i in range(300):
            hub.publish("spam", {"i": i})
        assert len(hub.backlog()) == 200  # maxlen cap