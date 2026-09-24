"""Temporal launch seam for entity-created temporal materialization."""

from __future__ import annotations

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


async def start_entity_materialization(
    *,
    tenant_id: str,
    entity_id: str,
    identity: dict[str, Any],
) -> MaterializationLaunch:
    """Start one deterministic Temporal workflow for an entity.

    The caller owns only the enqueue operation. Temporal owns retries,
    checkpoints and recovery; this function never performs the materialization
    fold in the API process.
    """
    from workflow.client import connect_temporal

    run_id = "run-" + _fingerprint({"tenant_id": tenant_id, "entity_id": entity_id})[:24]
    workflow_id = f"{entity_id}/temporal-materialization/{run_id}"
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
    except Exception as exc:  # noqa: BLE001 - any transport failure is deferred, never false-success
        return MaterializationLaunch(
            run_id=run_id,
            workflow_id=workflow_id,
            status="DEFERRED",
            reason=f"temporal unavailable: {exc}",
        )
    return MaterializationLaunch(run_id=run_id, workflow_id=workflow_id, status="QUEUED")


__all__ = ["MaterializationLaunch", "start_entity_materialization"]
