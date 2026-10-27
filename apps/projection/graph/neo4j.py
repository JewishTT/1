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

    @classmethod
    def from_settings(cls) -> Neo4jGraphStore:
        """Build the production adapter from the shared service settings."""
        from config.settings import get_settings
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise RuntimeError(
                "The Neo4j graph worker requires the neo4j Python driver"
            ) from exc
        settings = get_settings()
        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        store = cls(driver)
        store.ensure_constraints()
        return store

    def ensure_constraints(self) -> None:
        """Install tenant-scoped node identity constraints required for safe MERGE."""
        with self._driver.session() as session:
            session.run(
                "CREATE CONSTRAINT projection_node_tenant_identity IF NOT EXISTS "
                "FOR (n:ProjectionNode) REQUIRE (n.tenant_id, n.node_id) IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT projection_hyperedge_tenant_identity IF NOT EXISTS "
                "FOR (h:HyperEdge) REQUIRE (h.tenant_id, h.edge_id) IS UNIQUE"
            )

    @staticmethod
    def _tenant_id(properties: dict, provenance: dict) -> str:
        tenant_id = str(properties.get("tenant_id") or provenance.get("tenant_id") or "").strip()
        if not tenant_id:
            raise ValueError("tenant_id is required for tenant-scoped Neo4j writes")
        return tenant_id

    def close(self) -> None:
        """Close the injected Neo4j driver during worker shutdown."""
        self._driver.close()

    def write_node(self, node: GraphNode, provenance: dict) -> None:
        enforce_projection_provenance(provenance)
        label = self._sanitize(node.node_type)
        tenant_id = self._tenant_id(node.properties, provenance)
        with self._driver.session() as session:
            session.run(
                f"MERGE (n:ProjectionNode:{label} {{tenant_id: $tenant_id, node_id: $node_id}}) "
                "ON CREATE SET n += $props RETURN n",
                tenant_id=tenant_id,
                node_id=node.node_id,
                props={**node.properties, "tenant_id": tenant_id},
            )

    def write_hyperedge(self, edge: HyperEdge, provenance: dict) -> str:
        """Reify one n-ary relation with tenant-scoped node and membership keys."""
        enforce_projection_provenance(provenance)
        rel_label = self._sanitize(edge.edge_type)
        tenant_id = self._tenant_id(edge.properties, provenance)
        with self._driver.session() as session:
            session.run(
                "MERGE (h:ProjectionNode:HyperEdge {tenant_id: $tenant_id, edge_id: $edge_id}) "
                "ON CREATE SET h.rel_id = $edge_id, h.edge_type = $edge_type, h += $props",
                tenant_id=tenant_id,
                edge_id=edge.edge_id,
                edge_type=edge.edge_type,
                props={**dict(edge.properties), "tenant_id": tenant_id},
            )
            for member in edge.members:
                session.run(
                    "MATCH (m:ProjectionNode {tenant_id: $tenant_id, node_id: $member}), "
                    "(h:HyperEdge {tenant_id: $tenant_id, edge_id: $edge_id}) "
                    f"MERGE (m)-[:PART_OF_{rel_label} {{tenant_id: $tenant_id}}]->(h)",
                    tenant_id=tenant_id,
                    member=member,
                    edge_id=edge.edge_id,
                )
        return edge.edge_id

    def write_edge(self, edge: GraphEdge, provenance: dict) -> None:
        """Upsert a relation by tenant and claim revision id, never by endpoints."""
        enforce_projection_provenance(provenance)
        rel = self._sanitize(edge.edge_type)
        tenant_id = self._tenant_id(edge.properties, provenance)
        with self._driver.session() as session:
            session.run(
                f"MATCH (a:ProjectionNode {{tenant_id: $tenant_id, node_id: $source}}), "
                f"(b:ProjectionNode {{tenant_id: $tenant_id, node_id: $target}}) "
                f"MERGE (a)-[r:{rel} {{tenant_id: $tenant_id, rel_id: $rel_id}}]->(b) "
                "SET r += $props RETURN r",
                tenant_id=tenant_id,
                source=edge.source,
                target=edge.target,
                rel_id=edge.edge_id,
                props={**dict(edge.properties), "tenant_id": tenant_id},
            )

    def neighbors(
        self,
        node_id: str,
        edge_type: str | None = None,
        *,
        direction: str | EdgeDirection | None = None,
        tenant_id: str | None = None,
    ) -> list[str]:
        """Return tenant-scoped neighbors; an omitted tenant is refused."""
        if not tenant_id or not tenant_id.strip():
            raise ValueError("tenant_id is required for tenant-scoped Neo4j traversal")
        wanted = EdgeDirection.OUT if direction is None else EdgeDirection(str(direction).lower())
        rel = f":{self._sanitize(edge_type)}" if edge_type else ""
        if wanted == EdgeDirection.IN:
            step = f"<-[r{rel}]-"
        elif wanted == EdgeDirection.BOTH:
            step = f"-[r{rel}]-"
        else:
            step = f"-[r{rel}]->"
        query = (
            f"MATCH (n:ProjectionNode {{tenant_id:$tenant_id, node_id:$id}}){step}"
            "(m:ProjectionNode {tenant_id:$tenant_id}) RETURN m.node_id"
        )
        with self._driver.session() as session:
            rows = session.run(query, id=node_id, tenant_id=tenant_id).data()
        return sorted(r["m.node_id"] for r in rows)

    def node(self, node_id: str, *, tenant_id: str | None = None) -> GraphNode | None:
        """Read one node only within its tenant."""
        if not tenant_id or not tenant_id.strip():
            raise ValueError("tenant_id is required for tenant-scoped Neo4j node reads")
        with self._driver.session() as session:
            rows = session.run(
                "MATCH (n:ProjectionNode {tenant_id:$tenant_id, node_id:$id}) "
                "RETURN n.node_id AS id, labels(n) AS labels, properties(n) AS full",
                id=node_id,
                tenant_id=tenant_id,
            ).data()
        if not rows:
            return None
        data: dict[str, Any] = dict(rows[0]["full"])
        labels = [str(label) for label in rows[0].get("labels", [])]
        node_type = next((label for label in labels if label != "ProjectionNode"), "Unknown")
        data.pop("tenant_id", None)
        return GraphNode(node_id=node_id, node_type=node_type, properties=data)

    def delete_logical_relation(self, tenant_id: str, logical_relation_id: str) -> int:
        """Remove binary edges and reified hyperedges for one logical relation."""
        if not tenant_id.strip() or not logical_relation_id.strip():
            raise ValueError("tenant_id and logical_relation_id are required")
        with self._driver.session() as session:
            edge_rows = session.run(
                "MATCH (a:ProjectionNode {tenant_id: $tenant_id})-[r]->"
                "(b:ProjectionNode {tenant_id: $tenant_id}) "
                "WHERE r.tenant_id = $tenant_id "
                "AND r.logical_relation_id = $logical_relation_id "
                "WITH collect(r) AS rels, count(r) AS deleted "
                "FOREACH (r IN rels | DELETE r) RETURN deleted",
                tenant_id=tenant_id,
                logical_relation_id=logical_relation_id,
            ).data()
            hyper_rows = session.run(
                "MATCH (h:ProjectionNode:HyperEdge {tenant_id: $tenant_id, "
                "logical_relation_id: $logical_relation_id}) "
                "WITH collect(h) AS nodes, count(h) AS deleted "
                "FOREACH (h IN nodes | DETACH DELETE h) RETURN deleted",
                tenant_id=tenant_id,
                logical_relation_id=logical_relation_id,
            ).data()
        edges_deleted = int(edge_rows[0].get("deleted", 0)) if edge_rows else 0
        hyperedges_deleted = int(hyper_rows[0].get("deleted", 0)) if hyper_rows else 0
        return edges_deleted + hyperedges_deleted

    def clear_tenant_projection(self, tenant_id: str) -> int:
        """Clear a tenant's projected nodes and relations before a canonical rebuild."""
        if not tenant_id.strip():
            raise ValueError("tenant_id is required")
        with self._driver.session() as session:
            rows = session.run(
                "MATCH (n:ProjectionNode {tenant_id: $tenant_id}) "
                "WITH collect(n) AS nodes, count(n) AS deleted "
                "FOREACH (n IN nodes | DETACH DELETE n) RETURN deleted",
                tenant_id=tenant_id,
            ).data()
        return int(rows[0].get("deleted", 0)) if rows else 0

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
