"""Backpressure limiter + retry budget enforcement (T063/T064, FR-028, US3).

Python-side mirror of the Rust dispatcher contract used by worker callbacks and
the orchestrator: lag/queue-depth throttles dispatch rate; exhausting a retry
budget routes the item to the dead-letter queue instead of retrying forever.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class BudgetExhausted(Exception):
    pass


def lag_scale(downstream_lag_s: float) -> float:
    if downstream_lag_s <= 10.0:
        return 1.0
    if downstream_lag_s >= 120.0:
        return 0.0
    return 1.0 - (downstream_lag_s - 10.0) / 110.0


def rate_limiter(queue_depth: int, max_rate_per_s: float, downstream_lag_s: float) -> float:
    by_lag = max(0.0, lag_scale(downstream_lag_s))
    if queue_depth <= 1_000:
        by_depth = 1.0
    elif queue_depth >= 50_000:
        by_depth = 0.0
    else:
        by_depth = 1.0 - (queue_depth - 1_000) / 49_000.0
    return max_rate_per_s * by_lag * by_depth


@dataclass
class RetryBudget:
    max_attempts: int = 5
    max_per_source: int = 3
    max_per_investigation: int = 4
    max_global: int | None = None


@dataclass
class RetryCounter:
    attempts: dict[str, int] = field(default_factory=dict)
    global_count: int = 0

    def check(self, budget: RetryBudget, source_key: str | None = None, investigation_key: str | None = None) -> bool:
        if budget.max_attempts <= 0:
            return True
        if source_key and self.attempts.get(source_key, 0) >= budget.max_per_source:
            return False
        if investigation_key and self.attempts.get(investigation_key, 0) >= budget.max_per_investigation:
            return False
        return not (budget.max_global is not None and self.global_count >= budget.max_global)

    def record(self, budget: RetryBudget, source_key: str | None = None, investigation_key: str | None = None) -> None:
        if not self.check(budget, source_key, investigation_key):
            raise BudgetExhausted("retry budget exhausted")
        self.global_count += 1
        if source_key:
            self.attempts[source_key] = self.attempts.get(source_key, 0) + 1
        if investigation_key:
            self.attempts[investigation_key] = self.attempts.get(investigation_key, 0) + 1