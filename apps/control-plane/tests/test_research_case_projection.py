"""Contracts for durable Feature 034 projections.

The projection tests deliberately use only canonical context/action contracts and real
projection serializers. They do not fabricate observations or relation rows to turn a
missing backend into an apparent successful read.
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from services.research_case_projection import (
    PostgresResearchCaseProjectionProvider,
    _claim_state,
    _cursor_decode,
    _cursor_encode,
    _epistemic_state,
    _row_visible_as_of,
)


class _EmptyMappings:
    def mappings(self):
        return self

    def all(self):
        return []


class _EmptySession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, *_args, **_kwargs):
        return _EmptyMappings()


class _FakeStore:
    def __init__(self, *, revisions=()):
        self._revisions = list(revisions)
        self.context = SimpleNamespace(
            context_id="case-context-1",
            tenant_id="tenant-1",
            investigation_id="case-investigation-1",
        )
        self.metadata = {
            "tenant_id": "tenant-1",
            "scope_digest": "sha256:" + "a" * 64,
            "scope_revision": 1,
            "approved": True,
            "allowed_source_ids": ["crossref_works"],
        }

    async def get_context(self, case_id):
        return self.context if case_id == self.context.context_id else None

    async def get_person_case_metadata(self, case_id):
        return self.metadata if case_id == self.context.context_id else None

    async def obligations(self, case_id):
        assert case_id == self.context.context_id
        return [SimpleNamespace(obligation_id="obligation-1", question="Which public record supports this publication?")]

    async def actions(self, obligation_id):
        assert obligation_id == "obligation-1"
        return []

    async def revisions(self, case_id):
        assert case_id == self.context.context_id
        return self._revisions


@pytest.mark.asyncio
async def test_coverage_does_not_conflate_not_planned_with_no_results() -> None:
    store = _FakeStore()
    provider = PostgresResearchCaseProjectionProvider(
        session_factory=_EmptySession,
        context_store=store,
        policy=SimpleNamespace(policy_digest="sha256:" + "b" * 64),
    )
    ledger = await provider.coverage_ledger(case_id="case-context-1", tenant_id="tenant-1")

    assert ledger["overall_state"] == "NOT_PLANNED"
    assert ledger["items"][0]["state"] == "PLAN_NOT_CREATED"
    assert ledger["items"][0]["reason_code"] == "PLAN_NOT_CREATED"
    assert ledger["items"][0]["records_received"] == 0


@pytest.mark.asyncio
async def test_coverage_exposes_the_persisted_capability_gap_after_planning() -> None:
    revision = SimpleNamespace(snapshot={
        "plan_digest": "sha256:" + "c" * 64,
        "plan_state": "BLOCKED_CAPABILITY",
        "capability_gaps": [{
            "obligation_id": "obligation-1",
            "detail": "no enabled, attested source supports public_professional_role",
        }],
    })
    store = _FakeStore(revisions=[revision])
    provider = PostgresResearchCaseProjectionProvider(
        session_factory=_EmptySession,
        context_store=store,
        policy=SimpleNamespace(policy_digest="sha256:" + "b" * 64),
    )
    ledger = await provider.coverage_ledger(case_id="case-context-1", tenant_id="tenant-1")

    assert ledger["overall_state"] == "BLOCKED_CAPABILITY"
    assert ledger["items"][0]["state"] == "NO_ELIGIBLE_ACTIONS"
    assert ledger["items"][0]["reason_code"] == "NO_ELIGIBLE_SOURCE_ACTION"
    assert "no enabled, attested source" in ledger["items"][0]["detail"]


def test_claim_state_and_polarity_are_not_inferred_from_a_stored_relation() -> None:
    assert _claim_state("active") == "proposed"
    assert _claim_state("contested") == "contested"
    assert _claim_state("retracted") == "retracted"
    row = SimpleNamespace(relation_id="relation-1", contradicts=[])
    assert _epistemic_state(row, {"relation-1"}) == "NEITHER"


def test_as_of_projection_excludes_claims_with_unknown_knowledge_time() -> None:
    row = SimpleNamespace(known_from=None, known_until=None)
    assert not _row_visible_as_of(row, datetime(2025, 1, 1, tzinfo=UTC))
    row.known_from = datetime(2025, 2, 1, tzinfo=UTC)
    assert not _row_visible_as_of(row, datetime(2025, 1, 1, tzinfo=UTC))
    row.known_from = datetime(2024, 1, 1, tzinfo=UTC)
    assert _row_visible_as_of(row, datetime(2025, 1, 1, tzinfo=UTC))


def test_claim_cursor_is_stable_and_rejects_invalid_input() -> None:
    created_at = datetime(2026, 10, 25, 12, 30, tzinfo=UTC)
    cursor = _cursor_encode(created_at, "relation-abc")
    moment, relation_id = _cursor_decode(cursor)
    assert moment == created_at
    assert relation_id == "relation-abc"
    with pytest.raises(ValueError, match="invalid relation-claim cursor"):
        _cursor_decode("not-a-cursor")


class _FakeValues:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _FakeResult:
    def __init__(self, *, mappings=(), scalars=()):
        self._mappings = list(mappings)
        self._scalars = list(scalars)

    def mappings(self):
        return _FakeValues(self._mappings)

    def scalars(self):
        return _FakeValues(self._scalars)


class _ProjectionDatabase:
    def __init__(self, *, intents=(), reservations=(), observations=()):
        self.intents = list(intents)
        self.reservations = list(reservations)
        self.observations = list(observations)


class _ProjectionSession(_EmptySession):
    def __init__(self, database):
        self.database = database

    async def execute(self, statement, *_args, **_kwargs):
        sql = str(statement).lower()
        if "person_case_dispatch_intents" in sql:
            return _FakeResult(mappings=self.database.intents)
        if "person_case_budget_reservations" in sql:
            return _FakeResult(mappings=self.database.reservations)
        if "from observations" in sql:
            return _FakeResult(scalars=self.database.observations)
        return _FakeResult()


class _ActionStore(_FakeStore):
    def __init__(self, *, actions, revisions=()):
        super().__init__(revisions=revisions)
        self._actions = list(actions)

    async def actions(self, obligation_id):
        assert obligation_id == "obligation-1"
        return list(self._actions)


@pytest.mark.asyncio
async def test_coverage_links_broker_ack_to_the_real_observation_row() -> None:
    scope_digest = "sha256:" + "a" * 64
    policy_digest = "sha256:" + "b" * 64
    action = SimpleNamespace(
        action_id="action-approved-1",
        parent_action_id="action-proposed-1",
        obligation_id="obligation-1",
        source_id="crossref_works",
        catalogue_source_id="crossref_doi",
        scope_digest=scope_digest,
        policy_digest=policy_digest,
        status="approved",
        requires_operator_approval=False,
    )
    intent_payload = {
        "case_id": "case-context-1",
        "tenant_id": "tenant-1",
        "run_id": "run-1",
        "idempotency_key": "run-key-1",
        "approved_action_refs": ["action-approved-1"],
        "scope_digest": scope_digest,
        "policy_digest": policy_digest,
        "state": "PUBLISHED",
        "outcome": {
            "published": True,
            "budget_reservation_id": "reservation-1",
            "records": [{
                "action_id": "action-approved-1",
                "task_id": "TSK-actual-task-1",
                "source_id": "crossref_doi",
                "published": True,
                "verdict": "PUBLISHED",
                "topic": "acquisition.request",
                "offset": 17,
            }],
        },
    }
    now = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
    observation = SimpleNamespace(
        observation_id="OBS-actual-1",
        tenant_id="tenant-1",
        investigation_id="case-investigation-1",
        task_id="TSK-actual-task-1",
        source_id="crossref_doi",
        uri="https://api.crossref.org/works?query=Public",
        raw_ref="s3://raw/sha256/ab/cd",
        created_at=now,
        status="created",
        content_hash="deadbeef",
    )
    database = _ProjectionDatabase(
        intents=[{
            "payload": intent_payload,
            "created_at": now,
            "updated_at": now,
        }],
        reservations=[{
            "reservation_id": "reservation-1",
            "idempotency_key": "run-key-1",
            "state": "PUBLISHED",
            "payload": {"state": "PUBLISHED"},
            "created_at": now,
            "updated_at": now,
        }],
        observations=[observation],
    )
    store = _ActionStore(actions=[action])
    provider = PostgresResearchCaseProjectionProvider(
        session_factory=lambda: _ProjectionSession(database),
        context_store=store,
        policy=SimpleNamespace(policy_digest=policy_digest),
    )

    ledger = await provider.coverage_ledger(case_id="case-context-1", tenant_id="tenant-1")

    assert ledger["overall_state"] == "OBSERVATIONS_RECEIVED"
    assert ledger["source_of_truth"].startswith("postgres:")
    item = ledger["items"][0]
    assert item["state"] == "OBSERVATIONS_RECEIVED"
    assert item["attempts"] == 1
    assert item["records_received"] == 1
    assert item["observation_refs"] == ["OBS-actual-1"]
    assert item["raw_artifact_refs"] == ["s3://raw/sha256/ab/cd"]
    assert item["budget_reservation_id"] == "reservation-1"
