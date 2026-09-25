"""Temporal launch seam for entity-created temporal materialization."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from workflows.temporal_materialization import (
    TASK_QUEUE,
    MaterializationWorkflowInput,
    TemporalEntityMaterializationWorkflow,
)


@dataclass(frozen=True)
class MaterializationLaunch:
    run_id: str
    workflow_id: str
    status: str
    reason: str = ""


def _fingerprint(value: Any) -> str:
    material = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


async def _enqueue_durable(tenant_id: str, entity_id: str, run_id: str, workflow_id: str, identity: dict[str, Any]) -> None:
    from db.materialization_outbox import SqlMaterializationOutbox
    from db.session import create_tables, make_session_factory
    await create_tables()
    async with make_session_factory()() as session:
        await SqlMaterializationOutbox(session).enqueue(
            tenant_id=tenant_id, entity_id=entity_id, run_id=run_id,
            workflow_id=workflow_id, identity=identity,
        )


async def start_entity_materialization(
    *,
    tenant_id: str,
    entity_id: str,
    identity: dict[str, Any],
) -> MaterializationLaunch:
    """Start one deterministic Temporal workflow for an entity.

    The launch request is durably enqueued before the transport call when
    PostgreSQL is reachable; a database outage never blocks Temporal.
    """
    identity_dict = {str(k): str(v) for k, v in identity.items()}
    run_id = "run-" + _fingerprint({"tenant_id": tenant_id, "entity_id": entity_id, "identity": identity_dict})[:24]
    workflow_id = f"{entity_id}/temporal-materialization/{run_id}"
    from workflow.client import connect_temporal

    from db.session import make_session_factory
    try:
        await asyncio.wait_for(_enqueue_durable(tenant_id, entity_id, run_id, workflow_id, identity_dict), timeout=0.75)
    except Exception as exc:  # noqa: BLE001 - DB outage must not lose Temporal request
        _outbox_reason = str(exc)

    request_source_ids = ()
    request = MaterializationWorkflowInput(
        tenant_id=tenant_id,
        entity_id=entity_id,
        source_record_ids=request_source_ids,
        run_id=run_id,
        entity_identity={str(k): str(v) for k, v in identity.items()},
    )
    try:
        client = await connect_temporal()
        await client.start_workflow(
            TemporalEntityMaterializationWorkflow.run,
            request,
            id=workflow_id,
            task_queue=TASK_QUEUE,
        )
        try:
            async with make_session_factory()() as session:
                from db.materialization_outbox import SqlMaterializationOutbox
                outbox = SqlMaterializationOutbox(session)
                row = await outbox.get(tenant_id=tenant_id, run_id=run_id)
                if row is not None:
                    await outbox.dispatched(row)
        except Exception:  # noqa: BLE001, S110 - launch succeeded; outbox ack is best effort
            pass
    except Exception as exc:  # noqa: BLE001 - any transport failure is deferred, never false-success
        return MaterializationLaunch(
            run_id=run_id,
            workflow_id=workflow_id,
            status="DEFERRED",
            reason=f"temporal unavailable: {exc}",
        )
    return MaterializationLaunch(run_id=run_id, workflow_id=workflow_id, status="QUEUED")


__all__ = ["MaterializationLaunch", "start_entity_materialization"]
