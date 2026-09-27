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


def _flag_complex(fan: dict[str, list[str]], dimension: int):
    """Mirror of ``DirectionalFlagProvider.compute``'s tree, before persistence.

    Duplicated deliberately: the provider does not expose its SimplexTree, and
    the only way to prove the provider is not silently discarding homological
    classes is to hand the very same complex to gudhi with the zero-length-bar
    filter lifted.
    """
    import gudhi

    tree = gudhi.SimplexTree()
    vertices = sorted({v for members in fan.values() for v in members})
    for v in vertices:
        tree.insert([vertices.index(v)], filtration=0.0)
    for members in fan.values():
        members_idx = sorted(vertices.index(m) for m in members)
        for a in members_idx:
            for b in members_idx:
                if a != b:
                    tree.insert([a, b], filtration=float(b))
    tree.expansion(dimension)
    return tree


def _h1(tree, *, min_persistence: float, persistence_dim_max: bool = False) -> list[tuple[float, float]]:
    return [(b, d) for dim, (b, d) in tree.persistence(
        min_persistence=min_persistence, persistence_dim_max=persistence_dim_max
    ) if dim == 1]


@pytest.mark.skipif(not _has_gudhi(), reason="gudhi not installed")
def test_gudhi_provider_h1_on_a_real_hole() -> None:
    # A 3x3 grid has four genuine VR holes, so the pipeline really does surface
    # H1 — the directed-flag case below cannot, for reasons that are gudhi's.
    pts = [(float(x), float(y)) for x in range(3) for y in range(3)]
    dm = np.zeros((len(pts), len(pts)))
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            dm[i, j] = dm[j, i] = float(np.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]))
    diag = GudhiProvider().compute(dm, dimension=2)
    assert 1 in diag
    assert all(death > birth for birth, death in diag[1])  # non-zero persistence
    assert GudhiProvider().compute(dm, dimension=2) == diag  # and deterministic


@pytest.mark.skipif(not _has_gudhi(), reason="gudhi not installed")
def test_directional_flag_provider_h0_h1() -> None:
    # two disjoint dirigible fans over a shared vertex pool
    fan = {"p1": ["a", "b", "c"], "p2": ["c", "d", "e"], "p3": ["a", "b", "c", "d"]}
    diag = DirectionalFlagProvider().compute(fan, dimension=2)
    # H0: at least one connected class survives
    assert any(dim == 0 for dim in diag)

    # H1: the fan's cycles are real, but every one of them is FILLED at the
    # scale it is born, so no H1 class survives the provider's gudhi defaults.
    #
    # The provider inserts every ordered pair of each fan's members, so the
    # complex is a union of cliques and ``expansion(2)`` makes it the FLAG
    # complex of that graph. A flag complex is homotopy equivalent to its
    # 1-skeleton, and the clique complex of a union of cliques is a union of
    # simplices, hence contractible: H1 is identically 0 for ANY fan, at ANY
    # dimension >= 2. gudhi agrees — it does compute the cycles, but reports
    # each with birth == death, and ``persistence()``'s default
    # ``min_persistence=0`` is strictly-greater, so all of them are filtered.
    # The pure-python science stack applies the same rule
    # (tda/persistence.py: ``death_value > birth_value + ZERO_EPS``).
    assert 1 not in diag

    # ...and the cycles were genuinely computed rather than dropped by the
    # provider: with the zero-length filter lifted they are all there, and all
    # of them are zero-persistence. This assertion is what distinguishes "the
    # flag complex fills every cycle at birth" from "the code threw H1 away".
    computed = _h1(_flag_complex(fan, 2), min_persistence=-1.0)
    assert computed, "gudhi must still see the fan's cycles in H1"
    assert all(death == birth for birth, death in computed)

    # gudhi's other default compounds it: persistence_dim_max=False skips the
    # maximal dimension outright, so dimension=1 has no H1 to report at all.
    assert _h1(_flag_complex(fan, 1), min_persistence=-1.0) == []
    assert _h1(
        _flag_complex(fan, 1), min_persistence=-1.0, persistence_dim_max=True
    ), "the 1-skeleton is the case where the cycles would be infinite"


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