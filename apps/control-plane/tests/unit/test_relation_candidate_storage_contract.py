"""Contract tests for truthful storage of relation candidates and replay keys."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP.parents[1] / "apps" / "shared"))

from db.relation_candidate_store import candidate_row_values
from db.schema import EntityStreamRow, RelationCandidateRow
from domain.relation_candidate import RelationCandidate
from semantic.contracts import RelationRef


@pytest.mark.unit
def test_unresolved_logical_identity_is_preserved_without_a_fabricated_id() -> None:
    candidate = RelationCandidate(
        subject_mention_ref="MN-subject",
        object_mention_ref="MN-object",
        relation_ref=RelationRef("works_for", "1"),
        relation_surface="CEO of",
        context_ref="CX-frame",
        semantic_regime_ref="RG-regime",
        tenant_id="tenant-a",
        observation_refs=("OBS-1",),
        evidence_refs=("MN-subject", "MN-object"),
    ).with_id()
    row = candidate_row_values(candidate)
    assert candidate.logical_candidate_id == ""
    assert candidate.candidate_id.startswith("CNDR-")
    assert row["logical_candidate_id"] == ""
    assert row["candidate_id"] == candidate.candidate_id
    assert row["relation_surface"] == "CEO of"
    assert row["candidate_payload"]["candidate_id"] == candidate.candidate_id
    assert row["candidate_payload"]["relation_surface"] == "CEO of"


@pytest.mark.unit
def test_candidate_table_accepts_full_payload_without_a_logical_id_check() -> None:
    constraint_names = {constraint.name for constraint in RelationCandidateRow.__table__.constraints}
    assert "ck_relation_candidate_logical" not in constraint_names
    assert "candidate_payload" in RelationCandidateRow.__table__.c


@pytest.mark.unit
def test_entity_stream_declares_a_partial_source_event_replay_key() -> None:
    indexes = {index.name: index for index in EntityStreamRow.__table__.indexes}
    replay_index = indexes["uq_entity_stream_source_event"]
    assert replay_index.unique is True
    assert replay_index.dialect_options["postgresql"]["where"] is not None
    assert "source_event_id" in EntityStreamRow.__table__.c
