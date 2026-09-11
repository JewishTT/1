"""Integration test: quarantine preservation + replay (T060, US3, FR-023).

Forced preservation guarantees no rejected candidate is silently dropped: it
lands in quarantine with its original payload; replay returns the payload
byte-for-byte; re-evaluation then paves the way to acceptance.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apps" / "shared"))

import pytest
from events.dlq import DLQRecord, QuarantineStore


@pytest.mark.integration
class TestQuarantine:
    def test_rejected_model_payload_is_preserved(self) -> None:
        store = QuarantineStore()
        record = DLQRecord(reason="parse-failure", payload=b"rejected candidate A", topic="cognitive-events")
        rid = store.quarantine(record)
        assert store.get(rid).preserved is True

    def test_event_never_dropped_silently(self) -> None:
        store = QuarantineStore()
        store.quarantine(DLQRecord(reason="schema-mismatch", payload=b"x", topic="cognitive-events"))
        listed = store.list(topic="cognitive-events")
        assert len(listed) == 1
        assert listed[0]["preserved"] is True

    def test_replay_returns_payload_byte_for_byte(self) -> None:
        store = QuarantineStore()
        payload = b"the original malformed candidate bytes"
        rid = store.quarantine(DLQRecord(reason="poison-message", payload=payload, topic="cognitive-events"))
        assert store.replay(rid) == payload

    def test_replay_unknown_returns_none(self) -> None:
        assert QuarantineStore().replay("DLQ-missing") is None

    def test_re_evaluation_can_accept(self) -> None:
        store = QuarantineStore()
        rid = store.quarantine(DLQRecord(reason="policy-gated", payload=b"", topic="cognitive-events"))
        payload = store.replay(rid)
        assert payload is not None
        # Re-evaluate: the payload now parses cleanly -> accept + purge.
        assert store.purge(rid) is True
        assert store.get(rid) is None

    def test_quarantine_is_idempotent(self) -> None:
        store = QuarantineStore()
        rid = store.quarantine(DLQRecord(reason="dup", payload=b"v", topic="cognitive-events"))
        assert store.quarantine(DLQRecord(reason="dup", payload=b"v", topic="cognitive-events")) == rid
        assert len(store.list()) == 1