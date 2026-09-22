"""Structural network measures over a graph projection (T059).

Adapted from lau-network-science (MIT) — deterministic, pure-stdlib subset:
degree statistics, clustering, transitivity, degree assortativity, degree
Gini, power-law exponent (Clauset–Shalizi–Newman MLE), and Watts–Strogatz
small-world sigma against an analytic Erdős–Rényi baseline.

   Source repo : donors/lau-network-science (https://github.com/larryng/lau-network-science)
   License     : MIT
   What changed: Rust crate → python functions on ``AdjacencyView``; kept the
                 standard graph-statistics semantics only; sigma baseline made
                 analytic (open). No centrality/epidemic/neural models carried.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import log
from typing import Any

import path_shim  # noqa: F401 - keep apps/shared ahead of conflicting dirs
from graph.adjacency import AdjacencyView


@dataclass(frozen=True)
class NetworkMeasures:
    """A deterministic summary of structural features of a graph projection."""
    n_nodes: int
    n_edges: int
    density: float
    avg_degree: float
    max_degree: int
    avg_clustering: float
    transitivity: float
    assortativity: float
    degree_gini: float
    power_law_alpha: float | None
    power_law_x_min: int | None
    avg_shortest_path: float
    small_world_sigma: float | None
    degree_distribution: dict[int, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_nodes": self.n_nodes,
            "n_edges": self.n_edges,
            "density": self.density,
            "avg_degree": self.avg_degree,
            "max_degree": self.max_degree,
            "avg_clustering": self.avg_clustering,
            "transitivity": self.transitivity,
            "assortativity": self.assortativity,
            "degree_gini": self.degree_gini,
            "power_law_alpha": self.power_law_alpha,
            "power_law_x_min": self.power_law_x_min,
            "avg_shortest_path": self.avg_shortest_path,
            "small_world_sigma": self.small_world_sigma,
            "degree_distribution": self.degree_distribution,
        }


def _adjacency_of(view: AdjacencyView) -> dict[str, set[str]]:
    adj: dict[str, set[str]] = {node: set() for node in view.nodes}
    for edge in view.edges:
        adj.setdefault(edge.source, set()).add(edge.target)
        adj.setdefault(edge.target, set()).add(edge.source)
    return adj


def network_measures(view: AdjacencyView) -> NetworkMeasures:
    """Compute deterministic structural measures for an undirected adjacency."""
    adj = _adjacency_of(view)
    nodes = sorted(adj)
    n = len(nodes)
    edges: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for edge in view.edges:
        pair = (edge.source, edge.target)
        if edge.source == edge.target:
            continue
        key = (min(pair), max(pair))
        if key not in seen:
            seen.add(key)
            edges.append(pair)
    m = len(edges)

    degrees = {node: len(neighbors) for node, neighbors in adj.items()}
    degree_counts: dict[int, int] = {}
    for degree in degrees.values():
        degree_counts[degree] = degree_counts.get(degree, 0) + 1

    def triangles() -> int:
        total = 0
        for source, target in edges:
            shared = len(adj[source] & adj[target])
            total += shared
        return total // 3

    triangle_count = triangles()

    def local_clustering() -> list[float]:
        values: list[float] = []
        for neighbors in adj.values():
            k = len(neighbors)
            if k < 2:
                values.append(0.0)
                continue
            possible = k * (k - 1) / 2.0
            present = 0
            for neighbor in neighbors:
                present += len(neighbors & adj[neighbor])
            actual = present / 2.0
            values.append(actual / possible)
        return values

    clustering_values = local_clustering()
    avg_clustering = sum(clustering_values) / n if n else 0.0

    triads = sum(k * (k - 1) for k in degrees.values()) // 2
    transitivity = 3.0 * triangle_count / triads if triads else 0.0

    def degree_assortativity() -> float:
        if not edges:
            return 0.0
        j_sum = sum(degrees[u] for u, _ in edges)
        k_sum = sum(degrees[v] for _, v in edges)
        jk_sum = sum(float(degrees[u]) * degrees[v] for u, v in edges)
        j2_sum = sum(float(degrees[u]) ** 2 + degrees[v] ** 2 for u, v in edges) / 2.0
        mean_jk = jk_sum / m
        mean_jk_half = (j_sum + k_sum) / (2.0 * m)
        numerator = mean_jk - mean_jk_half ** 2
        denominator = j2_sum / m - mean_jk_half ** 2
        if denominator == 0.0:
            return 0.0
        return numerator / denominator

    assortativity = degree_assortativity()

    def degree_gini() -> float:
        values = sorted(degrees.values())
        if not values:
            return 0.0
        total = float(sum(values))
        if total == 0.0:
            return 0.0
        count = len(values)
        return (
            2.0 * sum(position * value for position, value in enumerate(values, start=1))
            / (count * total)
        ) - (count + 1.0) / count

    gini = degree_gini()

    def power_law_mle() -> tuple[float | None, int | None]:
        observed = sorted(v for v in degrees.values() if v >= 1)
        if not observed:
            return None, None
        x_min = min(observed)
        terms = sum(log(v / x_min) for v in observed)
        if terms == 0.0:
            return None, x_min
        return 1.0 + len(observed) / terms, x_min

    alpha, x_min = power_law_mle()

    def average_shortest_path() -> float:
        if n <= 1:
            return 0.0
        distances: list[int] = []
        for start in nodes:
            queue = [start]
            seen_nodes = {start}
            level = 0
            while queue:
                next_level: list[str] = []
                for node in queue:
                    for neighbor in adj[node]:
                        if neighbor not in seen_nodes:
                            seen_nodes.add(neighbor)
                            next_level.append(neighbor)
                distances.extend([level + 1] * len(next_level))
                queue = next_level
                level += 1
        reachable = n * (n - 1)
        return (sum(distances) / reachable) if reachable else 0.0

    avg_path = average_shortest_path()

    def small_world_sigma() -> float | None:
        if n < 3 or avg_clustering == 0.0 or avg_path == 0.0:
            return None
        avg_degree = (2.0 * m) / n
        if avg_degree <= 0.0:
            return None
        c_rand = avg_degree / (n - 1) if n > 1 else 0.0
        if c_rand <= 0.0:
            return None
        l_rand = log(n) / log(avg_degree) if avg_degree > 1.0 else 1.0
        return (avg_clustering / c_rand) / (avg_path / l_rand)

    sigma = small_world_sigma()
    avg_degree = (2.0 * m) / n if n else 0.0

    return NetworkMeasures(
        n_nodes=n,
        n_edges=m,
        density=(2.0 * m / (n * (n - 1))) if n > 1 else 0.0,
        avg_degree=avg_degree,
        max_degree=max(degrees.values()) if degrees else 0,
        avg_clustering=avg_clustering,
        transitivity=transitivity,
        assortativity=assortativity,
        degree_gini=gini,
        power_law_alpha=alpha,
        power_law_x_min=x_min,
        avg_shortest_path=avg_path,
        small_world_sigma=sigma,
        degree_distribution={degree: degree_counts[degree] for degree in sorted(degree_counts)},
    )