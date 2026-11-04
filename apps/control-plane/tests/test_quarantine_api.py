from __future__ import annotations

import pytest
from fastapi import HTTPException

from api.auth import Role, TenantContext
from api.routes import quarantine
from events.dlq import DLQRecord
from events.dlq_durable import ObjectStoreSink


class FakeObjectStore:
    raw_bucket = "knowledge-raw"

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put_raw(self, body: bytes, *, tenant_id: str, meta=None):
        import hashlib
        from types import SimpleNamespace

        digest = hashlib.sha256(body).hexdigest()
        key = f"raw/{tenant_id}/202611/{digest}"
        self.objects[f"{self.raw_bucket}/{key}"] = body
        return SimpleNamespace(
            sha256=digest,
            uri=f"s3://{self.raw_bucket}/{key}",
            size=len(body),
        )

    async def put_immutable_object(self, key, body, *, tenant_id="", meta=None):
        current = self.objects.get(f"{self.raw_bucket}/{key}")
        if current is not None and current != body:
            raise ValueError("immutable object collision")
        self.objects[f"{self.raw_bucket}/{key}"] = body
        return current is None

    async def get_object(self, key):
        return self.objects.get(f"{self.raw_bucket}/{key}")

    async def list_objects_page(self, prefix, *, limit=100, continuation_token=None):
        keys = sorted(
            key.removeprefix(f"{self.raw_bucket}/")
            for key in self.objects
            if key.startswith(f"{self.raw_bucket}/{prefix}")
        )
        offset = int(continuation_token or "0")
        selected = keys[offset:offset + limit]
        token = str(offset + limit) if offset + limit < len(keys) else None
        return selected, token


@pytest.fixture
def object_store(monkeypatch: pytest.MonkeyPatch) -> FakeObjectStore:
    store = FakeObjectStore()
    monkeypatch.setattr(quarantine, "ObjectStore", lambda: store)
    return store


def analyst(tenant_id: str = "tenant-a") -> TenantContext:
    return TenantContext(tenant_id, "analyst-user", frozenset({Role.ANALYST}))


@pytest.mark.asyncio
async def test_list_and_get_are_backed_by_tenant_scoped_durable_metadata(object_store):
    sink = ObjectStoreSink(store=object_store, tenant_id="tenant-a")
    record = DLQRecord(
        tenant_id="tenant-a",
        reason="transport_failed",
        payload=b"original-event-envelope",
        topic="cognitive.dlq",
        source_id="SRC-1",
        task_id="TASK-1",
        original_event_id="evt-1",
    )
    receipt = await sink.aput(record)

    listing = await quarantine.list_quarantine(ctx=analyst())
    detail = await quarantine.get_quarantined(receipt["record_id"], ctx=analyst())

    assert len(listing["items"]) == 1
    assert listing["items"][0]["record_id"] == receipt["record_id"]
    assert detail["task_id"] == "TASK-1"
    assert "payload_ref" not in detail
    assert "payload_key" not in detail


@pytest.mark.asyncio
async def test_tenant_cannot_enumerate_or_read_another_tenants_records(object_store):
    sink = ObjectStoreSink(store=object_store, tenant_id="tenant-a")
    receipt = await sink.aput(
        DLQRecord(
            tenant_id="tenant-a",
            reason="transport_failed",
            payload=b"private-request",
            topic="cognitive.dlq",
        )
    )
    listing = await quarantine.list_quarantine(ctx=analyst("tenant-b"))
    assert listing["items"] == []
    with pytest.raises(HTTPException) as exc:
        await quarantine.get_quarantined(receipt["record_id"], ctx=analyst("tenant-b"))
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_replay_requires_admin_and_stays_disabled_without_governed_redrive():
    with pytest.raises(HTTPException) as denied:
        await quarantine.replay_record("DLQ-" + "a" * 24, analyst())
    assert denied.value.status_code == 403

    admin = TenantContext("tenant-a", "admin-user", frozenset({Role.ADMIN}))
    with pytest.raises(HTTPException) as unavailable:
        await quarantine.replay_record("DLQ-" + "a" * 24, admin)
    assert unavailable.value.status_code == 503
    assert "record remains preserved" in unavailable.value.detail


@pytest.mark.asyncio
async def test_re_evaluation_requires_admin_and_does_not_delete_records():
    with pytest.raises(HTTPException) as denied:
        await quarantine.re_evaluate("DLQ-" + "a" * 24, analyst())
    assert denied.value.status_code == 403
