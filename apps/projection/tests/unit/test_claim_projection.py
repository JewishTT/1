"""Admission-gated graph projection contracts."""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from domain.relation_claim import RelationClaim, RelationRoleBinding
from domain.relation_identity import RelationArityMode
from graph.abstraction import InMemoryGraphStore
from graph.claim_projection import project_admitted_claim, reconcile_claim_projection
from graph.relation_store import RelationClaimService

pytestmark = pytest.mark.unit


def _claim(*, nary: bool = False) -> RelationClaim:
    service = RelationClaimService(tenant_id="tenant-1")
    if nary:
        claim = service.build(
            relation_type="employment",
            arity_mode=RelationArityMode.NARY,
            subject_ref="person-1",
            object_ref="org-1",
            context_ref="context-1",
            role_bindings=(
                RelationRoleBinding(role="person", member_ref="person-1"),
                RelationRoleBinding(role="organization", member_ref="org-1"),
                RelationRoleBinding(role="location", member_ref="place-1"),
            ),
        )
    else:
        claim = service.build(
            relation_type="works_for",
            arity_mode=RelationArityMode.DIRECTED,
            subject_ref="person-1",
            object_ref="org-1",
            context_ref="context-1",
        )
    return replace(claim, observation_refs=("OBS-1",), assertion_refs=("ASSERT-1",))


def test_only_valid_claim_is_projected_and_replay_is_idempotent() -> None:
    graph = InMemoryGraphStore()
    claim = _claim()
    verdict = {"verdict": "VALID", "recorded_at": "2026-10-27T00:00:00+00:00"}

    first = project_admitted_claim(graph, claim, validation_record=verdict)
    second = project_admitted_claim(graph, claim, validation_record=verdict)

    assert first == second == {
        "relation_id": claim.relation_id,
        "nodes": 2,
        "edges": 1,
        "hyperedges": 0,
    }
    assert {node.node_id for node in graph.nodes()} == {"person-1", "org-1"}
    assert len(graph.edges()) == 1
    assert graph.edges()[0].edge_id == claim.relation_id


def test_non_valid_verdict_cannot_create_any_graph_state() -> None:
    graph = InMemoryGraphStore()
    claim = _claim()
    with pytest.raises(ValueError, match="VALID"):
        project_admitted_claim(
            graph, claim, validation_record={"verdict": "REJECTED", "reasons": ["bad evidence"]}
        )
    assert graph.nodes() == []
    assert graph.edges() == []


def test_nary_claim_remains_one_hyperedge_not_a_clique() -> None:
    graph = InMemoryGraphStore()
    claim = _claim(nary=True)
    result = project_admitted_claim(graph, claim, validation_record={"verdict": "valid"})
    assert result["nodes"] == 3
    assert result["edges"] == 0
    assert result["hyperedges"] == 1
    assert len(graph.edges()) == 0
    assert len(graph._hyperedges) == 1
    edge = next(iter(graph._hyperedges.values()))
    assert set(edge.members) == {"person-1", "org-1", "place-1"}


def test_claim_without_observation_provenance_is_refused_before_writes() -> None:
    graph = InMemoryGraphStore()
    claim = _claim()
    claim = replace(claim, observation_refs=())
    with pytest.raises(ValueError, match="observation reference"):
        project_admitted_claim(graph, claim, validation_record={"verdict": "valid"})
    assert graph.nodes() == []
    assert graph.edges() == []



def test_rejected_verdict_removes_previous_projection_for_logical_relation() -> None:
    graph = InMemoryGraphStore()
    claim = _claim()
    valid = {"verdict": "VALID", "recorded_at": "2026-10-27T00:00:00+00:00"}
    rejected = {"verdict": "REJECTED", "reasons": [{"code": "EVIDENCE_REVOKED"}]}

    assert reconcile_claim_projection(graph, claim, validation_record=valid)["projected"] is True
    assert len(graph.edges()) == 1

    outcome = reconcile_claim_projection(graph, claim, validation_record=rejected)
    assert outcome["projected"] is False
    assert outcome["cleared"] == 1
    assert graph.edges() == []
    assert graph.hyperedges() == []


def test_replaying_nary_claim_does_not_duplicate_hyperedge_membership() -> None:
    graph = InMemoryGraphStore()
    claim = _claim(nary=True)
    first = reconcile_claim_projection(graph, claim, validation_record={"verdict": "VALID"})
    second = reconcile_claim_projection(graph, claim, validation_record={"verdict": "VALID"})
    assert first["projected"] is True
    assert second["projected"] is True
    assert len(graph.hyperedges()) == 1
    assert len(graph.member_hyperedges("person-1")) == 1
