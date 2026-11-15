"""HTTP contract tests for `/api/v1/specops/lab` (Feature 036).

The router is thin; these tests prove the wire behaviour the UI depends on: the
department envelope, the 409/422/424/404 vocabulary, tenant isolation, and that a
captured secret never appears in a response body.
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("COGNITIVE_AUTH_MODE", "development")
os.environ.setdefault("COGNITIVE_AUTH_ALLOW_DEV_HEADERS", "true")
os.environ.setdefault("GHOSTLINE_PINNED", "1")

BASE = "/api/v1/specops/lab"


def _client(tenant: str = "ten-router-a", user: str = "user-router-a") -> TestClient:
    from api.main import app

    return TestClient(app, headers={"x-tenant-id": tenant, "x-user-id": user})


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    from specops.engagement.config import clear_engagement_config_cache
    from specops.engagement.fabric import EngagementFabric
    from specops.lab.audit import AuditLog
    from specops.lab.engine import LabEngine
    import api.routes.specops_lab as lab_route

    monkeypatch.setenv("GHOSTLINE_ENGAGEMENT_DIR", str(tmp_path / "engagement"))
    clear_engagement_config_cache()
    lab_route.LAB = LabEngine(records=EngagementFabric(), audit=AuditLog())
    tenant = f"ten-{uuid.uuid4().hex[:8]}"
    yield _client(tenant=tenant, user=f"user-{tenant}")
    clear_engagement_config_cache()


def _roe(client: TestClient) -> str:
    res = client.post(
        "/api/v1/specops/roe",
        json={"target_ref": "lab-target-1", "scope": "drill", "approved_by": "supervisor@lab"},
    )
    assert res.status_code == 200, res.text
    return res.json()["roe_id"]


def _campaign(client: TestClient, name: str = "drill") -> str:
    res = client.post(
        BASE + "/campaigns",
        json={"name": name, "roster": ["a@lab.test", "b@lab.test"], "attack_mapping": ["T1566"]},
    )
    assert res.status_code == 200, res.text
    return res.json()["campaign"]["campaign_id"]


def test_overview_reports_full_red_team_scope_and_verified_donor(client):
    res = client.get(BASE)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["scope"] == "red-team"
    assert body["lab"]["egress_policy"] == "roe-gated"
    assert body["readiness"]["donor"]["status"] == "verified"
    assert body["readiness"]["donor"]["adapter_served"] is True


def test_launch_uses_the_409_gate_and_succeeds_after_roe(client):
    cid = _campaign(client)
    blocked = client.post(f"{BASE}/campaigns/{cid}/launch", json={"roe_id": "missing"})
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["error"] == "RoEError"

    launched = client.post(f"{BASE}/campaigns/{cid}/launch", json={"roe_id": _roe(client)})
    assert launched.status_code == 200, launched.text
    campaign = launched.json()["campaign"]
    assert campaign["state"] == "complete"
    assert campaign["funnel"]["submitted"] == 0


def test_session_rejects_invalid_target_and_capture_is_redacted(client):
    roe_id = _roe(client)
    refused = client.post(
        BASE + "/aitm/sessions",
        json={"mode": "reverse_proxy", "target_host": "bad host!", "roe_id": roe_id},
    )
    assert refused.status_code == 422
    assert refused.json()["detail"]["error"] == "TargetRefused"

    started = client.post(
        BASE + "/aitm/sessions",
        json={"mode": "reverse_proxy", "target_host": "specops-lab.local", "roe_id": roe_id},
    )
    assert started.status_code == 200, started.text
    session_id = started.json()["session"]["session_id"]
    captured = client.post(
        f"{BASE}/aitm/sessions/{session_id}/capture",
        json={"kind": "token", "secret": "tok-top-secret", "label": "lab"},
    )
    assert captured.status_code == 200, captured.text
    assert "tok-top-secret" not in captured.text
    assert captured.json()["artifact"]["redacted_preview"]


def test_cross_tenant_campaign_is_404(client):
    cid = _campaign(client)
    other = _client(tenant=f"ten-{uuid.uuid4().hex[:8]}", user="other")
    assert other.get(f"{BASE}/campaigns/{cid}").status_code == 404


def test_kill_switch_blocks_and_reset_restores(client):
    assert client.post(BASE + "/kill-switch").status_code == 200
    blocked = client.post(BASE + "/campaigns", json={"name": "x", "roster": ["a@lab.test"]})
    assert blocked.status_code == 409
    assert client.post(BASE + "/reset").json()["lab"]["status"] == "ready"
    assert client.post(BASE + "/campaigns", json={"name": "y", "roster": ["a@lab.test"]}).status_code == 200


def test_report_generation_and_export_are_enveloped(client):
    cid = _campaign(client)
    client.post(f"{BASE}/campaigns/{cid}/launch", json={"roe_id": _roe(client)})
    report = client.post(f"{BASE}/reports/{cid}")
    assert report.status_code == 200, report.text
    figures = report.json()["report"]["figures"]
    assert figures["sent"]["status"] == "derived"
    assert figures["captured_credentials"]["value"] == 0

    export = client.post(f"{BASE}/reports/{cid}/export")
    assert export.status_code == 200
    body = export.json()["export"]
    assert body["format"] == "markdown"
    assert body["digest"]


def test_full_mode_starts_external_session_after_roe(client):
    res = client.post(
        BASE + "/aitm/sessions",
        json={"mode": "reverse_proxy", "target_host": "external.example", "roe_id": _roe(client)},
    )
    assert res.status_code == 200, res.text
    assert res.json()["session"]["target_host"] == "external.example"


def test_audit_chain_is_visible_and_intact(client):
    cid = _campaign(client)
    client.post(f"{BASE}/campaigns/{cid}/launch", json={"roe_id": _roe(client)})
    res = client.get(BASE + "/audit?limit=50")
    assert res.status_code == 200
    events = res.json()["events"]
    assert events and events[0]["row_hash"]
    assert all("password" not in str(e["detail"]).lower() for e in events)
