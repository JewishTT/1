"""Dead-letter / quarantine records.

Failure records are tenant-scoped, content-addressed, and retain the original
request envelope in immutable object storage. Metadata is safe to project into
operator views; payload bytes are never returned by list/get APIs.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DLQRecord:
    record_id: str = ""
    reason: str = ""
    payload: bytes = b""
    topic: str = ""
    partition: int = 0
    preserved: bool = True
    tenant_id: str = ""
    investigation_id: str = ""
    source_id: str = ""
    task_id: str = ""
    original_event_id: str = ""
    original_event_type: str = ""
    status: int = 0
    detail: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.record_id:
            identity = "\n".join(
                (
                    self.tenant_id,
                    self.topic,
                    self.reason,
                    self.original_event_id,
                    self.fingerprint(),
                )
            )
            self.record_id = "DLQ-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]

    def fingerprint(self) -> str:
        digest = hashlib.sha256(self.payload).hexdigest()
        return base64.b64encode(self.payload[:9]).decode("ascii")[:12] + ":" + digest[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "reason": self.reason,
            "topic": self.topic,
            "partition": self.partition,
            "preserved": self.preserved,
            "fingerprint": self.fingerprint(),
            "tenant_id": self.tenant_id,
            "investigation_id": self.investigation_id,
            "source_id": self.source_id,
            "task_id": self.task_id,
            "original_event_id": self.original_event_id,
            "original_event_type": self.original_event_type,
            "status": self.status,
            "detail": dict(self.detail),
        }


class QuarantineStore:
    """Process-local test/development store with optional durable write-through."""

    def __init__(self, sink=None) -> None:
        self._records: dict[str, DLQRecord] = {}
        self._by_fingerprint: dict[tuple[str, str, str, str, str], str] = {}
        self.sink = sink

    def quarantine(self, record: DLQRecord) -> str:
        key = (
            record.tenant_id,
            record.topic,
            record.reason,
            record.original_event_id,
            record.fingerprint(),
        )
        existing = self._by_fingerprint.get(key)
        if existing is not None:
            return existing
        # Persist before mutating memory. A sink failure must not look like success.
        if self.sink is not None:
            self.sink.put(record)
        self._records[record.record_id] = record
        self._by_fingerprint[key] = record.record_id
        return record.record_id

    def get(self, record_id: str) -> DLQRecord | None:
        return self._records.get(record_id)

    def list(self, topic: str | None = None) -> list[dict]:
        records = [r for r in self._records.values() if topic is None or r.topic == topic]
        return [r.to_dict() for r in sorted(records, key=lambda r: r.record_id)]

    def replay(self, record_id: str) -> bytes | None:
        record = self._records.get(record_id)
        return None if record is None else record.payload

    def purge(self, record_id: str) -> bool:
        record = self._records.pop(record_id, None)
        if record is not None:
            key = (
                record.tenant_id,
                record.topic,
                record.reason,
                record.original_event_id,
                record.fingerprint(),
            )
            self._by_fingerprint.pop(key, None)
        return record is not None
