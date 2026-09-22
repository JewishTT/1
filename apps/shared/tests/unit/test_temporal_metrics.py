"""T2-03: temporal_metrics — burstiness edges + honest empty (SC-005)."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest

from domain.temporal_metrics import (
    burstiness,
    causal_fidelity,
    characteristic_timescale,
    events_per_day,
    temporal_metrics,
)

pytestmark = pytest.mark.unit

T0 = datetime(2024, 1, 1, 0, 0, 0)


def _series(n: int, step_s: float) -> list[datetime]:
    return [T0 + timedelta(seconds=i * step_s) for i in range(n)]


def test_burstiness_periodic_is_minus_one() -> None:
    # perfectly periodic: variance of intervals ~ 0 -> ratio ~ 0 -> B ~ -1
    assert burstiness(_series(10, 60.0)) < -0.9


def test_burstiness_poisson_approx_zero() -> None:
    # exponential intervals => sigma/mu == 1 => B == 0
    import random

    rng = random.Random(42)
    ts = [T0]
    for _ in range(2000):
        ts.append(ts[-1] + timedelta(seconds=rng.expovariate(0.01)))
    assert abs(burstiness(ts)) < 0.05


def test_burstiness_single_burst_is_one() -> None:
    # identical timestamps => mean 0 -> B defined as 1.0 (maximum burst)
    ts = [T0] * 5
    assert burstiness(ts) == 1.0


def test_burstiness_requires_two_events() -> None:
    with pytest.raises(ValueError):
        burstiness([T0])


def test_characteristic_timescale_median() -> None:
    # intervals: [1s, 4s, 4s]; median = 4.0
    ts = [T0, T0 + timedelta(seconds=1), T0 + timedelta(seconds=5), T0 + timedelta(seconds=9)]
    assert characteristic_timescale(ts) == 4.0


def test_causal_fidelity_bounds() -> None:
    # perfectly clocked stream: fidelity ~ 1.0 == static graph behaviour
    assert causal_fidelity(_series(10, 1.0)) >= 0.9
    # a huge time gap severs reachability => fidelity collapses toward 0
    bursty = [
        T0,
        T0 + timedelta(seconds=1),
        T0 + timedelta(seconds=2),
        T0 + timedelta(days=365),
        T0 + timedelta(days=365, seconds=1),
    ]
    # pairs spanning the one-year hole are not temporally reachable
    assert causal_fidelity(bursty) < 0.7


def test_causal_fidelity_trivial_two_events_is_one() -> None:
    # two events = a single edge; no ordering information to weigh (c=1.0)
    assert causal_fidelity([T0, T0 + timedelta(seconds=100)]) == 1.0


def test_temporal_metrics_empty_is_empty_dict() -> None:
    assert temporal_metrics([]) == {}


def test_temporal_metrics_deterministic() -> None:
    a = temporal_metrics(_series(8, 3.0))
    b = temporal_metrics(_series(8, 3.0))
    assert a == b
    assert "n_points" in a and a["n_points"] == 8
    assert -1.0 <= a["burstiness_b"] <= 1.0
    # 2 events exactly one day apart => 2 events/day
    assert events_per_day(_series(2, 86400)) == pytest.approx(2.0, abs=1e-6)