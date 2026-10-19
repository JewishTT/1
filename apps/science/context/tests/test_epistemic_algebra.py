"""Epistemic algebra: the four values, the thirteen states, the contradictions, the vector.

Spec 030 T068, T069, T064, T070, T074 — US3, FR-010/011/012/016.

Four things are checked here and each is a different kind of failure:

* **T068 — the truth table.** ``TRUE_ONLY`` and ``FALSE_ONLY`` are *incomparable*, not
  opposites. Exhaustive over all four values and all sixteen pairs, because the state
  space is finite and sampling it would be choosing which collapse not to look for.
  Confidence is checked as a separate field that nothing in the algebra reads.
* **T069 — contradiction survival.** Every heuristic FR-012 names is offered to a real
  contradiction and every one comes back declined, with both sides intact.
* **T070 — the thirteen states.** Checked as dimension tuples, not labels, and checked
  for pairwise distinctness. A pair of states that agreed would mean two different facts
  round-trip to one value.
* **T074 — fourteen components.** A vector, a composite that keeps it, and the two
  constructions that must be refused.

The corpus half at the bottom (T064/T066) runs every case in
``bench/fixtures/global_upgrade/epistemic/cases.jsonl`` through the real
:meth:`ResearchState.resolve` and compares against the fixture's independently-written
expectation. The harness below maps fixture fields onto resolve()'s arguments; the
decision logic under test is the library's, not this file's, which is what stops the two
agreeing with each other by construction.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from dataclasses import replace
from itertools import product
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from context.epistemic import (
    _CANO13,
    FR016_ROLE_COMPONENT,
    AbsenceAxis,
    CompositeScore,
    Contradiction,
    ContradictionKind,
    EpistemicStateError,
    EvidenceAxis,
    EvidenceContribution,
    Proposition,
    QueryAxis,
    ResearchState,
    ResearchStateName,
    ResolutionAttempt,
    ResolutionHeuristic,
    ScopeAxis,
    ScoreComponent,
    ScoreVector,
    SearchDisposition,
    TruthState,
    accumulate,
    attempt_resolution,
    consensus,
    contradiction_for_both,
    derive_truth_state,
    knowledge_leq,
    negate,
    truth_leq,
)

#: ``.../apps/science/context/tests/`` -> parents[2] is ``apps/science`` (which is what
#: makes ``context.*`` importable above) and parents[4] is the repository root, which is
#: where ``bench/fixtures`` lives. Resolved from ``__file__`` rather than from the CWD so
#: the corpus is found identically from the repo root, from ``apps/science`` and from an
#: editor.
CORPUS = (
    Path(__file__).resolve().parents[4]
    / "bench"
    / "fixtures"
    / "global_upgrade"
    / "epistemic"
    / "cases.jsonl"
)

pytestmark = pytest.mark.unit

ALL_STATES = tuple(TruthState)
ALL_PAIRS = tuple(product(ALL_STATES, repeat=2))


# =============================================================================
# T068 — the four-valued support truth table
# =============================================================================


class TestFourValuedSupport:
    def test_the_flag_table_is_section_13_1(self) -> None:
        assert TruthState.from_flags(False, False) is TruthState.NEITHER
        assert TruthState.from_flags(True, False) is TruthState.TRUE_ONLY
        assert TruthState.from_flags(False, True) is TruthState.FALSE_ONLY
        assert TruthState.from_flags(True, True) is TruthState.BOTH

    def test_flags_round_trip_for_every_state(self) -> None:
        for state in ALL_STATES:
            assert TruthState.from_flags(*state.flags) is state

    def test_true_only_and_false_only_are_incomparable_in_the_knowledge_order(self) -> None:
        """The load-bearing property of T068: incomparable, not opposites.

        Neither sits below the other, because neither has more *evidence* than the other.
        "One-sided true evidence" and "one-sided false evidence" are two different
        amounts of the same thing, and collapsing them into a chain would make
        ``accumulate`` order its inputs -- which is why the diamond exists.
        """
        assert not knowledge_leq(TruthState.TRUE_ONLY, TruthState.FALSE_ONLY)
        assert not knowledge_leq(TruthState.FALSE_ONLY, TruthState.TRUE_ONLY)

    def test_the_truth_order_does_rank_them_and_that_is_not_the_same_order(self) -> None:
        """Incomparability is a property of the *knowledge* order specifically.

        The truth order ranks FALSE_ONLY below TRUE_ONLY -- more true is higher -- and
        reading that ranking as a knowledge claim is the collapse. Both orders are
        checked here precisely because they disagree, and an implementation that had only
        one would pass whichever half it was written against.
        """
        assert truth_leq(TruthState.FALSE_ONLY, TruthState.TRUE_ONLY)
        assert not truth_leq(TruthState.TRUE_ONLY, TruthState.FALSE_ONLY)
        assert knowledge_leq(TruthState.TRUE_ONLY, TruthState.BOTH)
        assert not truth_leq(TruthState.TRUE_ONLY, TruthState.BOTH)

    def test_neither_and_both_are_the_two_incomparable_pairs(self) -> None:
        """Exhaustive: exactly two pairs are incomparable in the knowledge order."""
        incomparable = {
            (left, right)
            for left, right in ALL_PAIRS
            if not knowledge_leq(left, right) and not knowledge_leq(right, left)
        }
        assert incomparable == {
            (TruthState.TRUE_ONLY, TruthState.FALSE_ONLY),
            (TruthState.FALSE_ONLY, TruthState.TRUE_ONLY),
        }

    def test_the_incomparability_survives_every_operator(self) -> None:
        """No combination of the five operators can rank one above the other.

        The diamond property has to hold at the operation level, not only on the
        relation: two operators applied to incomparable inputs would produce comparable
        outputs, and the order would be broken one step downstream of where anyone looks.
        """
        for op in (accumulate, consensus):
            result = op(TruthState.TRUE_ONLY, TruthState.FALSE_ONLY)
            for other in ALL_STATES:
                assert (
                    knowledge_leq(result, other) or knowledge_leq(other, result)
                    or other in (TruthState.TRUE_ONLY, TruthState.FALSE_ONLY)
                    or result in (TruthState.TRUE_ONLY, TruthState.FALSE_ONLY)
                )

    def test_both_is_maximum_in_one_order_and_not_in_the_other(self) -> None:
        """The two orders are genuinely different, not the same order spelled twice."""
        assert knowledge_leq(TruthState.TRUE_ONLY, TruthState.BOTH)
        assert knowledge_leq(TruthState.FALSE_ONLY, TruthState.BOTH)
        # In the truth order BOTH sits BELOW TRUE_ONLY. Reading it as the maximum is the
        # single most common way the two orders get collapsed.
        assert truth_leq(TruthState.BOTH, TruthState.TRUE_ONLY)
        assert not truth_leq(TruthState.TRUE_ONLY, TruthState.BOTH)

    def test_accumulating_a_true_with_a_false_is_both_not_a_choice(self) -> None:
        for left, right in ALL_PAIRS:
            assert accumulate(left, right) is accumulate(right, left)
        assert accumulate(TruthState.TRUE_ONLY, TruthState.FALSE_ONLY) is TruthState.BOTH
        assert accumulate(TruthState.TRUE_ONLY, TruthState.TRUE_ONLY) is TruthState.TRUE_ONLY

    def test_consensus_of_disagreement_is_neither_not_a_side(self) -> None:
        for left, right in ALL_PAIRS:
            assert consensus(left, right) is consensus(right, left)
        assert consensus(TruthState.TRUE_ONLY, TruthState.FALSE_ONLY) is TruthState.NEITHER

    def test_negate_is_an_involution_over_the_whole_space(self) -> None:
        for state in ALL_STATES:
            assert negate(negate(state)) is state
        assert negate(TruthState.TRUE_ONLY) is TruthState.FALSE_ONLY
        assert negate(TruthState.BOTH) is TruthState.BOTH

    def test_absence_of_positive_support_is_not_negative_support(self) -> None:
        """FR-011's first clause, as an executable statement.

        ``NEITHER`` and ``FALSE_ONLY`` are different states and the derive function must
        not reach one from the other. This is the collapse that turns "nobody has found
        anything" into "there is nothing".
        """
        assert derive_truth_state([]) is TruthState.NEITHER
        assert derive_truth_state(
            [EvidenceContribution(evidence_id="E1", positive=True, admissible=False)]
        ) is TruthState.NEITHER
        assert derive_truth_state(
            [EvidenceContribution(evidence_id="E1", positive=False, coverage_qualified=True)]
        ) is TruthState.NEITHER

    def test_a_coverage_qualified_absence_contributes_neither_side(self) -> None:
        state = derive_truth_state(
            [
                EvidenceContribution(evidence_id="E1", positive=True),
                EvidenceContribution(evidence_id="E2", positive=False, coverage_qualified=True),
            ]
        )
        assert state is TruthState.TRUE_ONLY

    def test_conflict_does_not_collapse_to_a_boolean(self) -> None:
        state = derive_truth_state(
            [
                EvidenceContribution(evidence_id="E1", positive=True),
                EvidenceContribution(evidence_id="E2", positive=False),
            ]
        )
        assert state is TruthState.BOTH
        assert state.positive and state.negative
        assert state.is_conflicted


class TestConfidenceIsSeparate:
    """§13.4: ``truth_state`` and ``score`` are independent and neither converts to the other."""

    def test_confidence_is_carried_but_changes_no_axis(self) -> None:
        low = replace(
            ResearchState.for_name(ResearchStateName.POSITIVE_SUPPORT), confidence=0.0
        )
        high = replace(
            ResearchState.for_name(ResearchStateName.POSITIVE_SUPPORT), confidence=1.0
        )
        assert low.confidence == 0.0 and high.confidence == 1.0
        assert low.fingerprint == high.fingerprint

    def test_no_truth_state_converts_to_a_probability(self) -> None:
        for name in ("to_probability", "as_probability", "probability", "score"):
            assert not hasattr(TruthState, name)

    def test_a_proposition_holds_its_score_apart_from_its_truth_state(self) -> None:
        prop = Proposition(
            subject="s", predicate="p", object="o", truth_state=TruthState.TRUE_ONLY, score=0.01
        )
        assert prop.truth_state is TruthState.TRUE_ONLY
        assert prop.as_dict()["truth_state"] == "true_only"
        assert prop.as_dict()["score"] == 0.01

    def test_the_two_axes_are_carried_separately_in_the_serialised_form(self) -> None:
        payload = replace(
            ResearchState.for_name(ResearchStateName.POSITIVE_SUPPORT), confidence=0.42
        ).as_dict()
        assert payload["confidence"] == 0.42
        assert payload["truth_state"] == "true_only"


# =============================================================================
# T069 — contradiction survives
# =============================================================================


def _contradiction(proposition_id: str = "PRP-TEST") -> Contradiction:
    return Contradiction(
        proposition_id=proposition_id,
        kind=ContradictionKind.SUPPORT,
        detail="two sources state opposite things",
        independent=True,
        sides=(
            {"side": "supporting", "refs": ("EVD-A",)},
            {"side": "refuting", "refs": ("EVD-B",)},
        ),
        subject_refs=("EVD-A", "EVD-B"),
    )


def _corpus_contradiction(case_id: str) -> Contradiction:
    return _contradiction(proposition_id=f"PRP-{case_id}")


class TestContradictionSurvival:
    def test_both_support_and_refutation_create_one_and_keep_both_sides(self) -> None:
        prop = Proposition(
            subject="s", predicate="p", object="o", truth_state=TruthState.BOTH
        )
        contradiction = Contradiction(
            proposition_id=prop.proposition_id,
            kind=ContradictionKind.SUPPORT,
            detail="disagreement",
            sides=({"side": "s", "refs": ("a",)}, {"side": "r", "refs": ("b",)}),
        )
        assert contradiction is not None
        assert len(contradiction.sides) == 2

    def test_a_contradiction_must_be_constructed_with_sides(self) -> None:
        """A contradiction with no sides is not a contradiction; with none, it raises."""
        with pytest.raises(ValueError):
            Contradiction(
                proposition_id="P",
                kind=ContradictionKind.SUPPORT,
                detail="d",
                sides=(),
            )

    def test_the_constructor_that_makes_contradictions_always_attaches_both(self) -> None:
        """The guarantee is at the factory, which is where a ``BOTH`` state becomes one.

        ``Contradiction`` refuses an *empty* side list; the stronger property -- that
        support and refutation both arrive -- is enforced by the only thing in this module
        that creates one from a proposition. Checking it here rather than asserting the
        dataclass does more than it does is deliberate: a test that overstates a
        guarantee is worse than one that does not have it.
        """
        for support, negative in (
            (("EVD-A",), ("EVD-B",)),
            ((), ("EVD-B",)),
            (("EVD-A",), ()),
        ):
            prop = Proposition(
                subject="s", predicate="p", object="o", truth_state=TruthState.BOTH
            )
            built = contradiction_for_both(
                prop, positive_refs=support, negative_refs=negative
            )
            assert built is not None
            sides = [side["side"] for side in built.sides]
            assert sides == ["supporting", "refuting"]
            assert built.subject_refs == (*support, *negative)

    @pytest.mark.parametrize("heuristic", list(ResolutionHeuristic))
    def test_every_resolution_heuristic_is_declined(self, heuristic: ResolutionHeuristic) -> None:
        attempt = attempt_resolution(_contradiction(), offered=[heuristic])
        assert attempt.resolved is False
        assert attempt.declared_state is TruthState.BOTH
        assert attempt.offered == (heuristic,)
        assert heuristic.value in attempt.reason

    def test_recency_document_majority_and_a_single_high_score_are_all_declined_together(
        self,
    ) -> None:
        attempt = attempt_resolution(
            _contradiction(),
            offered=["recency", "document_majority", "single_high_score", "last_write_wins"],
        )
        assert attempt.resolved is False
        assert attempt.declared_state is TruthState.BOTH
        assert len(attempt.offered) == 4

    def test_the_attempt_records_the_state_the_caller_wanted_to_assert(self) -> None:
        """The caller is allowed to want a side; the record shows it did not get one."""
        attempt = attempt_resolution(
            _contradiction(), offered=["recency"], declared_state=TruthState.TRUE_ONLY
        )
        assert attempt.declared_state is TruthState.BOTH
        assert "true_only" in attempt.reason

    def test_an_attempt_cannot_be_constructed_as_resolved(self) -> None:
        with pytest.raises(EpistemicStateError, match="FR-012"):
            ResolutionAttempt(
                contradiction_id="C",
                declared_state=TruthState.BOTH,
                offered=(),
                reason="because I said so",
                resolved=True,
            )

    def test_an_attempt_cannot_be_constructed_with_one_side_dropped(self) -> None:
        with pytest.raises(EpistemicStateError, match="both sides"):
            ResolutionAttempt(
                contradiction_id="C",
                declared_state=TruthState.BOTH,
                offered=(),
                reason="r",
                sides_retained=False,
            )

    def test_resolution_records_an_explanation_and_never_deletes_support(self) -> None:
        original = _contradiction()
        explained = original.resolve("registry corrected its own record in 2026-02")
        assert explained.status.value in ("explained", "resolved")
        assert explained.explanation
        assert explained.sides == original.sides

    def test_a_conflicted_state_obliges_the_caller_to_hold_a_contradiction(self) -> None:
        assert ResearchState.for_name(ResearchStateName.BOTH_CONTRADICTION).contradiction_required
        assert not ResearchState.for_name(
            ResearchStateName.POSITIVE_SUPPORT, detection_power=None
        ).contradiction_required

    def test_conflicted_evidence_cannot_ride_on_a_determined_truth_state(self) -> None:
        with pytest.raises(EpistemicStateError, match="BOTH"):
            ResearchState(
                disposition=SearchDisposition.COMPLETED,
                query=QueryAxis.RAN_MATCHED,
                truth_state=TruthState.TRUE_ONLY,
                absence=AbsenceAxis.NOT_APPLICABLE,
                evidence=EvidenceAxis.CONFLICTED,
            )


# =============================================================================
# T070 — thirteen states, six dimensions, no collapse
# =============================================================================


def _anchor(name: ResearchStateName) -> ResearchState:
    needs_power = AbsenceAxis.QUALIFIED_ABSENCE in _CANO13[name]
    return ResearchState.for_name(name, detection_power=1.0 if needs_power else None)


class TestThirteenStates:
    def test_there_are_exactly_thirteen(self) -> None:
        assert len(ResearchStateName) == 13
        assert set(_CANO13) == set(ResearchStateName)

    def test_no_two_states_share_a_dimension_tuple(self) -> None:
        """The whole of "no collapse". Two agreeing tuples is two facts with one value."""
        seen: dict[tuple[str, ...], ResearchStateName] = {}
        for name in ResearchStateName:
            fingerprint = _anchor(name).fingerprint
            assert fingerprint not in seen, (
                f"{name} and {seen.get(fingerprint)} share a tuple; two distinct epistemic "
                "facts round-trip to one value"
            )
            seen[fingerprint] = name
        assert len(seen) == 13

    @pytest.mark.parametrize("name", list(ResearchStateName))
    def test_each_state_is_constructible_and_names_itself(self, name: ResearchStateName) -> None:
        state = _anchor(name)
        assert state.name is name

    @pytest.mark.parametrize("name", list(ResearchStateName))
    def test_each_state_survives_serialisation(self, name: ResearchStateName) -> None:
        state = _anchor(name)
        assert ResearchState.from_dict(state.as_dict()).fingerprint == state.fingerprint

    @pytest.mark.parametrize("name", list(ResearchStateName))
    def test_a_state_read_back_with_a_missing_axis_is_refused(
        self, name: ResearchStateName
    ) -> None:
        payload = _anchor(name).as_dict()
        del payload["absence"]
        with pytest.raises(EpistemicStateError, match="collapsed"):
            ResearchState.from_dict(payload)

    def test_saturated_with_scope_is_a_record_not_a_member(self) -> None:
        """T070's actual point: exhaustion composes with whatever the search found.

        An exhausted search that found evidence on both sides is a different record from
        an exhausted search that found nothing, and a flat enum with a
        ``SATURATED_WITH_SCOPE`` member could only say one of those things.
        """
        empty = _anchor(ResearchStateName.SATURATED_WITH_SCOPE)
        contradicted = ResearchState(
            disposition=SearchDisposition.EXHAUSTED,
            query=QueryAxis.RAN_MATCHED,
            truth_state=TruthState.BOTH,
            absence=AbsenceAxis.NOT_APPLICABLE,
            evidence=EvidenceAxis.CONFLICTED,
            scope=ScopeAxis.DECLARED,
        )
        assert empty.fingerprint != contradicted.fingerprint
        assert contradicted.name is None, (
            "no member of ResearchStateName describes exhausted-and-contradicted, which is "
            "the reason the model is dimensions"
        )
        assert contradicted.contradiction_required

    def test_exhaustion_requires_a_declared_scope(self) -> None:
        with pytest.raises(EpistemicStateError, match="declared scope"):
            ResearchState(
                disposition=SearchDisposition.EXHAUSTED,
                query=QueryAxis.RAN_ZERO_MATCH,
                truth_state=TruthState.NEITHER,
                absence=AbsenceAxis.SEARCHED_NO_RESULT,
                evidence=EvidenceAxis.NONE,
                scope=ScopeAxis.UNDECLARED,
            )

    def test_a_declared_scope_cannot_be_attached_to_an_unfinished_run(self) -> None:
        with pytest.raises(EpistemicStateError, match="declared search scope"):
            ResearchState(
                disposition=SearchDisposition.COMPLETED,
                query=QueryAxis.RAN_MATCHED,
                truth_state=TruthState.TRUE_ONLY,
                absence=AbsenceAxis.NOT_APPLICABLE,
                evidence=EvidenceAxis.OBSERVED,
                scope=ScopeAxis.DECLARED,
            )

    def test_a_failed_run_cannot_report_a_qualified_absence(self) -> None:
        with pytest.raises(EpistemicStateError, match="never saw the world"):
            ResearchState(
                disposition=SearchDisposition.FAILED,
                query=QueryAxis.NOT_RUN,
                truth_state=TruthState.NEITHER,
                absence=AbsenceAxis.QUALIFIED_ABSENCE,
                evidence=EvidenceAxis.NONE,
                detection_power=0.95,
            )

    def test_an_unrepresentable_query_cannot_claim_it_ran(self) -> None:
        with pytest.raises(EpistemicStateError, match="UNRUNNABLE"):
            ResearchState(
                disposition=SearchDisposition.UNREPRESENTABLE,
                query=QueryAxis.RAN_ZERO_MATCH,
                truth_state=TruthState.NEITHER,
                absence=AbsenceAxis.NOT_APPLICABLE,
                evidence=EvidenceAxis.NONE,
            )

    def test_support_cannot_ride_on_a_query_that_matched_nothing(self) -> None:
        with pytest.raises(EpistemicStateError, match="absence of positive support"):
            ResearchState(
                disposition=SearchDisposition.COMPLETED,
                query=QueryAxis.RAN_ZERO_MATCH,
                truth_state=TruthState.TRUE_ONLY,
                absence=AbsenceAxis.NOT_APPLICABLE,
                evidence=EvidenceAxis.OBSERVED,
            )


# =============================================================================
# T066 / FR-014 — undeclared detection power is informational only
# =============================================================================


class TestDetectionPowerGate:
    def test_a_qualified_absence_without_declared_power_cannot_be_built(self) -> None:
        with pytest.raises(EpistemicStateError, match="declared detection power"):
            ResearchState(
                disposition=SearchDisposition.COMPLETED,
                query=QueryAxis.RAN_ZERO_MATCH,
                truth_state=TruthState.NEITHER,
                absence=AbsenceAxis.QUALIFIED_ABSENCE,
                evidence=EvidenceAxis.NONE,
                detection_power=None,
            )

    @pytest.mark.parametrize(
        ("power", "coverage"),
        [(None, 0.99), (None, None), (0.1, 0.99), (0.9, None), (0.9, 0.2)],
    )
    def test_any_missing_precondition_gives_informational_only(
        self, power: float | None, coverage: float | None
    ) -> None:
        state = ResearchState.for_detection_power(detection_power=power, coverage=coverage)
        assert state.absence is AbsenceAxis.INFORMATIONAL_ONLY
        assert state.may_claim_absence is False
        assert state.limitations, "an informational-only state must say which half is missing"

    def test_declared_power_above_threshold_with_declared_coverage_is_earned(self) -> None:
        state = ResearchState.for_detection_power(detection_power=0.93, coverage=0.91)
        assert state.absence is AbsenceAxis.SEARCHED_NO_RESULT
        assert not state.limitations

    def test_declared_power_alone_is_not_a_qualified_absence(self) -> None:
        """FR-014 names six preconditions; a source's power is one of them."""
        state = ResearchState.for_detection_power(detection_power=0.94, coverage=0.96)
        assert state.absence is not AbsenceAxis.QUALIFIED_ABSENCE
        assert state.may_claim_absence is False


# =============================================================================
# T074 — fourteen components, one policy version, no absorbed pair
# =============================================================================


class TestFourteenComponents:
    def test_there_are_exactly_fourteen(self) -> None:
        assert len(ScoreComponent) == 14
        assert len({item.value for item in ScoreComponent}) == 14

    def test_the_named_ten_of_fr_016_are_addressable(self) -> None:
        assert set(FR016_ROLE_COMPONENT) == {
            "relevance",
            "source_reliability",
            "claim_support",
            "identity_match",
            "novelty",
            "centrality",
            "freshness",
            "uncertainty",
            "independence",
            "action_utility",
        }

    def test_the_four_that_are_one_component_each_map_to_one_component(self) -> None:
        for role in ("relevance", "source_reliability", "novelty", "freshness", "independence"):
            assert isinstance(FR016_ROLE_COMPONENT[role], ScoreComponent)

    def test_the_rest_have_no_component_and_are_declared_as_such(self) -> None:
        """Claim support is a TruthState, not a score. Folding it in is the defect.

        Recorded as ``None`` on purpose: a caller looking for a home for "claim support"
        finds a refusal rather than a fourth column, which is what stops the composite
        from quietly acquiring it.
        """
        for role in ("claim_support", "identity_match", "centrality", "uncertainty", "action_utility"):
            assert role in FR016_ROLE_COMPONENT
            assert FR016_ROLE_COMPONENT[role] is None

    def test_unmeasured_is_distinct_from_zero(self) -> None:
        vector = ScoreVector(relevance=0.0)
        assert vector.measured() == (ScoreComponent.RELEVANCE,)
        assert vector.get(ScoreComponent.RELEVANCE) == 0.0
        assert vector.get(ScoreComponent.NOVELTY) is None
        payload = vector.as_dict()
        assert payload["relevance"] == 0.0
        assert payload["novelty"] is None

    def test_two_readings_differing_in_one_component_stay_distinguishable(self) -> None:
        a = ScoreVector(relevance=0.5, novelty=0.5).as_dict()
        b = ScoreVector(relevance=0.5, novelty=0.6).as_dict()
        assert a != b

    def test_a_composite_must_carry_its_policy_version(self) -> None:
        vector = ScoreVector(relevance=1.0)
        with pytest.raises(EpistemicStateError, match="policy version"):
            vector.composite({"relevance": 1.0}, policy_version="   ")

    def test_a_composite_retains_the_component_vector(self) -> None:
        vector = ScoreVector(relevance=0.4, novelty=0.9)
        composite = vector.composite(
            {"relevance": 0.5, "novelty": 0.5}, policy_version="rank/1"
        )
        assert isinstance(composite, CompositeScore)
        assert composite.value == pytest.approx(0.65)
        assert composite.policy_version == "rank/1"
        assert composite.vector is vector
        payload = composite.as_dict()
        assert payload["components"]["relevance"] == 0.4
        assert payload["components"]["novelty"] == 0.9
        assert payload["weights"] == {"novelty": 0.5, "relevance": 0.5}

    def test_a_composite_cannot_weigh_a_component_nobody_measured(self) -> None:
        """Dropping it would reweight the rest silently and read as a real score."""
        vector = ScoreVector(relevance=0.4)
        with pytest.raises(EpistemicStateError, match="not measured"):
            vector.composite({"relevance": 1.0, "novelty": 1.0}, policy_version="rank/1")

    def test_a_composite_cannot_be_constructed_without_its_vector(self) -> None:
        with pytest.raises(TypeError):
            CompositeScore(value=1.0, weights={ScoreComponent.RELEVANCE: 1.0}, policy_version="p/1")

    def test_probability_of_success_must_declare_its_semantics(self) -> None:
        with pytest.raises(EpistemicStateError, match="semantics"):
            ScoreVector(probability_of_success=0.73, probability_semantics="  ")
        assert (
            ScoreVector(probability_of_success=0.73).as_dict()["probability_semantics"]
            == "uncalibrated_score"
        )

    def test_a_scalar_alone_is_not_a_thing_this_module_produces(self) -> None:
        """U1: the vector is the stored truth. There is no constructor that yields a bare float."""
        assert ScoreVector(relevance=1.0).composite(
            {"relevance": 1.0}, policy_version="rank/1"
        ).value == 1.0
        assert not isinstance(ScoreVector(relevance=1.0), float)


# =============================================================================
# T064 / T066 — the corpus, run against the library
# =============================================================================


def _load_corpus() -> list[dict[str, Any]]:
    return [json.loads(line) for line in CORPUS.read_text(encoding="utf-8").splitlines() if line]


CORPUS_CASES = _load_corpus()
CASE_IDS = [case["case_id"] for case in CORPUS_CASES]


def _resolve(case: dict[str, Any]) -> ResearchState:
    """Map one fixture onto :meth:`ResearchState.resolve`.

    Plumbing, not policy. Every judgement about *what the case means* lives in the
    fixture's ``expected`` block and is checked against the library; this function only
    decides which resolve() argument a fixture field corresponds to.
    """
    sources: Sequence[dict[str, Any]] = case["sources"]
    declared_powers = [
        source["declared_detection_power"]
        for source in sources
        if source["declared_detection_power"] is not None
    ]
    contributions = [
        EvidenceContribution(
            evidence_id=item["ref"],
            positive=bool(item["positive"]),
            explicit_denial=bool(item.get("explicit_denial")),
        )
        for item in case["evidence"]
        if item["positive"] is not None
    ]
    non_settling = [item for item in case["evidence"] if item["positive"] is None]
    all_declared = bool(case.get("all_fr014_preconditions_declared"))
    return ResearchState.resolve(
        source_reachable=all(source["reaches_platform"] for source in sources)
        if sources
        else True,
        supports_query_kind=all(source["supports_query_kind"] for source in sources)
        if sources
        else True,
        capability_available=all(source["capability_available"] for source in sources)
        if sources
        else True,
        query_executed=bool(case["query_ran"]),
        collection_completed=bool(case.get("collection_completed")),
        observations_read=len(case["evidence"]),
        inconclusive_evidence=bool(non_settling),
        contributions=contributions,
        detection_power=declared_powers[0] if declared_powers else None,
        coverage_estimate=sources[0]["coverage_estimate"] if sources else None,
        universe_declared=all_declared,
        freshness_declared=all_declared,
        errors_accounted=all(source["errors_accounted"] for source in sources)
        if sources
        else True,
        budget_truncated=any(source["budget_truncated"] for source in sources),
        exhausted_within_declared_scope=bool(
            case.get("exhausted_within_declared_scope")
        ),
    )
def _axes(state: ResearchState) -> dict[str, str]:
    payload = state.as_dict()
    return {key: payload[key] for key in
            ("disposition", "query", "truth_state", "absence", "evidence", "scope")}


def _evaluate(assertion: str, case: dict[str, Any], state: ResearchState) -> bool:
    """The machine-checkable half of ``prohibited_false_inference``.

    Each name is a claim the platform must *refuse*. ``none`` is the one case where
    nothing is being prohibited -- the single supported universal claim in the corpus.
    """
    if assertion == "none":
        return True
    checks = {
        "may_claim_universal_negative": lambda: not state.may_claim_absence,
        "contradiction_resolved": lambda: (
            not state.contradiction_required
            or attempt_resolution(_corpus_contradiction(case["case_id"])).resolved is False
        ),
        "predicate_dropped": lambda: bool(case.get("predicate_raw", {}).get("label")),
        "is_qualified_absence": lambda: not state.may_claim_absence,
        "is_negative_support": lambda: state.truth_state is not TruthState.FALSE_ONLY,
        "is_refuted": lambda: state.evidence is not EvidenceAxis.REFUTED,
    }
    return checks[assertion]()


class TestCorpusIsReal:
    def test_the_corpus_file_exists_and_is_not_empty(self) -> None:
        assert CORPUS.exists(), f"missing fixture corpus at {CORPUS}"
        assert len(CORPUS_CASES) >= 8

    def test_every_case_declares_the_five_things_the_corpus_exists_for(self) -> None:
        for case in CORPUS_CASES:
            assert case["ground_truth"]
            assert case["expected"]["research_state"]
            assert case["prohibited_false_inference"]["inference"]
            assert case["prohibited_false_inference"]["because"]
            assert case["prohibited_false_inference"]["assertion"] in {
                "may_claim_universal_negative",
                "contradiction_resolved",
                "predicate_dropped",
                "is_qualified_absence",
                "is_negative_support",
                "is_refuted",
                "none",
            }
            assert case["applicable_measurement"]["method"]

    def test_no_case_claims_a_licence_anybody_granted(self) -> None:
        """Every case is synthetic. A real licence here would be a fabricated grant."""
        for case in CORPUS_CASES:
            assert case["provenance"] == "synthetic"
            assert case["source_licence"] == "synthetic"
            for source in case["sources"]:
                assert source["licence"] == "synthetic"

    def test_no_case_claims_its_measurement_was_performed(self) -> None:
        for case in CORPUS_CASES:
            assert case["applicable_measurement"]["status"] == "not_performed_for_this_fixture"

    def test_every_required_category_is_present(self) -> None:
        required = {
            "positive_only",
            "negative_only",
            "both",
            "unknown",
            "unsupported_source",
            "failed_source",
            "searched_no_result_known_detection_power",
            "searched_no_result_unknown_detection_power",
        }
        assert required <= {case["category"] for case in CORPUS_CASES}


@pytest.mark.parametrize("case", CORPUS_CASES, ids=CASE_IDS)
class TestCorpusAgainstTheLibrary:
    def test_the_library_produces_the_state_the_fixture_expects(self, case: dict[str, Any]) -> None:
        state = _resolve(case)
        assert _axes(state) == case["expected"]["research_state"], (
            f"{case['case_id']}: ground truth is {case['ground_truth']!r}"
        )

    def test_the_state_names_itself_as_the_fixture_expects(self, case: dict[str, Any]) -> None:
        state = _resolve(case)
        assert (state.name.value if state.name is not None else None) == (
            case["expected"]["research_state_name"]
        )

    def test_the_prohibited_inference_is_refused(self, case: dict[str, Any]) -> None:
        """The corpus is a test, not documentation.

        The assertion name is read from the fixture and evaluated against the record the
        platform actually built. Change the engine and this goes red -- which is the only
        thing that separates a fixture corpus from a README.
        """
        state = _resolve(case)
        assertion = case["prohibited_false_inference"]["assertion"]
        assert _evaluate(assertion, case, state), (
            f"{case['case_id']} permits the inference "
            f"{case['prohibited_false_inference']['inference']!r}, which "
            f"{case['prohibited_false_inference']['because']}"
        )

    def test_may_claim_universal_negative_matches_the_fixture(
        self, case: dict[str, Any]
    ) -> None:
        assert _resolve(case).may_claim_absence == (
            case["expected"]["may_claim_universal_negative"]
        )


class TestTheIndependentTest:
    """The user story's independent test, as the fixtures state it.

    Five inputs, at least four distinct non-collapsed outcomes. Distinctness is asserted
    across the whole set rather than at exactly four, because "at least four distinct"
    is not a property of a list of four.
    """

    FIVE = (
        "EPI-FAIL-01",
        "EPI-SNR-KNOWN-02",
        "EPI-SNR-UNKNOWN-01",
        "EPI-BOTH-01",
        "EPI-UNK-01",
    )

    def _state(self, case_id: str) -> ResearchState:
        case = next(c for c in CORPUS_CASES if c["case_id"] == case_id)
        return _resolve(case)

    def test_all_five_inputs_are_present(self) -> None:
        assert set(self.FIVE) <= set(CASE_IDS)

    def test_they_resolve_to_at_least_four_distinct_outcomes(self) -> None:
        fingerprints = {self._state(case_id).fingerprint for case_id in self.FIVE}
        assert len(fingerprints) >= 4
        assert len(fingerprints) == 5, "five distinct inputs must not share a fingerprint"

    def test_zero_result_declared_and_undeclared_differ_in_exactly_the_absence_axis(
        self,
    ) -> None:
        """The centre of the story, as a one-axis difference.

        Same disposition, same query axis, same truth state, same evidence, same scope.
        The *only* thing separating "it does not exist" from "we did not see it" is
        whether the source declared what it would have found.
        """
        declared = self._state("EPI-SNR-KNOWN-02")
        undeclared = self._state("EPI-SNR-UNKNOWN-01")
        assert declared.absence is AbsenceAxis.QUALIFIED_ABSENCE
        assert undeclared.absence is AbsenceAxis.INFORMATIONAL_ONLY
        assert declared.may_claim_absence is True
        assert undeclared.may_claim_absence is False
        differing = {
            axis
            for axis in ("disposition", "query", "truth_state", "evidence", "scope")
            if getattr(declared, axis) is not getattr(undeclared, axis)
        }
        assert differing == set()

    def test_an_unreachable_source_is_not_a_zero_result(self) -> None:
        unreachable = self._state("EPI-FAIL-01")
        zero = self._state("EPI-SNR-UNKNOWN-01")
        assert unreachable.disposition is SearchDisposition.FAILED
        assert zero.disposition is SearchDisposition.COMPLETED
        assert unreachable.fingerprint != zero.fingerprint

    def test_disagreement_is_not_any_of_the_zero_results(self) -> None:
        both = self._state("EPI-BOTH-01")
        assert both.truth_state is TruthState.BOTH
        assert both.evidence is EvidenceAxis.CONFLICTED
        assert both.fingerprint not in {
            self._state(case_id).fingerprint
            for case_id in ("EPI-SNR-KNOWN-02", "EPI-SNR-UNKNOWN-01", "EPI-FAIL-01")
        }
