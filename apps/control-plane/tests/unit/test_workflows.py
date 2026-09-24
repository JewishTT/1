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
            reconcile_and_publish,
        )

        assert hasattr(TemporalEntityMaterializationWorkflow, "run")
        assert callable(reconcile_and_publish)
        request = MaterializationWorkflowInput("tenant", "entity", ("record-1",), "run-1")
        assert request.mode == "rebuild"

    @pytest.mark.asyncio
    async def test_activity_builds_cc_records(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from workflows import temporal_materialization as module

        def fake_run(entity_id: str, identity: dict[str, str], session: object = None):
            return {
                "captures": [
                    {
                        "url": "https://example.com/a",
                        "observed_at": "2024-01-01T00:00:00Z",
                        "status": 200,
                        "digest": "sha256:x",
                        "record_id": "evt-1",
                        "locator": "warc.gz@1,2",
                        "crawl": "CC-MAIN-2024-10",
                        "subset": "warc",
                    }
                ]
            }

        monkeypatch.setattr("services.cc_temporality.run_cc_temporality", fake_run)
        result = await module.reconcile_and_publish("t1", "e1", [], "run-1", {"domain": "example.com"})
        assert result["status"] == "READY"
        assert result["publication"]["source_cut"]["source_record_ids"]

    @pytest.mark.asyncio
    async def test_temporal_dispatch_starts_deterministic_workflow(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from services import temporal_materialization_dispatch as dispatch

        class FakeClient:
            def __init__(self) -> None:
                self.calls: list[tuple[object, object, str, str]] = []

            async def start_workflow(self, workflow: object, request: object, *, id: str, task_queue: str):
                self.calls.append((workflow, request, id, task_queue))

        client = FakeClient()

        async def connect():
            return client

        monkeypatch.setattr("workflow.client.connect_temporal", connect)
        first = await dispatch.start_entity_materialization(
            tenant_id="t1", entity_id="e1", identity={"domain": "example.com"}
        )
        second = await dispatch.start_entity_materialization(
            tenant_id="t1", entity_id="e1", identity={"domain": "example.com"}
        )
        assert first.status == second.status == "QUEUED"
        assert first.run_id == second.run_id
        assert first.workflow_id == second.workflow_id
        assert len(client.calls) == 2
        assert client.calls[0][1].entity_identity == {"domain": "example.com"}

    @pytest.mark.asyncio
    async def test_temporal_dispatch_defers_on_connection_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from services import temporal_materialization_dispatch as dispatch

        async def fail():
            raise OSError("temporal down")

        monkeypatch.setattr("workflow.client.connect_temporal", fail)
        launch = await dispatch.start_entity_materialization(
            tenant_id="t1", entity_id="e1", identity={"domain": "example.com"}
        )
        assert launch.status == "DEFERRED"
        assert launch.workflow_id.endswith(launch.run_id)

    def test_investigation_workflow_has_signal_handlers(self):
        from workflows.investigation import InvestigationWorkflow

        for name in ("pause", "resume", "approve", "reject", "schedule_recrawl", "complete"):
            assert hasattr(InvestigationWorkflow, name), name
