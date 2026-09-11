"""API integration test: resolution review endpoints (feature 005 US2)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.integration
class TestResolutionApi:
    def test_empty_queue_is_readable(self, client: TestClient) -> None:
        resp = client.get("/api/v1/investigations/INV-1/resolutions")
        assert resp.status_code == 200
        assert resp.json()["pairs"] == []

    def test_decision_records_append_only_and_reports_state(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/investigations/INV-1/resolutions/decide",
            json={
                "pair_key": "ENT-A&&ENT-B",
                "decision": "ACCEPT",
                "reasoning": "two independent sources",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["candidate_state"] == "accepted"
        assert body["event"] == "resolution.candidate_decided"
        assert body["review"]["target_type"] == "candidate"
        assert body["review"]["target_id"] == "ENT-A&&ENT-B"

        resp = client.get("/api/v1/investigations/INV-1/resolutions")
        pairs = resp.json()["pairs"]
        assert pairs and pairs[0]["pair_key"] == "ENT-A&&ENT-B"
        assert pairs[0]["decision"] == "ACCEPT"

    def test_second_decision_never_overwrites(self, client: TestClient) -> None:
        first = client.post(
            "/api/v1/investigations/INV-1/resolutions/decide",
            json={"pair_key": "ENT-X&&ENT-Y", "decision": "ACCEPT"},
        ).json()["review"]
        second = client.post(
            "/api/v1/investigations/INV-1/resolutions/decide",
            json={"pair_key": "ENT-X&&ENT-Y", "decision": "REJECT", "reasoning": "mismatch"},
        ).json()
        assert second["candidate_state"] == "rejected"
        assert second["review"]["review_id"] != first["review_id"]

    def test_candidate_review_decision_maps_distinct_ids(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/investigations/INV-1/resolutions/decide",
            json={"pair_key": "ENT-1&&ENT-2", "decision": "UNCERTAIN"},
        )
        assert resp.status_code == 200
        assert resp.json()["candidate_state"] == "open"