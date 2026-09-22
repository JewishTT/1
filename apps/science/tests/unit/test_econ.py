"""Unit tests: econ crisis ABM + narrative operators (T070/T090)."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from econ.crisis_abm import ABMConfig, run_abm
from econ.operators import (
    BeliefHolder,
    EchoChamberEffect,
    EntropyBoundForecastDecay,
    NarrativeEngine,
)


def _fast_config(n_steps: int = 60) -> ABMConfig:
    return ABMConfig(n_steps=n_steps, n_lp=6, n_spec=8, n_csr=4, metric_window=30)


class TestCrisisABM:
    def test_deterministic_run(self):
        result = run_abm(_fast_config())
        assert result.price.shape == (60,)
        assert np.allclose(run_abm(_fast_config()).price, result.price)

    def test_seed_changes_trajectory(self):
        first = run_abm(_fast_config(), seed=1)
        second = run_abm(_fast_config(), seed=2)
        assert not np.allclose(first.price, second.price)

    def test_summary_contract(self):
        summary = run_abm(_fast_config(80)).summary()
        for key in (
            "n_steps",
            "final_price",
            "final_stress",
            "mean_return",
            "realized_volatility",
            "max_drawdown",
            "mean_spread",
            "stress_events",
            "total_forced_deleveraging",
        ):
            assert key in summary
        assert summary["n_steps"] == 80
        assert summary["max_drawdown"] >= 0.0

    def test_crisis_events_are_valid_indices(self):
        result = run_abm(_fast_config(80))
        for event in result.crisis_events():
            assert 0 <= event < 80

    def test_reserve_migration_ratio_bounded(self):
        ratio = run_abm(_fast_config()).reserve_migration_ratio()
        assert float(ratio.min()) >= 0.0
        assert float(ratio.max()) <= 1.0


class TestNarrativeEngine:
    def test_deterministic(self):
        context = {"Stock_Volatility": 0.7, "market_sentiment": -0.2, "fear_index": 0.6}
        first = NarrativeEngine().generate_narrative(context)
        second = NarrativeEngine().generate_narrative(context)
        assert first.title == second.title
        assert first.impact == second.impact
        assert first.strength == second.strength

    def test_bear_market_narrative(self):
        narrative = NarrativeEngine().generate_narrative({"market_sentiment": -0.5})
        assert narrative.title == "Gold Is Dead"
        assert narrative.impact["gold"] == pytest.approx(-0.2)


class TestEntropyBoundForecastDecay:
    def test_short_history_returns_prediction_unchanged(self):
        decay = EntropyBoundForecastDecay()
        for _ in range(6):
            assert decay.update_forecast(10.0, 10.0) == pytest.approx(10.0)
        assert decay.metrics()["user_count"] == 6

    def test_metrics_contract(self):
        decay = EntropyBoundForecastDecay()
        for _ in range(10):
            decay.update_forecast(10.0, 10.0)
        metrics = decay.metrics()
        assert 0.0 < metrics["avg_accuracy"] <= 1.0
        assert metrics["user_count"] == 10
        assert 0.0 <= metrics["entropy_level"] <= 1.0


class TestEchoChamber:
    def _similar_agents(self) -> list[BeliefHolder]:
        return [
            BeliefHolder("a", trust_government=0.90, risk_appetite=0.90, fear_index=0.10, faith_in_shaman=0.10, belief_in_narrative=0.90),
            BeliefHolder("b", trust_government=0.95, risk_appetite=0.80, fear_index=0.05, faith_in_shaman=0.05, belief_in_narrative=0.90),
        ]

    def test_build_graph_and_density(self):
        chamber = EchoChamberEffect(similarity_threshold=0.9)
        chamber.build_belief_graph(self._similar_agents())
        assert set(chamber.graph) == {"a", "b"}
        assert 0.0 <= chamber.graph_density() <= 1.0

    def test_update_beliefs_bounded(self):
        chamber = EchoChamberEffect(similarity_threshold=0.7)
        agents = [
            BeliefHolder(f"a{i}", trust_government=0.5 + 0.1 * i)
            for i in range(4)
        ]
        chamber.build_belief_graph(agents)
        chamber.update_beliefs(agents, {})
        assert len(chamber.vectors) == 4
        for agent in agents:
            assert 0.0 <= agent.trust_government <= 1.0
        assert 0.0 <= chamber.bubble_risk <= 1.0