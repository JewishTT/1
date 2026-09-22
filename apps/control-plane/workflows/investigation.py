"""Investigation + recrawl workflows for Temporal (T078, FR-022).

The workflows are thin Temporal glue around a deterministic lifecycle state
machine (`InvestigationLifecycle`) so that state transitions, pause/resume,
human approval, scheduled recrawls and recovery are testable without a Temporal
server. Temporal (T016 client, `apps/shared/workflow/client.py`) provides the
worker connection, durability, retries and recovery — the lifecycle here only
ever schedules work and records the resulting state as checkpoints.

Investigation monitoring (feature 005 US5, T029)
================================================
Donor: investigator (MIT) ``donors/investigator/src/investigator/state/investigation.py``.
License: MIT (logic layer only).

Adaptation notes
----------------
- Each lifecycle transition now also resolves to a catalog ``investigation.*``
  event type (``state_event_type``) recorded as an ``investigation.state_event``
  marker, and completion records a one-shot ``investigation.snapshot`` marker
  from the domain monitor — the "persist once at close" invariant. Markers stay
  deterministic (no I/O inside the workflow; the event bus is fed by the
  activity/route layer from these markers, matching the existing
  ``record_marker("checkpoint", ...)`` pattern).
- The monitor counters/failed counters themselves are owned by
  ``cp_domain.investigation.InvestigationMonitor`` (T028) and reused here.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import ClassVar

from temporalio import workflow

from cp_domain.investigation import InvestigationMonitor

TASK_QUEUE = "cognitive-investigations"


def state_event_type(state: LifecycleState) -> str:
    """Map a lifecycle state to the ``investigation.*`` catalog event type."""
    return {
        LifecycleState.CREATED: "investigation.created",
        LifecycleState.QUEUED: "investigation.updated",
        LifecycleState.ACQUIRING: "investigation.started",
        LifecycleState.AWAITING_APPROVAL: "investigation.updated",
        LifecycleState.APPROVED: "investigation.updated",
        LifecycleState.REJECTED: "investigation.updated",
        LifecycleState.RECRAWL: "investigation.updated",
        LifecycleState.COMPLETED: "investigation.completed",
        LifecycleState.PAUSED: "investigation.paused",
    }[state]


class LifecycleState(enum.StrEnum):
    CREATED = "created"
    QUEUED = "queued"
    ACQUIRING = "acquiring"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    RECRAWL = "recrawl"
    COMPLETED = "completed"
    PAUSED = "paused"


class InvalidLifecycleTransition(Exception):
    pass


@dataclass
class LifecycleConfig:
    autostart: bool = True
    approval_required: bool = False
    recrawl_interval: timedelta = timedelta(hours=6)
    max_acquire_steps: int = 3


@dataclass
class InvestigationLifecycle:
    """Deterministic investigation state machine (pure logic, no I/O)."""

    investigation_id: str
    config: LifecycleConfig
    state: LifecycleState = LifecycleState.CREATED
    step: int = 0
    recrawl_at: datetime | None = None
    events: list[dict] = field(default_factory=list)
    monitor: InvestigationMonitor = field(default_factory=InvestigationMonitor)

    _ALLOWED: ClassVar[dict[LifecycleState, tuple[LifecycleState, ...]]] = {
        LifecycleState.CREATED: (LifecycleState.QUEUED, LifecycleState.PAUSED),
        LifecycleState.QUEUED: (
            LifecycleState.ACQUIRING,
            LifecycleState.AWAITING_APPROVAL,
            LifecycleState.PAUSED,
            LifecycleState.COMPLETED,
        ),
        LifecycleState.ACQUIRING: (
            LifecycleState.ACQUIRING,
            LifecycleState.AWAITING_APPROVAL,
            LifecycleState.RECRAWL,
            LifecycleState.PAUSED,
            LifecycleState.COMPLETED,
        ),
        LifecycleState.AWAITING_APPROVAL: (
            LifecycleState.APPROVED,
            LifecycleState.REJECTED,
            LifecycleState.PAUSED,
        ),
        LifecycleState.APPROVED: (LifecycleState.ACQUIRING, LifecycleState.RECRAWL),
        LifecycleState.REJECTED: (LifecycleState.COMPLETED, LifecycleState.QUEUED),
        LifecycleState.RECRAWL: (LifecycleState.ACQUIRING, LifecycleState.COMPLETED),
        LifecycleState.PAUSED: (LifecycleState.QUEUED, LifecycleState.COMPLETED),
        LifecycleState.COMPLETED: (),
    }

    def advance(self, event: str, at: datetime | None = None) -> LifecycleState:
        """Apply one lifecycle event and return the new state."""
        at = at or datetime.now(UTC)
        transitions: dict[str, LifecycleState] = {
            "enqueue": LifecycleState.QUEUED,
            "acquire": LifecycleState.ACQUIRING,
            "pause": LifecycleState.PAUSED,
            "resume": LifecycleState.QUEUED,
            "need_approval": LifecycleState.AWAITING_APPROVAL,
            "approve": LifecycleState.APPROVED,
            "reject": LifecycleState.REJECTED,
            "schedule_recrawl": LifecycleState.RECRAWL,
            "complete": LifecycleState.COMPLETED,
        }
        if event not in transitions:
            raise InvalidLifecycleTransition(f"Unknown event: {event}")
        target = transitions[event]
        if target not in self._ALLOWED[self.state]:
            raise InvalidLifecycleTransition(
                f"investigation {self.investigation_id}: {self.state} --{event}--> {target}"
            )
        if target == LifecycleState.ACQUIRING:
            self.step += 1
            if self.config.max_acquire_steps and self.step > self.config.max_acquire_steps:
                return self.advance("complete", at)
        if target == LifecycleState.RECRAWL:
            self.recrawl_at = at + self.config.recrawl_interval
        self.state = target
        self.events.append(
            {
                "event": event,
                "to": target.value,
                "at": at.isoformat(),
                "event_type": state_event_type(target),
            }
        )
        return self.state

    def auto_start(self, at: datetime | None = None) -> LifecycleState:
        if self.state is not LifecycleState.CREATED:
            return self.state
        nxt = self.advance("enqueue", at)
        if self.config.approval_required:
            return self.advance("need_approval", at)
        if self.config.autostart:
            return self.advance("acquire", at)
        return nxt

    def checkpoint(self) -> dict:
        """Durable checkpoint — recovery resumes from here (FR-022 recovery)."""
        return {
            "investigation_id": self.investigation_id,
            "state": self.state.value,
            "step": self.step,
            "recrawl_at": self.recrawl_at.isoformat() if self.recrawl_at else None,
            "event_count": len(self.events),
        }

    @classmethod
    def recover(cls, checkpoint: dict, config: LifecycleConfig) -> InvestigationLifecycle:
        """Rebuild lifecycle from a durable checkpoint (workflow recovery)."""
        lc = cls(investigation_id=checkpoint["investigation_id"], config=config)
        lc.state = LifecycleState(checkpoint["state"])
        lc.step = checkpoint["step"]
        if checkpoint.get("recrawl_at"):
            lc.recrawl_at = datetime.fromisoformat(checkpoint["recrawl_at"])
        return lc


@workflow.defn
class InvestigationWorkflow:
    """Long-running investigation workflow.

    Drives the lifecycle over Temporal signals/activities: acquire batches,
    await human approval when configured, pause/resume on demand, schedule
    recrawls, and complete. Temporal replays history (durability + recovery);
    every mutation passes through the deterministic lifecycle and is recorded
    as a marker so a recovered run resumes from the last checkpoint.
    """

    def __init__(self) -> None:
        self._lifecycle: InvestigationLifecycle | None = None

    @workflow.run
    async def run(self, investigation_id: str, config: LifecycleConfig) -> dict:
        self._lifecycle = InvestigationLifecycle(
            investigation_id=investigation_id,
            config=config or LifecycleConfig(),
        )
        self._lifecycle.auto_start(workflow.now())
        workflow.record_marker("checkpoint", self._lifecycle.checkpoint())
        if self._lifecycle.state in (LifecycleState.ACQUIRING, LifecycleState.APPROVED):
            await workflow.execute_activity(
                "acquisition.acquire_batch",
                args=[investigation_id, self._lifecycle.step],
                task_queue=TASK_QUEUE,
            )
        while self._lifecycle.state is not LifecycleState.COMPLETED:
            workflow.wait_condition(
                lambda: self._lifecycle.state in (
                    LifecycleState.APPROVED,
                    LifecycleState.QUEUED,
                    LifecycleState.RECRAWL,
                    LifecycleState.COMPLETED,
                )
            )
        workflow.record_marker(
            "investigation.snapshot",
            self._lifecycle.monitor.snapshot(
                self._lifecycle.investigation_id, "COMPLETED", workflow.now()
            ),
        )
        return {"investigation_id": investigation_id, "state": self._lifecycle.state.value}

    @workflow.signal
    async def pause(self) -> None:
        self._apply("pause")

    @workflow.signal
    async def resume(self) -> None:
        self._apply("resume")

    @workflow.signal
    async def approve(self) -> None:
        self._apply("approve")

    @workflow.signal
    async def reject(self) -> None:
        self._apply("reject")

    @workflow.signal
    async def schedule_recrawl(self) -> None:
        self._apply("schedule_recrawl")

    @workflow.signal
    async def complete(self) -> None:
        self._apply("complete")

    def _apply(self, event: str) -> LifecycleState:
        if self._lifecycle is None:
            raise InvalidLifecycleTransition("lifecycle not started")
        self._lifecycle.advance(event, workflow.now())
        workflow.record_marker("checkpoint", self._lifecycle.checkpoint())
        workflow.record_marker(
            "investigation.state_event",
            {
                "event": event,
                "to": self._lifecycle.state.value,
                "event_type": state_event_type(self._lifecycle.state),
                "at": workflow.now().isoformat(),
            },
        )
        if event in ("approve", "reject") and self._lifecycle.state is LifecycleState.APPROVED:
            workflow.record_marker("human_approval", {"decision": event})
        return self._lifecycle.state


@workflow.defn
class RecrawlWorkflow:
    """Scheduled recrawl: sleeps until the next recrawl, signals the parent
    investigation, and re-runs the acquisition activity until stopped."""

    @workflow.run
    async def run(self, investigation_id: str, interval_seconds: int) -> None:
        while True:
            await workflow.sleep(timedelta(seconds=interval_seconds))
            workflow.signal(InvestigationWorkflow, "schedule_recrawl")
            await workflow.execute_activity(
                "acquisition.recrawl",
                args=[investigation_id],
                task_queue=TASK_QUEUE,
            )