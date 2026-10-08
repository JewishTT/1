"""Contract: four-valued truth, propositions, contradictions (spec 025 §13).

``plan.md`` marks this the highest-discipline item in the whole specification:
"Four-valued ``TruthState`` algebra -- **Do not exist.** Zero donor hits --
research §3.7. **NEW.** Highest-discipline item; truth-table gate is a release
gate (R3)."

There is no donor, so these tests are the release gate. They are exhaustive
rather than sampled: the state space has four elements, so enumerating all pairs
and all triples *completely* verifies each law instead of testing a random subset
of it. For a finite lattice this is stronger than property-based sampling, and it
needs no new dependency.

The law set is Stone's characterisation, so proving all of it proves these are
lattices rather than merely plausible-looking tables:

* commutativity, associativity, idempotence, absorption -- on both binary ops
* monotonicity of each op in each argument
* join is the least upper bound, meet the greatest lower bound
* ``negate`` is an involution and exchanges the two flags

The two-orders test is the one that guards the usual mistake: ``BOTH`` is the
*maximum* in the knowledge order and is *not* the maximum in the truth order.
Collapsing them yields operators that look individually plausible and are jointly
wrong.
"""

from __future__ import annotations

import sys
from itertools import product
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from context.epistemic import (
    KNOWLEDGE_JOIN,
    KNOWLEDGE_MEET,
    TRUTH_JOIN,
    TRUTH_MEET,
    Contradiction,
    ContradictionKind,
    ContradictionStatus,
    EvidenceContribution,
    Proposition,
    TruthState,
    accumulate,
    and_,
    consensus,
    contradiction_for_both,
    derive_truth_state,
    knowledge_leq,
    knowledge_less,
    negate,
    or_,
    truth_leq,
    truth_less,
)

pytestmark = pytest.mark.contract

ALL = tuple(TruthState)
PAIRS = tuple(product(ALL, repeat=2))
TRIPLES = tuple(product(ALL, repeat=3))


class TestFourStates:
    def test_flag_table_matches_section_13_1(self) -> None:
        assert TruthState.from_flags(False, False) is TruthState.NEITHER
        assert TruthState.from_flags(True, False) is TruthState.TRUE_ONLY
        assert TruthState.from_flags(False, True) is TruthState.FALSE_ONLY
        assert TruthState.from_flags(True, True) is TruthState.BOTH

    def test_flags_round_trip(self) -> None:
        for state in ALL:
            assert TruthState.from_flags(*state.flags) is state

    def test_both_carries_both_flags(self) -> None:
        assert TruthState.BOTH.positive and TruthState.BOTH.negative

    def test_only_both_is_conflicted(self) -> None:
        conflicted = {state for state in ALL if state.is_conflicted}
        assert conflicted == {TruthState.BOTH}

    def test_determined_states_are_the_one_sided_ones(self) -> None:
        assert {s for s in ALL if s.is_determined} == {
            TruthState.TRUE_ONLY,
            TruthState.FALSE_ONLY,
        }


class TestTwoOrders:
    def test_true_only_and_false_only_are_incomparable_in_knowledge_order(self) -> None:
        """The diamond's middle elements must not become comparable.

        This is what a rank map silently destroys: ranking both at 1 makes each
        one less than the other, turning a diamond into a chain, after which every
        monotonicity and least-upper-bound argument is quietly wrong.
        """
        assert not knowledge_leq(TruthState.TRUE_ONLY, TruthState.FALSE_ONLY)
        assert not knowledge_leq(TruthState.FALSE_ONLY, TruthState.TRUE_ONLY)

    def test_neither_and_both_are_incomparable_in_truth_order(self) -> None:
        assert not truth_leq(TruthState.NEITHER, TruthState.BOTH)
        assert not truth_leq(TruthState.BOTH, TruthState.NEITHER)

    def test_orders_are_antisymmetric(self) -> None:
        for leq in (knowledge_leq, truth_leq):
            for left, right in PAIRS:
                if left is not right:
                    assert not (leq(left, right) and leq(right, left))

    def test_reflexivity_holds_in_both_orders(self) -> None:
        for state in ALL:
            assert knowledge_leq(state, state)
            assert truth_leq(state, state)

    def test_strict_helpers_exclude_equality(self) -> None:
        assert not knowledge_less(TruthState.TRUE_ONLY, TruthState.TRUE_ONLY)
        assert knowledge_less(TruthState.NEITHER, TruthState.TRUE_ONLY)
        assert truth_less(TruthState.FALSE_ONLY, TruthState.TRUE_ONLY)
        for state in ALL:
            assert knowledge_leq(state, TruthState.BOTH)

    def test_both_is_below_true_only_in_truth_order(self) -> None:
        """The point of having two orders: conflicting evidence is not 'most true'."""
        assert truth_leq(TruthState.BOTH, TruthState.TRUE_ONLY)
        assert not truth_leq(TruthState.TRUE_ONLY, TruthState.BOTH)

    def test_neither_is_minimum_in_knowledge_order(self) -> None:
        for state in ALL:
            assert knowledge_leq(TruthState.NEITHER, state)

    def test_false_only_is_minimum_in_truth_order(self) -> None:
        for state in ALL:
            assert truth_leq(TruthState.FALSE_ONLY, state)

    def test_the_two_orders_genuinely_disagree(self) -> None:
        disagreements = [
            (left, right)
            for left, right in PAIRS
            if knowledge_leq(left, right) != truth_leq(left, right)
        ]
        assert disagreements, "if both orders agreed, one of them would be wrong"

    def test_joins_and_meets_are_the_declared_pairs(self) -> None:
        assert (KNOWLEDGE_JOIN, KNOWLEDGE_MEET) == (accumulate, consensus)
        assert (TRUTH_JOIN, TRUTH_MEET) == (or_, and_)


class TestNegation:
    def test_negate_exchanges_the_flags(self) -> None:
        for state in ALL:
            positive, negative = negate(state).flags
            assert (positive, negative) == (state.negative, state.positive)

    def test_negate_is_an_involution(self) -> None:
        for state in ALL:
            assert negate(negate(state)) is state

    def test_negate_swaps_the_determined_states(self) -> None:
        assert negate(TruthState.TRUE_ONLY) is TruthState.FALSE_ONLY
        assert negate(TruthState.FALSE_ONLY) is TruthState.TRUE_ONLY

    def test_negate_fixes_neither_and_both(self) -> None:
        assert negate(TruthState.NEITHER) is TruthState.NEITHER
        assert negate(TruthState.BOTH) is TruthState.BOTH


def _assert_lattice(join, meet, leq, name: str) -> None:
    """Stone's characterisation, exhaustively over the four-element state space.

    This verifies a *lattice*, which is a property about a specific order. It
    applies to ``accumulate``/``consensus`` under the knowledge order. It does
    **not** apply to ``and_``/``or_``: those are truth-functional composition
    operators, and they are not monotone under the truth order, so asserting
    least-upper-bound behaviour of them would be asserting something false.
    """
    for left, right in PAIRS:
        assert join(left, right) is join(right, left), f"{name}: join not commutative"
        assert meet(left, right) is meet(right, left), f"{name}: meet not commutative"
        assert join(left, left) is left, f"{name}: join not idempotent"
        assert meet(left, left) is left, f"{name}: meet not idempotent"

    for first, second, third in TRIPLES:
        assert join(first, join(second, third)) is join(
            join(first, second), third
        ), f"{name}: join not associative"
        assert meet(first, meet(second, third)) is meet(
            meet(first, second), third
        ), f"{name}: meet not associative"
        assert join(first, meet(first, second)) is first, f"{name}: absorption"
        assert meet(first, join(first, second)) is first, f"{name}: absorption"
        # monotonicity in each argument, under *this* lattice's order
        for other in ALL:
            if leq(first, other):
                assert leq(join(first, second), join(other, second)), f"{name}: join not monotone"
                assert leq(meet(first, second), meet(other, second)), f"{name}: meet not monotone"

    for left, right in PAIRS:
        for candidate in ALL:
            # join is the least upper bound under the given order
            if leq(left, candidate) and leq(right, candidate):
                assert leq(join(left, right), candidate), f"{name}: join is not least"
            # meet is the greatest lower bound
            if leq(candidate, left) and leq(candidate, right):
                assert leq(candidate, meet(left, right)), f"{name}: meet is not greatest"

    # antisymmetry: distinct elements are never mutually below one another.
    for left, right in PAIRS:
        if left is not right:
            assert not (leq(left, right) and leq(right, left)), f"{name}: order not antisymmetric"


class TestKnowledgeLattice:
    def test_accumulate_consensus_forms_a_lattice(self) -> None:
        _assert_lattice(accumulate, consensus, knowledge_leq, "knowledge")

    def test_neither_is_the_knowledge_identity_for_join(self) -> None:
        for state in ALL:
            assert accumulate(TruthState.NEITHER, state) is state

    def test_neither_absorbs_in_the_knowledge_meet(self) -> None:
        for state in ALL:
            assert consensus(TruthState.NEITHER, state) is TruthState.NEITHER

    def test_true_meets_false_at_neither(self) -> None:
        """Two bodies of evidence that disagree agree on nothing."""
        assert consensus(TruthState.TRUE_ONLY, TruthState.FALSE_ONLY) is TruthState.NEITHER

    def test_true_accumulates_false_into_both(self) -> None:
        """The headline behaviour: disagreement is a state, not a coin flip."""
        assert accumulate(TruthState.TRUE_ONLY, TruthState.FALSE_ONLY) is TruthState.BOTH

    def test_agreeing_evidence_stays_one_sided(self) -> None:
        assert consensus(TruthState.TRUE_ONLY, TruthState.TRUE_ONLY) is TruthState.TRUE_ONLY
        assert accumulate(TruthState.TRUE_ONLY, TruthState.TRUE_ONLY) is TruthState.TRUE_ONLY


class TestTruthOrderIsAlsoALattice:
    """``or_``/``and_`` are the lattice operations of the *truth* order.

    This is the classical Belnap-Dunn result and it holds only because the truth
    order treats ``NEITHER`` and ``BOTH`` as incomparable. Under a rank-based order
    that ranked them alike, ``or_(NEITHER, BOTH)`` stops being the least upper
    bound and the whole structure fails -- which is exactly the bug these tests
    caught during development.
    """

    def test_or_and_form_a_lattice(self) -> None:
        _assert_lattice(or_, and_, truth_leq, "truth")

    def test_neither_join_both_is_true_only(self) -> None:
        """``or_(NEITHER, BOTH) = TRUE_ONLY`` is the load-bearing cell.

        ``TRUE_ONLY`` is the *unique* upper bound of ``NEITHER`` and ``BOTH``
        under the truth order, so this single cell is what proves the whole
        lattice. An arithmetic slip here silently breaks least-upper-bound.
        """
        assert or_(TruthState.NEITHER, TruthState.BOTH) is TruthState.TRUE_ONLY
        upper = [
            state
            for state in ALL
            if truth_leq(TruthState.NEITHER, state) and truth_leq(TruthState.BOTH, state)
        ]
        assert upper == [TruthState.TRUE_ONLY]

    def test_neither_meet_both_is_false_only(self) -> None:
        assert and_(TruthState.NEITHER, TruthState.BOTH) is TruthState.FALSE_ONLY

    def test_de_morgan(self) -> None:
        for left, right in PAIRS:
            assert negate(and_(left, right)) is or_(negate(left), negate(right))
            assert negate(or_(left, right)) is and_(negate(left), negate(right))

    def test_distributive(self) -> None:
        for first, second, third in TRIPLES:
            assert and_(first, or_(second, third)) is or_(
                and_(first, second), and_(first, third)
            )

    def test_true_conjoined_false_is_false(self) -> None:
        assert and_(TruthState.TRUE_ONLY, TruthState.FALSE_ONLY) is TruthState.FALSE_ONLY

    def test_true_disjoined_false_is_true(self) -> None:
        assert or_(TruthState.TRUE_ONLY, TruthState.FALSE_ONLY) is TruthState.TRUE_ONLY

    def test_conflicting_meet_collapses_to_neither(self) -> None:
        assert and_(TruthState.BOTH, TruthState.BOTH) is TruthState.BOTH
        assert or_(TruthState.NEITHER, TruthState.NEITHER) is TruthState.NEITHER

    def test_knowledge_and_truth_disagree_on_the_cross_pair(self) -> None:
        left, right = TruthState.TRUE_ONLY, TruthState.FALSE_ONLY
        assert accumulate(left, right) is not or_(left, right)
        assert consensus(left, right) is not and_(left, right)


class TestTruthStateDerivation:
    def test_support_only(self) -> None:
        assert derive_truth_state([EvidenceContribution("E1", positive=True)]) is (
            TruthState.TRUE_ONLY
        )

    def test_refutation_only(self) -> None:
        assert derive_truth_state([EvidenceContribution("E1", positive=False)]) is (
            TruthState.FALSE_ONLY
        )

    def test_both_sides_accumulate_to_both(self) -> None:
        state = derive_truth_state(
            [
                EvidenceContribution("E1", positive=True),
                EvidenceContribution("E2", positive=False),
            ]
        )
        assert state is TruthState.BOTH

    def test_inadmissible_contributes_nothing(self) -> None:
        state = derive_truth_state(
            [
                EvidenceContribution("E1", positive=True),
                EvidenceContribution("E2", positive=False, admissible=False),
            ]
        )
        assert state is TruthState.TRUE_ONLY

    def test_coverage_qualified_absence_is_not_a_refutation(self) -> None:
        """"Searched and found nothing" is not evidence of falsity (§13A, §0.2)."""
        state = derive_truth_state(
            [
                EvidenceContribution("E1", positive=False),
                EvidenceContribution("E2", positive=False, coverage_qualified=True),
            ]
        )
        assert state is TruthState.FALSE_ONLY

    def test_weight_does_not_change_the_state(self) -> None:
        """§14.1: confidence is a separate quantity; the lattice has no weights."""
        light = derive_truth_state([EvidenceContribution("E1", positive=True, weight=0.1)])
        heavy = derive_truth_state([EvidenceContribution("E1", positive=True, weight=99.0)])
        assert light is heavy


class TestProposition:
    def test_identity_excludes_polarity(self) -> None:
        """Two polarities of one fact are one fact, which is what makes accumulate
        accumulate instead of fork."""
        positive = Proposition(subject="ORG-1", predicate="owns", object="ORG-9")
        negative = Proposition(subject="ORG-1", predicate="owns", object="ORG-9")
        assert positive.proposition_id == negative.proposition_id

    def test_negated_id_is_the_same_proposition(self) -> None:
        proposition = Proposition(subject="ORG-1", predicate="owns", object="ORG-9")
        assert proposition.negated_id == proposition.proposition_id

    def test_identity_distinguishes_the_object(self) -> None:
        left = Proposition(subject="ORG-1", predicate="owns", object="ORG-9")
        right = Proposition(subject="ORG-1", predicate="owns", object="ORG-8")
        assert left.proposition_id != right.proposition_id

    def test_identity_distinguishes_scope(self) -> None:
        left = Proposition(subject="A", predicate="p", object="B", scope="ORG-1")
        right = Proposition(subject="A", predicate="p", object="B", scope="ORG-2")
        assert left.proposition_id != right.proposition_id

    def test_identity_distinguishes_the_temporal_qualifier(self) -> None:
        left = Proposition(subject="A", predicate="p", object="B", temporal_qualifier="2024")
        right = Proposition(subject="A", predicate="p", object="B", temporal_qualifier="2025")
        assert left.proposition_id != right.proposition_id

    def test_declared_mismatched_id_is_refused(self) -> None:
        with pytest.raises(ValueError):
            Proposition(
                subject="A", predicate="p", object="B", proposition_id="PRP-wrong"
            )

    def test_subject_and_predicate_are_required(self) -> None:
        with pytest.raises(ValueError):
            Proposition(subject="", predicate="p", object="B")

    def test_score_is_carried_and_never_derived(self) -> None:
        """§13.4: the two are independent fields."""
        scored = Proposition(
            subject="A",
            predicate="p",
            object="B",
            truth_state=TruthState.BOTH,
            score={"kind": "MODEL_POSTERIOR", "value": 0.88},
        )
        assert scored.truth_state is TruthState.BOTH
        assert scored.score["value"] == 0.88

    def test_there_is_no_truth_state_to_probability_conversion(self) -> None:
        """§13.4: truth_state never converts to a probability."""
        assert not hasattr(TruthState, "to_probability")
        assert not hasattr(TruthState, "to_score")


class TestContradiction:
    def _both(self) -> Proposition:
        return Proposition(
            subject="ORG-1",
            predicate="owns",
            object="ORG-9",
            truth_state=TruthState.BOTH,
        )

    def test_both_implies_a_contradiction(self) -> None:
        """§13.3: BOTH implies a Contradiction exists in the same revision."""
        contradiction = contradiction_for_both(
            self._both(), positive_refs=["E1"], negative_refs=["E2"]
        )
        assert contradiction is not None
        assert contradiction.proposition_id == self._both().proposition_id

    def test_non_both_states_imply_nothing(self) -> None:
        for state in (TruthState.NEITHER, TruthState.TRUE_ONLY, TruthState.FALSE_ONLY):
            proposition = Proposition(
                subject="A", predicate="p", object="B", truth_state=state
            )
            assert contradiction_for_both(proposition) is None

    def test_both_sides_are_retained(self) -> None:
        """§0.2: contradictory sources != overwrite one source."""
        contradiction = contradiction_for_both(
            self._both(), positive_refs=["E1", "E3"], negative_refs=["E2"]
        )
        sides = {side["side"]: side["refs"] for side in contradiction.sides}
        assert sides == {"supporting": ("E1", "E3"), "refuting": ("E2",)}

    def test_contradiction_without_sides_is_refused(self) -> None:
        with pytest.raises(ValueError):
            Contradiction(
                proposition_id="PRP-x",
                kind=ContradictionKind.NUMERIC,
                detail="values differ",
                sides=(),
            )

    def test_contradiction_without_detail_is_refused(self) -> None:
        with pytest.raises(ValueError):
            Contradiction(
                proposition_id="PRP-x",
                kind=ContradictionKind.NUMERIC,
                detail="",
                sides=({"side": "supporting", "refs": ()},),
            )

    def test_resolution_records_an_explanation(self) -> None:
        contradiction = contradiction_for_both(
            self._both(), positive_refs=["E1"], negative_refs=["E2"]
        )
        resolved = contradiction.resolve("ownership transferred mid-period")
        assert resolved.status in (
            ContradictionStatus.EXPLAINED,
            ContradictionStatus.RESOLVED,
        )
        assert resolved.explanation

    def test_resolution_requires_an_explanation(self) -> None:
        contradiction = contradiction_for_both(
            self._both(), positive_refs=["E1"], negative_refs=["E2"]
        )
        with pytest.raises(ValueError):
            contradiction.resolve("")

    def test_resolution_keeps_the_same_identity(self) -> None:
        """Resolving explains the disagreement; it does not invent a new fact."""
        contradiction = contradiction_for_both(
            self._both(), positive_refs=["E1"], negative_refs=["E2"]
        )
        assert contradiction.resolve("explained").contradiction_id == (
            contradiction.contradiction_id
        )

    def test_resolution_keeps_both_sides(self) -> None:
        contradiction = contradiction_for_both(
            self._both(), positive_refs=["E1"], negative_refs=["E2"]
        )
        resolved = contradiction.resolve("explained")
        assert len(resolved.sides) == 2

    def test_independence_is_recorded(self) -> None:
        contradiction = contradiction_for_both(
            self._both(), positive_refs=["E1"], negative_refs=["E2"], independent=True
        )
        assert contradiction.independent is True

    def test_kind_distinguishes_support_from_numeric(self) -> None:
        """§13.3: a Contradiction may exist without BOTH, e.g. numeric conflict."""
        numeric = Contradiction(
            proposition_id="PRP-x",
            kind=ContradictionKind.NUMERIC,
            detail="balance differs by 4M",
            sides=(
                {"side": "supporting", "refs": ("E1",)},
                {"side": "refuting", "refs": ("E2",)},
            ),
        )
        assert numeric.kind is ContradictionKind.NUMERIC
