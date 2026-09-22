"""Unit tests: Takens delay embedding helpers (011, FR-009).

Pure numpy-free helpers: determinism (same input ⇒ identical matrix) and honesty
(a too-short series gives an EMPTY embedding — the no-fabrication invariant I-3).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from tda.series import (
    embedding_distance_matrix,
    max_pairwise_distance,
    takens_embed,
)


class TestTakensEmbed:
    def test_embed_dim_and_lag(self):
        matrix = takens_embed([float(i) for i in range(12)], lag=2, dim=3)
        assert len(matrix[0]) == 3
        # point 0 = [s0, s2, s4]
        assert matrix[0] == [0.0, 2.0, 4.0]
        # number of points = n - lag*(dim-1)
        assert len(matrix) == 12 - 2 * 2

    def test_too_short_is_honest_empty(self):
        assert takens_embed([1.0], lag=2, dim=3) == []
        assert takens_embed([], lag=1, dim=2) == []

    def test_params_validate(self):
        with pytest.raises(ValueError):
            takens_embed([1.0, 2.0], lag=0)
        with pytest.raises(ValueError):
            takens_embed([1.0, 2.0], dim=1)

    def test_embed_deterministic(self):
        series = [float(i % 7) for i in range(60)]
        assert takens_embed(series, lag=3, dim=2) == takens_embed(series, lag=3, dim=2)


class TestEmbeddingDistanceMatrix:
    def test_square_symmetric_zero_diagonal(self):
        dm = embedding_distance_matrix([1.0, 4.0, 9.0, 16.0, 25.0], lag=1, dim=2)
        n = len(dm)
        assert n == 4
        for i in range(n):
            assert dm[i][i] == 0.0
            for j in range(n):
                assert dm[i][j] == dm[j][i]

    def test_empty_series_empty_matrix(self):
        assert embedding_distance_matrix([]) == []
        # a single sample cannot embed a 2-d point -> honest empty cloud
        assert embedding_distance_matrix([0.5], lag=1, dim=2) == []

    def test_max_pairwise(self):
        dm = [[0.0, 2.0, 1.0], [2.0, 0.0, 1.0], [1.0, 1.0, 0.0]]
        assert max_pairwise_distance(dm) == 2.0
        assert max_pairwise_distance([[0.0]]) == 0.0