"""Integration test: entity + finding lineage drill-down resolves to evidence (T049).

Confirms the US1-proven lineage (FR-032) is exposed through the entity and
finding overview services: findings drill to observations and raw sources, and
the chain never breaks evidence anchoring to immutable observations (I-1).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from services.catalog import Catalog, EntityRecord, FindingRecord

OBSERVATIONS = {
    "OBS-1001": {"observation_id": "OBS-1001", "uri": "http://fixtures.local/report.html", "content_hash": "sha256:aa"},
    "OBS-1002": {"observation_id": "OBS-1002", "uri": "http://fixtures.local/ledger.html", "content_hash": "sha256:bb"},
}


@pytest.fixture
def catalog() -> Catalog:
    catalog = Catalog(observations=OBSERVATIONS)
    catalog.put_entity(
        EntityRecord(
            entity_id="ENT-2001",
            canonical_identity={"account": "Yard"},
            versions=[
                {"version": 1, "identity": {"account": "Yard"}, "first_seen": "2026-01-01T00:00:00Z"},
                {"version": 2, "identity": {"account": "Yard", "bank": "LHT"}, "first_seen": "2026-01-03T00:00:00Z"},
            ],
            aliases=["Yard", "yard-account"],
            relationships=[{"type": "candidate_of", "target": "ENT-2002"}],
            supporting_assertions=["ASR-9001"],
            evidence_ids=["OBS-1001"],
            observations=["OBS-1001"],
            structural_signals=[{"signal": "tda_loop", "feature_id": "FEAT-42", "persistence": 2.3}],
        )
    )
    catalog.put_finding(
        FindingRecord(
            finding_id="FND-5001",
            why_detected="loop + velocity spike",
            structural_evidence=[{"feature_id": "FEAT-42", "kind": "tda_loop"}],
            semantic_evidence=[{"kind": "named_entity", "value": "Yard"}],
            supporting_graph_region={"subgraph": "Yard cluster"},
            supporting_assertions=["ASR-9001"],
            observations=["OBS-1001", "OBS-1002"],
            sources=["http://fixtures.local/report.html", "http://fixtures.local/ledger.html"],
        )
    )
    return catalog


@pytest.mark.integration
class TestLineage:
    def test_entity_view_exposes_versions_aliases_and_signals(self, catalog: Catalog) -> None:
        view = catalog.entity("ENT-2001")
        assert view is not None
        assert view["current_state"]["version"] == 2
        assert len(view["historical_versions"]) == 2
        assert "Yard" in view["aliases"]
        assert view["structural_signals"][0]["persistence"] == 2.3

    def test_entity_evidence_anchors_to_observations(self, catalog: Catalog) -> None:
        view = catalog.entity("ENT-2001")
        assert all(e["immutable"] for e in view["evidence"])
        assert view["timeline"][0]["uri"] == "http://fixtures.local/report.html"

    def test_finding_view_links_observations_and_sources(self, catalog: Catalog) -> None:
        view = catalog.finding("FND-5001")
        assert view is not None
        assert len(view["observations"]) == 2
        assert all(o["immutable"] for o in view["observations"])
        assert view["evidence_resolves"] is True
        assert view["supporting_graph_region"]["subgraph"] == "Yard cluster"

    def test_lineage_chain_covers_full_path(self, catalog: Catalog) -> None:
        chain = catalog.lineage("FND-5001")
        kinds = [step["kind"] for step in chain]
        assert kinds[0] == "finding"
        assert "feature" in kinds
        assert "assertion" in kinds
        assert "observation" in kinds
        assert "source" in kinds
        # FR-032: the walk terminates at a raw source, never a dangling ref.
        assert any("fixtures.local" in step["label"] for step in chain[-2:])