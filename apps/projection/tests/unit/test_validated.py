"""T3-05: validated.py — stat-validated hyperedge filtering (FR-011)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from tda.validated import (
    ValidatedHyperedgeSet,
    hyperedge_survival,
    order_hyperlaplacian_values,
    validate_hyperedges,
)

pytestmark = pytest.mark.unit


def test_survival_rare_edge_is_surprising() -> None:
    p_low = hyperedge_survival(50, 100, 0.01)  # 50 co-mentions @ 1% baseline
    p_high = hyperedge_survival(2, 100, 0.5)   # 2 co-mentions @ 50% baseline
    assert p_low < p_high


def test_validate_filters_noisy_edges() -> None:
    fans = {
        ("a", "b"): 80,   # very frequent, null_p=0.3 -> significant
        ("c", "d"): 3,    # rare vs null_p=0.3 -> rejected
        ("a", "c", "d"): 40,
    }
    out = validate_hyperedges(fans, n_trials=100, null_p=0.3, alpha=0.05)
    assert isinstance(out, ValidatedHyperedgeSet)
    members = out.to_list()
    assert ("a", "b") in members
    assert ("c", "d") not in members
    assert ("a", "c", "d") in members
    for e in out.valid_edges:
        assert len(e.members) >= 2


def test_validate_deterministic_and_sorted() -> None:
    fans = {("x", "y"): 10, ("y", "z"): 12, ("a", "b", "c"): 9}
    a = validate_hyperedges(fans, n_trials=20, null_p=0.4, alpha=0.05)
    b = validate_hyperedges(fans, n_trials=20, null_p=0.4, alpha=0.05)
    assert a.to_list() == b.to_list()
    assert a.to_list() == sorted(a.to_list())


def test_order_hyperlaplacian_clamped_for_coupled_fan() -> None:
    # perfectly symmetric triangle fan: every vertex has the same total degree,
    # so lamb_min(e) == 0 for every uniform edge (echo chamber signature).
    coupled = {("n1", "n2"): 100, ("n2", "n3"): 100, ("n1", "n3"): 100}
    vals = order_hyperlaplacian_values(coupled, order=2)
    assert vals == [0.0, 0.0, 0.0]
    # hub/star structure => a member dominates every edge => lamb_min < 0
    star = {("hub", "a"): 10, ("hub", "b"): 10, ("a", "b"): 1}
    vals2 = order_hyperlaplacian_values(star, order=2)
    assert vals2
    assert min(vals2) < 0.0
    assert vals2 == sorted(vals2)


def test_empty_fan_cut_is_empty() -> None:
    out = validate_hyperedges({}, n_trials=100, null_p=0.1, alpha=0.05)
    assert len(out) == 0