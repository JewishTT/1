"""Unit tests: Schelling segregation fixture (T069)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fixtures.schelling import run_schelling


class TestSchelling:
    def test_low_tolerance_converges(self):
        run = run_schelling(size=40, kind_a=16, kind_b=16, tolerance=0.3, radius=2, max_steps=150, seed=7)
        assert run.converges
        assert run.satisfaction[-1] == pytest.approx(1.0)
        assert 0.0 <= run.segregation[-1] <= 1.0
        assert len(run.segregation) == run.steps

    def test_high_tolerance_difficult(self):
        run = run_schelling(size=20, kind_a=8, kind_b=8, tolerance=1.0, radius=1, max_steps=10, seed=3)
        assert len(run.segregation) == 10  # either converged at step<=10 or stalled
        assert run.satisfaction[-1] <= 1.0

    def test_deterministic(self):
        first = run_schelling(size=30, kind_a=12, kind_b=12, tolerance=0.4, seed=5)
        second = run_schelling(size=30, kind_a=12, kind_b=12, tolerance=0.4, seed=5)
        assert first.segregation == second.segregation
        assert first.satisfaction == second.satisfaction
        assert first.converges == second.converges

    def test_population_exceeds_ring_raises(self):
        with pytest.raises(ValueError):
            run_schelling(size=10, kind_a=7, kind_b=7)

    def test_as_dict_contract(self):
        report = run_schelling(size=30, kind_a=12, kind_b=12, tolerance=0.4, seed=5).as_dict()
        for key in ("size", "tolerance", "converges", "steps", "final_segregation", "final_satisfaction"):
            assert key in report