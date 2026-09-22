"""Kinetics macro-state graph: transition pathways and order (T057).

Concept from ABa-KiTo (no license declared → methods only; clean-room
implementation). The donor clusters agent trajectories into "nodes"
(macro-states) per tolerance interval, builds a transition adjacency and
extracts dominant pathways. Here that is reduced to a deterministic, stdlib
subset: tolerance grouping of a scalar reaction coordinate into macro-states,
a transition + occupation graph, dominant simple pathways ranked by flux, and
a χ-like order parameter (fraction of time spent in ordered macro-states).

   Source repo : donors/ABa-KiTo (ABRam_BG_V01.py, modules_mokito.py)
   License     : NO-LICENSE — methods only (original implementation)
   What changed: ISOKANN/HDBSCAN/networkx → tolerance grouping + greedy DFS
                 pathway ranking; no machine-learning dependencies.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MacroState:
    """A macro-state (node) defined by a tolerance interval of coordinates."""
    index: int
    lower: float
    upper: float

    @property
    def center(self) -> float:
        return (self.lower + self.upper) / 2.0


def find_intervals(values: Sequence[float], tolerance: float) -> list[MacroState]:
    """Group distinct coordinate values into tolerance intervals (MoKiTo style).

    Values are sorted; a new interval opens whenever the gap to the previous
    value exceeds ``tolerance``. Deterministic.
    """
    if not values:
        return []
    ordered = sorted(set(values))
    intervals: list[MacroState] = []
    lower = ordered[0]
    previous = ordered[0]
    index = 0
    for value in ordered[1:]:
        if value - previous > tolerance:
            intervals.append(MacroState(index=index, lower=lower, upper=previous))
            index += 1
            lower = value
        previous = value
    intervals.append(MacroState(index=index, lower=lower, upper=previous))
    return intervals


def assign_macrostate(value: float, intervals: Sequence[MacroState]) -> int | None:
    for state in intervals:
        if state.lower <= value <= state.upper:
            return state.index
    # gap value: nearest interval wins
    distances = [(abs(value - ((state.lower + state.upper) / 2.0)), state.index) for state in intervals]
    _, index = min(distances, key=lambda pair: (pair[0], pair[1]))
    return index


@dataclass
class MacroTransitionGraph:
    """Macro-state graph with occupation and transition counts."""
    states: list[MacroState] = field(default_factory=list)
    occupation: dict[int, int] = field(default_factory=dict)
    transitions: dict[tuple[int, int], int] = field(default_factory=dict)

    def num_states(self) -> int:
        return len(self.states)

    def transition_density(self) -> float:
        n = self.num_states()
        if n < 2:
            return 0.0
        possible = n * (n - 1)
        return len(self.transitions) / possible if possible else 0.0

    def total_flux(self) -> int:
        return sum(self.transitions.values())

    def as_dict(self) -> dict[str, Any]:
        return {
            "num_states": self.num_states(),
            "occupation": {state: self.occupation.get(state, 0) for state in sorted(self.occupation)},
            "transition_count": len(self.transitions),
            "transition_density": self.transition_density(),
            "total_flux": self.total_flux(),
        }


def build_macro_graph(series: Sequence[float], tolerance: float) -> MacroTransitionGraph:
    """Assign each timestep to a macro-state and count transitions."""
    states = find_intervals(series, tolerance)
    assignments = [assign_macrostate(value, states) for value in series]
    graph = MacroTransitionGraph(states=states)
    for index, assignment in enumerate(assignments):
        if assignment is None:
            continue
        graph.occupation[assignment] = graph.occupation.get(assignment, 0) + 1
        if index > 0:
            previous = assignments[index - 1]
            if previous is not None and assignment != previous:
                key = (previous, assignment)
                graph.transitions[key] = graph.transitions.get(key, 0) + 1
    return graph


@dataclass(frozen=True)
class Pathway:
    """A dominant transition pathway through macro-states."""
    states: tuple[int, ...]
    flux: float

    def as_dict(self) -> dict[str, Any]:
        return {"states": list(self.states), "flux": self.flux}


def dominant_pathways(
    graph: MacroTransitionGraph,
    *,
    max_edges: int = 4,
    top_k: int = 3,
) -> list[Pathway]:
    """Top-k simple pathways ranked by total flow (deterministic).

    A path's flux is its minimum edge weight (weakest link); ties resolve to
    the lexicographically smallest state sequence. DFS prunes at ``max_edges``.
    """
    adjacency: dict[int, list[tuple[int, int]]] = {}
    for (source, target), count in graph.transitions.items():
        adjacency.setdefault(source, []).append((target, count))

    starts = sorted(
        (state for state, count in graph.occupation.items() if count > 0),
        key=lambda state: graph.occupation[state],
        reverse=True,
    )

    results: dict[tuple[int, ...], float] = {}
    for start in starts:
        stack: list[tuple[tuple[int, ...], int]] = [((start,), float("inf"))]
        while stack:
            path, flow = stack.pop()
            if len(path) > 1:
                results.setdefault(path, flow)
            if len(path) - 1 >= max_edges:
                continue
            for target, count in sorted(adjacency.get(path[-1], []), key=lambda pair: (pair[1], pair[0])):
                if target in path:
                    continue
                stack.append((path + (target,), min(flow, float(count))))

    ranked = sorted(
        results.items(),
        key=lambda item: (item[1], item[0]),
        reverse=True,
    )[:top_k]
    return [Pathway(states=path, flux=flow) for path, flow in ranked]


def chi_order(series: Sequence[float], ordered_states: set[int], tolerance: float) -> float:
    """χ-like order parameter: fraction of timesteps in ordered macro-states."""
    if not series:
        return 0.0
    graph = build_macro_graph(series, tolerance)
    consistent = sum(
        count for state, count in graph.occupation.items() if state in ordered_states
    )
    return consistent / len(series)