"""Stopping policy (T045).

Tracks marginal information gain per source frontier: when the gain-per-acquire
decays below a threshold for a sustained window the policy returns SLEEP; below
an absolute floor it returns STOP. A frontier explosion (frontier size exceeding
the guard) forces SLEEP to protect budgets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class StopState(str, Enum):
    RUN = "RUN"
    SLEEP = "SLEEP"
    STOP = "STOP"


@dataclass
class SourceStats:
    source_id: str
    gains: list[float] = field(default_factory=list)
    frontier_size: int = 0
    max_history: int = 20


class StoppingPolicy:
    def __init__(
        self,
        sleep_below: float = 0.15,
        stop_below: float = 0.05,
        guard_frontier: int = 100_000,
        window: int = 8,
    ) -> None:
        self._sleep_below = sleep_below
        self._stop_below = stop_below
        self._guard_frontier = guard_frontier
        self._window = window
        self._stats: dict[str, SourceStats] = {}

    def record_gain(self, source_id: str, gain: float) -> None:
        stats = self._stats.setdefault(source_id, SourceStats(source_id=source_id))
        stats.gains.append(gain)
        if len(stats.gains) > stats.max_history:
            stats.gains = stats.gains[-stats.max_history :]

    def set_frontier_size(self, source_id: str, frontier_size: int) -> None:
        self._stats.setdefault(
            source_id, SourceStats(source_id=source_id)
        ).frontier_size = frontier_size

    def state_for(self, source_id: str) -> StopState:
        stats = self._stats.get(source_id)
        if stats is None:
            return StopState.RUN
        if stats.gains:
            recent = stats.gains[-self._window :]
            avg_gain = sum(recent) / len(recent)
            if avg_gain < self._stop_below:
                return StopState.STOP
            if avg_gain < self._sleep_below:
                return StopState.SLEEP
        if stats.frontier_size > self._guard_frontier:
            return StopState.SLEEP  # explosion guard
        return StopState.RUN

    def marginal_gain(self, source_id: str) -> float:
        stats = self._stats.get(source_id)
        if not stats or not stats.gains:
            return 0.0
        recent = stats.gains[-self._window :]
        return sum(recent) / len(recent)
