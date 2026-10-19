"""Tests for FR-029 seed security enforcement on investigation creation (T072).

The three rejection cases are pure request validation and need no infrastructure.
The acceptance case persists an investigation, so it needs PostgreSQL and is
guarded the same way every other integration suite in this repository is: skip
when the store is unreachable, never fail with a raw connection error. A test
that reports "defect" when the only problem is an absent database is a false
signal, and this repository already fixed that pattern elsewhere
(``test_infra_connectivity.py``, ``test_postgres_context_store.py``,
``test_frontier_loop.py``).
"""

import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def _pg_reachable() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 5432), timeout=2):
            return True
    except OSError:
        return False


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

    @pytest.mark.skipif(not _pg_reachable(), reason="postgres unavailable")
    def test_default_seed_still_accepted(self) -> None:
        resp = client.post(
            "/api/v1/investigations",
            json={"name": "t", "seeds": [], "objective": {"type": "osint"}, "scope": {}},
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "RUNNING"
