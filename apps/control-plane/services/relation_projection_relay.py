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
from graph.claim_projection import reconcile_claim_projection
from graph.neo4j import Neo4jGraphStore


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
    claimed = []
    for row in rows:
        row.status = "DISPATCHING"
        row.attempts += 1
        row.lease_expires_at = moment + LEASE
        row.last_error = ""
        claimed.append(
            {
                "outbox_id": row.outbox_id,
                "tenant_id": row.tenant_id,
                "relation_id": row.relation_id,
                "attempts": row.attempts,
            }
        )
    # Copy primitives before commit; SQLAlchemy may expire ORM rows on commit.
    await session.commit()
    return claimed


async def _finish(
    factory: async_sessionmaker,
    outbox_id: str,
    *,
    status: str,
    expected_attempt: int,
    reason: str = "",
    backoff_seconds: int = 5,
) -> None:
    """Finish only the lease generation that is still current.

    Revalidation may put a DISPATCHING row back to PENDING while graph I/O is
    in flight. The old worker must not overwrite that new handoff.
    """
    async with factory() as session:
        result = await session.execute(
            select(RelationClaimProjectionOutbox).where(
                RelationClaimProjectionOutbox.outbox_id == outbox_id
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return
        if row.status != "DISPATCHING" or row.attempts != expected_attempt:
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
    graph = graph_store if graph_store is not None else Neo4jGraphStore.from_settings()
    counts = {"claimed": 0, "projected": 0, "skipped": 0, "failed": 0}
    try:
        async with factory() as session:
            batch = await _claim_batch(session, limit=limit)
        counts["claimed"] = len(batch)

        for item in batch:
            try:
                async with factory() as session:
                    trigger_result = await session.execute(
                        select(RelationClaimRow).where(
                            RelationClaimRow.tenant_id == item["tenant_id"],
                            RelationClaimRow.relation_id == item["relation_id"],
                        )
                    )
                    trigger_row = trigger_result.scalar_one_or_none()
                    if trigger_row is None:
                        raise ValueError(
                            "outbox points to a missing or cross-tenant relation claim"
                        )
                    latest_result = await session.execute(
                        select(RelationClaimRow.relation_id)
                        .where(
                            RelationClaimRow.tenant_id == item["tenant_id"],
                            RelationClaimRow.logical_relation_id
                            == trigger_row.logical_relation_id,
                        )
                        .order_by(
                            RelationClaimRow.revision_number.desc(),
                            RelationClaimRow.created_at.desc(),
                            RelationClaimRow.relation_id.desc(),
                        )
                        .limit(1)
                    )
                    latest_relation_id = latest_result.scalar_one_or_none()
                    await session.commit()

                # A stale outbox item cannot clobber or delete a newer revision.
                if latest_relation_id != item["relation_id"]:
                    await _finish(
                        factory,
                        item["outbox_id"],
                        status="DISPATCHED",
                        expected_attempt=int(item["attempts"]),
                    )
                    counts["skipped"] += 1
                    continue

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

                outcome = reconcile_claim_projection(
                    graph,
                    claim,
                    validation_record=validation_record,
                )
                await _finish(
                    factory,
                    item["outbox_id"],
                    status="DISPATCHED",
                    expected_attempt=int(item["attempts"]),
                )
                if outcome["projected"]:
                    counts["projected"] += 1
                elif outcome["cleared"]:
                    counts["skipped"] += 1
            except Exception as exc:  # noqa: BLE001 - backend failures must trigger durable retry
                backoff = min(300, 2 ** min(int(item["attempts"]), 8))
                await _finish(
                    factory,
                    item["outbox_id"],
                    status="FAILED",
                    expected_attempt=int(item["attempts"]),
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


__all__ = ["main", "relay_relation_projection_outbox", "run_relation_projection_relay_forever"]
