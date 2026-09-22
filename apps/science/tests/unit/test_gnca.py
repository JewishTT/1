"""Unit tests: graph-neural CA contafion + herd dynamics (T072)."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sims.gnca import FinancialContagionCA, HerdDynamics


class TestContagionCA:
    def test_deterministic(self):
        run_a = FinancialContagionCA(num_nodes=30, edge_prob=0.2, capital_buffer=0.3, seed=11).run([0], max_steps=30)
        run_b = FinancialContagionCA(num_nodes=30, edge_prob=0.2, capital_buffer=0.3, seed=11).run([0], max_steps=30)
        assert np.array_equal(run_a.states, run_b.states)
        assert run_a.default_counts == run_b.default_counts

    def test_defaults_monotonic(self):
        run = FinancialContagionCA(num_nodes=30, edge_prob=0.2, capital_buffer=0.3, seed=11).run([0], max_steps=30)
        counts = run.default_counts
        assert all(counts[i] <= counts[i + 1] for i in range(len(counts) - 1))
        assert counts[0] == 1
        assert 0 < counts[-1] <= 30

    def test_adjacency_row_normalized(self):
        ca = FinancialContagionCA(num_nodes=30, edge_prob=0.2, capital_buffer=0.3, seed=11)
        rowsums = ca.adjacency.sum(axis=1)
        nonzero = rowsums[rowsums > 0]
        assert nonzero.size > 0
        assert np.allclose(nonzero, 1.0)

    def test_as_dict_contract(self):
        report = FinancialContagionCA(num_nodes=30, edge_prob=0.2, seed=11).run([0], max_steps=20).as_dict()
        for key in ("steps", "converged", "final_defaults", "default_trace"):
            assert key in report


class TestHerdDynamics:
    def test_run_shapes(self):
        dyn = HerdDynamics(num_nodes=10, dim=3, edge_prob=0.3, seed=3)
        x0 = np.linspace(-1.0, 1.0, 10).reshape(10, 1).repeat(3, axis=1) * 0.2
        run = dyn.run(x0, steps=20)
        assert run.states.shape == (21, 10, 3)
        assert len(run.lambda_series) == 20
        assert len(run.eta_series) == 20
        assert len(run.order_parameter()) == 21

    def test_collapse_events_bounded_and_sorted(self):
        dyn = HerdDynamics(num_nodes=10, dim=3, edge_prob=0.3, seed=3)
        x0 = np.random.default_rng(0).normal(size=(10, 3))
        run = dyn.run(x0, steps=30)
        assert all(0 <= event < 30 for event in run.collapse_events)
        assert run.collapse_events == sorted(run.collapse_events)

    def test_deterministic(self):
        x0 = np.random.default_rng(5).normal(size=(8, 2)) / 3.0
        run_a = HerdDynamics(num_nodes=8, dim=2, edge_prob=0.4, seed=9).run(x0, steps=15)
        run_b = HerdDynamics(num_nodes=8, dim=2, edge_prob=0.4, seed=9).run(np.copy(x0), steps=15)
        assert np.array_equal(run_a.states, run_b.states)