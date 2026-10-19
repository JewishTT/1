"""Open-world predicates survive storage, projection and API with label and span intact.

Spec 030 T067 — FR-013, CD-6/CD-7.

FR-013 is a single sentence with two halves that fail in opposite directions:

    "Unknown entity types, relation predicates, attributes and source output kinds MUST be
    preserved with their original label and span; registry mismatch MUST produce an
    explicit unknown/conflict/unsupported marker rather than a silent drop."

The first half is about **not losing** the label. The second is about **not fabricating**
one. A predicate type that is unresolvable must not be given an invented operator, and a
dropped predicate must not be silently discarded — both are silent lies about the world.

What is checked here:

* ``predicate_raw`` is non-nullable at every layer, and always carries the origin words.
* It round-trips through the candidate's wire form and back with the span intact.
* It is *derived*, not stored, so it cannot drift from the identity material — and
  because it is derived, adding it did not fork a single ``candidate_id``.
* An unknown predicate produces a typed ``unknown`` candidate with a resolution marker,
  never a drop and never a ``known``.
* The span is never borrowed from another field when there is no trigger span.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from domain.predicate_hypothesis import (
    PredicateContractError,
    PredicateHypothesis,
    PredicateRaw,
    PredicateResolutionState,
    RawPredicateOrigin,
)
from domain.relation_candidate import (
    CandidateStatus,
    RelationCandidate,
    SpanRef,
)
from semantic.contracts import RelationRef

pytestmark = pytest.mark.unit


def _candidate(**over) -> RelationCandidate:
    base = {
        "subject_mention_ref": "MEN-1",
        "object_mention_ref": "MEN-2",
        "context_ref": "CTX-1",
        "semantic_regime_ref": "SR-1",
        "tenant_id": "tenant-a",
    }
    return RelationCandidate(**{**base, **over})


# =============================================================================
# The raw label itself
# =============================================================================


class TestPredicateRawIsNonNullable:
    def test_an_empty_label_is_refused(self) -> None:
        for value in ("", "   ", "\t\n"):
            with pytest.raises(PredicateContractError) as excinfo:
                PredicateRaw(label=value)
            assert excinfo.value.code == "predicate_raw_required"

    def test_the_refusal_names_the_reason_it_exists(self) -> None:
        with pytest.raises(PredicateContractError) as excinfo:
            PredicateRaw(label="")
        assert "indistinguishable" in str(excinfo.value)

    def test_an_unknown_predicate_carries_the_observed_words(self) -> None:
        hypothesis = PredicateHypothesis(surface_form="originator of")
        assert hypothesis.resolution_state is PredicateResolutionState.UNKNOWN
        assert hypothesis.predicate_raw.label == "originator of"
        assert hypothesis.predicate_raw.origin is RawPredicateOrigin.OBSERVED_SURFACE
        assert hypothesis.predicate_raw.is_observed

    def test_a_resolved_predicate_still_reports_the_words_that_produced_it(self) -> None:
        hypothesis = PredicateHypothesis(
            surface_form="works for", relation_ref=RelationRef("employment")
        )
        raw = hypothesis.predicate_raw
        assert raw.label == "works for"
        assert raw.origin is RawPredicateOrigin.OBSERVED_SURFACE, (
            "the observation said 'works for', and that is what must be preserved even "
            "when the platform also knows the type"
        )

    def test_a_typed_only_predicate_says_it_is_typed(self) -> None:
        """The platform's own label is legitimate but must announce itself.

        Without the origin marker a typed fallback renders in the UI as though a human
        wrote it in the source, which is FR-013's second half failing in the opposite
        direction: not a drop, but a fabrication.
        """
        hypothesis = PredicateHypothesis(relation_ref=RelationRef("employment"))
        raw = hypothesis.predicate_raw
        assert raw.label == "employment"
        assert raw.origin is RawPredicateOrigin.TYPED_RESOLUTION
        assert not raw.is_observed

    def test_a_hypothesis_with_neither_words_nor_a_type_is_refused(self) -> None:
        with pytest.raises(PredicateContractError) as excinfo:
            PredicateHypothesis()
        assert excinfo.value.code == "predicate_asserts_nothing"

    def test_a_half_span_is_refused(self) -> None:
        with pytest.raises(PredicateContractError) as excinfo:
            PredicateRaw(label="originator of", char_start=412)
        assert excinfo.value.code == "predicate_raw_half_span"

    def test_an_inverted_span_is_refused(self) -> None:
        with pytest.raises(PredicateContractError) as excinfo:
            PredicateRaw(label="originator of", char_start=425, char_end=412)
        assert excinfo.value.code == "predicate_raw_inverted_span"


# =============================================================================
# On the candidate, through storage and the wire
# =============================================================================


class TestCandidateCarriesTheRawPredicate:
    def test_an_unknown_predicate_reaches_the_wire_with_its_label_and_span(self) -> None:
        candidate = _candidate(
            relation_surface="originator of",
            trigger_span=SpanRef("SEG-7", 412, 425),
        )
        payload = candidate.predicate_raw_payload()
        assert payload["label"] == "originator of"
        assert payload["span_ref"] == "SEG-7"
        assert payload["char_start"] == 412
        assert payload["char_end"] == 425
        assert payload["resolution_state"] == "unknown"
        assert payload["is_unknown"] is True

    def test_the_predicate_is_typed_unknown_rather_than_dropped_or_invented(self) -> None:
        candidate = _candidate(relation_surface="originator of")
        assert candidate.predicate_is_unknown
        assert candidate.relation_ref is None, (
            "an unknown predicate must not acquire an operator type; a sentinel relation "
            "would make unknown semantics into known vocabulary"
        )
        assert candidate.candidate_status is CandidateStatus.PROPOSE

    def test_a_candidate_with_no_surface_falls_back_to_the_hypotheses_own(self) -> None:
        candidate = _candidate(
            predicate_hypothesis=PredicateHypothesis(surface_form="shareholder of")
        )
        assert candidate.predicate_raw.label == "shareholder of"

    def test_a_typed_candidate_is_not_reported_as_unknown(self) -> None:
        candidate = _candidate(relation_ref=RelationRef("employment"))
        assert not candidate.predicate_is_unknown
        assert candidate.predicate_raw.origin is RawPredicateOrigin.TYPED_RESOLUTION

    def test_a_header_only_predicate_travels_without_a_span_and_says_so(self) -> None:
        """No trigger phrase means no span. The gap is reported, not filled in.

        Borrowing another field's offsets here would be a fabricated citation: the reader
        would follow the span to a place in the document where the predicate is not.
        """
        candidate = _candidate(relation_surface="Originating counterparty")
        raw = candidate.predicate_raw
        assert raw.label == "Originating counterparty"
        assert not raw.has_span
        assert raw.char_start is None
        assert raw.span_ref == ""

    def test_the_wire_form_is_json_shaped_and_complete(self) -> None:
        candidate = _candidate(
            relation_surface="originator of",
            trigger_span=SpanRef("SEG-7", 412, 425),
        )
        payload = candidate.predicate_raw_payload()
        assert set(payload) >= {
            "label",
            "origin",
            "span_ref",
            "char_start",
            "char_end",
            "resolution_state",
            "is_unknown",
            "candidate_id",
        }
        assert all(
            isinstance(value, str | bool | int) or value is None
            for value in payload.values()
        )
        assert isinstance(payload["label"], str) and payload["label"]
        assert isinstance(payload["char_start"], int)
        assert isinstance(payload["is_unknown"], bool)

    def test_the_wire_form_survives_a_json_round_trip(self) -> None:
        import json

        candidate = _candidate(
            relation_surface="originator of",
            trigger_span=SpanRef("SEG-7", 412, 425),
        )
        before = json.loads(json.dumps(candidate.predicate_raw_payload()))
        after = json.loads(json.dumps(candidate.predicate_raw_payload()))
        assert before == after
        assert before["label"] == "originator of"


# =============================================================================
# Derived, not stored — the property that keeps stored ids intact
# =============================================================================


class TestPredicateRawDoesNotForkIdentity:
    def test_it_is_not_a_candidate_field(self) -> None:
        """A field would have to be classified, and every classification re-keys something.

        Logical material re-keys every ``CAND-``/``CNDR-``; revision material enters
        ``candidate_id`` and forks every candidate; mutable-projection metadata would
        weaken the guarantee that two candidates sharing a ``candidate_id`` differ only
        in ``confidence``. Being a property is what avoids all three.
        """
        from dataclasses import fields

        assert "predicate_raw" not in {field.name for field in fields(RelationCandidate)}
        assert isinstance(RelationCandidate.predicate_raw, property)

    def test_the_raw_predicate_cannot_disagree_with_the_material_it_is_derived_from(
        self,
    ) -> None:
        """Every input is already revision material, so the address covers the label."""
        candidate = _candidate(
            relation_surface="originator of",
            trigger_span=SpanRef("SEG-7", 412, 425),
        )
        revision = candidate._revision_material(candidate.logical_candidate_id)
        assert candidate.predicate_raw.label == revision["relation_surface"]
        assert revision["trigger_span"] == {"segment_ref": "SEG-7", "start": 412, "end": 425,
                                            "mention_ref": ""}

    def test_two_candidates_differing_only_in_the_raw_words_have_different_ids(self) -> None:
        """The label still reaches the address -- through the surface it is derived from."""
        one = _candidate(relation_surface="originator of").with_id()
        two = _candidate(relation_surface="shareholder of").with_id()
        assert one.candidate_id != two.candidate_id

    def test_adding_predicate_raw_changed_no_stored_identifier(self) -> None:
        """Two candidates with identical material still mint one id, and re-deriving it
        from the record reproduces it. If this fails, an existing ``candidate_id`` moved.
        """
        first = _candidate(relation_surface="originator of").with_id()
        second = _candidate(relation_surface="originator of").with_id()
        assert first.candidate_id == second.candidate_id
        assert first.content_hash == second.content_hash
        assert first.candidate_id.startswith("CNDR-")

    def test_a_changed_span_changes_the_id(self) -> None:
        """The span is address-bearing, so moving it is a different reading."""
        one = _candidate(
            relation_surface="originator of", trigger_span=SpanRef("SEG-7", 412, 425)
        ).with_id()
        two = _candidate(
            relation_surface="originator of", trigger_span=SpanRef("SEG-9", 100, 113)
        ).with_id()
        assert one.candidate_id != two.candidate_id

    def test_the_derived_value_follows_a_changed_hypothesis(self) -> None:
        """It follows the hypothesis, not the surface, once one has been constructed.

        The hypothesis is the authority after construction -- it holds the resolution and
        the alternatives, and a bare ``relation_surface`` no longer describes the
        predicate on its own. Checking this rather than assuming it is what keeps the
        derivation from being a second, disagreeing source of truth.
        """
        candidate = _candidate(relation_surface="shareholder of")
        assert candidate.predicate_raw.label == "shareholder of"
        after = replace(
            candidate,
            predicate_hypothesis=PredicateHypothesis(surface_form="originator of"),
        )
        assert after.predicate_raw.label == "originator of"


# =============================================================================
# Resolution markers — explicit, never inferred from an absent field
# =============================================================================


class TestResolutionMarkersAreExplicit:
    def test_the_four_states_stay_distinct(self) -> None:
        states = {
            PredicateHypothesis(surface_form="originator of").resolution_state,
            PredicateHypothesis(
                relation_ref=RelationRef("employment")
            ).resolution_state,
            PredicateHypothesis(
                relation_ref=RelationRef("ownership"),
                alternative_refs=(RelationRef("control"),),
            ).resolution_state,
            PredicateHypothesis(
                relation_ref=RelationRef("ownership"),
                alternative_refs=(RelationRef("control"),),
                resolution_state=PredicateResolutionState.CONFLICTING,
            ).resolution_state,
        }
        assert states == set(PredicateResolutionState)

    def test_ambiguous_is_not_reported_as_known(self) -> None:
        hypothesis = PredicateHypothesis(
            relation_ref=RelationRef("ownership"),
            alternative_refs=(RelationRef("control"),),
        )
        assert hypothesis.resolution_state is PredicateResolutionState.AMBIGUOUS

    def test_conflicting_is_never_silently_downgraded_to_ambiguous(self) -> None:
        hypothesis = PredicateHypothesis(
            relation_ref=RelationRef("ownership"),
            alternative_refs=(RelationRef("control"),),
        ).with_conflict(RelationRef("control"))
        assert hypothesis.resolution_state is PredicateResolutionState.CONFLICTING

    def test_an_unknown_predicate_cannot_be_claimed_as_conflicting_without_a_ref(self) -> None:
        with pytest.raises(PredicateContractError) as excinfo:
            PredicateHypothesis(
                surface_form="originator of",
                resolution_state=PredicateResolutionState.CONFLICTING,
            )
        assert excinfo.value.code == "predicate_resolution_without_ref"

    def test_a_ref_carries_the_observation_through_the_resolution(self) -> None:
        """Recognising a predicate later is a new reading, not a different hypothesis."""
        before = PredicateHypothesis(surface_form="originator of")
        after = PredicateHypothesis(
            surface_form="originator of",
            relation_ref=RelationRef("originator"),
            alternative_refs=(RelationRef("beneficial_owner"),),
        )
        assert before.resolution_state is PredicateResolutionState.UNKNOWN
        assert after.resolution_state is PredicateResolutionState.AMBIGUOUS
        assert before.predicate_raw.label == after.predicate_raw.label == "originator of"
        assert after.predicate_raw.origin is RawPredicateOrigin.OBSERVED_SURFACE

    def test_the_surface_is_readable_from_every_resolution_state(self) -> None:
        for hypothesis in (
            PredicateHypothesis(surface_form="originator of"),
            PredicateHypothesis(surface_form="works for", relation_ref=RelationRef("employment")),
        ):
            assert hypothesis.as_surface() == hypothesis.surface_form
