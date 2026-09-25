"""Relay durable materialization outbox rows to Temporal."""
from __future__ import annotations

import asyncio

from db.materialization_outbox import SqlMaterializationOutbox
from db.session import create_tables, make_session_factory


async def relay_materialization_outbox(*, limit: int = 20) -> dict[str, int]:
    """Claim pending rows and start idempotent Temporal workflows."""
    from workflow.client import connect_temporal

    from workflows.temporal_materialization import (
        TASK_QUEUE,
        MaterializationWorkflowInput,
        TemporalEntityMaterializationWorkflow,
    )

    await create_tables()
    counts = {"claimed": 0, "dispatched": 0, "failed": 0}
    async with make_session_factory()() as session:
        outbox = SqlMaterializationOutbox(session)
        rows = await outbox.claim_ready(limit=limit)
        counts["claimed"] = len(rows)
        for row in rows:
            try:
                client = await connect_temporal()
                request = MaterializationWorkflowInput(
                    tenant_id=row.tenant_id, entity_id=row.entity_id,
                    source_record_ids=(), run_id=row.run_id,
                    entity_identity={str(k): str(v) for k, v in (row.identity or {}).items()},
                )
                await client.start_workflow(
                    TemporalEntityMaterializationWorkflow.run,
                    request, id=row.workflow_id, task_queue=TASK_QUEUE,
                )
                await outbox.dispatched(row)
                counts["dispatched"] += 1
            except Exception as exc:  # noqa: BLE001 - relay retries from durable FAILED row
                await outbox.failed(row, str(exc))
                counts["failed"] += 1
    return counts


async def run_outbox_relay_forever(*, interval_seconds: float = 5.0) -> None:
    while True:
        await relay_materialization_outbox()
        await asyncio.sleep(interval_seconds)


__all__ = ["relay_materialization_outbox", "run_outbox_relay_forever"]
