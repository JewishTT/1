"""Integration of the donor CorrelationGraph into collective resolution (spec 003).

Verifies CorrelationService.export_graph() yields a valid D3 node-link payload +
Mermaid rendering for the webapp GraphPanel contract, while never merging
candidates (I-2).
"""

from __future__ import annotations

import json

from resolution.collective import CorrelationService
from resolution.resolver import ResolvedPair


def _pairs() -> list[ResolvedPair]:
    return [
        ResolvedPair(
            candidate_a="CAND-1",
            candidate_b="CAND-2",
            raw_pair_score=0.8,
            collective_score=0.85,
            reasons=["name_prefix"],
            strategies={"name"},
        ),
        ResolvedPair(
            candidate_a="CAND-2",
            candidate_b="CAND-3",
            raw_pair_score=0.6,
            collective_score=0.7,
            reasons=["email_domain"],
            strategies={"email"},
        ),
    ]


def test_export_graph_returns_node_link_and_mermaid() -> None:
    service = CorrelationService()
    service.create_edges(_pairs())
    exported = service.export_graph()

    assert "summary" in exported
    node_link = exported["node_link"]
    assert isinstance(node_link["nodes"], list) and len(node_link["nodes"]) == 3
    assert isinstance(node_link["links"], list) and len(node_link["links"]) == 2

    candidates = {n["value"] for n in node_link["nodes"]}
    assert candidates == {"CAND-1", "CAND-2", "CAND-3"}
    assert all(n["type"] == "candidate" for n in node_link["nodes"])

    json.dumps(node_link)  # serialisable for the webapp GraphPanel contract
    mermaid = exported["mermaid"]
    assert mermaid.startswith("graph TD")
    assert mermaid.count("-->") == 2


def test_export_graph_lists_observations_per_node() -> None:
    service = CorrelationService()
    service.create_edges(_pairs())
    nodes = service.export_graph()["node_link"]["nodes"]
    for node in nodes:
        assert node["observations"], "each node should carry its edge provenance"


def test_export_graph_reports_temporal_conflicts_when_requested() -> None:
    """spec 004: with conflict_days set, the summary carries a temporal scan."""
    service = CorrelationService()
    service.create_edges(_pairs())
    exported = service.export_graph(
        conflict_days=30,
        observed_dates={"ev-1": ["2024-05-10", "2024-09-20"]},
        ordering_edges=[{"type": "event_followed_by", "src": "ev-2", "dst": "ev-1"}],
    )
    conflicts = exported["conflicts"]
    assert "ev-1" in conflicts["events"]  # spread contradiction detected
    assert conflicts["orderings"] == []


def test_export_graph_without_conflicts_is_backwards_compatible() -> None:
    service = CorrelationService()
    service.create_edges(_pairs())
    exported = service.export_graph()
    assert "conflicts" not in exported