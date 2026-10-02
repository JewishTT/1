"""Feature 024 T021 -- backpressure must actually reduce the acquisition rate.

Constitution: "downstream queue growth must reduce acquisition rate, not expand
the Kafka backlog."

Pre-repair, ``Dispatcher._dispatch`` passed ``{"downstream_lag_s": 0.0}`` as a
literal. There was no way to express downstream pressure at all, so FR-015 was
unsatisfiable by construction and untestable. Each test below fails against that.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.dispatcher import (  # noqa: E402
    Dispatcher,
    NullProbe,
    PressureSample,
)


class FixedProbe:
    def __init__(self, sample: PressureSample) -> None:
        self._s = sample
        self.calls = 0

    def sample(self) -> PressureSample:
        self.calls += 1
        return self._s


class RampProbe:
    """Pressure that worsens across successive polls."""

    def __init__(self, samples: list[PressureSample]) -> None:
        self._samples = list(samples)

    def sample(self) -> PressureSample:
        return self._samples.pop(0) if self._samples else self._samples


def make_dispatcher(probe, **kw) -> Dispatcher:
    d = Dispatcher.__new__(Dispatcher)
    d._frontier = kw["frontier"]
    d._scorer = kw["scorer"]
    d._policy = kw["policy"]
    d._batch_size = kw.get("batch_size", 10)
    d._producer = None
    d._probe = probe
    d._base_rate_per_s = kw.get("base_rate_per_s", 1.0)
    d._callbacks = []
    d.halted_by_backpressure = 0
    return d


class FakeFrontier:
    def __init__(self, n: int) -> None:
        self.n = n
        self.pops = 0

    def pop_next(self, *, tenant_id=None):
        if self.pops >= self.n:
            return None
        self.pops += 1
        return type("Item", (), {"frontier_id": f"F{self.pops}", "uri": "http://x/", "host_key": "x"})()

    def cooldown(self, *a, **k):
        return None


class FakeScorer:
    def score(self, spec, ctx):
        lag = ctx.get("downstream_lag_s", 0.0)
        return type("S", (), {"utility": 1.0 - min(lag, 120.0) / 240.0})()


class FakePolicy:
    def check(self, **kw):
        return type("D", (), {"value": "ALLOW"})()


def build(probe, n_items=10, batch=10, rate=1.0):
    return make_dispatcher(
        probe,
        frontier=FakeFrontier(n_items),
        scorer=FakeScorer(),
        policy=FakePolicy(),
        batch_size=batch,
        base_rate_per_s=rate,
    )


# --- the constitutional rule -------------------------------------------------

def test_no_pressure_dispatches_full_batch():
    d = build(NullProbe(), n_items=10, batch=10)
    assert len(d.poll_once()) == 10
    assert d.halted_by_backpressure == 0


def test_moderate_lag_reduces_the_batch():
    """lag_scale: <=10s -> 1.0, >=120s -> 0.0, linear between."""
    d = build(FixedProbe(PressureSample(lag_s=65.0)), n_items=50, batch=10)
    dispatched = len(d.poll_once())
    assert 0 < dispatched < 10, f"expected a reduced batch, got {dispatched}"


def test_severe_lag_halts_acquisition_entirely():
    d = build(FixedProbe(PressureSample(lag_s=200.0)), n_items=50, batch=10)
    assert d.poll_once() == []
    assert d.halted_by_backpressure == 1


def test_queue_depth_pressure_halts_acquisition():
    """Depth alone must throttle, independent of lag."""
    d = build(FixedProbe(PressureSample(queue_depth=60_000)), n_items=50, batch=10)
    assert d.poll_once() == []
    assert d.halted_by_backpressure == 1


# --- pressure must reduce rate, never widen the backlog ----------------------

def test_pressure_monotonically_narrows_the_batch():
    samples = [
        PressureSample(lag_s=0.0),
        PressureSample(lag_s=40.0),
        PressureSample(lag_s=80.0),
    ]
    widths = []
    for s in samples:
        d = build(FixedProbe(s), n_items=100, batch=10)
        widths.append(len(d.poll_once()))
    assert widths[0] >= widths[1] >= widths[2], widths
    assert widths[0] > widths[2], "pressure did not reduce acquisition at all"


def test_pressure_never_increases_the_batch():
    calm = build(FixedProbe(PressureSample(lag_s=5.0)), n_items=100, batch=10).poll_once()
    hot = build(FixedProbe(PressureSample(lag_s=115.0)), n_items=100, batch=10).poll_once()
    assert len(hot) < len(calm)


def test_halted_dispatcher_pops_nothing():
    """Nothing may be leased and cooled down under pressure -- that would churn
    leases instead of applying backpressure."""
    frontier = FakeFrontier(50)
    d = build(FixedProbe(PressureSample(lag_s=200.0)), n_items=50)
    d._frontier = frontier
    d.poll_once()
    d.poll_once()
    assert frontier.pops == 0


def test_scorer_receives_real_lag_not_a_literal_zero():
    seen: list[float] = []

    class SpyScorer:
        def score(self, spec, ctx):
            seen.append(ctx["downstream_lag_s"])
            return type("S", (), {"utility": 0.5})()

    d = build(FixedProbe(PressureSample(lag_s=30.0)), n_items=2, batch=2)
    d._scorer = SpyScorer()
    d.poll_once()
    assert seen and all(v == 30.0 for v in seen), seen
    assert 0.0 not in seen


def test_pressure_is_sampled_once_per_tick_not_per_item():
    probe = FixedProbe(PressureSample(lag_s=20.0))
    d = build(probe, n_items=10, batch=10)
    d.poll_once()
    assert probe.calls == 1


def test_effective_rate_is_monotonic_in_lag():
    d = build(NullProbe(), rate=10.0)
    rates = [d.effective_rate(PressureSample(lag_s=x)) for x in (0.0, 30.0, 60.0, 90.0, 120.0)]
    assert rates == sorted(rates, reverse=True)
    assert rates[0] == 10.0
    assert rates[-1] == 0.0


def test_null_probe_is_a_default_not_a_hardcoded_literal():
    d = build(NullProbe())
    assert d.pressure() == PressureSample()
    assert d.effective_rate(PressureSample()) == d._base_rate_per_s