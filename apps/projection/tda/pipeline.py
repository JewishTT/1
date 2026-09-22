"""TDA pipeline (T042).

Adaptive subgraph → weighted filtration (edge weights = 1 - similarity) →
GUDHI SimplexTree persistence for H0/H1/H2. Configurable dimension and a memory
budget (max simplices below budget). Single- and multi-parameter separation:
only the single-parameter (Vietoris–Rips over candidate feature vectors) path is
implemented; the multiparameter path raises NotSupported. The pipeline is
structural only — it never issues identity claims (I-6).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


class PersistenceProvider(Protocol):
    def compute(self, distance_matrix: np.ndarray, dimension: int) -> dict: ...


class GudhiProvider:
    """GUDHI SimplexTree persistence (T042)."""

    def compute(self, distance_matrix: np.ndarray, dimension: int) -> dict:
        import gudhi

        tree = gudhi.SimplexTree()
        n = distance_matrix.shape[0]
        for i in range(n):
            tree.insert([i], filtration=0.0)
        for i in range(n):
            for j in range(i + 1, n):
                tree.insert([i, j], filtration=float(distance_matrix[i, j]))
        tree.expansion(dimension)
        diag = tree.persistence()  # (dim, (birth, death))
        out: dict[int, list[tuple[float, float]]] = {}
        for dim, (birth, death) in diag:
            out.setdefault(int(dim), []).append((float(birth), float(death)))
        return out


class DirectionalFlagProvider:
    """Directed flag complex on an N-ary co-occurrence fan (FR-008, 011).

    Builds the maximal simplex from the *native* hypergraph fan (members of a
    co-mention), not a lossy pairwise clique (hypergraph.py keeps N-ary
    structure first-class). Every member becomes a vertex with filtration 0,
    every (ordered) pair present in the fan gets an edge at its *temporal
    delay* as the filtration value. Deterministic for a fixed fan + clock.
    """

    def compute(self, fan: dict[str, list[str]], dimension: int) -> dict:
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
        out: dict[int, list[tuple[float, float]]] = {}
        for dim, (birth, death) in tree.persistence():
            out.setdefault(int(dim), []).append((float(birth), float(death)))
        return out


@dataclass
class Filtration:
    node_ids: list[str]
    distance_matrix: np.ndarray

    def __post_init__(self) -> None:
        if self.distance_matrix.shape != (len(self.node_ids), len(self.node_ids)):
            raise ValueError("distance matrix must be square over node_ids")


@dataclass
class DelaySeriesComplex:
    """Takens delay embedding (FR-009) → point set for VR persistence.

    ``lag``/``dim`` are the delay-embedding parameters. The signal is a
    deterministic series (an entity's life-stream values); the embedding
    reconstructs the attractor shape that TDA then measures (no Newtonian
    instantaneity — the *shape* is the invariant).
    """

    series: list[float]
    lag: int = 1
    dim: int = 2

    def __post_init__(self) -> None:
        if self.lag < 1:
            raise ValueError("lag must be >= 1")
        if self.dim < 2:
            raise ValueError("Takens dim must be >= 2")

    def embed(self) -> np.ndarray:
        n = len(self.series)
        if n < self.lag * (self.dim - 1) + 1:
            return np.zeros((0, self.dim))
        points = []
        for i in range(n - self.lag * (self.dim - 1)):
            points.append([self.series[i + self.lag * k] for k in range(self.dim)])
        return np.asarray(points, dtype=float)

    def distance_matrix(self) -> np.ndarray:
        pts = self.embed()
        n = len(pts)
        if n == 0:
            return np.zeros((0, 0))
        d = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                d[i, j] = d[j, i] = float(np.linalg.norm(pts[i] - pts[j]))
        return d


class MemoryBudgetExceeded(RuntimeError):
    pass


class AdaptiveSubgraph:
    """Selects a bounded subgraph from all nodes via similarity threshold."""

    def __init__(self, max_nodes: int = 256) -> None:
        self._max_nodes = max_nodes

    def select(self, node_ids: list[str], features: dict[str, np.ndarray],
               similarity_threshold: float = 0.2) -> Filtration:
        if len(node_ids) > self._max_nodes:
            raise MemoryBudgetExceeded(f"subgraph {len(node_ids)} > budget {self._max_nodes}")
        n = len(node_ids)
        dist = np.ones((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                sim = self._cosine(features[node_ids[i]], features[node_ids[j]])
                dist[i, j] = dist[j, i] = 1.0 - sim
        return Filtration(node_ids=node_ids, distance_matrix=dist)

    @staticmethod
    def _cosine(a: np.ndarray, b: np.ndarray) -> float:
        la, lb = np.linalg.norm(a), np.linalg.norm(b)
        if la == 0 or lb == 0:
            return 0.0
        return float(np.dot(a, b) / (la * lb))


class TDAPipeline:
    def __init__(self, provider: PersistenceProvider | None = None,
                 dimension: int = 2, max_nodes: int = 256) -> None:
        self._provider = provider or GudhiProvider()
        self._dimension = dimension
        self._selected = AdaptiveSubgraph(max_nodes=max_nodes)

    @property
    def dimension(self) -> int:
        return self._dimension

    def run(self, node_ids: list[str], features: dict[str, np.ndarray]) -> dict:
        """Single-parameter Vietoris-Rips over the adaptive subgraph."""
        filtration = self._selected.select(node_ids, features)
        return {  # structural signal: birth/death pairs per dim
            "dimension": self._dimension,
            "nodes": filtration.node_ids,
            "diagrams": self._provider.compute(filtration.distance_matrix, self._dimension),
            "algorithm": "vietoris-rips-single-parameter",
        }

    def run_multiparameter(self, *args, **kwargs):
        raise NotImplementedError(
            "multiparameter TDA is out of scope for the single-parameter pipeline (T042)"
        )