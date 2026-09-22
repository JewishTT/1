"""Integration test: lifecycle envelope reaches Redpanda (T131, I-11).

Produce an `observation.created` envelope carrying the v2 routing fields
(tenant_id, source_id, work_id, region_id) into the dev Redpanda and
consume back the same record, verifying the proto roundtrip. This proves
the transport chain for the Observation Gate event emission path.

Skipped if the broker is unavailable.
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "shared"))

import pytest
from confluent_kafka import Consumer, KafkaError, Producer
from events.event_envelope_pb2 import EventEnvelope
from events.kafka import build_envelope

_BROKER = os.getenv("KAFKA_BOOTSTRAP", "localhost:19092")
_TOPIC = f"__test_obs_gate_{uuid.uuid4().hex[:8]}"
_TIMEOUT = 15.0

pytestmark = pytest.mark.integration


def _broker_available() -> bool:
    try:
        p = Producer({"bootstrap.servers": _BROKER, "socket.timeout.ms": 1000})
        p.list_topics(timeout=2)
        return True
    except Exception:
        return False


requires_broker = pytest.mark.skipif(not _broker_available(), reason="redpanda/kafka unavailable")


def _produce_envelope(env: EventEnvelope, key: str) -> None:
    p = Producer({"bootstrap.servers": _BROKER, "message.timeout.ms": 5000})
    p.produce(_TOPIC, env.SerializeToString(), key=key.encode())
    p.flush(10)


def _consume_one(group_id: str) -> EventEnvelope | None:
    c = Consumer(
        {
            "bootstrap.servers": _BROKER,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": True,
            "session.timeout.ms": 6000,
        }
    )
    c.subscribe([_TOPIC])
    deadline = time.time() + _TIMEOUT
    while time.time() < deadline:
        msg = c.poll(1.0)
        if msg is None or msg.error():
            if msg and msg.error().code() != KafkaError._PARTITION_EOF:
                pass
            continue
        env = EventEnvelope()
        env.ParseFromString(msg.value())
        c.close()
        return env
    c.close()
    return None


@requires_broker
def test_lifecycle_envelope_reaches_redpanda_with_v2_fields() -> None:
    obs_id = f"OBS-{uuid.uuid4().hex[:10]}"
    env = build_envelope(
        event_type="observation.created",
        event_version="2.0",
        producer="observation-gate",
        producer_version="0.1.0",
        payload=b"s3://know/obs/abc123",
        tenant_id="TENANT-99",
        source_id="SRC-3",
        work_id="WK-INT-1",
        region_id="us-east",
        investigation_id="INV-1",
        observation_id=obs_id,
        event_id=f"EVT-{obs_id}",
    )
    _produce_envelope(env, key=obs_id)

    got = _consume_one(f"test-obs-{obs_id}")
    assert got is not None, f"no record received within {_TIMEOUT}s on {_TOPIC}"
    assert got.event_type == "observation.created"
    assert got.observation_id == obs_id
    assert got.tenant_id == "TENANT-99"
    assert got.source_id == "SRC-3"
    assert got.work_id == "WK-INT-1"
    assert got.region_id == "us-east"
    assert got.payload == b"s3://know/obs/abc123"