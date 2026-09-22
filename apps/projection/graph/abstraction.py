"""Graph abstraction impl (T038, I-2, I-11, I-12).

No vendor imports here: `GraphStore` is a pure protocol + in-memory store.
Uri/typed nodes and edges; idempotent writes (I-11); every write must carry
provenance (I-12) else it is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from domain import enforce_projection_provenance
from domain.hypergraph import hyperedge_id

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


@dataclass(frozen=True)
class HyperEdge:
    """Projection-level hyperedge (feature 009).

    N-ary temporal relation over nodes. The native N-ary form is primary;
    pairwise projections are derived and lossy. Identity is deterministic
    on (edge_type, members, valid_from); writes are idempotent (I-11) and
    provenance-enforced (I-12) — mirrors domain.hypergraph.HyperEdge while
    staying a projection-level contract (no domain imports needed here).
    """

    edge_type: str
    source: tuple[str, ...]  # N members; source/target kept for symmetry
    target: str = ""
    properties: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        members = tuple(self.source)
        if len(members) < 2:
            raise ValueError(f"hyperedge requires >= 2 members, got {len(members)}")
        if len(set(members)) != len(members):
            raise ValueError("hyperedge members must be distinct")
        object.__setattr__(self, "source", tuple(sorted(members)))
        if not self.edge_type:
            raise ValueError("hyperedge requires edge_type")

    @property
    def members(self) -> tuple[str, ...]:
        return self.source

    @property
    def edge_id(self) -> str:
        """Deterministic identity shared with the domain (block G).

        Delegates to the single ``hyperedge_id`` helper so the projection can
        never diverge from the domain's logical identity for the same N-ary
        relation (edge_type, members, tenant).
        """
        return hyperedge_id(
            self.edge_type,
            self.source,
            tenant_id=self.properties.get("tenant_id", "default-tenant"),
        )

    def __hash__(self) -> int:
        return hash((self.edge_type, self.source))

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, HyperEdge)
            and self.edge_type == other.edge_type
            and self.source == other.source
        )


class GraphStore(Protocol):
    def write_node(self, node: GraphNode, provenance: dict) -> None: ...
    def write_edge(self, edge: GraphEdge, provenance: dict) -> None: ...
    def write_hyperedge(self, edge: HyperEdge, provenance: dict) -> str: ...
    def neighbors(self, node_id: str, edge_type: str | None = None) -> list[str]: ...
    def node(self, node_id: str) -> GraphNode | None: ...


class InMemoryGraphStore:
    """In-memory GraphStore honoring I-11 (idempotent) and I-12 (provenance)."""

    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: set[GraphEdge] = set()
        self._adj: dict[str, set[GraphEdge]] = {}
        self._hyperedges: dict[str, HyperEdge] = {}
        self._hyper_membership: dict[str, set[str]] = {}

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

    def write_hyperedge(self, edge: HyperEdge, provenance: dict) -> str:
        """Idempotent N-ary write (I-11): hyperedge stored natively.

        Membership becomes explicit participation edges (derived), but the
        N-ary form itself is retained as primary — pairwise views are
        projections, never the authority.
        """
        enforce_projection_provenance(provenance)
        for member in edge.members:
            if member not in self._nodes:
                raise ValueError(f"Hyperedge member missing: {member}")
        if edge in self._hyperedges:
            return edge.edge_id  # idempotent (I-11)
        self._hyperedges[edge.edge_id] = edge
        for member in edge.members:
            self._hyper_membership.setdefault(member, set()).add(edge.edge_id)
        return edge.edge_id

    def hyperedge(self, edge_id: str) -> HyperEdge | None:
        return self._hyperedges.get(edge_id)

    def member_hyperedges(self, node_id: str) -> list[HyperEdge]:
        """All N-ary relations a node participates in (native, ordered)."""
        return sorted(
            (self._hyperedges[eid] for eid in self._hyper_membership.get(node_id, set())),
            key=lambda e: e.edge_id,
        )

    def hyperedges(self) -> list[HyperEdge]:
        return sorted(self._hyperedges.values(), key=lambda e: e.edge_id)

    def incidence_complex(self) -> dict[str, Any]:
        """Maximal simplices for the TDA plane (native N-ary, deterministic)."""
        return {
            "maximal_simplices": [
                {
                    "simplex_id": e.edge_id,
                    "nodes": list(e.members),
                    "dim": len(e.members) - 1,
                    "edge_type": e.edge_type,
                }
                for e in self.hyperedges()
            ]
        }

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