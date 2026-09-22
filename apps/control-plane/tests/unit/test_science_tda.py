"""API tests: /api/science/invariant — Takens + VR persistence (011, FR-009)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
_ROOT = Path(__file__).resolve().parents[3]
for _rel in ("science", "interpretation", "bulk-ingestion"):
    sys.path.insert(0, str(_ROOT / _rel))

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _invariant(client: TestClient, series: list[float], **overrides):
    body = {"entity_id": "ENT-2001", "series": series}
    body.update(overrides)
    return client.post("/api/science/invariant", json=body)


class TestTDAInvariant:
    def test_periodic_series_yields_diagram(self, client: TestClient) -> None:
        import math

        series = [math.sin(2 * math.pi * i / 40) for i in range(96)]
        resp = _invariant(client, series, lag=2, embed_dim=2, max_dim=1)
        assert resp.status_code == 200
        body = resp.json()
        assert body["provider"] == "vr-z2-science"
        assert body["structural_only"] is True  # I-6
        assert body["series_len"] == 96
        diagrams = body["diagrams"]
        assert "0" in diagrams  # connected components pop upfront
        assert body["digest"] and len(body["digest"]) == 64
        assert body["stats"] and "0" in body["stats"]

    def test_scope_exceeded_is_422(self, client: TestClient) -> None:
        # 156-point VR exceeds the 8192-simplex budget -> honest 422, not a lie
        import math

        series = [math.sin(2 * math.pi * i / 40) for i in range(156)]
        resp = _invariant(client, series, lag=1, embed_dim=2, max_dim=1)
        assert resp.status_code == 422
        assert resp.json()["detail"]["error"] == "topology_scope_exceeded"

    def test_empty_series_is_honest(self, client: TestClient) -> None:
        resp = _invariant(client, [])
        assert resp.status_code == 200
        body = resp.json()
        assert body["diagrams"] == {}
        assert len(body["embedding"]["points"]) == 0

    def test_drift_unchanged(self, client: TestClient) -> None:
        series = [float(i % 5) for i in range(40)]
        first = _invariant(client, series, lag=1, embed_dim=2, max_dim=1)
        assert first.status_code == 200
        second = _invariant(
            client, series, lag=1, embed_dim=2, max_dim=1,
            prev_diagram=first.json()["diagrams"],
        )
        assert second.status_code == 200
        assert second.json()["drift"]["changed"] is False
        assert second.json()["drift"]["delta_max_persistence"] == 0.0

    def test_drift_changed(self, client: TestClient) -> None:
        import math

        series = [math.sin(2 * math.pi * i / 20) for i in range(40)]
        first = _invariant(client, series, lag=1, embed_dim=2, max_dim=1)
        assert first.status_code == 200
        faster = [math.sin(2 * math.pi * i / 10) for i in range(40)]
        second = _invariant(
            client, faster, lag=1, embed_dim=2, max_dim=1,
            prev_diagram=first.json()["diagrams"],
        )
        assert second.status_code == 200
        assert second.json()["drift"]["changed"] is True