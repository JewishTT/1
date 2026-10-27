"""Projection of admitted SQL claims to the derived graph.

This module accepts an explicit validation record and refuses every verdict except
VALID. Candidate rows have no call path into it.
"""
from __future__ import annotations

from typing import Any

from domain.relation_identity import RelationArityMode
from graph.abstraction import GraphStore
from graph.relation_store import GraphProjectionBridge


def _value(value: Any) -> str:
    return str(getattr(value, "value", value)).strip().lower()


def project_admitted_claim(
    graph_store: GraphStore,
    claim: Any,
    *,
    validation_record: dict[str, Any],
) -> dict[str, int | str]:
    """Idempotently project one admitted claim revision and its evidence references."""
    if not validation_record or _value(validation_record.get("verdict", "")) != "valid":
        raise ValueError("only a durably recorded VALID claim may enter the graph projection")
    if _value(getattr(claim, "status", "")) != "active":
        raise ValueError("only an active claim revision may enter the graph projection")
    tenant_id = str(getattr(claim, "tenant_id", "") or "").strip()
    if not tenant_id:
        raise ValueError("claim tenant_id is required for graph projection")
    observations = tuple(str(ref) for ref in getattr(claim, "observation_refs", ()) if str(ref))
    if not observations:
        raise ValueError("a graph claim must retain at least one observation reference")

    provenance = {
        "event_id": f"claim-validation:{claim.relation_id}",
        "observation_id": observations[0],
        "tenant_id": tenant_id,
    }
    bridge = GraphProjectionBridge()
    nodes = bridge.to_nodes(claim)
    for node in nodes:
        graph_store.write_node(node, provenance)

    if _value(getattr(claim, "arity_mode", "")) == RelationArityMode.NARY.value:
        graph_store.write_hyperedge(bridge.to_hyperedge(claim), provenance)
        return {"relation_id": str(claim.relation_id), "nodes": len(nodes), "edges": 0, "hyperedges": 1}

    graph_store.write_edge(bridge.to_edge(claim), provenance)
    return {"relation_id": str(claim.relation_id), "nodes": len(nodes), "edges": 1, "hyperedges": 0}


__all__ = ["project_admitted_claim"]
