"""Canonical Redpanda bootstrap resolver for Kafka-protocol clients."""
from __future__ import annotations

import os

DEFAULT_KAFKA_BOOTSTRAP_SERVERS = "localhost:19092"


def kafka_bootstrap_servers() -> str:
    """Return normalized Redpanda broker endpoints; reject empty overrides."""
    raw = os.environ.get("KAFKA_BOOTSTRAP_SERVERS") or DEFAULT_KAFKA_BOOTSTRAP_SERVERS
    brokers = [item.strip() for item in raw.split(",") if item.strip()]
    if not brokers:
        raise RuntimeError(
            "KAFKA_BOOTSTRAP_SERVERS (Redpanda) must contain at least one broker address"
        )
    return ",".join(brokers)


def redpanda_producer_config(
    bootstrap_servers: str, *, compression: str = "zstd"
) -> dict[str, object]:
    """Shared bounded producer defaults; preserve idempotent, durable publication."""
    if not str(bootstrap_servers).strip():
        raise ValueError("Redpanda bootstrap servers are required")
    if compression not in {"zstd", "snappy", "lz4", "gzip", "none"}:
        raise ValueError("unsupported librdkafka compression codec")
    return {
        "bootstrap.servers": bootstrap_servers,
        "enable.idempotence": True,
        "acks": "all",
        "compression.type": compression,
        "linger.ms": 5,
        "batch.size": 65_536,
        "queue.buffering.max.kbytes": 16_384,
        "delivery.timeout.ms": 120_000,
        "max.in.flight.requests.per.connection": 5,
        "socket.keepalive.enable": True,
    }


def redpanda_consumer_config(
    *, bootstrap_servers: str, group_id: str, auto_offset_reset: str = "earliest"
) -> dict[str, object]:
    """Bound consumer memory and make offset ownership explicit.

    Offsets are committed by the durable handler after its database/object-store effect;
    these settings never auto-advance or discard records under backpressure.
    """
    if not str(bootstrap_servers).strip() or not str(group_id).strip():
        raise ValueError("Redpanda bootstrap servers and consumer group are required")
    if auto_offset_reset not in {"earliest", "latest", "error"}:
        raise ValueError("unsupported auto.offset.reset policy")
    return {
        "bootstrap.servers": bootstrap_servers,
        "group.id": group_id,
        "auto.offset.reset": auto_offset_reset,
        "enable.auto.commit": False,
        "enable.auto.offset.store": False,
        "max.poll.records": 200,
        "max.poll.interval.ms": 300_000,
        "session.timeout.ms": 45_000,
        "heartbeat.interval.ms": 3_000,
        "partition.assignment.strategy": "cooperative-sticky",
        "fetch.wait.max.ms": 50,
        "fetch.min.bytes": 1_024,
        "fetch.max.bytes": 8_388_608,
        "max.partition.fetch.bytes": 1_048_576,
        "queued.max.messages.kbytes": 16_384,
    }
