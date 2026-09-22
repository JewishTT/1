"""Neo4j adapter (T038) — the ONLY module allowed to import the vendor driver.

Application code talks to `GraphStore`; this adapter implements the same
protocol over Neo4j. Kept thin: label sanitization, node/edge upserts.
"""

from __future__ import annotations

from typing import Any

from domain import enforce_projection_provenance

import path_shim  # noqa: F401

from .abstraction import GraphEdge, GraphNode, GraphStore, HyperEdge


class Neo4jGraphStore(GraphStore):
    def __init__(self, driver=None) -> None:
        self._driver = driver
        if driver is None:
            raise RuntimeError("Neo4jGraphStore requires a neo4j.Driver instance")

    def write_node(self, node: GraphNode, provenance: dict) -> None:
        enforce_projection_provenance(provenance)
        label = self._sanitize(node.node_type)
        with self._driver.session() as session:
            session.run(
                f"MERGE (n:{label} {{node_id: $node_id}}) "
                "ON CREATE SET n += $props RETURN n",
                node_id=node.node_id,
                props=node.properties,
            )

    def write_hyperedge(self, edge: HyperEdge, provenance: dict) -> str:
        """Reify an N-ary relation: hyperedge node + participation edges.

        Neo4j has no native hyperedges; the deterministic ``edge_id`` makes
        the reification idempotent (I-11) and rebuildable from events (I-12).
        Participation is modeled as ``PART_OF_<TYPE>`` edges from each member
        to the hyperedge node — pairwise/co-mention projections remain
        derived, never authoritative.
        """
        enforce_projection_provenance(provenance)
        rel_label = self._sanitize(edge.edge_type)
        with self._driver.session() as session:
            session.run(
                "MERGE (h:HyperEdge {edge_id: $edge_id}) "
                "ON CREATE SET h.edge_type = $edge_type, h += $props",
                edge_id=edge.edge_id,
                edge_type=edge.edge_type,
                props=dict(edge.properties),
            )
            for member in edge.members:
                session.run(
                    "MATCH (m {node_id: $member}), (h:HyperEdge {edge_id: $edge_id}) "
                    f"MERGE (m)-[:PART_OF_{rel_label}]->(h)",
                    member=member,
                    edge_id=edge.edge_id,
                )
        return edge.edge_id

    def write_edge(self, edge: GraphEdge, provenance: dict) -> None:
        enforce_projection_provenance(provenance)
        rel = self._sanitize(edge.edge_type)
        with self._driver.session() as session:
            session.run(
                f"MATCH (a {{node_id:$source}}), (b {{node_id:$target}}) "
                f"MERGE (a)-[r:{rel}]->(b) RETURN r",
                source=edge.source,
                target=edge.target,
            )

    def neighbors(self, node_id: str, edge_type: str | None = None) -> list[str]:
        rel = self._sanitize(edge_type) if edge_type else None
        query = "MATCH (n {node_id:$id})-[r]->(m) RETURN m.node_id"
        if rel:
            query = f"MATCH (n {{node_id:$id}})-[r:{rel}]->(m) RETURN m.node_id"
        with self._driver.session() as session:
            rows = session.run(query, id=node_id).data()
        return sorted(r["m.node_id"] for r in rows)

    def node(self, node_id: str) -> GraphNode | None:
        with self._driver.session() as session:
            rows = session.run(
                "MATCH (n {node_id:$id}) RETURN n.node_id AS id, n AS full", id=node_id
            ).data()
        if not rows:
            return None
        data: dict[str, Any] = dict(rows[0]["full"])
        node_type = data.pop("_type", "Unknown")
        return GraphNode(node_id=node_id, node_type=node_type, properties=data)

    @staticmethod
    def _sanitize(name: str) -> str:
        out: list[str] = []
        prev = ""
        for c in name:
            ch = c if c.isalnum() else "_"
            if ch == "_" and prev == "_":
                continue  # collapse consecutive separators
            out.append(ch)
            prev = ch
        safe = "".join(out).strip("_")
        if not safe or safe[0].isdigit():
            safe = "_" + safe
        return safe