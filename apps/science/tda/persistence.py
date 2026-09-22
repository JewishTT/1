"""VR persistence: barcodes, Betti curves and agent features (T054).

Adapted from persistence-agent (MIT / Apache-2.0, "SuperInstance Contributors"):
the Vietoris–Rips filtration builder, Z₂ column reduction, barcode container
(Betti curves / mean / max / total persistence) and the AgentFeatures
personality vector (stability / adaptability / depth → archetype).

   Source repo : donors/persistence-agent (https://github.com/superinstance-ai/persistence-agent)
   License     : MIT OR Apache-2.0
   What changed: Rust → pure-python/numpy; simplices stay sorted tuples; column
                 reduction stores columns as sets (XOR = symmetric difference);
                 zero-length bars dropped exactly as ``pairs_to_barcodes`` does.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from itertools import combinations
from typing import Any

INF = float("inf")
ZERO_EPS = 1e-12
MAX_SIMPLICES = 4096


class Metric(Enum):
    EUCLIDEAN = "euclidean"
    MANHATTAN = "manhattan"
    COSINE = "cosine"


@dataclass(frozen=True)
class ActionPoint:
    """A single agent observation in behavior space (point + timestamp)."""
    agent_id: str
    timestamp: float
    features: tuple[float, ...]


class PointCloud:
    """Named points with a deterministic distance matrix (agent dynamics)."""

    def __init__(self, points: list[ActionPoint], metric: Metric = Metric.EUCLIDEAN) -> None:
        self.points = sorted(points, key=lambda point: (point.agent_id, point.timestamp))
        self.metric = metric

    def distance_matrix(self) -> list[list[float]]:
        vectors = [point.features for point in self.points]
        n = len(vectors)
        matrix = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                matrix[i][j] = matrix[j][i] = self._distance(vectors[i], vectors[j])
        return matrix

    def _distance(self, left: Sequence[float], right: Sequence[float]) -> float:
        if self.metric is Metric.EUCLIDEAN:
            return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right)))
        if self.metric is Metric.MANHATTAN:
            return sum(abs(a - b) for a, b in zip(left, right))
        # cosine
        denominator = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
        if denominator == 0.0:
            return 1.0
        return 1.0 - sum(a * b for a, b in zip(left, right)) / denominator

    @property
    def size(self) -> int:
        return len(self.points)


@dataclass(frozen=True)
class VRComplex:
    """Simplicial filtration: sorted simplex tuples + their filtration values."""
    simplices: list[tuple[int, ...]]
    filtration_values: list[float]

    def simplices_of_dim(self, dim: int) -> list[tuple[tuple[int, ...], float]]:
        return [
            (simplex, value)
            for simplex, value in zip(self.simplices, self.filtration_values)
            if len(simplex) == dim + 1
        ]


def _max_pairwise(distance_matrix: list[list[float]], simplex: tuple[int, ...]) -> float:
    best = 0.0
    for a, b in combinations(simplex, 2):
        best = max(best, distance_matrix[a][b])
    return best


def build_filtration(cloud: PointCloud, max_dim: int, *, budget: int = MAX_SIMPLICES) -> VRComplex:
    """Build a full Vietoris–Rips filtration up to ``max_dim``.

    Each simplex appears at its maximum pairwise distance (standard VR flag
    complex); vertices appear at 0. Ordering matches the Rust builder: by
    filtration value, then simplex size, then lexicographic — so faces always
    precede co-faces, which is what the reduction relies on.
    """
    distance_matrix = cloud.distance_matrix()
    n = cloud.size
    simplices: list[tuple[int, ...]] = []
    values: list[float] = []

    for i in range(n):
        simplices.append((i,))
        values.append(0.0)

    previous = [(i,) for i in range(n)]
    for dim in range(1, max_dim + 1):
        candidates = list(combinations(range(n), dim + 1))
        if dim > 1:
            # keep only cliques whose facets are all present in ``previous``
            candidates = [sigma for sigma in candidates if all(
                facet in previous for facet in combinations(sigma, dim)
            )]
        next_simplices: list[tuple[int, ...]] = []
        for sigma in candidates:
            if len(simplices) >= budget:
                raise ValueError(
                    f"filtration exceeds budget ({budget} simplices); "
                    "raise budget or reduce max_dim / points"
                )
            value = _max_pairwise(distance_matrix, sigma)
            simplices.append(sigma)
            values.append(value)
            next_simplices.append(sigma)
        previous = tuple(next_simplices)
        if not previous:
            break

    order = sorted(
        range(len(simplices)),
        key=lambda index: (values[index], len(simplices[index]), simplices[index]),
    )
    return VRComplex(
        simplices=[simplices[index] for index in order],
        filtration_values=[values[index] for index in order],
    )


@dataclass(frozen=True)
class Barcode:
    """Persistence barcode for a single homology dimension."""
    dimension: int
    bars: list[tuple[float, float]] = field(default_factory=list)

    def num_bars(self) -> int:
        return len(self.bars)

    def betti_at(self, eps: float) -> int:
        return sum(
            1
            for birth, death in self.bars
            if birth <= eps + ZERO_EPS and (math.isinf(death) or death > eps)
        )

    def betti_curve(self, eps_values: Sequence[float]) -> list[int]:
        return [self.betti_at(eps) for eps in eps_values]

    def mean_persistence(self) -> float:
        finite = [death - birth for birth, death in self.bars if math.isfinite(death)]
        return (sum(finite) / len(finite)) if finite else 0.0

    def max_persistence(self) -> float:
        return max(
            (death - birth for birth, death in self.bars if math.isfinite(death)),
            default=0.0,
        )

    def total_persistence(self) -> float:
        return sum(death - birth for birth, death in self.bars if math.isfinite(death))


@dataclass(frozen=True)
class BarcodeCollection:
    barcodes: list[Barcode] = field(default_factory=list)

    def dimension(self, dim: int) -> Barcode | None:
        for barcode in self.barcodes:
            if barcode.dimension == dim:
                return barcode
        return None

    def betti_numbers(self, eps: float) -> list[int]:
        return [barcode.betti_at(eps) for barcode in self.barcodes]


def reduce_boundary(simplices: list[tuple[int, ...]], values: list[float]) -> tuple[
    list[set[int]], list[tuple[int, int | None]]
]:
    """Standard column reduction of the Z₂ boundary matrix (persistence-agent).

    Returns ``(reduced_columns, pairs)`` where each pair is ``(birth, death)``
    in simplex-index space (``death=None`` ⇒ feature persists to ∞).
    """
    index_of = {simplex: position for position, simplex in enumerate(simplices)}
    count = len(simplices)
    columns: list[set[int]] = []
    for simplex in simplices:
        boundary = {index_of[facet] for facet in combinations(simplex, len(simplex) - 1)} if len(simplex) > 1 else set()
        columns.append(boundary)

    low_to_column: dict[int, int] = {}
    for column_index in range(count):
        low = max(columns[column_index]) if columns[column_index] else None
        while low is not None and low in low_to_column:
            columns[column_index] ^= columns[low_to_column[low]]
            low = max(columns[column_index]) if columns[column_index] else None
        if low is not None:
            low_to_column[low] = column_index

    pairs: list[tuple[int, int | None]] = []
    paired_death: set[int] = set()
    for column_index in range(count):
        if columns[column_index]:
            low = max(columns[column_index])
            pairs.append((low, column_index))
            paired_death.add(low)
    for column_index in range(count):
        if not columns[column_index] and column_index not in paired_death:
            pairs.append((column_index, None))

    return columns, pairs


def filtration_to_barcodes(
    simplices: list[tuple[int, ...]],
    values: list[float],
    max_dim: int,
) -> BarcodeCollection:
    """Convert a filtration to per-dimension barcodes via Z₂ reduction."""
    _, pairs = reduce_boundary(simplices, values)
    by_dimension: dict[int, list[tuple[float, float]]] = {dim: [] for dim in range(max_dim + 1)}
    for birth_index, death_index in pairs:
        dimension = len(simplices[birth_index]) - 1
        if dimension > max_dim:
            continue
        birth_value = values[birth_index]
        if death_index is None:
            by_dimension[dimension].append((birth_value, INF))
            continue
        death_value = values[death_index]
        if death_value > birth_value + ZERO_EPS:
            by_dimension[dimension].append((birth_value, death_value))
    return BarcodeCollection(
        barcodes=[
            Barcode(dimension=dim, bars=sorted(by_dimension[dim]))
            for dim in range(max_dim + 1)
        ]
    )


def persistence_barcodes(
    cloud: PointCloud,
    max_dim: int = 2,
    *,
    budget: int = MAX_SIMPLICES,
) -> BarcodeCollection:
    """End-to-end: point cloud → VR filtration → per-dimension barcodes."""
    complex_ = build_filtration(cloud, max_dim, budget=budget)
    return filtration_to_barcodes(complex_.simplices, complex_.filtration_values, max_dim)


@dataclass(frozen=True)
class AgentFeatures:
    """Personality vector extracted from persistence barcodes."""
    stability: float
    adaptability: float
    depth: float
    personality_vector: tuple[float, float, float]

    @classmethod
    def from_barcodes(cls, barcodes: BarcodeCollection) -> AgentFeatures:
        stability = cls._compute_stability(barcodes)
        adaptability = cls._compute_adaptability(barcodes)
        depth = cls._compute_depth(barcodes)
        return cls(
            stability=stability,
            adaptability=adaptability,
            depth=depth,
            personality_vector=(stability, adaptability, depth),
        )

    @classmethod
    def _compute_stability(cls, barcodes: BarcodeCollection) -> float:
        h0 = barcodes.dimension(0)
        if h0 is None or h0.num_bars() == 0:
            return 0.0
        infinite = sum(1 for _, death in h0.bars if math.isinf(death))
        return infinite / h0.num_bars()

    @classmethod
    def _compute_adaptability(cls, barcodes: BarcodeCollection) -> float:
        h1 = barcodes.dimension(1)
        if h1 is None:
            return 0.0
        total = h1.num_bars()
        mean = h1.mean_persistence()
        short_lived = sum(1 for birth, death in h1.bars if math.isfinite(death) and death - birth < mean)
        return short_lived / (total + 1)

    @classmethod
    def _compute_depth(cls, barcodes: BarcodeCollection) -> float:
        h2 = barcodes.dimension(2)
        return h2.total_persistence() if h2 is not None else 0.0

    def archetype(self) -> str:
        if self.stability > 0.7 and self.adaptability < 0.3:
            return "Steady"
        if self.adaptability > 0.5 and self.depth > 0.5:
            return "Explorer"
        if self.depth > 0.7:
            return "Deep"
        if self.stability > 0.5 and self.adaptability > 0.3:
            return "Balanced"
        return "Volatile"

    def as_dict(self) -> dict[str, Any]:
        return {
            "stability": self.stability,
            "adaptability": self.adaptability,
            "depth": self.depth,
            "personality_vector": list(self.personality_vector),
            "archetype": self.archetype(),
        }


def from_distance_matrix(
    matrix: Sequence[Sequence[float]],
    *,
    max_dim: int = 2,
    budget: int = MAX_SIMPLICES,
) -> BarcodeCollection:
    """Barcodes straight from an explicit (symmetric) distance matrix."""
    rows = [[float(value) for value in row] for row in matrix]
    n = len(rows)
    simplices: list[tuple[int, ...]] = []
    values: list[float] = []
    for i in range(n):
        simplices.append((i,))
        values.append(0.0)
    previous = [(i,) for i in range(n)]
    for dim in range(1, max_dim + 1):
        candidates = list(combinations(range(n), dim + 1))
        if dim > 1:
            candidates = [sigma for sigma in candidates if all(
                facet in previous for facet in combinations(sigma, dim)
            )]
        next_simplices = []
        for sigma in candidates:
            if len(simplices) >= budget:
                raise ValueError(f"filtration exceeds budget ({budget} simplices)")
            values.append(_max_pairwise(rows, sigma))
            simplices.append(sigma)
            next_simplices.append(sigma)
        previous = tuple(next_simplices)
        if not previous:
            break
    order = sorted(
        range(len(simplices)),
        key=lambda index: (values[index], len(simplices[index]), simplices[index]),
    )
    return filtration_to_barcodes(
        [simplices[index] for index in order],
        [values[index] for index in order],
        max_dim,
    )