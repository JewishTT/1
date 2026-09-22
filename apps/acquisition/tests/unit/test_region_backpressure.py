"""Region-level backpressure (T113)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))

from dispatcher.regional import RegionBackpressure, RegionPressure, Verdict  # noqa: E402


def test_go_within_capacity() -> None:
    bp = RegionBackpressure(capacity_per_region=10)
    bp.observe(RegionPressure(region="emea", ready_depth=4, in_flight=2, capacity=10))
    assert bp.verdict("emea") == Verdict.GO
    assert bp.can_dispatch("emea")


def test_throttle_when_over_capacity() -> None:
    bp = RegionBackpressure(capacity_per_region=10)
    bp.observe(RegionPressure(region="apac", ready_depth=8, in_flight=5, capacity=10))
    assert bp.verdict("apac") == Verdict.THROTTLE
    assert not bp.can_dispatch("apac")


def test_halt_on_hard_cap() -> None:
    bp = RegionBackpressure(capacity_per_region=10, throttle_factor=1.5)
    bp.observe(RegionPressure(region="emea", ready_depth=12, in_flight=6, capacity=10))
    assert bp.verdict("emea") == Verdict.HALT


def test_halt_on_lag_ceiling() -> None:
    bp = RegionBackpressure(lag_ceiling_s=300)
    pressure = RegionPressure(
        region="amer", ready_depth=1, in_flight=1, capacity=10, oldest_age_s=900
    )
    bp.observe(pressure)
    assert bp.verdict("amer") == Verdict.HALT


def test_missing_region_is_go() -> None:
    assert RegionBackpressure().verdict("nope") == Verdict.GO


def test_observation_updates_verdict_lifecycle() -> None:
    bp = RegionBackpressure(capacity_per_region=10)
    bp.observe(RegionPressure(region="emea", ready_depth=2, in_flight=1, capacity=10))
    assert bp.verdict("emea") == Verdict.GO
    bp.observe(RegionPressure(region="emea", ready_depth=10, in_flight=6, capacity=10))
    assert bp.verdict("emea") == Verdict.HALT
    report = bp.report()
    assert report["emea"]["verdict"] == "halt"
    assert report["emea"]["total"] == 16


def test_region_names_normalized() -> None:
    bp = RegionBackpressure()
    bp.observe(RegionPressure(region="EU-North", ready_depth=0, in_flight=0, capacity=10))
    assert bp.report() is not None
    assert bp.verdict("eu-north") == Verdict.GO