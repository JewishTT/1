"""Adjacency view for TDA / entity-network analysis (FR-013, US4).

Reads the graph projection and returns a plain (nodes, edges) adjacency that
downstream analytical planes (TDA, network analysis) consume without importing
a vendor client (Constitution V). The view shares the projection's identifiers,
so a finding traces back to the same observation id (Invariant 9: search is
not traversal is not OLAP — they only agree on keys).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from domain import enforce_projection_provenance

import path_shim  # noqa: F401 - keep apps/shared ahead of conflicting dirs


@dataclass(frozen=True)
class AdjacencyEdge:
    source: str
    target: str
    edge_type: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AdjacencyView:
    """A deterministic (nodes, edges) snapshot for analytical consumers."""

    nodes: list[str]
    edges: list[AdjacencyEdge]
    provenance: dict[str, Any] = field(default_factory=dict)

    def index_of(self, node_id: str) -> int:
        try:
            return self.nodes.index(node_id)
        except ValueError as exc:
            raise KeyError(f"unknown node: {node_id}") from exc

    def to_tda_input(self) -> tuple[list[str], list[tuple[int, int, float]]]:
        """Return (node_ids, weighted edge index triples) ready for TDA."""
        seen: set[str] = set()
        nodes: list[str] = []
        for edge in self.edges:
            for endpoint in (edge.source, edge.target):
                if endpoint not in seen:
                    seen.add(endpoint)
                    nodes.append(endpoint)
        nodes.sort()
        lookup = {node_id: position for position, node_id in enumerate(nodes)}
        triples = [
            (lookup[edge.source], lookup[edge.target], float(edge.properties.get("weight", 1.0)))
            for edge in sorted(self.edges, key=lambda e: (e.source, e.target, e.edge_type))
        ]
        return nodes, triples

    def degree_centrality(self) -> dict[str, int]:
        """Plain degree per node — the cheapest structural signal."""
        degrees: dict[str, int] = {node_id: 0 for node_id in self.nodes}
        for edge in self.edges:
            degrees.setdefault(edge.source, 0)
            degrees.setdefault(edge.target, 0)
            degrees[edge.source] += 1
            degrees[edge.target] += 1
        return degrees

    def subgraph(self, node_ids: Iterable[str]) -> "AdjacencyView":
        """Deterministic induced subgraph (bounds TDA workloads)."""
        keep = frozenset(node_ids)
        edges = [e for e in self.edges if e.source in keep and e.target in keep]
        return AdjacencyView(
            nodes=sorted(keep), edges=edges, provenance=dict(self.provenance)
        )


def build_adjacency(
    edges: Iterable[AdjacencyEdge | tuple[str, str, str]],
    *,
    nodes: Iterable[str] | None = None,
    provenance: dict[str, Any] | None = None,
) -> AdjacencyView:
    """Build a view from explicit edges (deterministic order, no duplicates)."""
    normalized: list[AdjacencyEdge] = []
    seen: set[tuple[str, str, str]] = set()
    for edge in edges:
        item = edge if isinstance(edge, AdjacencyEdge) else AdjacencyEdge(*edge)
        key = (item.source, item.target, item.edge_type)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(item)
    node_ids = set(nodes or [])
    node_ids.update(item.source for item in normalized)
    node_ids.update(item.target for item in normalized)
    return AdjacencyView(
        nodes=sorted(node_ids),
        edges=sorted(normalized, key=lambda e: (e.source, e.target, e.edge_type)),
        provenance=dict(provenance or {}),
    )


def adjacency_from_store(
    store: Any,
    *,
    node_ids: Iterable[str] | None = None,
    edge_type: str | None = None,
    provenance: dict[str, Any] | None = None,
) -> AdjacencyView:
    """Read adjacency from a GraphStore-like projection (deterministic).

    ``node_ids=None`` enumerates every node the store exposes; otherwise the
    view is restricted to the given set (bounding analytical workloads).
    """
    all_nodes = list(store.nodes()) if hasattr(store, "nodes") else list(node_ids or [])
    selected = (
        sorted(set(node_ids)) if node_ids is not None else sorted(str(n) for n in all_nodes)
    )
    edges: list[AdjacencyEdge] = []
    for node in selected:
        for neighbor in sorted(store.neighbors(str(node), edge_type)):
            edges.append(
                AdjacencyEdge(
                    source=str(node),
                    target=str(neighbor),
                    edge_type=edge_type or "",
                )
            )
    return build_adjacency(edges, provenance=provenance)


def to_distance_matrix(view: AdjacencyView) -> tuple[list[str], list[list[float]]]:
    """Shortest-path distance matrix over unweighted edges (TDA input)."""
    nodes, triples = view.to_tda_input()
    lookup = {node_id: position for position, node_id in enumerate(nodes)}
    size = len(nodes)
    inf = float("inf")
    matrix = [[0.0 if i == j else inf for j in range(size)] for i in range(size)]
    for source, target, weight in triples:
        distance = min(weight, 1.0)
        i, j = lookup[source], lookup[target]
        matrix[i][j] = min(matrix[i][j], distance)
        matrix[j][i] = min(matrix[j][i], distance)  # undirected for H0/H1
    for k in range(size):
        for i in range(size):
            through_k = matrix[i][k]
            if through_k == inf:
                continue
            for j in range(size):
                candidate = through_k + matrix[k][j]
                if candidate < matrix[i][j]:
                    matrix[i][j] = candidate
    return nodes, matrix


def co_mention_adjacency(
    mentions_by_entity: dict[str, Iterable[str]],
    *,
    provenance: dict[str, Any] | None = None,
) -> AdjacencyView:
    """Entity↔entity co-mention view for network analysis (US4).

    ``mentions_by_entity`` maps entity_id → observation ids mentioning it. Two
    entities connect when they co-occur in the same observation; the edge keeps
    the shared observation id so the analyst traces it back to evidence.
    """
    enforce_projection_provenance(
        provenance or {"event_id": "co-mention", "observation_id": ""}
    )
    observation_index: dict[str, list[str]] = {}
    for entity_id, observations in mentions_by_entity.items():
        for observation_id in observations:
            observation_index.setdefault(str(observation_id), []).append(entity_id)
    edges: list[AdjacencyEdge] = []
    for observation_id in sorted(observation_index):
        entities = sorted(set(observation_index[observation_id]))
        for position, left in enumerate(entities):
            for right in entities[position + 1 :]:
                edges.append(
                    AdjacencyEdge(
                        source=left,
                        target=right,
                        edge_type="co_mention",
                        properties={"observation_id": observation_id},
                    )
                )
    return build_adjacency(
        edges,
        provenance={
            "event_id": "co-mention-projection",
            "observation_id": ",".join(sorted(observation_index)),
            **(provenance or {}),
        },
    )