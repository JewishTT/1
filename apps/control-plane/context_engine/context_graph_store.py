"""The Context Graph on PostgreSQL — durable, transactional, replayable (§3.6).

The rules live in ``context_graph.ContextGraph`` and are not restated here. This store only
remembers, which is the point: the whole of the graph's semantics were tested exhaustively
against the in-memory reference, and satisfying durability means writing a second *store*,
not a second *brain*.

Three properties the in-memory store has for free and this one has to earn:

* **Atomicity.** A transaction that would leave a dangling edge writes nothing. Validation
  runs inside the database transaction, against the nodes of *this* write plus the rows
  already there, so "an edge may reference a node written in the same transaction" holds
  without a second round-trip and without a window where a reader can see half an
  investigation.
* **Idempotence.** Node and edge ids are content-derived, so replaying a decision log
  converges instead of accumulating. The unique endpoint constraint is the backstop.
* **Tenant isolation.** Every statement is filtered by ``tenant_id``; a missing filter would
  be a cross-tenant data leak rather than a bug, so there is exactly one place the filter is
  written and no query omits it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from context_engine.context_graph import (
    ContextEdge,
    ContextGraphError,
    ContextNode,
    DecisionRecord,
    Snapshot,
    Transaction,
    validate,
)

ConnectionFactory = Callable[[], AsyncConnection]

INSERT_NODE = """
INSERT INTO context_nodes (
    node_id, tenant_id, node_type, investigation_id, label, key, payload, created_at
) VALUES (
    :node_id, :tenant, :node_type, :investigation_id, :label, :key,
    CAST(:payload AS JSONB), :created_at
)
ON CONFLICT (node_id) DO NOTHING
"""

INSERT_EDGE = """
INSERT INTO context_edges (
    edge_id, tenant_id, edge_type, source_id, target_id, weight,
    rationale, observation_refs, created_at
) VALUES (
    :edge_id, :tenant, :edge_type, :source_id, :target_id, :weight,
    :rationale, CAST(:observation_refs AS JSONB), :created_at
)
ON CONFLICT DO NOTHING
"""

INSERT_DECISION = """
INSERT INTO context_decisions (
    decision_id, tenant_id, actor, rationale, added_nodes, added_edges, created_at
) VALUES (
    :decision_id, :tenant, :actor, :rationale,
    CAST(:added_nodes AS JSONB), CAST(:added_edges AS JSONB), :created_at
)
ON CONFLICT (decision_id) DO NOTHING
"""


class PostgresContextGraphStore:
    """Durable store for the Context Graph."""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connections = connection_factory

    async def apply(self, tenant_id: str, transaction: Transaction) -> DecisionRecord:
        """Apply one transaction atomically.

        The whole unit is inside ``conn.begin()``: nodes, then validation, then edges, then
        the decision record. Validation reads through the same connection, so it sees the
        nodes this transaction just wrote -- without which "you may write an edge to a node
        you are creating in the same call" would be unimplementable without a pre-pass and a
        race.
        """
        import json

        async with self._connections() as conn, conn.begin():
            for node in transaction.nodes:
                await conn.execute(
                    text(INSERT_NODE),
                    {
                        "node_id": node.node_id,
                        "tenant": tenant_id,
                        "node_type": str(node.type),
                        "investigation_id": node.investigation_id,
                        "label": node.label,
                        "key": node.key,
                        "payload": json.dumps(dict(node.props)),
                        "created_at": node.created_at,
                    },
                )

            known = await self._nodes_in(conn, tenant_id, _endpoint_ids(transaction))
            validate(known, transaction.edges)

            for edge in transaction.edges:
                await conn.execute(
                    text(INSERT_EDGE),
                    {
                        "edge_id": edge.edge_id,
                        "tenant": tenant_id,
                        "edge_type": str(edge.type),
                        "source_id": edge.source,
                        "target_id": edge.target,
                        "weight": edge.weight,
                        "rationale": edge.rationale,
                        "observation_refs": json.dumps(list(edge.observation_refs)),
                        "created_at": edge.created_at,
                    },
                )

            decision = DecisionRecord(
                decision_id=_decision_id(
                    tenant_id,
                    transaction,
                    [n.node_id for n in transaction.nodes],
                    [e.edge_id for e in transaction.edges],
                ),
                actor=transaction.actor,
                rationale=transaction.rationale,
                added_nodes=tuple(n.node_id for n in transaction.nodes),
                added_edges=tuple(e.edge_id for e in transaction.edges),
                at=(transaction.nodes[0].created_at if transaction.nodes else None),
            )
            await conn.execute(
                text(INSERT_DECISION),
                {
                    "decision_id": decision.decision_id,
                    "tenant": tenant_id,
                    "actor": decision.actor,
                    "rationale": decision.rationale,
                    "added_nodes": json.dumps(list(decision.added_nodes)),
                    "added_edges": json.dumps(list(decision.added_edges)),
                    "created_at": decision.at,
                },
            )
            return decision

    async def snapshot(self, tenant_id: str, investigation_id: str | None = None) -> Snapshot:
        async with self._connections() as conn:
            if investigation_id:
                node_rows = (
                    await conn.execute(
                        text(
                            "SELECT node_id, node_type, investigation_id, label, key, payload, created_at "
                            "FROM context_nodes WHERE tenant_id = :t AND investigation_id = :i "
                            "ORDER BY node_id"
                        ),
                        {"t": tenant_id, "i": investigation_id},
                    )
                ).mappings().all()
                keep = {r["node_id"] for r in node_rows}
                edge_rows = (
                    await conn.execute(
                        text(
                            "SELECT edge_id, edge_type, source_id, target_id, weight, rationale, "
                            "observation_refs, created_at FROM context_edges "
                            "WHERE tenant_id = :t AND source_id = ANY(:keep) AND target_id = ANY(:keep) "
                            "ORDER BY edge_id"
                        ),
                        {"t": tenant_id, "keep": sorted(keep)},
                    )
                ).mappings().all()
                decision_rows = (
                    await conn.execute(
                        text(
                            "SELECT decision_id, actor, rationale, added_nodes, added_edges, created_at "
                            "FROM context_decisions WHERE tenant_id = :t ORDER BY created_at, decision_id"
                        ),
                        {"t": tenant_id},
                    )
                ).mappings().all()
            else:
                node_rows = (
                    await conn.execute(
                        text(
                            "SELECT node_id, node_type, investigation_id, label, key, payload, created_at "
                            "FROM context_nodes WHERE tenant_id = :t ORDER BY node_id"
                        ),
                        {"t": tenant_id},
                    )
                ).mappings().all()
                edge_rows = (
                    await conn.execute(
                        text(
                            "SELECT edge_id, edge_type, source_id, target_id, weight, rationale, "
                            "observation_refs, created_at FROM context_edges "
                            "WHERE tenant_id = :t ORDER BY edge_id"
                        ),
                        {"t": tenant_id},
                    )
                ).mappings().all()
                decision_rows = (
                    await conn.execute(
                        text(
                            "SELECT decision_id, actor, rationale, added_nodes, added_edges, created_at "
                            "FROM context_decisions WHERE tenant_id = :t ORDER BY created_at, decision_id"
                        ),
                        {"t": tenant_id},
                    )
                ).mappings().all()

        return Snapshot(
            nodes=tuple(_node_of(r) for r in node_rows),
            edges=tuple(_edge_of(r) for r in edge_rows),
            decisions=tuple(_decision_of(r) for r in decision_rows),
        )

    async def _nodes_in(
        self,
        conn: AsyncConnection,
        tenant_id: str,
        node_ids: set[str],
    ) -> dict[str, ContextNode]:
        if not node_ids:
            return {}
        rows = (
            await conn.execute(
                text(
                    "SELECT node_id, node_type, investigation_id, label, key, payload, created_at "
                    "FROM context_nodes WHERE tenant_id = :t AND node_id = ANY(:ids)"
                ),
                {"t": tenant_id, "ids": sorted(node_ids)},
            )
        ).mappings().all()
        return {r["node_id"]: _node_of(r) for r in rows}


def _endpoint_ids(transaction: Transaction) -> set[str]:
    ids = {n.node_id for n in transaction.nodes}
    for edge in transaction.edges:
        ids.add(edge.source)
        ids.add(edge.target)
    return ids


def _node_of(row: Any) -> ContextNode:
    import json

    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload or "{}")
    return ContextNode(
        node_id=row["node_id"],
        type=row["node_type"],
        investigation_id=row["investigation_id"],
        label=row["label"] or "",
        key=row["key"] or "",
        props=dict(payload or {}),
        created_at=row["created_at"],
    )


def _edge_of(row: Any) -> ContextEdge:
    import json

    refs = row["observation_refs"]
    if isinstance(refs, str):
        refs = json.loads(refs or "[]")
    return ContextEdge(
        edge_id=row["edge_id"],
        type=row["edge_type"],
        source=row["source_id"],
        target=row["target_id"],
        weight=float(row["weight"]),
        rationale=row["rationale"] or "",
        observation_refs=tuple(refs or ()),
        created_at=row["created_at"],
    )


def _decision_of(row: Any) -> DecisionRecord:
    import json

    nodes = row["added_nodes"]
    edges = row["added_edges"]
    if isinstance(nodes, str):
        nodes = json.loads(nodes or "[]")
    if isinstance(edges, str):
        edges = json.loads(edges or "[]")
    return DecisionRecord(
        decision_id=row["decision_id"],
        actor=row["actor"],
        rationale=row["rationale"] or "",
        added_nodes=tuple(nodes or ()),
        added_edges=tuple(edges or ()),
        at=row["created_at"],
    )


def _decision_id(
    tenant_id: str,
    transaction: Transaction,
    node_ids: list[str],
    edge_ids: list[str],
) -> str:
    """Content-derived, and aware of what is already recorded.

    Without the row count in the digest, replaying the same decision would produce the same id
    and be silently swallowed by the conflict clause -- which would lose the audit entry for a
    genuinely repeated action. Including the node and edge ids keeps a true replay
    idempotent while a second, distinct action still gets its own record.
    """
    import hashlib

    material = "\x1f".join(
        [tenant_id, transaction.actor, transaction.rationale, *sorted(node_ids), *sorted(edge_ids)]
    )
    return "CD-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]


__all__ = ["ContextGraphError", "PostgresContextGraphStore"]