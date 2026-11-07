"""HTTP contract for the crypto transaction fabric.

Uses a NOOP plan so the route, vault unlock, approval gate and ledger are
exercised without an RPC. The point is that no HTTP body can skip the digest
approval, not that a no-op is interesting on its own.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from specops.cryptotx.config import clear_config_cache


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("COGNITIVE_AUTH_MODE", "development")
    monkeypatch.setenv("COGNITIVE_AUTH_ALLOW_DEV_HEADERS", "true")
    monkeypatch.setenv("CRYPTOTX_DATA_DIR", str(tmp_path / "cryptotx"))
    monkeypatch.setenv("CRYPTOTX_SCRYPT_N", "4096")
    monkeypatch.setenv("CRYPTOTX_APPROVAL_SECRET", "s" * 32)
    clear_config_cache()
    yield
    clear_config_cache()


def _client() -> TestClient:
    from api.main import app

    return TestClient(app, headers={"x-tenant-id": "t", "x-user-id": "analyst"})


def _plan() -> dict:
    return {
        "plan_id": "plan-api-test",
        "name": "noop",
        "network": "testnet",
        "nodes": [
            {
                "node_id": "noop",
                "kind": "noop",
                "chain": "ethereum",
                "network": "testnet",
                "wallet_id": None,
                "asset": "",
                "amount": "0",
                "params": {},
            }
        ],
        "edges": [],
    }


def test_vault_plan_approval_and_run_surface(tmp_path):
    client = _client()
    password = "correct horse battery"

    status = client.get("/api/v1/specops/cryptotx/status")
    assert status.status_code == 200, status.text
    assert status.json()["readiness"]["approval_configured"] is True

    created = client.post(
        "/api/v1/specops/cryptotx/vault",
        json={"password": password, "words": 12},
    )
    assert created.status_code == 200, created.text
    assert created.json()["recovery_phrase"]
    duplicate = client.post(
        "/api/v1/specops/cryptotx/vault",
        json={"password": password, "words": 12},
    )
    assert duplicate.status_code == 409

    wallet = client.post(
        "/api/v1/specops/cryptotx/wallets",
        json={
            "password": password,
            "chain": "ethereum",
            "network": "testnet",
            "label": "api",
        },
    )
    assert wallet.status_code == 200, wallet.text
    assert wallet.json()["address"].startswith("0x")

    plan = client.post("/api/v1/specops/cryptotx/plans", json={"plan": _plan()})
    assert plan.status_code == 200, plan.text
    digest = plan.json()["digest"]

    minted = client.post(
        "/api/v1/specops/cryptotx/approvals",
        json={"plan_id": "plan-api-test", "ttl_s": 600},
    )
    assert minted.status_code == 200, minted.text
    token = minted.json()["token"]
    assert minted.json()["digest"] == digest

    denied = client.post(
        "/api/v1/specops/cryptotx/plans/plan-api-test/runs",
        json={"password": password, "dry_run": False},
    )
    assert denied.status_code == 409
    assert denied.json()["detail"]["error"] == "ApprovalRequired"

    dry = client.post(
        "/api/v1/specops/cryptotx/plans/plan-api-test/runs",
        json={"password": password, "dry_run": True},
    )
    assert dry.status_code == 200, dry.text
    assert dry.json()["state"] == "completed"
    assert dry.json()["node_results"]["noop"]["state"] == "succeeded"

    live = client.post(
        "/api/v1/specops/cryptotx/plans/plan-api-test/runs",
        json={"password": password, "dry_run": False, "approval_token": token},
    )
    assert live.status_code == 200, live.text
    assert live.json()["state"] == "completed"

    runs = client.get("/api/v1/specops/cryptotx/runs")
    assert runs.status_code == 200
    assert len(runs.json()["runs"]) == 2

    audit = client.get("/api/v1/specops/cryptotx/audit")
    actions = [event["action"] for event in audit.json()["events"]]
    assert "wallet_created" in actions
    assert "approval_minted" in actions
    assert "run_finished" in actions
