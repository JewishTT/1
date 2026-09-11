"""Graph abstraction impl (T038, I-2, I-11, I-12).

No vendor imports here: `GraphStore` is a pure protocol + in-memory store.
Uri/typed nodes and edges; idempotent writes (I-11); every write must carry
provenance (I-12) else it is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from domain import enforce_projection_provenance

import path_shim  # noqa: F401 - ensure apps/shared precedes conflicting dirs


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    node_type: str
    properties: dict[str, Any] = field(default_factory=dict)

    def __hash__(self) -> int:
        return hash((self.node_id, self.node_type))


@dataclass(frozen=True)
class GraphEdge:
    edge_type: str
    source: str
    target: str
    properties: dict[str, Any] = field(default_factory=dict)

    def __hash__(self) -> int:
        return hash((self.edge_type, self.source, self.target))


class GraphStore(Protocol):
    def write_node(self, node: GraphNode, provenance: dict) -> None: ...
    def write_edge(self, edge: GraphEdge, provenance: dict) -> None: ...
    def neighbors(self, node_id: str, edge_type: str | None = None) -> list[str]: ...
    def node(self, node_id: str) -> GraphNode | None: ...


class InMemoryGraphStore:
    """In-memory GraphStore honoring I-11 (idempotent) and I-12 (provenance)."""

    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: set[GraphEdge] = set()
        self._adj: dict[str, set[GraphEdge]] = {}

    def write_node(self, node: GraphNode, provenance: dict) -> None:
        enforce_projection_provenance(provenance)
        if node.node_id in self._nodes:
            existing = self._nodes[node.node_id]
            if existing.node_type != node.node_type:
                raise ValueError(
                    f"Node {node.node_id} type immutable: {existing.node_type} != {node.node_type}"
                )
            return  # idempotent: same identity, no duplicate
        self._nodes[node.node_id] = node

    def write_edge(self, edge: GraphEdge, provenance: dict) -> None:
        enforce_projection_provenance(provenance)
        if edge.source not in self._nodes or edge.target not in self._nodes:
            raise ValueError(f"Edge endpoints must exist: {edge.source} -> {edge.target}")
        if edge in self._edges:
            return  # idempotent (I-11)
        self._edges.add(edge)
        self._adj.setdefault(edge.source, set()).add(edge)
        self._adj.setdefault(edge.target, set()).add(edge)

    def neighbors(self, node_id: str, edge_type: str | None = None) -> list[str]:
        out: set[str] = set()
        for e in self._adj.get(node_id, set()):
            if edge_type is None or e.edge_type == edge_type:
                out.add(e.target if e.source == node_id else e.source)
        return sorted(out)

    def node(self, node_id: str) -> GraphNode | None:
        return self._nodes.get(node_id)

    def nodes(self) -> list[GraphNode]:
        return list(self._nodes.values())

    def edges(self) -> list[GraphEdge]:
        return sorted(self._edges, key=lambda e: (e.source, e.target, e.edge_type))