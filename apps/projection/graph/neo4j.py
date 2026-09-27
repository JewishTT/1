"""Neo4j adapter (T038) — the ONLY module allowed to import the vendor driver.

Application code talks to `GraphStore`; this adapter implements the same
protocol structurally over Neo4j (T077 — it does not subclass the protocol).
Kept thin: label sanitization, node/edge upserts. Relations are MERGEd on the
caller-supplied id, never on the endpoint pair, so two relations of one type
between the same pair stay distinct and a re-write is idempotent (I-11).
"""

from __future__ import annotations

from typing import Any

from domain import enforce_projection_provenance

import path_shim  # noqa: F401 - ensure apps/shared precedes conflicting dirs

from .abstraction import EdgeDirection, GraphEdge, GraphNode, HyperEdge


class Neo4jGraphStore:
    """Structural `GraphStore` implementation over a neo4j driver (T077)."""

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
        The reified node carries that id under both ``edge_id`` and ``rel_id``
        so reification is MERGEd on the id and shares the identifier namespace
        with the pairwise path. Participation is modeled as
        ``PART_OF_<TYPE>`` edges from each member to the hyperedge node —
        pairwise/co-mention projections remain derived, never authoritative.
        """
        enforce_projection_provenance(provenance)
        rel_label = self._sanitize(edge.edge_type)
        with self._driver.session() as session:
            session.run(
                "MERGE (h:HyperEdge {edge_id: $edge_id, rel_id: $edge_id}) "
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
        """Upsert a relation MERGEd on ``rel_id`` with the full payload (FR-038).

        The id is supplied by the caller (the relation layer) and is never
        invented here; MERGEing on it rather than on the endpoint pair keeps two
        relations of one type between the same pair distinct, and re-writing one
        id updates its properties instead of creating a second relationship.
        """
        enforce_projection_provenance(provenance)
        rel = self._sanitize(edge.edge_type)
        with self._driver.session() as session:
            session.run(
                f"MATCH (a {{node_id:$source}}), (b {{node_id:$target}}) "
                f"MERGE (a)-[r:{rel} {{rel_id:$rel_id}}]->(b) "
                "SET r += $props RETURN r",
                source=edge.source,
                target=edge.target,
                rel_id=edge.edge_id,
                props=dict(edge.properties),
            )

    def neighbors(
        self,
        node_id: str,
        edge_type: str | None = None,
        *,
        direction: str | EdgeDirection | None = None,
    ) -> list[str]:
        """Neighbouring node ids, direction preserved (FR-010).

        Mirrors `InMemoryGraphStore.neighbors`, including the mode-derived
        default when `direction` is omitted.
        """
        wanted = EdgeDirection.OUT if direction is None else EdgeDirection(str(direction).lower())
        rel = f":{self._sanitize(edge_type)}" if edge_type else ""
        if wanted == EdgeDirection.IN:
            step = f"<-[r{rel}]-"
        elif wanted == EdgeDirection.BOTH:
            step = f"-[r{rel}]-"
        else:
            step = f"-[r{rel}]->"
        query = f"MATCH (n {{node_id:$id}}){step}(m) RETURN m.node_id"
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
        """Coerce a type name into a valid ASCII Cypher label.

        Only ASCII alphanumerics survive: `str.isalnum()` is also true for
        Cyrillic and other non-ASCII letters, which would emit an invalid (or,
        worse, silently different) label, so every other character collapses to
        a single separator. A name with no ASCII content sanitizes to the empty
        string rather than to a label the driver cannot parse.
        """
        out: list[str] = []
        prev = ""
        for c in name:
            ch = c if (c.isascii() and c.isalnum()) else "_"
            if ch == "_" and prev == "_":
                continue  # collapse consecutive separators
            out.append(ch)
            prev = ch
        safe = "".join(out).strip("_")
        if not safe or safe[0].isdigit():
            safe = "_" + safe
        return safe
