"""W2/W3/W5: the worker turns a request into observations, or into a named refusal.

Pinned behaviors:
  - every page becomes an observation, not just page 1
  - the published shape is SourceConnector's, field for field (no second shape)
  - 4xx is an answer -> an observation carrying that status
  - 5xx -> DLQ, named, never dropped
  - transport failure -> DLQ; unknown source / refused host -> quarantine
  - a replayed request does not produce a second observation (idempotency)
  - a failed request stays replayable (constitution: nothing auto-deleted)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))

import pytest
from events.topics import TOPIC_DLQ, TOPIC_QUARANTINE, topic_for
from sources.catalogue import Pagination, SourceDefinition
from sources.connector import AcquisitionTask, SourceConnector
from sources.executor import AcquisitionError
from worker_acquisition import (
    AcquisitionWorker,
    Failure,
    RequestParser,
    classify_error,
    classify_status,
    is_valid_answer,
)

pytestmark = pytest.mark.unit

#: Fields whose value is a property of *this* fetch rather than of the shape.
#: Two honest fetches of identical bytes must differ here and nowhere else.
PER_FETCH_FIELDS = frozenset({"retrieved_at", "elapsed_s"})



def make_definition(**over) -> SourceDefinition:
    base = {
        "source_id": "SRC-test",
        "name": "test_source",
        "enabled": True,
        "category": "search",
        "description": "",
        "parser": "raw_text",
        "applies_to": (),
        "entity_hints": (),
        "requires_key": False,
        "key_env": "",
        "contact": "search_engine",
        "contact_inferred": False,
        "kind": "http",
        "kind_inferred": False,
        "os_requirement": "any",
        "tool": {"url": "https://example.test/{query}"},
        "pagination": Pagination(),
        "parser_is_identity": True,
        "source_path": "test.yaml",
    }
    base.update(over)
    return SourceDefinition(**base)


def task(**over) -> AcquisitionTask:
    base = {
        "task_id": "TSK-test",
        "source_id": "SRC-test",
        "source_name": "test_source",
        "query": "acme",
        "category": "search",
        "tenant_id": "ten-1",
        "investigation_id": "INV-1",
    }
    base.update(over)
    return AcquisitionTask(**base)


class FakeTransport:
    """A scripted transport: one scripted response per page, in order.

    An item is either ``(status, body)`` or a bare exception, which is raised
    from ``request`` so the executor's own guard sees it.
    """

    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.requests: list[str] = []
        self.closed = False

    async def request(self, method, url, headers=None):
        self.requests.append(url)
        item = self.responses[min(len(self.requests) - 1, len(self.responses) - 1)]
        if isinstance(item, Exception):
            raise item
        return _Response(*item)

    async def aclose(self) -> None:
        self.closed = True


class _Response:
    def __init__(self, status: int, body: bytes, content_type: str = "text/html") -> None:
        self.status_code = status
        self.content = body
        self.headers = {"content-type": content_type}


class Collector(SourceConnector):
    """The real `SourceConnector`, resolving one scripted definition.

    Only `definition_for` is overridden — the catalogue is not a test fixture.
    `collect` itself is the production method, so the event shape the worker
    publishes is the connector's own and not a copy written here.
    """

    def __init__(self, definition: SourceDefinition, transport) -> None:
        from sources.executor import HttpSourceExecutor

        self.test_definition = definition
        self.transport = transport
        super().__init__(executor=HttpSourceExecutor(client=transport))

    def definition_for(self, source_id: str) -> SourceDefinition | None:
        if source_id == self.test_definition.source_id:
            return self.test_definition
        return None


class RecordingSink:
    def __init__(self) -> None:
        self.failures: list[Failure] = []

    def __call__(self, failure: Failure, envelope=None) -> None:
        self.failures.append(failure)


def make_worker(responses, *, pagination=None, definition_over=None):
    transport = FakeTransport(responses)
    over = {"pagination": pagination} if pagination else {}
    over.update(definition_over or {})
    definition = make_definition(**over)
    collector = Collector(definition, transport)
    published: list[tuple[str, dict, str]] = []
    sink = RecordingSink()
    worker = AcquisitionWorker(
        connector=collector,
        sink=sink,
        publish=lambda topic, event, *, key="": published.append((topic, event, key)),
    )
    return worker, published, sink, transport


def envelope_for(t: AcquisitionTask):
    from events.kafka import build_envelope

    payload = json.dumps(
        {
            "category": t.category,
            "execution_class": "http",
            "query": t.query,
            "source_id": t.source_id,
            "task_id": t.task_id,
            "verdict": "dispatch",
        },
        sort_keys=True,
    ).encode("utf-8")
    return build_envelope(
        event_type="acquisition.request",
        event_version="2.0",
        producer="dispatcher",
        producer_version="0.1.0",
        payload=payload,
        investigation_id=t.investigation_id,
        tenant_id=t.tenant_id,
        source_id=t.source_id,
    )


class TestEveryPageBecomesAnObservation:
    async def test_all_pages_are_collected_not_just_page_one(self) -> None:
        pagination = Pagination(strategy="page", param="page", page_size=1, max_pages=3)
        worker, published, sink, transport = make_worker(
            [(200, b"one"), (200, b"two"), (200, b"three")], pagination=pagination
        )
        result = await worker.handle(envelope_for(task()))

        assert len(published) == 3
        assert [e["page"] for _t, e, _k in published] == [1, 2, 3]
        assert [e["byte_length"] for _t, e, _k in published] == [3, 3, 5]
        assert len(result.observations) == 3
        assert sink.failures == []

    async def test_each_page_has_its_own_observation_id(self) -> None:
        pagination = Pagination(strategy="page", param="page", page_size=1, max_pages=2)
        worker, published, _sink, _t = make_worker(
            [(200, b"one"), (200, b"two")], pagination=pagination
        )
        await worker.handle(envelope_for(task()))
        ids = [e["event_id"] for _t, e, _k in published]
        assert len(set(ids)) == 2


class TestObservationShapeIsTheConnectors:
    async def test_worker_publishes_the_connector_shape_field_for_field(self) -> None:
        """The anti-rot pin: one producer of `observation.created`, not two.

        Runs the connector's own `collect` independently and compares, so a
        second shape written anywhere fails here rather than in production.
        """
        worker, published, _sink, _t = make_worker([(200, b"body")])
        t = task()
        await worker.handle(envelope_for(t))

        # The connector is asked again, directly, for what it would emit alone.
        direct = SourceConnector(executor=worker.connector.executor)
        direct.definition_for = worker.connector.definition_for  # type: ignore[method-assign]
        expected = [event async for _capture, event in direct.collect(t)]

        assert len(published) == 1
        _topic, event, key = published[0]
        assert len(expected) == 1
        assert set(event) == set(expected[0]), "worker must not add or drop fields"

        # Two independent fetches cannot agree on *when* they happened, so the
        # per-fetch timing fields are excluded from the value comparison. They
        # are the only permitted divergence — asserted as a set, not assumed —
        # and they are the reason idempotency keys on the content-addressed
        # `event_id` rather than on the body.
        diverged = {f for f in expected[0] if event[f] != expected[0][f]}
        assert diverged <= PER_FETCH_FIELDS, f"unexpected divergence in {sorted(diverged)}"
        for field in set(expected[0]) - PER_FETCH_FIELDS:
            assert event[field] == expected[0][field], f"field {field} diverged"

        assert published[0][0] == topic_for("observation.created")
        assert key == event["event_id"]

    async def test_the_content_addressed_id_is_stable_across_fetches(self) -> None:
        """The identity that makes replay idempotent does not move with the clock."""
        worker, _published, _sink, _t = make_worker([(200, b"body")])
        t = task()
        direct = SourceConnector(executor=worker.connector.executor)
        direct.definition_for = worker.connector.definition_for  # type: ignore[method-assign]
        first = [e async for _c, e in direct.collect(t)]
        second = [e async for _c, e in direct.collect(t)]
        assert first[0]["event_id"] == second[0]["event_id"]
        assert first[0]["content_digest"] == second[0]["content_digest"]

    def test_worker_module_does_not_define_its_own_observation_shape(self) -> None:
        """A second literal shape in the worker is the rot this forbids."""
        import inspect

        import worker_acquisition as mod

        src = inspect.getsource(mod)
        # The only place an observation dict is *built* must be the connector.
        assert "observation.created" in src  # it is named, for the topic lookup
        assert '"retrieved_at"' not in src
        assert '"content_digest":' not in src
        assert '"page_count"' not in src

    def test_worker_imports_no_graph_claim_or_admission_symbol(self) -> None:
        import inspect

        import worker_acquisition as mod

        src = inspect.getsource(mod)
        for forbidden in (
            "relation_claim",
            "candidate",
            "admission",
            "graph",
            "projection",
            "mention",
        ):
            assert forbidden not in src, f"producer code must not import {forbidden}"


class TestValidAnswerIsAnObservation:
    """The 4xx side of the line: a refusal to find something IS the finding."""

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 429])
    async def test_4xx_becomes_an_observation_with_that_status(self, status) -> None:
        worker, published, sink, _t = make_worker([(status, b"nope")])
        result = await worker.handle(envelope_for(task()))

        assert len(published) == 1
        assert published[0][1]["status"] == status
        assert result.failures == ()
        assert sink.failures == [], "a 4xx must not be routed to a failure lane"

    @pytest.mark.parametrize("status", [200, 201, 301, 404])
    def test_is_valid_answer_line_is_drawn_at_500(self, status) -> None:
        assert is_valid_answer(status) is True

    @pytest.mark.parametrize("status", [500, 502, 503, 504])
    def test_5xx_is_not_a_valid_answer(self, status) -> None:
        assert is_valid_answer(status) is False

    def test_classify_status_returns_none_for_an_answer(self) -> None:
        assert classify_status(404) is None

    def test_classify_status_names_a_5xx(self) -> None:
        failure = classify_status(503, source_id="SRC-test", task_id="TSK-test")
        assert failure is not None
        assert failure.topic == TOPIC_DLQ
        assert failure.code == "upstream_server_error"
        assert failure.status == 503


class TestServerErrorIsDeadLettered:
    async def test_5xx_goes_to_the_dlq_with_a_reason(self) -> None:
        worker, published, sink, _t = make_worker([(500, b"boom")])
        result = await worker.handle(envelope_for(task()))

        assert published == [], "a 5xx must not become an observation"
        assert len(sink.failures) == 1
        failure = sink.failures[0]
        assert failure.topic == TOPIC_DLQ
        assert failure.code == "upstream_server_error"
        assert "500" in failure.reason
        assert result.failures[0].topic == TOPIC_DLQ

    async def test_5xx_stops_pagination(self) -> None:
        """One upstream outage must not become N dead letters."""
        pagination = Pagination(strategy="page", param="page", page_size=1, max_pages=3)
        worker, published, sink, transport = make_worker(
            [(500, b"boom"), (200, b"two"), (200, b"three")], pagination=pagination
        )
        await worker.handle(envelope_for(task()))
        assert published == []
        assert len(sink.failures) == 1
        assert len(transport.requests) == 1


class TestTransportFailureIsDeadLettered:
    async def test_transport_failure_is_a_dlq_entry(self) -> None:
        worker, published, sink, _t = make_worker([ConnectionResetError("connection reset")])
        result = await worker.handle(envelope_for(task()))

        assert published == []
        assert len(sink.failures) == 1
        assert sink.failures[0].topic == TOPIC_DLQ
        assert sink.failures[0].code == "transport_failed"
        assert "ConnectionResetError" in sink.failures[0].reason
        assert result.failures[0].code == "transport_failed"

    async def test_timeout_is_also_a_dead_letter(self) -> None:
        worker, _p, sink, _t = make_worker([TimeoutError("timed out")])
        await worker.handle(envelope_for(task()))
        assert sink.failures[0].topic == TOPIC_DLQ
        assert "TimeoutError" in sink.failures[0].reason


class TestUnresolvableIsQuarantined:
    """Never guess: an unresolvable source is a named refusal, not a default."""

    async def test_unknown_source_id_is_quarantined(self) -> None:
        worker, published, sink, _t = make_worker([(200, b"x")])
        # The worker is handed a task whose source the connector cannot resolve.
        result = await worker.handle(envelope_for(task(source_id="SRC-missing")))

        assert published == []
        assert len(sink.failures) == 1
        assert sink.failures[0].topic == TOPIC_QUARANTINE
        assert sink.failures[0].code == "unknown_source"
        assert "SRC-missing" in sink.failures[0].reason
        assert result.failures[0].topic == TOPIC_QUARANTINE

    async def test_refused_host_is_quarantined(self) -> None:
        worker, published, sink, _t = make_worker(
            [(200, b"x")], definition_over={"tool": {"url": "http://127.0.0.1/{query}"}}
        )
        result = await worker.handle(envelope_for(task()))

        assert published == []
        assert sink.failures[0].topic == TOPIC_QUARANTINE
        assert sink.failures[0].code == "host_in_reserved_range"
        assert result.failures[0].code == "host_in_reserved_range"

    async def test_private_range_host_is_refused_without_a_connection(self) -> None:
        worker, _p, sink, transport = make_worker(
            [(200, b"x")], definition_over={"tool": {"url": "http://10.1.2.3/{query}"}}
        )
        await worker.handle(envelope_for(task()))
        assert sink.failures[0].code == "host_in_reserved_range"
        assert transport.requests == [], "a refused host must never be contacted"

    async def test_non_http_source_is_quarantined(self) -> None:
        worker, published, sink, _t = make_worker(
            [(200, b"x")], definition_over={"kind": "system_app"}
        )
        await worker.handle(envelope_for(task()))
        assert published == []
        assert sink.failures[0].topic == TOPIC_QUARANTINE
        assert sink.failures[0].code == "not_an_http_source"

    def test_every_refusal_names_its_own_lane_and_reason(self) -> None:
        cases = {
            "transport_failed": TOPIC_DLQ,
            "unknown_source": TOPIC_QUARANTINE,
            "not_an_http_source": TOPIC_QUARANTINE,
            "host_in_reserved_range": TOPIC_QUARANTINE,
            "keyed_source_without_key_env": TOPIC_QUARANTINE,
            "source_has_no_url": TOPIC_QUARANTINE,
        }
        for code, topic in cases.items():
            failure = classify_error(AcquisitionError(code, f"{code} happened"))
            assert failure.topic == topic, f"{code} routed to the wrong lane"
            assert failure.code == code
            assert failure.reason == f"{code} happened"

    def test_an_unrecognised_error_code_is_not_silently_defaulted(self) -> None:
        """A new upstream guard must be visible, not folded into a known bucket."""
        failure = classify_error(AcquisitionError("brand_new_guard", "unheard of"))
        assert failure.code == "brand_new_guard"
        assert failure.topic == TOPIC_QUARANTINE


class TestMalformedRequestIsQuarantined:
    async def test_unreadable_payload_is_quarantined_not_dropped(self) -> None:
        from events.kafka import build_envelope

        worker, published, sink, _t = make_worker([(200, b"x")])
        envelope = build_envelope(
            event_type="acquisition.request",
            event_version="2.0",
            producer="dispatcher",
            producer_version="0.1.0",
            payload=b"{'not': 'json'}",
            tenant_id="ten-1",
        )
        result = await worker.handle(envelope)
        assert published == []
        assert sink.failures[0].topic == TOPIC_QUARANTINE
        assert sink.failures[0].code == "request_payload_unreadable"
        assert result.failures[0].code == "request_payload_unreadable"

    def test_request_without_a_source_is_refused(self) -> None:
        from events.kafka import build_envelope

        envelope = build_envelope(
            event_type="acquisition.request",
            event_version="2.0",
            producer="dispatcher",
            producer_version="0.1.0",
            payload=b'{"task_id": "T-1"}',
            tenant_id="ten-1",
        )
        with pytest.raises(AcquisitionError, match="source_id"):
            RequestParser().parse(envelope)

    def test_request_without_a_task_id_is_refused(self) -> None:
        from events.kafka import build_envelope

        envelope = build_envelope(
            event_type="acquisition.request",
            event_version="2.0",
            producer="dispatcher",
            producer_version="0.1.0",
            payload=b'{"source_id": "SRC-1"}',
            tenant_id="ten-1",
        )
        with pytest.raises(AcquisitionError, match="task_id"):
            RequestParser().parse(envelope)


class TestIdempotencyUnderReplay:
    async def test_replayed_request_publishes_no_second_observation(self) -> None:
        worker, published, _sink, transport = make_worker([(200, b"same bytes")])
        envelope = envelope_for(task())

        first = await worker.handle(envelope)
        second = await worker.handle(envelope)

        assert len(first.observations) == 1
        assert second.superseded is True
        assert second.observations == ()
        assert len(published) == 1, "a replay must not produce a second copy"
        assert len(transport.requests) == 1, "a replay must not re-fetch"

    async def test_replayed_request_keeps_the_same_observation_id(self) -> None:
        worker, published, _sink, _t = make_worker([(200, b"same bytes")])
        envelope = envelope_for(task())
        await worker.handle(envelope)
        await worker.handle(envelope)
        assert len({e["event_id"] for _t, e, _k in published}) == 1

    async def test_replay_is_a_fixed_point(self) -> None:
        """Invariant 12: replaying N times leaves the same published set."""
        worker, published, _sink, _t = make_worker([(200, b"bytes")])
        envelope = envelope_for(task())
        for _ in range(4):
            await worker.handle(envelope)
        assert len(published) == 1

    async def test_a_different_query_is_a_different_observation(self) -> None:
        """Idempotency must not collapse two genuinely different collections."""
        worker, published, _sink, _t = make_worker([(200, b"bytes")])
        await worker.handle(envelope_for(task(query="acme")))
        await worker.handle(envelope_for(task(query="globex")))
        assert len(published) == 2

    async def test_a_failed_request_stays_replayable(self) -> None:
        """Constitution: rejected work is never auto-deleted, so it can be re-run."""
        worker, published, sink, transport = make_worker([(500, b"boom")])
        envelope = envelope_for(task())
        await worker.handle(envelope)
        assert len(sink.failures) == 1

        transport.responses = [(200, b"recovered")]
        second = await worker.handle(envelope)

        assert second.superseded is False, "a dead-lettered request must not be skipped"
        assert len(published) == 1
        assert published[0][1]["status"] == 200

    async def test_a_transport_failure_stays_replayable(self) -> None:
        worker, published, sink, transport = make_worker(
            [ConnectionResetError("reset")]
        )
        envelope = envelope_for(task())
        await worker.handle(envelope)
        assert sink.failures[0].topic == TOPIC_DLQ

        transport.responses = [(200, b"recovered")]
        second = await worker.handle(envelope)
        assert second.superseded is False
        assert len(published) == 1

    def test_worker_never_mints_an_id(self) -> None:
        """Invariant 12: no uuid4, no wall clock in the worker."""
        import inspect

        import worker_acquisition as mod

        src = inspect.getsource(mod)
        assert "uuid4" not in src
        assert "datetime.now" not in src
        assert "time.time" not in src
