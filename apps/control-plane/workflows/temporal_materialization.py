"""Temporal workflow for deterministic entity materialization (feature 014)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

TASK_QUEUE = "cognitive-temporal-materialization"


@dataclass(frozen=True)
class MaterializationWorkflowInput:
    tenant_id: str
    entity_id: str
    source_record_ids: tuple[str, ...]
    run_id: str
    mode: str = "rebuild"


@workflow.defn
class TemporalEntityMaterializationWorkflow:
    """Thin durable orchestration around deterministic materialization activities."""

    @workflow.run
    async def run(self, request: MaterializationWorkflowInput) -> dict[str, Any]:
        if not request.tenant_id or not request.entity_id or not request.run_id:
            raise ValueError("tenant_id, entity_id, and run_id are required")
        workflow.record_marker(
            "materialization.started",
            {
                "tenant_id": request.tenant_id,
                "entity_id": request.entity_id,
                "run_id": request.run_id,
                "source_record_ids": list(request.source_record_ids),
            },
        )
        result = await workflow.execute_activity(
            "temporal_materialization.reconcile_and_publish",
            args=[
                request.tenant_id,
                request.entity_id,
                list(request.source_record_ids),
                request.run_id,
            ],
            task_queue=TASK_QUEUE,
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        workflow.record_marker("materialization.ready", result)
        return result


__all__ = ["TASK_QUEUE", "MaterializationWorkflowInput", "TemporalEntityMaterializationWorkflow"]
