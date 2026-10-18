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

    def test_event_id_is_derived_not_random(self) -> None:
        """WP-C T044: two builds of the same envelope carry the same id.

        **This assertion is inverted, and the previous one was wrong.**

        It read ``assert env1.event_id != env2.event_id`` — that is, it asserted the
        *defect*. The default was ``str(uuid4())``, so redelivery produced a new
        logical event for every producer that did not override it, while every
        consumer in the platform dedups on ``event_id``. The test made that behaviour
        look intentional and therefore unfixable.

        The default is now derived from the event's own content. A clock stays out of
        the material, so a replay reproduces the address even though ``produced_at``
        differs — which is the whole point.
        """
        env1 = build_envelope(
            event_type="x", event_version="1", producer="t", producer_version="1", payload=b""
        )
        env2 = build_envelope(
            event_type="x", event_version="1", producer="t", producer_version="1", payload=b""
        )
        assert env1.event_id == env2.event_id
        assert env1.event_id.startswith("evt-")
        assert len(env1.event_id) == len("evt-") + 32

    def test_a_different_payload_is_a_different_event(self) -> None:
        """Derivation must still separate genuinely different events."""
        base = dict(
            event_type="x", event_version="1", producer="t", producer_version="1"
        )
        one = build_envelope(**base, payload=b"a")
        two = build_envelope(**base, payload=b"b")
        assert one.event_id != two.event_id

    def test_subject_kind_separates_events_that_differ_only_in_subject(self) -> None:
        """An observation-scoped event must not collide with an entity-scoped one.

        The material records *which* id it carries rather than inferring it from
        whichever field happens to be non-empty. A rule that treats "no observation
        id" and "no entity id" as the same case is exactly how two unrelated events
        end up sharing an address.
        """
        base = dict(
            event_type="x", event_version="1", producer="t", producer_version="1", payload=b""
        )
        observation_scoped = build_envelope(**base, observation_id="OBS-1")
        entity_scoped = build_envelope(**base, entity_id="ENT-1")
        assert observation_scoped.event_id != entity_scoped.event_id

    def test_an_explicit_event_id_is_still_honoured(self) -> None:
        """The gate legitimately mints one from §11's six components."""
        env = build_envelope(
            event_type="x",
            event_version="1",
            producer="t",
            producer_version="1",
            payload=b"",
            event_id="evt-" + "a" * 32,
        )
        assert env.event_id == "evt-" + "a" * 32

    def test_correlation_and_causation_lineage(self) -> None:
        build_envelope(
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

    def test_v2_fabric_fields_roundtrip(self) -> None:
        """T103: envelopes carry tenant/source/work/region routing fields."""
        env = build_envelope(
            event_type="acquisition.outcome",
            event_version="2.0",
            producer="worker-http",
            producer_version="0.4.0",
            payload=b'{"raw_ref": "s3://..._placeholder"}',
            tenant_id="TENANT-42",
            source_id="SRC-7",
            work_id="W-FABRIC-1",
            region_id="eu-west",
        )
        assert env.tenant_id == "TENANT-42"
        assert env.source_id == "SRC-7"
        assert env.work_id == "W-FABRIC-1"
        assert env.region_id == "eu-west"

        raw = env.SerializeToString()
        decoded = EventEnvelope()
        decoded.ParseFromString(raw)
        assert decoded.tenant_id == "TENANT-42"
        assert decoded.region_id == "eu-west"

    def test_v2_extra_fields_default_empty(self) -> None:
        """Backward-compatible: v1-style call sites keep empty v2 fields."""
        env = build_envelope(
            event_type="observation.created",
            event_version="1.0",
            producer="worker-http",
            producer_version="0.3.0",
            payload=b"",
        )
        assert env.tenant_id == ""
        assert env.source_id == ""
        assert env.work_id == ""
        assert env.region_id == ""