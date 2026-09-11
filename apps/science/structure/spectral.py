"""Normalized spectral/centrality measures (T122, US5).

Power iteration over the adjacency matrix gives the dominant eigenvalue λ₁; the
normalized spectral radius λ₁/(N-1) ∈ [0,1] with 1 only for the complete graph,
so scores are comparable across graph sizes and always in a documented range
(interface-contracts §7).
"""

from __future__ import annotations

from math import sqrt
from typing import Any


def spectral_radius_norm(graph: Any) -> float:
    """λ₁/(N-1) computed by deterministic power iteration, clamped to [0,1]."""
    adj = graph.adjacency()
    n = len(adj)
    if n < 2:
        return 0.0
    vector = {node: 1.0 for node in adj}
    for _ in range(200):
        nxt = {node: sum(vector[nb] for nb in nbrs) for node, nbrs in adj.items()}
        norm = sqrt(sum(x * x for x in nxt.values()))
        if norm == 0.0:
            break
        vector = {node: value / norm for node, value in nxt.items()}
    dot_radius_2nd = sum(
        vector.get(node, 0.0) * sum(vector.get(nb, 0.0) for nb in nbrs)
        for node, nbrs in adj.items()
    )
    vector_norm_sq = sum(x * x for x in vector.values())
    if vector_norm_sq == 0.0:
        return 0.0
    lam1 = dot_radius_2nd / vector_norm_sq
    return max(0.0, min(1.0, lam1 / (n - 1)))