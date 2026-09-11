"""Dead-letter / quarantine handlers (T065, FR-023, US3).

Preserves rejected candidates (malformed payloads, repeated failures, poison
messages) in a quarantine store; supports replay and re-evaluation. Quarantine
preservation is the guarantee: nothing is dropped silently — every rejected
candidate stays recoverable (SC-007).
"""

from __future__ import annotations

import base64
import hashlib
import uuid
from dataclasses import dataclass, field


@dataclass
class DLQRecord:
    record_id: str = field(default_factory=lambda: "DLQ-" + uuid.uuid4().hex[:12])
    reason: str = ""
    payload: bytes = b""
    topic: str = ""
    partition: int = 0
    preserved: bool = True

    def fingerprint(self) -> str:
        digest = hashlib.sha256(self.payload).hexdigest()
        return base64.b64encode(self.payload).decode()[:12] + ":" + digest[:12]

    def to_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "reason": self.reason,
            "topic": self.topic,
            "partition": self.partition,
            "preserved": self.preserved,
            "fingerprint": self.fingerprint(),
        }


class QuarantineStore:
    """Preserves rejected candidates for replay/re-evaluation."""

    def __init__(self, sink=None) -> None:
        """sink: optional durable copy (e.g., MinIO prefix) — production adapter."""
        self._records: dict[str, DLQRecord] = {}
        self._by_fingerprint: dict[str, str] = {}
        self.sink = sink

    def quarantine(self, record: DLQRecord) -> str:
        # Idempotent preserve (I-11): dedupe by payload fingerprint so a
        # re-rejected identical message returns the original record.
        existing = self._by_fingerprint.get(record.fingerprint())
        if existing is not None:
            return existing
        self._records[record.record_id] = record
        self._by_fingerprint[record.fingerprint()] = record.record_id
        if self.sink is not None:
            self.sink.put(record)
        return record.record_id

    def get(self, record_id: str) -> DLQRecord | None:
        return self._records.get(record_id)

    def list(self, topic: str | None = None) -> list[dict]:
        records = [r for r in self._records.values() if topic is None or r.topic == topic]
        return [r.to_dict() for r in sorted(records, key=lambda r: r.record_id)]

    def replay(self, record_id: str) -> bytes | None:
        record = self._records.get(record_id)
        if record is None:
            return None
        # Replay hands the preserved payload back to the pipeline unchanged.
        return record.payload

    def purge(self, record_id: str) -> bool:
        record = self._records.pop(record_id, None)
        if record is not None:
            self._by_fingerprint.pop(record.fingerprint(), None)
        return record is not None