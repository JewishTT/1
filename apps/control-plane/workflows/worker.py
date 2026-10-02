"""Temporal worker entrypoint.

Feature 024 T028 (D3=b): ``InvestigationWorkflow`` and ``RecrawlWorkflow`` were
declared with ``@workflow.defn`` on task queue ``cognitive-investigations``
(``workflows/investigation.py:39``), and no worker was registered on that queue. The
only registered workflow was ``TemporalEntityMaterializationWorkflow`` on its own
queue. Both investigation workflows were therefore unreachable -- the same class of
dead code as Layer 0, found by reading the worker rather than the workflow module.

They are now registered on their own queue, with the activities their bodies
schedule (``workflows/investigation_activities.py``).

Both queues are served by this one worker process. They are separate task queues
rather than one, so materialization and investigation scale independently and a
long investigation cannot starve entity materialization.
"""

from __future__ import annotations

import asyncio
import logging

from temporalio.worker import Worker
from workflow.client import connect_temporal

from workflows.investigation import (
    TASK_QUEUE as INVESTIGATION_TASK_QUEUE,
)
from workflows.investigation import (
    InvestigationWorkflow,
    RecrawlWorkflow,
)
from workflows.investigation_activities import ACTIVITIES as INVESTIGATION_ACTIVITIES
from workflows.temporal_materialization import (
    TASK_QUEUE,
    TemporalEntityMaterializationWorkflow,
    reconcile_and_publish,
)

log = logging.getLogger("cognitive.worker")

#: Materialization queue -- entity stream projection (pre-existing).
MATERIALIZATION_WORKFLOWS = [TemporalEntityMaterializationWorkflow]
MATERIALIZATION_ACTIVITIES = [reconcile_and_publish]

#: Investigation queue -- investigation lifecycle and recrawls (Feature 024 T028).
INVESTIGATION_WORKFLOWS = [InvestigationWorkflow, RecrawlWorkflow]
INVESTIGATION_ACTIVITIES = list(INVESTIGATION_ACTIVITIES)


async def run_worker() -> None:
    """Run both durable task queues until process shutdown."""
    client = await connect_temporal()
    await asyncio.gather(
        Worker(
            client,
            task_queue=TASK_QUEUE,
            workflows=MATERIALIZATION_WORKFLOWS,
            activities=MATERIALIZATION_ACTIVITIES,
        ).run(),
        Worker(
            client,
            task_queue=INVESTIGATION_TASK_QUEUE,
            workflows=INVESTIGATION_WORKFLOWS,
            activities=INVESTIGATION_ACTIVITIES,
        ).run(),
    )


async def run_worker_with_relay() -> None:
    """Run Temporal queues and the durable outbox relay concurrently."""
    from services.materialization_outbox_relay import run_outbox_relay_forever

    await asyncio.gather(run_worker(), run_outbox_relay_forever())


if __name__ == "__main__":
    asyncio.run(run_worker_with_relay())


__all__ = [
    "INVESTIGATION_ACTIVITIES",
    "INVESTIGATION_TASK_QUEUE",
    "INVESTIGATION_WORKFLOWS",
    "MATERIALIZATION_ACTIVITIES",
    "MATERIALIZATION_WORKFLOWS",
    "run_worker",
    "run_worker_with_relay",
]