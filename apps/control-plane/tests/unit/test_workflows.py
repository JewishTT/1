"""Unit tests for Temporal investigation/recrawl workflows (T078)."""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from workflows.investigation import (
    InvalidLifecycleTransition,
    InvestigationLifecycle,
    LifecycleConfig,
    LifecycleState,
    RecrawlWorkflow,
)


@pytest.fixture
def lifecycle() -> InvestigationLifecycle:
    return InvestigationLifecycle(investigation_id="inv-1", config=LifecycleConfig())


class TestLifecycle:
    def test_autostart_queues_then_acquires(self, lifecycle):
        assert lifecycle.auto_start() == LifecycleState.ACQUIRING
        assert lifecycle.step == 1

    def test_approval_required_needs_human_gate(self):
        lc = InvestigationLifecycle(
            investigation_id="inv-2", config=LifecycleConfig(approval_required=True)
        )
        assert lc.auto_start() == LifecycleState.AWAITING_APPROVAL
        assert lc.advance("approve") == LifecycleState.APPROVED
        assert lc.advance("acquire") == LifecycleState.ACQUIRING

    def test_pause_resume(self, lifecycle):
        lifecycle.auto_start()
        assert lifecycle.advance("pause") == LifecycleState.PAUSED
        assert lifecycle.advance("resume") == LifecycleState.QUEUED

    def test_reject_then_requeue_or_finish(self, lifecycle):
        lc = InvestigationLifecycle(
            investigation_id="inv-3", config=LifecycleConfig(approval_required=True)
        )
        lc.auto_start()
        lc.advance("reject")
        assert lc.advance("complete") == LifecycleState.COMPLETED

    def test_invalid_transition_raises(self, lifecycle):
        lifecycle.auto_start()
        with pytest.raises(InvalidLifecycleTransition):
            lifecycle.advance("approve")

    def test_unknown_event_raises(self, lifecycle):
        with pytest.raises(InvalidLifecycleTransition):
            lifecycle.advance("bogus")

    def test_max_acquire_steps_completes(self):
        lc = InvestigationLifecycle(
            investigation_id="inv-4", config=LifecycleConfig(max_acquire_steps=2)
        )
        lc.auto_start()  # step 1
        assert lc.advance("acquire") == LifecycleState.ACQUIRING  # step 2
        assert lc.advance("acquire") == LifecycleState.COMPLETED  # step 3 > max

    def test_recrawl_schedules_next(self, lifecycle):
        lifecycle.auto_start()
        at = datetime(2026, 1, 1, tzinfo=UTC)
        lifecycle.advance("schedule_recrawl", at)
        assert lifecycle.state == LifecycleState.RECRAWL
        assert lifecycle.recrawl_at == at + lifecycle.config.recrawl_interval


class TestRecovery:
    def test_checkpoint_roundtrip(self, lifecycle):
        lifecycle.auto_start()
        lifecycle.advance("pause")
        checkpoint = lifecycle.checkpoint()
        recovered = InvestigationLifecycle.recover(checkpoint, lifecycle.config)
        assert recovered.state == LifecycleState.PAUSED
        assert recovered.step == lifecycle.step
        assert recovered.investigation_id == "inv-1"

    def test_recrawl_interval_stored(self, lifecycle):
        recrawl_seconds = int(lifecycle.config.recrawl_interval.total_seconds())
        assert recrawl_seconds == int(timedelta(hours=6).total_seconds())


class TestWorkflowWiring:
    def test_recrawl_workflow_defined(self):
        assert hasattr(RecrawlWorkflow, "run")

    def test_temporal_materialization_workflow_is_defined(self):
        from workflows.temporal_materialization import (
            MaterializationWorkflowInput,
            TemporalEntityMaterializationWorkflow,
        )

        assert hasattr(TemporalEntityMaterializationWorkflow, "run")
        request = MaterializationWorkflowInput("tenant", "entity", ("record-1",), "run-1")
        assert request.mode == "rebuild"

    def test_investigation_workflow_has_signal_handlers(self):
        from workflows.investigation import InvestigationWorkflow

        for name in ("pause", "resume", "approve", "reject", "schedule_recrawl", "complete"):
            assert hasattr(InvestigationWorkflow, name), name
