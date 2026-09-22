"""API tests: /api/v1/network — projection-plane network/TDA surface (T041-T060)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
_ROOT = Path(__file__).resolve().parents[3]
# projection/shared provide `graph`/`metrics`; science must stay AHEAD so its
# `tda` package (persistence/phodms) is not shadowed by projection/tda.
for _rel in ("projection", "interpretation", "bulk-ingestion", "shared"):
    sys.path.insert(0, str(_ROOT / _rel))
sys.path.insert(0, str(_ROOT / "science"))

import math

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


TRIANGLE = [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}, {"source": "c", "target": "a"}]


class TestNetworkMeasures:
    def test_triangle_measures(self, client: TestClient) -> None:
        resp = client.post("/api/v1/network/measures", json={"edges": TRIANGLE})
        assert resp.status_code == 200
        body = resp.json()
        assert body["n_nodes"] == 3
        assert body["n_edges"] == 3
        assert body["avg_clustering"] == 1.0  # each node closes the triangle
        assert body["structural_only"] is True  # I-6
        assert body["degree_centrality"] == {"a": 2, "b": 2, "c": 2}

    def test_empty_edges_is_honest(self, client: TestClient) -> None:
        resp = client.post("/api/v1/network/measures", json={"edges": []})
        assert resp.status_code == 200
        body = resp.json()
        assert body["n_nodes"] == 0
        assert body["avg_degree"] == 0.0


class TestCommunities:
    def test_two_triangles_split(self, client: TestClient) -> None:
        edges = TRIANGLE + [
            {"source": "d", "target": "e"},
            {"source": "e", "target": "f"},
            {"source": "f", "target": "d"},
        ]
        resp = client.post("/api/v1/network/communities", json={"edges": edges})
        assert resp.status_code == 200
        body = resp.json()
        assert body["community_count"] >= 2
        assert body["modularity_q"] > 0.0
        assert body["structural_only"] is True


class TestHypergraph:
    def test_observation_hypergraph(self, client: TestClient) -> None:
        observations = {
            "obs-1": ["a", "b", "c"],
            "obs-2": ["a", "b", "d"],
            "obs-3": ["x", "y"],
        }
        resp = client.post("/api/v1/network/hypergraph", json={"observations": observations})
        assert resp.status_code == 200
        body = resp.json()
        assert body["num_edges"] == 3
        assert body["num_nodes"] == 6
        assert "node_degrees" in body and body["node_degrees"]["a"] == 2

    def test_empty_observations_refused(self, client: TestClient) -> None:
        resp = client.post("/api/v1/network/hypergraph", json={"observations": {}})
        assert resp.status_code == 422


class TestTemporal:
    def test_journey_and_reachability(self, client: TestClient) -> None:
        edges = [
            {"source": "a", "target": "b", "t": 1.0},
            {"source": "b", "target": "c", "t": 2.0},
            {"source": "a", "target": "c", "t": 5.0},
        ]
        resp = client.post(
            "/api/v1/network/temporal",
            json={"edges": edges, "source": "a", "target": "c"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["reachable_from"] == ["b", "c"]
        assert body["distance_matrix"]["a"]["c"] == 2.0  # via relay, not direct
        # Greedy earliest-arrival journey: a->b@1 -> b->c@2
        journey = body["journey"]
        assert journey[0] == [{ "source": "a", "target": "b", "t": 1.0, "edge_id": "" },
                               { "source": "b", "target": "c", "t": 2.0, "edge_id": "" }]
        assert body["motifs"]["relay"] >= 1


class TestDiagramFeatures:
    def _sine(self, n: int = 96) -> list[float]:
        return [math.sin(2 * math.pi * i / 40) for i in range(n)]

    def test_feature_payload_and_drift(self, client: TestClient) -> None:
        series = self._sine()
        first = client.post(
            "/api/v1/network/diagram-features",
            json={"entity_id": "ENT-2001", "series": series, "lag": 2, "embed_dim": 2, "max_dim": 1},
        )
        assert first.status_code == 200
        body = first.json()
        assert body["provider"] == "vr-z2-science+features"
        assert body["structural_only"] is True
        assert "0" in body["features"]["dimensions"]
        assert len(body["features_digest"]) == 64

        # Same window again -> zero-cost drift, hash unchanged (I-12).
        second = client.post(
            "/api/v1/network/diagram-features",
            json={
                "entity_id": "ENT-2001",
                "series": series,
                "lag": 2,
                "embed_dim": 2,
                "max_dim": 1,
                "prev_diagrams": body["diagrams"],
            },
        )
        assert second.status_code == 200
        drift = second.json()["drift"]
        assert any(entry["changed"] is False and entry["value"] == 0.0 for entry in drift.values())

    def test_short_series_deferred(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/network/diagram-features",
            json={"entity_id": "ENT-2001", "series": [1.0, 2.0]},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["error"] == "scope_refused"


class TestPhodms:
    def test_betti_zero_surface(self, client: TestClient) -> None:
        clouds = [
            [[0.0, 0.0], [4.0, 4.0]],
            [[0.0, 0.0], [4.0, 0.0]],
            [[0.2, 0.2], [3.8, 0.2]],
        ]
        resp = client.post(
            "/api/v1/network/phodms",
            json={"clouds": clouds, "thresholds": [1.0, 3.0, 5.0]},
        )
        assert resp.status_code == 200
        body = resp.json()
        surface = body["betti_zero_surface"]
        assert len(surface) == 3  # per threshold
        assert all(len(slice_) == 3 for slice_ in surface)
        assert body["structural_only"] is True
        assert body["rank_invariant"]["verdict"] in {"valid", "in_margin", "outside_window"}

    def test_out_of_bounds_refused(self, client: TestClient) -> None:
        clouds = [[[0.0, 0.0] for _ in range(9)] for _ in range(3)]
        resp = client.post("/api/v1/network/phodms", json={"clouds": clouds})
        assert resp.status_code == 422
        assert resp.json()["detail"]["error"] == "scope_refused"