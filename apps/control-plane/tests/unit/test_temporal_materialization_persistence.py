"""Persistence metadata tests for temporal materialization."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from db.materialization_cursor import SqlMaterializationCursorRepository
from db.schema import (
    MaterializationCursor,
    TemporalHistoryPublication,
    TemporalMaterializationRun,
    TemporalWindowRevision,
)
from db.temporal_materialization import SqlTemporalMaterializationRepository


def test_temporal_tables_have_tenant_entity_indexes() -> None:
    for model in (TemporalMaterializationRun, TemporalWindowRevision, TemporalHistoryPublication):
        indexes = {
            tuple(column.name for column in index.columns) for index in model.__table__.indexes
        }
        assert any("tenant_id" in columns and "entity_id" in columns for columns in indexes)




def test_history_head_is_entity_scoped_generation_authority() -> None:
    from db.schema import TemporalHistoryHead

    assert set(TemporalHistoryHead.__table__.primary_key.columns.keys()) == {
        "tenant_id", "entity_id"
    }

def test_publication_generation_is_unique_per_entity() -> None:
    names = {
        tuple(column.name for column in index.columns)
        for index in TemporalHistoryPublication.__table__.indexes
    }
    assert ("tenant_id", "entity_id", "projection_generation") in names


def test_generation_scoped_storage_ids_do_not_collide() -> None:
    first = SqlTemporalMaterializationRepository.revision_storage_id("wr-abc", 1)
    second = SqlTemporalMaterializationRepository.revision_storage_id("wr-abc", 2)
    assert first != second
    assert SqlTemporalMaterializationRepository.audit_id(
        run_id="run-1", integrity_fingerprint="fp"
    ) != SqlTemporalMaterializationRepository.audit_id(
        run_id="run-2", integrity_fingerprint="fp"
    )


def test_cursor_table_is_tenant_entity_run_scoped_and_page_unique() -> None:
    indexes = {
        tuple(column.name for column in index.columns)
        for index in MaterializationCursor.__table__.indexes
    }
    assert ("tenant_id", "entity_id", "run_id") in indexes
    assert ("tenant_id", "entity_id", "run_id", "crawl", "page") in indexes


def test_cursor_identity_is_deterministic_and_tenant_scoped() -> None:
    first = SqlMaterializationCursorRepository.cursor_id(
        tenant_id="tenant-a", entity_id="entity-1", run_id="run-1", crawl="CC-MAIN-2025-30", page=0
    )
    retry = SqlMaterializationCursorRepository.cursor_id(
        tenant_id="tenant-a", entity_id="entity-1", run_id="run-1", crawl="CC-MAIN-2025-30", page=0
    )
    other_tenant = SqlMaterializationCursorRepository.cursor_id(
        tenant_id="tenant-b", entity_id="entity-1", run_id="run-1", crawl="CC-MAIN-2025-30", page=0
    )
    assert first == retry
    assert first != other_tenant


@pytest.mark.asyncio
async def test_cursor_prepare_then_complete_is_idempotent_payload_state() -> None:
    from db.schema import MaterializationCursor

    class Session:
        def __init__(self) -> None:
            self.flushes = 0
            self.commits = 0

        async def flush(self) -> None:
            self.flushes += 1

        async def commit(self) -> None:
            self.commits += 1

    session = Session()
    repository = SqlMaterializationCursorRepository(session)  # type: ignore[arg-type]
    row = MaterializationCursor(
        cursor_id="cursor-1", tenant_id="t1", entity_id="e1", run_id="r1",
        crawl="CC-MAIN-2025-30", page=0, status="PENDING", last_error="",
    )
    payload = {"record": {"record_hash": "abc"}}
    await repository.prepare(row, result_payload=payload)
    assert row.status == "PROCESSING"
    assert row.result_payload == payload
    await repository.complete(row, result_payload=payload)
    assert row.status == "COMPLETED"
    assert row.completed_at is not None
    assert session.flushes == 1
    assert session.commits == 1


class _ScalarResult:
    def __init__(self, value=None) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _PublishSession:
    def __init__(self, results: list) -> None:
        self.results = list(results)
        self.added: list[object] = []
        self.commits = 0
        self.flushes = 0

    async def flush(self) -> None:
        self.flushes += 1

    async def execute(self, statement):
        return _ScalarResult(self.results.pop(0) if self.results else None)

    def add(self, row) -> None:
        self.added.append(row)

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_publish_is_idempotent_for_same_fingerprint() -> None:
    from datetime import UTC, datetime

    from domain.dynamics import StreamRecord
    from domain.temporal_materialization import materialize_history

    from db.schema import TemporalHistoryPublication

    record = StreamRecord(
        entity_id="e1", tenant_id="t1", kind="fact",
        ts=datetime(2024, 1, 1, tzinfo=UTC), sequence=1,
        payload={"event_at": "2024-01-01T00:00:00+00:00"},
    )
    history = materialize_history([record], tenant_id="t1", entity_id="e1", projection_generation=1)
    existing = TemporalHistoryPublication(
        publication_id=history.publication.publication_id,
        tenant_id="t1", entity_id="e1", source_cut_id=history.publication.source_cut.cut_id,
        projection_generation=1, integrity_fingerprint=history.publication.integrity_fingerprint,
        payload=history.publication.to_dict(),
    )
    session = _PublishSession([None, existing])
    repository = SqlTemporalMaterializationRepository(session)  # type: ignore[arg-type]

    publication_id = await repository.publish(history, run_id="run-2")

    assert publication_id == history.publication.publication_id
    assert len(session.added) == 1
    assert type(session.added[0]).__name__ == "TemporalHistoryHead"
    assert session.commits == 0


@pytest.mark.asyncio
async def test_publish_new_generation_uses_head_and_namespaced_revisions() -> None:
    from datetime import UTC, datetime

    from domain.dynamics import StreamRecord
    from domain.temporal_materialization import materialize_history

    from db.schema import TemporalHistoryHead

    head = TemporalHistoryHead(
        tenant_id="t1", entity_id="e1", projection_generation=1,
        publication_id="pub-old",
    )
    record = StreamRecord(
        entity_id="e1", tenant_id="t1", kind="fact",
        ts=datetime(2024, 1, 1, tzinfo=UTC), sequence=1,
        payload={"event_at": "2024-01-01T00:00:00+00:00"},
    )
    history = materialize_history([record], tenant_id="t1", entity_id="e1", projection_generation=2)
    session = _PublishSession([head, None, None])
    repository = SqlTemporalMaterializationRepository(session)  # type: ignore[arg-type]

    await repository.publish(history, run_id="run-2")

    revision_rows = [row for row in session.added if type(row).__name__ == "TemporalWindowRevision"]
    assert revision_rows and revision_rows[0].revision_id.endswith("-g2")
    assert head.projection_generation == 2
    assert head.publication_id == history.publication.publication_id
    assert session.commits == 1
