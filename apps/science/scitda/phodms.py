"""Spatiotemporal persistent homology: Betti-0 surfaces, rank invariants,
erosion distance (T056). Adapted from PHoDMSs (MIT).

   Source repo : donors/PHoDMSs (https://github.com/asilkoc/PHoDMSs)
   License     : MIT
   What changed: Dionysus/SciPy/multiprocessing → pure-python deterministic
                 subset; Betti-0 surface via min-cone union-find; rank
                 invariant via our own Z₂ reduction (tda.persistence); erosion
                 ported to nested lists (identical shift semantics).

The pipeline mirrors the donor: ``clouds`` is a list of particle clouds over
time; the "cone" over time window [t1, t2] uses the element-wise minimum of
the per-timestep distance matrices, and its β₀ at threshold s is
``betti_zero_surface[s][t1][t2]``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations
from typing import Any

from .persistence import filtration_to_barcodes


@dataclass(frozen=True)
class RankInvariant:
    """A value of the spatiotemporal rank invariant (or a margin verdict)."""
    s1: int
    t1: int
    t2: int
    s2: int
    t3: int
    t4: int
    dim: int
    rank: int
    verdict: str = "valid"

    def as_dict(self) -> dict[str, Any]:
        return {
            "s1": self.s1,
            "t1": self.t1,
            "t2": self.t2,
            "s2": self.s2,
            "t3": self.t3,
            "t4": self.t4,
            "dim": self.dim,
            "rank": self.rank,
            "verdict": self.verdict,
        }


def _distance_matrix(cloud: Sequence[Sequence[float]]) -> list[list[float]]:
    n = len(cloud)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            point_a = cloud[i]
            point_b = cloud[j]
            matrix[i][j] = matrix[j][i] = sum(
                (a - b) ** 2 for a, b in zip(point_a, point_b)
            ) ** 0.5
    return matrix


def _min_cone_distance_matrices(
    clouds: Sequence[Sequence[Sequence[float]]],
) -> list[list[list[float]]]:
    """Element-wise minimum of distance matrices over every time window."""
    per_time = [_distance_matrix(cloud) for cloud in clouds]
    n = len(per_time)
    cones: list[list[list[float] | None]] = [[None] * n for _ in range(n)]
    for t1 in range(n):
        running = [list(row) for row in per_time[t1]]
        for t2 in range(t1, n):
            if t2 > t1:
                for i in range(len(running)):
                    for j in range(len(running)):
                        running[i][j] = min(running[i][j], per_time[t2][i][j])
            cones[t1][t2] = [list(row) for row in running]
    return [list(row) for row in cones]  # type: ignore[return-value]


def cone_simplex_grid(
    clouds: Sequence[Sequence[Sequence[float]]],
    threshold: float,
    *,
    max_dim: int = 1,
) -> list[list[list[set[tuple[int, ...]] | None]]]:
    """VR simplices below ``threshold`` for every time-window cone.

    Simplices of dimension ≤ ``max_dim`` whose maximum pairwise distance in the
    cone is ≤ threshold (faces included so faces precede co-faces).
    """
    cones = _min_cone_distance_matrices(clouds)
    n = len(clouds)
    grid: list[list[list[set[tuple[int, ...]] | None]]] = [
        [[None] * n for _ in range(n)] for _ in range(n)
    ]
    for t1 in range(n):
        for t2 in range(t1, n):
            distances = cones[t1][t2]
            num_points = len(distances)
            present: set[tuple[int, ...]] = {(i,) for i in range(num_points)}
            for dim in range(1, max_dim + 1):
                for sigma in combinations(range(num_points), dim + 1):
                    if not all(facet in present for facet in combinations(sigma, dim)):
                        continue
                    maximum = max(distances[a][b] for a, b in combinations(sigma, 2))
                    if maximum <= threshold:
                        present.add(sigma)
            grid[t1][t2] = present
    return grid


def _component_count(num_points: int, edges: Sequence[tuple[int, int]]) -> int:
    parent = list(range(num_points))

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a: int, b: int) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    for a, b in edges:
        union(a, b)
    return len({find(node) for node in range(num_points)})


def betti_zero_surface(
    clouds: Sequence[Sequence[Sequence[float]]],
    thresholds: Sequence[float],
) -> list[list[list[int]]]:
    """β₀ surface: F[s][t1][t2] = #components of that window's cone.

    The lower triangle (t2 < t1) is zero, matching the donor's half-grid. With
    two particles at distance d, F[s][t1][t2] is 2 below the cone distance and
    1 once the cone at this threshold merges them.
    """
    n = len(clouds)
    m = len(thresholds)
    surface: list[list[list[int]]] = [[[0] * n for _ in range(n)] for _ in range(m)]
    for s_index, threshold in enumerate(thresholds):
        grid = cone_simplex_grid(clouds, threshold, max_dim=1)
        for t1 in range(n):
            for t2 in range(t1, n):
                simplices = grid[t1][t2]
                if simplices is None:
                    continue
                edges = [sigma for sigma in simplices if len(sigma) == 2]
                surface[s_index][t1][t2] = _component_count(len(clouds[0]), edges)
    return surface


def _two_level_complex(
    first: set[tuple[int, ...]],
    second: set[tuple[int, ...]],
) -> tuple[list[tuple[int, ...]], list[float]]:
    """Union complex: first simplices at 0, second-only at 1 (ranks)."""
    combined: dict[tuple[int, ...], float] = {}
    for simplex in first:
        combined[simplex] = 0.0
    for simplex in second:
        if simplex not in combined:
            combined[simplex] = 1.0
    return list(combined), list(combined.values())


def rank_invariant(
    clouds: Sequence[Sequence[Sequence[float]]],
    thresholds: Sequence[float],
    dim: int,
    s1: int,
    t1: int,
    t2: int,
    s2: int,
    t3: int,
    t4: int,
) -> RankInvariant:
    """Spatiotemporal rank invariant (dim-β bars) for the given window pair.

    Mirrors the donor's ``rank_indices``: valid when ``t3 <= t1 <= t2 <= t4``
    and ``s1 <= s2``; margin verdicts return 0/−1 instead of a rank.
    """
    m = len(thresholds)
    n = len(clouds)
    if t3 <= t1 <= t2 <= t4 and s1 <= s2:
        first = cone_simplex_grid(clouds, thresholds[s1], max_dim=dim + 1)[t1][t2]
        second = cone_simplex_grid(clouds, thresholds[s2], max_dim=dim + 1)[t3][t4]
        if first is None or second is None:
            return RankInvariant(s1, t1, t2, s2, t3, t4, dim, 0)
        simplices, values = _two_level_complex(first, second - first)
        barcodes = filtration_to_barcodes(simplices, values, max_dim=dim)
        dimension = barcodes.dimension(dim)
        rank = dimension.num_bars() if dimension is not None else 0
        return RankInvariant(s1, t1, t2, s2, t3, t4, dim, rank)
    radius = min([t1, n - t2 - 1, m - s1 - 1, n - t3 - 1, t4, s2])
    for offset in range(radius):
        if (
            t3 + offset <= t1 - offset
            and t1 - offset <= t2 + offset
            and t2 + offset <= t4 - offset
            and s1 + offset <= s2 - offset
        ):
            return RankInvariant(s1, t1, t2, s2, t3, t4, dim, 0, verdict="in_margin")
    return RankInvariant(s1, t1, t2, s2, t3, t4, dim, -1, verdict="outside_window")


def betti0_erosion_distance(
    f: list[list[list[int]]],
    g: list[list[list[int]]],
    *,
    spacing: int = 1,
    time_weight: int = 1,
    scale_weight: int = 1,
) -> int:
    """Erosion distance between two β₀ surfaces (donor's ``erosion``).

    Returns ``max_shift * spacing`` where ``max_shift`` is the largest number
    of (scale) shifts needed so that one surface dominates the other; 0 means
    the surfaces are already ordered. Deterministic, pure python.
    """
    shape = (len(f), len(f[0]), len(f[0][0]))
    if shape != (len(g), len(g[0]), len(g[0][0])):
        raise ValueError("betti-zero surfaces must have identical shapes")
    i1 = shape[0]

    def element_shift(
        surface: list[list[list[int]]],
        other: list[list[list[int]]],
        i: int,
        j: int,
        k: int,
    ) -> int:
        radius = min(
            (i1 - i - 1) // scale_weight,
            (j - 1) // time_weight if j >= 1 else -1,
            (k - 1) // time_weight if k >= 1 else -1,
        )
        radius = max(radius, 0)
        if surface[i][j][k] >= other[i][j][k] or surface[i][j][k] == 0:
            return 0
        shifted = i + radius * scale_weight
        if shifted >= i1:
            return radius + 1
        if surface[i][j][k] < other[shifted][j - radius * time_weight][k - radius * time_weight]:
            return radius + 1
        low, high = 0, radius
        current = (low + high) // 2
        while high - low > 1:
            shifted = i + current * scale_weight
            if surface[i][j][k] >= other[shifted][j - current * time_weight][k - current * time_weight]:
                high = current
            else:
                low = current
            current = (low + high) // 2
        shifted = i + low * scale_weight
        if surface[i][j][k] >= other[shifted][j - low * time_weight][k - low * time_weight]:
            return low
        return high

    max_shift = 0
    for i in range(i1):
        for j in range(shape[1]):
            for k in range(shape[2]):
                max_shift = max(
                    max_shift,
                    element_shift(f, g, i, j, k),
                    element_shift(g, f, i, j, k),
                )
    return max_shift * spacing