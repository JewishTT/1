"""W1: the plan driver feeds the real Dispatcher and records acknowledged offsets.

Pinned behaviors:
  - a dispatched task is published with the broker's partition+offset
  - a deferred task is NOT published, and says why (the scheduler decides, not us)
  - the scheduler's envelope contract holds for the tasks we feed it
  - the request payload is JSON and carries the query a worker needs
  - replaying a plan produces the same task ids (Invariant 12)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))

import pytest
from adapters.registry import REGISTRY, register
from dispatcher.plan_driver import (
    ContractViolation,
    PlanDispatcher,
    assert_request_contract,
)
from dispatcher.scheduler import Dispatcher
from sources.connector import AcquisitionTask, plan

pytestmark = pytest.mark.contract


@pytest.fixture(autouse=True)
def _registry():
    saved = dict(REGISTRY._sources)
    REGISTRY._sources.clear()
    yield
    REGISTRY._sources.clear()
    REGISTRY._sources.update(saved)


class AckedProducer:
    """A producer that acknowledges, like the broker does.

    Mirrors `KafkaProducer`'s surface the driver actually uses: async `produce`,
    then delivery reports arriving via `flush`/`drain`.
    """

    def __init__(self) -> None:
        self.published: list[tuple[str, object, str | None]] = []
        self.acked: list[object] = []
        self._offset = 40
        self.events: list[object] = []

    def produce(self, topic: str, envelope, *, key: str | None = None) -> None:
        self.published.append((topic, envelope, key))
        self._offset += 1
        self.acked.append(
            _Delivery(
                topic=topic,
                partition=1,
                offset=self._offset,
                key=key or "",
            )
        )

    def flush(self, timeout: float = 10.0) -> int:
        return 0

    def drain(self):
        out = tuple(self.acked)
        self.acked.clear()
        return out


class _Delivery:
    def __init__(self, *, topic: str, partition: int, offset: int, key: str) -> None:
        self.topic = topic
        self.partition = partition
        self.offset = offset
        self.key = key
        self.event_type = ""


def task(**over) -> AcquisitionTask:
    base = {
        "task_id": "TSK-abc",
        "source_id": "SRC-1",
        "source_name": "src",
        "query": "acme corp",
        "category": "search",
        "tenant_id": "ten-1",
        "investigation_id": "INV-1",
    }
    base.update(over)
    return AcquisitionTask(**base)


def dispatcher_with(producer, **kw) -> Dispatcher:
    register("web", execution_class="http", capabilities={"http"})
    return Dispatcher(producer=producer, **kw)


class TestDispatchPublishes:
    def test_dispatched_task_is_published_with_acked_offset(self) -> None:
        producer = AckedProducer()
        driver = PlanDispatcher(
            dispatcher=dispatcher_with(producer), producer=producer
        )
        records = driver.dispatch([task()])

        assert len(records) == 1
        rec = records[0]
        assert rec.published is True
        assert rec.verdict == "dispatch"
        assert rec.topic == "acquisition"
        assert rec.partition == 1
        assert rec.offset > 0
        assert rec.key == "TSK-abc"
        assert rec.to_dict()["offset"] == rec.offset

    def test_topic_is_the_catalog_topic_for_the_event(self) -> None:
        from events.topics import topic_for

        producer = AckedProducer()
        driver = PlanDispatcher(dispatcher=dispatcher_with(producer), producer=producer)
        driver.dispatch([task()])
        topic, _envelope, _key = producer.published[0]
        assert topic == topic_for("acquisition.request")

    def test_each_task_gets_its_own_offset_not_a_previous_one(self) -> None:
        """A task must never be credited with another task's acknowledgement."""
        producer = AckedProducer()
        driver = PlanDispatcher(dispatcher=dispatcher_with(producer), producer=producer)
        records = driver.dispatch(
            [task(task_id="TSK-1"), task(task_id="TSK-2"), task(task_id="TSK-3")]
        )
        offsets = [r.offset for r in records]
        assert len(set(offsets)) == 3, "offsets must be distinct per task"
        assert offsets == sorted(offsets)

    def test_publish_is_keyed_by_task_id(self) -> None:
        producer = AckedProducer()
        driver = PlanDispatcher(dispatcher=dispatcher_with(producer), producer=producer)
        driver.dispatch([task()])
        _topic, _envelope, key = producer.published[0]
        assert key == "TSK-abc"

    def test_no_acknowledgement_is_reported_as_not_published(self) -> None:
        """Fire-and-forget must not read as success."""

        class Silent(AckedProducer):
            def produce(self, topic, envelope, *, key=None):  # never acks
                return None

        producer = Silent()
        driver = PlanDispatcher(dispatcher=dispatcher_with(producer), producer=producer)
        rec = driver.dispatch([task()])[0]
        assert rec.published is False
        assert "acknowledged nothing" in rec.reason


class TestDeferral:
    def test_deferred_task_is_not_published(self) -> None:
        producer = AckedProducer()
        # No capability registered at all -> the scheduler must defer.
        driver = PlanDispatcher(dispatcher=Dispatcher(producer=producer), producer=producer)
        rec = driver.dispatch([task()])[0]
        assert rec.published is False
        assert rec.verdict == "defer"
        assert producer.published == []
        assert "capability gap" in rec.reason

    def test_low_utility_defers_and_says_why(self) -> None:
        producer = AckedProducer()
        driver = PlanDispatcher(
            dispatcher=dispatcher_with(producer, min_utility=10.0), producer=producer
        )
        rec = driver.dispatch([task()])[0]
        assert rec.verdict == "defer"
        assert "utility" in rec.reason

    def test_capability_gap_is_never_a_silent_misroute(self) -> None:
        """A task needing an engine nothing provides defers; it is not rerouted."""
        producer = AckedProducer()
        driver = PlanDispatcher(
            dispatcher=dispatcher_with(producer), producer=producer
        )
        rec = driver.dispatch_one(
            task(),
            context_score_fields={"required_capabilities": ["parquet", "range-read"]},
        )
        assert rec.published is False
        assert rec.verdict == "defer"
        assert "capability gap" in rec.reason
        assert "parquet" in rec.reason
        assert producer.published == []


class TestRequestEnvelopeContract:
    def test_envelope_satisfies_the_worker_contract(self) -> None:
        producer = AckedProducer()
        driver = PlanDispatcher(dispatcher=dispatcher_with(producer), producer=producer)
        driver.dispatch([task()])
        _topic, envelope, _key = producer.published[0]
        assert_request_contract(envelope)  # must not raise

    def test_contract_requires_a_source_id(self) -> None:
        producer = AckedProducer()
        driver = PlanDispatcher(dispatcher=dispatcher_with(producer), producer=producer)
        driver.dispatch([task()])
        _t, envelope, _k = producer.published[0]
        envelope.source_id = ""
        with pytest.raises(ContractViolation, match="source_id"):
            assert_request_contract(envelope)

    def test_contract_requires_a_tenant(self) -> None:
        producer = AckedProducer()
        driver = PlanDispatcher(dispatcher=dispatcher_with(producer), producer=producer)
        driver.dispatch([task()])
        _t, envelope, _k = producer.published[0]
        envelope.tenant_id = ""
        with pytest.raises(ContractViolation, match="tenant_id"):
            assert_request_contract(envelope)

    def test_contract_rejects_a_foreign_event_type(self) -> None:
        producer = AckedProducer()
        driver = PlanDispatcher(dispatcher=dispatcher_with(producer), producer=producer)
        driver.dispatch([task()])
        _t, envelope, _k = producer.published[0]
        envelope.event_type = "something.else"
        with pytest.raises(ContractViolation, match="expected acquisition.request"):
            assert_request_contract(envelope)

    def test_contract_rejects_a_missing_envelope(self) -> None:
        with pytest.raises(ContractViolation, match="no envelope"):
            assert_request_contract(None)


class TestRequestPayloadIsExecutable:
    """The payload is the only thing a worker gets; it must be usable."""

    def _payload(self, **over) -> dict:
        producer = AckedProducer()
        driver = PlanDispatcher(dispatcher=dispatcher_with(producer), producer=producer)
        driver.dispatch([task(**over)])
        _t, envelope, _k = producer.published[0]
        return json.loads(envelope.payload)

    def test_payload_is_json_not_a_python_repr(self) -> None:
        producer = AckedProducer()
        driver = PlanDispatcher(dispatcher=dispatcher_with(producer), producer=producer)
        driver.dispatch([task()])
        _t, envelope, _k = producer.published[0]
        # The defect this pins: str(dict) emits single quotes and is not JSON.
        assert json.loads(envelope.payload)["task_id"] == "TSK-abc"
        assert b"'task_id'" not in envelope.payload

    def test_payload_carries_the_query(self) -> None:
        assert self._payload()["query"] == "acme corp"

    def test_payload_carries_source_and_verdict(self) -> None:
        data = self._payload()
        assert data["source_id"] == "SRC-1"
        assert data["verdict"] == "dispatch"
        assert data["execution_class"] == "http"

    def test_worker_can_parse_the_payload_into_a_task(self) -> None:
        from worker_acquisition import RequestParser

        producer = AckedProducer()
        driver = PlanDispatcher(dispatcher=dispatcher_with(producer), producer=producer)
        driver.dispatch([task()])
        _t, envelope, _k = producer.published[0]
        parsed = RequestParser().parse(envelope)
        assert parsed.task_id == "TSK-abc"
        assert parsed.source_id == "SRC-1"
        assert parsed.query == "acme corp"
        assert parsed.tenant_id == "ten-1"
        assert parsed.investigation_id == "INV-1"


class TestDeterminism:
    def test_task_mapping_is_order_independent(self) -> None:
        from dispatcher.plan_driver import task_mapping

        a = task_mapping(task(), uri="https://e.com", context_score_fields={"z": 1, "a": 2})
        b = task_mapping(task(), uri="https://e.com", context_score_fields={"a": 2, "z": 1})
        assert list(a) == list(b)
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

    def test_plan_is_stable_across_calls(self) -> None:
        first = plan("acme corp")
        second = plan("acme corp")
        assert [t.task_id for t in first] == [t.task_id for t in second]

    def test_no_uuid_or_wallclock_in_the_driver(self) -> None:
        """Invariant 12: ids are derived, never minted."""
        import inspect

        import dispatcher.plan_driver as mod

        src = inspect.getsource(mod)
        assert "uuid4" not in src
        assert "uuid1" not in src
        assert "datetime.now" not in src
        assert "time.time" not in src
