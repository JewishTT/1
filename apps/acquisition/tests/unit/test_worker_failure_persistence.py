from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))

from events.topics import TOPIC_DLQ  # noqa: E402
from worker_acquisition import Failure, kafka_failure_sink  # noqa: E402


class FakeObjectStore:
    raw_bucket = "knowledge-raw"

    def __init__(self):
        self.objects = {}

    async def put_raw(self, body, *, tenant_id, meta=None):
        import hashlib

        digest = hashlib.sha256(body).hexdigest()
        key = f"raw/{tenant_id}/202611/{digest}"
        self.objects[f"{self.raw_bucket}/{key}"] = body
        return SimpleNamespace(sha256=digest, uri=f"s3://{self.raw_bucket}/{key}", size=len(body))

    async def put_immutable_object(self, key, body, *, tenant_id="", meta=None):
        self.objects[f"{self.raw_bucket}/{key}"] = body
        return True


class FakeProducer:
    def __init__(self, store):
        self.store = store
        self.records = []

    def publish_sync(self, topic, value, *, key, event_type=""):
        # The failure marker cannot become visible before both immutable objects exist.
        assert len(self.store.objects) == 2
        marker = json.loads(value)
        self.records.append((topic, marker, key, event_type))
        return SimpleNamespace(topic=topic, partition=0, offset=len(self.records) - 1)


class Envelope:
    def __init__(self, *, tenant_id="tenant-a"):
        self.tenant_id = tenant_id
        self.investigation_id = "INV-1"
        self.source_id = "SRC-1"
        self.work_id = "TASK-1"
        self.event_id = "evt-1"
        self.event_type = "acquisition.request"

    def SerializeToString(self):
        return b"original-envelope-bytes"


@pytest.mark.asyncio
async def test_original_envelope_is_persisted_before_failure_marker():
    store = FakeObjectStore()
    producer = FakeProducer(store)
    sink = kafka_failure_sink(producer, store)
    failure = Failure(
        code="transport_failed",
        reason="source timeout",
        topic=TOPIC_DLQ,
        source_id="SRC-1",
        task_id="TASK-1",
    )

    ack = await sink(failure, Envelope())

    assert ack.topic == TOPIC_DLQ
    assert len(store.objects) == 2
    assert len(producer.records) == 1
    marker = producer.records[0][1]
    assert marker["tenant_id"] == "tenant-a"
    assert marker["original_event_id"] == "evt-1"
    assert marker["payload_size"] == len(b"original-envelope-bytes")
    assert marker["payload_ref"].startswith("s3://knowledge-raw/raw/tenant-a/")
    assert producer.records[0][2].startswith("DLQ-")


@pytest.mark.asyncio
async def test_sink_refuses_tenantless_failures_without_writing_or_publishing():
    store = FakeObjectStore()
    producer = FakeProducer(store)
    sink = kafka_failure_sink(producer, store)
    with pytest.raises(RuntimeError, match="tenant_id"):
        await sink(
            Failure(code="transport_failed", reason="timeout", topic=TOPIC_DLQ),
            Envelope(tenant_id=""),
        )
    assert store.objects == {}
    assert producer.records == []
