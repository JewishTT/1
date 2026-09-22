"""Schelling segregation on a ring lattice — science fixture (T069).

Concept from ABM_polarisation (no license declared → methods only; clean-room
implementation). The donor runs Schelling-style opinion/neighbourhood models
with tolerance tests on a network. Here a classic Schelling model runs on a
periodic ring: two agent classes plus empty cells; agents are satisfied when
their same-type fraction among neighbours reaches ``tolerance``; unsatisfied
agents relocate to a random empty cell (deterministic, seeded). Output covers
the segregation curve and convergence.

   Source repo : donors/ABM_polarisation (schelling-network.jl, 99_functions.jl)
   License     : NO-LICENSE — methods only (original implementation)
   What changed: Julia/agentpy → seeded pure-python; ring neighbourhood; per-step
                 segregation + satisfaction trace as a dataclass.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any


@dataclass
class SchellingAgent:
    """A resident on the ring."""
    kind: int  # 0 or 1
    satisfied: bool = True


@dataclass
class SchellingRun:
    """Outcome of one seed-parameterized segregation simulation."""
    size: int
    tolerance: float
    converges: bool
    steps: int
    segregation: list[float]
    satisfaction: list[float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "size": self.size,
            "tolerance": self.tolerance,
            "converges": self.converges,
            "steps": self.steps,
            "final_segregation": self.segregation[-1] if self.segregation else 0.0,
            "final_satisfaction": self.satisfaction[-1] if self.satisfaction else 1.0,
            "segregation_trace": self.segregation,
        }


def _neighbors(node: int, size: int, radius: int) -> list[int]:
    return [(node + offset) % size for offset in range(-radius, radius + 1) if offset != 0]


def run_schelling(
    *,
    size: int = 40,
    kind_a: int = 16,
    kind_b: int = 16,
    tolerance: float = 0.5,
    radius: int = 2,
    max_steps: int = 200,
    seed: int = 7,
) -> SchellingRun:
    """Run one Schelling simulation (deterministic given seed)."""
    if kind_a + kind_b > size:
        raise ValueError("agent population exceeds ring size")
    rng = random.Random(seed)
    cells: list[SchellingAgent | None] = [None] * size
    positions: list[int] = list(range(size))
    rng.shuffle(positions)
    for position in positions[:kind_a]:
        cells[position] = SchellingAgent(kind=0)
    for position in positions[kind_a : kind_a + kind_b]:
        cells[position] = SchellingAgent(kind=1)
    empties = [position for position, cell in enumerate(cells) if cell is None]

    segregation_trace: list[float] = []
    satisfaction_trace: list[float] = []

    def same_fraction(node: int) -> float:
        cell = cells[node]
        if cell is None:
            return 0.0
        neighbors = [cells[neighbor] for neighbor in _neighbors(node, size, radius)]
        present = [candidate for candidate in neighbors if candidate is not None]
        if not present:
            return 0.0
        same = sum(1 for candidate in present if candidate.kind == cell.kind)
        return same / len(present)

    for step in range(max_steps):
        for cell in cells:
            if cell is not None:
                cell.satisfied = True
        for node in range(size):
            if cells[node] is None:
                continue
            cells[node].satisfied = same_fraction(node) >= tolerance

        unhappy = [node for node in range(size) if cells[node] is not None and not cells[node].satisfied]
        segregation_trace.append(sum(same_fraction(node) for node in range(size) if cells[node] is not None) / max(kind_a + kind_b, 1))
        satisfaction_trace.append(1.0 - len(unhappy) / max(kind_a + kind_b, 1))

        if not unhappy:
            return SchellingRun(
                size=size,
                tolerance=tolerance,
                converges=True,
                steps=step + 1,
                segregation=segregation_trace,
                satisfaction=satisfaction_trace,
            )

        rng.shuffle(unhappy)
        for node in unhappy:
            if not empties:
                break
            destination = empties.pop(rng.randrange(len(empties)))
            empties.append(node)
            cells[destination], cells[node] = cells[node], None

    return SchellingRun(
        size=size,
        tolerance=tolerance,
        converges=False,
        steps=max_steps,
        segregation=segregation_trace,
        satisfaction=satisfaction_trace,
    )