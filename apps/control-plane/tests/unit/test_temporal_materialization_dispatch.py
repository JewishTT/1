from __future__ import annotations

import pytest

from services import temporal_materialization_dispatch as dispatch


@pytest.mark.asyncio
async def test_temporal_launch_fails_closed_when_outbox_cannot_be_committed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_enqueue(*args, **kwargs) -> None:
        raise ConnectionError("postgres is offline")

    monkeypatch.setattr(dispatch, "_enqueue_durable", fail_enqueue)

    result = await dispatch.start_entity_materialization(
        tenant_id="tenant-a",
        entity_id="entity-1",
        identity={"domain": "example.org"},
    )

    assert result.status == "DEFERRED"
    assert result.reason == "durable outbox unavailable: ConnectionError"
    assert result.run_id.startswith("run-")
    assert result.workflow_id.startswith("entity-1/temporal-materialization/")


@pytest.mark.asyncio
async def test_temporal_launch_identity_is_idempotent_across_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    async def fail_enqueue(*args, **kwargs) -> None:
        nonlocal attempts
        attempts += 1
        raise ConnectionError("postgres is offline")

    monkeypatch.setattr(dispatch, "_enqueue_durable", fail_enqueue)
    first = await dispatch.start_entity_materialization(
        tenant_id="tenant-a", entity_id="entity-1", identity={"domain": "example.org"}
    )
    second = await dispatch.start_entity_materialization(
        tenant_id="tenant-a", entity_id="entity-1", identity={"domain": "example.org"}
    )

    assert attempts == 2
    assert first.run_id == second.run_id
    assert first.workflow_id == second.workflow_id
    assert first.status == second.status == "DEFERRED"
