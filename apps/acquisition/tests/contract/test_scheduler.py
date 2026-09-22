"""Dispatcher scheduler contract tests (T110/T132/T133, US1, Constitution gates).

Pinned behaviors:
  - Stage A: below-min utility defers, never dispatches (T132)
  - capability intersection: a task needing `browser` routes to a browser
    registration, never to an http one (T110)
  - explicit CapabilityGap: unknown capability -> Defer, not a misroute (T090)
  - capability fallback: no required_capabilities -> http baseline
  - Stage B: resource limits can park a dispatch (T133)
  - host_of: canonical host key for concurrency/source limits
  - acquisition.request envelope carries tenant/source/work/region (T103/T104)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))

import pytest
from adapters.registry import REGISTRY, register
from dispatcher.scheduler import Dispatcher, ScheduleDecision, ScopeLimits, Verdict, host_of

pytestmark = pytest.mark.contract


@pytest.fixture(autouse=True)
def _clean_registry():
    adapters = REGISTRY._sources
    saved = dict(adapters)
    adapters.clear()
    yield
    adapters.clear()
    adapters.update(saved)


def task(**overrides) -> dict:
    base = {
        "task_id": "T-1",
        "uri": "https://example.com/page",
        "tenant_id": "ten-1",
        "source_id": "src-1",
        "work_id": "wk-1",
        "region": "eu-west",
        "required_capabilities": ["http"],
        "expected_gain": 0.6,
        "novelty": 0.7,
        "relevance": 0.6,
        "freshness": 0.5,
        "source_quality": 0.8,
        "network_cost": 0.1,
        "compute_cost": 0.1,
    }
    base.update(overrides)
    return base


def test_low_utility_defers() -> None:
    d = Dispatcher(min_utility=0.5)
    dec = d.schedule(task(expected_gain=0.001, novelty=0.001))
    assert dec.verdict is Verdict.DEFER
    assert "utility" in dec.reason


def test_capability_match_selects_http() -> None:
    register("web", execution_class="http", capabilities={"http"})
    d = Dispatcher()
    dec = d.schedule(task(required_capabilities=["http"]))
    assert dec.verdict is Verdict.DISPATCH
    assert dec.execution_class == "http"
    assert dec.source_type == "web"


def test_capability_intersection_routes_browser() -> None:
    register("web", execution_class="http", capabilities={"http"})
    register("js", execution_class="browser", capabilities={"http", "javascript", "dom"})
    d = Dispatcher()
    dec = d.schedule(task(required_capabilities=["javascript", "http"], uri="https://spa.example/"))
    assert dec.verdict is Verdict.DISPATCH
    assert dec.execution_class == "browser"
    assert dec.source_type == "js"


def test_capability_gap_defers_explicitly() -> None:
    register("web", execution_class="http", capabilities={"http"})
    d = Dispatcher()
    dec = d.schedule(task(required_capabilities=["parquet", "range-read"]))
    assert dec.verdict is Verdict.DEFER
    assert "gap" in dec.reason
    assert "parquet" in dec.reason


def test_no_required_capabilities_falls_back_to_http() -> None:
    register("web", execution_class="http", capabilities={"http"})
    d = Dispatcher()
    dec = d.schedule(task(required_capabilities=[]))
    assert dec.verdict is Verdict.DISPATCH
    assert dec.execution_class == "http"


def test_resource_limit_parks_dispatch() -> None:
    register("web", execution_class="http", capabilities={"http"})

    class RejectingLimits:
        def allows(
            self, execution_class: str, region: str | None, host_key: str, required: set[str]
        ) -> tuple[bool, str]:
            return False, "browser capacity exhausted"

    d = Dispatcher(limits=RejectingLimits())
    dec = d.schedule(task())
    assert dec.verdict is Verdict.DEFER
    assert "capacity" in dec.reason


def test_scope_limits_default_allows() -> None:
    register("web", execution_class="http", capabilities={"http"})
    d = Dispatcher(limits=ScopeLimits())
    assert d.schedule(task()).verdict is Verdict.DISPATCH


def test_host_of_canonicalizes() -> None:
    assert host_of("https://News.Example.com/page?a=1") == "news.example.com"
    assert host_of("http://x.local/") == "x.local"
    assert host_of("plain-host") == "plain-host"


def test_dispatch_carries_routing_and_utility() -> None:
    register("web", execution_class="http", capabilities={"http"})
    d = Dispatcher()
    dec: ScheduleDecision = d.schedule(task())
    assert dec.verdict is Verdict.DISPATCH
    assert dec.utility > 0.0
    assert dec.region == "eu-west"


class MemoryProducer:
    """Captures produced envelopes — the producer is injectable, so tests never
    need a broker (the audit found `emit_request` dropped the envelope; this
    pin is the fix)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object, str | None]] = []

    def produce(self, topic: str, envelope, *, key: str | None = None) -> None:
        self.calls.append((topic, envelope, key))


def test_emit_request_produces_acquisition_request_envelope() -> None:
    register("web", execution_class="http", capabilities={"http"})
    producer = MemoryProducer()
    d = Dispatcher(producer=producer)
    t = task()
    dec = d.schedule(t)
    assert dec.verdict is Verdict.DISPATCH

    d.emit_request(t, dec)

    assert len(producer.calls) == 1
    topic, env, key = producer.calls[0]
    assert topic == "acquisition"
    assert env.event_type == "acquisition.request"
    assert env.event_version == "2.0"
    assert env.tenant_id == "ten-1"
    assert env.source_id == "src-1"
    assert env.work_id == "wk-1"
    assert env.region_id == "eu-west"
    assert env.investigation_id == ""
    assert key == "T-1"
    assert b"dispatch" in env.payload  # verdict travels in the payload


def test_emit_request_without_producer_is_noop() -> None:
    """Back-compat: no producer configured → nothing produced, no crash."""
    register("web", execution_class="http", capabilities={"http"})
    d = Dispatcher()
    t = task()
    dec = d.schedule(t)
    d.emit_request(t, dec)  # must not raise despite no transport
