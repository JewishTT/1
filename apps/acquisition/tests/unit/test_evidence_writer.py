"""Raw-first relational persistence contracts for Layer 0."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from evidence_writer import EvidenceWriteError, PostgresAcquisitionEvidenceWriter


class _AsyncContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class _Mappings:
    def __init__(self, row):
        self.row = row

    def first(self):
        return self.row


class _Result:
    def __init__(self, row=None):
        self.row = row

    def mappings(self):
        return _Mappings(self.row)


class _Session:
    def __init__(self):
        self.captures = {}
        self.observations = {}

    def begin(self):
        return _AsyncContext()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, statement, params):
        sql = str(statement).lower()
        p = dict(params)
        if "insert into captures" in sql:
            if p["capture_id"] not in self.captures and not any(
                row["tenant_id"] == p["tenant_id"]
                and row["capture_fingerprint"] == p["capture_fingerprint"]
                for row in self.captures.values()
            ):
                self.captures[p["capture_id"]] = p
            return _Result()
        if "select capture_id, capture_fingerprint, content_digest" in sql:
            for row in self.captures.values():
                if (
                    row["tenant_id"] == p["tenant_id"]
                    and (
                        row["capture_id"] == p["capture_id"]
                        or row["capture_fingerprint"] == p["capture_fingerprint"]
                    )
                ):
                    return _Result({
                        "capture_id": row["capture_id"],
                        "capture_fingerprint": row["capture_fingerprint"],
                        "content_digest": row["content_digest"],
                    })
            return _Result()
        if "insert into observations" in sql:
            p["provenance"] = json.loads(p["provenance"])
            self.observations.setdefault(p["observation_id"], p)
            return _Result()
        if "select tenant_id, task_id, raw_ref, content_hash, provenance" in sql:
            return _Result(self.observations.get(p["observation_id"]))
        raise AssertionError(f"unexpected SQL in evidence writer test: {sql}")


def _evidence():
    body = b'{"message":"public metadata"}'
    digest = hashlib.sha256(body).hexdigest()
    tenant = "tenant-034"
    capture_id = "CAP-" + "a" * 32
    source_id = "SRC-" + "b" * 32
    capture = SimpleNamespace(
        capture_id=capture_id,
        tenant_id=tenant,
        source_id=source_id,
        source_family="academic",
        target_uri="https://api.crossref.org/works",
        locator="GET https://api.crossref.org/works?query=Public",
        content_digest=digest,
        content_length=len(body),
        media_type="application/json",
        fetched_at=datetime(2026, 10, 25, tzinfo=UTC),
        time_basis=SimpleNamespace(value="fetch"),
        transport="http",
        ingest_batch_id="unbatched",
        ingest_attempt=1,
        recorded_by="test",
        capture_fingerprint=hashlib.sha256(b"capture-fingerprint").hexdigest(),
    )
    raw_ref = f"s3://knowledge/raw/{tenant}/202610/{digest}"
    observation = {
        "observation_id": "OBS-" + digest[:32],
        "tenant_id": tenant,
        "investigation_id": "INV-" + "c" * 32,
        "source_id": source_id,
        "work_id": "TSK-" + "d" * 32,
        "capture_id": capture_id,
        "locator": "$",
        "record_digest": digest,
        "content_type": "application/json",
        "raw_ref": raw_ref,
        "parser_hint": "structured_fields",
        "record_metadata": {"target_uri": capture.target_uri, "task_id": "TSK-" + "d" * 32},
        "provenance": {"collector": "source-connector"},
    }
    return capture, observation, raw_ref


@pytest.mark.asyncio
async def test_capture_and_observation_are_committed_idempotently():
    session = _Session()
    writer = PostgresAcquisitionEvidenceWriter(lambda: session)
    capture, observation, raw_ref = _evidence()

    first = await writer.persist(capture=capture, observation=observation, raw_ref=raw_ref)
    second = await writer.persist(capture=capture, observation=observation, raw_ref=raw_ref)

    assert first == second
    assert len(session.captures) == 1
    assert len(session.observations) == 1
    stored = session.observations[observation["observation_id"]]
    assert stored["raw_ref"] == raw_ref
    assert stored["content_hash"] == observation["record_digest"]
    assert stored["provenance"]["capture_id"] == capture.capture_id
    assert stored["provenance"]["parser_hint"] == "structured_fields"


@pytest.mark.asyncio
async def test_tenant_or_digest_mismatch_fails_before_relational_write():
    session = _Session()
    writer = PostgresAcquisitionEvidenceWriter(lambda: session)
    capture, observation, raw_ref = _evidence()
    observation = {**observation, "tenant_id": "different-tenant"}

    with pytest.raises(EvidenceWriteError, match="tenant_id differ"):
        await writer.persist(capture=capture, observation=observation, raw_ref=raw_ref)
    assert session.captures == {}
    assert session.observations == {}
