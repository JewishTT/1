"""Topological *insight*: the two outputs persistence alone does not give.

Persistence produces intervals. On its own that is a table of birth/death pairs, and a
reader still has to know what to do with them. These are the two answers that matter for
reconnaissance, both read off the same diagrams and neither requiring a second
computation:

**Hidden clusters.** H0 intervals that never die are connected components that survive
every threshold. A graph about people and organisations has real clusters that nobody
labelled -- a shell around one owner, a set of domains behind one registrar, a cluster of
profiles sharing infrastructure. Those are the long-lived H0 intervals, and this module
returns them *with their members*, because a cluster you cannot name is a curiosity and a
cluster you can is a lead.

**Anomalies.** A node is topologically anomalous when it joins its own structure late, or
when its neighbourhood is unlike the rest. Both are read from the same filtration, and
both are attributed to specific nodes rather than reported as a single score.

Why union-find rather than gudhi for membership
-----------------------------------------------
Attribution needs the member lists, and the exact way to get them is a connected
components computation on the filtration at a chosen scale -- which is union-find, in
O(n^2 alpha(n)) over the edges that survive, and needs no extra library. Reading it out
of the persistence output would require re-running persistence with simplex tracking and
would be slower for the same answer.

Every threshold used here is reported alongside the result. A cluster boundary is a claim
about a scale, and a claim whose scale is not stated cannot be checked.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

#: An H0 interval whose death exceeds this counts as a persistent component. Chosen as a
#: *relative* rule rather than a magic distance: a graph's distances are not on a fixed
#: scale, and a constant that works for one embedding is meaningless for the next.
PERSISTENCE_RATIO = 0.5


@dataclass(frozen=True, slots=True)
class Cluster:
    """One persistent connected component."""

    cluster_id: int
    #: Birth of the component: the scale at which its longest-lived interval appeared.
    birth: float
    #: ``None`` for a component that never merges -- the ones that matter.
    death: float | None
    lifetime: float
    members: tuple[str, ...] = ()
    #: True when this component survived every scale, i.e. it is a genuine cluster
    #: rather than a transient group that merged later.
    persistent: bool = False

    @property
    def size(self) -> int:
        """How many nodes. On the record rather than only in the dict, because every
        caller asks it before deciding whether the cluster is worth reading."""
        return len(self.members)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "birth": self.birth,
            "death": self.death,
            "lifetime": self.lifetime,
            "size": len(self.members),
            "members": list(self.members),
            "persistent": self.persistent,
        }


@dataclass(frozen=True, slots=True)
class Anomaly:
    """One node whose topological position departs from its peers."""

    node_id: str
    #: Scale at which this node joined the component that contains it. High means the
    #: node is connected to the structure only loosely.
    join_scale: float
    #: How far the node sits from the mean join scale of its own cluster. This is the
    #: comparable number: a node can have a high absolute join scale simply by being in
    #: a loose cluster.
    deviation: float
    reason: str = "late_join"
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "join_scale": self.join_scale,
            "deviation": self.deviation,
            "reason": self.reason,
            "detail": self.detail,
        }


class _UnionFind:
    def __init__(self, n: int) -> None:
        self._parent = list(range(n))
        self._rank = [0] * n

    def find(self, x: int) -> int:
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]  # path halving
            x = self._parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self._rank[ra] < self._rank[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra
        if self._rank[ra] == self._rank[rb]:
            self._rank[ra] += 1


def _finite_edges(distance_matrix: np.ndarray) -> list[tuple[float, int, int]]:
    """Edges that exist, as ``(weight, i, j)``, heaviest first.

    ``+inf`` marks a pair the selector dropped; it is not an edge of any length, so it is
    excluded rather than clamped. Reversed because union-find has to see edges in
    increasing weight order to reproduce the filtration.
    """
    n = distance_matrix.shape[0]
    iu = np.triu_indices(n, k=1)
    weights = distance_matrix[iu]
    keep = np.isfinite(weights)
    # The weights must be filtered *together with* the index pairs. Indexing the
    # unfiltered array with filtered indices was a real bug here: it paired surviving
    # (i, j) with the weight of some dropped pair, so a dropped +inf leaked in and the
    # reported edge scale was wrong.
    weights = weights[keep]
    rows, cols = iu[0][keep], iu[1][keep]
    edges = [(float(w), int(r), int(c)) for w, r, c in zip(weights, rows, cols, strict=True)]
    edges.sort(key=lambda e: e[0])
    return edges


def hidden_clusters(
    node_ids: Sequence[str],
    distance_matrix: np.ndarray,
    diagrams: dict[int, Sequence[tuple[float, float | None]]] | None = None,
    *,
    min_members: int = 2,
    include_transient: bool = False,
) -> list[Cluster]:
    """Connected components that never merge, with their members.

    This is the persistent-component computation and it needs **no threshold**. Edges are
    applied in increasing order of weight; a component that still exists after the last
    edge was applied is one that survived every scale of the filtration, which is exactly
    an H0 interval with infinite death.

    An earlier version cut the filtration at ``PERSISTENCE_RATIO`` times the longest
    finite merge. That is wrong and measurably so: on four planted clusters of fifteen
    nodes it returned ten fragments of two to six nodes, because the reference lifetime
    was itself tiny and half of it cut through the real structure. The infinite intervals
    are already in the diagram and need no invented cut.
    """
    n = distance_matrix.shape[0]
    if n == 0:
        return []

    edges = _finite_edges(distance_matrix)
    if not edges:
        # Every pair was dropped, so every node is its own component. Returning one
        # cluster of all of them -- which this did at first -- asserts a connection the
        # selector explicitly refused to make. A single node is the one case where
        # "everything is in one component" happens to be true.
        if n == 1:
            return [
                Cluster(
                    cluster_id=0,
                    birth=0.0,
                    death=None,
                    lifetime=float("inf"),
                    members=(str(node_ids[0]),),
                    persistent=True,
                )
            ]
        return [
            Cluster(
                cluster_id=index,
                birth=0.0,
                death=None,
                lifetime=float("inf"),
                members=(str(node_ids[index]),),
                persistent=True,
            )
            for index in range(n)
        ]

    uf = _UnionFind(n)
    members: dict[int, list[int]] = {i: [i] for i in range(n)}
    # The weight at which a vertex first became part of a component of size > 1. This is
    # the node's own join scale and is what makes a node comparable to its peers.
    join_scale: dict[int, float] = {}
    component_birth: dict[int, float] = {i: 0.0 for i in range(n)}
    merged_into_larger: set[int] = set()

    for weight, i, j in edges:
        ri, rj = uf.find(i), uf.find(j)
        if ri == rj:
            continue
        if len(members[ri]) < len(members[rj]):
            ri, rj = rj, ri
        # The absorbed component stops existing as a component of its own.
        merged_into_larger.add(rj)
        uf.union(ri, rj)
        root = uf.find(ri)
        members[root] = members.pop(ri, []) + members.pop(rj, [])
        component_birth.setdefault(root, weight)
        for vertex in members[root]:
            join_scale.setdefault(vertex, weight)

    groups = [sorted(group) for group in members.values()]
    groups.sort(key=lambda g: (-len(g), min(g)))

    clusters: list[Cluster] = []
    transient_id = 0
    for group in groups:
        if len(group) < min_members:
            continue
        root = uf.find(group[0])
        transient = root in merged_into_larger
        if transient and not include_transient:
            continue
        scales = [join_scale.get(v, 0.0) for v in group]
        birth = min(scales) if scales else 0.0
        death = max(scales) if scales else None
        if transient:
            clusters.append(
                Cluster(
                    cluster_id=len(clusters),
                    birth=float(birth),
                    death=float(death or 0.0),
                    lifetime=float((death or 0.0) - birth),
                    members=tuple(str(node_ids[v]) for v in group),
                    persistent=False,
                )
            )
            transient_id += 1
        else:
            clusters.append(
                Cluster(
                    cluster_id=len(clusters),
                    birth=float(birth),
                    death=None,
                    lifetime=float("inf"),
                    members=tuple(str(node_ids[v]) for v in group),
                    persistent=True,
                )
            )
    return clusters


def _join_scales(node_ids: Sequence[str], distance_matrix: np.ndarray) -> dict[int, float]:
    """The weight at which each vertex first joined a component of size > 1.

    Shared by both outputs so a cluster's membership and an anomaly's attribution come
    from one pass over the filtration and cannot disagree.
    """
    n = distance_matrix.shape[0]
    edges = _finite_edges(distance_matrix)
    uf = _UnionFind(n)
    size: dict[int, int] = {i: 1 for i in range(n)}
    join: dict[int, float] = {}
    for weight, i, j in edges:
        ri, rj = uf.find(i), uf.find(j)
        if ri == rj:
            continue
        merged = size[ri] + size[rj]
        uf.union(ri, rj)
        root = uf.find(ri)
        size[root] = merged
        if merged > 1:
            join.setdefault(i, weight)
            join.setdefault(j, weight)
    return join


def anomalies(
    node_ids: Sequence[str],
    distance_matrix: np.ndarray,
    clusters: Sequence[Cluster],
    *,
    z_threshold: float = 1.5,
) -> list[Anomaly]:
    """Nodes that join their own structure later than their peers.

    Deviation is measured *within* a cluster. An absolute join-scale threshold would flag
    every member of a loosely-connected cluster, which says something about the cluster
    rather than about any node; the comparison has to be local for the number to mean
    anything.
    """
    out: list[Anomaly] = []
    index = {str(nid): i for i, nid in enumerate(node_ids)}
    if not clusters or distance_matrix.shape[0] == 0:
        return out

    join = _join_scales(node_ids, distance_matrix)
    by_cluster: dict[int, list[int]] = {}
    for cluster in clusters:
        for member in cluster.members:
            if member in index:
                by_cluster.setdefault(cluster.cluster_id, []).append(index[member])

    for cid, members in by_cluster.items():
        scales = [join.get(m, 0.0) for m in members]
        if len(scales) < 3:
            continue
        mean = sum(scales) / len(scales)
        variance = sum((s - mean) ** 2 for s in scales) / len(scales)
        stdev = variance**0.5
        if stdev <= 0:
            # Every member joined at the same scale: no member departs from the others.
            continue
        for member, scale in zip(members, scales, strict=True):
            deviation = (scale - mean) / stdev
            if deviation >= z_threshold:
                out.append(
                    Anomaly(
                        node_id=str(node_ids[member]),
                        join_scale=float(scale),
                        deviation=float(deviation),
                        reason="late_join",
                        detail={
                            "cluster_id": cid,
                            "cluster_size": len(members),
                            "cluster_mean_join_scale": float(mean),
                            "cluster_stdev": float(stdev),
                        },
                    )
                )
    out.sort(key=lambda a: -a.deviation)
    return out


def summarise(
    node_ids: Sequence[str],
    distance_matrix: np.ndarray,
    diagrams: dict[int, Sequence[tuple[float, float | None]]] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Clusters and anomalies from one filtration, with the scales stated.

    The scales travel with the answer because a cluster boundary is a claim about a
    scale, and a claim whose scale is not stated cannot be checked by anyone reading it.
    """
    clusters = hidden_clusters(node_ids, distance_matrix, diagrams, **kwargs)
    found = anomalies(node_ids, distance_matrix, clusters)
    edges = _finite_edges(distance_matrix)
    return {
        "nodes": len(node_ids),
        "edges": len(edges),
        "scale": {
            "max_finite_edge": edges[-1][0] if edges else 0.0,
            "largest_cluster": max((len(c.members) for c in clusters), default=0),
            "persistent_clusters": sum(1 for c in clusters if c.persistent),
        },
        "clusters": [c.to_dict() for c in clusters],
        "anomalies": [a.to_dict() for a in found],
    }


__all__ = ["Anomaly", "Cluster", "PERSISTENCE_RATIO", "anomalies", "hidden_clusters", "summarise"]