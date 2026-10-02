"""Durable quarantine sink (Feature 024 T020, FR-016).

``QuarantineStore`` takes an optional ``sink`` and has had exactly one since it was
written: none. Every quarantined payload lived in a process-local dict, so a restart
lost every rejected record -- and the constitution is explicit that rejected
candidates are never auto-deleted and must remain replayable.

This module supplies the missing adapter over the existing ``ObjectStore``. The
payload goes in as an immutable content-addressed raw object, which is the same
treatment evidence gets (Principle I), and the index metadata goes in a small
sidecar. Nothing here re-implements storage: ``storage.s3.ObjectStore`` already does
content addressing, dedup and ref URIs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from events.dlq import DLQRecord, QuarantineStore

RAW_BUCKET = "knowledge-raw"
META_PREFIX = "dlq/index"


class QuarantineSink(Protocol):
    """Durable home for quarantined records."""

    def put(self, record: DLQRecord) -> str: ...
    def load(self, record_id: str) -> DLQRecord | None: ...
    def index(self) -> list[dict]: ...
    def drop(self, record_id: str) -> bool: ...


@dataclass
class ObjectStoreSink:
    """Persist quarantined payloads and an index into the object store.

    Two objects per record:
      * ``{raw bucket}/raw/{prefix}/{sha256}`` -- the payload, immutable,
        content-addressed, exactly the treatment evidence gets (Principle I).
      * ``{raw bucket}/dlq/index/{record_id}.json`` -- reason, topic, partition,
        fingerprint, and the payload's sha256.

    The index is the fragile half: it is a plain key per record rather than a
    listing, so enumeration needs record ids the caller already knows. That is a
    deliberate trade for not adding a catalog service, and it is named here so it
    is not mistaken for something stronger.
    """

    store: Any
    tenant_id: str = "dlq"

    def _meta_key(self, record_id: str) -> str:
        return f"{META_PREFIX}/{record_id}.json"

    def put(self, record: DLQRecord) -> str:
        import anyio

        async def _write() -> None:
            ref = await self.store.put_raw(
                record.payload,
                tenant_id=self.tenant_id,
                meta={"dlq_record_id": record.record_id, "topic": record.topic},
            )
            body = json.dumps(
                {
                    "record_id": record.record_id,
                    "reason": record.reason,
                    "topic": record.topic,
                    "partition": record.partition,
                    "preserved": record.preserved,
                    "fingerprint": record.fingerprint(),
                    "payload_sha256": ref.sha256,
                    "payload_ref": ref.uri,
                    "payload_size": ref.size,
                },
                sort_keys=True,
            ).encode()
            await self.store._put(RAW_BUCKET, self._meta_key(record.record_id), body)

        anyio.run(_write)
        return record.record_id

    def load(self, record_id: str) -> DLQRecord | None:
        import anyio

        async def _read_meta() -> bytes | None:
            key = self._meta_key(record_id)
            if not await self.store.exists(key):
                return None
            return await self.store.read_range(bucket=RAW_BUCKET, key=key)

        raw = anyio.run(_read_meta)
        if raw is None:
            return None
        meta = json.loads(raw.decode())

        async def _read_payload() -> bytes:
            return await self.store.read_range(bucket=RAW_BUCKET, key=meta["payload_ref"])

        payload = anyio.run(_read_payload)
        return DLQRecord(
            record_id=meta["record_id"],
            reason=meta["reason"],
            payload=payload,
            topic=meta["topic"],
            partition=meta.get("partition", 0),
            preserved=meta.get("preserved", True),
        )

    def index(self) -> list[dict]:
        # Enumeration needs a list API the object store does not expose here;
        # callers hydrate from record ids they already hold.
        return []

    def drop(self, record_id: str) -> bool:
        """Remove the index entry so the record stops resolving.

        The payload object is deliberately left behind: it is immutable and
        content-addressed, and Principle I forbids destroying evidence. Dropping a
        quarantine entry is a policy decision, not an erasure.
        """
        import anyio

        async def _rm() -> bool:
            client = self.store._s3()
            await client.delete_object(Bucket=RAW_BUCKET, Key=self._meta_key(record_id))
            return True

        try:
            return anyio.run(_rm)
        except Exception:
            return False


class DurableQuarantineStore(QuarantineStore):
    """Quarantine store that reads through to a durable sink.

    Writes go to both memory and sink. Reads fall back to the sink so a record
    quarantined before a restart is still replayable afterwards -- which is the
    whole point of preserving rejected candidates.
    """

    def __init__(self, sink: QuarantineSink) -> None:
        super().__init__(sink=sink)

    def get(self, record_id: str) -> DLQRecord | None:
        found = super().get(record_id)
        if found is not None:
            return found
        if self.sink is None:
            return None
        return self.sink.load(record_id)

    def replay(self, record_id: str) -> bytes | None:
        record = self.get(record_id)
        return None if record is None else record.payload

    def purge(self, record_id: str) -> bool:
        removed = super().purge(record_id)
        if self.sink is not None:
            self.sink.drop(record_id)
        return removed


__all__ = [
    "DurableQuarantineStore",
    "RAW_BUCKET",
    "META_PREFIX",
    "ObjectStoreSink",
    "QuarantineSink",
]