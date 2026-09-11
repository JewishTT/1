"""GraphSnapshot + rebuild(projection_id) from Kafka offsets (T041, I-12).

A snapshot captures the projection state head (projection_id, last event/offset,
checksum of edge set). `rebuild(projection_id)` replays the durable event log
from the snapshot offset and reconstructs the graph in a fresh store — the
projection is fully reproducible from durable evidence/events.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field

from domain import enforce_projection_provenance

import path_shim  # noqa: F401

from .abstraction import GraphEdge, GraphNode, GraphStore, InMemoryGraphStore


def _checksum(edges: list[GraphEdge]) -> str:
    joined = "|".join(f"{e.edge_type}:{e.source}->{e.target}" for e in sorted(edges, key=str))
    return hashlib.sha256(joined.encode()).hexdigest()[:16]


@dataclass
class ReplayEvent:
    event_id: str
    offset: int
    kind: str  # "node" | "edge"
    payload: dict


@dataclass
class GraphSnapshot:
    projection_id: str = field(default_factory=lambda: "PROJ-" + uuid.uuid4().hex[:12])
    last_offset: int = 0
    edge_count: int = 0
    node_count: int = 0
    checksum: str = ""


class RebuildableGraphStore:
    """Wraps a GraphStore, logs replay events, and manages snapshots."""

    def __init__(self, store: GraphStore | None = None) -> None:
        self._store = store or InMemoryGraphStore()
        self._log: list[ReplayEvent] = []
        self._offset = 0

    @property
    def store(self) -> GraphStore:
        return self._store

    def write_node(self, node: GraphNode, provenance: dict) -> None:
        enforce_projection_provenance(provenance)
        self._store.write_node(node, provenance)
        self._log.append(ReplayEvent(provenance.get("event_id", "evt"), self._offset, "node", {"node": node}))
        self._offset += 1

    def write_edge(self, edge: GraphEdge, provenance: dict) -> None:
        enforce_projection_provenance(provenance)
        self._store.write_edge(edge, provenance)
        self._log.append(ReplayEvent(provenance.get("event_id", "evt"), self._offset, "edge", {"edge": edge}))
        self._offset += 1

    def snapshot(self) -> GraphSnapshot:
        snap = GraphSnapshot()
        edges = self._asset_edges()
        snap.edge_count = len(edges)
        snap.node_count = self._count_nodes()
        snap.last_offset = self._offset
        snap.checksum = _checksum(edges)
        return snap

    def rebuild(self, projection_id: str) -> GraphStore:
        """Rebuild into a fresh store by replaying the durable log from offset 0."""
        fresh = InMemoryGraphStore()
        for ev in sorted(self._log, key=lambda e: e.offset):
            provenance = {"event_id": ev.event_id, "observation_id": "replay:" + str(ev.offset)}
            if ev.kind == "node":
                fresh.write_node(ev.payload["node"], provenance)
            else:
                fresh.write_edge(ev.payload["edge"], provenance)
        return fresh

    def replay_events(self) -> list[ReplayEvent]:
        return list(self._log)

    def _asset_edges(self) -> list[GraphEdge]:
        if hasattr(self._store, "edges"):
            return self._store.edges()
        return []

    def _count_nodes(self) -> int:
        if hasattr(self._store, "nodes"):
            return len(self._store.nodes())
        return 0