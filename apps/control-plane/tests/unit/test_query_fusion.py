"""Fusion scoring is real, not an algebraic no-op (T004/T006, D6).

Before the fix, ``query_planner._fuse`` computed
``EVIDENCE_BASE * max_score + (1 - EVIDENCE_BASE) * max_score``, which is
identically ``max_score``: a backend returning a weak hit and a backend
returning overwhelming corroboration for the same document fused to the same
number, and evidence strength was discarded.

Two properties are pinned here:

1. Independent *source* agreement changes the score. Constitution Governance is
   explicit that publication count is not independent-source count, so two
   backends reading one source are ONE piece of evidence, not two.
2. ``relevance`` and ``support`` are retained on ``FusedResult`` beside the
   composite, so any client can re-derive or dispute the composite
   (Constitution IV: no single score equates to truth).
"""

from __future__ import annotations

import sys
from dataclasses import fields
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from services.query_planner import (
    EVIDENCE_BASE,
    BackendHit,
    FusedResult,
    QueryPlanner,
)

OBS = {
    "OBS-1": {"observation_id": "OBS-1", "uri": "http://fixtures.local/a", "content_hash": "sha256:aa"},
}


class StubBackend:
    """Returns a fixed hit list: no rescoring, so assertions can be exact."""

    def __init__(self, hits: list[BackendHit]) -> None:
        self.hits = list(hits)

    async def search(self, text: str, filters, limit: int = 20) -> list[BackendHit]:
        return list(self.hits[:limit])


def hit(doc_id: str, score: float, source_id: str | None, *, backend: str = "") -> BackendHit:
    return BackendHit(
        doc_id=doc_id,
        score=score,
        backend=backend,
        source_id=source_id,
        observation_id="OBS-1",
        payload={"text": "Yard account transfers"},
    )


def plan_for(backends: dict[str, StubBackend]) -> QueryPlanner:
    return QueryPlanner(backends=dict(backends), observations=OBS)


class TestEvidenceStrengthIsNotDiscarded:
    async def test_two_sources_outrank_one_source_at_equal_relevance(self) -> None:
        """The bug in one assertion: both fusions used to be plain `max_score`."""
        planner = plan_for({
            "alpha": StubBackend([hit("DOC-MULTI", 0.8, "src-a", backend="alpha")]),
            "beta": StubBackend([hit("DOC-MULTI", 0.8, "src-b", backend="beta")]),
            "gamma": StubBackend([hit("DOC-SINGLE", 0.8, "src-a", backend="gamma")]),
            "delta": StubBackend([hit("DOC-SINGLE", 0.8, "src-a", backend="delta")]),
        })
        results = {r.doc_id: r for r in await planner.execute(planner.plan("Yard"))}

        multi = results["DOC-MULTI"]
        single = results["DOC-SINGLE"]

        # Identical relevance and identical publication count (two backends
        # each). The only difference is whether those two backends read the
        # same source -- that is what must move the score.
        assert multi.relevance == single.relevance == 0.8
        assert len(multi.backends) == len(single.backends) == 2
        assert multi.support == 2
        assert single.support == 1
        assert multi.score > single.score
        assert multi.score == pytest.approx(0.8 * (1 + EVIDENCE_BASE))

    async def test_three_backends_reading_one_source_are_one_piece_of_evidence(self) -> None:
        """Publication count is not independent-source count."""
        same = hit("DOC-ONE-SOURCE", 0.7, "src-a")
        planner = plan_for({
            "alpha": StubBackend([same]),
            "beta": StubBackend([same]),
            "gamma": StubBackend([same]),
        })
        (result,) = await planner.execute(planner.plan("Yard"))

        assert result.backends == ["alpha", "beta", "gamma"]  # three publications
        assert result.support == 1  # one independent source
        assert result.score == pytest.approx(result.relevance)

    async def test_duplicate_source_id_is_not_double_counted(self) -> None:
        planner = plan_for({
            "alpha": StubBackend([hit("DOC-2", 0.5, "src-a"), hit("DOC-2", 0.5, "src-a")]),
            "beta": StubBackend([hit("DOC-2", 0.5, "src-b")]),
        })
        (result,) = await planner.execute(planner.plan("Yard"))

        assert result.support == 2
        assert result.score == pytest.approx(0.5 * (1 + EVIDENCE_BASE))

    async def test_a_third_source_keeps_earning_credit(self) -> None:
        planner = plan_for({
            "alpha": StubBackend([hit("DOC-3", 0.5, "src-a")]),
            "beta": StubBackend([hit("DOC-3", 0.5, "src-b")]),
            "gamma": StubBackend([hit("DOC-3", 0.5, "src-c")]),
        })
        (result,) = await planner.execute(planner.plan("Yard"))

        assert result.support == 3
        assert result.score == pytest.approx(0.5 * (1 + EVIDENCE_BASE * 2))


class TestComponentsAreRetained:
    async def test_relevance_and_support_are_retained_beside_the_composite(self) -> None:
        planner = plan_for({
            "alpha": StubBackend([hit("DOC-1", 0.8, "src-a")]),
            "beta": StubBackend([hit("DOC-1", 0.4, "src-b")]),
        })
        (result,) = await planner.execute(planner.plan("Yard"))

        assert result.relevance == 0.8  # best single backend, not the average
        assert result.support == 2
        assert {f.name for f in fields(FusedResult)} >= {"doc_id", "score", "relevance", "support"}

    async def test_composite_is_rederivable_from_the_retained_components(self) -> None:
        """A client must be able to recompute the composite from the record."""
        planner = plan_for({
            "alpha": StubBackend([hit("DOC-1", 0.9, "src-a")]),
            "beta": StubBackend([hit("DOC-1", 0.3, "src-b")]),
            "gamma": StubBackend([hit("DOC-1", 0.5, "src-c")]),
        })
        (result,) = await planner.execute(planner.plan("Yard"))

        assert result.score == pytest.approx(
            result.relevance * (1 + EVIDENCE_BASE * (result.support - 1))
        )
        assert result.score == pytest.approx(0.9 * (1 + 0.6 * 2))

    async def test_composite_is_never_the_only_stored_number(self) -> None:
        """Constitution IV: the composite alone would not be the whole truth."""
        planner = plan_for({
            "alpha": StubBackend([hit("DOC-1", 0.8, "src-a")]),
            "beta": StubBackend([hit("DOC-1", 0.4, "src-b")]),
        })
        (result,) = await planner.execute(planner.plan("Yard"))

        # Evidence strength demonstrably moved the number...
        assert result.score > result.relevance
        # ...and both components survive independently of it, so a reader can
        # dispute either without trusting the composite. `support` is
        # checkable against the evidence chain the record already carries.
        assert result.support == 2 == len({e["source_id"] for e in result.evidence})
        assert {f.name for f in fields(FusedResult)} >= {"relevance", "support"}

    async def test_unattributed_evidence_earns_no_corroboration_credit(self) -> None:
        """A hit with no source_id cannot corroborate anything."""
        planner = plan_for({"alpha": StubBackend([hit("DOC-1", 0.8, None)])})
        (result,) = await planner.execute(planner.plan("Yard"))

        assert result.support == 0
        assert result.relevance == 0.8
        assert result.score == pytest.approx(0.8 * (1 - EVIDENCE_BASE))


class TestDeterministicOrdering:
    async def test_ties_are_broken_by_doc_id(self) -> None:
        planner = plan_for({
            "alpha": StubBackend([
                hit("DOC-C", 0.5, "src-a"),
                hit("DOC-A", 0.5, "src-a"),
                hit("DOC-B", 0.5, "src-a"),
            ]),
        })
        results = await planner.execute(planner.plan("Yard"))

        assert [r.doc_id for r in results] == ["DOC-A", "DOC-B", "DOC-C"]
        assert len({r.score for r in results}) == 1  # a genuine tie

    async def test_identical_inputs_give_identical_ordering(self) -> None:
        docs = ["DOC-C", "DOC-A", "DOC-B", "DOC-D"]
        expected = ["DOC-A", "DOC-B", "DOC-C", "DOC-D"]

        async def order_for(backend_order: tuple[str, ...]) -> list[str]:
            planner = plan_for({
                name: StubBackend([hit(d, 0.4, "src-a") for d in docs]) for name in backend_order
            })
            return [r.doc_id for r in await planner.execute(planner.plan("Yard"))]

        assert await order_for(("alpha", "beta")) == expected
        assert await order_for(("beta", "alpha")) == expected

    async def test_support_can_outrank_raw_relevance(self) -> None:
        """The boost is a declared, bounded judgement -- not rank-order-preserving."""
        planner = plan_for({
            "alpha": StubBackend([hit("DOC-LOUD", 0.7, "src-a")]),
            "beta": StubBackend([hit("DOC-LOUD", 0.7, "src-a")]),
            "gamma": StubBackend([hit("DOC-CORROBORATED", 0.5, "src-a")]),
            "delta": StubBackend([hit("DOC-CORROBORATED", 0.5, "src-a")]),
            "epsilon": StubBackend([hit("DOC-CORROBORATED", 0.5, "src-b")]),
        })
        results = await planner.execute(planner.plan("Yard"))

        # 0.5 * 1.6 = 0.8 outranks 0.7 * 1.0: corroboration is worth more than
        # the relevance gap it closes. Under the old no-op both were 0.5/0.7
        # and the louder, uncorroborated document won.
        assert results[0].doc_id == "DOC-CORROBORATED"
        assert results[0].score == pytest.approx(0.8)
        assert results[0].support == 2
        assert results[1].doc_id == "DOC-LOUD"
        assert results[1].score == pytest.approx(0.7)
        assert results[1].support == 1
