"""Contract tests for the collection metrics vectors (T114, US1).

Pinned behaviors:
  - counters increment per event; per-execution-class slices stay isolated
  - lifecycle counts the gate's four verdicts (created/changed/unchanged/duplicate)
  - frontier metrics are EWMA rates (gauges), not cumulative counters
  - scheduler decision latency is recorded; verdict distribution totals dispatch/defer
  - all vectors live on a renderable registry (T073 scrape target)
"""

from __future__ import annotations

import pytest

import prometheus_client

from scoring import metrics

pytestmark = pytest.mark.contract


@pytest.fixture(autouse=True)
def _isolate():
    for metric in (metrics.COLLECTOR_BYTES, metrics.OBSERVATION_LIFECYCLE, metrics.SCHEDULER_VERDICTS):
        _reset_counter(metric)
    yield


def _reset_counter(counter) -> None:  # noqa: ANN001
    counter.clear()


def test_collector_throughput_slices_by_execution_class() -> None:
    metrics.record_collection("http", 1000)
    metrics.record_collection("http", 500)
    metrics.record_collection("browser", 9000)
    http = metrics.COLLECTOR_BYTES.labels(execution_class="http")._value.get()
    browser = metrics.COLLECTOR_BYTES.labels(execution_class="browser")._value.get()
    assert http == 1500
    assert browser == 9000


def test_lifecycle_counts_all_four_verdicts() -> None:
    for lc in ("created", "changed", "unchanged", "duplicate"):
        metrics.record_observation_lifecycle(lc)
    for lc in ("created", "changed", "unchanged", "duplicate"):
        assert metrics.OBSERVATION_LIFECYCLE.labels(lifecycle=lc)._value.get() == 1


def test_frontier_rates_are_gauges() -> None:
    metrics.record_frontier_enqueue(12.5)
    metrics.record_frontier_dequeue(10.0)
    assert metrics.FRONTIER_ENQUEUE._value.get() == 12.5
    assert metrics.FRONTIER_DEQUEUE._value.get() == 10.0


def test_scheduler_latency_recorded() -> None:
    with metrics.timed_schedule():
        pass  # simulated decision
    sample = metrics.SCHEDULER_DECISION_LATENCY.collect()[0]
    assert sample.samples
    assert sample.name.startswith("cognitive_scheduler_decision_seconds")
    text = prometheus_client.generate_latest().decode()
    assert "cognitive_scheduler_decision_seconds_count" in text
    assert "cognitive_scheduler_decision_seconds_sum" in text


def test_scheduler_verdicts_total() -> None:
    metrics.record_decision("dispatch")
    metrics.record_decision("defer")
    metrics.record_decision("dispatch")
    assert metrics.SCHEDULER_VERDICTS.labels(verdict="dispatch")._value.get() == 2
    assert metrics.SCHEDULER_VERDICTS.labels(verdict="defer")._value.get() == 1


def test_registry_renders_prometheus_text() -> None:
    reg = metrics.register_metrics()
    metrics.record_collection("http", 42)
    text = prometheus_client.generate_latest().decode()
    assert "cognitive_collector_bytes_total" in text
    assert "cognitive_scheduler_decision_seconds" in text