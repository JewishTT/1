"""T111/T112: adaptive state at source and worker-class granularity.

Pinned behaviors:
  - SourceState: successes raise yield, failures raise error_rate; low
    independence_yield compresses utility; unchanged/duplicate still count as
    delivered observations (not failures)
  - WorkerClassState: saturation + failure_rate compress capacity; failure rate
    decays on success; throughput/latency ema tracked
  - scorer folds both levels into utility: a saturated worker-class OR an
    erroring source lowers the same task's score vs. baseline
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scoring.scorer import (
    HeuristicUtilityScorer,
    Outcome,
    SourceState,
    WorkerClassState,
    lifecycle_to_outcome,
)


class TestSourceState:
    def test_success_raises_yield_failure_raises_error(self) -> None:
        s = SourceState(source_id="src-1").updated(outcome=Outcome.SUCCESS, changed=True)
        s = s.updated(outcome=Outcome.SUCCESS, changed=True)
        assert s.yield_rate > 0.5
        assert s.error_rate == 0.0
        s = s.updated(outcome=Outcome.FAILURE)
        assert s.error_rate > 0.0

    def test_unchanged_and_duplicate_count_as_delivered(self) -> None:
        s = SourceState(source_id="src-1").updated(outcome=Outcome.UNCHANGED, changed=False)
        assert s.yield_rate > 0.5
        assert s.error_rate == 0.0
        s2 = SourceState(source_id="src-1").updated(outcome=Outcome.DUPLICATE, changed=False)
        assert s2.yield_rate > 0.5

    def test_low_independence_yield_compresses_utility(self) -> None:
        low = SourceState(source_id="s", independence_yield=0.0, yield_rate=1.0).utility_factor()
        high = SourceState(source_id="s", independence_yield=1.0, yield_rate=1.0).utility_factor()
        assert low < high
        assert high <= 1.0

    def test_unchanged_lowers_change_rate(self) -> None:
        s = SourceState(source_id="s", change_rate=0.9).updated(
            outcome=Outcome.UNCHANGED, changed=False
        )
        assert s.change_rate < 0.9


class TestWorkerClassState:
    def test_failure_rate_decays_on_success(self) -> None:
        w = WorkerClassState(worker_class="browser").updated(
            outcome=Outcome.FAILURE, latency_ms=900.0
        )
        assert w.failure_rate > 0.0
        w = w.updated(outcome=Outcome.SUCCESS, latency_ms=100.0)
        assert w.failure_rate > 0.0
        assert w.failure_rate < 0.5
        assert w.latency_ms > 0.0

    def test_saturation_compresses_capacity(self) -> None:
        idle = WorkerClassState(worker_class="http", saturation=0.0).capacity_factor()
        busy = WorkerClassState(worker_class="http", saturation=0.9).capacity_factor()
        assert idle > busy
        assert busy >= 0.0

    def test_throughput_tracked(self) -> None:
        w = WorkerClassState(worker_class="http").updated(
            outcome=Outcome.SUCCESS, throughput=12.0, queue_age_s=3.0
        )
        assert w.throughput > 0.0
        assert w.queue_age_s > 0.0


class TestScorerIntegration:
    def _task(self, **overrides) -> dict:
        base = {
            "expected_gain": 1.0,
            "relevance": 1.0,
            "novelty": 1.0,
            "freshness": 1.0,
            "discovery_potential": 1.0,
            "source_quality": 1.0,
            "network_cost": 0.05,
            "compute_cost": 0.05,
            "duplicate_risk": 0.05,
        }
        base.update(overrides)
        return base

    def test_erroring_source_reduces_utility(self) -> None:
        scorer = HeuristicUtilityScorer()
        baseline = scorer.score(self._task(source_id="src-1"), {}).utility
        for _ in range(4):
            scorer.adjust_source("src-1", Outcome.FAILURE)
        degraded = scorer.score(self._task(source_id="src-1"), {}).utility
        assert degraded < baseline

    def test_saturated_worker_class_reduces_utility(self) -> None:
        scorer = HeuristicUtilityScorer()
        baseline = scorer.score(self._task(worker_class="browser"), {}).utility
        scorer.adjust_worker("browser", Outcome.SUCCESS, saturation=0.95)
        assert scorer.score(self._task(worker_class="browser"), {}).utility < baseline

    def test_lifecycle_mapping(self) -> None:
        assert lifecycle_to_outcome("created") is Outcome.SUCCESS
        assert lifecycle_to_outcome("changed") is Outcome.SUCCESS
        assert lifecycle_to_outcome("unchanged") is Outcome.UNCHANGED
        assert lifecycle_to_outcome("duplicate") is Outcome.DUPLICATE
        assert lifecycle_to_outcome("failed") is Outcome.FAILURE