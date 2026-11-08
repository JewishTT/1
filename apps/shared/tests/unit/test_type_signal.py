from __future__ import annotations

import pytest

from semantic.type_signal import TypeMappingCandidate, TypeSignal
from semantic.vocabularies import Concept, MatchPredicate


def _signal(**overrides):
    payload = {
        "source_vocab": "https://schema.org/",
        "surface": "Person",
        "mention_ref": "MN-123",
        "structural_path": ("jsonld[0]", "@graph", "0", "@type"),
        "observation_refs": ("OBS-1",),
        "evidence_refs": ("OBS-1",),
        "producer_ref": "structured/json-ld",
        "tenant_id": "tenant-test",
    }
    payload.update(overrides)
    return TypeSignal(**payload)


def test_type_signal_round_trips_and_preserves_source_surface():
    signal = _signal()
    assert signal.signal_id.startswith("TS-")
    assert signal.surface == "Person"
    assert signal.source_vocab == "https://schema.org/"
    assert TypeSignal.from_dict(signal.to_dict()) == signal


def test_type_signal_identity_excludes_mapping_candidates_and_evidence_revision():
    first = _signal()
    candidate = TypeMappingCandidate(
        source="schema:Person", target="core:Person",
        match_type=MatchPredicate.EXACT_MATCH, confidence=0.9,
        provenance=("review-1",), mapping_version="1", created_by="test",
        evidence_refs=("OBS-1",),
    )
    revised = _signal(mapping_candidates=(candidate,),
                      observation_refs=("OBS-2",), evidence_refs=("OBS-2",))
    assert revised.signal_id == first.signal_id
    assert revised.mapping_candidates == (candidate,)
    assert TypeSignal.from_dict(revised.to_dict()) == revised


def test_detector_without_external_vocabulary_uses_none_not_synthetic_name():
    assert _signal(source_vocab=None).source_vocab is None
    with pytest.raises(ValueError, match="external vocabulary or be None"):
        _signal(source_vocab="regex")


def test_signal_rejects_carried_id_that_disagrees_with_its_content():
    with pytest.raises(ValueError, match="disagrees with derived"):
        _signal(signal_id="TS-fabricated")


def test_mapping_candidate_refuses_missing_match_type():
    with pytest.raises(ValueError):
        TypeMappingCandidate(source="schema:Person", target="core:Person",
                             match_type="")


def test_non_hierarchical_mapping_is_representable():
    candidate = TypeMappingCandidate(
        source="provider:ResearchGroup", target="core:Organization",
        match_type=MatchPredicate.RELATED_MATCH, mapping_version="1",
        created_by="reviewer",
    )
    assert candidate.match_type is MatchPredicate.RELATED_MATCH
    assert candidate.to_dict()["match_type"] == "related_match"


def test_concept_exposes_related_match_as_a_cross_vocabulary_link():
    concept = Concept(concept_id="research-group", related_match=("provider:ResearchGroup",))
    links = concept.matches(MatchPredicate.RELATED_MATCH)
    assert len(links) == 1
    assert links[0].target_ref == "provider:ResearchGroup"
    assert Concept(concept_id="research-group").content_key() != concept.content_key()


def test_mapping_candidate_canonicalizes_identity_metadata_before_hashing():
    candidate = TypeMappingCandidate(
        source="schema:Person", target="core:Person",
        match_type=MatchPredicate.EXACT_MATCH,
        mapping_version=" 1 ", created_by=" reviewer ",
        mapping_set_id=" map-set ", mapping_set_version=" 2 ",
    )
    assert candidate.mapping_version == "1"
    assert candidate.created_by == "reviewer"
    assert candidate.mapping_set_id == "map-set"
    assert candidate.mapping_set_version == "2"
