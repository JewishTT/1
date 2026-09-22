"""T3-05: diagram determinism + drift / features (SC-006/SC-007/SC-008)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from tda.diagram import PersistenceDiagram, simplify

pytestmark = pytest.mark.unit


def test_simplify_drops_short_lived() -> None:
    pairs = [(0.0, 0.0), (0.0, 1.0), (2.0, 2.0 + 1e-6), (3.0, 10.0)]
    kept = simplify(pairs, epsilon=0.5)
    assert kept == [(0.0, 1.0), (3.0, 10.0)]


def test_diagram_hash_content_addressable() -> None:
    d1 = PersistenceDiagram({0: [(0.0, 1.0), (2.0, None)], 1: [(0.0, 0.5)]})
    d2 = PersistenceDiagram({0: [(0.0, 1.0), (2.0, None)], 1: [(0.0, 0.5)]})
    assert d1.diagram_hash == d2.diagram_hash
    assert isinstance(d1.diagram_hash, str) and len(d1.diagram_hash) == 64


def test_diagram_hash_changes_on_perturbation() -> None:
    a = PersistenceDiagram({0: [(0.0, 0.7), (1.0, 2.2)]})
    b = PersistenceDiagram({0: [(0.0, 0.7), (1.0, 2.3)]})
    assert a.diagram_hash != b.diagram_hash


def test_structural_claim_is_not_identity() -> None:
    d = PersistenceDiagram({0: [(0.0, 1.0)]})
    claim = d.structural_claim("entity-1")
    assert claim["structural_only"] is True  # I-6
    assert claim["dimensions"] == [0]
    assert claim["classes_by_dim"] == {0: 1}


def test_persistence_inf() -> None:
    from tda.diagram import persistence

    assert persistence(1.0, None) == float("inf")
    assert persistence(1.0, 3.0) == 2.0


def test_to_canonical_reproducible() -> None:
    d = PersistenceDiagram({0: [(0.123456789, 9.0)], 2: [(1.0, None)]})
    assert "0.123456789".startswith(d.to_canonical()) or "0.123456789" in d.to_canonical()
    assert d.to_canonical() == PersistenceDiagram({0: [(0.123456789, 9.0)], 2: [(1.0, None)]}).to_canonical()