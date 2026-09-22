"""T3-05: Takens delay embedding (FR-009) — pure numpy, no gudhi (SC-006).

A periodic signal embeds onto a closed orbit; a collapse (constant or too-short
series) must produce an HONEST empty / degenerate embedding, never garbage — the
no-fabrication invariant (I-3) holds at the embedding step too.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pytest

from tda.pipeline import DelaySeriesComplex

pytestmark = pytest.mark.unit


def test_periodic_signal_embeds_on_closed_orbit() -> None:
    # period-4 square-ish orbit sampled densely; lag=1, dim=2
    period = 4
    series = [float((i % period) / period) for i in range(400)]
    cplx = DelaySeriesComplex(series=series, lag=1, dim=2)
    pts = cplx.embed()
    assert pts.shape[0] > 0
    # adjacent embedded points repeat the orbit: distance between points 1 lag
    # apart is bounded (orbit is closed, not a drift)
    orbit_radius = float(np.linalg.norm(pts[0] - pts[1]))
    assert orbit_radius > 0.0
    # the orbit is periodic -> the same shape recurs at `period` rows
    assert np.allclose(pts[period], pts[0])


def test_sine_embedding_compact() -> None:
    import math

    series = [math.sin(2 * math.pi * i / 40) for i in range(200)]
    cplx = DelaySeriesComplex(series=series, lag=2, dim=2)
    pts = cplx.embed()
    span = float(pts.max() - pts.min())
    assert span > 0.0  # non-degenerate shape
    assert 0.0 < span <= 2.0  # bounded within the sine range


def test_constant_series_collapses_to_zero_distance() -> None:
    cplx = DelaySeriesComplex(series=[5.0] * 50, lag=1, dim=2)
    dm = cplx.distance_matrix()
    assert dm.shape[0] == 49
    assert np.allclose(dm, 0.0)  # a single collapsed point: no topology


def test_too_short_is_honest_empty() -> None:
    # n < lag*(dim-1)+1 -> no embedded points, no fabricated topology (I-3)
    cplx = DelaySeriesComplex(series=[1.0], lag=2, dim=3)
    assert cplx.embed().shape == (0, 3)
    assert cplx.distance_matrix().shape == (0, 0)


def test_higher_dimension_embedding() -> None:
    series = [float(i) for i in range(64)]
    pts = DelaySeriesComplex(series=series, lag=1, dim=4).embed()
    assert pts.shape[1] == 4
    assert pts.shape[0] == 61