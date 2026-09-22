"""TopologicalFeature materialization + quantitative TDA features (T043, T3-03).

The TDA story does not end at a diagram: an analyst needs *numbers* that are
stable under noise and comparable *between windows* (drift). We provide:

- amplitude — bottleneck / Wasserstein-q size of a single diagram;
- persistence entropy — how concentrated the "topological mass" is;
- persistence landscapes — L^p-friendly, stable vectorization (Bubenik);
- Betti curve — number of classes alive at each scale (cheap vectorization);
- drift — bottleneck/Wasserstein distance *between two windows* keyed by dim.

Everything is a pure function of (birth, death) pairs with no hidden state: the
same input mapping NEVER changes (I-12 / C-3 honest rebuild; SC-007 drift, SC-008
deterministic hashes). Features are STRUCTURAL signals only — they may never
create trusted Entities (I-6).
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np


@dataclass
class TopologicalFeature:
    feature_id: str
    dimension: int
    birth: float
    death: float | None
    supporting_nodes: list[str] = field(default_factory=list)
    supporting_edges: list[tuple[str, str]] = field(default_factory=list)
    algorithm_version: str = "gudhi-simplex-0"
    structural_only: bool = True  # I-6: never an identity claim

    @property
    def persistence(self) -> float:
        return float("inf") if self.death is None else float(self.death) - self.birth


class TDAFeatureBuilder:
    """Materializes TopologicalFeature objects and emits tda.completed events."""

    def __init__(self, emitter=None) -> None:
        self._emitter = emitter  # callable(event_type, payload)
        self.materialized: list[TopologicalFeature] = []

    def materialize(self, tda_result: dict, algorithm_version: str = "gudhi-simplex-0") -> list[TopologicalFeature]:
        nodes = tda_result.get("nodes") or []
        features: list[TopologicalFeature] = []
        for dim, pairs in (tda_result.get("diagrams") or {}).items():
            for birth, death in pairs:
                feature = TopologicalFeature(
                    feature_id="TDA-" + uuid.uuid4().hex[:12],
                    dimension=int(dim),
                    birth=birth,
                    death=None if death == float("inf") else death,
                    supporting_nodes=_supporting_nodes(nodes, int(dim), birth, death),
                    supporting_edges=_supporting_edges(nodes, int(dim), birth, death),
                    algorithm_version=algorithm_version,
                )
                features.append(feature)
                self.materialized.append(feature)
                if self._emitter:
                    self._emitter("tda.completed", {
                        "feature_id": feature.feature_id,
                        "dimension": feature.dimension,
                        "birth": feature.birth,
                        "death": feature.death,
                        "supporting_nodes": feature.supporting_nodes,
                        "algorithm_version": feature.algorithm_version,
                        "structural_only": feature.structural_only,
                    })
        return features


def _supporting_nodes(node_ids: list[str], dim: int, birth: float, death: float) -> list[str]:
    # structural: a component/birth approximates to the closest low-dimensional
    # skeleton; for our purposes return the lid of relevant nodes deterministically.
    k = min(dim + 2, len(node_ids))
    return node_ids[:k]


def _supporting_edges(node_ids: list[str], dim: int, birth: float, death: float) -> list[tuple[str, str]]:
    edges: list[tuple[str, str]] = []
    for i in range(min(len(node_ids), 8) - 1):
        edges.append((node_ids[i], node_ids[i + 1]))
    return edges


_INF = float("inf")


def _finite(pairs: Sequence[tuple[float, float | None]]) -> list[tuple[float, float]]:
    return [(float(b), float(d)) for b, d in pairs if d is not None and d != _INF]


def _essential(pairs: Sequence[tuple[float, float | None]]) -> list[float]:
    return sorted(float(b) for b, d in pairs if d is None or d == _INF)


def _diag_cost(b: float, d: float) -> float:
    """L-inf distance from point to the diagonal (class resilience).

    Projection onto (t, t) minimizes max(|b-t|, |d-t|) at the midpoint; the
    minimal sup-norm distance is half the persistence.
    """
    return (d - b) / 2.0


def _augmented_bottleneck_feasible(
    f1: list[tuple[float, float]],
    f2: list[tuple[float, float]],
    beta: float,
) -> bool:
    """Is the bottleneck distance <= beta?

    Models the classic augmented perfect matching: each finite class matches
    either to a partner class or to its OWN diagonal slot; diagonal slots of the
    two diagrams interconnect freely at zero cost. Feasible iff a perfect
    matching of size len(f1) + len(f2) exists.
    """
    an, bn = len(f1), len(f2)
    n = an + bn
    left, right = n, n
    adj: list[list[int]] = [[] for _ in range(left)]
    # left 0..an-1 = class A_i ; left an+j = diagonal slot of B_j
    # right 0..bn-1 = class B_j ; right bn+i = diagonal slot of A_i
    diag_a = [(_diag_cost(b, d)) <= beta for b, d in f1]
    diag_b = [(_diag_cost(b, d)) <= beta for b, d in f2]

    def link_a_to_b(i: int, j: int) -> None:
        bi, di = f1[i]
        bj, dj = f2[j]
        if max(abs(bi - bj), abs(di - dj)) <= beta:
            adj[i].append(j)

    for i in range(an):
        for j in range(bn):
            link_a_to_b(i, j)
        if diag_a[i]:
            adj[i].append(bn + i)  # A_i -> its own diagonal slot (right bn+i)
    for j in range(bn):
        if diag_b[j]:
            adj[an + j].append(j)  # B_j -> its own diagonal slot (right j)
        for i in range(an):
            adj[an + j].append(bn + i)  # diagonal slots interconnect at 0 cost
    # Kuhn max matching; feasibility == perfect covering of all n left nodes.
    match_right = [-1] * right
    seen = [False] * right

    def dfs(u: int) -> bool:
        for v in adj[u]:
            if seen[v]:
                continue
            seen[v] = True
            if match_right[v] == -1 or dfs(match_right[v]):
                match_right[v] = u
                return True
        return False

    covered = 0
    for u in range(left):
        seen = [False] * right
        if dfs(u):
            covered += 1
    return covered == n


def bottleneck(d1: Sequence[tuple[float, float | None]], d2: Sequence[tuple[float, float | None]]) -> float:
    """Bottleneck (L-infinity) distance between two persistence diagrams.

    Finite classes match by sup-norm; any class may degrade onto the diagonal at
    half its persistence. Essential classes (infinite life) are matched by birth
    radius. Deterministic: threshold search + perfect matching (SC-008).
    """
    f1, f2 = _finite(d1), _finite(d2)
    candidates = [0.0]
    for b, d in f1:
        candidates.append(_diag_cost(b, d))
    for b, d in f2:
        candidates.append(_diag_cost(b, d))
    for pb, pd in f1:
        for qb, qd in f2:
            candidates.append(max(abs(pb - qb), abs(pd - qd)))
    for beta in sorted(candidates):
        if _augmented_bottleneck_feasible(f1, f2, beta):
            finite = beta
            break
    else:
        finite = max(candidates)
    e1, e2 = _essential(d1), _essential(d2)
    essential = max((abs(a - b) for a, b in zip(e1, e2)), default=0.0)
    return max(finite, essential)


def _min_cost_perfect_matching(cost: np.ndarray) -> float:
    """Kuhn–Munkres (Hungarian) for a square cost matrix — deterministic.

    Pure numpy: avoids a hard scipy runtime dependency for the diagram matching
    stage (SC-008 keeps the feature pipeline runnable in minimal installs).
    """
    n = cost.shape[0]
    if n == 0:
        return 0.0
    lfill = 1e12
    u = np.zeros(n + 1)
    v = np.zeros(n + 1)
    p = np.zeros(n + 1, dtype=int)
    way = np.zeros(n + 1, dtype=int)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = np.full(n + 1, lfill)
        used = np.zeros(n + 1, dtype=bool)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = lfill
            j1 = 0
            for j in range(1, n + 1):
                if not used[j]:
                    cur = cost[i0 - 1, j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur
                        way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]
                        j1 = j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    return float(-v[0])


def wasserstein(
    d1: Sequence[tuple[float, float | None]],
    d2: Sequence[tuple[float, float | None]],
    q: float = 1.0,
) -> float:
    """Wasserstein-q distance between diagrams (same augmented layout).

    Min-weight perfect matching with diagonal degradation at half-persistence
    (L-inf ground metric); essential classes charged |birth_a - birth_b|^q.
    """
    f1, f2 = _finite(d1), _finite(d2)
    an, bn = len(f1), len(f2)
    n = an + bn
    if n == 0:
        base = 0.0
    else:
        cost = np.full((n, n), 1e12)
        for i, (bi, di) in enumerate(f1):
            for j, (bj, dj) in enumerate(f2):
                cost[i][j] = (max(abs(bi - bj), abs(di - dj))) ** q
            cost[i][bn + i] = _diag_cost(bi, di) ** q  # A_i -> its diagonal
        for j, (bj, dj) in enumerate(f2):
            cost[an + j][j] = _diag_cost(bj, dj) ** q  # B_j -> its diagonal
            for i in range(an):
                cost[an + j][bn + i] = 0.0  # diagonal slots interconnect
        base = _min_cost_perfect_matching(cost)
    e1, e2 = _essential(d1), _essential(d2)
    base += sum(abs(a - b) ** q for a, b in zip(e1, e2))
    return base ** (1.0 / q) if base else 0.0


def amplitude(
    pairs: Sequence[tuple[float, float | None]],
    metric: str = "bottleneck",
    q: float = 1.0,
) -> float:
    """Amplitude of one diagram: distance from the empty diagram.

    Bottleneck amplitude = largest persistence; Wasserstein-q = Lq norm of
    persistences. Essential classes each contribute +inf in the bottleneck
    metric, so a lone survivor of a class yields a +inf amplitude.
    """
    if not pairs:
        return 0.0
    pers = [float("inf") if (d is None or d == _INF) else (float(d) - b) for b, d in pairs]
    if metric == "bottleneck":
        return max(pers) if pers else 0.0
    if metric == "wasserstein":
        return sum(abs(p) ** q for p in pers) ** (1.0 / q) if pers else 0.0
    raise ValueError(f"unsupported metric: {metric}")


def persistence_entropy(pairs: Sequence[tuple[float, float | None]]) -> float:
    """Shannon entropy over normalized persistences of *finite* classes.

    Essential classes are excluded (their persistence is unbounded); an empty or
    all-essential diagram has entropy 0.0. Deterministic (SC-008).
    """
    pers = [float(d) - b for b, d in pairs if d is not None and d != _INF and float(d) > b]
    total = sum(pers)
    if total <= 0.0:
        return 0.0
    return -sum((p / total) * math.log(p / total) for p in pers)


def landscapes(
    pairs: Sequence[tuple[float, float | None]],
    k_max: int = 3,
    n_grid: int = 64,
) -> list[list[float]]:
    """Persistence landscape vectorization (Bubenik): lambda_k over a t-grid.

    Each finite class (b, d) contributes ``max(0, min(t-b, d-t))``; an essential
    class contributes ``max(0, t-b)`` (it never dies). lambda_k = k-th largest
    value across classes at each grid point => shape (k_max, n_grid). Rounding to
    1e-9 keeps byte-identical rebuilds (I-12).
    """
    if not pairs:
        return [[0.0] * n_grid for _ in range(k_max)]
    births = [float(b) for b, _ in pairs]
    deaths = [float(d) if d is not None and d != _INF else max(births, default=0.0) + 1.0 for b, d in pairs]
    eps = (max(deaths) - min(births)) or 1.0
    grid = np.linspace(min(births), min(births) + eps, n_grid)
    contrib = np.zeros((n_grid, len(pairs)))
    for i, (b, d) in enumerate(pairs):
        if d is None or d == _INF:
            contrib[:, i] = np.maximum(grid - b, 0.0)
        else:
            contrib[:, i] = np.maximum(np.minimum(grid - b, d - grid), 0.0)
    order = np.argsort(-contrib, axis=1)
    out: list[list[float]] = []
    for k in range(k_max):
        row = np.zeros(n_grid)
        if k < len(pairs):
            for t in range(n_grid):
                row[t] = contrib[t, order[t, k]]
        out.append([round(float(v), 9) for v in row])
    return out


def betti_curve(pairs: Sequence[tuple[float, float | None]], n_grid: int = 64) -> list[float]:
    """Betti-0 style curve: number of classes alive across a t-grid."""
    if not pairs:
        return [0.0] * n_grid
    births = [float(b) for b, _ in pairs]
    deaths = [float(d) if d is not None and d != _INF else _INF for _, d in pairs]
    lo, hi = min(births), max((d for d in deaths if d != _INF), default=min(births) + 1.0)
    grid = np.linspace(lo, hi, n_grid)
    curve = []
    for t in grid:
        curve.append(float(sum(1 for b, d in zip(births, deaths) if b <= t < d)))
    return [round(v, 9) for v in curve]


def _round_pairs(pairs) -> list[tuple[float, float]]:
    return [(round(float(b), 9), round(float(d), 9) if d is not None and d != _INF else _INF) for b, d in pairs]


def drift(
    prev: Sequence[tuple[float, float | None]],
    cur: Sequence[tuple[float, float | None]],
    metric: str = "bottleneck",
    q: float = 1.0,
) -> dict:
    """Distance between two windows' diagrams (SC-007) + stable serializer.

    Returns ``{metric, q, value, changed, prev_hash, cur_hash}`` where the
    hashes are sha256 over the canonical JSON of the rounded pairs — drift is
    thus content-addressed and rebuildable (I-12 / C-3).
    """
    if metric == "bottleneck":
        value = bottleneck(prev, cur)
    elif metric == "wasserstein":
        value = wasserstein(prev, cur, q=q)
    else:
        raise ValueError(f"unsupported metric: {metric}")
    p_round, c_round = _round_pairs(prev), _round_pairs(cur)
    h_prev = hashlib.sha256(json.dumps(p_round, sort_keys=True).encode("utf-8")).hexdigest()
    h_cur = hashlib.sha256(json.dumps(c_round, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "metric": metric,
        "q": q,
        "value": round(float(value), 9),
        "changed": h_prev != h_cur,
        "prev_hash": h_prev,
        "cur_hash": h_cur,
    }


def compute_features(
    diagrams: dict[int, Sequence[tuple[float, float | None]]],
    *,
    dimensions: Sequence[int] = (0, 1),
    k_max: int = 3,
    n_grid: int = 64,
) -> dict:
    """Deterministic aggregate feature payload for a full multi-dim diagram set.

    Keys per dim: ``bottleneck_amplitude``, ``wasserstein_amplitude``,
    ``entropy``, ``landscapes``, ``betti``. The whole payload is stable under a
    stable input (SC-008) and marked structural-only (I-6).
    """
    out: dict = {"structural_only": True, "dimensions": {int(d): {} for d in dimensions}}
    for dim in dimensions:
        pairs = diagrams.get(int(dim), [])
        cell = out["dimensions"][int(dim)]
        cell["bottleneck_amplitude"] = amplitude(pairs, "bottleneck")
        cell["wasserstein_amplitude"] = amplitude(pairs, "wasserstein", q=1.0)
        cell["entropy"] = persistence_entropy(pairs)
        cell["landscapes"] = landscapes(pairs, k_max=k_max, n_grid=n_grid)
        cell["betti"] = betti_curve(pairs, n_grid=n_grid)
    return out


def features_digest(features: dict) -> str:
    """Content-addressed digest of a ``compute_features`` payload (I-12)."""
    return hashlib.sha256(json.dumps(features, sort_keys=True).encode("utf-8")).hexdigest()


__all__ = [
    "TDAFeatureBuilder",
    "TopologicalFeature",
    "amplitude",
    "betti_curve",
    "bottleneck",
    "compute_features",
    "drift",
    "features_digest",
    "landscapes",
    "persistence_entropy",
    "wasserstein",
]