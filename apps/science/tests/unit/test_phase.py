"""Unit tests: phase-transition operators (T071)."""

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from operators.phase import (
    analyze_trajectory,
    classify_regime,
    critical_slowing_factor,
    ginzburg_landau_potential,
    hysteresis_width,
    kuramoto_order,
    lag_one_autocorrelation,
    order_parameter,
)


class TestOrderParameters:
    def test_synchronized_phases(self):
        assert kuramoto_order([0.0, 0.0, 0.0, 0.0]) == pytest.approx(1.0)

    def test_antiphase_cancels(self):
        assert kuramoto_order([0.0, math.pi]) == pytest.approx(0.0)

    def test_order_parameter_on_fields(self):
        assert order_parameter(np.ones((2, 2))) == pytest.approx(1.0)
        assert order_parameter(np.array([1.0, -1.0])) == pytest.approx(0.0)


class TestGinzburgLandau:
    def test_at_critical_linear_term_vanishes(self):
        potential = ginzburg_landau_potential(0.5, control=1.5, r_critical=1.5)
        assert potential["linear"] == pytest.approx(0.0)
        assert potential["free_energy"] == pytest.approx(potential["quartic"])

    def test_energy_is_component_sum(self):
        potential = ginzburg_landau_potential(0.4, control=1.2, r_critical=1.5)
        assert potential["free_energy"] == pytest.approx(potential["linear"] + potential["quartic"])


class TestCriticalSlowing:
    def test_factor_bounded_and_at_far_control_equals_one(self):
        factor = critical_slowing_factor(0.3, control=1.5, r_critical=1.5)
        assert 0.01 <= factor <= 1.0
        assert critical_slowing_factor(2.0, control=0.0, r_critical=1.5) == pytest.approx(1.0)

    def test_autocorrelation_of_constant_is_zero(self):
        assert lag_one_autocorrelation([1, 1, 1, 1, 1]) == pytest.approx(0.0)

    def test_autocorrelation_of_trend_is_high(self):
        assert lag_one_autocorrelation(list(range(20))) > 0.5


class TestRegime:
    def test_regime_labels(self):
        assert classify_regime(0.9, 0.0) == "ordered"
        assert classify_regime(0.2, 0.1) == "disordered"
        assert classify_regime(0.6, 0.0) == "critical"
        assert classify_regime(0.2, 0.9) == "critical"


class TestHysteresis:
    def test_identical_sweeps_zero(self):
        orders = [0.1, 0.4, 0.7, 0.9]
        assert hysteresis_width(orders, list(reversed(orders)), list(range(4))) == pytest.approx(0.0)

    def test_divergent_sweeps_width(self):
        assert hysteresis_width([0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [0, 1, 2]) == pytest.approx(1.0)


class TestAnalyzeTrajectory:
    def test_report_contract(self):
        field = np.zeros((5, 3))
        field[:] = [[0.2] * 3, [0.4] * 3, [0.6] * 3, [0.8] * 3, [1.0] * 3]
        report = analyze_trajectory(field, control_path=[0.0, 0.5, 1.0, 1.5, 2.0])
        assert report.regime in {"ordered", "critical", "disordered"}
        assert report.order_parameter == pytest.approx(1.0)
        assert report.as_dict()["regime"] == report.regime

    def test_empty_trajectory(self):
        report = analyze_trajectory(np.zeros((0, 3)))
        assert report.regime == "disordered"
        assert report.order_parameter == 0.0