"""One broker-address convention shared by every Kafka-compatible client."""
from __future__ import annotations

import os

DEFAULT_KAFKA_BOOTSTRAP_SERVERS = "localhost:19092"
LEGACY_BROKER_ENV = "COGNITIVE_KAFKA_BROKERS"


def kafka_bootstrap_servers() -> str:
    """Resolve canonical configuration before the legacy compatibility alias."""
    raw = (
        os.environ.get("KAFKA_BOOTSTRAP_SERVERS")
        or os.environ.get(LEGACY_BROKER_ENV)
        or DEFAULT_KAFKA_BOOTSTRAP_SERVERS
    )
    brokers = [item.strip() for item in raw.split(",") if item.strip()]
    if not brokers:
        raise RuntimeError(
            "KAFKA_BOOTSTRAP_SERVERS must contain at least one broker address"
        )
    return ",".join(brokers)
