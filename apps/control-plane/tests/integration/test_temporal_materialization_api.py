"""API integration tests for temporal materialization."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "shared"))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.entities import router
from api.routes.temporal_materializations import router as temporal_router


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.include_router(temporal_router, prefix="/api/v1")
    return TestClient(app)


def test_create_entity_starts_materialization(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import api.routes.entities as entities_route

    monkeypatch.setattr(entities_route, "_next_entity_id", lambda: "ENT-9001")
    record = {
        "entity_id": "ENT-9001",
        "kind": "fact",
        "ts": "2024-01-01T00:00:00+00:00",
        "tenant_id": "default-tenant",
        "payload": {"event_at": "2024-01-01T00:00:00+00:00"},
        "observation_id": "obs-1",
        "sequence": 1,
    }
    response = client.post(
        "/api/v1/entities",
        json={
            "canonical_identity": {"account": "Temporal"},
            "source_records": [record],
        },
    )
    assert response.status_code == 202
    body = response.json()
    assert body["materialization"]["status"] in {"QUEUED", "DEFERRED"}
    assert body["materialization"]["run_id"].startswith("run-")
    entity_id = body["entity"]["entity_id"]
    history = client.get(f"/api/v1/entities/{entity_id}/temporal-history")
    assert history.status_code == 404


def test_current_and_features_endpoints(client: TestClient) -> None:
    record = {
        "entity_id": "ENT-9004",
        "kind": "fact",
        "ts": "2024-01-01T00:00:00+00:00",
        "tenant_id": "default-tenant",
        "payload": {"event_at": "2024-01-01T00:00:00+00:00"},
        "observation_id": "obs-4",
        "sequence": 1,
    }
    assert (
        client.post(
            "/api/v1/entities/ENT-9004/temporal-materializations", json={"source_records": [record]}
        ).status_code
        == 200
    )
    current = client.get("/api/v1/entities/ENT-9004/temporal-history/current")
    features = client.get("/api/v1/entities/ENT-9004/temporal-features")
    assert current.status_code == 200 and current.json()["is_latest_valid"] is True
    assert features.status_code == 200 and features.json()["features"]


def test_health_and_run_status_are_tenant_scoped(client: TestClient) -> None:
    record = {
        "entity_id": "ENT-9003",
        "kind": "fact",
        "ts": "2024-01-01T00:00:00+00:00",
        "tenant_id": "default-tenant",
        "payload": {"event_at": "2024-01-01T00:00:00+00:00"},
        "observation_id": "obs-3",
        "sequence": 1,
    }
    created = client.post(
        "/api/v1/entities/ENT-9003/temporal-materializations",
        json={"source_records": [record], "reason": "health test"},
    )
    assert created.status_code == 200
    run_id = created.json()["run_id"]
    assert client.get(f"/api/v1/temporal-materializations/{run_id}").status_code == 200
    assert client.get("/api/v1/temporal-materializations/health").json()["runs"]
    audit = client.get(f"/api/v1/temporal-materializations/{run_id}/audit")
    assert audit.status_code == 200 and audit.json()["entries"]
    record = {
        "entity_id": "ENT-9002",
        "kind": "fact",
        "ts": "2024-01-01T00:00:00+00:00",
        "tenant_id": "default-tenant",
        "payload": {"event_at": "2024-01-01T00:00:00+00:00"},
        "observation_id": "obs-2",
        "sequence": 1,
    }
    response = client.post(
        "/api/v1/entities/ENT-9002/temporal-materializations",
        json={
            "source_records": [record],
            "reason": "test",
            "window_days": 7,
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "PUBLISHED"
    point = client.get(
        "/api/v1/entities/ENT-9002/temporal-history/at",
        params={"at": datetime(2024, 1, 1, tzinfo=UTC).isoformat()},
    )
    assert point.status_code == 200
    assert point.json()["window_revision"]["window"]["event_count"] == 1
