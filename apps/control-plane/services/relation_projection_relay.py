"""Durable at-least-once relay from VALID claim verdicts to the Neo4j projection."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.relation_claim_store import SqlRelationClaimStore
from db.schema import RelationClaim as RelationClaimRow
from db.schema import RelationClaimProjectionOutbox
from db.session import create_tables, make_session_factory
from projection.graph.claim_projection import project_admitted_claim
from projection.graph.neo4j import Neo4jGraphStore


LEASE = timedelta(minutes=10)


def _valid_record(record: dict[str, Any] | None) -> bool:
    if not record:
        return False
    verdict = getattr(record.get("verdict", ""), "value", record.get("verdict", ""))
    return str(verdict).strip().lower() == "valid"


async def _claim_batch(
    session: AsyncSession,
    *,
    limit: int,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    moment = now or datetime.now(UTC)
    ready = or_(
        RelationClaimProjectionOutbox.status == "PENDING",
        and_(
            RelationClaimProjectionOutbox.status == "FAILED",
            RelationClaimProjectionOutbox.available_at <= moment,
        ),
        and_(
            RelationClaimProjectionOutbox.status == "DISPATCHING",
            RelationClaimProjectionOutbox.lease_expires_at <= moment,
        ),
    )
    result = await session.execute(
        select(RelationClaimProjectionOutbox)
        .where(ready)
        .order_by(
            RelationClaimProjectionOutbox.available_at,
            RelationClaimProjectionOutbox.created_at,
            RelationClaimProjectionOutbox.outbox_id,
        )
        .limit(max(1, min(limit, 500)))
        .with_for_update(skip_locked=True)
    )
    rows = list(result.scalars().all())
    for row in rows:
        row.status = "DISPATCHING"
        row.attempts += 1
        row.lease_expires_at = moment + LEASE
        row.last_error = ""
    await session.commit()
    return [
        {
            "outbox_id": row.outbox_id,
            "tenant_id": row.tenant_id,
            "relation_id": row.relation_id,
            "attempts": row.attempts,
        }
        for row in rows
    ]


async def _finish(
    factory: async_sessionmaker,
    outbox_id: str,
    *,
    status: str,
    reason: str = "",
    backoff_seconds: int = 5,
) -> None:
    async with factory() as session:
        result = await session.execute(
            select(RelationClaimProjectionOutbox).where(
                RelationClaimProjectionOutbox.outbox_id == outbox_id
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return
        row.status = status
        row.lease_expires_at = None
        row.last_error = str(reason)[:4000]
        if status == "FAILED":
            row.available_at = datetime.now(UTC) + timedelta(seconds=backoff_seconds)
        await session.commit()


async def relay_relation_projection_outbox(
    *,
    limit: int = 50,
    graph_store: Any | None = None,
    session_factory: async_sessionmaker | None = None,
) -> dict[str, int]:
    """Project ready VALID claims with replay-safe, durable per-claim checkpoints.

    The SQL outbox is committed before touching Neo4j. On a crash after a graph
    write but before marking DISPATCHED, the lease expires and the same claim is
    replayed; all graph operations are keyed by the claim's deterministic IDs.
    """
    owns_factory = session_factory is None
    factory = session_factory or make_session_factory()
    owns_graph = graph_store is None
    graph = graph_store or Neo4jGraphStore.from_settings()
    counts = {"claimed": 0, "projected": 0, "skipped": 0, "failed": 0}
    try:
        await create_tables()
        async with factory() as session:
            batch = await _claim_batch(session, limit=limit)
        counts["claimed"] = len(batch)

        for item in batch:
            try:
                async with factory() as session:
                    claim_store = SqlRelationClaimStore(session)
                    claim = await claim_store.get(
                        item["relation_id"], tenant_id=item["tenant_id"]
                    )
                    record_result = await session.execute(
                        select(RelationClaimRow.validation_record).where(
                            RelationClaimRow.tenant_id == item["tenant_id"],
                            RelationClaimRow.relation_id == item["relation_id"],
                        )
                    )
                    validation_record = record_result.scalar_one_or_none()
                    await session.commit()

                if claim is None:
                    raise ValueError("outbox points to a missing or cross-tenant relation claim")
                if not _valid_record(validation_record) or str(claim.status).lower() != "active":
                    await _finish(
                        factory,
                        item["outbox_id"],
                        status="SKIPPED",
                        reason="claim is no longer VALID and active at projection time",
                    )
                    counts["skipped"] += 1
                    continue

                project_admitted_claim(
                    graph,
                    claim,
                    validation_record=validation_record,
                )
                await _finish(factory, item["outbox_id"], status="DISPATCHED")
                counts["projected"] += 1
            except Exception as exc:
                backoff = min(300, 2 ** min(int(item["attempts"]), 8))
                await _finish(
                    factory,
                    item["outbox_id"],
                    status="FAILED",
                    reason=f"{type(exc).__name__}: {exc}",
                    backoff_seconds=backoff,
                )
                counts["failed"] += 1
        return counts
    finally:
        if owns_graph and hasattr(graph, "close"):
            graph.close()
        if owns_factory:
            bind = getattr(factory, "kw", {}).get("bind")
            if bind is not None:
                await bind.dispose()


async def run_relation_projection_relay_forever(*, interval_seconds: float = 5.0) -> None:
    """Run the durable relay as a standalone production worker."""
    factory = make_session_factory()
    graph = Neo4jGraphStore.from_settings()
    try:
        await create_tables()
        while True:
            await relay_relation_projection_outbox(
                graph_store=graph,
                session_factory=factory,
            )
            await asyncio.sleep(max(0.25, interval_seconds))
    finally:
        graph.close()
        bind = getattr(factory, "kw", {}).get("bind")
        if bind is not None:
            await bind.dispose()


def main() -> None:
    asyncio.run(run_relation_projection_relay_forever())


__all__ = ["relay_relation_projection_outbox", "run_relation_projection_relay_forever", "main"]
