"""Unit tests for deterministic SpecOps&CI decision outbox identities and enqueue semantics."""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from db.specops_ci_signal_outbox import (
    SPECOPS_DECISION_SIGNAL,
    enqueue_decision_signal,
    outbox_id_for,
)


class _Result:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one_or_none(self) -> Any:
        return self.value


class _Session:
    def __init__(self) -> None:
        self.rows: list[Any] = []

    async def execute(self, _statement: Any) -> _Result:
        return _Result(self.rows[0] if self.rows else None)

    def add(self, row: Any) -> None:
        self.rows.append(row)


def sample_payload() -> dict[str, Any]:
    return {
        "operation_id": "sci-op-123",
        "tenant_id": "tenant-1",
        "authorization_id": "auth-1",
        "snapshot_id": "snapshot-1",
        "step_id": "review",
        "spec_digest": "a" * 64,
        "decision_id": "decision-1",
        "approved": True,
        "reviewer_id": "admin-1",
        "approval_ref": "ticket:SEC-1",
    }


def test_outbox_id_is_deterministic_and_tenant_bound() -> None:
    first = outbox_id_for(tenant_id="tenant-1", decision_id="decision-1")
    assert first == outbox_id_for(tenant_id="tenant-1", decision_id="decision-1")
    assert first != outbox_id_for(tenant_id="tenant-2", decision_id="decision-1")
    assert first.startswith("scio-")


def test_enqueue_creates_a_compact_temporal_signal_intent() -> None:
    session = _Session()
    payload = sample_payload()
    row = asyncio.run(enqueue_decision_signal(
        session,  # type: ignore[arg-type]
        tenant_id="tenant-1",
        operation_id="sci-op-123",
        step_id="review",
        spec_digest="a" * 64,
        decision_id="decision-1",
        payload=payload,
    ))

    assert row.status == "PENDING"
    assert row.signal_name == SPECOPS_DECISION_SIGNAL
    assert row.payload == payload
    assert row.outbox_id == outbox_id_for(
        tenant_id="tenant-1",
        decision_id="decision-1",
    )
    assert len(session.rows) == 1


def test_repeated_enqueue_is_idempotent_but_payload_changes_are_rejected() -> None:
    session = _Session()
    payload = sample_payload()
    first = asyncio.run(enqueue_decision_signal(
        session,  # type: ignore[arg-type]
        tenant_id="tenant-1",
        operation_id="sci-op-123",
        step_id="review",
        spec_digest="a" * 64,
        decision_id="decision-1",
        payload=payload,
    ))
    repeated = asyncio.run(enqueue_decision_signal(
        session,  # type: ignore[arg-type]
        tenant_id="tenant-1",
        operation_id="sci-op-123",
        step_id="review",
        spec_digest="a" * 64,
        decision_id="decision-1",
        payload=payload,
    ))
    assert repeated is first
    assert len(session.rows) == 1

    changed = {**payload, "approved": False}
    with pytest.raises(ValueError, match="different payload"):
        asyncio.run(enqueue_decision_signal(
            session,  # type: ignore[arg-type]
            tenant_id="tenant-1",
            operation_id="sci-op-123",
            step_id="review",
            spec_digest="a" * 64,
            decision_id="decision-1",
            payload=changed,
        ))
