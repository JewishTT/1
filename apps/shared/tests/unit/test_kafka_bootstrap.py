"""Shared broker resolution tests for Redpanda producer/consumer configuration."""
from __future__ import annotations

import sys
from pathlib import Path

APP_SHARED = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_SHARED))

from config.kafka import kafka_bootstrap_servers


def test_canonical_kafka_setting_wins_over_legacy_alias(monkeypatch) -> None:
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda-a:19092, redpanda-b:19092")
    monkeypatch.setenv("COGNITIVE_KAFKA_BROKERS", "old-kafka:9092")
    assert kafka_bootstrap_servers() == "redpanda-a:19092,redpanda-b:19092"


def test_legacy_alias_remains_a_compatibility_fallback(monkeypatch) -> None:
    monkeypatch.delenv("KAFKA_BOOTSTRAP_SERVERS", raising=False)
    monkeypatch.setenv("COGNITIVE_KAFKA_BROKERS", "legacy:19092")
    assert kafka_bootstrap_servers() == "legacy:19092"


def test_empty_broker_list_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", " , ")
    monkeypatch.delenv("COGNITIVE_KAFKA_BROKERS", raising=False)
    try:
        kafka_bootstrap_servers()
    except RuntimeError as exc:
        assert "KAFKA_BOOTSTRAP_SERVERS" in str(exc)
    else:
        raise AssertionError("empty broker configuration must be rejected")
