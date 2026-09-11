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


class UtilityScorerProtocol(Protocol):
    def score(self, task: dict, context: dict) -> UtilityScore: ...
    def feature_vector(self, host_key: str) -> AdaptiveState: ...
    def adjust(self, action: str, outcome: Outcome, latency_ms: float = 0.0, payload_bytes: int = 0) -> None: ...


class HeuristicUtilityScorer:
    """Baseline heuristic per contracts/utility-scorer.md (R-3). Replaceable:"""

    def __init__(self) -> None:
        self._host_state: dict[str, AdaptiveState] = {}
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