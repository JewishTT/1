"""TDA pipeline (T042).

Adaptive subgraph → weighted filtration (edge weights = 1 - similarity) →
GUDHI SimplexTree persistence for H0/H1/H2. Configurable dimension and a memory
budget (max simplices below budget). Single- and multi-parameter separation:
only the single-parameter (Vietoris–Rips over candidate feature vectors) path is
implemented; the multiparameter path raises NotSupported. The pipeline is
structural only — it never issues identity claims (I-6).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from tda.insight import summarise


class PersistenceProvider(Protocol):
    def compute(self, distance_matrix: np.ndarray, dimension: int) -> dict: ...


class GudhiProvider:
    """GUDHI SimplexTree persistence (T042).

    Inserts in one batch. The pairwise ``tree.insert`` loop cost 73 ms at n=256 on its
    own -- small next to persistence, but it is pure interpreter overhead crossing into
    C++ 32 640 times, and ``insert_batch`` does the same work in one call.
    """

    def compute(self, distance_matrix: np.ndarray, dimension: int) -> dict:
        import gudhi

        n = distance_matrix.shape[0]
        tree = gudhi.SimplexTree()

        if n == 0:
            return {}

        # Non-finite distances are pairs the selector dropped; GUDHI must never see them
        # as edges, so they are filtered out of the batch rather than clamped.
        rows, cols = np.nonzero(np.triu(np.isfinite(distance_matrix), k=1))
        filtrations = [float(distance_matrix[i, j]) for i, j in zip(rows, cols, strict=True)]

        tree.insert_batch(np.arange(n, dtype=np.uint32).reshape(1, n), np.zeros(n, dtype=float))
        if len(rows):
            # ``insert_batch`` takes the torch.sparse layout: a (k+1, n) array whose
            # columns are the simplices, not a list of vertex lists. For edges that is a
            # 2 x m array of the paired indices.
            tree.insert_batch(
                np.ascontiguousarray(np.vstack([rows, cols]), dtype=np.uint32),
                np.asarray(filtrations, dtype=float),
            )
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
    structure first-class). Every member becomes a vertex with filtration 0;
    every ordered pair present in the fan gets an edge whose filtration is the
    time that pair first co-occurred.

    **The filtration used to be the vertex index.** ``float(b)`` where ``b`` came
    from ``vertices.index(m)`` is a *position in a sorted list*, not a delay, so the
    filtration was a relabelling of the alphabet: rename the entities and the whole
    diagram moved. The docstring promised "temporal delay" and the unit test copied
    the same expression, so the bug was invisible to the suite.

    Now the filtration is real time, supplied by the caller as ``times`` keyed by fan
    key (the observation that carried the co-occurrence). Without it every edge sits at
    ``0.0`` — one scale, no temporal claim. That is the honest default: the platform
    cannot invent when two entities met, and a fabricated axis would make every
    downstream "when did this loop appear" answer wrong.
    """

    def compute(
        self,
        fan: dict[str, list[str]],
        dimension: int,
        *,
        times: Mapping[str, float] | None = None,
    ) -> dict:
        import gudhi

        tree = gudhi.SimplexTree()
        vertices = sorted({v for members in fan.values() for v in members})
        index = {v: i for i, v in enumerate(vertices)}
        for i in range(len(vertices)):
            tree.insert([i], filtration=0.0)

        # A pair that appears in several fans is born at the earliest of them: the
        # complex only needs the moment the edge came into existence, and taking the
        # latest would report a loop as forming later than it did.
        birth: dict[tuple[int, int], float] = {}
        for key, members in fan.items():
            when = float((times or {}).get(key, 0.0))
            idx = [index[m] for m in members]
            for a in idx:
                for b in idx:
                    if a == b:
                        continue
                    edge = (a, b) if a < b else (b, a)
                    if edge not in birth or when < birth[edge]:
                        birth[edge] = when
        for (a, b), when in birth.items():
            tree.insert([a, b], filtration=when)

        tree.expansion(dimension)
        out: dict[int, list[tuple[float, float]]] = {}
        for dim, (b, d) in tree.persistence():
            out.setdefault(int(dim), []).append((float(b), float(d)))
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
    """Selects a bounded subgraph from all nodes via similarity threshold.

    Speed
    -----
    This was measured at 1.18 s for n=256 before, and the downstream persistence at
    15.4 s, because of two separate defects:

    1. ``similarity_threshold`` was accepted, documented and **never applied**. The class
       therefore built the complete graph -- C(256,2) = 32 640 edges and C(256,3) = 2.7M
       triangles -- no matter how dissimilar the nodes were. Applying it is what makes the
       class do what its own name and signature say.
    2. the pairwise loop recomputed ``features[node_ids[i]]`` inside the inner loop and
       called ``np.dot`` per pair. One normalised matrix product replaces it.

    Both are arithmetic reorganisation, not a change of mathematics: with
    ``similarity_threshold=0`` the distance matrix is the same one the old loop produced,
    which the equivalence test asserts.
    """

    def __init__(self, max_nodes: int = 256, similarity_threshold: float = 0.2) -> None:
        self._max_nodes = max_nodes
        self._similarity_threshold = similarity_threshold

    @property
    def similarity_threshold(self) -> float:
        return self._similarity_threshold

    def select(
        self,
        node_ids: list[str],
        features: dict[str, np.ndarray],
        similarity_threshold: float | None = None,
    ) -> Filtration:
        if len(node_ids) > self._max_nodes:
            raise MemoryBudgetExceeded(f"subgraph {len(node_ids)} > budget {self._max_nodes}")
        threshold = (
            self._similarity_threshold if similarity_threshold is None else similarity_threshold
        )
        n = len(node_ids)
        if n == 0:
            return Filtration(node_ids=[], distance_matrix=np.zeros((0, 0)))

        # Stack once, then one normalised matrix product for every pair at once. The
        # old loop made two dict lookups and a scalar np.dot per pair; this is the same
        # quantity evaluated in C.
        dim = len(next(iter(features.values()))) if features else 0
        matrix = np.empty((n, dim), dtype=np.float64)
        for row, node_id in enumerate(node_ids):
            matrix[row] = features[node_id]
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        # A zero vector has no direction: cosine is undefined, and the old code returned
        # 0.0 for it. Dividing by the clamped norm reproduces that exactly.
        np.divide(matrix, np.where(norms == 0.0, 1.0, norms), out=matrix)
        similarity = matrix @ matrix.T

        dist = 1.0 - similarity
        np.fill_diagonal(dist, 0.0)
        if threshold > 0.0:
            # Dropped pairs become +inf, which GUDHI treats as "this simplex does not
            # exist yet". That is the honest encoding: the edge is not a long edge, it is
            # absent. Capping at a large finite value instead would fabricate a distance.
            np.fill_diagonal(dist, np.inf)
            dist[similarity < threshold] = np.inf
            # Restore the diagonal: a node is never filtered from itself.
            np.fill_diagonal(dist, 0.0)
        return Filtration(node_ids=list(node_ids), distance_matrix=dist)

    @staticmethod
    def _cosine(a: np.ndarray, b: np.ndarray) -> float:
        """Kept for callers that hold two vectors. The batch path is :meth:`select`."""
        la, lb = np.linalg.norm(a), np.linalg.norm(b)
        if la == 0 or lb == 0:
            return 0.0
        return float(np.dot(a, b) / (la * lb))


class TDAPipeline:
    """Single-parameter Vietoris-Rips persistence over the adaptive subgraph.

    Cost is exposed rather than discovered, because the measured spread is three orders
    of magnitude and every one of those orders is a configuration choice:

    ==============  =========================  ==================
    n               configuration              persistence (dim 2)
    ==============  =========================  ==================
    256             threshold 0.0 (complete)   ~9 800 ms
    256             threshold 0.6, clustered    ~89 ms
    64              threshold 0.6, clustered    ~5 ms
    ==============  =========================  ==================

    :meth:`estimate` answers this before the run instead of after it, so a caller can
    choose a threshold or a dimension knowingly.
    """

    def __init__(self, provider: PersistenceProvider | None = None,
                 dimension: int = 2, max_nodes: int = 256,
                 similarity_threshold: float = 0.2,
                 max_simplices: int | None = None,
                 with_insight: bool = True) -> None:
        self._provider = provider or GudhiProvider()
        self._dimension = dimension
        self._selected = AdaptiveSubgraph(
            max_nodes=max_nodes, similarity_threshold=similarity_threshold
        )
        self._max_simplices = max_simplices
        self._insight = with_insight

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def similarity_threshold(self) -> float:
        return self._selected.similarity_threshold

    def estimate(self, node_ids: list[str], features: dict[str, np.ndarray]) -> dict:
        """What ``run`` would cost, computed without running it.

        The simplex count is the whole story: persistence is superlinear in it, and the
        jump from the 1-skeleton to the 2-skeleton is a factor of C(n,2)/1 per vertex --
        2.7M triangles at n=256 against 32 640 edges. Reporting the count lets a caller
        see why a dimension or a threshold has to move.
        """
        import math

        n = len(node_ids)
        filtration = self._selected.select(node_ids, features)
        finite = int(np.count_nonzero(np.isfinite(filtration.distance_matrix)))
        edges = (finite - n) // 2 if n else 0
        triangles: int | None = None
        if edges and self._dimension >= 2:
            # C(n,3) is the worst case, reached only when the selector kept every pair.
            # A thresholded graph has fewer, and the exact number is not derivable from
            # the edge count alone, so the bound is reported rather than a guess.
            triangles = math.comb(n, 3)
        return {
            "nodes": n,
            "edges": edges,
            "triangles_upper_bound": triangles,
            "similarity_threshold": self.similarity_threshold,
            "dimension": self._dimension,
            "max_simplices": self._max_simplices,
        }

    def run(self, node_ids: list[str], features: dict[str, np.ndarray]) -> dict:
        """Single-parameter Vietoris-Rips over the adaptive subgraph."""
        filtration = self._selected.select(node_ids, features)
        cost = self.estimate(node_ids, features)
        if (
            self._max_simplices is not None
            and cost["triangles_upper_bound"] is not None
            and cost["triangles_upper_bound"] > self._max_simplices
        ):
            raise MemoryBudgetExceeded(
                f"run would build up to {cost['triangles_upper_bound']:,} simplices, "
                f"over the declared budget {self._max_simplices:,}; raise "
                f"similarity_threshold above {self._selected.similarity_threshold} "
                f"or lower max_nodes"
            )
        diagrams = self._provider.compute(filtration.distance_matrix, self._dimension)
        # The two named outputs. Persistence gives intervals; a cluster detector and an
        # anomaly list are what a reader of those intervals actually wants, so they are
        # produced here rather than left as a module nobody calls.
        insight = (
            summarise(filtration.node_ids, filtration.distance_matrix, diagrams)
            if self._insight
            else None
        )
        return {  # structural signal: birth/death pairs per dim
            "dimension": self._dimension,
            "nodes": filtration.node_ids,
            "diagrams": diagrams,
            "algorithm": "vietoris-rips-single-parameter",
            "similarity_threshold": self._selected.similarity_threshold,
            "cost": cost,
            "clusters": insight["clusters"] if insight else [],
            "anomalies": insight["anomalies"] if insight else [],
        }

    def run_multiparameter(self, *args, **kwargs):
        raise NotImplementedError(
            "multiparameter TDA is out of scope for the single-parameter pipeline (T042)"
        )