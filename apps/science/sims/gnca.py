"""Graph-neural cellular automata: contagion CA + continuous herd dynamics (T072).

Adapted from hive-mind-gnca (MIT): a deterministic, torch/networkx-free port of
the FinancialContagionCA (default rule on an Erdős–Rényi interbank exposure
graph) and of the ContinuousGNCA idea (global herd "laws of motion" through
mean aggregated neighbour messages) with fast/slow memory. Collapse is flagged
by resonance — when fast-update amplitude Λ outstrips the slow-dispersion
baseline η ("Λ > η"), sustained for a minimum window.

   Source repo : donors/hive-mind-gnca (modules/ca.py, gnca_continuous.py)
   License     : MIT
   What changed: PyTorch/PyG/networkx → numpy/stdlib; ER graph built with the
                 stdlib RNG; continuous net uses fixed seeded weights instead
                 of learned MLPs; collapse detector is a deterministic rule.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class FinancialContagionCA:
    """Interbank default-propagation automaton (hive-mind FinancialContagionCA)."""
    num_nodes: int = 100
    edge_prob: float = 0.1
    capital_buffer: float = 0.3
    seed: int = 42
    adjacency: np.ndarray = field(default_factory=lambda: np.zeros((0, 0)))

    def __post_init__(self) -> None:
        if self.adjacency.shape == (0, 0):
            self.adjacency = self._build_row_normalized()

    def _build_row_normalized(self) -> np.ndarray:
        rng = random.Random(self.seed)
        adjacency = np.zeros((self.num_nodes, self.num_nodes))
        for i in range(self.num_nodes):
            for j in range(i + 1, self.num_nodes):
                if rng.random() < self.edge_prob:
                    adjacency[i, j] = 1.0
                    adjacency[j, i] = 1.0
        degrees = adjacency.sum(axis=1, keepdims=True)
        degrees[degrees == 0] = 1.0
        return adjacency / degrees

    def step(self, state: np.ndarray) -> np.ndarray:
        """One default-update step (defaults are absorbing)."""
        exposure = self.adjacency @ state
        return np.clip((exposure > self.capital_buffer).astype(float) + state, 0.0, 1.0)

    def run(
        self,
        initial_defaults: Sequence[int] | None = None,
        *,
        max_steps: int = 60,
    ) -> ContagionRun:
        seed = np.zeros(self.num_nodes)
        if initial_defaults is not None:
            for node in initial_defaults:
                seed[node] = 1.0
        states = [seed]
        default_counts = [int(seed.sum())]
        for _ in range(max_steps):
            if states[-1].sum() == self.num_nodes:
                break
            next_state = self.step(states[-1])
            states.append(next_state)
            default_counts.append(int(next_state.sum()))
            if np.array_equal(next_state, states[-2]):
                break
        return ContagionRun(
            states=np.array(states),
            default_counts=default_counts,
            converged=default_counts[-1] == default_counts[-2],
            steps=len(states),
        )


@dataclass
class ContagionRun:
    """Trajectory of a contagion simulation (deterministic per seed)."""
    states: np.ndarray
    default_counts: list[int]
    converged: bool
    steps: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "steps": self.steps,
            "converged": self.converged,
            "final_defaults": self.default_counts[-1] if self.default_counts else 0,
            "default_trace": self.default_counts,
        }


@dataclass
class HerdDynamics:
    """Continuous GNCA-style herd dynamics with fast/slow memory (deterministic).

    ``x`` is a (N, dim) state field (e.g. price + momentum). Each step the
    neighbourhood mean-message (seeded linear readout) feeds a fast memory
    (short horizon) and a slow memory (long horizon); the field advances by a
    bounded residual of the fast-vs-slow discrepancy.
    """
    num_nodes: int
    dim: int = 4
    edge_prob: float = 0.15
    seed: int = 7
    fast_decay: float = 0.30
    slow_decay: float = 0.90
    learning_rate: float = 0.10

    adjacency: np.ndarray = field(default_factory=lambda: np.zeros((0, 0)))
    weights: np.ndarray = field(default_factory=lambda: np.zeros((0, 0)))
    slow_memory: np.ndarray = field(default_factory=lambda: np.zeros((0, 0)))
    fast_memory: np.ndarray = field(default_factory=lambda: np.zeros((0, 0)))

    def __post_init__(self) -> None:
        base = self.adjacency
        if base.shape == (0, 0):
            base = FinancialContagionCA(
                num_nodes=self.num_nodes, edge_prob=self.edge_prob, seed=self.seed
            ).adjacency
            self.adjacency = base
        if self.weights.size == 0:
            rng = np.random.default_rng(self.seed)
            self.weights = rng.normal(size=(self.dim, self.dim))
        zeros = np.zeros((self.num_nodes, self.dim))
        self.slow_memory = zeros
        self.fast_memory = zeros

    def step(self, x: np.ndarray) -> np.ndarray:
        messages = self.adjacency @ np.tanh(x @ self.weights)
        self.fast_memory = self.fast_decay * self.fast_memory + (1.0 - self.fast_decay) * messages
        self.slow_memory = self.slow_decay * self.slow_memory + (1.0 - self.slow_decay) * messages
        delta = self.learning_rate * (self.fast_memory - self.slow_memory)
        return x + np.tanh(delta)

    def run(self, x0: np.ndarray, *, steps: int = 40) -> HerdRun:
        states = [np.asarray(x0, dtype=float)]
        lambda_series: list[float] = []
        eta_series: list[float] = []
        for _ in range(steps):
            states.append(self.step(states[-1]))
            delta = states[-1] - states[-2]
            lambda_series.append(float(np.mean(np.abs(delta))))
            eta_series.append(float(_dispersion(states[-1])))
        run = HerdRun(
            states=np.array(states),
            lambda_series=lambda_series,
            eta_series=eta_series,
            resonance_threshold=1.0,
        )
        run.collapse_events = run._detect_collapse(min_sustained=3)
        return run


def _dispersion(x: np.ndarray) -> float:
    if x.shape[0] < 2:
        return 0.0
    mean = x.mean(axis=0)
    variances = ((x - mean) ** 2).mean(axis=0)
    return float(np.sqrt(variances.sum()))


@dataclass
class HerdRun:
    """Herd-dynamics trajectory plus the collapse (resonance) detector output."""
    states: np.ndarray
    lambda_series: list[float]
    eta_series: list[float]
    resonance_threshold: float
    collapse_events: list[int] = field(default_factory=list)

    def _detect_collapse(self, *, min_sustained: int) -> list[int]:
        episodes: list[int] = []
        streak = 0
        for index, (lam, eta) in enumerate(zip(self.lambda_series, self.eta_series)):
            resonance = lam / max(eta, 1e-12) > self.resonance_threshold
            streak = streak + 1 if resonance else 0
            if streak == min_sustained:
                episodes.append(index - min_sustained + 1)
        return episodes

    def as_dict(self) -> dict[str, Any]:
        return {
            "final_order_parameter": float(np.abs(self.states[-1].mean())),
            "collapse_events": self.collapse_events,
            "max_lambda": max(self.lambda_series, default=0.0),
            "max_eta": max(self.eta_series, default=0.0),
        }

    def order_parameter(self) -> list[float]:
        return [float(np.abs(state.mean())) for state in self.states]