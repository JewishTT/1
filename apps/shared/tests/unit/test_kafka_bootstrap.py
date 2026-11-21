"""Canonical Redpanda bootstrap configuration contracts."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

APP_SHARED = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_SHARED))

from config.kafka import kafka_bootstrap_servers
from events.kafka import IdempotentProducer


def test_canonical_bootstrap_normalizes_broker_list(monkeypatch) -> None:
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda-a:19092, redpanda-b:19092")
    assert kafka_bootstrap_servers() == "redpanda-a:19092,redpanda-b:19092"


def test_unset_bootstrap_uses_local_redpanda_default(monkeypatch) -> None:
    monkeypatch.delenv("KAFKA_BOOTSTRAP_SERVERS", raising=False)
    assert kafka_bootstrap_servers() == "localhost:19092"


def test_empty_bootstrap_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", " , ")
    with pytest.raises(RuntimeError, match="KAFKA_BOOTSTRAP_SERVERS"):
        kafka_bootstrap_servers()


def test_redpanda_producer_uses_durable_batched_defaults() -> None:
    config = IdempotentProducer._producer_config("redpanda:19092")
    assert config["bootstrap.servers"] == "redpanda:19092"
    assert config["enable.idempotence"] is True
    assert config["acks"] == "all"
    assert config["compression.type"] == "zstd"
    assert config["linger.ms"] == 5
    assert config["batch.size"] == 65_536
    assert config["queue.buffering.max.kbytes"] == 16_384


def test_compose_has_redpanda_only_and_no_legacy_kafka_profile() -> None:
    repository_root = APP_SHARED.parents[1]
    compose = (repository_root / "apps" / "deploy" / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    assert "redpandadata/redpanda@sha256:" in compose
    assert "confluentinc/cp-kafka" not in compose
    assert "cp-schema-registry" not in compose
    assert "legacy-kafka" not in compose
