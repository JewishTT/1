"""Frontier operational state (T026, FR-003, R-4).

Postgres is authoritative (hierarchical GLOBAL→TENANT→INVESTIGATION→SOURCE→
HOST→TASK); Redis provides hot lease/cooldown/locking. Kafka is never the
frontier queue (I-5/R-4). Looks up items by priority, respects cooldown/lease,
tracks retry and dedup.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class FrontierItem:
    frontier_id: str
    uri: str
    tenant_id: str
    investigation_id: str | None = None
    source_id: str | None = None
    host_key: str | None = None
    partition: str = "global"
    priority: float = 0.0
    state: str = "READY"  # READY | LEASED | DONE | COOLDOWN | RETRY | QUARANTINED
    retries: int = 0
    lease_until: float = 0.0
    next_schedule_at: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def schedule_key(self) -> str:
        return f"{self.tenant_id}:{self.uri}"


class Frontier:
    """In-memory authoritative frontier + lease/cooldown semantics.

    Redis-backed variant is a drop-in replacement behind this interface; the
    authoritative hierarchy + lease/cooldown/retry semantics are preserved.
    """

    def __init__(self) -> None:
        self._items: dict[str, FrontierItem] = {}
        self._by_schedule: dict[str, str] = {}  # schedule_key -> frontier_id

    def enqueue(self, item: FrontierItem) -> bool:
        key = item.schedule_key()
        existing_id = self._by_schedule.get(key)
        if existing_id:
            # Dedup: prefer higher priority / retain existing (idempotent enqueue).
            existing = self._items[existing_id]
            if item.priority > existing.priority:
                existing.priority = item.priority
                existing.state = "READY"
            return False
        self._items[item.frontier_id] = item
        self._by_schedule[key] = item.frontier_id
        return True

    def pop_next(self, *, tenant_id: str | None = None, now: float | None = None) -> FrontierItem | None:
        now = now if now is not None else time.time()
        candidates = [i for i in self._items.values() if i.state in ("READY", "RETRY")]
        if tenant_id:
            candidates = [i for i in candidates if i.tenant_id == tenant_id]
        candidates = [i for i in candidates if i.next_schedule_at <= now]
        if not candidates:
            return None
        best = max(candidates, key=lambda i: i.priority)
        best.state = "LEASED"
        best.lease_until = now + 30.0
        return best

    def lease_expired(self, frontier_id: str, now: float | None = None) -> bool:
        item = self._items.get(frontier_id)
        if item is None:
            return True
        now = now if now is not None else time.time()
        return item.lease_until <= now

    def complete(self, frontier_id: str) -> None:
        item = self._items.get(frontier_id)
        if item:
            item.state = "DONE"
            item.next_schedule_at = time.time() + 3600.0  # reseed freshness

    def fail_retry(self, frontier_id: str, *, max_retries: int = 3, cooldown_s: float = 60.0) -> None:
        item = self._items.get(frontier_id)
        if item is None:
            return
        if item.retries >= max_retries:
            item.state = "QUARANTINED"
            return
        item.retries += 1
        item.state = "RETRY"
        item.next_schedule_at = time.time() + cooldown_s

    def cooldown(self, frontier_id: str, until: float) -> None:
        item = self._items.get(frontier_id)
        if item:
            item.state = "COOLDOWN"
            item.next_schedule_at = until

    def cancel(self, frontier_id: str) -> None:
        item = self._items.pop(frontier_id, None)
        if item:
            self._by_schedule.pop(item.schedule_key(), None)

    def count(self, tenant_id: str | None = None) -> int:
        if tenant_id is None:
            return len(self._items)
        return sum(1 for i in self._items.values() if i.tenant_id == tenant_id)

    def ready_count(self, tenant_id: str | None = None) -> int:
        return sum(
            1
            for i in self._items.values()
            if i.state in ("READY", "RETRY") and (tenant_id is None or i.tenant_id == tenant_id)
        )


class PgFrontier:
    """Postgres-authoritative frontier (FR-005, R-4).

    Scheduling state lives in ``frontier_items``; leases/cooldowns/retries are
    enforced with atomic UPDATEs so competing schedulers never double-lease.
    Event stream is never the frontier queue. Mirror of the in-memory :class:
    `Frontier` interface, async over a SQLAlchemy async session.
    """

    LEASE_S = 30.0
    RESEED_S = 3600.0
    RETRY_COOLDOWN_S = 60.0
    MAX_RETRIES = 3

    def __init__(self, session_factory) -> None:
        self._factory = session_factory

    @staticmethod
    def _utc(dt) -> float:
        return dt.timestamp() if dt is not None else 0.0

    @staticmethod
    def _from_row(row) -> FrontierItem:
        return FrontierItem(
            frontier_id=row.frontier_id,
            uri=row.uri,
            tenant_id=row.tenant_id,
            investigation_id=row.investigation_id,
            source_id=row.source_id,
            host_key=row.host_key,
            partition=getattr(row, "partition", None) or "global",
            priority=row.priority,
            state=row.state,
            retries=row.retries,
            lease_until=row.lease_until.timestamp() if row.lease_until else 0.0,
            next_schedule_at=row.next_schedule_at.timestamp() if row.next_schedule_at else 0.0,
        )

    async def enqueue(self, item: FrontierItem) -> bool:
        """Idempotent enqueue: unique (tenant_id, uri), prefers higher priority.

        Partition is carried on the row (T119) so per-region dispatchers can
        pull only their own shard.
        """
        from sqlalchemy import update
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        from db.schema import FrontierItem as Row

        insert_stmt = pg_insert(Row).values(
            frontier_id=item.frontier_id,
            tenant_id=item.tenant_id,
            investigation_id=item.investigation_id,
            source_id=item.source_id,
            uri=item.uri,
            host_key=item.host_key,
            partition=item.partition or "global",
            priority=item.priority,
            state="READY",
            retries=0,
            lease_until=None,
            next_schedule_at=None,
        )
        insert_stmt = insert_stmt.on_conflict_do_nothing(index_elements=["tenant_id", "uri"])
        async with self._factory() as session:
            result = await session.execute(insert_stmt)
            if not result.rowcount:
                # Dedup: upgrade priority if the known item is still actionable.
                await session.execute(
                    update(Row)
                    .where(
                        Row.tenant_id == item.tenant_id,
                        Row.uri == item.uri,
                        Row.priority < item.priority,
                        Row.state.in_(("READY", "RETRY")),
                    )
                    .values(priority=item.priority, state="READY")
                )
            await session.commit()
            return bool(result.rowcount)

    async def pop_next(
        self,
        *,
        tenant_id: str | None = None,
        partition: str | None = None,
        now: float | None = None,
    ) -> FrontierItem | None:
        """Lease one READY/RETRY item (highest priority, tenant/region filtered)."""
        from sqlalchemy import text

        now = now if now is not None else time.time()
        filters = ["state IN ('READY', 'RETRY')", "(next_schedule_at IS NULL OR next_schedule_at <= :now)"]
        params: dict = {"now": datetime.fromtimestamp(now, UTC)}
        if tenant_id:
            filters.append("tenant_id = :tenant_id")
            params["tenant_id"] = tenant_id
        if partition:
            filters.append("partition = :partition")
            params["partition"] = partition
        lock = text(
            "WITH next AS ("
            "  SELECT frontier_id FROM frontier_items"
            f"  WHERE {' AND '.join(filters)}"
            "  ORDER BY priority DESC, created_at ASC"
            "  LIMIT 1 FOR UPDATE SKIP LOCKED"
            ") UPDATE frontier_items SET state='LEASED', lease_until=:lease"
            " FROM next WHERE frontier_items.frontier_id = next.frontier_id"
            " RETURNING *"
        )
        lease = datetime.fromtimestamp(now + self.LEASE_S, UTC)
        async with self._factory() as session:
            result = await session.execute(lock, {**params, "lease": lease})
            await session.commit()
            row = result.first()
        return self._from_row(row) if row else None

    async def lease_expired(self, frontier_id: str, now: float | None = None) -> bool:
        from sqlalchemy import select

        from db.schema import FrontierItem as Row

        now = now if now is not None else time.time()
        async with self._factory() as session:
            row = (
                await session.execute(
                    select(Row.lease_until).where(Row.frontier_id == frontier_id)
                )
            ).scalar_one_or_none()
        return row is None or row.timestamp() <= now

    async def complete(
        self,
        frontier_id: str,
        *,
        digest: str | None = None,
        etag: str | None = None,
        status: str = "completed",
    ) -> None:
        """Mark DONE + reseed freshness + record last_digest/etag (re-observation)."""
        from sqlalchemy import update

        from db.schema import FrontierItem as Row

        values: dict = {
            "state": "DONE",
            "next_schedule_at": datetime.fromtimestamp(time.time() + self.RESEED_S, UTC),
            "lease_until": None,
        }
        if digest is not None:
            values["last_digest"] = digest
        if etag is not None:
            values["last_etag"] = etag
        async with self._factory() as session:
            await session.execute(update(Row).where(Row.frontier_id == frontier_id).values(**values))
            await session.commit()

    async def fail_retry(
        self, frontier_id: str, *, max_retries: int | None = None, cooldown_s: float | None = None
    ) -> None:
        from sqlalchemy import update

        from db.schema import FrontierItem as Row

        max_retries = max_retries or self.MAX_RETRIES
        cooldown_s = cooldown_s if cooldown_s is not None else self.RETRY_COOLDOWN_S
        async with self._factory() as session:
            row = (
                await session.execute(
                    Row.__table__.select().where(Row.frontier_id == frontier_id)
                )
            ).first()
            await session.commit()
            if row is None:
                return
            retries = (row.retries or 0) + 1
            next_state = "QUARANTINED" if retries >= max_retries else "RETRY"
            async with self._factory() as session:
                await session.execute(
                    update(Row)
                    .where(Row.frontier_id == frontier_id)
                    .values(
                        state=next_state,
                        retries=retries,
                        next_schedule_at=datetime.fromtimestamp(time.time() + cooldown_s, UTC),
                        lease_until=None,
                    )
                )
                await session.commit()

    async def cooldown(self, frontier_id: str, until: float) -> None:
        from sqlalchemy import update

        from db.schema import FrontierItem as Row

        async with self._factory() as session:
            await session.execute(
                update(Row)
                .where(Row.frontier_id == frontier_id)
                .values(state="COOLDOWN", next_schedule_at=datetime.fromtimestamp(until, UTC))
            )
            await session.commit()

    async def cancel(self, frontier_id: str) -> None:
        from db.schema import FrontierItem as Row

        async with self._factory() as session:
            await session.execute(Row.__table__.delete().where(Row.frontier_id == frontier_id))
            await session.commit()

    async def last_digest(self, frontier_id: str, _uri: str | None = None) -> str | None:
        """Last known content digest for re-observation three-way split (R-08)."""
        from db.schema import FrontierItem as Row

        async with self._factory() as session:
            return (
                await session.execute(
                    Row.__table__.select().with_only_columns(Row.last_digest).where(Row.frontier_id == frontier_id)
                )
            ).scalar_one_or_none()

    async def last_etag(self, frontier_id: str) -> str | None:
        """Last known ETag for re-observation without a refetch (T101)."""
        from db.schema import FrontierItem as Row

        async with self._factory() as session:
            return (
                await session.execute(
                    Row.__table__.select().with_only_columns(Row.last_etag).where(Row.frontier_id == frontier_id)
                )
            ).scalar_one_or_none()

    async def checkpoint(self, frontier_id: str) -> dict[str, object]:
        """Full re-observation checkpoint (digest + etag) for the planner."""
        from db.schema import FrontierItem as Row

        async with self._factory() as session:
            row = (
                await session.execute(
                    Row.__table__.select()
                    .with_only_columns(Row.last_digest, Row.last_etag)
                    .where(Row.frontier_id == frontier_id)
                )
            ).first()
        if row is None:
            return {"digest": None, "etag": None}
        return {"digest": row.last_digest, "etag": row.last_etag}

    async def reschedule(self, frontier_id: str, *, when: float | None = None) -> None:
        """Return a done/cooldown item to READY (freshness reseed) — the normal
        re-observation path reuses ONE row per tenant+uri (FR-005)."""
        from sqlalchemy import update

        from db.schema import FrontierItem as Row

        async with self._factory() as session:
            await session.execute(
                update(Row)
                .where(Row.frontier_id == frontier_id)
                .values(
                    state="READY",
                    next_schedule_at=datetime.fromtimestamp(when if when is not None else time.time(), UTC),
                    lease_until=None,
                )
            )
            await session.commit()

    async def count(self, tenant_id: str | None = None) -> int:
        from sqlalchemy import func, select

        from db.schema import FrontierItem as Row

        async with self._factory() as session:
            stmt = select(func.count()).select_from(Row)
            if tenant_id:
                stmt = stmt.where(Row.tenant_id == tenant_id)
            return (await session.execute(stmt)).scalar_one()

    async def ready_count(self, tenant_id: str | None = None) -> int:
        from sqlalchemy import func, select

        from db.schema import FrontierItem as Row

        stmt = (
            select(func.count())
            .select_from(Row)
            .where(Row.state.in_(("READY", "RETRY")))
        )
        if tenant_id:
            stmt = stmt.where(Row.tenant_id == tenant_id)
        async with self._factory() as session:
            return (await session.execute(stmt)).scalar_one()