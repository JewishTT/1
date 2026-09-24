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


if __name__ == "__main__":
    asyncio.run(run_worker())


__all__ = ["run_worker"]
