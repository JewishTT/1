"""Durable SQL persistence for the append-only entity stream.

The shared :class:`~domain.dynamics.StreamRecord` contract is deliberately
stdlib-only, while this adapter owns the SQLAlchemy boundary. Records are
content-addressed and immutable; callers can safely retry an append after an
unknown transaction outcome.
"""

from __future__ import annotations

from collections.abc import Iterable

from domain.dynamics import StreamAppendRejected, StreamRecord
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.schema import EntityStreamRow


class SqlEntityStreamRepository:
    """Persist and replay one tenant-scoped entity stream.

    ``session`` is supplied by the caller so the repository can participate in
    the control-plane request/worker transaction boundary. No method updates or
    deletes an existing row. Exact retries resolve to the stored record and do
    not create another sequence position.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def append(self, record: StreamRecord) -> StreamRecord:
        """Append one record, returning the canonical stored representation."""
        return (await self.append_many((record,)))[0]

    async def append_many(self, records: Iterable[StreamRecord]) -> list[StreamRecord]:
        """Append a batch in one transaction, preserving input order.

        Existing hashes are treated as exact retries only when the persisted
        content matches. A sequence collision with different content is
        rejected before the transaction is committed, and database uniqueness
        errors are re-checked after rollback to handle concurrent retries.
        """
        candidates = list(records)
        if not candidates:
            return []
        if any(not isinstance(record, StreamRecord) for record in candidates):
            raise TypeError("entity stream records must be StreamRecord instances")

        unique: dict[str, StreamRecord] = {}
        sequence_records: dict[tuple[str, str, int], StreamRecord] = {}
        for record in candidates:
            previous = unique.get(record.record_hash)
            if previous is not None:
                if not _same_content(previous, record):
                    raise StreamAppendRejected(
                        f"record hash collision for {record.record_hash}"
                    )
                continue
            key = (record.tenant_id, record.entity_id, record.sequence)
            sequence_previous = sequence_records.get(key)
            if (
                sequence_previous is not None
                and sequence_previous.record_hash != record.record_hash
            ):
                raise StreamAppendRejected(
                    f"sequence {record.sequence} already has a different record for "
                    f"{record.tenant_id}/{record.entity_id}"
                )
            sequence_records[key] = record
            unique[record.record_hash] = record

        resolved: dict[str, StreamRecord] = {}
        pending: list[StreamRecord] = []
        for record in unique.values():
            existing = await self._by_hash(
                record.record_hash, tenant_id=record.tenant_id
            )
            if existing is not None:
                if not _same_content(existing, record):
                    raise StreamAppendRejected(
                        f"record hash collision for {record.record_hash}"
                    )
                resolved[record.record_hash] = existing
                continue
            existing = await self._by_sequence(
                record.tenant_id, record.entity_id, record.sequence
            )
            if existing is not None:
                raise StreamAppendRejected(
                    f"sequence {record.sequence} already has a different record for "
                    f"{record.tenant_id}/{record.entity_id}"
                )
            pending.append(record)

        for record in pending:
            self.session.add(_to_row(record))
        if pending:
            try:
                await self.session.commit()
            except IntegrityError:
                await self.session.rollback()
                # A concurrent writer may have won the unique race. Return
                # exact retries when the row is now present; propagate all
                # other integrity errors to the caller.
                for record in pending:
                    existing = await self._by_hash(
                        record.record_hash, tenant_id=record.tenant_id
                    )
                    if existing is not None and _same_content(existing, record):
                        resolved[record.record_hash] = existing
                        continue
                    raise
            for record in pending:
                resolved[record.record_hash] = record

        return [resolved[record.record_hash] for record in candidates]

    async def list_records(
        self,
        *,
        tenant_id: str,
        entity_id: str,
        after_sequence: int = 0,
        limit: int | None = None,
    ) -> list[StreamRecord]:
        """Return records in accepted stream order within one tenant/entity."""
        if not tenant_id or not entity_id:
            raise ValueError("tenant_id and entity_id are required")
        if after_sequence < 0:
            raise ValueError("after_sequence must be non-negative")
        if limit is not None and limit <= 0:
            raise ValueError("limit must be positive")

        query = (
            select(EntityStreamRow)
            .where(
                EntityStreamRow.tenant_id == tenant_id,
                EntityStreamRow.entity_id == entity_id,
                EntityStreamRow.sequence > after_sequence,
            )
            .order_by(EntityStreamRow.sequence)
        )
        if limit is not None:
            query = query.limit(limit)
        result = await self.session.execute(query)
        return [_from_row(row) for row in result.scalars().all()]

    async def replay(
        self, *, tenant_id: str, entity_id: str, limit: int | None = None
    ) -> list[StreamRecord]:
        """Materialization-facing alias for an ordered stream replay."""
        return await self.list_records(tenant_id=tenant_id, entity_id=entity_id, limit=limit)

    async def get_by_record_hash(
        self, record_hash: str, *, tenant_id: str
    ) -> StreamRecord | None:
        """Resolve a content hash within an explicit tenant scope."""
        if not record_hash or not tenant_id:
            raise ValueError("record_hash and tenant_id are required")
        result = await self.session.execute(
            select(EntityStreamRow).where(
                EntityStreamRow.record_hash == record_hash,
                EntityStreamRow.tenant_id == tenant_id,
            )
        )
        row = result.scalar_one_or_none()
        return _from_row(row) if row is not None else None

    async def _by_hash(
        self, record_hash: str, *, tenant_id: str | None = None
    ) -> StreamRecord | None:
        query = select(EntityStreamRow).where(EntityStreamRow.record_hash == record_hash)
        if tenant_id is not None:
            query = query.where(EntityStreamRow.tenant_id == tenant_id)
        result = await self.session.execute(query)
        row = result.scalar_one_or_none()
        return _from_row(row) if row is not None else None

    async def _by_sequence(
        self, tenant_id: str, entity_id: str, sequence: int
    ) -> StreamRecord | None:
        result = await self.session.execute(
            select(EntityStreamRow).where(
                EntityStreamRow.tenant_id == tenant_id,
                EntityStreamRow.entity_id == entity_id,
                EntityStreamRow.sequence == sequence,
            )
        )
        row = result.scalar_one_or_none()
        return _from_row(row) if row is not None else None


def _to_row(record: StreamRecord) -> EntityStreamRow:
    return EntityStreamRow(
        tenant_id=record.tenant_id,
        entity_id=record.entity_id,
        sequence=record.sequence,
        record_hash=record.record_hash,
        kind=record.kind,
        ts=record.ts,
        payload=record.to_dict()["payload"],
        valid_from=record.valid_from,
        valid_until=record.valid_until,
        observation_id=record.observation_id,
        dataset_id=record.dataset_id,
        extraction_version=record.extraction_version,
    )


def _from_row(row: EntityStreamRow) -> StreamRecord:
    return StreamRecord(
        entity_id=row.entity_id,
        kind=row.kind,
        ts=row.ts,
        tenant_id=row.tenant_id,
        payload=dict(row.payload or {}),
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        observation_id=row.observation_id or "",
        dataset_id=row.dataset_id or "",
        extraction_version=row.extraction_version or "",
        sequence=row.sequence,
        record_hash=row.record_hash,
    )


def _same_content(left: StreamRecord, right: StreamRecord) -> bool:
    """Compare persisted semantic fields, excluding generated record_id."""
    return (
        left.entity_id == right.entity_id
        and left.tenant_id == right.tenant_id
        and left.sequence == right.sequence
        and left.kind == right.kind
        and left.ts == right.ts
        and left.payload == right.payload
        and left.valid_from == right.valid_from
        and left.valid_until == right.valid_until
        and left.observation_id == right.observation_id
        and left.dataset_id == right.dataset_id
        and left.extraction_version == right.extraction_version
        and left.record_hash == right.record_hash
    )


__all__ = ["SqlEntityStreamRepository"]

