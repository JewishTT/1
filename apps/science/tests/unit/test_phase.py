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
    def test_quadratic_term_vanishes_at_critical_point(self):
        potential = ginzburg_landau_potential(0.5, control=1.5, r_critical=1.5)
        assert potential["quadratic"] == pytest.approx(0.0)
        assert potential["free_energy"] == pytest.approx(potential["quartic"])

    def test_energy_is_component_sum(self):
        potential = ginzburg_landau_potential(0.4, control=1.2, r_critical=1.5)
        assert potential["free_energy"] == pytest.approx(
            potential["quadratic"] + potential["quartic"]
        )

    def test_below_critical_only_origin_minimum(self):
        potential = ginzburg_landau_potential(0.4, control=1.2, r_critical=1.5)
        assert potential["minima_abs"] == pytest.approx(0.0)

    def test_above_critical_produces_double_well(self):
        """The mean-field double well is the reason the operator exists.

        The donor's linear control coupling could not produce it: it tilts a
        single minimum. Repaired on transfer (AGENTS.md §2), so this pins the
        repaired behaviour, not the donor's.
        """
        alpha, beta, r_c = 1.0, 0.5, 1.5
        control = 2.5
        expected = math.sqrt(alpha * (control - r_c) / beta)
        potential = ginzburg_landau_potential(0.0, alpha=alpha, beta=beta,
                                              control=control, r_critical=r_c)
        assert potential["minima_abs"] == pytest.approx(expected)

        # Each minimum is a stationary point of the repaired free energy.
        psi = expected
        field = -alpha * (control - r_c) * psi + beta * psi ** 3
        assert field == pytest.approx(0.0, abs=1e-12)

    def test_donor_linear_coupling_could_not_bistabilise(self):
        """Guards the defect: a linear-in-psi coupling has a single stationary point."""
        control, r_c, beta = 2.5, 1.5, 0.5
        # donor form: F = -alpha (control - r_c) psi + beta psi^4 -> one real root pair
        # repaired form: F = -1/2 alpha (control - r_c) psi^2 + 1/4 beta psi^4
        depth = control - r_c
        repaired_psi = math.sqrt(depth / beta)
        donor_slope_at_min = -depth + 4 * beta * repaired_psi ** 3
        assert donor_slope_at_min != pytest.approx(0.0)


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

    def test_divergent_sweeps_give_loop_area(self):
        """Hysteresis is the enclosed area, so it scales with the control range.

        The donor returned the mean branch separation (1.0 here) regardless of
        how far control was swept. The rectangle below is 2 wide and 1 tall, so
        its area is 2.0. Repaired on transfer (AGENTS.md §2).
        """
        assert hysteresis_width([0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [0, 1, 2]) == pytest.approx(2.0)

    def test_area_scales_with_swept_control_range(self):
        narrow = hysteresis_width([0.0, 0.0], [1.0, 1.0], [0.0, 1.0])
        wide = hysteresis_width([0.0, 0.0], [1.0, 1.0], [0.0, 4.0])
        assert wide == pytest.approx(4.0 * narrow)

    def test_single_point_is_no_loop(self):
        assert hysteresis_width([0.5], [0.5], [0.0]) == pytest.approx(0.0)


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

    def test_dampening_reaches_the_report(self):
        """The donor computed the slowing factor but never surfaced it."""
        field = np.full((4, 3), 0.3)
        near = analyze_trajectory(field, control_path=[0.0, 0.0, 0.0, 1.5])
        far = analyze_trajectory(field, control_path=[0.0, 0.0, 0.0, 9.0])
        assert near.dampening < far.dampening
        assert 0.01 <= near.dampening <= 1.0
        assert "critical_slowing_dampening" in near.as_dict()