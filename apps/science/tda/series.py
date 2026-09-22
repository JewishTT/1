"""Takens delay-embedding for topological series analysis (011, FR-009).

A series alone carries no topology: to measure the "shape" of an entity's
life-stream we reconstruct an attractor via delay embedding and feed the
resulting point cloud into VR persistence (`tda.persistence`). Both helpers are
pure functions of the input (I-12): same series + same lag/dim ⇒ byte-identical
embedding, and too-short series honestly produce an EMPTY cloud — never a
fabricated shape (I-3).
"""

from __future__ import annotations

from itertools import combinations
from math import sqrt


def takens_embed(series: list[float], *, lag: int = 1, dim: int = 2) -> list[list[float]]:
    """Embed ``series`` into R^dim using delay coordinates.

    Point i is ``[s[i], s[i+lag], ..., s[i + (dim-1)*lag]]``. Returns an empty
    list when the series is too short to embed even one point (honest-empty).
    """
    if lag < 1:
        raise ValueError("lag must be >= 1")
    if dim < 2:
        raise ValueError("Takens dim must be >= 2")
    need = lag * (dim - 1) + 1
    if len(series) < need:
        return []
    points: list[list[float]] = []
    for i in range(len(series) - (need - 1)):
        points.append([float(series[i + lag * k]) for k in range(dim)])
    return points


def embedding_distance_matrix(
    series: list[float],
    *,
    lag: int = 1,
    dim: int = 2,
) -> list[list[float]]:
    """Euclidean pairwise distances of the Takens embedding (square matrix)."""
    points = takens_embed(series, lag=lag, dim=dim)
    n = len(points)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            distance = sqrt(
                sum((a - b) ** 2 for a, b in zip(points[i], points[j]))
            )
            matrix[i][j] = matrix[j][i] = distance
    return matrix


def max_pairwise_distance(matrix: list[list[float]]) -> float:
    """Largest off-diagonal entry (filtration ceiling for the VR complex)."""
    best = 0.0
    n = len(matrix)
    for a, b in combinations(range(n), 2):
        best = max(best, matrix[a][b])
    return best


__all__ = ["embedding_distance_matrix", "max_pairwise_distance", "takens_embed"]