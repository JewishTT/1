"""Focused tests for SQL entity-stream durability and tenant isolation."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "shared"))

from domain.dynamics import StreamAppendRejected, StreamRecord

from db.entity_stream import SqlEntityStreamRepository
from db.schema import EntityStreamRow


class _Result:
    def __init__(self, rows: list[EntityStreamRow]) -> None:
        self._rows = rows

    def scalar_one_or_none(self) -> EntityStreamRow | None:
        return self._rows[0] if self._rows else None

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[EntityStreamRow]:
        return self._rows


class _Session:
    """Small SQLAlchemy-shaped store for repository contract tests."""

    def __init__(self) -> None:
        self.rows: list[EntityStreamRow] = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, row: EntityStreamRow) -> None:
        self.rows.append(row)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def execute(self, statement) -> _Result:
        params = statement.compile().params
        found = list(self.rows)
        if "record_hash_1" in params:
            found = [row for row in found if row.record_hash == params["record_hash_1"]]
        if "tenant_id_1" in params:
            found = [row for row in found if row.tenant_id == params["tenant_id_1"]]
        if "entity_id_1" in params:
            found = [row for row in found if row.entity_id == params["entity_id_1"]]
        if "sequence_1" in params:
            sequence = params["sequence_1"]
            if "entity_stream.sequence >" in str(statement):
                found = [row for row in found if row.sequence > sequence]
            else:
                found = [row for row in found if row.sequence == sequence]
        if "entity_stream.record_hash =" not in str(statement):
            found.sort(key=lambda row: row.sequence)
        if statement._limit_clause is not None:
            found = found[: statement._limit_clause.value]
        return _Result(found)


def _record(
    entity_id: str = "ENT-1",
    sequence: int = 1,
    tenant_id: str = "tenant-a",
    payload: dict | None = None,
) -> StreamRecord:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return StreamRecord(
        entity_id=entity_id,
        tenant_id=tenant_id,
        kind="property.set",
        ts=now,
        sequence=sequence,
        payload=payload or {"property": "name", "value": "Alice"},
        valid_from=now,
        valid_until=now + timedelta(days=1),
        observation_id="OBS-1",
        dataset_id="dataset-1",
        extraction_version="entity-v1",
    )


@pytest.mark.asyncio
async def test_append_and_replay_round_trip_preserves_stream_contract() -> None:
    session = _Session()
    repository = SqlEntityStreamRepository(session)  # type: ignore[arg-type]
    record = _record()

    stored = await repository.append(record)

    assert stored.to_dict() == record.to_dict()
    assert session.commits == 1
    assert (await repository.replay(tenant_id="tenant-a", entity_id="ENT-1")) == [record]


@pytest.mark.asyncio
async def test_append_many_is_idempotent_and_preserves_input_order() -> None:
    session = _Session()
    repository = SqlEntityStreamRepository(session)  # type: ignore[arg-type]
    first, second = _record(sequence=1), _record(sequence=2, payload={"value": "Bob"})
    await repository.append(first)

    result = await repository.append_many([first, first, second])

    assert result == [first, first, second]
    assert len(session.rows) == 2
    assert session.commits == 2


@pytest.mark.asyncio
async def test_append_rejects_sequence_collision_without_writing() -> None:
    session = _Session()
    repository = SqlEntityStreamRepository(session)  # type: ignore[arg-type]
    await repository.append(_record(sequence=1))
    conflict = _record(sequence=1, payload={"value": "different"})

    with pytest.raises(StreamAppendRejected, match="sequence 1"):
        await repository.append(conflict)

    assert len(session.rows) == 1
    assert session.commits == 1


@pytest.mark.asyncio
async def test_replay_is_ordered_and_tenant_scoped() -> None:
    session = _Session()
    repository = SqlEntityStreamRepository(session)  # type: ignore[arg-type]
    await repository.append_many(
        [
            _record(sequence=1),
            _record(sequence=2, payload={"value": "Bob"}),
            _record(entity_id="ENT-2", sequence=1),
            _record(tenant_id="tenant-b", sequence=1),
        ]
    )

    scoped = await repository.list_records(tenant_id="tenant-a", entity_id="ENT-1")
    after_one = await repository.list_records(
        tenant_id="tenant-a", entity_id="ENT-1", after_sequence=1
    )
    other_tenant = await repository.list_records(tenant_id="tenant-b", entity_id="ENT-1")

    assert [record.sequence for record in scoped] == [1, 2]
    assert [record.sequence for record in after_one] == [2]
    assert [record.tenant_id for record in other_tenant] == ["tenant-b"]


@pytest.mark.asyncio
async def test_record_hash_lookup_requires_matching_tenant() -> None:
    session = _Session()
    repository = SqlEntityStreamRepository(session)  # type: ignore[arg-type]
    record = await repository.append(_record())

    assert await repository.get_by_record_hash(
        record.record_hash, tenant_id="tenant-a"
    ) == record
    assert await repository.get_by_record_hash(record.record_hash, tenant_id="tenant-b") is None
    with pytest.raises(ValueError, match="tenant_id"):
        await repository.get_by_record_hash(record.record_hash, tenant_id="")


@pytest.mark.asyncio
async def test_batch_rejects_conflicting_sequence_before_database_write() -> None:
    session = _Session()
    repository = SqlEntityStreamRepository(session)  # type: ignore[arg-type]

    with pytest.raises(StreamAppendRejected, match="sequence 1"):
        await repository.append_many(
            [_record(sequence=1), _record(sequence=1, payload={"value": "different"})]
        )

    assert session.rows == []
    assert session.commits == 0

