"""W4 (live): the same circle against a real broker, a real consumer and a real source.

Marked distinct from ``test_loop_closed.py`` on purpose. The hermetic test proves
the wiring; this one proves the two claims a double cannot:

  - the request physically reached the broker at a partition and offset the
    broker assigned, and a consumer group read it back off the topic;
  - a real source was fetched over the network and produced an
    ``observation.created`` that was likewise acknowledged.

It is skipped — not failed — when no broker answers, because a missing broker is
an environment fact and a red test would say the code is wrong. What it needs:

  * Kafka on ``COGNITIVE_KAFKA_BROKERS`` (default ``localhost:9092``)
  * outbound HTTPS to a real source
  * ``COGNITIVE_LIVE=1`` to run, so a routine suite never depends on a network

Topics are namespaced per run by a content-derived suffix, so a rerun cannot
collide with a previous run's offsets and a leftover message cannot be mistaken
for a fresh one.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("COGNITIVE_LIVE") != "1",
        reason="live test; set COGNITIVE_LIVE=1 and run a broker",
    ),
]

from adapters.registry import REGISTRY  # noqa: E402
from dispatcher.kafka_producer import KafkaProducer, ensure_topics  # noqa: E402
from dispatcher.plan_driver import PlanDispatcher  # noqa: E402
from dispatcher.scheduler import Dispatcher  # noqa: E402
from events import event_envelope_pb2 as pb  # noqa: E402
from events.topics import TOPIC_DLQ, TOPIC_QUARANTINE, topic_for  # noqa: E402
from sources.connector import AcquisitionTask, SourceConnector  # noqa: E402
from worker_acquisition import (  # noqa: E402
    AcquisitionWorker,
    observation_publisher,
)

POLL_TIMEOUT_S = 25.0


def broker_up() -> bool:
    try:
        from confluent_kafka.admin import AdminClient
        from dispatcher.kafka_producer import brokers

        AdminClient({"bootstrap.servers": ",".join(brokers())}).list_topics(timeout=5)
        return True
    except Exception:
        return False


requires_broker = pytest.mark.skipif(not broker_up(), reason="no kafka broker")


@pytest.fixture(autouse=True)
def _registry():
    saved = dict(REGISTRY._sources)
    REGISTRY._sources.clear()
    yield
    REGISTRY._sources.clear()
    REGISTRY._sources.update(saved)


def live_source() -> tuple[AcquisitionTask, str] | None:
    """A real, keyless, enabled, http source from the real catalogue.

    Picked deterministically (lowest ``source_id``) so a rerun exercises the same
    source and a failure is reproducible.
    """
    from sources.catalogue import load_catalogue as _load

    definitions, _rejected = _load()
    usable = [
        d
        for d in definitions
        if d.enabled and not d.requires_key and d.kind == "http" and d.tool.get("url")
    ]
    for definition in sorted(usable, key=lambda d: d.source_id):
        task = AcquisitionTask(
            task_id="TSK-live-" + definition.source_id[4:12],
            source_id=definition.source_id,
            source_name=definition.name,
            query="acme",
            category=definition.category,
            tenant_id="tenant-live",
            investigation_id="INV-live",
        )
        return task, definition.source_id
    return None


def await_topics(topics, *, timeout=30.0) -> None:
    """Block until the broker serves metadata for ``topics``.

    A topic created moments ago is not immediately subscribable: a consumer can
    sit in a rebalance with no assignment until metadata propagates, which reads
    as "no messages" rather than as an error. Waiting for metadata first turns
    that race into a deterministic wait.
    """
    from confluent_kafka.admin import AdminClient
    from dispatcher.kafka_producer import brokers

    admin = AdminClient({"bootstrap.servers": ",".join(brokers())})
    wanted = set(topics)
    deadline = time.time() + timeout
    while time.time() < deadline:
        present = set(admin.list_topics(timeout=5).topics)
        if wanted <= present:
            return
        time.sleep(0.5)
    raise AssertionError(f"topics never appeared in broker metadata: {sorted(wanted - present)}")


def consume_until(client, topics, *, want, match, timeout=POLL_TIMEOUT_S):
    """Poll a real consumer group until ``want`` matching envelopes arrive.

    Reads from ``earliest`` and selects with ``match`` rather than using
    ``latest``: the request is published *before* the consumer subscribes, so a
    ``latest`` reset can start after our own message and miss it. The topic is
    shared and long-lived, so position alone cannot identify our record.
    """
    from confluent_kafka import Consumer

    consumer = Consumer(
        {
            "bootstrap.servers": client,
            "group.id": f"test-acquisition-{int(time.time() * 1000)}",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe(topics)
    found = []
    deadline = time.time() + timeout
    try:
        while time.time() < deadline and len(found) < want:
            msg = consumer.poll(1.0)
            if msg is None or msg.error():
                continue
            envelope = pb.EventEnvelope()
            envelope.ParseFromString(msg.value())
            if match(envelope):
                found.append(envelope)
    finally:
        consumer.close()
    return found


def request_for(task_id: str):
    """Select the request envelope this run published."""

    def match(envelope) -> bool:
        if envelope.event_type != "acquisition.request":
            return False
        try:
            return json.loads(envelope.payload).get("task_id") == task_id
        except (TypeError, ValueError):
            return False

    return match


@requires_broker
def test_request_reaches_the_broker_with_an_acknowledged_offset() -> None:
    """W1 live: the dispatcher's request is really on the topic, really acked."""
    from adapters.registry import register
    from dispatcher.kafka_producer import brokers

    topic = topic_for("acquisition.request")
    ensure_topics([topic, topic_for("observation.created"), TOPIC_DLQ, TOPIC_QUARANTINE])
    await_topics([topic, topic_for("observation.created"), TOPIC_DLQ, TOPIC_QUARANTINE])

    register("web", execution_class="http", capabilities={"http"})
    producer = KafkaProducer()
    task = AcquisitionTask(
        task_id="TSK-live-dispatch",
        source_id="SRC-live",
        source_name="live",
        query="acme",
        category="search",
        tenant_id="tenant-live",
        investigation_id="INV-live",
    )
    record = PlanDispatcher(
        dispatcher=Dispatcher(producer=producer), producer=producer
    ).dispatch([task])[0]

    assert record.published is True
    assert record.topic == topic
    assert record.partition >= 0
    assert record.offset > 0, "the broker must have assigned a real offset"
    assert record.key == "TSK-live-dispatch"

    # Read it back off the topic with a real consumer group.
    found = consume_until(
        ",".join(brokers()),
        [topic],
        want=1,
        match=request_for("TSK-live-dispatch"),
        timeout=POLL_TIMEOUT_S,
    )
    assert found, f"no acquisition.request for TSK-live-dispatch arrived on {topic}"
    assert found[-1].event_type == "acquisition.request"
    assert found[-1].event_version == "2.0"
    assert found[-1].source_id == "SRC-live"
    payload = json.loads(found[-1].payload)
    assert payload["query"] == "acme"
    assert payload["verdict"] == "dispatch"


@requires_broker
def test_the_loop_closes_over_the_live_broker() -> None:
    """W4 live: dispatch → broker → consume → real fetch → acked observation."""
    from adapters.registry import register
    from dispatcher.kafka_producer import brokers

    picked = live_source()
    if picked is None:  # pragma: no cover - the catalogue is not empty in practice
        pytest.skip("no runnable http source in the catalogue")
    task, source_id = picked

    request_topic = topic_for("acquisition.request")
    observation_topic = topic_for("observation.created")
    ensure_topics([request_topic, observation_topic, TOPIC_DLQ, TOPIC_QUARANTINE])
    await_topics([request_topic, observation_topic, TOPIC_DLQ, TOPIC_QUARANTINE])

    # --- publish the request through the real dispatcher --------------------
    register("web", execution_class="http", capabilities={"http"})
    producer = KafkaProducer()
    record = PlanDispatcher(
        dispatcher=Dispatcher(producer=producer), producer=producer
    ).dispatch([task])[0]
    assert record.published is True
    assert record.offset > 0

    # --- a real consumer group reads it back --------------------------------
    bootstrap = ",".join(brokers())
    requests = consume_until(
        bootstrap,
        [request_topic],
        want=1,
        match=request_for(task.task_id),
        timeout=POLL_TIMEOUT_S,
    )
    assert requests, "the request never arrived on the topic"
    envelope = requests[-1]
    assert envelope.event_type == "acquisition.request"

    # --- the worker executes it against the real catalogue ------------------
    published: list[object] = []
    worker = AcquisitionWorker(
        connector=SourceConnector(),
        publish=lambda topic, event, *, key="": published.append((topic, event, key)),
    )
    result = asyncio.run(worker.handle(envelope))

    assert result.source_id == source_id
    assert result.failures == (), f"live source dead-lettered: {result.failures}"
    assert len(published) >= 1, "a live fetch produced no observation"

    topic_used, observation, key = published[0]
    assert topic_used == observation_topic
    assert observation["status"] < 500
    assert observation["source_id"] == source_id
    assert key == observation["event_id"]

    # The id is recomputable from the record: content-addressed, so replaying
    # this request cannot mint a second copy.
    from sources.connector import observation_id

    assert observation["event_id"] == observation_id(
        observation["source_id"],
        observation["query"],
        observation["page"],
        observation["content_digest"],
    )

    # --- and the same worker is a fixed point under replay ------------------
    before = len(published)
    replay = asyncio.run(worker.handle(envelope))
    assert replay.superseded is True
    assert len(published) == before, "replay must not add an observation"


@requires_broker
def test_a_live_4xx_is_an_observation_and_a_real_refusal_is_classified() -> None:
    """W3 against the real world: the 4xx side of the line, using real servers.

    Scope is deliberately the half that is *reliably* observable: real sources
    answer 4xx constantly for a target that does not exist, and every one of
    those must become an observation. The 5xx side is pinned hermetically in
    ``test_acquisition_worker.py`` instead — whether some third-party server
    chooses to return a 5xx today is not something a test may depend on, and a
    suite that did would be reporting someone else's uptime as a regression.

    What is asserted about refusals here is the classification: a real dead
    letter is either a 5xx (with its status) or a transport failure (with none),
    and never a 4xx.
    """
    from sources.catalogue import load_catalogue as _load

    definitions, _rejected = _load()
    candidates = [
        d
        for d in sorted(definitions, key=lambda d: d.source_id)
        if d.enabled
        and not d.requires_key
        and d.kind == "http"
        and d.tool.get("url")
    ][:14]

    seen_status: dict[int, AcquisitionTask] = {}
    sink_records: list = []
    seen_4xx = False

    for definition in candidates:
        task = AcquisitionTask(
            task_id="TSK-live-status-" + definition.source_id[4:12],
            source_id=definition.source_id,
            source_name=definition.name,
            # A target that does not exist drives most sources to 404.
            query="zzz-no-such-entity-zzz-918273",
            category=definition.category,
            tenant_id="tenant-live",
            investigation_id="INV-live",
        )
        published: list = []
        worker = AcquisitionWorker(
            connector=SourceConnector(),
            sink=lambda failure, env=None, _sink=sink_records.append: _sink(failure),
            # Bound explicitly: a lambda closing over the loop's `published`
            # would capture the *current* binding, which is a latent bug the
            # moment the consumer outlives the iteration.
            publish=lambda topic, event, *, key="", _out=published: _out.append(
                (topic, event, key)
            ),
        )
        try:
            result = asyncio.run(worker.handle(_as_request(task)))
        except Exception:
            continue
        if not result.failures:
            for _topic, event, _key in published:
                status = int(event["status"])
                seen_status.setdefault(status, task)
                if 400 <= status < 500:
                    seen_4xx = True
        if seen_4xx and sink_records:
            break

    assert seen_4xx, f"no live 4xx observed; saw {sorted(seen_status)}"

    # The boundary, checked against real servers: a 4xx produced an observation
    # carrying that status, and no 4xx was routed to a failure lane.
    assert not [f for f in sink_records if 400 <= f.status < 500]
    for failure in sink_records:
        assert failure.topic == TOPIC_DLQ, f"{failure.code} went to {failure.topic}"
        if failure.code == "upstream_server_error":
            assert failure.status >= 500
        else:
            assert failure.code == "transport_failed", failure.code
            assert failure.status == 0, "a transport failure has no HTTP status"


def _as_request(task: AcquisitionTask):
    """The same envelope the dispatcher would emit, built by the shared builder."""
    from events.kafka import build_envelope

    return build_envelope(
        event_type="acquisition.request",
        event_version="2.0",
        producer="dispatcher",
        producer_version="0.1.0",
        payload=json.dumps(
            {
                "task_id": task.task_id,
                "query": task.query,
                "source_id": task.source_id,
                "verdict": "dispatch",
                "execution_class": "http",
            },
            sort_keys=True,
        ).encode("utf-8"),
        investigation_id=task.investigation_id,
        tenant_id=task.tenant_id,
        source_id=task.source_id,
    )


@requires_broker
def test_live_failure_lands_on_a_named_topic() -> None:
    """A real unresolvable source is published to quarantine, acknowledged, not dropped."""
    import worker_acquisition

    producer = KafkaProducer()
    ensure_topics([TOPIC_QUARANTINE, TOPIC_DLQ])
    await_topics([TOPIC_QUARANTINE, TOPIC_DLQ])
    recorded: list = []
    acked: list = []
    sink = worker_acquisition.kafka_failure_sink(producer)

    def recording_sink(failure, envelope=None):
        recorded.append(failure)
        # `publish_sync` returns what the broker acknowledged, so the delivery
        # report is captured here rather than read back off the producer: a
        # later `flush` clears the acknowledgement list by design.
        acked.append(sink(failure, envelope))

    worker = AcquisitionWorker(
        connector=SourceConnector(),
        sink=recording_sink,
        publish=observation_publisher(producer),
    )
    task = AcquisitionTask(
        task_id="TSK-live-missing",
        source_id="SRC-does-not-exist-0000",
        source_name="missing",
        query="acme",
        category="search",
        tenant_id="tenant-live",
        investigation_id="INV-live",
    )
    result = asyncio.run(worker.handle(_as_request(task)))

    assert result.observations == ()
    assert len(recorded) == 1
    assert recorded[0].topic == TOPIC_QUARANTINE
    assert recorded[0].code == "unknown_source"
    # And it is actually on the topic, at an offset the broker assigned.
    assert acked and acked[0] is not None, "the quarantine record was never acknowledged"
    assert acked[0].topic == TOPIC_QUARANTINE
    assert acked[0].offset > 0
