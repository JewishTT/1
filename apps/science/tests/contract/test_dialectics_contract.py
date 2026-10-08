"""Contract: hypothesis spaces, lifecycle, dialectical pairing (§15.3, §15.4, §18).

§15.3 opens with why a space has to be an object: "Posteriors and information gain
are only meaningful relative to a declared space." A confidence figure without the
space it ranges over is a number without a denominator.

``apps/science/hypotheses/model.py`` already has a 7-state lifecycle over a flat
list -- real, tested code, kept. What it cannot express is exclusivity,
compatibility, exhaustiveness or residual mass. These tests pin the additions.

The four §15.3 rules enforced here:

1. a non-exhaustive space must carry ``H_OTHER``;
2. probabilities normalise only within an exclusivity group, never against
   compatible members that may be jointly true;
3. ``H_OTHER`` mass shrinks only by evidence or by admitting a concrete hypothesis
   -- and shrinks, rather than being deleted;
4. ``CONFIRMED`` is revisable, ``SUPERSEDED`` is terminal, ``PROPOSED ->
   CONFIRMED`` is forbidden.

§18.5 steelman parity is pinned because a counter-hypothesis built under weaker
conditions than the thesis it opposes is a straw man, and the engine then reports
that the thesis survived.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from context.dialectics import (
    FORBIDDEN_TRANSITIONS,
    LIFECYCLE,
    CounterHypothesisOutcome,
    DialecticalPair,
    Exhaustive,
    Hypothesis,
    HypothesisSpace,
    HypothesisStatus,
    HypothesisTransitionError,
    ResolutionState,
    SteelmanParity,
    can_transition,
    generate_counter_hypotheses,
    revise_pair,
    transition,
)

pytestmark = pytest.mark.contract

CTX = "CXI-test"
PARITY = SteelmanParity(
    same_evidence_view=True,
    same_template_family=True,
    same_complexity_bound=True,
    same_assumption_budget=True,
)


def _space(**kwargs) -> HypothesisSpace:
    a = Hypothesis("direct ownership", posterior=0.7, local_id="LHYP-a")
    b = Hypothesis("nominee control", posterior=0.0, local_id="LHYP-b")
    return HypothesisSpace(
        context_id=CTX,
        question="who controls the SPV?",
        members=(a, b, Hypothesis.residual(0.3)),
        exclusivity_groups=(frozenset({"LHYP-a", "LHYP-b"}),),
        exhaustive=Exhaustive.FALSE,
        **kwargs,
    )


class TestLifecycle:
    def test_seven_states(self) -> None:
        assert len(list(HypothesisStatus)) == 7

    def test_superseded_is_terminal(self) -> None:
        assert LIFECYCLE[HypothesisStatus.SUPERSEDED] == frozenset()

    def test_proposed_to_confirmed_is_forbidden(self) -> None:
        """§15.4 names this pair explicitly."""
        assert (HypothesisStatus.PROPOSED, HypothesisStatus.CONFIRMED) in (
            FORBIDDEN_TRANSITIONS
        )
        assert can_transition(
            HypothesisStatus.PROPOSED, HypothesisStatus.CONFIRMED
        ) is False
        with pytest.raises(HypothesisTransitionError):
            transition(HypothesisStatus.PROPOSED, HypothesisStatus.CONFIRMED)

    def test_confirmation_is_revisable(self) -> None:
        """§15.4: 'confirmation is revisable by contrary evidence'."""
        assert can_transition(HypothesisStatus.CONFIRMED, HypothesisStatus.CONTESTED)

    def test_illegal_jumps_are_refused(self) -> None:
        with pytest.raises(HypothesisTransitionError):
            transition(HypothesisStatus.ACTIVE, HypothesisStatus.PROPOSED)

    def test_every_declared_transition_is_permitted(self) -> None:
        for current, targets in LIFECYCLE.items():
            for target in targets:
                assert can_transition(current, target), (current, target)

    def test_declared_targets_are_all_reachable(self) -> None:
        for targets in LIFECYCLE.values():
            for target in targets:
                assert target in HypothesisStatus


class TestSpaceRequiresResidual:
    def test_non_exhaustive_space_without_residual_is_refused(self) -> None:
        with pytest.raises(ValueError) as excinfo:
            HypothesisSpace(
                context_id=CTX,
                question="q",
                members=(
                    Hypothesis("a", local_id="LHYP-a"),
                    Hypothesis("b", local_id="LHYP-b"),
                ),
                exhaustive=Exhaustive.FALSE,
            )
        assert "RESIDUAL" in str(excinfo.value)

    def test_unknown_exhaustiveness_also_requires_a_residual(self) -> None:
        with pytest.raises(ValueError):
            HypothesisSpace(
                context_id=CTX,
                question="q",
                members=(Hypothesis("a", local_id="LHYP-a"),),
                exhaustive=Exhaustive.UNKNOWN,
            )

    def test_exhaustive_space_needs_no_residual(self) -> None:
        space = HypothesisSpace(
            context_id=CTX,
            question="q",
            members=(
                Hypothesis("a", posterior=0.6, local_id="LHYP-a"),
                Hypothesis("b", posterior=0.4, local_id="LHYP-b"),
            ),
            exclusivity_groups=(frozenset({"LHYP-a", "LHYP-b"}),),
            exhaustive=Exhaustive.TRUE,
        )
        assert space.residual is None
        assert space.unaccounted_mass() == 0.0

    def test_two_residuals_are_refused(self) -> None:
        with pytest.raises(ValueError):
            HypothesisSpace(
                context_id=CTX,
                question="q",
                members=(Hypothesis.residual(0.2), Hypothesis.residual(0.3)),
                exhaustive=Exhaustive.FALSE,
            )

    def test_a_space_with_no_members_is_refused(self) -> None:
        with pytest.raises(ValueError):
            HypothesisSpace(context_id=CTX, question="q", members=())

    def test_a_space_without_a_question_is_refused(self) -> None:
        with pytest.raises(ValueError):
            HypothesisSpace(
                context_id=CTX,
                question="",
                members=(Hypothesis("a", local_id="LHYP-a"),),
                exhaustive=Exhaustive.TRUE,
            )

    def test_residual_prior_mass_must_be_open(self) -> None:
        with pytest.raises(ValueError):
            Hypothesis.residual(0.0)
        with pytest.raises(ValueError):
            Hypothesis.residual(1.0)


class TestResidualIsDerived:
    """Regression: the residual was a separate field and could disagree with members."""

    def test_residual_is_read_from_members(self) -> None:
        space = _space()
        assert space.residual is not None
        assert space.residual in space.members

    def test_evidence_movement_updates_the_residual(self) -> None:
        moved = _space().with_posterior_evidence(
            {"LHYP-a": 0.85, "LHYP-residual": 0.15}
        )
        assert moved.residual is not None
        assert moved.residual.posterior == pytest.approx(0.15)


class TestExclusivity:
    def test_exclusive_pair_is_recognised(self) -> None:
        space = _space()
        assert space.is_exclusive_with("LHYP-a", "LHYP-b") is True

    def test_normalisation_happens_within_the_group(self) -> None:
        """Only competitors' mass is renormalised, never the residual's."""
        space = HypothesisSpace(
            context_id=CTX,
            question="who controls the SPV?",
            members=(
                Hypothesis("direct ownership", posterior=0.6, local_id="LHYP-a"),
                Hypothesis("nominee control", posterior=0.2, local_id="LHYP-b"),
                Hypothesis.residual(0.2),
            ),
            exclusivity_groups=(frozenset({"LHYP-a", "LHYP-b"}),),
            exhaustive=Exhaustive.FALSE,
        )
        distribution, reason = space.normalise_group("LHYP-a")
        assert reason == ""
        # LHYP-b is the sole competitor, so it takes the whole relative share.
        assert distribution == {"LHYP-b": 1.0}

    def test_normalisation_shares_mass_between_two_competitors(self) -> None:
        space = HypothesisSpace(
            context_id=CTX,
            question="q",
            members=(
                Hypothesis("a", posterior=0.6, local_id="LHYP-a"),
                Hypothesis("b", posterior=0.2, local_id="LHYP-b"),
                Hypothesis("c", posterior=0.2, local_id="LHYP-c"),
            ),
            exclusivity_groups=(frozenset({"LHYP-a", "LHYP-b", "LHYP-c"}),),
            exhaustive=Exhaustive.TRUE,
        )
        distribution, reason = space.normalise_group("LHYP-a")
        assert reason == ""
        assert distribution == {"LHYP-b": 0.5, "LHYP-c": 0.5}
        assert sum(distribution.values()) == pytest.approx(1.0)

    def test_compatible_members_are_never_normalised_against_each_other(self) -> None:
        """§15.3: dividing jointly-true hypotheses would force a false choice."""
        space = HypothesisSpace(
            context_id=CTX,
            question="q",
            members=(
                Hypothesis("a", posterior=0.5, local_id="LHYP-a"),
                Hypothesis("b", posterior=0.5, local_id="LHYP-b"),
                Hypothesis.residual(0.5),
            ),
            compatible_pairs=(("LHYP-a", "LHYP-b"),),
            exhaustive=Exhaustive.FALSE,
        )
        assert space.is_exclusive_with("LHYP-a", "LHYP-b") is False
        assert space.is_declared_compatible("LHYP-a", "LHYP-b") is True
        _distribution, reason = space.normalise_group("LHYP-a")
        assert "no exclusivity group" in reason

    def test_group_naming_an_unknown_member_is_refused(self) -> None:
        with pytest.raises(ValueError):
            HypothesisSpace(
                context_id=CTX,
                question="q",
                members=(Hypothesis("a", local_id="LHYP-a"),),
                exclusivity_groups=(frozenset({"LHYP-a", "LHYP-ghost"}),),
                exhaustive=Exhaustive.TRUE,
            )

    def test_a_group_of_one_is_refused(self) -> None:
        with pytest.raises(ValueError):
            HypothesisSpace(
                context_id=CTX,
                question="q",
                members=(Hypothesis("a", local_id="LHYP-a"),),
                exclusivity_groups=(frozenset({"LHYP-a"}),),
                exhaustive=Exhaustive.TRUE,
            )

    def test_normalisation_without_competitor_mass_says_so(self) -> None:
        space = HypothesisSpace(
            context_id=CTX,
            question="q",
            members=(
                Hypothesis("a", posterior=0.0, local_id="LHYP-a"),
                Hypothesis("b", posterior=0.0, local_id="LHYP-b"),
                Hypothesis.residual(0.5),
            ),
            exclusivity_groups=(frozenset({"LHYP-a", "LHYP-b"}),),
            exhaustive=Exhaustive.FALSE,
        )
        _distribution, reason = space.normalise_group("LHYP-a")
        assert "no posterior mass" in reason


class TestResidualShrinks:
    def test_admitting_a_member_takes_residual_mass(self) -> None:
        space = _space().with_admitted_member(
            Hypothesis("state control", local_id="LHYP-new"), takes=0.15
        )
        assert space.member("LHYP-new").posterior == pytest.approx(0.15)
        assert space.residual is not None
        assert space.residual.posterior == pytest.approx(0.15)

    def test_admitting_preserves_total_mass(self) -> None:
        space = _space().with_admitted_member(
            Hypothesis("state control", local_id="LHYP-new"), takes=0.15
        )
        assert space.posterior_total() == pytest.approx(1.0)

    def test_taking_the_whole_residual_needs_a_declared_exhaustive_space(self) -> None:
        with pytest.raises(ValueError) as excinfo:
            _space().with_admitted_member(Hypothesis("x", local_id="LHYP-x"))
        assert "exhaustive" in str(excinfo.value)

    def test_declaring_exhaustive_drops_the_residual(self) -> None:
        space = _space().with_admitted_member(
            Hypothesis("z", local_id="LHYP-z"), exhaustive=Exhaustive.TRUE
        )
        assert space.residual is None
        assert space.posterior_total() == pytest.approx(1.0)

    def test_taking_more_than_the_residual_holds_is_refused(self) -> None:
        with pytest.raises(ValueError):
            _space().with_admitted_member(Hypothesis("w", local_id="LHYP-w"), takes=0.9)

    def test_admitting_the_residual_itself_is_refused(self) -> None:
        with pytest.raises(ValueError):
            _space().with_admitted_member(Hypothesis.residual(0.1), takes=0.05)

    def test_evidence_is_the_other_only_route(self) -> None:
        space = _space().with_posterior_evidence({"LHYP-residual": 0.1})
        assert space.residual.posterior == pytest.approx(0.1)


class TestDialecticalPair:
    def _pair(self, parity: SteelmanParity = PARITY, **kwargs) -> DialecticalPair:
        thesis = Hypothesis(
            "direct ownership",
            local_id="LHYP-a",
            assumptions=("registry is current", "no nominee"),
        )
        antithesis = Hypothesis(
            "nominee control",
            local_id="LHYP-b",
            assumptions=("registry is current", "nominee exists"),
        )
        return DialecticalPair(
            context_id=CTX, thesis=thesis, antithesis=antithesis, parity=parity, **kwargs
        )

    def test_common_premises_are_extracted(self) -> None:
        pair = self._pair()
        assert pair.shared_between() == ("registry is current",)

    def test_disputed_premises_are_extracted(self) -> None:
        pair = self._pair()
        assert pair.disputed_between() == ("no nominee", "nominee exists")

    def test_a_pair_needs_two_distinct_hypotheses(self) -> None:
        thesis = Hypothesis("x", local_id="LHYP-a")
        with pytest.raises(ValueError):
            DialecticalPair(
                context_id=CTX, thesis=thesis, antithesis=thesis, parity=PARITY
            )

    def test_the_residual_cannot_be_a_dialectical_participant(self) -> None:
        thesis = Hypothesis("x", local_id="LHYP-a")
        with pytest.raises(ValueError):
            DialecticalPair(
                context_id=CTX, thesis=thesis, antithesis=Hypothesis.residual(0.2),
                parity=PARITY,
            )

    def test_parity_failure_is_recorded_not_hidden(self) -> None:
        weak = SteelmanParity(
            same_evidence_view=False,
            same_template_family=True,
            same_complexity_bound=False,
            same_assumption_budget=True,
        )
        assert weak.is_parity is False
        assert set(weak.failures) == {"evidence_view", "complexity_bound"}
        assert weak.as_dict()["parity"] is False

    def test_a_parity_failure_still_produces_a_recorded_pair(self) -> None:
        """The failure is a finding about the engine, so it must be recorded."""
        weak = SteelmanParity(same_evidence_view=False, same_template_family=False,
                              same_complexity_bound=False, same_assumption_budget=False)
        pair = self._pair(parity=weak)
        assert pair.as_dict()["parity_audit"]["parity"] is False

    def test_a_new_pair_starts_open(self) -> None:
        assert self._pair().resolution_state is ResolutionState.OPEN


class TestCounterHypothesisGeneration:
    def _space(self) -> HypothesisSpace:
        return HypothesisSpace(
            context_id=CTX,
            question="q",
            members=(
                Hypothesis("direct", local_id="LHYP-a"),
                Hypothesis("nominee", local_id="LHYP-b"),
            ),
            exhaustive=Exhaustive.TRUE,
        )

    def test_generation_produces_pairs(self) -> None:
        space = self._space()
        thesis = space.member("LHYP-a")
        counter = space.member("LHYP-b")
        pairs, outcome = generate_counter_hypotheses(
            space, thesis, templates=(("nominee", counter),)
        )
        assert outcome is CounterHypothesisOutcome.GENERATED
        assert len(pairs) == 1

    def test_insufficient_evidence_is_named(self) -> None:
        space = self._space()
        pairs, outcome = generate_counter_hypotheses(
            space, space.member("LHYP-a"), templates=(), evidence_available=False
        )
        assert outcome is CounterHypothesisOutcome.INSUFFICIENT_EVIDENCE
        assert pairs == ()

    def test_budget_exhaustion_is_named(self) -> None:
        space = self._space()
        _pairs, outcome = generate_counter_hypotheses(
            space,
            space.member("LHYP-a"),
            templates=(("nominee", space.member("LHYP-b")),),
            budget=0,
        )
        assert outcome is CounterHypothesisOutcome.BUDGET_EXHAUSTED

    def test_a_duplicate_template_is_named(self) -> None:
        space = self._space()
        thesis = space.member("LHYP-a")
        _pairs, outcome = generate_counter_hypotheses(
            space, thesis, templates=(("self", thesis),)
        )
        assert outcome is CounterHypothesisOutcome.COUNTERHYPOTHESIS_DUPLICATE

    def test_no_valid_counterhypothesis_is_a_result_not_a_skip(self) -> None:
        space = self._space()
        discarded = Hypothesis("dead", local_id="LHYP-z", status=HypothesisStatus.DISCARDED)
        _pairs, outcome = generate_counter_hypotheses(
            space, discarded, templates=(("n", space.member("LHYP-b")),)
        )
        assert outcome is CounterHypothesisOutcome.NO_VALID_COUNTERHYPOTHESIS

    def test_five_outcomes_exist(self) -> None:
        """§18.4 lists exactly these."""
        assert len(list(CounterHypothesisOutcome)) == 5

    def test_revision_keeps_the_pair_open(self) -> None:
        thesis = Hypothesis("a", local_id="LHYP-a")
        antithesis = Hypothesis("b", local_id="LHYP-b")
        pair = DialecticalPair(
            context_id=CTX, thesis=thesis, antithesis=antithesis, parity=PARITY
        )
        revised = revise_pair(
            pair,
            differential_predictions=("registry shows ORG-A"),
            discriminating_tests=("pull the SPV filing"),
        )
        assert revised.differential_predictions
        assert revised.discriminating_tests
        assert revised.resolution_state is ResolutionState.OPEN

    def test_inconclusive_stays_inconclusive(self) -> None:
        assert ResolutionState.INCONCLUSIVE.value == "inconclusive"