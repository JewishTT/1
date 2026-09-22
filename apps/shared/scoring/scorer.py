"""UtilityScorer + AdaptiveState impl (T027, `contracts/utility-scorer.md`, FR-027).

Drives Useful Information Yield / Resource Cost (not req/sec). Scorer is
replaceable behind this contract (learned model implements the same interface).
Admission scores are separate (I-7). Backpressure lag + stopping-policy signals
surface here.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Protocol


class Outcome(str, enum.Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    RETRY = "retry"
    UNCHANGED = "unchanged"
    DUPLICATE = "duplicate"


@dataclass
class UtilityScore:
    utility: float
    priority: float
    expected_novelty: float
    expected_cost: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class AdaptiveState:
    host_key: str
    ewma_latency_ms: float = 100.0
    ewma_error_rate: float = 0.0
    ewma_payload_bytes: float = 0.0
    success_rate: float = 1.0
    retry_rate: float = 0.0
    change_rate: float = 0.5
    discovery_yield: float = 0.0
    concurrency: int = 1
    cooldown_until_ms: int = 0
    last_request_ms: int = 0
    window_n: int = 0
    _alpha: float = 0.2

    def update(self, outcome: Outcome, latency_ms: float, payload_bytes: int = 0, changed: bool = True) -> None:
        self.window_n += 1
        self.ewma_latency_ms = self._alpha * latency_ms + (1 - self._alpha) * self.ewma_latency_ms
        if outcome is Outcome.SUCCESS:
            self.success_rate = self._alpha * 1.0 + (1 - self._alpha) * self.success_rate
            self.retry_rate = self._alpha * 0.0 + (1 - self._alpha) * self.retry_rate
        elif outcome is Outcome.FAILURE:
            self.success_rate = self._alpha * 0.0 + (1 - self._alpha) * self.success_rate
            self.retry_rate = self._alpha * 1.0 + (1 - self._alpha) * self.retry_rate
        else:  # retry
            self.retry_rate = self._alpha * 1.0 + (1 - self._alpha) * self.retry_rate
        self.ewma_error_rate = self._alpha * (1.0 - self.success_rate) + (1 - self._alpha) * self.ewma_error_rate
        if payload_bytes > 0:
            self.ewma_payload_bytes = self._alpha * payload_bytes + (1 - self._alpha) * self.ewma_payload_bytes
        self.change_rate = self._alpha * (1.0 if changed else 0.0) + (1 - self._alpha) * self.change_rate


@dataclass
class SourceState:
    """T111: adaptive state at the SOURCE granularity (yield/change/cost/errors).

    Immutable, copy-on-refresh: each observation produces a new instance so the
    state machine stays history-free and testable. ``utility_factor()`` folds
    the source beliefs into the scheduler's expected gain.
    """

    source_id: str
    source_kind: str = "web"
    yield_rate: float = 0.5
    change_rate: float = 0.5
    freshness: float = 0.5
    cost: float = 0.0
    error_rate: float = 0.0
    independence_yield: float = 0.0
    window_n: int = 0
    _alpha: float = 0.2

    def updated(
        self,
        *,
        outcome: Outcome,
        changed: bool = True,
        cost: float = 0.0,
        independence_yield: float = 0.0,
        fresh: bool = True,
    ) -> "SourceState":
        succeeded = outcome in (Outcome.SUCCESS, Outcome.UNCHANGED, Outcome.DUPLICATE)
        a = self._alpha
        return SourceState(
            source_id=self.source_id,
            source_kind=self.source_kind,
            yield_rate=(1 - a) * self.yield_rate + a * (1.0 if succeeded else 0.0),
            change_rate=(1 - a) * self.change_rate + a * (1.0 if changed else 0.0),
            freshness=(1 - a) * self.freshness + a * (1.0 if fresh else 0.0),
            cost=(1 - a) * self.cost + a * cost,
            error_rate=(1 - a) * self.error_rate + a * (0.0 if succeeded else 1.0),
            independence_yield=(1 - a) * self.independence_yield + a * independence_yield,
            window_n=self.window_n + 1,
            _alpha=self._alpha,
        )

    def utility_factor(self) -> float:
        """1.0 = healthy; compressed by failures, boosted by independence yield."""
        base = 0.5 + 0.5 * self.yield_rate
        independence = 0.5 + 0.5 * self.independence_yield
        reliability = max(0.0, 1.0 - 2.0 * self.error_rate)
        return base * independence * reliability


@dataclass
class WorkerClassState:
    """T112: adaptive state at the WORKER-CLASS granularity.

    Throughput/saturation/latency/failure as copy-on-refresh beliefs; feeds the
    scheduler through ``capacity_factor()`` (resources, R-3).
    """

    worker_class: str
    throughput: float = 0.0
    latency_ms: float = 0.0
    saturation: float = 0.0
    failure_rate: float = 0.0
    queue_age_s: float = 0.0
    window_n: int = 0
    _alpha: float = 0.2

    def updated(
        self,
        *,
        outcome: Outcome,
        latency_ms: float = 0.0,
        throughput: float | None = None,
        saturation: float | None = None,
        queue_age_s: float | None = None,
    ) -> "WorkerClassState":
        a = self._alpha
        failed = outcome is Outcome.FAILURE
        return WorkerClassState(
            worker_class=self.worker_class,
            throughput=(1 - a) * self.throughput + a * (throughput or 0.0),
            latency_ms=(1 - a) * self.latency_ms + a * latency_ms,
            saturation=(1 - a) * self.saturation + a * (saturation or self.saturation),
            failure_rate=(1 - a) * self.failure_rate + a * (1.0 if failed else 0.0),
            queue_age_s=(1 - a) * self.queue_age_s + a * (queue_age_s or 0.0),
            window_n=self.window_n + 1,
            _alpha=self._alpha,
        )

    def capacity_factor(self) -> float:
        """1.0 = idle/healthy; degrades with saturation and failure rate."""
        return max(0.0, 1.0 - self.saturation) * max(0.0, 1.0 - 2.0 * self.failure_rate)


class UtilityScorerProtocol(Protocol):
    def score(self, task: dict, context: dict) -> UtilityScore: ...
    def feature_vector(self, host_key: str) -> AdaptiveState: ...
    def adjust(self, action: str, outcome: Outcome, latency_ms: float = 0.0, payload_bytes: int = 0) -> None: ...


class HeuristicUtilityScorer:
    """Baseline heuristic per contracts/utility-scorer.md (R-3). Replaceable:"""

    def __init__(self) -> None:
        self._host_state: dict[str, AdaptiveState] = {}
        self._source_state: dict[str, SourceState] = {}
        self._worker_state: dict[str, WorkerClassState] = {}
        self._default = AdaptiveState(host_key="*")

    def score(self, task: dict, context: dict) -> UtilityScore:
        configured = {
            "expected_gain": task.get("expected_gain", 0.5),
            "relevance": task.get("relevance", 0.5),
            "novelty": task.get("novelty", 0.5),
            "freshness": task.get("freshness", 0.5),
            "discovery": task.get("discovery_potential", 0.3),
            "source_quality": task.get("source_quality", 0.6),
            "network_cost": task.get("network_cost", 0.1),
            "compute_cost": task.get("compute_cost", 0.1),
            "duplicate_risk": task.get("duplicate_risk", 0.1),
        }
        host = task.get("host_key", "*")
        state = self._host_state.get(host, self._default)

        numerator = (
            configured["expected_gain"]
            * configured["relevance"]
            * configured["novelty"]
            * configured["freshness"]
            * configured["discovery"]
            * configured["source_quality"]
        )
        denominator = (
            configured["network_cost"]
            + configured["compute_cost"]
            + configured["duplicate_risk"]
            + max(state.ewma_error_rate, 1e-9)
        )
        utility = numerator / denominator if denominator > 0 else 0.0

        # T111: source-level adaptive beliefs modulate expected utility.
        source_id = task.get("source_id")
        if source_id:
            source = self._source_state.get(source_id)
            if source is not None:
                utility *= source.utility_factor()

        # T112: worker-class adaptive beliefs modulate utility (capacity-aware).
        worker_class = task.get("worker_class")
        if worker_class:
            worker = self._worker_state.get(worker_class)
            if worker is not None:
                utility *= worker.capacity_factor()

        # Backpressure: downstream lag reduces priority (FR-028, R-11).
        lag = context.get("downstream_lag_s", 0.0)
        if lag > 10.0:
            utility *= max(0.0, 1.0 - (lag - 10.0) / 120.0)

        # Stopping policy signal: decay when marginal yield is low (R-11).
        if state.discovery_yield < 0.02 and state.window_n > 50:
            utility *= 0.5

        priority = min(1.0, utility)
        return UtilityScore(
            utility=utility,
            priority=priority,
            expected_novelty=configured["novelty"],
            expected_cost=denominator,
            reasons=["heuristic-utility-scorer-v1"],
        )

    def feature_vector(self, host_key: str) -> AdaptiveState:
        return self._host_state.setdefault(host_key, AdaptiveState(host_key=host_key))

    def adjust(self, action: str, outcome: Outcome, latency_ms: float = 0.0, payload_bytes: int = 0) -> None:
        host = action if action else "*"
        state = self.feature_vector(host)
        state.update(outcome, latency_ms, payload_bytes)
        if outcome is Outcome.FAILURE:
            state.cooldown_until_ms = 60_000
        else:
            state.cooldown_until_ms = 0

    # --- T111/T112 adaptive state surfaces (source + worker-class levels) ---

    def source_state(self, source_id: str) -> SourceState:
        return self._source_state.setdefault(source_id, SourceState(source_id=source_id))

    def worker_state(self, worker_class: str) -> WorkerClassState:
        return self._worker_state.setdefault(worker_class, WorkerClassState(worker_class=worker_class))

    def adjust_source(
        self,
        source_id: str,
        outcome: Outcome,
        *,
        changed: bool = True,
        cost: float = 0.0,
        independence_yield: float = 0.0,
        fresh: bool = True,
    ) -> SourceState:
        self._source_state[source_id] = self.source_state(source_id).updated(
            outcome=outcome,
            changed=changed,
            cost=cost,
            independence_yield=independence_yield,
            fresh=fresh,
        )
        return self._source_state[source_id]

    def adjust_worker(
        self,
        worker_class: str,
        outcome: Outcome,
        *,
        latency_ms: float = 0.0,
        throughput: float | None = None,
        saturation: float | None = None,
        queue_age_s: float | None = None,
    ) -> WorkerClassState:
        self._worker_state[worker_class] = self.worker_state(worker_class).updated(
            outcome=outcome,
            latency_ms=latency_ms,
            throughput=throughput,
            saturation=saturation,
            queue_age_s=queue_age_s,
        )
        return self._worker_state[worker_class]


def lifecycle_to_outcome(lifecycle: str) -> Outcome:
    """Map ObservationGate lifecycle -> scorer Outcome (feedbacks, T116-T118)."""
    return {
        "created": Outcome.SUCCESS,
        "changed": Outcome.SUCCESS,
        "unchanged": Outcome.UNCHANGED,
        "duplicate": Outcome.DUPLICATE,
        "failed": Outcome.FAILURE,
        "quarantined": Outcome.FAILURE,
    }.get(lifecycle, Outcome.FAILURE)