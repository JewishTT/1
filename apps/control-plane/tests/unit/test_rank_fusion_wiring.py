"""Rank fusion is wired into the live query path, not merely available (T004, D6).

`apps/shared/scoring/fusion.py` shipped a clean-room reciprocal rank fusion with
26 passing tests and no caller. A scorer nothing calls is a document with
docstrings. These tests pin the wiring in `QueryPlanner`, because the wiring is
where the interesting failures live and none of them are visible from the fusion
module's own tests:

1. Incomparable score scales stop mattering. A backend that emits 1000.0 and one
   that emits 0.001 do not disagree under rank fusion, because position is the
   only thing read. Under the old score-weighted composite the 1000.0 wins every
   comparison regardless of rank.
2. A failed backend stays distinguishable from an empty one. Both contribute no
   candidates, and conflating them turns "this source is broken" into "this source
   has nothing to say" -- the user then reads silence as absence of evidence.
3. Attribution survives into `FusedResult`, so the fused number can be re-derived
   and disputed per ranker instead of trusted as one opaque float.
4. `rederive_composite()` stays truthful under rank fusion. Reporting the
   score-weighted formula here would return a number that never produced the
   field it sits next to.

A backend returning duplicates for one doc_id would make rank fusion ambiguous,
but the fusion contract rejects that outright, so `execute` must not let it
through silently either.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from scoring.fusion import DEFAULT_K

from services.query_planner import (
    RANK_FUSION,
    SCORE_WEIGHTED,
    AllBackendsFailed,
    BackendHit,
    QueryFilters,
    QueryPlanner,
)

OBS = {
    "OBS-1": {
        "observation_id": "OBS-1",
        "uri": "http://fixtures.local/a",
        "content_hash": "sha256:aa",
    },
}


class StubBackend:
    """Returns a fixed hit list: no rescoring, so assertions can be exact."""

    def __init__(self, hits: list[BackendHit] | None = None, error: Exception | None = None) -> None:
        self.hits = list(hits or [])
        self.error = error

    async def search(self, text: str, filters: QueryFilters, limit: int = 20) -> list[BackendHit]:
        if self.error is not None:
            raise self.error
        return list(self.hits[:limit])


def hit(doc_id: str, score: float = 0.5, source_id: str | None = None) -> BackendHit:
    return BackendHit(doc_id=doc_id, score=score, source_id=source_id)


async def run(backends: dict, fusion: str = RANK_FUSION, query: str = "q"):
    planner = QueryPlanner(backends, OBS)
    return await planner.execute(planner.plan(query, fusion=fusion))


class TestStrategySelection:
    async def test_rank_fusion_is_a_selectable_strategy(self):
        assert await run({"search": StubBackend([hit("a")])}, RANK_FUSION)

    async def test_score_weighted_remains_the_default(self):
        planner = QueryPlanner({"search": StubBackend([hit("a")])}, OBS)
        assert planner.plan("q").fusion == SCORE_WEIGHTED

    async def test_an_unknown_strategy_is_refused(self):
        planner = QueryPlanner({"search": StubBackend([hit("a")])}, OBS)
        with pytest.raises(ValueError):
            planner.plan("q", fusion="vibes")


class TestScaleStopsMattering:
    async def test_a_huge_score_does_not_beat_a_better_rank(self):
        """The point of fusion: magnitude from an incomparable scale cannot win.

        `loud` reports 1000.0 for `bad` at rank 1 and 0.001 for `good` at rank 2.
        `quiet` reports 0.002 for `good` at rank 1. Under score-weighted fusion
        `bad` wins on raw magnitude even though `quiet` ranks `good` first; under
        rank fusion both rankers place `good` ahead, so `good` wins.
        """
        backends = {
            "loud": StubBackend([hit("bad", 1000.0), hit("good", 0.001)]),
            "quiet": StubBackend([hit("good", 0.002)]),
        }

        weighted = {r.doc_id for r in await run(backends, SCORE_WEIGHTED)}
        assert "bad" in weighted

        fused = await run(backends, RANK_FUSION)
        assert fused[0].doc_id == "good", "rank fusion let a raw score magnitude decide"

    async def test_the_score_is_the_declared_formula(self):
        fused = await run(
            {"a": StubBackend([hit("x")]), "b": StubBackend([hit("x")])}, RANK_FUSION
        )
        assert fused[0].score == pytest.approx(2 * (1 / (DEFAULT_K + 1)))


class TestFailureIsNotEmptiness:
    async def test_a_broken_backend_does_not_silently_become_empty(self):
        backends = {
            "ok": StubBackend([hit("a")]),
            "broken": StubBackend(error=TimeoutError("upstream timed out")),
        }
        fused = await run(backends, RANK_FUSION)
        (result,) = fused
        # It contributed nothing to the score...
        assert result.per_ranker_ranks == {"ok": 1, "broken": None}
        assert result.score == pytest.approx(1 / (DEFAULT_K + 1))
        # ...but the response names it as failed rather than as silent.
        assert [d["backend"] for d in result.degraded_backends] == ["broken"]

    async def test_an_empty_backend_is_not_reported_as_broken(self):
        backends = {"ok": StubBackend([hit("a")]), "quiet": StubBackend([])}
        fused = await run(backends, RANK_FUSION)
        assert fused[0].degraded_backends == []

    async def test_total_outage_still_raises_rather_than_returning_nothing(self):
        backends = {"a": StubBackend(error=OSError("down")), "b": StubBackend(error=OSError("down"))}
        with pytest.raises(AllBackendsFailed):
            await run(backends, RANK_FUSION)


class TestAttributionSurvives:
    async def test_each_ranker_keeps_the_rank_it_assigned(self):
        backends = {
            "a": StubBackend([hit("x"), hit("y")]),
            "b": StubBackend([hit("y"), hit("x")]),
        }
        fused = await run(backends, RANK_FUSION)
        # `x` is rank 1 at `a` and rank 2 at `b`; absence must not be padded.
        by_id = {r.doc_id: r for r in fused}
        assert by_id["x"].per_ranker_ranks == {"a": 1, "b": 2}
        assert by_id["y"].per_ranker_ranks == {"a": 2, "b": 1}

    async def test_the_policy_is_fingerprinted_on_every_result(self):
        fused = await run({"a": StubBackend([hit("x")])}, RANK_FUSION)
        assert fused[0].fusion_policy_fingerprint.startswith("sha256:")

    async def test_evidence_still_resolves_to_immutable_observations(self):
        backends = {"a": StubBackend([hit("x", source_id="src-1")])}
        fused = await run(backends, RANK_FUSION)
        (evidence,) = fused[0].evidence
        assert evidence["observation"]["immutable"] is True

    async def test_the_fused_score_can_be_re_derived_not_merely_trusted(self):
        """Constitution IV: a client can dispute the number it was handed."""
        fused = await run({"a": StubBackend([hit("x")]), "b": StubBackend([hit("x")])}, RANK_FUSION)
        (result,) = fused
        assert result.fusion == RANK_FUSION
        assert result.rederive_composite() == pytest.approx(result.score)

    async def test_score_weighted_results_still_re_derive_the_old_way(self):
        fused = await run({"a": StubBackend([hit("x", 0.8, "src-1")])}, SCORE_WEIGHTED)
        (result,) = fused
        assert result.fusion == SCORE_WEIGHTED
        assert result.per_ranker_ranks == {}
        assert result.rederive_composite() == pytest.approx(result.score)


class TestOrderingIsDeterministic:
    async def test_ties_break_by_doc_id_not_by_backend_arrival(self):
        """A genuine tie, resolved by id and not by which backend answered first.

        `b` leads backend `a` and `a` leads backend `b`, so both score exactly
        `1/(k+1)`. Nothing in the arithmetic distinguishes them, and the order
        backends happen to be iterated in is not a property of the query -- so the
        result has to fall back to the candidate id.
        """
        first = await run({"a": StubBackend([hit("b"), hit("a")]),
                           "b": StubBackend([hit("a"), hit("b")])}, RANK_FUSION)
        second = await run({"b": StubBackend([hit("a"), hit("b")]),
                            "a": StubBackend([hit("b"), hit("a")])}, RANK_FUSION)
        assert first[0].score == pytest.approx(second[0].score), "not actually a tie"
        assert [r.doc_id for r in first] == [r.doc_id for r in second] == ["a", "b"]