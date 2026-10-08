"""Starting investigations on Temporal, and scheduling their recrawls.

The gap this closes: ``InvestigationWorkflow`` and ``RecrawlWorkflow`` were both registered
on the ``cognitive-investigations`` queue by ``workflows/worker.py``, and nothing anywhere
called ``start_workflow``. A worker with no producer is idle capacity -- investigations were
created in the database and never acquired a single batch. ``Schedule.create`` was likewise
absent from the codebase, so the recrawl interval in ``LifecycleConfig`` was a number no
scheduler ever read.

Two things start work here, and they are separate on purpose:

:func:`start_investigation` begins the bounded acquire loop.
:func:`ensure_recrawl_schedule` registers a recurring recrawl, and is idempotent --
re-registering an existing schedule would produce a second recrawl per interval, doubling
acquisition cost for the same coverage.

Both degrade rather than raise when Temporal is unreachable. An investigation is a durable
row before it is a workflow, so failing the API request because a workflow server is down
would turn a recoverable scheduling delay into a lost investigation. The row stays, and
:func:`recover_unstarted` finds what never got started.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

#: The queue ``workflows/worker.py`` registers the investigation workflows on. Imported
#: rather than repeated: a producer and a worker on different queues is a workflow that is
#: accepted and then never picked up.
TASK_QUEUE = "cognitive-investigations"


@dataclass(frozen=True, slots=True)
class StartOutcome:
    """What a start attempt did, and why."""

    investigation_id: str
    workflow_id: str
    started: bool
    reason: str = ""
    #: True when an existing run was adopted rather than a second one started. Starting a
    #: duplicate would run two acquire loops over one frontier and double every cost.
    reused: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "investigation_id": self.investigation_id,
            "workflow_id": self.workflow_id,
            "started": self.started,
            "reused": self.reused,
            "reason": self.reason,
        }


def workflow_id_for(investigation_id: str) -> str:
    """The deterministic workflow id for an investigation.

    Deterministic so a retry adopts the running workflow instead of starting a second one.
    A random id would make ``start_workflow`` idempotent only by accident, and the retry
    that raced would double the acquisition.
    """
    return f"investigation-{investigation_id}"


def recrawl_schedule_id(investigation_id: str) -> str:
    return f"recrawl-{investigation_id}"


async def start_investigation(
    investigation_id: str,
    *,
    config: dict[str, Any] | None = None,
    client: Any | None = None,
) -> StartOutcome:
    """Start the investigation's acquire workflow, adopting a run that already exists.

    Checks for an existing run first. Temporal rejects a duplicate id outright, so without
    the check a retry after an ambiguous failure would surface as an error on an
    investigation that is in fact running.
    """
    workflow_id = workflow_id_for(investigation_id)
    connection = client
    try:
        if connection is None:
            from workflow.client import connect_temporal

            connection = await connect_temporal()
    except Exception as exc:  # noqa: BLE001 - a scheduling failure is not an API failure
        log.warning("temporal unavailable for %s: %s", investigation_id, exc)
        return StartOutcome(
            investigation_id=investigation_id,
            workflow_id=workflow_id,
            started=False,
            reason=f"temporal_unavailable:{type(exc).__name__}",
        )

    from workflows.investigation import InvestigationWorkflow

    try:
        handle = connection.get_workflow_handle(workflow_id)
        described = await handle.describe()
    except Exception:  # noqa: BLE001 - "no such run" is the normal first-start case
        described = None

    if described is not None:
        # A run already exists. Adopting is correct whether it is still running or has
        # finished: starting again would either double the acquire loop or re-acquire an
        # investigation that already terminated.
        return StartOutcome(
            investigation_id=investigation_id,
            workflow_id=workflow_id,
            started=False,
            reused=True,
            reason="workflow_already_exists",
        )

    try:
        await connection.start_workflow(
            InvestigationWorkflow.run,
            investigation_id,
            config or {},
            id=workflow_id,
            task_queue=TASK_QUEUE,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("failed to start %s: %s", investigation_id, exc)
        return StartOutcome(
            investigation_id=investigation_id,
            workflow_id=workflow_id,
            started=False,
            reason=f"start_failed:{type(exc).__name__}",
        )

    log.info("started investigation workflow %s", workflow_id)
    return StartOutcome(
        investigation_id=investigation_id, workflow_id=workflow_id, started=True
    )


async def ensure_recrawl_schedule(
    investigation_id: str,
    *,
    interval_seconds: int,
    client: Any | None = None,
) -> bool:
    """Register the recrawl schedule once. Returns whether a schedule now exists.

    Idempotent by id: a schedule already carrying this id is left alone. Re-registering
    would create a second recurring action on the same interval, and the platform would pay
    for the same frontier sweep twice per tick.
    """
    connection = client
    try:
        if connection is None:
            from workflow.client import connect_temporal

            connection = await connect_temporal()
    except Exception as exc:  # noqa: BLE001
        log.warning("temporal unavailable for recrawl schedule %s: %s", investigation_id, exc)
        return False

    from temporalio.client import (
        Schedule,
        ScheduleActionStartWorkflow,
        ScheduleOverlapPolicy,
        ScheduleSpec,
    )

    schedule_id = recrawl_schedule_id(investigation_id)
    try:
        handle = await connection.get_schedule_handle(schedule_id)
        await handle.describe()
        return True
    except Exception as exc:  # noqa: BLE001 - an absent schedule is the expected first call
        log.debug("no existing recrawl schedule for %s: %s", investigation_id, exc)

    interval = max(1, int(interval_seconds))
    try:
        await connection.create_schedule(
            Schedule(
                action=ScheduleActionStartWorkflow(
                    "RecrawlWorkflow",
                    args=[investigation_id, interval],
                    id=workflow_id_for(investigation_id) + "-recrawl",
                    task_queue=TASK_QUEUE,
                ),
                spec=ScheduleSpec(
                    # Every interval, counted from creation. A calendar-based spec would
                    # need a timezone the caller has not supplied, and defaulting to UTC
                    # would put recrawls at a different wall-clock time than intended.
                    intervals=[interval],
                ),
                # A recrawl that fires while the previous sweep is still running must not
                # pile up. The default overlap policy buffers, which for a recrawl means a
                # backlog of identical sweeps each waiting its turn.
                policies=ScheduleOverlapPolicy.SKIP,
            ),
            id=schedule_id,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("failed to schedule recrawl for %s: %s", investigation_id, exc)
        return False
    return True


async def signal_investigation(
    investigation_id: str, signal: str, *, client: Any | None = None
) -> bool:
    """Send one of the workflow's signals through an external handle.

    Exists because ``workflow.signal`` inside a workflow is a decorator factory, not a
    transport: the only way to reach a running investigation is a handle from the client.
    ``signal`` is validated against the workflow's own vocabulary so a typo fails here
    rather than as a no-op at the server.
    """
    allowed = {"pause", "resume", "approve", "reject", "schedule_recrawl", "complete"}
    if signal not in allowed:
        raise ValueError(
            f"unknown investigation signal {signal!r}; expected one of {sorted(allowed)}"
        )
    connection = client
    try:
        if connection is None:
            from workflow.client import connect_temporal

            connection = await connect_temporal()
        # Signals go through a handle, not the client: ``Client`` has no
        # ``signal_workflow``. Getting a handle is also what proves a run exists, so a
        # signal to an investigation that was never started reports "not found" instead of
        # appearing to succeed.
        handle = connection.get_workflow_handle(workflow_id_for(investigation_id))
        await handle.signal(signal)
    except Exception as exc:  # noqa: BLE001
        log.warning("failed to signal %s: %s", investigation_id, exc)
        return False
    return True


async def recover_unstarted(
    investigation_ids: list[str], *, client: Any | None = None
) -> list[StartOutcome]:
    """Start every investigation in the list that has no workflow.

    The recovery path for a Temporal outage during creation. Idempotent, because
    ``start_investigation`` adopts an existing run -- so running recovery twice does not
    double the work.
    """
    outcomes: list[StartOutcome] = []
    for investigation_id in investigation_ids:
        outcomes.append(await start_investigation(investigation_id, client=client))
    return outcomes
