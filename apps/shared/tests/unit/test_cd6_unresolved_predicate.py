"""CD-6: a relation the platform cannot name is representable, and stays unasserted.

Task T005 (SC-O) of ``specs/019-universal-relation-extraction``.

Constitution 4 says the platform never fabricates what it has not observed. The trap
here is subtler than inventing a type: a vocabulary that *refuses* an untyped relation
has not lied yet, but it has already lost the world. "Originator of" is a real relation
between two real mentions, and if the platform has no operator for it, the honest
outcome is a candidate that keeps the words — not a dropped observation.

This file pins three things, and the third is the one that is easy to lose:

1. A candidate with no declared type is constructible, and keeps its surface (CD-6).
2. Resolving that surface later is a new *revision* of one logical candidate, not a
   second candidate (FR-039). Keying identity on the resolved type instead would split
   one hypothesis in two the first time anything read it.
3. Material refuses the unresolved candidate, and says what to do instead (FR-010).

If (3) ever starts passing, the boundary has been dissolved and untyped relations can
reach the world as assertions. If (1) or (2) breaks, the platform is losing
observations to the shape of its own vocabulary.
"""

from __future__ import annotations

import pytest

from domain.predicate_hypothesis import (
    PredicateContractError,
    PredicateHypothesis,
    PredicateResolutionState,
)
from domain.relation_candidate import RelationCandidate, TemporalHypothesis
from domain.relation_claim_material import (
    EvidenceGrade,
    MaterialContractError,
    build,
)
from semantic.contracts import RelationRef

#: What the observation actually said. Deliberately not an operator name: "originator"
#: is ambiguous in a way the platform has not settled, and pretending otherwise is the
#: failure this feature exists to prevent.
SURFACE = "originator of"

BASE = {
    "subject_mention_ref": "MN-A",
    "object_mention_ref": "MN-B",
    "context_ref": "CX-test",
    "semantic_regime_ref": "RG-test",
    "tenant_id": "T1",
}


def _candidate(**overrides) -> RelationCandidate:
    return RelationCandidate(
        temporal_hypothesis=TemporalHypothesis.absent(), **BASE, **overrides
    ).with_id()


def _material(candidate: RelationCandidate):
    return build(
        candidate,
        subject_ref="EN-A",
        object_ref="EN-B",
        revision_number=1,
        evidence_grade=EvidenceGrade.WEAK,
        tenant_id="T1",
    )


class TestUnresolvedIsRepresentable:
    def test_a_candidate_needs_no_declared_type(self) -> None:
        candidate = _candidate(relation_surface=SURFACE)
        assert candidate.relation_ref is None
        assert candidate.relation_type == ""

    def test_the_words_survive(self) -> None:
        assert _candidate(relation_surface=SURFACE).relation_surface == SURFACE

    def test_the_resolution_state_says_unknown_rather_than_guessing(self) -> None:
        hypothesis = _candidate(relation_surface=SURFACE).predicate_hypothesis
        assert hypothesis.resolution_state is PredicateResolutionState.UNKNOWN
        assert hypothesis.relation_ref is None

    def test_a_typed_candidate_is_still_known(self) -> None:
        candidate = _candidate(relation_ref=RelationRef("works_for"))
        assert candidate.predicate_hypothesis.resolution_state is PredicateResolutionState.KNOWN
        # A ref with no surface stated derives one, so nothing existing has to supply it.
        assert candidate.relation_surface == "works_for"

    def test_no_ref_and_no_surface_describes_nothing_and_is_refused(self) -> None:
        with pytest.raises(PredicateContractError) as excinfo:
            PredicateHypothesis()
        assert excinfo.value.code == "predicate_asserts_nothing"

    def test_the_platform_will_not_guess_a_type_from_a_bare_string(self) -> None:
        """``"owner of"`` and ``"works_for"`` are the same shape; choosing is fabricating.

        This is the sharpest form of the constitution-4 trap in this feature. Guessing
        would not merely lose information - it would commit a typed relation to the world
        that the platform has no evidence for, and the error would be invisible because
        the guess produces a perfectly well-formed reference.
        """
        with pytest.raises(PredicateContractError) as excinfo:
            PredicateHypothesis(relation_ref="works_for", surface_form="CEO of")
        assert excinfo.value.code == "predicate_string_ref_refused"

    def test_the_refusal_names_both_ways_forward(self) -> None:
        """A gate that only says no gets routed around by guessing."""
        with pytest.raises(PredicateContractError) as excinfo:
            PredicateHypothesis(relation_ref="works_for")
        message = str(excinfo.value)
        assert "RelationRef('works_for')" in message
        assert "surface_form='works_for'" in message

    def test_the_candidate_says_the_same_thing(self) -> None:
        from domain.relation_candidate import CandidateContractError

        with pytest.raises(CandidateContractError) as excinfo:
            _candidate(relation_ref=SURFACE)
        assert excinfo.value.code == "invalid_relation_ref"
        assert "relation_surface" in str(excinfo.value)

    def test_an_alternative_may_be_a_bare_string(self) -> None:
        """Not an inconsistency: an alternative is a type already being offered.

        The primary ref is the one position where a string could be an unresolved surface,
        so it has to be disambiguated. An alternative cannot be, so it need not be.
        """
        hypothesis = PredicateHypothesis(
            relation_ref=RelationRef("ownership"), surface_form=SURFACE
        ).with_alternatives("affiliation")
        assert [str(r) for r in hypothesis.alternative_refs] == ["affiliation@1"]
        assert hypothesis.resolution_state is PredicateResolutionState.AMBIGUOUS

    def test_legacy_provenance_is_read_as_a_surface(self) -> None:
        """The one place guessing is allowed, because there it knows it is guessing."""
        hypothesis = PredicateHypothesis.from_candidate_field("founder of")
        assert hypothesis.relation_ref is None
        assert hypothesis.surface_form == "founder of"
        assert hypothesis.resolution_state is PredicateResolutionState.UNKNOWN


class TestResolutionIsARevision:
    def test_one_hypothesis_keeps_one_logical_id(self) -> None:
        unresolved = _candidate(relation_surface=SURFACE)
        resolved = _candidate(relation_ref=RelationRef("ownership"), relation_surface=SURFACE)
        assert resolved.logical_candidate_id == unresolved.logical_candidate_id

    def test_recognising_it_mints_a_reading_not_a_candidate(self) -> None:
        unresolved = _candidate(relation_surface=SURFACE)
        resolved = _candidate(relation_ref=RelationRef("ownership"), relation_surface=SURFACE)
        assert resolved.candidate_id != unresolved.candidate_id

    def test_genuinely_different_predicates_stay_different_hypotheses(self) -> None:
        assert (
            _candidate(relation_ref=RelationRef("owns")).logical_candidate_id
            != _candidate(relation_ref=RelationRef("located_in")).logical_candidate_id
        )

    def test_two_readings_of_one_surface_differ_only_by_the_reading(self) -> None:
        """Ambiguity must be visible as ambiguity, not flattened to the first answer."""
        first = PredicateHypothesis(relation_ref=RelationRef("ownership"), surface_form=SURFACE)
        second = PredicateHypothesis(relation_ref=RelationRef("control"), surface_form=SURFACE)
        assert first.content_key() != second.content_key()
        assert first.surface_form == second.surface_form == SURFACE


class TestMaterialHoldsTheLine:
    def test_a_typed_candidate_materialises(self) -> None:
        material = _material(
            _candidate(relation_ref=RelationRef("works_for"), relation_surface="CEO of")
        )
        assert material.relation_type == "works_for"
        assert not material.is_committed

    def test_an_untyped_candidate_does_not_reach_material(self) -> None:
        with pytest.raises(MaterialContractError) as excinfo:
            _material(_candidate(relation_surface=SURFACE))
        assert excinfo.value.code == "material_requires_resolved_predicate"

    def test_the_refusal_says_how_to_proceed(self) -> None:
        """A gate that only says no leaves the operator inventing a type to get past it."""
        with pytest.raises(MaterialContractError) as excinfo:
            _material(_candidate(relation_surface=SURFACE))
        message = str(excinfo.value)
        assert "relation_surface" in message
        assert "SemanticRegime" in message
        assert "Do not invent a type" in message
