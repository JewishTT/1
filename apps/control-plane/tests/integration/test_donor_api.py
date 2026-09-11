"""API integration test: correlations + review endpoints (T020/T021, FR-004/FR-006)."""

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
class TestDonorPatternApi:
    def test_correlations_exposed_without_merge(self, client: TestClient) -> None:
        resp = client.get("/api/v1/entities/ENT-2001/correlations")
        assert resp.status_code == 200
        body = resp.json()
        edges = body["correlations"]
        assert edges and edges[0]["kind"] == "possible_match"
        assert "auto_merge" not in edges[0]

    def test_review_recorded_as_provenance(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/entities/ENT-2001/review",
            json={"decision": "ACCEPT", "reasoning": "confirmed by analyst"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["event"] == "review.recorded"
        review = body["review"]
        assert review["decision"] == "ACCEPT"
        assert review["provenance"]["event_id"]

    def test_reviews_listed_per_target(self, client: TestClient) -> None:
        client.post("/api/v1/entities/ENT-2001/review", json={"decision": "UNCERTAIN"})
        resp = client.get("/api/v1/entities/ENT-2001/reviews")
        assert resp.status_code == 200
        reviews = resp.json()["reviews"]
        assert reviews and reviews[0]["target_id"] == "ENT-2001"

    def test_connector_register_and_recon_plan(self, client: TestClient) -> None:
        reg = client.post(
            "/api/v1/connectors/register",
            json={"name": "web-smoke", "source_types": ["HTTP"]},
        )
        assert reg.status_code == 200
        assert reg.json()["connector"]["status"] == "REGISTERED"

        activated = client.post("/api/v1/connectors/web-smoke/activate")
        assert activated.status_code == 200
        assert activated.json()["connector"]["status"] == "ACTIVE"

        plan = client.post(
            "/api/v1/connectors/web-smoke/recon-plans",
            json={"investigation_id": "INV-1", "strategy": {"depth": 1}},
        )
        assert plan.status_code == 200
        assert plan.json()["plan"]["status"] == "PLANNED"