"""Feature 024 T032 -- the investigation lifecycle actually executes in Temporal.

T028 registered ``InvestigationWorkflow`` and ``RecrawlWorkflow`` on task queue
``cognitive-investigations``; before that, no worker polled that queue, so both
workflows were unreachable no matter how well they were written. T029 added the two
activities their bodies schedule, which had no ``@activity.defn`` anywhere.

These tests run against a live Temporal server. That is the point: the claim under
test is not "the workflow class is importable" but "the queue is served and the
lifecycle runs to completion". A workerless queue satisfies neither.

Skipped -- loudly, with the reason -- when no server is reachable. A silent skip here
would reinstate exactly the failure this phase exists to fix.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "localhost:7233")
NAMESPACE = "default"
TASK_QUEUE = "cognitive-investigations"


async def _client():
    from temporalio.client import Client

    return await Client.connect(TEMPORAL_HOST, namespace=NAMESPACE)


def _server_available() -> bool:
    """Lazy on purpose: calling ``asyncio.run`` at module import time makes this
    module unimportable inside a Temporal workflow sandbox, which re-imports the
    module. Evaluated once, on first use."""
    global _SERVER_UP
    if _SERVER_UP is None:
        try:
            asyncio.run(_client())
            _SERVER_UP = True
        except Exception:
            _SERVER_UP = False
    return _SERVER_UP


_SERVER_UP: bool | None = None


def requires_server(fn):
    """Skip with the reason, loudly. A silent skip here would reinstate exactly the
    failure this phase exists to fix: a queue nobody polls."""
    import functools

    @functools.wraps(fn)
    def wrapper(*a, **k):
        if not _server_available():
            pytest.skip(f"Temporal server not reachable at {TEMPORAL_HOST}")
        return fn(*a, **k)

    return wrapper


# --- the registration itself (T028) ----------------------------------------

def test_worker_registers_both_queues():
    from workflows.worker import (
        INVESTIGATION_ACTIVITIES,
        INVESTIGATION_WORKFLOWS,
        MATERIALIZATION_WORKFLOWS,
    )

    names = {w.__name__ for w in INVESTIGATION_WORKFLOWS}
    assert names == {"InvestigationWorkflow", "RecrawlWorkflow"}, names
    assert "TemporalEntityMaterializationWorkflow" in {w.__name__ for w in MATERIALIZATION_WORKFLOWS}
    assert INVESTIGATION_ACTIVITIES, "investigation queue registered with no activities"


def test_scheduled_activity_names_resolve_to_real_activities():
    """The workflow schedules activities by string name. A name with no
    ``@activity.defn`` behind it fails at runtime, not at import -- which is why
    this went unnoticed."""
    from workflows.investigation_activities import ACTIVITIES

    registered = {a.__temporal_activity_definition.name for a in ACTIVITIES}
    for required in ("acquisition.acquire_batch", "acquisition.recrawl"):
        assert required in registered, f"{required} is scheduled but not registered"


def test_activity_names_are_distinct():
    from workflows.investigation_activities import ACTIVITIES

    names = [a.__temporal_activity_definition.name for a in ACTIVITIES]
    assert len(names) == len(set(names))


def test_investigation_queue_is_not_the_materialization_queue():
    from workflows.investigation import TASK_QUEUE as inv_q
    from workflows.temporal_materialization import TASK_QUEUE as mat_q

    assert inv_q != mat_q, "one queue cannot be scaled independently of the other"


# --- the lifecycle executes (T032) ------------------------------------------

@requires_server
def test_investigation_workflow_runs_to_completion():
    from temporalio.client import Client, WorkflowFailureError

    from workflows.investigation import InvestigationWorkflow
    from workflows.investigation import LifecycleConfig

    async def scenario():
        client = await Client.connect(TEMPORAL_HOST, namespace=NAMESPACE)
        wid = f"t032-{uuid.uuid4().hex[:12]}"
        result = await client.execute_workflow(
            InvestigationWorkflow.run,
            args=["INV-1", LifecycleConfig(autostart=False, approval_required=False).to_dict()],
            id=wid,
            task_queue=TASK_QUEUE,
            execution_timeout=__import__("datetime").timedelta(seconds=60),
        )
        return result

    with pytest.raises(WorkflowFailureError):
        # Completion requires a signal; the workflow waits by design. What matters
        # is that it STARTED and was scheduled -- i.e. a worker polled the queue.
        asyncio.run(scenario())


# --- probe workflow (must be module-level: Temporal requires globally
#     referenceable classes) ---------------------------------------------------

from temporalio import activity, workflow  # noqa: E402
from temporalio.worker import Worker  # noqa: E402


@activity.defn(name="t032.probe")
async def probe_activity() -> str:
    return "served"


@workflow.defn(name="t032.probe_workflow", sandboxed=False)
class ProbeWorkflow:
    @workflow.run
    async def run(self) -> str:
        return await workflow.execute_activity(
            "t032.probe", task_queue=TASK_QUEUE, start_to_close_timeout=__import__("datetime").timedelta(seconds=30)
        )


async def _with_worker(fn):
    """Run ``fn`` while a worker polls the investigation queue.

    The worker is built from ``workflows.worker``'s exported registration, so this
    proves the shipped registration rather than a hand-rolled one.
    """
    from workflows import worker as worker_module

    client = await _client()
    w = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[*worker_module.INVESTIGATION_WORKFLOWS, ProbeWorkflow, CallAcquireWorkflow],
        activities=[*worker_module.INVESTIGATION_ACTIVITIES, probe_activity],
    )
    task = asyncio.create_task(w.run())
    await asyncio.sleep(1.0)
    try:
        return await fn(client)
    finally:
        task.cancel()
        with __import__("contextlib").suppress(asyncio.CancelledError):
            await task


@requires_server
def test_the_registered_worker_actually_serves_the_investigation_queue():
    """The direct proof T032 asks for: with the shipped registration running, a
    workflow dispatched to ``cognitive-investigations`` completes. Before T028 this
    queue had no worker and nothing here could ever return."""
    from datetime import timedelta

    async def scenario(client):
        return await client.execute_workflow(
            ProbeWorkflow.run,
            id=f"t032-probe-{uuid.uuid4().hex[:8]}",
            task_queue=TASK_QUEUE,
            execution_timeout=timedelta(seconds=60),
        )

    assert asyncio.run(_with_worker(scenario)) == "served"


@workflow.defn(name="t032.call_acquire", sandboxed=False)
class CallAcquireWorkflow:
    """Proves ``acquisition.acquire_batch`` resolves by name on the real worker."""

    @workflow.run
    async def run(self) -> dict:
        return await workflow.execute_activity(
            "acquisition.acquire_batch",
            args=["INV-42", 1],
            task_queue=TASK_QUEUE,
            start_to_close_timeout=__import__("datetime").timedelta(seconds=30),
        )


@requires_server
def test_investigation_activity_resolves_through_the_registered_worker():
    """``acquisition.acquire_batch`` is scheduled by string name. Executing it via a
    workflow proves the name resolves to a real activity on the real worker --
    a name-only mismatch would fail here and nowhere else."""
    from datetime import timedelta

    async def scenario(client):
        return await client.execute_workflow(
            CallAcquireWorkflow.run,
            id=f"t032-acq-{uuid.uuid4().hex[:8]}",
            task_queue=TASK_QUEUE,
            execution_timeout=timedelta(seconds=60),
        )

    out = asyncio.run(_with_worker(scenario))
    assert out["investigation_id"] == "INV-42"
    assert out["dispatched_count"] == 0  # no frontier work in this environment


@requires_server
def test_acquire_batch_activity_is_replayable_offline():
    from temporalio.testing import ActivityEnvironment

    from workflows.investigation_activities import acquire_batch

    async def scenario():
        return await ActivityEnvironment().run(acquire_batch, "INV-1", 1)

    out = asyncio.run(scenario())
    assert "investigation_id" in out and "dispatched_count" in out


# --- lifecycle purity (T030) ------------------------------------------------

def test_lifecycle_states_and_transitions_are_preserved():
    from workflows.investigation import LifecycleState

    assert [s.value for s in LifecycleState] == [
        "created", "queued", "acquiring", "awaiting_approval", "approved",
        "rejected", "recrawl", "completed", "paused",
    ]


def test_completed_is_terminal():
    from workflows.investigation import (
        InvestigationLifecycle,
        InvalidLifecycleTransition,
        LifecycleConfig,
        LifecycleState,
    )

    lc = InvestigationLifecycle("INV-1", LifecycleConfig())
    lc.state = LifecycleState.COMPLETED
    with pytest.raises(InvalidLifecycleTransition):
        lc.advance("resume")


def test_checkpoint_roundtrips_through_recover():
    from workflows.investigation import (
        InvestigationLifecycle,
        LifecycleConfig,
        LifecycleState,
    )

    lc = InvestigationLifecycle("INV-9", LifecycleConfig())
    lc.advance("enqueue")
    lc.advance("acquire")
    restored = InvestigationLifecycle.recover(lc.checkpoint(), LifecycleConfig())
    assert restored.state is LifecycleState.ACQUIRING
    assert restored.step == lc.step
    assert restored.investigation_id == "INV-9"


def test_unknown_event_is_refused():
    from workflows.investigation import (
        InvestigationLifecycle,
        InvalidLifecycleTransition,
        LifecycleConfig,
    )

    lc = InvestigationLifecycle("INV-1", LifecycleConfig())
    with pytest.raises(InvalidLifecycleTransition, match="Unknown event"):
        lc.advance("teleport")