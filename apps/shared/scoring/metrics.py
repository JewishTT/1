"""Collection metrics for the Global Collection Fabric (T114, US1, R-11).

Prometheus vectors tracked by the fabric: collector throughput, observation
lifecycle counts, frontier enqueue/dequeue rates, scheduler decision latency and
verdict distribution. Cost-per-useful-observation (T115) composes the counts
here with the knowledge funnel counters pushed by interpretation/admission.
"""

from __future__ import annotations

import math
import time

from prometheus_client import Counter, Gauge, Histogram
from prometheus_client.registry import CollectorRegistry as Registry

# Collector throughput (bytes) per execution class — network+compute proxy.
COLLECTOR_BYTES = Counter(
    "cognitive_collector_bytes_total", "bytes streamed through the fabric", ["execution_class"]
)

# Lifecycle classification counts from the Observation Gate (T130/T131).
OBSERVATION_LIFECYCLE = Counter(
    "cognitive_observation_lifecycle_total", "gate lifecycle verdicts", ["lifecycle"]
)

# Frontier activity — authoritative Postgres (R-02): rates, not states.
FRONTIER_ENQUEUE = Gauge(
    "cognitive_frontier_enqueue_rate",
    "observations enqueued to frontier per second (EWMA)",
)
FRONTIER_DEQUEUE = Gauge(
    "cognitive_frontier_dequeue_rate",
    "observations dequeued from frontier per second (EWMA)",
)

# Scheduler stages (T110/T132/T133) — decision latency + verdict mix.
SCHEDULER_DECISION_LATENCY = Histogram(
    "cognitive_scheduler_decision_seconds", "two-stage scheduler decision latency"
)
SCHEDULER_VERDICTS = Counter(
    "cognitive_scheduler_verdicts_total", "scheduler decisions", ["verdict"]
)

# Cost-per-useful-observation KPI (T115): useful knowledge findings normalized
# by the cost of the collection funnel that produced them.
USEFUL_FINDINGS = Counter(
    "cognitive_useful_findings_total", "useful findings accepted into knowledge"
)
COLLECTION_COST_USD = Counter(
    "cognitive_collection_cost_usd_total", "accumulated collection spend (USD)"
)
COST_PER_USEFUL = Gauge(
    "cognitive_cost_per_useful_observation",
    "USD per useful finding (findings / (network+compute+storage+worker cost))",
)


def cost_per_useful_observation(total_cost_usd: float, useful_findings: float) -> float:
    """T115 KPI denominator guard: no useful findings -> +inf, not ZeroDivision."""
    if useful_findings <= 0:
        return math.inf
    return max(total_cost_usd, 0.0) / useful_findings


_USEFUL_TOTAL: float = 0.0
_COST_TOTAL: float = 0.0


def record_useful_finding(n: float = 1.0) -> None:
    global _USEFUL_TOTAL
    _USEFUL_TOTAL += n
    USEFUL_FINDINGS.inc(n)


def record_collection_cost(usd: float) -> None:
    global _COST_TOTAL
    _COST_TOTAL += usd
    if _COST_TOTAL > 0:
        COST_PER_USEFUL.set(cost_per_useful_observation(_COST_TOTAL, _USEFUL_TOTAL))
    COLLECTION_COST_USD.inc(usd)


def record_collection(execution_class: str, bytes_: int) -> None:
    """Collector throughput (per R-09 execution-class pricing)."""
    COLLECTOR_BYTES.labels(execution_class=execution_class).inc(bytes_)


def record_observation_lifecycle(lifecycle: str) -> None:
    OBSERVATION_LIFECYCLE.labels(lifecycle=lifecycle).inc()


def record_frontier_enqueue(rate: float) -> None:
    FRONTIER_ENQUEUE.set(rate)


def record_frontier_dequeue(rate: float) -> None:
    FRONTIER_DEQUEUE.set(rate)


class _TimedScheduler:
    """Records decision latency across the two scheduler stages."""

    def __enter__(self) -> _TimedScheduler:
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_exc) -> None:  # noqa: ANN002
        SCHEDULER_DECISION_LATENCY.observe(time.perf_counter() - self._start)


def timed_schedule() -> _TimedScheduler:
    return _TimedScheduler()


def record_decision(verdict: str) -> None:
    SCHEDULER_VERDICTS.labels(verdict=verdict).inc()


def register_metrics() -> Registry:
    """Registry exposing the fabric vectors for /metrics scraping (T073)."""
    reg = Registry()
    for metric in (
        COLLECTOR_BYTES,
        OBSERVATION_LIFECYCLE,
        FRONTIER_ENQUEUE,
        FRONTIER_DEQUEUE,
        SCHEDULER_DECISION_LATENCY,
        SCHEDULER_VERDICTS,
        USEFUL_FINDINGS,
        COLLECTION_COST_USD,
        COST_PER_USEFUL,
    ):
        reg.register(metric)
    return reg