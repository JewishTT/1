"""Feature 024 T020 -- durable quarantine.

Uses a fake object store, so these are hermetic. The behaviours that matter are
the ones the platform could not do before: a record quarantined before a restart
must still be replayable after it, because the constitution forbids auto-deleting
rejected candidates.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from events.dlq import DLQRecord, QuarantineStore  # noqa: E402
from events.dlq_durable import (  # noqa: E402
    RAW_BUCKET,
    DurableQuarantineStore,
    ObjectStoreSink,
)


class FakeS3:
    def __init__(self, store: "FakeObjectStore") -> None:
        self._store = store

    async def delete_object(self, *, Bucket: str, Key: str) -> None:
        self._store.objects.pop(f"{Bucket}/{Key}", None)


class FakeObjectStore:
    """Enough of ObjectStore for the sink: content-addressed put + read + exists."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put_raw(self, body: bytes, *, tenant_id: str, meta=None):
        import hashlib

        digest = hashlib.sha256(body).hexdigest()
        key = f"raw/{tenant_id}/{digest}"
        self.objects[f"{RAW_BUCKET}/{key}"] = body
        return type(
            "Ref",
            (),
            {"sha256": digest, "uri": key, "size": len(body), "tenant_prefix": tenant_id, "year_month": ""},
        )()

    async def _put(self, bucket: str, key: str, body: bytes) -> None:
        self.objects[f"{bucket}/{key}"] = body

    async def exists(self, key: str) -> bool:
        return f"{RAW_BUCKET}/{key}" in self.objects

    async def read_range(self, *, bucket: str, key: str, offset: int = 0, length=None) -> bytes:
        return self.objects.get(f"{bucket}/{key}", b"")

    def _s3(self) -> FakeS3:
        return FakeS3(self)


def record(reason="parser.oversized", payload=b'{"a":1}', topic="interpretation") -> DLQRecord:
    return DLQRecord(reason=reason, payload=payload, topic=topic)


def test_payload_is_persisted_and_readable_back():
    store = FakeObjectStore()
    sink = ObjectStoreSink(store=store)
    q = DurableQuarantineStore(sink)
    rid = q.quarantine(record(payload=b"real-bytes"))

    assert store.objects, "nothing was written to the object store"
    assert q.replay(rid) == b"real-bytes"


def test_record_survives_a_restart():
    """The defect this fixes: quarantine lived only in a process-local dict, so a
    restart lost every rejected record. A fresh store over the same sink must still
    replay it."""
    store = FakeObjectStore()
    sink = ObjectStoreSink(store=store)
    rid = DurableQuarantineStore(sink).quarantine(record(payload=b"pre-restart"))

    after_restart = DurableQuarantineStore(ObjectStoreSink(store=store))
    assert after_restart.replay(rid) == b"pre-restart"
    assert after_restart.get(rid) is not None


def test_metadata_records_reason_topic_and_fingerprint():
    store = FakeObjectStore()
    q = DurableQuarantineStore(ObjectStoreSink(store=store))
    rid = q.quarantine(record(reason="policy.uncertain", topic="acquisition"))

    meta_key = f"{RAW_BUCKET}/dlq/index/{rid}.json"
    meta = json.loads(store.objects[meta_key])
    assert meta["reason"] == "policy.uncertain"
    assert meta["topic"] == "acquisition"
    assert meta["preserved"] is True
    assert meta["fingerprint"] == DLQRecord(reason="parser.oversized", payload=b'{"a":1}', topic="interpretation").fingerprint()


def test_quarantine_is_idempotent_across_restart():
    """Same payload, same fingerprint -> same record id, not a second copy."""
    store = FakeObjectStore()
    first = DurableQuarantineStore(ObjectStoreSink(store=store))
    rid1 = first.quarantine(record(payload=b"dup"))

    second = DurableQuarantineStore(ObjectStoreSink(store=store))
    rid2 = second.quarantine(record(payload=b"dup"))
    assert rid1 == rid2


def test_memory_is_still_authoritative_when_present():
    """A fresh read hits memory and does not pay for a round trip."""
    store = FakeObjectStore()
    q = DurableQuarantineStore(ObjectStoreSink(store=store))
    rid = q.quarantine(record(payload=b"x"))
    assert q.get(rid).payload == b"x"
    assert q.replay(rid) == b"x"


def test_missing_record_is_none_not_an_exception():
    q = DurableQuarantineStore(ObjectStoreSink(store=FakeObjectStore()))
    assert q.get("DLQ-nope") is None
    assert q.replay("DLQ-nope") is None


def test_purged_record_is_gone_from_memory():
    store = FakeObjectStore()
    q = DurableQuarantineStore(ObjectStoreSink(store=store))
    rid = q.quarantine(record())
    assert q.purge(rid) is True
    assert q.get(rid) is None


def test_plain_store_is_unchanged_without_a_sink():
    """Backwards compatibility: routes/quarantine.py constructs QuarantineStore()
    with no sink and must behave exactly as before."""
    q = QuarantineStore()
    rid = q.quarantine(record(payload=b"in-memory"))
    assert q.replay(rid) == b"in-memory"
    assert len(q.list()) == 1
    assert q.purge(rid) is True
    assert q.get(rid) is None


def test_sink_put_returns_the_record_id():
    store = FakeObjectStore()
    rid = ObjectStoreSink(store=store).put(record(payload=b"y"))
    assert rid.startswith("DLQ-")