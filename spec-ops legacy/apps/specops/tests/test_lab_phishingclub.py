"""Adapter configuration proofs for the Phishing Club service."""

from __future__ import annotations

from specops.lab import phishingclub


def test_default_service_is_loopback_https(monkeypatch):
    monkeypatch.delenv("PHISHINGCLUB_URL", raising=False)
    monkeypatch.delenv("PHISHINGCLUB_CONSOLE_URL", raising=False)
    monkeypatch.delenv("PHISHINGCLUB_VERIFY_TLS", raising=False)

    cfg = phishingclub.config()

    assert cfg["base_url"] == "https://127.0.0.1:8002"
    assert cfg["console_url"] == "https://127.0.0.1:8002"
    assert cfg["verify_tls"] is False
    assert cfg["configured"] is True


def test_remote_service_keeps_tls_verification(monkeypatch):
    monkeypatch.setenv("PHISHINGCLUB_URL", "https://phishing.example")
    monkeypatch.delenv("PHISHINGCLUB_VERIFY_TLS", raising=False)

    assert phishingclub.config()["verify_tls"] is True


def test_tls_verification_can_be_overridden(monkeypatch):
    monkeypatch.setenv("PHISHINGCLUB_URL", "https://127.0.0.1:8002")
    monkeypatch.setenv("PHISHINGCLUB_VERIFY_TLS", "true")

    assert phishingclub.config()["verify_tls"] is True

    monkeypatch.setenv("PHISHINGCLUB_VERIFY_TLS", "off")

    assert phishingclub.config()["verify_tls"] is False
