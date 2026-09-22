"""Unit: scale bench invariants at 1M and 10M observation counts (T123/T124).

Imports the bench modules from their on-disk paths (importlib) so this suite is
immune to the pre-existing dual-root ``bench`` quirk: ``pytest`` points at the
repo ``bench`` directory while the wheel-installed ``bench`` package may shadow
it. Loading by file path is layout-agnostic by construction.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "apps" / "shared"))
sys.path.insert(0, str(_REPO / "apps"))

_BENCH = _REPO / "bench"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_scale = _load(
    "bench_scale_disk", _BENCH / "collection" / "bench_scale.py"
)
_chaos = _load(
    "bench_replay_disk", _BENCH / "chaos" / "bench_replay.py"
)

bench_scale = _scale.bench_scale
bench_replay = _chaos.bench_replay

import pytest

pytestmark = pytest.mark.unit


def test_1m_bench_lifecycle_conserves_observations() -> None:
    report = bench_scale(1, quick=True)
    assert report["observations"] == 100_000
    total = sum(report["lifecycle"].values())
    assert total == report["observations"]
    assert report["frontier_unique"] > 0
    assert report["observations_per_sec"] > 0


def test_10m_bench_has_same_projection_shape() -> None:
    report = bench_scale(10, quick=True)
    assert report["observations"] == 1_000_000  # quick cap applied per declared million
    total = sum(report["lifecycle"].values())
    assert total == report["observations"]
    assert report["lifecycle"]["duplicate"] / total == pytest.approx(0.5, abs=1e-6)
    assert report["lifecycle"]["created"] / total == pytest.approx(0.4864865, abs=1e-4)
    assert report["frontier_unique"] > 0


def test_replay_invariants_without_uncovered() -> None:
    replay = bench_replay(records=200, kill_at=70)
    assert replay["processed_before_crash"] == 70
    assert replay["replayed_after_crash"] == 130
    assert replay["uncovered"] == 0
    assert replay["exactly_once_projection"] is True
