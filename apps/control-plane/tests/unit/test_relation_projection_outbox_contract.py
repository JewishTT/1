"""Schema and transaction contract for durable relation projection admission."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql.dml import Insert

from db.relation_claim_store import CLAIM_JSONB_COLUMNS, SqlRelationClaimStore, _validation_column
from db.schema import RelationClaim as RelationClaimRow
from db.schema import RelationClaimProjectionOutbox


class _Result:
    def __init__(self, row=None):
        self.row = row

    def scalar_one_or_none(self):
        return self.row


class _Session:
    def __init__(self):
        self.row = SimpleNamespace(validation_record=None)
        self.statements = []
        self.committed = False

    async def execute(self, statement):
        self.statements.append(statement)
        if len(self.statements) == 1:
            return _Result(self.row)
        return _Result(None)

    async def commit(self):
        self.committed = True


def test_validation_record_is_a_separate_durable_jsonb_column() -> None:
    assert isinstance(RelationClaimRow.__table__.c.validation_record.type, JSONB)
    assert "validation_record" not in CLAIM_JSONB_COLUMNS
    assert _validation_column() == (RelationClaimRow, "validation_record")


def test_projection_outbox_has_tenant_claim_uniqueness_and_retry_lease() -> None:
    table = RelationClaimProjectionOutbox.__table__
    uniques = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("tenant_id", "relation_id") in uniques
    assert "lease_expires_at" in table.c
    assert "attempts" in table.c
    assert "status" in table.c


@pytest.mark.asyncio
async def test_valid_verdict_and_outbox_enqueue_commit_together() -> None:
    session = _Session()
    store = SqlRelationClaimStore(session)
    await store.record_validation(
        "REL-1",
        tenant_id="tenant-1",
        result={"verdict": "VALID", "layers": {}, "reasons": [], "grade_components": {}},
    )
    assert session.row.validation_record["verdict"] == "VALID"
    assert len(session.statements) == 2
    insertion = session.statements[1]
    assert isinstance(insertion, Insert)
    assert insertion.table.name == "relation_claim_projection_outbox"
    sql = str(insertion.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT ON CONSTRAINT uq_relation_claim_projection_outbox_claim" in sql
    assert session.committed is True


@pytest.mark.asyncio
async def test_non_valid_verdict_is_durable_without_admission_enqueue() -> None:
    session = _Session()
    store = SqlRelationClaimStore(session)
    await store.record_validation(
        "REL-2",
        tenant_id="tenant-1",
        result={"verdict": "REJECTED", "layers": {}, "reasons": [{"code": "R1"}]},
    )
    assert session.row.validation_record["verdict"] == "REJECTED"
    assert len(session.statements) == 1
    assert session.committed is True
