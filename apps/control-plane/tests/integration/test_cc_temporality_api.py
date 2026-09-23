"""API integration test: POST /entities/{id}/cc-temporality (CC-TEMPORALITY v1).

Hermetic: L0 pull is monkeypatched — no CC index, no network.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from fastapi.testclient import TestClient

import services.cc_temporality as cc_service
from api.main import app
from zero.cc_capture import RawCapture


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _patch_pull(monkeypatch: pytest.MonkeyPatch, captures: list[RawCapture]) -> None:
    monkeypatch.setattr(cc_service, "pull_capture_index", lambda *a, **k: captures)


@pytest.mark.integration
class TestCcTemporalityApi:
    def test_domain_entity_full_payload(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        created = client.post(
            "/api/v1/entities",
            json={"canonical_identity": {"domain": "example.com"}},
        ).json()["entity"]
        entity_id = created["entity_id"]

        _patch_pull(
            monkeypatch,
            [
                RawCapture(
                    url="https://example.com/a",
                    timestamp="20231012030104",
                    digest="sha256:a1",
                    status=200,
                    mime="text/html",
                    length=1024,
                    collection="CC-MAIN-2023-40",
                ),
                RawCapture(
                    url="https://example.com/b",
                    timestamp="20231014000000",
                    digest="sha256:b2",
                    status=200,
                    mime="text/html",
                    length=2048,
                    collection="CC-MAIN-2023-40",
                ),
            ],
        )
        resp = client.post(f"/api/v1/entities/{entity_id}/cc-temporality")
        assert resp.status_code == 200
        body = resp.json()
        assert body["entity_id"] == entity_id
        assert body["plan"]["kind"] == "domain"
        assert body["plan"]["surt_prefix"] == "http://com,example,"
        assert len(body["captures"]) == 2
        assert body["series"] == [
            {"t": "2023-10-12", "count": 1},
            {"t": "2023-10-14", "count": 1},
        ]
        assert body["metrics"]["events_per_day"] > 0
        assert body["notes"] == []

    def test_missing_captures_reported_honestly(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        created = client.post(
            "/api/v1/entities",
            json={"canonical_identity": {"domain": "ghost.example"}},
        ).json()["entity"]
        _patch_pull(monkeypatch, [])
        resp = client.post(f"/api/v1/entities/{created['entity_id']}/cc-temporality")
        assert resp.status_code == 200
        body = resp.json()
        assert body["captures"] == []
        assert body["series"] == []
        assert any("insufficient data" in n for n in body["notes"])

    def test_unknown_entity_404(self, client: TestClient) -> None:
        resp = client.post("/api/v1/entities/ENT-NOPE/cc-temporality")
        assert resp.status_code == 404
