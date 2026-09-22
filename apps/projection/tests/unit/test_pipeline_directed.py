"""T3-05: directed flag provider + Takens delay embedding (FR-008/009, SC-006)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pytest

from tda.pipeline import (
    DelaySeriesComplex,
    DirectionalFlagProvider,
    Filtration,
    GudhiProvider,
    TDAPipeline,
)

pytestmark = pytest.mark.unit


def _features(node_ids: list[str], dim: int = 4) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(7)
    return {n: rng.normal(size=dim) for n in node_ids}


def _has_gudhi() -> bool:
    try:
        import gudhi  # noqa: F401

        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _has_gudhi(), reason="gudhi not installed")
def test_gudhi_provider_determinism() -> None:
    dm = np.array([[0.0, 0.3, 0.8], [0.3, 0.0, 0.5], [0.8, 0.5, 0.0]])
    a = GudhiProvider().compute(dm, dimension=1)
    b = GudhiProvider().compute(dm, dimension=1)
    assert a == b
    assert 0 in a  # H0 classes present


@pytest.mark.skipif(not _has_gudhi(), reason="gudhi not installed")
def test_directional_flag_provider_h0_h1() -> None:
    # two disjoint dirigible fans over a shared vertex pool
    fan = {"p1": ["a", "b", "c"], "p2": ["c", "d", "e"], "p3": ["a", "b", "c", "d"]}
    diag = DirectionalFlagProvider().compute(fan, dimension=2)
    # H0: at least one connected class survives
    assert any(dim == 0 for dim in diag)
    # the fan forms cycles -> H1 populated for the shared-triangle core
    assert any(dim == 1 for dim in diag)


def test_delay_series_complex_periodic_embedding() -> None:
    # a perfect sine should produce a recognizable torus embedding (compact)
    import math

    series = [math.sin(2 * math.pi * i / 40) for i in range(200)]
    cplx = DelaySeriesComplex(series=series, lag=2, dim=2)
    pts = cplx.embed()
    assert pts.shape[0] > 0 and pts.shape[1] == 2
    dm = cplx.distance_matrix()
    assert dm.shape == (pts.shape[0], pts.shape[0])
    # diagonals zero, symmetric
    assert np.allclose(np.diag(dm), 0.0)
    assert np.allclose(dm, dm.T)


def test_delay_series_complex_too_short() -> None:
    # n=2, lag=1, dim=2: threshold n = 1*(2-1)+1 = 2 -> exactly 1 point
    cplx = DelaySeriesComplex(series=[1.0, 2.0], lag=1, dim=2)
    assert cplx.embed().shape == (1, 2)
    # n < threshold -> empty embedding (honest no-fabrication, I-3)
    too_short = DelaySeriesComplex(series=[1.0], lag=1, dim=2)
    assert too_short.embed().shape == (0, 2)


def test_takens_params_validate() -> None:
    with pytest.raises(ValueError):
        DelaySeriesComplex(series=[1.0], lag=0)
    with pytest.raises(ValueError):
        DelaySeriesComplex(series=[1.0], lag=1, dim=1)


def test_filtration_shape_validation() -> None:
    with pytest.raises(ValueError):
        Filtration(node_ids=["a", "b"], distance_matrix=np.zeros((3, 3)))


@pytest.mark.skipif(not _has_gudhi(), reason="gudhi not installed")
def test_tda_pipeline_runs_single_param() -> None:
    pipe = TDAPipeline(dimension=1, max_nodes=128)
    nodes = ["n1", "n2", "n3", "n4"]
    result = pipe.run(nodes, _features(nodes))
    assert result["algorithm"] == "vietoris-rips-single-parameter"
    assert result["nodes"] == nodes


def test_multiparameter_not_supported() -> None:
    pipe = TDAPipeline(dimension=1)
    with pytest.raises(NotImplementedError):
        pipe.run_multiparameter()