"""Frontier operational state (T026, FR-003, R-4).

Postgres is authoritative (hierarchical GLOBAL→TENANT→INVESTIGATION→SOURCE→
HOST→TASK); Redis provides hot lease/cooldown/locking. Kafka is never the
frontier queue (I-5/R-4). Looks up items by priority, respects cooldown/lease,
tracks retry and dedup.

This module is the **only** writer of ``frontier_items``. Producers -- the recon
planner, the API, the feedback loop, the discovery bridge -- all go through
:class:`PgFrontier.enqueue`, so the one INSERT here decides which columns each
producer may influence: ``provenance`` is the caller's to state (FR-007) and the
scheduling columns are this module's to decide (ADR-0016/0017). A second INSERT
anywhere else would be a second authority (SC-012).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError


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
    # FR-007: the caller's account of *how* this item came to be known, when the
    # answer is "discovery" -- which source, under which method, for which query,
    # and which other sources had already seen the same URL. Empty for an item
    # seeded by a recon plan, an API caller or the feedback loop, none of which
    # name a discovery; `{}` is the false statement about provenance rather than
    # an unknown one, and the column is NOT NULL for exactly that reason.
    #
    # Declared last, with a default, so every existing construction site -- which
    # is the whole of the codebase's other producers -- keeps working unchanged
    # and the field is purely additive.
    provenance: dict[str, Any] = field(default_factory=dict)

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


_UNIQUE_VIOLATION = "23505"
_DEDUP_CONSTRAINT = "uq_frontier_schedule"


def _is_dedup_violation(exc: IntegrityError) -> bool:
    """True only for a unique violation on the frontier's own dedup index.

    A blanket ``except IntegrityError`` would report a NOT NULL violation, a bad
    foreign key or a length overflow to the caller as "this URL was already
    known" -- a lie that both hides the bug and quietly breaks the idempotency
    an enqueue promises. So the driver error has to name the constraint.

    When the driver does not surface a SQLSTATE at all this returns ``False``:
    re-raising is the recoverable choice, because the alternative is guessing at
    which integrity rule fired from a message that may not contain one.
    """
    orig = exc.orig
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate != _UNIQUE_VIOLATION:
        return False
    return _DEDUP_CONSTRAINT in str(orig)


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
        # `getattr` rather than `row.provenance`: a row projected by a narrower
        # SELECT need not carry the column, and a read path that raised for that
        # would make the audit column into a hard dependency of leasing. Copied,
        # not aliased, so a caller mutating the item's document cannot write
        # through to the row the session still has loaded.
        stored = getattr(row, "provenance", None)
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
            provenance=dict(stored) if stored else {},
        )

    async def enqueue(self, item: FrontierItem) -> bool:
        """Idempotent enqueue: unique (tenant_id, uri), prefers higher priority.

        Partition is carried on the row (T119) so per-region dispatchers can
        pull only their own shard.

        ``provenance`` (FR-007) is carried through whole -- nested lists and all.
        Filtering it to a known subset here is the boundary loss the column
        exists to prevent, and it is unrecoverable afterwards: nothing downstream
        can know what was discarded.

        The five scheduling columns are **named here and never read from
        ``item``**. A newly enqueued item is READY, un-leased, un-retried and
        unscheduled, and that is this method's decision, not the caller's
        (ADR-0016/0017). Spelling them out rather than trusting a default is what
        makes the guarantee structural instead of incidental: a producer that
        does put ``state`` or ``retries`` on its item cannot get its value into
        the row, so no producer can become a second scheduler whose rules nobody
        can find.
        """
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
            provenance=item.provenance or {},
            state="READY",
            retries=0,
            lease_until=None,
            next_schedule_at=None,
        )
        insert_stmt = insert_stmt.on_conflict_do_nothing(index_elements=["tenant_id", "uri"])
        async with self._factory() as session:
            try:
                result = await session.execute(insert_stmt)
            except IntegrityError as exc:
                # `ON CONFLICT (tenant_id, uri) DO NOTHING` absorbs the ordinary
                # duplicate, so reaching here means a *concurrent* transaction
                # committed the same (tenant_id, uri) between our snapshot and our
                # insert, and the driver reported the violation instead. That is
                # still a duplicate, and still success (FR-006). Anything else is a
                # bug and re-raises -- see `_is_dedup_violation`.
                if not _is_dedup_violation(exc):
                    raise
                await session.rollback()
                await self._upgrade_priority(session, item)
                await session.commit()
                return False
            if not result.rowcount:
                # Dedup: upgrade priority if the known item is still actionable.
                await self._upgrade_priority(session, item)
            await session.commit()
            return bool(result.rowcount)

    @staticmethod
    async def _upgrade_priority(session, item: FrontierItem) -> None:
        """Raise the priority of an already-known item, and only while actionable.

        A caller offering the same (tenant_id, uri) at a higher priority outranks
        the row already queued. A row that is LEASED, DONE, COOLDOWN or
        QUARANTINED is left exactly as it is: re-prioritising work that is
        mid-flight or finished is a scheduling decision, and the scheduler makes
        it.

        ``provenance`` is **not** rewritten here. First write wins: overwriting
        it would let a second producer erase the ``seen_by[]`` and ``sources[]``
        the first one accumulated, which is the loss FR-007 exists to prevent.
        Within one discovery pass those lists are already merged by ``coalesce``
        before the sink is called, so nothing is lost by leaving the row alone.
        """
        from sqlalchemy import update

        from db.schema import FrontierItem as Row

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