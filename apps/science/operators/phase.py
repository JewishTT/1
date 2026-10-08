"""Phase-transition operator: order parameter, critical slowing, hysteresis (T071).

Adapted from cognitive_phase_transitions (MIT, Khomyakov): the Ginzburg–Landau
potential terms, the Kuramoto-like phase-coherence order parameter, critical
slowing down near the transition, and hysteresis measurement between forward /
backward control sweeps — rendered as deterministic stdlib/numpy operators.

   Source repo : donors/cognitive_phase_transitions/scripts/cognitive_phase_transition.py
   License     : MIT
   What changed: online covariance / MPC training dropped; potential terms kept;
                 order parameter and slowing-down factor exposed as pure
                 functions over explicit fields.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np


def kuramoto_order(phases: Sequence[float]) -> float:
    """Kuramoto phase-coherence order parameter r ∈ [0, 1]."""
    if not phases:
        return 0.0
    real = sum(math.cos(phase) for phase in phases)
    imag = sum(math.sin(phase) for phase in phases)
    return math.hypot(real, imag) / len(phases)


def order_parameter(psi: np.ndarray) -> float:
    """|mean(psi)| over a complex or vector field."""
    field = np.asarray(psi)
    if field.size == 0:
        return 0.0
    return float(np.abs(field.mean()))


def ginzburg_landau_potential(
    order: float,
    *,
    alpha: float = 1.0,
    beta: float = 0.5,
    control: float = 0.0,
    r_critical: float = 1.5,
) -> dict[str, float]:
    """Canonical mean-field Ginzburg–Landau free energy ``F(ψ) = -½α(control - r_c)ψ² + ¼βψ⁴``.

    The donor carried the control coupling as a term *linear* in ``ψ``. A linear
    coupling cannot produce the double well that mean-field theory exists to
    describe: it tilts a single minimum and yields no transition. The coupling
    is quadratic here, so for ``control > r_critical`` two degenerate minima
    appear at ``±sqrt(alpha(control - r_critical)/beta)`` and the order
    parameter becomes bistable — which is the phenomenon the operator is named
    for. Donor defect repaired on transfer (``AGENTS.md`` §2).

    Returns the quadratic term, the quartic term, their sum, and the magnitude
    of the stable nonzero minimum (``0.0`` when the origin is the only minimum).
    """
    depth = alpha * (control - r_critical)
    quadratic = -0.5 * depth * order ** 2
    quartic = 0.25 * beta * order ** 4
    minima_abs = math.sqrt(depth / beta) if depth > 0.0 and beta > 0.0 else 0.0
    return {
        "quadratic": quadratic,
        "quartic": quartic,
        "free_energy": quadratic + quartic,
        "minima_abs": minima_abs,
    }


def critical_slowing_factor(
    order: float,
    *,
    control: float,
    r_critical: float = 1.5,
    slowdown_exp: float = 1.0,
) -> float:
    """Dampening applied near the critical surface (donor's ``DPSI_SLOWDOWN_FACTOR``).

    The closer ``control`` is to ``r_critical`` while order stays low, the
    larger the dampening (→ slower response): factor ∈ (0, 1].
    """
    distance = abs(control - r_critical)
    suppression = 1.0 - math.exp(-distance) if order < r_critical else 1.0
    return max(0.01, suppression ** slowdown_exp)


def lag_one_autocorrelation(series: Sequence[float]) -> float:
    """Lag-1 autocorrelation of the de-trended series (critical-slowing proxy)."""
    values = np.asarray([float(value) for value in series])
    if len(values) < 3 or np.allclose(values, values[0]):
        return 0.0
    centered = values - values.mean()
    denominator = float(np.dot(centered[:-1], centered[:-1]))
    if denominator == 0.0:
        return 0.0
    return float(np.dot(centered[:-1], centered[1:]) / denominator)


def classify_regime(order: float, autocorrelation: float) -> str:
    """Three-regime classification deterministically."""
    if order > 0.8:
        return "ordered"
    if order > 0.5 or autocorrelation > 0.8:
        return "critical"
    return "disordered"


def hysteresis_width(
    forward_orders: Sequence[float],
    backward_orders: Sequence[float],
    control_values: Sequence[float],
) -> float:
    """Area enclosed by the forward/backward control sweeps: ``∮M dH``.

    The donor averaged the pointwise separation between the two branches, which
    measures a gap, not a loop, and therefore ignores how far the control was
    actually swept — two sweeps separated by 1 across a wide control range and
    across a narrow one scored identically. Hysteresis is the *area* of the
    cycle, so this integrates the order parameter against the control parameter
    over the closed contour (trapezoidal rule, Green/Poincaré style). Zero when
    the forward branch coincides with the reversed backward branch. Donor
    defect repaired on transfer (``AGENTS.md`` §2).
    """
    forward = [float(value) for value in forward_orders]
    backward = list(reversed([float(value) for value in backward_orders]))
    control = [float(value) for value in control_values]
    size = min(len(forward), len(backward), len(control))
    if size < 2:
        return 0.0
    # Closed contour: forward branch out, backward branch back.
    contour = (
        [(control[i], forward[i]) for i in range(size)]
        + [(control[i], backward[i]) for i in range(size - 1, -1, -1)]
    )
    area = 0.0
    for index in range(len(contour)):
        h_a, m_a = contour[index]
        h_b, m_b = contour[(index + 1) % len(contour)]
        area += 0.5 * (h_b - h_a) * (m_a + m_b)
    return abs(area)

@dataclass(frozen=True)
class PhaseReport:
    """The operator's deterministic verdict on a field trajectory.

    ``dampening`` is the donor's ``DPSI_SLOWDOWN_FACTOR`` applied to the final
    control point. It used to be computed by :func:`critical_slowing_factor` but
    never reached a report, so the critical-slowing claim was untestable from the
    operator's own output.
    """

    order_parameter: float
    autocorrelation: float
    regime: str
    free_energy: float
    hysteresis: float
    dampening: float = 1.0
    minima_abs: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "order_parameter": self.order_parameter,
            "lag_one_autocorrelation": self.autocorrelation,
            "regime": self.regime,
            "free_energy": self.free_energy,
            "hysteresis_width": self.hysteresis,
            "critical_slowing_dampening": self.dampening,
            "minima_abs": self.minima_abs,
        }


def analyze_trajectory(
    field_path: Sequence[Sequence[float]],
    *,
    control_path: Sequence[float] | None = None,
    backward_field: Sequence[Sequence[float]] | None = None,
    r_critical: float = 1.5,
) -> PhaseReport:
    """Full analysis of a field trajectory → PhaseReport.

    Boundary: this consumes an already-computed trajectory of field states, not
    raw samples. Detecting a regime *change* from raw samples is
    ``temporal.changedetect.detect_change_points``; this operator answers "what
    phase is this trajectory in", which is a different question.
    """
    field = np.asarray(field_path, dtype=float)
    if field.size == 0:
        return PhaseReport(0.0, 0.0, "disordered", 0.0, 0.0)
    final_order = order_parameter(field[-1])
    # The order-parameter trajectory itself is the critical-slowing proxy; the
    # donor called this `autocorrelation_values`, which misdescribed it.
    order_series = [float(np.abs(np.asarray(step).mean())) for step in field]
    autocorrelation = lag_one_autocorrelation(order_series)
    control = control_path[-1] if control_path else final_order
    potential = ginzburg_landau_potential(final_order, control=control, r_critical=r_critical)
    dampening = critical_slowing_factor(final_order, control=control, r_critical=r_critical)
    hysteresis = 0.0
    if backward_field is not None:
        hysteresis = hysteresis_width(
            order_series,
            [float(np.abs(np.asarray(step).mean())) for step in backward_field],
            control_path or list(range(len(order_series))),
        )
    return PhaseReport(
        order_parameter=final_order,
        autocorrelation=autocorrelation,
        regime=classify_regime(final_order, autocorrelation),
        free_energy=potential["free_energy"],
        hysteresis=hysteresis,
        dampening=dampening,
        minima_abs=potential["minima_abs"],
    )