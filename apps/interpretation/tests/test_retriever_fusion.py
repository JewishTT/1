"""The local RRF copy was three separate bugs; the shared contract forbids all three.

`CrossSemanticRetriever.search` used to compute `1.0 / (rank + 60) + 0.01 * hit.score`
inline. That expression had:

1. **A 0-based rank.** `enumerate` without `start=1` gave the backend's *best*
   hit rank 0, so it scored `1/60` where it should have scored `1/61`. Every
   fused list was shifted by one, and a single-backend "fusion" was not a
   no-op -- it silently rescaled.
2. **The raw score folded back in.** `+ 0.01 * hit.score` reintroduces exactly
   the magnitude sensitivity that reciprocal rank fusion removes. Backends do
   not share a scale, so a backend emitting 1000.0 for its worst match and 0.001
   for its best one could still win the ranking outright. That is the defect the
   algorithm exists to remove.
3. **Non-deterministic ties.** `sorted` on equal scores fell through to dict
   insertion order, which is backend arrival order -- not a property of the query.

The fix delegates to `scoring.fusion`. These tests pin the three properties so a
future hand-rolled shortcut gets caught immediately.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from retrieval.retriever import CrossSemanticRetriever, Hit

pytestmark = pytest.mark.unit


class StubRetriever:
    """Fixed result list, with scores deliberately on incompatible scales."""

    def __init__(self, name: str, hits: list[Hit], caps: set[str]) -> None:
        self.name = name
        self._hits = list(hits)
        self._caps = caps

    def supports(self, badge: str) -> bool:
        return badge in self._caps

    def retrieve(self, badge: str, query: str, top_k: int = 10) -> list[Hit]:
        return list(self._hits[:top_k])


def hit(doc_id: str, score: float = 0.5, backend: str = "") -> Hit:
    return Hit(doc_id=doc_id, text=doc_id, score=score, backend=backend)


def retriever(*backends: StubRetriever) -> CrossSemanticRetriever:
    return CrossSemanticRetriever(list(backends))


class TestRankIsOneBased:
    def test_a_single_backend_scores_its_best_hit_as_one_over_k_plus_one(self):
        from scoring.fusion import DEFAULT_K

        r = retriever(StubRetriever("solo", [hit("a")], {"http"}))
        (top,) = r.search("page content")
        assert top.score == pytest.approx(1 / (DEFAULT_K + 1))

    def test_a_lone_hit_is_not_a_no_op(self):
        """Regression: 0-based rank made one hit score 1/60 instead of 1/61."""
        from scoring.fusion import DEFAULT_K

        r = retriever(StubRetriever("solo", [hit("a")], {"http"}))
        (top,) = r.search("page content")
        assert top.score != pytest.approx(1 / DEFAULT_K)


class TestScoresAreNeverAnInput:
    def test_a_worse_ranked_hit_with_a_huge_score_cannot_win(self):
        """The whole point: magnitude is not a vote.

        `loud` ranks `bad` first but scores it 1000.0, and ranks `good` second at
        0.001. `quiet` ranks `good` first at 0.002. Under the old formula the
        1000.0 contributed 10.0 and dominated outright.
        """
        r = retriever(
            StubRetriever("loud", [hit("bad", 1000.0), hit("good", 0.001)], {"http"}),
            StubRetriever("quiet", [hit("good", 0.002)], {"http"}),
        )
        got = [h.doc_id for h in r.search("page content")]
        assert got[0] == "good"

    def test_identical_ranks_give_identical_scores_despite_scores(self):
        r = retriever(
            StubRetriever("a", [hit("x", 100.0)], {"http"}),
            StubRetriever("b", [hit("y", 0.0001)], {"http"}),
        )
        results = {h.doc_id: h.score for h in r.search("page content")}
        assert results["x"] == pytest.approx(results["y"])


class TestAttribution:
    def test_a_corrobated_hit_names_every_backend_that_placed_it(self):
        r = retriever(
            StubRetriever("a", [hit("both"), hit("solo")], {"http"}),
            StubRetriever("b", [hit("both")], {"http"}),
        )
        by_id = {h.doc_id: h for h in r.search("page content")}
        assert by_id["both"].score > by_id["solo"].score
        assert by_id["both"].backend == "a, b"
        assert by_id["solo"].backend == "a"

    def test_the_hit_text_survives_fusion(self):
        r = retriever(
            StubRetriever("a", [Hit("x", text="body text", score=1.0, backend="a")], {"http"})
        )
        (top,) = r.search("page content")
        assert top.text == "body text"


class TestDeterminism:
    def test_ties_break_by_doc_id_not_by_backend_arrival(self):
        """Equal rank in both backends -> equal score -> doc_id decides."""
        first = retriever(
            StubRetriever("a", [hit("b"), hit("a")], {"http"}),
            StubRetriever("b", [hit("a"), hit("b")], {"http"}),
        )
        second = retriever(
            StubRetriever("b", [hit("a"), hit("b")], {"http"}),
            StubRetriever("a", [hit("b"), hit("a")], {"http"}),
        )
        assert [h.doc_id for h in first.search("page content")] == [
            h.doc_id for h in second.search("page content")
        ]


class TestFirstMergeStillWins:
    def test_merge_first_bypasses_fusion_entirely(self):
        only = StubRetriever("solo", [hit("a")], {"http"})
        assert [h.doc_id for h in retriever(only).search("page content", merge="first")] == ["a"]