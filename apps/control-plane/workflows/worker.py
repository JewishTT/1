"""Temporal worker entrypoint for temporal materialization."""

from __future__ import annotations

import asyncio

from temporalio.worker import Worker
from workflow.client import connect_temporal

from workflows.temporal_materialization import (
    TASK_QUEUE,
    TemporalEntityMaterializationWorkflow,
    reconcile_and_publish,
)


async def run_worker() -> None:
    """Run the durable materialization worker until process shutdown."""
    client = await connect_temporal()
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[TemporalEntityMaterializationWorkflow],
        activities=[reconcile_and_publish],
    )
    await worker.run()


async def run_worker_with_relay() -> None:
    """Run Temporal activities and the durable outbox relay concurrently."""
    from services.materialization_outbox_relay import run_outbox_relay_forever
    await asyncio.gather(run_worker(), run_outbox_relay_forever())


if __name__ == "__main__":
    asyncio.run(run_worker_with_relay())


__all__ = ["run_worker", "run_worker_with_relay"]
