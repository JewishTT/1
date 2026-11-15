from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from services.intelligence_reader import (
    IntelligenceReadDenied,
    IntelligenceSnapshotBudgetExceeded,
    PostgresIntelligenceReadPort,
)
from shared.contracts.intelligence_feed import IntelligenceQuery


NOW = datetime(2026, 11, 16, 0, 0, tzinfo=timezone.utc)


class _Rows:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class _Connection:
    def __init__(self):
        self.calls: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, statement, params):
        sql = str(statement)
        self.calls.append(sql)
        if "FROM entities" in sql and "entity_id = :entity_id" in sql:
            return _Rows([{
                "entity_id": "company-a",
                "entity_type": "company",
                "canonical_name": "Company A",
                "created_at": NOW,
            }])
        if "FROM relation_claim" in sql:
            return _Rows([{
                "relation_id": "relation-1",
                "relation_type": "paid",
                "subject_ref": "company-a",
                "object_ref": "company-b",
                "observation_refs": ["obs-rel"],
                "context_ref": "context-1",
                "status": "admitted",
                "confidence": 0.91,
                "evidence_grade": "A",
                "valid_from": NOW,
                "valid_to": None,
                "created_at": NOW,
            }])
        if "FROM entities" in sql and "entity_id IN :entity_ids" in sql:
            return _Rows([{
                "entity_id": "company-b",
                "entity_type": "company",
                "canonical_name": "Company B",
                "created_at": NOW,
            }])
        if "FROM entity_stream" in sql and "UNION" in sql:
            return _Rows([
                {"entity_id": "company-a", "observation_id": "obs-a"},
                {"entity_id": "company-b", "observation_id": "obs-b"},
            ])
        if "SELECT context_id, observation_id" in sql:
            return _Rows([{"context_id": "context-1", "observation_id": "obs-rel"}])
        if "FROM observations AS o" in sql:
            return _Rows([
                {
                    "observation_id": observation_id,
                    "source_id": "source-1",
                    "uri": "https://registry.example/filing",
                    "raw_ref": f"s3://knowledge/raw/tenant-a/{observation_id}",
                    "content_hash": digest,
                    "created_at": NOW,
                    "source_uri": "https://registry.example",
                }
                for observation_id, digest in (
                    ("obs-a", "a" * 64),
                    ("obs-b", "b" * 64),
                    ("obs-rel", "c" * 64),
                )
            ])
        raise AssertionError(f"unexpected SQL in read-port test: {sql}")


class _Factory:
    def __init__(self):
        self.connection = _Connection()

    def __call__(self):
        return self.connection


@pytest.mark.asyncio
async def test_postgres_read_port_builds_evidenced_graph_from_existing_tables():
    factory = _Factory()
    reader = PostgresIntelligenceReadPort(
        factory,
        tenant_id="tenant-a",
        allowed_purposes=frozenset({"economic_analysis"}),
    )

    snapshot = await reader.get_snapshot(IntelligenceQuery(
        tenant_id="tenant-a",
        subject_ref="company-a",
        purpose="economic_analysis",
        max_hops=1,
    ))

    assert snapshot.subject_entity_id == "company-a"
    assert {entity.entity_id for entity in snapshot.entities} == {"company-a", "company-b"}
    assert all(entity.evidence for entity in snapshot.entities)
    assert len(snapshot.relations) == 1
    relation = snapshot.relations[0]
    assert (relation.source_entity_id, relation.predicate, relation.target_entity_id) == (
        "company-a",
        "paid",
        "company-b",
    )
    assert relation.status == "admitted"
    assert relation.evidence_grade == "A"
    assert {ref.observation_id for ref in relation.evidence} == {"obs-rel"}
    assert all(ref.object_uri.startswith("s3://") for entity in snapshot.entities for ref in entity.evidence)
    assert any("FROM observations AS o" in sql for sql in factory.connection.calls)


@pytest.mark.asyncio
async def test_postgres_read_port_refuses_cross_tenant_and_unapproved_purpose_before_io():
    factory = _Factory()
    reader = PostgresIntelligenceReadPort(
        factory,
        tenant_id="tenant-a",
        allowed_purposes=frozenset({"economic_analysis"}),
    )

    with pytest.raises(IntelligenceReadDenied, match="tenant"):
        await reader.get_snapshot(IntelligenceQuery(
            tenant_id="tenant-b",
            subject_ref="company-a",
            purpose="economic_analysis",
        ))
    with pytest.raises(IntelligenceReadDenied, match="purpose"):
        await reader.get_snapshot(IntelligenceQuery(
            tenant_id="tenant-a",
            subject_ref="company-a",
            purpose="authorized_security_assessment",
        ))

    assert factory.connection.calls == []


@pytest.mark.asyncio
async def test_postgres_read_port_refuses_relationship_overflow_instead_of_truncating():
    class OverflowConnection(_Connection):
        async def execute(self, statement, params):
            sql = str(statement)
            if "FROM entities" in sql and "entity_id = :entity_id" in sql:
                return _Rows([{
                    "entity_id": "company-a",
                    "entity_type": "company",
                    "canonical_name": "Company A",
                    "created_at": NOW,
                }])
            if "FROM relation_claim" in sql:
                return _Rows([
                    {
                        "relation_id": f"relation-{i}",
                        "relation_type": "owns",
                        "subject_ref": "company-a",
                        "object_ref": "company-b",
                        "observation_refs": ["obs-rel"],
                        "context_ref": "",
                        "status": "unreviewed",
                        "confidence": None,
                        "evidence_grade": None,
                        "valid_from": None,
                        "valid_to": None,
                        "created_at": NOW,
                    }
                    for i in range(2)
                ])
            return await super().execute(statement, params)

    class OverflowFactory:
        def __init__(self):
            self.connection = OverflowConnection()

        def __call__(self):
            return self.connection

    reader = PostgresIntelligenceReadPort(
        OverflowFactory(),
        tenant_id="tenant-a",
        allowed_purposes=frozenset({"economic_analysis"}),
        max_relations=1,
    )

    with pytest.raises(IntelligenceSnapshotBudgetExceeded, match="exceeded"):
        await reader.get_snapshot(IntelligenceQuery(
            tenant_id="tenant-a",
            subject_ref="company-a",
            purpose="economic_analysis",
            max_hops=1,
        ))
