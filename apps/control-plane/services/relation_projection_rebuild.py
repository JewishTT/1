"""Rebuild a tenant's graph projection from canonical SQL claim revisions.

The rebuild is idempotent, but not a blue/green atomic swap. If interrupted after
clearing the graph, rerun it; the SQL claim ledger and verdict JSONB remain canonical.
"""
from __future__ import annotations

import argparse
import asyncio
from typing import Any

from sqlalchemy import func, select

from db.relation_claim_store import _from_row
from db.schema import RelationClaim as RelationClaimRow
from db.session import create_tables, make_session_factory
from graph.claim_projection import project_admitted_claim
from graph.neo4j import Neo4jGraphStore


def _is_valid(record: dict[str, Any] | None) -> bool:
    if not record:
        return False
    verdict = getattr(record.get("verdict", ""), "value", record.get("verdict", ""))
    return str(verdict).strip().lower() == "valid"


async def rebuild_tenant_claim_projection(
    tenant_id: str,
    *,
    batch_size: int = 250,
    graph_store: Any | None = None,
    session_factory: Any | None = None,
) -> dict[str, int | str]:
    """Clear derived graph state for one tenant, then rebuild from latest revisions."""
    if not tenant_id.strip():
        raise ValueError("tenant_id is required")
    batch_size = max(1, min(int(batch_size), 1000))
    owns_factory = session_factory is None
    factory = session_factory or make_session_factory()
    owns_graph = graph_store is None
    graph = graph_store if graph_store is not None else Neo4jGraphStore.from_settings()
    counts: dict[str, int | str] = {
        "tenant_id": tenant_id, "seen": 0, "projected": 0, "skipped": 0, "failed": 0
    }
    try:
        await create_tables()
        async with factory() as session:
            result = await session.execute(
                select(func.count(RelationClaimRow.relation_id)).where(
                    RelationClaimRow.tenant_id == tenant_id
                )
            )
            counts["seen"] = int(result.scalar_one() or 0)
            await session.commit()

        graph.clear_tenant_projection(tenant_id)
        offset = 0
        while True:
            ranked = (
                select(
                    RelationClaimRow.relation_id.label("relation_id"),
                    func.row_number()
                    .over(
                        partition_by=RelationClaimRow.logical_relation_id,
                        order_by=(
                            RelationClaimRow.revision_number.desc(),
                            RelationClaimRow.created_at.desc(),
                            RelationClaimRow.relation_id.desc(),
                        ),
                    )
                    .label("revision_rank"),
                )
                .where(RelationClaimRow.tenant_id == tenant_id)
                .subquery()
            )
            async with factory() as session:
                query = (
                    select(RelationClaimRow)
                    .join(ranked, ranked.c.relation_id == RelationClaimRow.relation_id)
                    .where(ranked.c.revision_rank == 1)
                    .order_by(RelationClaimRow.logical_relation_id)
                    .offset(offset)
                    .limit(batch_size)
                )
                result = await session.execute(query)
                rows = list(result.scalars().all())
                await session.commit()
            if not rows:
                break
            for row in rows:
                if not _is_valid(row.validation_record) or str(row.status).lower() != "active":
                    counts["skipped"] = int(counts["skipped"]) + 1
                    continue
                try:
                    project_admitted_claim(
                        graph,
                        _from_row(row),
                        validation_record=row.validation_record,
                    )
                    counts["projected"] = int(counts["projected"]) + 1
                except Exception:  # noqa: BLE001 - count failures; next rebuild can retry
                    counts["failed"] = int(counts["failed"]) + 1
            offset += len(rows)
        return counts
    finally:
        if owns_graph and hasattr(graph, "close"):
            graph.close()
        if owns_factory:
            bind = getattr(factory, "kw", {}).get("bind")
            if bind is not None:
                await bind.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--batch-size", type=int, default=250)
    args = parser.parse_args()
    print(
        asyncio.run(
            rebuild_tenant_claim_projection(args.tenant_id, batch_size=args.batch_size)
        )
    )


__all__ = ["main", "rebuild_tenant_claim_projection"]
