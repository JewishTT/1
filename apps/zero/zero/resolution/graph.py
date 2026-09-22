"""Resolution graph topology (spec/010 §0.8 step 4) — NO AI.

Deterministic graph analysis over the matched pairs produced upstream:

- ``connected_components`` = transitive closure (A→B, B→C ⟹ A→C). This is the
  equivalence relation we chase for record linking.
- ``modularity`` / ``greedy_modularity`` = a compact Louvain-style greedy
  modularity optimizer (``Q = (1/2m) sum [A_ij - k_i*k_j/(2m)] delta(c_i,c_j)``)
  for community detection on weighted adjacency.
- ``cluster_candidates`` = consolidation of harvested candidates by normalized
  value with max-confidence merge (wave output ⇄ entity view).
"""

from __future__ import annotations

from collections import defaultdict
from math import log10

from ..harvesters.contracts import ObservationCandidate
from .similarity import normalize


class UnionFind:
    """Path-compressed union-find (also usable as transitive-closure oracle)."""

    def __init__(self, n: int) -> None:
        self._parent = list(range(n))
        self._rank = [0] * n

    def find(self, node: int) -> int:
        root = node
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[node] != root:
            self._parent[node], node = root, self._parent[node]
        return root

    def union(self, a: int, b: int) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a == root_b:
            return
        if self._rank[root_a] < self._rank[root_b]:
            root_a, root_b = root_b, root_a
        self._parent[root_b] = root_a
        if self._rank[root_a] == self._rank[root_b]:
            self._rank[root_a] += 1


def connected_components(n: int, edges: list[tuple[int, int]]) -> list[set[int]]:
    """Transitive closure: equivalence classes over ``n`` nodes and ``edges``."""
    uf = UnionFind(n)
    for a, b in edges:
        uf.union(a, b)
    clusters: dict[int, set[int]] = defaultdict(set)
    for node in range(n):
        clusters[uf.find(node)].add(node)
    return [clusters[root] for root in sorted(clusters)]


def modularity(
    n: int,
    adjacency: dict[tuple[int, int], float],
    partition: list[int],
    *, weight_sum: float | None = None,
) -> float:
    """Standard modularity of a node→community ``partition`` on weighted edges."""
    edge_sum = weight_sum if weight_sum is not None else sum(adjacency.values())
    if edge_sum <= 0:
        return 0.0
    degrees = [0.0] * n
    for (a, b), weight in adjacency.items():
        degrees[a] += weight
        degrees[b] += weight
    community_degrees: dict[int, float] = defaultdict(float)
    for node, community in enumerate(partition):
        community_degrees[community] += degrees[node]
    internal_by_community: dict[int, float] = defaultdict(float)
    for (a, b), weight in adjacency.items():
        ca, cb = partition[a], partition[b]
        if ca == cb:
            internal_by_community[ca] += weight
    q = 0.0
    for community in set(partition):
        internal = internal_by_community.get(community, 0.0)
        cd = community_degrees[community]
        q += internal / (2 * edge_sum) - (cd * cd) / (4 * edge_sum * edge_sum)
    return q


def frozenset_key(a: int, b: int) -> frozenset:
    return frozenset((a, b))


def greedy_modularity(
    n: int,
    adjacency: dict[tuple[int, int], float],
    *,
    passes: int = 2,
) -> list[int]:
    """Greedy modularity optimizer (Louvain-style pass-1) for weighted graphs."""
    partition = list(range(n))
    degree = [0.0] * n
    for (a, b), weight in adjacency.items():
        degree[a] += weight
        degree[b] += weight
    edge_sum = sum(adjacency.values())
    if edge_sum <= 0:
        return partition
    neighbor_weights: list[dict[int, float]] = [defaultdict(float) for _ in range(n)]
    for (a, b), weight in adjacency.items():
        neighbor_weights[a][b] += weight
        neighbor_weights[b][a] += weight
    for _pass in range(passes):
        improved = False
        for node in range(n):
            community = partition[node]
            node_degree = degree[node]
            link_to_self = sum(
                weight
                for neighbor, weight in neighbor_weights[node].items()
                if partition[neighbor] == community
            )
            best_community = community
            best_gain = 0.0
            gains: dict[int, float] = defaultdict(float)
            for neighbor, weight in neighbor_weights[node].items():
                target = partition[neighbor]
                target_degree = _community_degree(partition, degree, target)
                if target != community:
                    link = link_to_self + weight
                    gains[target] += link - (node_degree * target_degree) / (2 * edge_sum)
                else:
                    gains[target] += weight - (node_degree * target_degree) / (2 * edge_sum)
            for target, gain in gains.items():
                if gain > best_gain + 1e-12:
                    best_gain = gain
                    best_community = target
            if best_community != community and best_gain > 0:
                partition[node] = best_community
                improved = True
        if not improved:
            break
    labels = _relabel(partition)
    return labels


def _community_degree(partition: list[int], degree: list[float], community: int) -> float:
    return sum(deg for node, deg in enumerate(degree) if partition[node] == community)


def _relabel(partition: list[int]) -> list[int]:
    mapping: dict[int, int] = {}
    labels: list[int] = []
    for community in partition:
        if community not in mapping:
            mapping[community] = len(mapping)
        labels.append(mapping[community])
    return labels


def community_detection(
    n: int,
    adjacency: dict[tuple[int, int], float],
) -> list[set[int]]:
    """Community partition as sorted node sets (alias for L1 Louvain pass)."""
    labels = greedy_modularity(n, adjacency)
    groups: dict[int, set[int]] = defaultdict(set)
    for node, label in enumerate(labels):
        groups[label].add(node)
    return [groups[label] for label in sorted(groups)]


def cluster_candidates(
    candidates: list[ObservationCandidate],
    *,
    min_confidence: float = 0.0,
) -> list[ObservationCandidate]:
    """Consolidate candidates by normalized value (kind-sensitive), keep max-repute.

    Returns one candidate per unique ``(kind, normalized_value)``: the one with
    the highest confidence; provenance fields are merged into a comma-joined
    ``raw_fields["sources"]``. Deterministic: iteration order = input order.
    """
    best: dict[tuple[str, str], ObservationCandidate] = {}
    for candidate in candidates:
        if candidate.confidence < min_confidence:
            continue
        key = (candidate.kind, normalize(candidate.value, candidate.kind))
        prior = best.get(key)
        if prior is None or candidate.confidence > prior.confidence:
            sources = _merge_sources(prior, candidate)
            merged_method = " + ".join(
                    filter(None, ((prior.method if prior else ""), candidate.method))
                )
            merged = ObservationCandidate(
                value=candidate.value,
                kind=candidate.kind,
                confidence=candidate.confidence,
                source_module=prior.source_module if prior else candidate.source_module,
                method=merged_method,
                raw_fields={**candidate.raw_fields, "sources": sources},
                evidence=candidate.evidence,
            )
            best[key] = merged
    return list(best.values())


def _merge_sources(prior: ObservationCandidate | None, candidate: ObservationCandidate) -> str:
    if prior is None:
        return candidate.source_module
    prior_sources = prior.raw_fields.get("sources", prior.source_module)
    if isinstance(prior_sources, str) and candidate.source_module not in prior_sources:
        return f"{prior_sources}," + candidate.source_module
    return str(prior_sources)


def log_confidence(confidence: float) -> float:
    """Deterministic confidence → log-odds scale (simple monotone transform)."""
    if confidence <= 0.0:
        return -float("inf")
    return log10(confidence / max(1.0 - confidence, 1e-9))