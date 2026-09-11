"""Contract tests for EventEnvelope (T017, FR-023, R-7).

event_id is idempotency key. All fields present; payload carries refs, never blobs (I-5).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apps" / "shared"))

import pytest

from events.event_envelope_pb2 import EventEnvelope
from events.kafka import build_envelope, now_rfc3339


@pytest.mark.contract
class TestEventEnvelopeContract:
    def test_envelope_has_all_required_fields(self) -> None:
        env = build_envelope(
            event_type="observation.created",
            event_version="1.0",
            producer="test-producer",
            producer_version="0.1.0",
            payload=b"",
            investigation_id="INV-001",
            correlation_id="COR-001",
            causation_id="CAU-001",
            observation_id="OBS-001",
            entity_id="ENT-001",
            event_id="EVT-001",
        )
        assert env.event_id == "EVT-001"
        assert env.event_type == "observation.created"
        assert env.event_version == "1.0"
        assert env.investigation_id == "INV-001"
        assert env.correlation_id == "COR-001"
        assert env.causation_id == "CAU-001"
        assert env.producer == "test-producer"
        assert env.producer_version == "0.1.0"
        assert env.observation_id == "OBS-001"
        assert env.entity_id == "ENT-001"
        assert env.produced_at  # RFC3339

    def test_envelope_serialization_roundtrip(self) -> None:
        env = build_envelope(
            event_type="candidate.created",
            event_version="2.1",
            producer="worker-http",
            producer_version="0.3.0",
            payload=b"\x0a\x04test",
        )
        raw = env.SerializeToString()
        decoded = EventEnvelope()
        decoded.ParseFromString(raw)
        assert decoded.event_type == "candidate.created"
        assert decoded.event_id == env.event_id

    def test_payload_is_bytes_not_blob(self) -> None:
        """I-5: Kafka carries refs, never raw blobs. Payload is raw bytes (references)."""
        ref_payload = b'{"observation_ref": "s3://knowledge/raw/tenant/202609/abc123"}'
        env = build_envelope(
            event_type="observation.created",
            event_version="1.0",
            producer="test",
            producer_version="0.1",
            payload=ref_payload,
        )
        assert len(env.payload) == len(ref_payload)
        assert b"s3://" in env.payload

    def test_produced_at_is_rfc3339(self) -> None:
        ts = now_rfc3339()
        assert "T" in ts
        assert "Z" in ts

    def test_event_id_is_default_uuid(self) -> None:
        env1 = build_envelope(
            event_type="x", event_version="1", producer="t", producer_version="1", payload=b""
        )
        env2 = build_envelope(
            event_type="x", event_version="1", producer="t", producer_version="1", payload=b""
        )
        assert env1.event_id != env2.event_id

    def test_correlation_and_causation_lineage(self) -> None:
        root = build_envelope(
            event_type="investigation.started",
            event_version="1",
            producer="api",
            producer_version="1",
            payload=b"",
            event_id="root",
        )
        child = build_envelope(
            event_type="acquisition.assigned",
            event_version="1",
            producer="dispatcher",
            producer_version="1",
            payload=b"",
            correlation_id="root",
            causation_id="root",
        )
        assert child.correlation_id == "root"
        assert child.causation_id == "root"