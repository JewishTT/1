"""Contract tests for tenant-scoped durable quarantine storage."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from events.dlq import DLQRecord, QuarantineStore  # noqa: E402
from events.dlq_durable import RAW_BUCKET, DurableQuarantineStore, ObjectStoreSink  # noqa: E402


class FakeObjectStore:
    raw_bucket = RAW_BUCKET

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put_raw(self, body: bytes, *, tenant_id: str, meta=None):
        import hashlib
        from types import SimpleNamespace

        digest = hashlib.sha256(body).hexdigest()
        key = f"raw/{tenant_id}/202611/{digest}"
        self.objects[f"{RAW_BUCKET}/{key}"] = body
        return SimpleNamespace(
            sha256=digest,
            uri=f"s3://{RAW_BUCKET}/{key}",
            size=len(body),
            tenant_prefix=f"{tenant_id}/202611",
            year_month="202611",
        )

    async def put_immutable_object(self, key: str, body: bytes, *, tenant_id="", meta=None):
        current = self.objects.get(f"{RAW_BUCKET}/{key}")
        if current is not None and current != body:
            raise ValueError("immutable object collision")
        self.objects[f"{RAW_BUCKET}/{key}"] = body
        return current is None

    async def get_object(self, key: str):
        return self.objects.get(f"{RAW_BUCKET}/{key}")

    async def list_objects_page(self, prefix: str, *, limit=100, continuation_token=None):
        keys = sorted(
            key.removeprefix(f"{RAW_BUCKET}/")
            for key in self.objects
            if key.startswith(f"{RAW_BUCKET}/{prefix}")
        )
        offset = int(continuation_token or "0")
        selected = keys[offset:offset + limit]
        token = str(offset + limit) if offset + limit < len(keys) else None
        return selected, token


def make_record(tenant_id="tenant-a", topic="interpretation", payload=b"raw"):
    return DLQRecord(
        tenant_id=tenant_id,
        reason="transport_failed",
        topic=topic,
        payload=payload,
    )


@pytest.mark.asyncio
async def test_payload_uses_bare_object_key_and_survives_restart():
    store = FakeObjectStore()
    sink = ObjectStoreSink(store=store, tenant_id="tenant-a")
    receipt = await sink.aput(make_record(payload=b"original-envelope"))
    restarted = ObjectStoreSink(store=store, tenant_id="tenant-a")
    restored = await restarted.aload(receipt["record_id"])
    assert restored is not None
    assert restored.payload == b"original-envelope"


@pytest.mark.asyncio
async def test_index_is_enumerable_and_paginates():
    store = FakeObjectStore()
    sink = ObjectStoreSink(store=store, tenant_id="tenant-a")
    for index in range(7):
        await sink.aput(make_record(payload=f"payload-{index}".encode()))
    page_1 = await sink.alist_page(limit=3)
    page_2 = await sink.alist_page(limit=3, cursor=page_1["next_cursor"])
    page_3 = await sink.alist_page(limit=3, cursor=page_2["next_cursor"])
    assert [len(page["items"]) for page in (page_1, page_2, page_3)] == [3, 3, 1]
    assert page_3["next_cursor"] is None


@pytest.mark.asyncio
async def test_same_payload_isolated_between_tenants():
    store = FakeObjectStore()
    a = ObjectStoreSink(store=store, tenant_id="tenant-a")
    b = ObjectStoreSink(store=store, tenant_id="tenant-b")
    receipt_a = await a.aput(make_record(tenant_id="tenant-a", payload=b"same"))
    receipt_b = await b.aput(make_record(tenant_id="tenant-b", payload=b"same"))
    assert receipt_a["record_id"] != receipt_b["record_id"]
    assert await a.aload(receipt_b["record_id"]) is None
    assert await b.aload(receipt_a["record_id"]) is None


@pytest.mark.asyncio
async def test_sink_rejects_cross_tenant_write_and_bad_uri():
    store = FakeObjectStore()
    sink = ObjectStoreSink(store=store, tenant_id="tenant-a")
    with pytest.raises(PermissionError):
        await sink.aput(make_record(tenant_id="tenant-b"))
    with pytest.raises(ValueError):
        sink._payload_key("s3://other-bucket/raw/tenant-a/file")


@pytest.mark.asyncio
async def test_topic_filter_keeps_continuation_cursor():
    store = FakeObjectStore()
    sink = ObjectStoreSink(store=store, tenant_id="tenant-a")
    for index in range(6):
        await sink.aput(make_record(topic="a" if index % 2 == 0 else "b", payload=f"p{index}".encode()))
    page = await sink.alist_page(limit=2, topic="b")
    assert len(page["items"]) == 2
    assert all(item["topic"] == "b" for item in page["items"])
    assert page["next_cursor"] is not None


@pytest.mark.asyncio
async def test_filtered_pagination_does_not_skip_keys_after_a_partial_page() -> None:
    store = FakeObjectStore()
    sink = ObjectStoreSink(store=store, tenant_id="tenant-a")
    topics = ("wanted", "wanted", "other", "wanted", "other", "wanted")
    expected: list[str] = []

    for index, topic in enumerate(topics):
        record_id = f"DLQ-{index:024x}"
        metadata = {
            "record_id": record_id,
            "tenant_id": "tenant-a",
            "topic": topic,
            "reason": "transport_failed",
            "preserved": True,
        }
        key = f"{RAW_BUCKET}/{sink._meta_key(record_id)}"
        store.objects[key] = json.dumps(metadata).encode("utf-8")
        if topic == "wanted":
            expected.append(record_id)

    first = await sink.alist_page(limit=3, topic="wanted")
    second = await sink.alist_page(
        limit=3, cursor=first["next_cursor"], topic="wanted"
    )

    observed = [item["record_id"] for item in first["items"] + second["items"]]
    assert observed == expected
    assert first["next_cursor"] is not None
    assert second["next_cursor"] is None


def test_durable_quarantine_cannot_purge():
    store = FakeObjectStore()
    q = DurableQuarantineStore(ObjectStoreSink(store=store, tenant_id="tenant-a"))
    with pytest.raises(RuntimeError, match="cannot be purged"):
        q.purge("DLQ-" + "a" * 24)


def test_memory_only_store_remains_explicitly_available_for_tests():
    q = QuarantineStore()
    rid = q.quarantine(DLQRecord(payload=b"memory", topic="interpretation"))
    assert q.replay(rid) == b"memory"
    assert q.purge(rid)
