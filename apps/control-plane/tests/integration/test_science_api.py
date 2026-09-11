"""API integration: science fabric routes (US1–US7 via /api/science).

Exercises the mounted ledger end-to-end: register a claim with provenance,
then the review/robustness surface used by the webapp (T138–T141). The
robustness list endpoint feeds the "Robustness context" panel and must expose
reports recorded by POST /api/science/robustness (FR-011).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from claims.registry import set_observations
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture(autouse=True)
def _seed_observations() -> None:
    set_observations({f"OBS-{i}": f"sha256:{i}" for i in range(1, 11)})


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.integration
class TestScienceApi:
    def test_register_claim_then_list(self, client: TestClient) -> None:
        resp = client.post(
            "/api/science/claims",
            json={
                "project_id": "P-science",
                "statement": "High-degree street hubs slow recovery",
                "distribution": {
                    "states": ["high", "low"],
                    "labels": ["high recovery", "low recovery"],
                    "probs": [0.7, 0.3],
                    "method": "binomial-kde@1.0",
                },
                "provenance": [
                    {
                        "link_id": "L1",
                        "observation_id": "OBS-1",
                        "raw_sha256": "sha256:1",
                        "direction": "supports",
                        "weight": 1.0,
                    }
                ],
            },
        )
        assert resp.status_code == 200
        claim_id = resp.json()["claim_id"]
        assert claim_id.startswith("SC-")

        listed = client.get("/api/science/claims")
        assert listed.status_code == 200
        ids = [claim["claim_id"] for claim in listed.json()["claims"]]
        assert claim_id in ids

    def test_robustness_list_starts_empty_then_reflects_report(self, client: TestClient) -> None:
        assert client.get("/api/science/robustness").json() == {"reports": []}

        claim_resp = client.post(
            "/api/science/claims",
            json={
                "project_id": "P-science",
                "statement": "Edge density predicts cascades",
                "distribution": {
                    "states": ["true", "false"],
                    "labels": ["prediction holds", "prediction fails"],
                    "probs": [0.6, 0.4],
                    "method": "logit@1.0",
                },
                "provenance": [
                    {
                        "link_id": "L1",
                        "observation_id": "OBS-1",
                        "raw_sha256": "sha256:1",
                        "direction": "supports",
                        "weight": 1.0,
                    }
                ],
            },
        )
        claim_id = claim_resp.json()["claim_id"]

        evidence = [
            {
                "link_id": f"E{i}",
                "observation_id": f"OBS-{i}",
                "raw_sha256": f"sha256:{i}",
                "direction": "supports",
                "weight": 1.0,
            }
            for i in range(10)
        ]
        report = client.post(
            "/api/science/robustness",
            json={"claim_id": claim_id, "evidence": evidence, "label_flip": (0.6,), "seed": 11},
        )
        assert report.status_code == 200
        body = report.json()
        assert body["report_id"].startswith("RB-")
        assert set(body["flip_rates"]) == {"missing", "flip", "biased_subsample"}

        listed = client.get("/api/science/robustness").json()
        assert [r["report_id"] for r in listed["reports"]] == [body["report_id"]]
        assert listed["reports"][0]["claim_ref"] == claim_id

        got = client.get(f"/api/science/robustness/{body['report_id']}")
        assert got.status_code == 200
        assert got.json()["claim_ref"] == claim_id

    def test_robustness_needs_evidence(self, client: TestClient) -> None:
        resp = client.post("/api/science/robustness", json={"claim_id": "CL-missing", "evidence": []})
        assert resp.status_code == 422
        assert resp.json()["detail"]["error"] == "no_evidence"

    def test_experiment_registry_reproduce_flow(self, client: TestClient) -> None:
        run = client.post(
            "/api/science/experiments",
            json={
                "input_refs": ["OBS-1", "OBS-2"],
                "output_refs": ["CL-1"],
                "seed": 7,
                "pipeline_version": "0.1.0",
                "tolerance": 1e-6,
            },
        )
        assert run.status_code == 200
        run_id = run.json()["run_id"]
        assert run_id.startswith("EX-")

        listed = client.get("/api/science/experiments").json()
        assert run_id in [r["run_id"] for r in listed["runs"]]

        repro = client.post("/api/science/experiments/reproduce", json={"run_id": run_id})
        assert repro.status_code == 200
        assert repro.json()["reproduced"] is True

        missing = client.post("/api/science/experiments/reproduce", json={"run_id": "EX-unknown"})
        assert missing.status_code == 404