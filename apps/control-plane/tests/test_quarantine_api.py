from __future__ import annotations

import pytest
from fastapi import HTTPException

from api.auth import TenantContext
from api.routes import quarantine


@pytest.mark.asyncio
async def test_dlq_list_fails_closed_when_tenant_repository_is_missing() -> None:
    with pytest.raises(HTTPException) as exc:
        await quarantine.list_quarantine(ctx=TenantContext("tenant-a", "analyst-a"))
    assert exc.value.status_code == 503
    assert "tenant-scoped durable" in exc.value.detail


@pytest.mark.asyncio
async def test_dlq_inspect_replay_and_reevaluate_do_not_fake_not_found() -> None:
    ctx = TenantContext("tenant-a", "analyst-a")
    operations = (
        quarantine.get_quarantined("DLQ-example", ctx),
        quarantine.replay_record("DLQ-example", ctx),
        quarantine.re_evaluate("DLQ-example", ctx),
    )
    for operation in operations:
        with pytest.raises(HTTPException) as exc:
            await operation
        assert exc.value.status_code == 503
