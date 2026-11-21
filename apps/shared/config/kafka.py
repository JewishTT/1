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
