"""T3-05: tda.features — amplitude/entropy/landscapes/Betti/drift (SC-007/SC-008).

Pure numpy+scipy quantitative features: no gudhi needed, so these run anywhere.
Determinism and drift (content-addressed hashes) are the acceptance criteria.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from tda.features import (
    amplitude,
    betti_curve,
    bottleneck,
    compute_features,
    drift,
    features_digest,
    landscapes,
    persistence_entropy,
    wasserstein,
)

pytestmark = pytest.mark.unit


# -- amplitude ---------------------------------------------------------------


def test_amplitude_empty_is_zero() -> None:
    assert amplitude([]) == 0.0
    assert amplitude([], metric="wasserstein") == 0.0


def test_amplitude_finite_single_class() -> None:
    # one class (0,1): persistence 1 -> bottleneck amp 1, W1 amp 1
    assert amplitude([(0.0, 1.0)]) == 1.0
    assert amplitude([(0.0, 1.0)], metric="wasserstein") == 1.0


def test_amplitude_essential_class_infinite() -> None:
    assert amplitude([(2.0, None)]) == float("inf")


# -- diagram distances -------------------------------------------------------


def test_bottleneck_zero_for_identical() -> None:
    d = [(0.0, 1.0), (1.0, 3.0)]
    assert bottleneck(d, d) == 0.0


def test_bottleneck_both_degrade_cheaper() -> None:
    # far apart points: degrading both onto the diagonal (0.5 and 1.0) beats
    # any point-to-point match (>= 4.0) -> bottleneck is max(0.5, 1.0) = 1.0
    assert bottleneck([(0.0, 1.0)], [(3.0, 5.0)]) == 1.0


def test_bottleneck_point_match_wins() -> None:
    # (0,1) vs (0,2): point-to-point sup cost 1 beats degrade-max(0.5,1.0)
    assert bottleneck([(0.0, 1.0)], [(0.0, 2.0)]) == 1.0


def test_bottleneck_empty_vs_empty() -> None:
    assert bottleneck([], []) == 0.0


def test_bottleneck_essential_births() -> None:
    # two essential classes at different births -> charged by birth gap
    assert bottleneck([(0.0, None)], [(5.0, None)]) == 5.0


def test_wasserstein_identical_and_empty() -> None:
    d = [(0.0, 1.0)]
    assert wasserstein(d, d) == 0.0
    assert wasserstein([], []) == 0.0
    # single class vs empty: degrade onto diagonal at half-persistence
    assert wasserstein(d, []) == 0.5


def test_wasserstein_partial_match() -> None:
    # (0,1) vs (2,4): point match cost 3, or both degrade (0.5 + 1.0) = 1.5
    assert wasserstein([(0.0, 1.0)], [(2.0, 4.0)], q=1.0) == 1.5


# -- persistence entropy -----------------------------------------------------


def test_entropy_empty_and_degenerate() -> None:
    assert persistence_entropy([]) == 0.0
    assert persistence_entropy([(0.0, 5.0)]) == 0.0  # single class: no entropy


def test_entropy_known_value() -> None:
    pairs = [(0.0, 1.0), (0.0, 3.0), (0.0, 6.0)]  # pers: 1, 3, 6
    probs = [1 / 10, 3 / 10, 6 / 10]
    expected = -sum(p * math.log(p) for p in probs)
    assert math.isclose(persistence_entropy(pairs), expected, rel_tol=1e-12)


def test_entropy_ignores_essential() -> None:
    # the (0,None) essential class contributes nothing to entropy
    assert persistence_entropy([(0.0, None), (0.0, 5.0)]) == 0.0


# -- landscapes & Betti ------------------------------------------------------


def test_landscapes_shape_and_peak() -> None:
    # single class (0,2): lambda_1(t) = max(0, min(t, 2-t)) peaks at 1.0
    cells = landscapes([(0.0, 2.0)], k_max=3, n_grid=64)
    assert len(cells) == 3 and all(len(r) == 64 for r in cells)
    lam1 = cells[0]
    # peak lands between grid nodes (2.0/63 spacing); assert near 1.0
    assert max(lam1) == pytest.approx(1.0, abs=0.05)


def test_landscapes_empty() -> None:
    assert landscapes([], k_max=2, n_grid=4) == [[0.0] * 4, [0.0] * 4]


def test_betti_curve_counts_live_classes() -> None:
    curve = betti_curve([(0.0, 2.0), (1.0, 3.0)], n_grid=64)
    midpoint = curve[32]
    # at the grid midpoint both classes are alive
    assert midpoint == 2.0
    assert all(v >= 0.0 for v in curve)


def test_betti_curve_empty() -> None:
    assert betti_curve([]) == [0.0] * 64


# -- drift -------------------------------------------------------------------


def test_drift_identical_is_stable() -> None:
    d = [(0.0, 1.0), (0.0, 2.0)]
    a = drift(d, d)
    b = drift(d, d)
    assert a == b
    assert a["changed"] is False
    assert a["value"] == 0.0
    assert a["prev_hash"] == a["cur_hash"]


def test_drift_detects_change() -> None:
    prev = [(0.0, 1.0)]
    cur = [(0.0, 4.0)]
    out = drift(prev, cur)
    assert out["changed"] is True
    assert out["value"] > 0.0


# -- aggregate payload -------------------------------------------------------


def test_compute_features_deterministic_digest() -> None:
    diagrams = {0: [(0.0, 1.0), (1.0, 3.0)], 1: [(0.1, 0.5)]}
    f1 = compute_features(diagrams, dimensions=(0, 1))
    f2 = compute_features(dict(diagrams), dimensions=(0, 1))
    assert f1 == f2
    assert features_digest(f1) == features_digest(f2)
    assert f1["structural_only"] is True  # I-6: never an identity claim
    assert "entropy" in f1["dimensions"][0]
    assert "betti" in f1["dimensions"][1]


def test_compute_features_structural_only() -> None:
    out = compute_features({0: [(0.0, 1.0)]}, dimensions=(0,))
    assert out["structural_only"] is True