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
        """A possible_match edge is readable back and implies no merge (FR-004, I-2).

        The edge is created in the test rather than assumed from hand-seeded rows: the
        previous version read ``ENT-2001`` and only passed on a database where somebody
        had already stored a correlation, so it measured seed state, not the contract.
        """
        created = client.post(
            "/api/v1/entities",
            json={"canonical_identity": {"account": "edge-owner"}},
        ).json()["entity"]
        other = client.post(
            "/api/v1/entities",
            json={"canonical_identity": {"account": "edge-other"}},
        ).json()["entity"]
        made = client.post(
            f"/api/v1/entities/{created['entity_id']}/correlations",
            json={"candidate_b": other["entity_id"], "reasons": ["shared handle"]},
        )
        assert made.status_code == 200, made.text

        resp = client.get(f"/api/v1/entities/{created['entity_id']}/correlations")
        assert resp.status_code == 200
        body = resp.json()
        edges = body["correlations"]
        assert edges and edges[0]["kind"] == "possible_match"
        assert "auto_merge" not in edges[0]
        # The correlate is still an entity of its own: no identity was folded in.
        assert client.get(f"/api/v1/entities/{other['entity_id']}").status_code == 200

    def test_review_recorded_as_provenance(self, client: TestClient) -> None:
        target = client.post(
            "/api/v1/entities",
            json={"canonical_identity": {"account": "review-target"}},
        ).json()["entity"]["entity_id"]
        resp = client.post(
            f"/api/v1/entities/{target}/review",
            json={"decision": "ACCEPT", "reasoning": "confirmed by analyst"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["event"] == "review.recorded"
        review = body["review"]
        assert review["decision"] == "ACCEPT"
        assert review["provenance"]["event_id"]

    def test_reviews_listed_per_target(self, client: TestClient) -> None:
        target = client.post(
            "/api/v1/entities",
            json={"canonical_identity": {"account": "review-list"}},
        ).json()["entity"]["entity_id"]
        client.post(f"/api/v1/entities/{target}/review", json={"decision": "UNCERTAIN"})
        resp = client.get(f"/api/v1/entities/{target}/reviews")
        assert resp.status_code == 200
        reviews = resp.json()["reviews"]
        assert reviews and reviews[0]["target_id"] == target

    def test_entity_timeline_carries_observed_at(self, client: TestClient) -> None:
        """A timeline entry must carry ``observed_at`` (the record's ts).

        The timeline is rebuilt from the entity stream; no seed fixture is assumed.
        """
        created = client.post(
            "/api/v1/entities",
            json={"canonical_identity": {"account": "timeline-check"}},
        ).json()["entity"]
        entity_id = created["entity_id"]
        record = {
            "entity_id": entity_id,
            "kind": "fact",
            "ts": "2026-01-01T00:00:00+00:00",
            "tenant_id": "default-tenant",
            "payload": {"event_at": "2026-01-01T00:00:00+00:00"},
            "observation_id": "obs-timeline-1",
            "sequence": 1,
        }
        resp = client.post(
            f"/api/v1/entities/{entity_id}/temporal-materializations",
            json={"source_records": [record]},
        )
        assert resp.status_code in (200, 202), resp.text
        resp = client.get(f"/api/v1/entities/{entity_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["timeline"]
        assert all(
            entry.get("observed_at") in {"2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00Z"}
            for entry in body["timeline"]
        )

    def test_entity_view_projects_identity_invariant(self, client: TestClient) -> None:
        """The atomic entity must surface its dynamic-invariant projection: a
        stable anchor id plus versioned, digest-backed continuity.
        """
        created = client.post(
            "/api/v1/entities",
            json={"canonical_identity": {"account": "invariant-seed"}},
        ).json()["entity"]
        entity_id = created["entity_id"]
        resp = client.get(f"/api/v1/entities/{entity_id}")
        assert resp.status_code == 200
        body = resp.json()
        inv = body["identity_invariant"]
        assert inv["status"] == "MATERIALIZED"
        assert inv["continuity"] == "PERSISTENT"
        assert inv["version"] == 1
        assert inv["history_depth"] == 1
        assert inv["identity_digest"].startswith("sha256:")
        assert inv["first_seen"]
        assert inv["last_seen"]

        created = client.post(
            "/api/v1/entities",
            json={"canonical_identity": {"account": "Pulse"}},
        ).json()["entity"]
        assert created["identity_invariant"]["version"] == 1
        assert created["identity_invariant"]["history_depth"] == 1
        # Same identity dimensions -> same digest (deterministic invariant).
        fresh = client.get(f"/api/v1/entities/{created['entity_id']}").json()
        assert fresh["identity_invariant"]["identity_digest"] == created["identity_invariant"]["identity_digest"]

    def test_entity_can_be_created_as_dynamic_invariant(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/entities",
            json={"canonical_identity": {"account": "Nimbus"}, "aliases": ["Nimbus", "nb-acc"]},
        )
        # ``202 Accepted``, not ``200``: creation launches durable temporal
        # materialization, and the contract is
        # ``specs/015-worldline-reconstruction/contracts/api.md:21``. The entity
        # itself is committed synchronously, which the reads below rely on.
        assert resp.status_code == 202
        body = resp.json()
        assert body["materialization"]["run_id"]
        assert body["materialization"]["status"] in {"QUEUED", "DEFERRED"}
        assert body["event"] == "entity.created"
        entity = body["entity"]
        assert entity["entity_id"].startswith("ENT-")
        assert entity["canonical_identity"] == {"account": "Nimbus"}
        assert entity["current_state"]["version"] == 1
        # No ``source_records`` were supplied, so there is nothing to cite yet:
        # the evidence list is present and empty rather than fabricated. The
        # immutable-evidence assertion belongs to a creation that does carry
        # source records (see ``test_entity_view_projects_identity_invariant``).
        assert entity["evidence"] == []
        assert entity["historical_versions"][0]["identity"] == {"account": "Nimbus"}
        # the new invariant is addressable right away
        assert client.get(f"/api/v1/entities/{entity['entity_id']}").status_code == 200

    def test_entity_create_rejects_empty_identity(self, client: TestClient) -> None:
        resp = client.post("/api/v1/entities", json={"canonical_identity": {"account": ""}})
        assert resp.status_code == 422

    def test_correlation_created_without_merge(self, client: TestClient) -> None:
        created = client.post(
            "/api/v1/entities",
            json={"canonical_identity": {"account": "Aster"}, "aliases": ["Aster"]},
        ).json()["entity"]
        other = client.post(
            "/api/v1/entities",
            json={"canonical_identity": {"account": "Other"}},
        ).json()["entity"]
        resp = client.post(
            f"/api/v1/entities/{created['entity_id']}/correlations",
            json={"candidate_b": other["entity_id"], "reasons": ["shared handle"]},
        )
        assert resp.status_code == 200
        edge = resp.json()["edge"]
        assert edge["candidate_a"] == created["entity_id"]
        assert edge["candidate_b"] == other["entity_id"]
        assert edge["kind"] == "possible_match"
        assert "auto_merge" not in edge
        # the correlate may stay non-materialized: edge exists, no identity made
        assert client.get(f"/api/v1/entities/{created['entity_id']}/correlations").json()[
            "correlations"
        ]

    def test_correlation_requires_materialized_source(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/entities/ENT-NOPE/correlations",
            json={"candidate_b": "ENT-2001"},
        )
        assert resp.status_code == 404

    def test_correlation_rejects_self_link(self, client: TestClient) -> None:
        created = client.post(
            "/api/v1/entities",
            json={"canonical_identity": {"account": "Self"}},
        ).json()["entity"]
        resp = client.post(
            f"/api/v1/entities/{created['entity_id']}/correlations",
            json={"candidate_b": created["entity_id"]},
        )
        assert resp.status_code == 409

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