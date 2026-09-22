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
    """Ginzburg–Landau potential components (donor's GL terms).

    Returns the linear term ``-alpha (control - r_critical) order``, the
    quartic term ``beta order^4``, and the total free-energy proxy.
    """
    linear = -alpha * (control - r_critical) * order
    quartic = beta * order ** 4
    free_energy = linear + quartic
    return {"linear": linear, "quartic": quartic, "free_energy": free_energy}


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


def hysteresis_width(forward_orders: Sequence[float], backward_orders: Sequence[float], control_values: Sequence[float]) -> float:
    """Total symmetric distance between two control sweeps (hysteresis proxy)."""
    forward = [float(value) for value in forward_orders]
    backward = list(reversed([float(value) for value in backward_orders]))
    size = min(len(forward), len(backward), len(control_values))
    if size == 0:
        return 0.0
    area = 0.0
    for index in range(size):
        area += abs(forward[index] - backward[index])
    return area / size


@dataclass(frozen=True)
class PhaseReport:
    """The operator's deterministic verdict on a field trajectory."""
    order_parameter: float
    autocorrelation: float
    regime: str
    free_energy: float
    hysteresis: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "order_parameter": self.order_parameter,
            "lag_one_autocorrelation": self.autocorrelation,
            "regime": self.regime,
            "free_energy": self.free_energy,
            "hysteresis_width": self.hysteresis,
        }


def analyze_trajectory(
    field_path: Sequence[Sequence[float]],
    *,
    control_path: Sequence[float] | None = None,
    backward_field: Sequence[Sequence[float]] | None = None,
    r_critical: float = 1.5,
) -> PhaseReport:
    """Full analysis of a field trajectory → PhaseReport."""
    field = np.asarray(field_path, dtype=float)
    if field.size == 0:
        return PhaseReport(0.0, 0.0, "disordered", 0.0, 0.0)
    final_order = order_parameter(field[-1])
    autocorrelation_values = [float(np.abs(field_step.mean())) for field_step in field]
    autocorrelation = lag_one_autocorrelation(autocorrelation_values)
    control = control_path[-1] if control_path else final_order
    potential = ginzburg_landau_potential(final_order, control=control, r_critical=r_critical)
    hysteresis = 0.0
    if backward_field is not None:
        hysteresis = hysteresis_width(
            [float(np.abs(np.asarray(step).mean())) for step in field],
            [float(np.abs(np.asarray(step).mean())) for step in backward_field],
            control_path or list(range(len(field))),
        )
    return PhaseReport(
        order_parameter=final_order,
        autocorrelation=autocorrelation,
        regime=classify_regime(final_order, autocorrelation),
        free_energy=potential["free_energy"],
        hysteresis=hysteresis,
    )