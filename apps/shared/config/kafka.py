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
    }
