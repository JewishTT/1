"""Rank fusion semantics (spec 030 CE-001 §16.2, DON-RET-003, T0701).

The formula is not the hard part. These pin the four decisions that decide whether a fused
ranking means anything:

* a candidate a list omitted is **absent** from that list, not ranked last in it;
* a ranker that failed is recorded as failed, distinct from one that legitimately found nothing;
* ``score`` from a ranker is never an input -- rankers' scores are not comparable across
  implementations, which is the entire reason RRF exists;
* ordering is deterministic, so two runs over the same lists produce the same ranks.

Also pinned here: the module is clean-room. ``ranknexus`` and ``fuse`` were verified not to exist
as fusion projects, so there was nothing to vendor and calling this "donor code" would be a false
attribution.
"""

from __future__ import annotations

import pytest

from scoring.fusion import (
    DEFAULT_K,
    FusionPolicy,
    RankedCandidate,
    RankerOutcome,
    RankerOutcome_,
    reciprocal_rank_fusion,
)

pytestmark = pytest.mark.unit

Q = "q-1"


def _cand(cid: str, rank: int, ranker: str = "bm25", score: float | None = None, **kw):
    return RankedCandidate(
        candidate_id=cid, source_ranker_id=ranker, rank=rank, query_id=Q, score=score, **kw
    )


def _ok(ranker: str, *cands: RankedCandidate) -> RankerOutcome_:
    return RankerOutcome_(
        ranker_id=ranker, query_id=Q, outcome=RankerOutcome.OK, candidates=cands
    )


class TestTheFormula:
    def test_a_candidate_in_one_list_gets_its_reciprocal_rank(self):
        got = reciprocal_rank_fusion([_ok("bm25", _cand("a", 1))], query_id=Q)
        assert got[0].fused_score == pytest.approx(1 / (DEFAULT_K + 1))

    def test_agreement_between_rankers_accumulates(self):
        got = reciprocal_rank_fusion(
            [_ok("bm25", _cand("a", 1, "bm25")), _ok("vector", _cand("a", 1, "vector"))],
            query_id=Q,
        )
        assert got[0].fused_score == pytest.approx(2 / (DEFAULT_K + 1))

    def test_a_candidate_found_by_both_outranks_one_found_by_a_single_ranker(self):
        got = reciprocal_rank_fusion(
            [
                _ok("bm25", _cand("both", 1, "bm25"), _cand("solo", 2, "bm25")),
                _ok("vector", _cand("both", 3, "vector")),
            ],
            query_id=Q,
        )
        assert got[0].candidate_id == "both"
        assert got[1].candidate_id == "solo"

    def test_k_changes_the_flattening_not_the_order_of_two_equal_candidates(self):
        a = reciprocal_rank_fusion([_ok("bm25", _cand("x", 1), _cand("y", 2))], query_id=Q)
        b = reciprocal_rank_fusion(
            [_ok("bm25", _cand("x", 1), _cand("y", 2))], query_id=Q, policy=FusionPolicy(k=1)
        )
        assert [r.candidate_id for r in a] == [r.candidate_id for r in b] == ["x", "y"]


class TestAbsenceIsNotATrailingRank:
    """The distinction RRF exists to preserve."""

    def test_an_omitted_candidate_gets_none_not_a_rank(self):
        got = reciprocal_rank_fusion(
            [_ok("bm25", _cand("a", 1, "bm25")), _ok("vector", _cand("b", 1, "vector"))],
            query_id=Q,
        )
        by_id = {r.candidate_id: r for r in got}
        assert by_id["a"].per_ranker_ranks["vector"] is None
        assert by_id["b"].per_ranker_ranks["bm25"] is None

    def test_the_explanation_says_which_list_omitted_it(self):
        got = reciprocal_rank_fusion(
            [_ok("bm25", _cand("a", 1, "bm25")), _ok("vector", _cand("b", 1, "vector"))],
            query_id=Q,
        )
        text = next(r.explanation() for r in got if r.candidate_id == "a")
        assert "vector:-" in text

    def test_a_candidate_in_n_of_m_lists_outranks_one_in_1_of_m_even_when_ranked_worse(self):
        """Corroboration beats a better single placement. That is the property."""
        got = reciprocal_rank_fusion(
            [
                _ok("bm25", _cand("corroborated", 5, "bm25")),
                _ok("vector", _cand("corroborated", 5, "vector")),
                _ok("graph", _cand("solo", 1, "graph")),
            ],
            query_id=Q,
        )
        assert got[0].candidate_id == "corroborated"


class TestFailureIsNotEmptiness:
    def test_a_failed_ranker_is_reported_separately(self):
        got = reciprocal_rank_fusion(
            [_ok("bm25", _cand("a", 1)), _ok("vector")],
            query_id=Q,
        ) if False else reciprocal_rank_fusion(
            [
                _ok("bm25", _cand("a", 1)),
                RankerOutcome_(
                    ranker_id="vector", query_id=Q, outcome=RankerOutcome.FAILED, error="timeout"
                ),
            ],
            query_id=Q,
        )
        assert got[0].failed_rankers == ("vector",)
        assert got[0].empty_rankers == ()

    def test_an_empty_ranker_is_reported_separately(self):
        got = reciprocal_rank_fusion(
            [_ok("bm25", _cand("a", 1)), RankerOutcome_(ranker_id="vector", query_id=Q,
                                                            outcome=RankerOutcome.EMPTY)],
            query_id=Q,
        )
        assert got[0].empty_rankers == ("vector",)
        assert got[0].failed_rankers == ()

    def test_a_failure_without_a_reason_is_refused(self):
        with pytest.raises(ValueError) as e:
            RankerOutcome_(ranker_id="x", query_id=Q, outcome=RankerOutcome.FAILED)
        assert "why" in str(e.value)

    def test_empty_while_returning_candidates_is_refused(self):
        with pytest.raises(ValueError):
            RankerOutcome_(
                ranker_id="x", query_id=Q, outcome=RankerOutcome.EMPTY,
                candidates=(_cand("a", 1, "x"),),
            )

    def test_a_broken_ranker_does_not_change_the_surviving_ranking(self):
        lists = [_ok("bm25", _cand("a", 1), _cand("b", 2))]
        with_failure = reciprocal_rank_fusion(
            lists + [RankerOutcome_(ranker_id="v", query_id=Q, outcome=RankerOutcome.FAILED,
                                    error="boom")],
            query_id=Q,
        )
        without = reciprocal_rank_fusion(lists, query_id=Q)
        assert [r.candidate_id for r in with_failure] == [r.candidate_id for r in without]


class TestScoresAreNeverAnInput:
    def test_a_ranker_score_does_not_change_the_fusion(self):
        """Scores from different implementations are not comparable. RRF exists for that."""
        a = reciprocal_rank_fusion([_ok("bm25", _cand("x", 1, score=0.1))], query_id=Q)
        b = reciprocal_rank_fusion([_ok("bm25", _cand("x", 1, score=9999.0))], query_id=Q)
        assert a[0].fused_score == b[0].fused_score
        assert a[0].fused_rank == b[0].fused_rank


class TestDeterminism:
    def test_ties_break_by_candidate_id_and_are_stable(self):
        one = reciprocal_rank_fusion([_ok("bm25", _cand("a", 1), _cand("b", 1))], query_id=Q)
        two = reciprocal_rank_fusion([_ok("bm25", _cand("b", 1), _cand("a", 1))], query_id=Q)
        assert [r.candidate_id for r in one] == [r.candidate_id for r in two] == ["a", "b"]

    def test_list_order_does_not_change_the_result(self):
        fwd = reciprocal_rank_fusion(
            [_ok("bm25", _cand("a", 1)), _ok("vector", _cand("a", 2, "vector"))], query_id=Q
        )
        rev = reciprocal_rank_fusion(
            [_ok("vector", _cand("a", 2, "vector")), _ok("bm25", _cand("a", 1))], query_id=Q
        )
        assert [r.candidate_id for r in fwd] == [r.candidate_id for r in rev]
        assert fwd[0].fused_score == rev[0].fused_score


class TestPolicyIsVersioned:
    def test_weights_shift_the_result(self):
        got = reciprocal_rank_fusion(
            [
                _ok("bm25", _cand("b", 1, "bm25")),
                _ok("vector", _cand("a", 1, "vector")),
            ],
            query_id=Q,
            policy=FusionPolicy(weights={"bm25": 0.1}, policy_version="weighted/1"),
        )
        assert got[0].candidate_id == "a"

    def test_the_policy_fingerprint_is_recorded_on_every_result(self):
        policy = FusionPolicy(policy_version="rrf-test/7")
        got = reciprocal_rank_fusion([_ok("bm25", _cand("a", 1))], query_id=Q, policy=policy)
        assert got[0].fusion_policy_fingerprint == policy.fingerprint()

    def test_two_policies_have_different_fingerprints(self):
        assert FusionPolicy().fingerprint() != FusionPolicy(k=30).fingerprint()

    def test_a_negative_weight_is_refused(self):
        with pytest.raises(ValueError):
            FusionPolicy(weights={"bm25": -1.0})

    def test_k_below_one_is_refused(self):
        with pytest.raises(ValueError):
            FusionPolicy(k=0)


class TestInputHygiene:
    def test_a_candidate_without_a_ranker_is_refused(self):
        with pytest.raises(ValueError) as e:
            RankedCandidate(candidate_id="a", source_ranker_id="  ", rank=1, query_id=Q)
        assert "source ranker" in str(e.value)

    def test_rank_zero_is_refused(self):
        with pytest.raises(ValueError) as e:
            RankedCandidate(candidate_id="a", source_ranker_id="bm25", rank=0, query_id=Q)
        assert "1-based" in str(e.value)

    def test_a_candidate_returned_twice_by_one_ranker_is_refused(self):
        with pytest.raises(ValueError) as e:
            reciprocal_rank_fusion(
                [_ok("bm25", _cand("a", 1, "bm25"), _cand("a", 2, "bm25"))], query_id=Q
            )
        assert "twice" in str(e.value)

    def test_mixing_queries_is_refused(self):
        wrong = RankerOutcome_(
            ranker_id="bm25", query_id="q-OTHER", outcome=RankerOutcome.OK,
            candidates=(_cand("a", 1),),
        )
        with pytest.raises(ValueError) as e:
            reciprocal_rank_fusion([wrong], query_id=Q)
        assert "q-OTHER" in str(e.value)

    def test_evidence_refs_are_deduplicated_across_rankers(self):
        got = reciprocal_rank_fusion(
            [
                _ok("bm25", _cand("a", 1, "bm25", evidence_refs=("obs-1", "obs-2"))),
                _ok("vector", _cand("a", 1, "vector", evidence_refs=("obs-2", "obs-3"))),
            ],
            query_id=Q,
        )
        assert got[0].evidence_refs == ("obs-1", "obs-2", "obs-3")


class TestAttribution:
    """This is clean-room, and saying so is part of the contract."""

    def test_the_module_states_it_is_not_donor_code(self):
        from pathlib import Path

        import scoring.fusion as fusion

        source = Path(fusion.__file__).read_text(encoding="utf-8")
        assert "clean-room" in source
        assert "ranknexus" in source and "fuse" in source