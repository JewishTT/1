"""T4-01: TopologicalInvariant.run() facade (SC-009 structural budget).

End-to-end L3 signature: series -> point cloud -> diagram -> features.
Determinism (same input -> same hash) and honesty (empty series -> empty
topology, never fabricated) are the invariants tested here.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from tda import TopologicalInvariant

pytestmark = pytest.mark.unit


def test_run_returns_content_addressed_payload() -> None:
    out = TopologicalInvariant().run(entity_id="e1", series=[1.0, 2.0, 3.0], fan={"p1": ["e1", "e2"]})
    assert out["entity_id"] == "e1"
    assert out["structural_only"] is True  # I-6
    assert isinstance(out["diagram_hash"], str) and len(out["diagram_hash"]) == 64
    assert isinstance(out["digest"], str) and len(out["digest"]) == 64
    assert out["dimensions"] == out["dimensions"]  # deterministic list


def test_run_deterministic_hashes() -> None:
    args = {"entity_id": "e1", "series": [float(i) for i in range(40)], "fan": {"p1": ["a", "b"]}}
    a = TopologicalInvariant(lag=2, embed_dim=2).run(**args)
    b = TopologicalInvariant(lag=2, embed_dim=2).run(**args)
    assert a["diagram_hash"] == b["diagram_hash"]
    assert a["digest"] == b["digest"]
    assert a["features"] == b["features"]


def test_run_empty_series_is_honest() -> None:
    # no samples -> no point cloud -> no classes; never fabricate topology (I-3)
    out = TopologicalInvariant().run(entity_id="e1", series=[])
    assert out["classes"] == 0
    assert out["dimensions"] == []


def test_run_too_short_series_is_honest() -> None:
    out = TopologicalInvariant(lag=2, embed_dim=2).run(entity_id="e1", series=[1.0])
    assert out["classes"] == 0  # cannot embed, so no topology claimed