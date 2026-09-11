"""Tests for FR-029 seed security enforcement on investigation creation (T072)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


@pytest.mark.integration
class TestSeedSecurity:
    @pytest.mark.parametrize(
        "payload",
        [
            {"name": "t", "seeds": ["ftp://example.com/x"]},
            {"name": "t", "seeds": ["http://example.com:21/x"]},
            {"name": "t", "seeds": ["http:///no-host"]},
        ],
    )
    def test_bad_seeds_rejected(self, payload: dict) -> None:
        payload["objective"] = {"type": "osint"}
        resp = client.post("/api/v1/investigations", json=payload)
        assert resp.status_code == 422
        assert "seed rejected" in resp.json()["detail"]

    def test_default_seed_still_accepted(self) -> None:
        resp = client.post(
            "/api/v1/investigations",
            json={"name": "t", "seeds": [], "objective": {"type": "osint"}, "scope": {}},
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "RUNNING"