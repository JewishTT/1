from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from api.auth import Role, TenantContext
from api.routes import specops_roe
from specops.roe.gate import RoeRegistry


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> RoeRegistry:
    store = RoeRegistry()
    monkeypatch.setattr(specops_roe, "REGISTRY", store)
    monkeypatch.setattr(specops_roe, "_TENANT_BY_ROE_ID", {})
    return store


def admin(tenant_id: str = "tenant-a") -> TenantContext:
    return TenantContext(tenant_id, "verified-supervisor", frozenset({Role.ADMIN}))


@pytest.mark.asyncio
async def test_roe_approver_is_verified_admin_not_request_input(registry: RoeRegistry) -> None:
    body = specops_roe.RoeCreate.model_validate({
        "target_ref": "lab://approved-range",
        "scope": "passive validation",
        "approved_by": "attacker-controlled-value",
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    })
    created = await specops_roe.record_roe(body, admin())
    stored = registry.get(created.roe_id)
    assert stored is not None
    assert stored.approved_by == "verified-supervisor"
    assert created.approved_by == "verified-supervisor"
    assert "approved_by" not in specops_roe.RoeCreate.model_fields


@pytest.mark.asyncio
async def test_analyst_cannot_create_rules_of_engagement(registry: RoeRegistry) -> None:
    analyst = TenantContext("tenant-a", "analyst-1", frozenset({Role.ANALYST}))
    body = specops_roe.RoeCreate(target_ref="lab://range", scope="passive validation")
    with pytest.raises(HTTPException) as exc:
        await specops_roe.record_roe(body, analyst)
    assert exc.value.status_code == 403
    assert registry._by_id == {}


@pytest.mark.asyncio
async def test_roe_read_is_tenant_scoped(registry: RoeRegistry) -> None:
    created = await specops_roe.record_roe(
        specops_roe.RoeCreate(target_ref="lab://tenant-a", scope="passive validation"),
        admin("tenant-a"),
    )
    with pytest.raises(HTTPException) as exc:
        await specops_roe.get_roe(
            created.roe_id,
            TenantContext("tenant-b", "admin-b", frozenset({Role.ADMIN})),
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("expiry", [
    "not-a-date",
    "2099-01-01T00:00:00",
    "2000-01-01T00:00:00Z",
])
async def test_roe_expiry_must_be_valid_zoned_and_future(
    registry: RoeRegistry, expiry: str
) -> None:
    body = specops_roe.RoeCreate(
        target_ref="lab://range", scope="passive validation", expires_at=expiry
    )
    with pytest.raises(HTTPException) as exc:
        await specops_roe.record_roe(body, admin())
    assert exc.value.status_code == 422
    assert registry._by_id == {}
