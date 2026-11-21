"""Canonical Redpanda bootstrap configuration contracts."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

APP_SHARED = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_SHARED))

from config.kafka import kafka_bootstrap_servers


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
