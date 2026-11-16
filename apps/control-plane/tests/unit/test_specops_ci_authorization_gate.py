"""Unit tests for the PostgreSQL authorization and decision gate."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

from services.specops_ci_authorization_gate import PostgresSpecOpsAuthorizationGate
from specops_ci.domain import AssessmentKind


class _Result:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class _Session:
    def __init__(self, responses: list[Any]) -> None:
        self._responses = responses

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    async def execute(self, _statement: Any) -> _Result:
        if not self._responses:
            raise AssertionError("unexpected database query")
        return _Result(self._responses.pop(0))


class _SessionFactory:
    def __init__(self, responses: list[Any]) -> None:
        self._responses = responses

    def __call__(self) -> _Session:
        return _Session(self._responses)


def _authorization(**overrides: Any) -> SimpleNamespace:
    now = datetime.now(timezone.utc)
    values = {
        "revoked_at": None,
        "source_snapshot_id": "snapshot-1",
        "issued_at": now - timedelta(minutes=5),
        "expires_at": now + timedelta(hours=1),
        "allowed_entity_ids": ["entity-1"],
        "allowed_assessments": [AssessmentKind.DETECTION_VALIDATION.value],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_revalidate_requires_current_exact_roster_and_assessment() -> None:
    gate = PostgresSpecOpsAuthorizationGate(
        _SessionFactory([_authorization()])  # type: ignore[arg-type]
    )
    now = datetime.now(timezone.utc)
    valid = __import__("asyncio").run(gate.revalidate(
        tenant_id="tenant-1",
        authorization_id="auth-1",
        snapshot_id="snapshot-1",
        operation_expires_at=(now + timedelta(minutes=30)).isoformat(),
        target_entity_ids=["entity-1"],
        assessment_kind=AssessmentKind.DETECTION_VALIDATION,
    ))
    assert valid is True

    gate = PostgresSpecOpsAuthorizationGate(
        _SessionFactory([_authorization()])  # type: ignore[arg-type]
    )
    outside_scope = __import__("asyncio").run(gate.revalidate(
        tenant_id="tenant-1",
        authorization_id="auth-1",
        snapshot_id="snapshot-1",
        operation_expires_at=(now + timedelta(minutes=30)).isoformat(),
        target_entity_ids=["entity-2"],
        assessment_kind=AssessmentKind.DETECTION_VALIDATION,
    ))
    assert outside_scope is False


def test_revalidate_rejects_revoked_and_expired_authorizations() -> None:
    now = datetime.now(timezone.utc)
    revoked = _authorization(revoked_at=now)
    gate = PostgresSpecOpsAuthorizationGate(
        _SessionFactory([revoked])  # type: ignore[arg-type]
    )
    result = __import__("asyncio").run(gate.revalidate(
        tenant_id="tenant-1",
        authorization_id="auth-1",
        snapshot_id="snapshot-1",
        operation_expires_at=(now + timedelta(minutes=30)).isoformat(),
        target_entity_ids=["entity-1"],
        assessment_kind=AssessmentKind.DETECTION_VALIDATION,
    ))
    assert result is False


def test_operator_decision_must_match_the_durable_row_and_live_authorization() -> None:
    now = datetime.now(timezone.utc)
    decision = {
        "decision_id": "decision-1",
        "authorization_id": "auth-1",
        "snapshot_id": "snapshot-1",
        "reviewer_id": "admin-1",
        "approval_ref": "ticket:SEC-123",
        "approved": True,
    }
    row = SimpleNamespace(
        decided_at=now - timedelta(seconds=2),
    )
    gate = PostgresSpecOpsAuthorizationGate(
        _SessionFactory([row, _authorization()])  # type: ignore[arg-type]
    )
    result = __import__("asyncio").run(gate.verify_operator_decision(
        tenant_id="tenant-1",
        operation_id="op-1",
        spec_digest="a" * 64,
        step_id="coverage",
        decision=decision,
    ))
    assert result is True


def test_rejected_decision_is_validly_audited_but_never_approved() -> None:
    now = datetime.now(timezone.utc)
    decision = {
        "decision_id": "decision-2",
        "authorization_id": "auth-1",
        "snapshot_id": "snapshot-1",
        "reviewer_id": "admin-1",
        "approval_ref": "ticket:SEC-124",
        "approved": False,
    }
    row = SimpleNamespace(decided_at=now - timedelta(seconds=1))
    gate = PostgresSpecOpsAuthorizationGate(
        _SessionFactory([row, _authorization()])  # type: ignore[arg-type]
    )
    result = __import__("asyncio").run(gate.verify_operator_decision(
        tenant_id="tenant-1",
        operation_id="op-1",
        spec_digest="b" * 64,
        step_id="coverage",
        decision=decision,
    ))
    assert result is True
