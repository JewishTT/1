"""Community detection and validation (T059).

Adapted from lau-network-science (MIT): label propagation for community
labels on ``AdjacencyView``, modularity ``Q`` as the objective, and a
normalized mutual information (NMI) evaluator for comparing partitions.
Deterministic: labels tie-break by identifier, iterations are bounded.

   Source repo : donors/lau-network-science (https://github.com/larryng/lau-network-science)
   License     : MIT
   What changed: community.rs label-propagation/modularity semantics → python;
                 NMI implemented directly (no scipy dependency).
"""

from __future__ import annotations

import math
from collections import Counter

import path_shim  # noqa: F401 - keep apps/shared ahead of conflicting dirs
from graph.adjacency import AdjacencyView


def label_propagation(view: AdjacencyView, *, max_iterations: int = 100) -> dict[str, str]:
    """Asynchronous label propagation → community label per node.

    Ties resolve to the smallest label (deterministic). Stops early when a
    full sweep changes nothing.
    """
    adj: dict[str, list[str]] = {node: [] for node in view.nodes}
    for edge in view.edges:
        if edge.source == edge.target:
            continue
        adj.setdefault(edge.source, []).append(edge.target)
        adj.setdefault(edge.target, []).append(edge.source)

    labels: dict[str, str] = {node: node for node in view.nodes}
    order = sorted(adj)
    for _ in range(max_iterations):
        changed = False
        for node in order:
            if not adj[node]:
                continue
            votes: dict[str, int] = Counter(labels[neighbor] for neighbor in adj[node])
            if len(votes) == 1 and labels[node] in votes:
                continue
            best_label, best_count = None, -1
            for label in sorted(votes):
                count = votes[label]
                if count > best_count or (count == best_count and (best_label is None or label < best_label)):
                    best_label, best_count = label, count
            if best_label is not None and best_label != labels[node]:
                labels[node] = best_label
                changed = True
        if not changed:
            break
    compact: dict[str, str] = {}
    for node in sorted(labels):
        compact[node] = labels[node]
    return compact


def modularity(partition: dict[str, str], view: AdjacencyView) -> float:
    """Newman–Girvan modularity Q for an undirected graph (∈ [-1, 1])."""
    degrees: dict[str, int] = {node: 0 for node in view.nodes}
    edges: list[tuple[str, str]] = []
    for edge in view.edges:
        if edge.source == edge.target:
            continue
        degrees[edge.source] = degrees.get(edge.source, 0) + 1
        degrees[edge.target] = degrees.get(edge.target, 0) + 1
        edges.append((edge.source, edge.target))

    twice_edges = 2 * len(edges)
    if twice_edges == 0:
        return 0.0

    community_totals: dict[str, int] = {}
    for node, label in partition.items():
        community_totals[label] = community_totals.get(label, 0) + degrees.get(node, 0)

    inside: dict[str, int] = {}
    for source, target in edges:
        if partition.get(source) == partition.get(target):
            label = partition[source]
            inside[label] = inside.get(label, 0) + 1

    total = 0.0
    for label, community_total in community_totals.items():
        total += inside.get(label, 0) / len(edges)
        total -= (community_total / twice_edges) ** 2
    return total


def normalized_mutual_information(left: dict[str, str], right: dict[str, str]) -> float:
    """NMI between two node→label mappings, in [0, 1] (deterministic)."""
    nodes = sorted({*left, *right})
    if not nodes:
        return 0.0
    contingency: dict[tuple[str, str], int] = Counter(
        (left[node], right[node]) for node in nodes
    )
    size = len(nodes)
    left_counts = Counter(left.get(node, "") for node in nodes)
    right_counts = Counter(right.get(node, "") for node in nodes)

    mutual = 0.0
    for (a, b), count in contingency.items():
        if count == 0:
            continue
        mutual += (count / size) * math.log(
            (count * size) / (left_counts[a] * right_counts[b]) or 1.0
        )
    entropy_left = -sum((c / size) * math.log(c / size) for c in left_counts.values())
    entropy_right = -sum((c / size) * math.log(c / size) for c in right_counts.values())
    if mutual <= 0.0 or entropy_left == 0.0 or entropy_right == 0.0:
        return 0.0
    return 2.0 * mutual / (entropy_left + entropy_right)