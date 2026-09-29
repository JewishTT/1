"""W4: the loop closes. Dispatcher → Kafka-shaped request → worker → observation.

Two tests, deliberately different in kind, because they prove different things:

``test_the_loop_closes_hermetically``
    Real :class:`Dispatcher`, real :class:`SourceConnector`, real worker — with
    the transport and the broker substituted. This is the one that must always
    run: it pins the wiring (a request really does carry a query; a worker
    really does publish per page) without depending on anyone's network.

``test_the_loop_closes_over_the_live_broker`` (in ``test_live_loop.py``)
    The same circle with a real broker and a real source. Marked separately
    because it needs a running Kafka and working egress; it proves the
    *acknowledgement* claim, which no in-memory double can.

Nothing here stubs the Dispatcher. The point of W1 is that the request a worker
receives is the one the scheduler actually emitted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))

import pytest
from adapters.registry import REGISTRY
from dispatcher.plan_driver import PlanDispatcher
from dispatcher.scheduler import Dispatcher
from events.topics import topic_for
from sources.connector import AcquisitionTask
from worker_acquisition import AcquisitionWorker, RequestParser

pytestmark = pytest.mark.integration

# The scripted transport and the scripted definition are the same fixtures the
# worker's own unit tests use, imported rather than restated: a second copy is a
# second definition of what a fake source is.
from test_acquisition_worker import (  # noqa: E402
    Collector,
    FakeTransport,
    make_definition,
)


@pytest.fixture(autouse=True)
def _registry():
    saved = dict(REGISTRY._sources)
    REGISTRY._sources.clear()
    yield
    REGISTRY._sources.clear()
    REGISTRY._sources.update(saved)


class RecordingProducer:
    """A producer that records what crossed it and acknowledges a fixed offset.

    Stands in for the broker only. The envelope is the scheduler's own, byte for
    byte, so what the worker parses here is what a real consumer would parse.
    """

    def __init__(self) -> None:
        self.published: list[tuple[str, object, str | None]] = []
        self._acked: list[object] = []
        self._offset = 100

    def produce(self, topic: str, envelope, *, key: str | None = None) -> None:
        self.published.append((topic, envelope, key))
        self._offset += 1
        self._acked.append(_Delivery(topic, 0, self._offset, key or ""))

    def flush(self, timeout: float = 10.0) -> int:
        return 0

    def drain(self):
        out = tuple(self._acked)
        self._acked.clear()
        return out


class _Delivery:
    def __init__(self, topic, partition, offset, key) -> None:
        self.topic = topic
        self.partition = partition
        self.offset = offset
        self.key = key
        self.event_type = ""


def test_the_loop_closes_hermetically() -> None:
    """plan → dispatch → request → fetch (all pages) → observation, with no network."""
    from adapters.registry import register
    from sources.catalogue import Pagination

    register("web", execution_class="http", capabilities={"http"})

    definition = make_definition(
        source_id="SRC-loop",
        name="loop_source",
        tool={"url": "https://example.test/search?q={query}&page=1"},
        pagination=Pagination(strategy="page", param="page", page_size=1, max_pages=2),
    )
    transport = FakeTransport([(200, b"page one"), (200, b"page two")])

    # --- W1: the real dispatcher emits a real request -----------------------
    producer = RecordingProducer()
    task = AcquisitionTask(
        task_id="TSK-loop",
        source_id="SRC-loop",
        source_name="loop_source",
        query="acme corp",
        category="search",
        tenant_id="ten-1",
        investigation_id="INV-1",
    )
    records = PlanDispatcher(
        dispatcher=Dispatcher(producer=producer), producer=producer
    ).dispatch([task])

    assert len(records) == 1
    assert records[0].published is True
    assert records[0].offset > 0, "the request must be acknowledged, not fire-and-forget"

    request_topic, request_envelope, request_key = producer.published[0]
    assert request_topic == topic_for("acquisition.request")
    assert request_key == "TSK-loop"

    # --- W2: the worker consumes it and publishes per page ------------------
    observations: list[tuple[str, dict, str]] = []
    collector = Collector(definition, transport)
    worker = AcquisitionWorker(
        connector=collector,
        publish=lambda topic, event, *, key="": observations.append((topic, event, key)),
    )
    result = await_worker(worker, request_envelope)

    assert result.failures == (), "the loop must not dead-letter a healthy source"
    assert len(observations) == 2, "both pages become observations"
    assert [e["page"] for _t, e, _k in observations] == [1, 2]
    assert all(t == topic_for("observation.created") for t, _e, _k in observations)
    assert all(e["task_id"] == "TSK-loop" for _t, e, _k in observations)
    assert all(e["query"] == "acme corp" for _t, e, _k in observations)
    assert len({e["event_id"] for _t, e, _k in observations}) == 2

    # The observation is content-addressed, so its id is recomputable from the
    # record alone — the property replay idempotency rests on.
    from sources.connector import observation_id

    for _topic, event, _key in observations:
        expected = observation_id(
            event["source_id"], event["query"], event["page"], event["content_digest"]
        )
        assert event["event_id"] == expected

    # --- the circle replays as a fixed point --------------------------------
    replay = await_worker(worker, request_envelope)
    assert replay.superseded is True
    assert len(observations) == 2, "a replay must not add a second copy"


def await_worker(worker: AcquisitionWorker, envelope) -> object:
    """Run one request through the worker from synchronous test code."""
    import asyncio

    return asyncio.run(worker.handle(envelope))


def test_the_request_the_worker_parses_is_the_scheduler_s_own() -> None:
    """No hand-built request: the worker is driven by the dispatcher's output."""
    from adapters.registry import register

    register("web", execution_class="http", capabilities={"http"})
    producer = RecordingProducer()
    task = AcquisitionTask(
        task_id="TSK-parse",
        source_id="SRC-parse",
        source_name="s",
        query="globex",
        category="search",
        tenant_id="ten-9",
        investigation_id="INV-9",
    )
    PlanDispatcher(dispatcher=Dispatcher(producer=producer), producer=producer).dispatch([task])
    _topic, envelope, _key = producer.published[0]

    parsed = RequestParser().parse(envelope)
    assert parsed.task_id == "TSK-parse"
    assert parsed.source_id == "SRC-parse"
    assert parsed.query == "globex"
    assert parsed.tenant_id == "ten-9"
    assert parsed.investigation_id == "INV-9"
    assert json.loads(envelope.payload)["verdict"] == "dispatch"
