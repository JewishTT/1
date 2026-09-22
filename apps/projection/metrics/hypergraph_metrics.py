"""Hypergraph metrics for co-mention / co-event projections (T058).

Adapted from HypergraphX (BSD-3). Deterministic, pure-stdlib subset: a
``Hypergraph`` value class where edges are observation-level sets of nodes,
plus elementary metrics — order, sizes, node degrees, pairwise overlap,
co-membership, and a builder from observations (the co-mention/co-event
derivation that projection planes will materialize).

   Source repo : donors/hypergraphx (https://github.com/HypergraphX/HypergraphX)
   License     : BSD-3-Clause
   What changed: full package → minimal hypergraph + metric subset; no SciPy/
                 Viper aggregators; the observation→hyperedge builder is new.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Hyperedge:
    """A single hyperedge (one observation): the set of nodes it covers."""
    id: str
    nodes: tuple[str, ...]
    properties: dict[str, Any] = field(default_factory=dict)

    def size(self) -> int:
        return len(self.nodes)


@dataclass
class Hypergraph:
    """Collection of hyperedges with derived metrics (deterministic)."""
    edges: list[Hyperedge] = field(default_factory=list)

    def add_edge(self, edge_id: str, nodes: Iterable[str], **properties: Any) -> None:
        unique = tuple(sorted(set(nodes)))
        self.edges.append(Hyperedge(id=edge_id, nodes=unique, properties=properties))

    @property
    def nodes(self) -> list[str]:
        seen: set[str] = set()
        for edge in self.edges:
            seen.update(edge.nodes)
        return sorted(seen)

    def num_edges(self) -> int:
        return len(self.edges)

    def num_nodes(self) -> int:
        return len(self.nodes)

    def order(self) -> int:
        return max((edge.size() for edge in self.edges), default=0)

    def edge_sizes(self) -> dict[int, int]:
        return dict(Counter(edge.size() for edge in self.edges).items())

    def node_degree(self, node: str) -> int:
        return sum(1 for edge in self.edges if node in edge.nodes)

    def degree_distribution(self) -> dict[int, int]:
        return dict(Counter(self.node_degree(node) for node in self.nodes).items())

    def average_node_degree(self) -> float:
        degrees = [self.node_degree(node) for node in self.nodes]
        return (sum(degrees) / len(degrees)) if degrees else 0.0

    def incidence_density(self) -> float:
        total_incidences = sum(edge.size() for edge in self.edges)
        possible = self.num_nodes() * self.num_edges()
        return (total_incidences / possible) if possible else 0.0

    def jaccard(self, left_edge_id: str, right_edge_id: str) -> float:
        left = next((e for e in self.edges if e.id == left_edge_id), None)
        right = next((e for e in self.edges if e.id == right_edge_id), None)
        if left is None or right is None:
            raise KeyError("unknown hyperedge id")
        left_set = set(left.nodes)
        right_set = set(right.nodes)
        union = left_set | right_set
        if not union:
            return 0.0
        return len(left_set & right_set) / len(union)

    def co_membership(self, left_node: str, right_node: str) -> int:
        """Number of hyperedges that contain both nodes."""
        return sum(
            1 for edge in self.edges if left_node in edge.nodes and right_node in edge.nodes
        )

    def connected_pairs(self) -> int:
        """Number of node pairs sharing at least one hyperedge."""
        pairs: set[tuple[str, str]] = set()
        for edge in self.edges:
            nodes = tuple(sorted(set(edge.nodes)))
            for i, left in enumerate(nodes):
                for right in nodes[i + 1 :]:
                    pairs.add((left, right))
        return len(pairs)

    def as_dict(self) -> dict[str, Any]:
        return {
            "num_nodes": self.num_nodes(),
            "num_edges": self.num_edges(),
            "order": self.order(),
            "edge_sizes": self.edge_sizes(),
            "degree_distribution": self.degree_distribution(),
            "average_node_degree": self.average_node_degree(),
            "incidence_density": self.incidence_density(),
            "connected_pairs": self.connected_pairs(),
        }


def hypergraph_from_observations(
    observations: dict[str, Iterable[str]],
    *,
    min_degree: int = 1,
) -> Hypergraph:
    """Build a hypergraph where each edge is one observation and its nodes.

    Entities mentioned in fewer than ``min_degree`` observations are dropped
    (they cannot participate in a strong co-membership signal), which keeps
    single-mention noise out of degree-based metrics. Filtering happens after
    degree counting so the metric reflects the full observation set.
    """
    observed: dict[str, set[str]] = {obs_id: set(nodes) for obs_id, nodes in observations.items()}
    mention_count: Counter[str] = Counter()
    for nodes in observed.values():
        mention_count.update(nodes)
    hypergraph = Hypergraph()
    for obs_id in sorted(observed):
        nodes = sorted(n for n in observed[obs_id] if mention_count[n] >= min_degree)
        if nodes:
            hypergraph.add_edge(obs_id, nodes)
    return hypergraph