"""Unit tests: recon plan → dispatcher wiring (T028, FR-009) + review event emission (T033)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from scoring.scorer import HeuristicUtilityScorer

from services.dispatcher import Dispatcher
from services.frontier import Frontier
from services.policy_service import PolicyService
from services.review import (
    ReviewAppendOnlyError,
    ReviewDecision,
    ReviewService,
    ReviewTargetType,
)
from services.source_registry import ReconPlanService


class MockProducer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, object, str | None]] = []

    def produce(self, topic, envelope, key=None, **kwargs) -> None:
        self.sent.append((topic, envelope, key))


class TestReconPlanDispatch:
    def _dispatcher(self, producer: MockProducer) -> Dispatcher:
        return Dispatcher(Frontier(), HeuristicUtilityScorer(), PolicyService(), producer=producer)

    def test_plan_runs_to_completion_with_lineage_events(self) -> None:
        producer = MockProducer()
        dispatcher = self._dispatcher(producer)
        plans = ReconPlanService()
        plan = plans.create(investigation_id="INV-1", tenant_id="default-tenant")

        result = dispatcher.run_recon_plan(
            plan, ["http://fixtures.local/a.html", "http://fixtures.local/b.html"]
        )

        assert result["plan"]["status"] == "COMPLETED"
        assert len(result["dispatched"]) == 2
        assert plan.task_ids == [r["task_id"] for r in result["dispatched"]]
        # recon.plan_started → acquisition.assigned (per dispatched task) →
        # recon.plan_completed lineage events (T028/T033).
        event_types = [e.event_type for _, e, _ in producer.sent]
        assert event_types[0] == "recon.plan_started"
        assert event_types[-1] == "recon.plan_completed"
        assert event_types.count("acquisition.assigned") == len(result["dispatched"])
        assert all(topic == "recon" or topic == "acquisition" for topic, _, _ in producer.sent)

    def test_frontier_items_scoped_to_plan_investigation(self) -> None:
        frontier = Frontier()
        dispatcher = Dispatcher(frontier, HeuristicUtilityScorer(), PolicyService())
        plans = ReconPlanService()
        plan = plans.create(investigation_id="INV-9", tenant_id="default-tenant")
        dispatcher.run_recon_plan(plan, ["http://fixtures.local/c.html"])
        assert frontier.count() == 1

    def test_no_dispatch_marks_plan_failed(self) -> None:
        dispatcher = Dispatcher(Frontier(), HeuristicUtilityScorer(), PolicyService())
        plans = ReconPlanService()
        plan = plans.create(investigation_id="INV-2", tenant_id="default-tenant")
        # Empty seeds → poll finds nothing → plan cannot complete.
        result = dispatcher.run_recon_plan(plan, [])
        assert result["plan"]["status"] == "FAILED"
        assert "failure_reason" in result["plan"]["strategy"]


class TestReviewEventEmission:
    def test_review_recorded_envelope_emitted(self) -> None:
        producer = MockProducer()
        svc = ReviewService(producer=producer)
        rec = svc.record(
            tenant_id="t1",
            analyst_id="a1",
            target_type=ReviewTargetType.CANDIDATE,
            target_id="c1",
            decision=ReviewDecision.ACCEPT,
            event_id="rev-evt-1",
        )
        assert len(producer.sent) == 1
        topic, envelope, key = producer.sent[0]
        assert topic == "review"
        assert envelope.event_type == "review.recorded"
        assert envelope.event_id == "rev-evt-1"
        assert envelope.entity_id == "c1"
        assert key == rec.review_id

    def test_no_producer_is_silent(self) -> None:
        svc = ReviewService()
        svc.record(
            tenant_id="t1",
            analyst_id="a1",
            target_type=ReviewTargetType.CANDIDATE,
            target_id="c1",
            decision=ReviewDecision.UNCERTAIN,
        )
        assert len(svc.all("t1")) == 1


class TestReviewService:
    def test_record_and_list(self) -> None:
        svc = ReviewService()
        rec = svc.record(
            tenant_id="t1",
            analyst_id="a1",
            target_type=ReviewTargetType.CANDIDATE,
            target_id="c1",
            decision=ReviewDecision.ACCEPT,
            reasoning="ok",
            roles=frozenset({"analyst"}),
        )
        assert rec.to_dict()["decision"] == "ACCEPT"
        assert len(svc.by_target("t1", ReviewTargetType.CANDIDATE, "c1")) == 1

    def test_review_immutable(self) -> None:
        svc = ReviewService()
        rec = svc.record(
            tenant_id="t1",
            analyst_id="a1",
            target_type=ReviewTargetType.CANDIDATE,
            target_id="c1",
            decision=ReviewDecision.ACCEPT,
        )
        with pytest.raises(ReviewAppendOnlyError):
            svc.mutate_attempt(rec.review_id, {"decision": "REJECT"})

    def test_replay_idempotent(self) -> None:
        svc = ReviewService()
        svc.record(
            tenant_id="t1",
            analyst_id="a1",
            target_type=ReviewTargetType.CANDIDATE,
            target_id="c1",
            decision=ReviewDecision.UNCERTAIN,
            event_id="rev-1",
        )
        again = svc.replay("rev-1")
        assert again is not None and again.replayed
        assert svc.replay("rev-unknown") is None

    def test_tenant_isolation(self) -> None:
        svc = ReviewService()
        svc.record(
            tenant_id="t1",
            analyst_id="a1",
            target_type=ReviewTargetType.FINDING,
            target_id="f1",
            decision=ReviewDecision.REJECT,
        )
        assert svc.all("t2") == []