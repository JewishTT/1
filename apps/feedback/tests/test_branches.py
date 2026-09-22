"""Feedback branches unit tests (T116/T117/T118): hermetic, no live stack."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "shared"))

import pytest
from scoring.scorer import HeuristicUtilityScorer

from feedback import FeedbackCandidate
from feedback.branch.entity import EntityResolutionHints, run_entity_feedback
from feedback.branch.finding import ENQUEUE_UTILITY, FindingCandidate, run_finding_feedback
from feedback.branch.source import (
    SourceOutcomeFeedback,
    run_source_feedback,
)
from feedback.frontier import MemoryFrontierSink


class TestSourceBranch:
    def test_success_keeps_deep_source(self) -> None:
        scorer = HeuristicUtilityScorer()
        forms = [
            SourceOutcomeFeedback(
                source_id="src-a",
                lifecycle="created",
                tenant_id="ten-1",
                cost=2.0,
                independence_yield=0.9,
            )
            for _ in range(4)
        ]
        cands = run_source_feedback(scorer, forms)
        assert len(cands) == 1
        assert cands[0].priority > 0.5  # deepen

    def test_erroring_source_is_dropped_from_frontier(self) -> None:
        scorer = HeuristicUtilityScorer()
        forms = [
            SourceOutcomeFeedback(source_id="src-err", lifecycle="failed", tenant_id="ten-1")
            for _ in range(4)
        ]
        cands = run_source_feedback(scorer, forms)
        assert cands == []

    def test_stable_changed_false_reduces(self) -> None:
        scorer = HeuristicUtilityScorer()
        forms = [
            SourceOutcomeFeedback(source_id="src-st", lifecycle="unchanged", tenant_id="ten-1")
            for _ in range(5)
        ]
        cands = run_source_feedback(scorer, forms)
        assert cands and cands[0].priority < 0.4  # reduce/keep steady


class TestEntityBranch:
    def test_aliases_identifiers_become_pivots(self) -> None:
        hints = EntityResolutionHints(
            entity_id="ENT-1",
            tenant_id="ten-1",
            names=["Target Person"],
            aliases=["TP", "tp-alpha"],
            emails=["tp@example.com"],
            handles=["@tp"],
            domains=["example.com"],
        )
        cands = run_entity_feedback(hints)
        by_kind = {c.payload["kind"] for c in cands}
        assert {"alias", "email", "handle", "domain"} <= by_kind
        assert all(c.kind == "pivot" for c in cands)

    def test_dedup_caseinsensitive_pivots(self) -> None:
        hints = EntityResolutionHints(
            entity_id="ENT-2",
            tenant_id="ten-1",
            aliases=["Example.COM", "example.com"],
        )
        assert len(run_entity_feedback(hints)) == 1

    def test_low_confidence_pivots_are_low_priority(self) -> None:
        low = EntityResolutionHints(entity_id="E1", tenant_id="t", aliases=["a1"], confidence=0.1)
        high = EntityResolutionHints(entity_id="E1", tenant_id="t", aliases=["a1"], confidence=0.9)
        assert run_entity_feedback(low)[0].priority < run_entity_feedback(high)[0].priority


class TestFindingBranch:
    def test_high_confidence_finding_enqueued(self) -> None:
        scorer = HeuristicUtilityScorer()
        findings = [
            FindingCandidate(finding_id="F1", entity_id="ENT-1", tenant_id="ten-1", confidence=0.9)
        ]
        cands = run_finding_feedback(scorer, findings)
        assert len(cands) == 1
        assert cands[0].kind == "hypothesis"
        assert cands[0].priority >= ENQUEUE_UTILITY

    def test_low_utility_finding_deferred(self) -> None:
        scorer = HeuristicUtilityScorer()
        findings = [
            FindingCandidate(
                finding_id="F2", entity_id="ENT-1", tenant_id="ten-1", estimated_utility=0.05
            )
        ]
        deferred: list[tuple] = []
        cands = run_finding_feedback(scorer, findings, emit=lambda t, p: deferred.append((t, p)))
        assert cands == []
        assert deferred and deferred[0][0] == "feedback.defer"


class TestSink:
    @pytest.mark.asyncio
    async def test_memory_sink_dedups_by_uri_and_tenant(self) -> None:
        sink = MemoryFrontierSink()
        c = FeedbackCandidate(uri="u://1", priority=0.5, kind="pivot", tenant_id="ten-1")
        assert await sink.enqueue_candidate(c) is True
        assert await sink.enqueue_candidate(c) is False
        c2 = FeedbackCandidate(uri="u://1", priority=0.5, kind="pivot", tenant_id="ten-2")
        assert await sink.enqueue_candidate(c2) is True

    def test_branches_emit_candidates_consumable_by_sink(self) -> None:
        hints = EntityResolutionHints(entity_id="E9", tenant_id="t", names=["K"])
        expect = run_entity_feedback(hints)
        assert all(isinstance(c, FeedbackCandidate) for c in expect)
