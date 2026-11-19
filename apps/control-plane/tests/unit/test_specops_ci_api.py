"""HTTP contract tests for the durable SpecOps&CI operation API.

The tests use isolated FastAPI applications and a deterministic async-session double.
They exercise the actual authentication dependencies and endpoint code without
requiring a live PostgreSQL or Temporal service.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.auth import Role, TenantContext, resolve_tenant
from api.routes import specops_ci
from db.schema import SpecOpsOperationDecision


class _Result:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one_or_none(self) -> Any:
        return self.value


class _Session:
    """Small async SQLAlchemy session double with an ordered result script."""

    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.added: list[Any] = []
        self.begin_count = 0

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    def begin(self) -> _Session:
        self.begin_count += 1
        return self

    async def execute(self, _statement: Any) -> _Result:
        if not self.responses:
            raise AssertionError("unexpected database query")
        return _Result(self.responses.pop(0))

    def add(self, row: Any) -> None:
        self.added.append(row)


class _SessionFactory:
    def __init__(self, session: _Session) -> None:
        self.session = session

    def __call__(self) -> _Session:
        return self.session


def _client(
    *,
    roles: frozenset[Role],
    tenant_id: str = "tenant-1",
) -> TestClient:
    app = FastAPI()
    app.include_router(specops_ci.router, prefix="/api/v1")
    context = TenantContext(
        tenant_id=tenant_id,
        user_id="reviewer-1",
        roles=roles,
    )
    app.dependency_overrides[resolve_tenant] = lambda: context
    return TestClient(app)


def _authorization_row() -> SimpleNamespace:
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        authorization_id="auth-1",
        tenant_id="tenant-1",
        source_snapshot_id="snapshot-1",
        issued_at=now - timedelta(minutes=5),
        expires_at=now + timedelta(hours=1),
        revoked_at=None,
    )


def _pending_approval() -> dict[str, str]:
    return {
        "operation_id": "sci-op-123",
        "tenant_id": "tenant-1",
        "authorization_id": "auth-1",
        "snapshot_id": "snapshot-1",
        "step_id": "coverage",
        "spec_digest": "a" * 64,
    }


class _ApprovalHandle:
    async def query(self, name: str) -> dict[str, str]:
        assert name == "get_pending_approval"
        return _pending_approval()


def _operation_summary() -> dict[str, str]:
    return {
        "tenant_id": "tenant-1",
        "authorization_id": "auth-1",
        "snapshot_id": "snapshot-1",
        "spec_digest": "a" * 64,
    }


def _install_operation_handle(
    monkeypatch: pytest.MonkeyPatch,
    handle: _ApprovalHandle,
) -> None:
    async def get_handles(_operation_id: str, _tenant_id: str):
        return handle, _operation_summary()

    monkeypatch.setattr(specops_ci, "_get_operation_handles", get_handles)


def test_operator_decision_requires_admin_role() -> None:
    with _client(roles=frozenset({Role.ANALYST})) as client:
        response = client.post(
            "/api/v1/specops-ci/operations/sci-op-123/steps/coverage/decision",
            json={"approved": True, "approval_ref": "ticket:SEC-123"},
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "insufficient role"


def test_admin_decision_and_signal_intent_are_written_in_one_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_operation_handle(monkeypatch, _ApprovalHandle())
    session = _Session([_authorization_row(), None, None])
    platform = SimpleNamespace(session_factory=_SessionFactory(session))

    async def get_platform(*, tenant_id: str):
        assert tenant_id == "tenant-1"
        return platform

    monkeypatch.setattr(specops_ci, "get_platform", get_platform)
    with _client(roles=frozenset({Role.ADMIN})) as client:
        response = client.post(
            "/api/v1/specops-ci/operations/sci-op-123/steps/coverage/decision",
            json={"approved": True, "approval_ref": "  ticket:SEC-123  "},
        )

    assert response.status_code == 202, response.text
    payload = response.json()
    assert payload["status"] == "queued_for_delivery"
    assert payload["approved"] is True
    assert payload["signal_name"] == "provide_operator_decision"
    assert session.begin_count == 1
    assert len(session.added) == 2

    decision, outbox = session.added
    assert isinstance(decision, SpecOpsOperationDecision)
    assert decision.tenant_id == "tenant-1"
    assert decision.operation_id == "sci-op-123"
    assert decision.authorization_id == "auth-1"
    assert decision.snapshot_id == "snapshot-1"
    assert decision.step_id == "coverage"
    assert decision.reviewer_id == "reviewer-1"
    assert decision.reviewer_role == "admin"
    assert decision.approval_ref == "ticket:SEC-123"
    assert outbox.decision_id == decision.decision_id
    assert outbox.tenant_id == decision.tenant_id
    assert outbox.payload["decision_id"] == decision.decision_id
    assert outbox.payload["spec_digest"] == "a" * 64
    assert outbox.status == "PENDING"


def test_existing_decision_is_idempotently_reused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_operation_handle(monkeypatch, _ApprovalHandle())
    decision = SimpleNamespace(
        decision_id="scid-existing",
        approved=False,
        reviewer_id="reviewer-1",
        approval_ref="ticket:SEC-123",
    )
    signal_payload = {
        **_pending_approval(),
        "decision_id": "scid-existing",
        "approved": False,
        "reviewer_id": "reviewer-1",
        "approval_ref": "ticket:SEC-123",
    }
    existing_outbox = SimpleNamespace(
        operation_id="sci-op-123",
        step_id="coverage",
        spec_digest="a" * 64,
        payload=signal_payload,
        outbox_id="scio-existing",
    )
    session = _Session([_authorization_row(), decision, existing_outbox])
    platform = SimpleNamespace(session_factory=_SessionFactory(session))

    async def get_platform(*, tenant_id: str):
        assert tenant_id == "tenant-1"
        return platform

    monkeypatch.setattr(specops_ci, "get_platform", get_platform)
    with _client(roles=frozenset({Role.ADMIN})) as client:
        response = client.post(
            "/api/v1/specops-ci/operations/sci-op-123/steps/coverage/decision",
            json={"approved": False, "approval_ref": "ticket:SEC-123"},
        )

    assert response.status_code == 202, response.text
    assert response.json()["decision_id"] == "scid-existing"
    assert response.json()["outbox_id"] == "scio-existing"
    assert session.begin_count == 1
    assert session.added == []


def test_delivery_status_is_not_visible_across_tenants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session([None])
    platform = SimpleNamespace(session_factory=_SessionFactory(session))

    async def get_platform(*, tenant_id: str):
        assert tenant_id == "tenant-2"
        return platform

    monkeypatch.setattr(specops_ci, "get_platform", get_platform)
    with _client(
        roles=frozenset({Role.ANALYST}),
        tenant_id="tenant-2",
    ) as client:
        response = client.get(
            "/api/v1/specops-ci/operations/sci-op-123/"
            "decisions/scid-secret/delivery"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "decision delivery record not found"


def test_operation_lookup_hides_workflows_owned_by_another_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ForeignHandle:
        async def query(self, name: str) -> dict[str, str]:
            assert name == "get_operation_summary"
            return {"tenant_id": "tenant-foreign"}

    class _TemporalClient:
        def get_workflow_handle(self, _operation_id: str) -> _ForeignHandle:
            return _ForeignHandle()

    async def connect_temporal() -> _TemporalClient:
        return _TemporalClient()

    # Replace only the import boundary used by the route helper.
    fake_workflow = ModuleType("workflow")
    fake_workflow.__path__ = []  # type: ignore[attr-defined]
    fake_client = ModuleType("workflow.client")
    fake_client.connect_temporal = connect_temporal  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "workflow", fake_workflow)
    monkeypatch.setitem(sys.modules, "workflow.client", fake_client)

    with pytest.raises(HTTPException) as raised:
        asyncio.run(
            specops_ci._get_operation_handles(
                "sci-op-123",
                "tenant-1",
            )
        )
    assert raised.value.status_code == 404
