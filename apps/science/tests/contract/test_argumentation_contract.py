"""Contract: ranking under a declared mode (spec 025 §20.3, §46.1).

§20.3 removes the v1 multiplicative utility outright -- ``IG x feasibility x
quality x discrimination / cost`` -- and replaces it with six rules. The one that
matters most in practice is rule 1: hard gates are *filters*, not factors. In a
multiplicative formula a candidate blocked by policy can still win by having a
large enough gain, because the gain multiplies and the blocker does not. A safety
filter that can be outvoted by a good score is not a safety filter.

Also pinned here:

* no cross-tier numeric comparison (§20.3 rule 3);
* the declared cost floor, so zero or unknown cost cannot divide out (rule 5);
* the ranking mode is *returned*, because rule 6 requires every transformation to
  be declared in the profile and echoed;
* dominance requires strict improvement somewhere (§46.1), so equal-valued
  candidates never dominate one another.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from context.argumentation import (
    Candidate,
    GainTier,
    RankingMode,
    _dominated_by,
    dominance_front,
    effective_cost,
    rank_candidates,
)

pytestmark = pytest.mark.contract


class TestModesMatchTheSpec:
    def test_exactly_three_modes(self) -> None:
        assert len(list(RankingMode)) == 3

    def test_mode_names_are_spelled_as_specified(self) -> None:
        assert {mode.value for mode in RankingMode} == {
            "LEXICOGRAPHIC",
            "PARETO_THEN_TIEBREAK",
            "WEIGHTED_ADDITIVE_NORMALIZED",
        }

    def test_gain_tiers_are_spelled_as_specified(self) -> None:
        assert GainTier.IG_PROBABILISTIC.value == "IG_PROBABILISTIC"
        assert GainTier.SURROGATE_SEPARATION.value == "SURROGATE_SEPARATION"

    def test_an_unknown_mode_is_refused(self) -> None:
        with pytest.raises(ValueError):
            rank_candidates([], mode="MULTIPLICATIVE_UTILITY")


class TestHardGatesAreFilters:
    """§20.3 rule 1. The removed formula let a good score outvote a safety block."""

    def test_policy_blocked_candidate_is_excluded_not_downweighted(self) -> None:
        blocked = Candidate("D-policy", {"gain": 100.0}, policy_allowed=False)
        allowed = Candidate("C-ok", {"gain": 5.0})
        result = rank_candidates(
            [blocked, allowed], mode="LEXICOGRAPHIC", criteria_order=("gain",)
        )
        assert result["ranked"] == ["C-ok"]
        assert blocked.blocked_reason == "policy"

    def test_the_block_is_recorded_with_its_reason(self) -> None:
        blocked = Candidate("D", {"gain": 1.0}, safety_clear=False)
        result = rank_candidates([blocked], mode="LEXICOGRAPHIC")
        assert result["blocked"] == [{"candidate_id": "D", "reason": "safety"}]

    @pytest.mark.parametrize(
        ("kwargs", "expected"),
        [
            ({"policy_allowed": False}, "policy"),
            ({"capabilities_available": False}, "capability"),
            ({"safety_clear": False}, "safety"),
            ({"feasible": False}, "feasibility"),
            ({}, ""),
        ],
    )
    def test_each_filter_names_itself(self, kwargs, expected) -> None:
        assert Candidate("X", {"gain": 1.0}, **kwargs).blocked_reason == expected

    def test_a_viable_candidate_has_no_reason(self) -> None:
        assert Candidate("X", {"gain": 1.0}).is_viable is True


class TestNoCrossTierComparison:
    """§20.3 rule 3."""

    def test_a_larger_surrogate_value_does_not_beat_a_probabilistic_one(self) -> None:
        probabilistic = Candidate(
            "P", {}, gain_tier=GainTier.IG_PROBABILISTIC, gain_value=0.1
        )
        surrogate = Candidate(
            "S", {}, gain_tier=GainTier.SURROGATE_SEPARATION, gain_value=0.9
        )
        result = rank_candidates([probabilistic, surrogate], mode="LEXICOGRAPHIC")
        assert result["ranked"][0] == "P"

    def test_candidates_within_a_tier_still_compare(self) -> None:
        low = Candidate("L", {}, gain_tier=GainTier.IG_PROBABILISTIC, gain_value=0.2)
        high = Candidate("H", {}, gain_tier=GainTier.IG_PROBABILISTIC, gain_value=0.7)
        result = rank_candidates([low, high], mode="LEXICOGRAPHIC")
        assert result["ranked"] == ["H", "L"]


class TestCostFloor:
    """§20.3 rule 5."""

    def test_zero_cost_does_not_divide_to_infinity(self) -> None:
        assert effective_cost(Candidate("X", {}, cost=0.0)) > 0.0

    def test_unknown_cost_uses_the_floor(self) -> None:
        assert effective_cost(Candidate("X", {}, cost=None)) > 0.0

    def test_a_real_cost_is_untouched(self) -> None:
        assert effective_cost(Candidate("X", {}, cost=5.0)) == 5.0

    def test_negative_cost_is_refused(self) -> None:
        with pytest.raises(ValueError):
            Candidate("X", {}, cost=-1.0)

    def test_cost_can_be_the_declared_tiebreak(self) -> None:
        cheap = Candidate("C-cheap", {"gain": 1.0, "cost": 1.0})
        dear = Candidate("C-dear", {"gain": 1.0, "cost": 99.0})
        result = rank_candidates(
            [dear, cheap], mode="LEXICOGRAPHIC", criteria_order=("gain",), tiebreak="cost"
        )
        assert result["ranked"][0] == "C-cheap"


class TestPareto:
    """§20.3 rule 2 / §46.1: incomparable criteria return a set, not a winner."""

    def test_incommensurable_candidates_are_both_kept(self) -> None:
        shallow = Candidate("A-shallow", {"precision": 0.9, "coverage": 0.2})
        deep = Candidate("B-deep", {"precision": 0.3, "coverage": 0.95})
        result = rank_candidates(
            [shallow, deep], mode="PARETO_THEN_TIEBREAK",
            dimensions=("precision", "coverage"),
        )
        assert set(result["non_dominated"]) == {"A-shallow", "B-deep"}

    def test_a_dominated_candidate_is_dropped(self) -> None:
        good = Candidate("G", {"precision": 0.9, "coverage": 0.9})
        bad = Candidate("B", {"precision": 0.1, "coverage": 0.1})
        result = rank_candidates(
            [good, bad], mode="PARETO_THEN_TIEBREAK",
            dimensions=("precision", "coverage"),
        )
        assert result["non_dominated"] == ["G"]

    def test_dominance_requires_strict_improvement_somewhere(self) -> None:
        equal_left = Candidate("X", {"p": 0.5, "c": 0.5})
        equal_right = Candidate("Y", {"p": 0.5, "c": 0.5})
        assert _dominated_by(equal_left, equal_right, ("p", "c")) is False

    def test_no_worse_everywhere_and_better_somewhere_dominates(self) -> None:
        weak = Candidate("X", {"p": 0.5, "c": 0.5})
        for stronger in (
            Candidate("Y", {"p": 0.9, "c": 0.5}),
            Candidate("Z", {"p": 0.5, "c": 0.9}),
        ):
            assert _dominated_by(weak, stronger, ("p", "c")) is True

    def test_a_candidate_never_dominates_itself(self) -> None:
        candidate = Candidate("X", {"p": 0.5})
        assert _dominated_by(candidate, candidate, ("p",)) is False

    def test_dominance_is_restricted_to_declared_dimensions(self) -> None:
        weak = Candidate("X", {"p": 0.5, "ignored": 0.0})
        strong = Candidate("Y", {"p": 0.5, "ignored": 1.0})
        assert _dominated_by(weak, strong, ("p",)) is False
        assert _dominated_by(weak, strong, ("p", "ignored")) is True

    def test_dominance_front_matches_the_ranking(self) -> None:
        candidates = [
            Candidate("A", {"p": 0.9, "c": 0.2}),
            Candidate("B", {"p": 0.3, "c": 0.95}),
            Candidate("C", {"p": 0.1, "c": 0.1}),
        ]
        result = rank_candidates(
            candidates, mode="PARETO_THEN_TIEBREAK", dimensions=("p", "c")
        )
        assert set(dominance_front(candidates, ("p", "c"))) == set(result["non_dominated"])


class TestDeclaredAndEchoed:
    """§20.3 rule 6: the mode travels with the result."""

    @pytest.mark.parametrize("mode", list(RankingMode))
    def test_every_mode_echoes_itself(self, mode: RankingMode) -> None:
        candidate = Candidate("X", {"gain": 1.0})
        result = rank_candidates([candidate], mode=mode.value)
        assert result["mode"] == mode.value

    def test_weighted_additive_reports_what_it_normalised_over(self) -> None:
        result = rank_candidates(
            [Candidate("X", {"p": 1.0, "c": 1.0})],
            mode="WEIGHTED_ADDITIVE_NORMALIZED",
            criteria_order=("p", "c"),
        )
        assert result["normalized_over"] == ["p", "c"]

    def test_ranking_is_deterministic(self) -> None:
        candidates = [Candidate(f"C{i}", {"gain": 1.0 - i * 0.1}) for i in range(5)]
        first = rank_candidates(candidates, mode="LEXICOGRAPHIC", criteria_order=("gain",))
        second = rank_candidates(candidates, mode="LEXICOGRAPHIC", criteria_order=("gain",))
        assert first["ranked"] == second["ranked"]

    def test_no_candidates_is_empty_not_an_error(self) -> None:
        result = rank_candidates([], mode="LEXICOGRAPHIC")
        assert result["ranked"] == []