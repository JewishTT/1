"""Integration test: backpressure throttling + retry budgets (T059, US3).

Growing downstream lag/queue depth must throttle dispatch instead of growing an
unbounded Kafka backlog; exhausted retry budgets surface as BudgetExhausted sent
to the dead-letter path — nothing retries forever. Mirrors the Rust dispatcher
contract (T063/T064) via the Python-side throttle facade used by worker
callbacks.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apps" / "control-plane"))

import pytest
from services.throttle import BudgetExhausted, RetryBudget, RetryCounter, lag_scale, rate_limiter


@pytest.mark.integration
class TestBackpressure:
    def test_growing_lag_throttles_to_zero(self) -> None:
        assert rate_limiter(100, 10.0, 5.0) == pytest.approx(10.0)
        assert rate_limiter(100, 10.0, 200.0) == 0.0  # full stop, no backlog growth
        mid = rate_limiter(100, 10.0, 30.0)
        assert 0.0 < mid < 10.0

    def test_queue_depth_throttles(self) -> None:
        assert rate_limiter(1_000, 10.0, 0.0) == 10.0
        assert rate_limiter(50_000, 10.0, 0.0) == 0.0
        assert 0.0 < rate_limiter(10_000, 10.0, 0.0) < 10.0

    def test_lag_scale_monotonic(self) -> None:
        assert lag_scale(0.0) >= lag_scale(30.0) >= lag_scale(120.0)

    def test_retry_budget_per_source_blocks(self) -> None:
        budget = RetryBudget(max_attempts=3, max_per_source=2, max_per_investigation=10)
        counter = RetryCounter()
        counter.record(budget, source_key="src-a", investigation_key="inv-1")
        counter.record(budget, source_key="src-a", investigation_key="inv-1")
        assert not counter.check(budget, source_key="src-a", investigation_key="inv-1")

    def test_retry_budget_exhaustion_raises_to_dlq_path(self) -> None:
        budget = RetryBudget(max_attempts=3, max_per_source=1, max_per_investigation=10)
        counter = RetryCounter()
        counter.record(budget, source_key="src-b", investigation_key="inv-2")
        with pytest.raises(BudgetExhausted):
            counter.record(budget, source_key="src-b", investigation_key="inv-2")

    def test_global_budget_cap(self) -> None:
        budget = RetryBudget(
            max_attempts=2, max_per_source=99, max_per_investigation=99, max_global=1
        )
        counter = RetryCounter()
        counter.record(budget, source_key="s1", investigation_key="i1")
        assert not counter.check(budget, source_key="s2", investigation_key="i2")