"""API integration: SpecOps tool catalog + entity graph projections."""

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
class TestToolsApi:
    def test_list_tools(self, client: TestClient) -> None:
        resp = client.get("/api/v1/tools")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == "default-tenant"
        tools = body["tools"]
        assert tools
        ids = [t["tool_id"] for t in tools]
        assert ids == sorted(ids)
        assert any(t["tool_id"] == "whois" for t in tools)

    def test_list_tools_filtered_by_entity_type(self, client: TestClient) -> None:
        resp = client.get("/api/v1/tools", params={"entity_type": "PHONE"})
        assert resp.status_code == 200
        tools = resp.json()["tools"]
        assert tools
        assert all("PHONE" in t["entity_types"] for t in tools)

    def test_list_tools_unknown_entity_type_is_empty(self, client: TestClient) -> None:
        resp = client.get("/api/v1/tools", params={"entity_type": "CRYPTO_ADDRESS"})
        assert resp.status_code == 200
        assert resp.json()["tools"] == []

    def test_enqueue_happy_path(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/tools/whois/enqueue",
            json={"entity_type": "DOMAIN", "entity_value": "example.com"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["event"] == "specops.tool_requested"
        run = body["run"]
        assert run["tool_id"] == "whois"
        assert run["entity_type"] == "DOMAIN"
        assert run["entity_value"] == "example.com"
        assert run["entity_id"] is None
        assert run["status"] == "QUEUED"
        assert run["command"] == []

    def test_enqueue_unknown_tool_404(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/tools/no-such-tool/enqueue",
            json={"entity_type": "DOMAIN", "entity_value": "example.com"},
        )
        assert resp.status_code == 404

    def test_enqueue_wrong_entity_type_422(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/tools/whois/enqueue",
            json={"entity_type": "EMAIL", "entity_value": "a@b.com"},
        )
        assert resp.status_code == 422

    def test_entities_list_contains_seed_catalog_node(self, client: TestClient) -> None:
        resp = client.get("/api/v1/entities")
        assert resp.status_code == 200
        body = resp.json()
        ids = [e["entity_id"] for e in body["entities"]]
        assert "ENT-2001" in ids
        seed = next(e for e in body["entities"] if e["entity_id"] == "ENT-2001")
        assert seed["canonical_identity"] == {"account": "Yard"}
        assert seed["entity_type"] == "USERNAME"
        assert seed["label"] == "Yard"

    def test_graph_returns_seed_node_and_correlation_edge(self, client: TestClient) -> None:
        """Feature 024: the graph is served from PostgreSQL, not a fixture.

        This test previously asserted the hardcoded demo (`ENT-2001 "Yard"`, one
        `possible_match` edge). Asserting that fixture meant the endpoint could never
        show a real investigation -- a green test over demo data. It now asserts the
        contract that matters: the endpoint answers 200, and whatever it reports
        declares where it came from, so a caller can tell real data from a degraded
        fallback.
        """
        resp = client.get("/api/v1/entities/graph")
        assert resp.status_code == 200
        body = resp.json()

        assert "nodes" in body and "edges" in body
        assert body["source"] in ("postgres", "fixture")
        assert body["source"] == "postgres" or body.get("degraded_reason")

        for node in body["nodes"]:
            assert node["id"]
            assert node["label"] is not None
            assert "entity_type" in node
        for edge in body["edges"]:
            assert edge["id"]
            assert edge["source"] != edge["target"], "a self-edge is never a relation"
            assert "kind" in edge and "label" in edge
        known = {n["id"] for n in body["nodes"]}
        for edge in body["edges"]:
            assert edge["source"] in known, "edge endpoint is not in the node set"
            assert edge["target"] in known, "edge endpoint is not in the node set"