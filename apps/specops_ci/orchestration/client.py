"""Submission helpers for immutable SpecOps&CI operations.

This module depends only on Temporal's Python SDK, not LangGraph. The control plane
can therefore submit/query workflows without installing the experimental worker plugin.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any

from temporalio.client import Client, WorkflowHandle

from specops_ci.domain import EngagementAuthorization
from specops_ci.orchestration.contracts import (
    OperationSpec,
    validate_operation_against_authorization,
)


SPECOPS_CI_WORKFLOW_TYPE = "specops-ci-operation-v1"
DEFAULT_TASK_QUEUE = "specops-ci-operations"


async def start_operation(
    client: Client,
    spec: OperationSpec,
    authorization: EngagementAuthorization,
    *,
    now: datetime | None = None,
    task_queue: str | None = None,
) -> WorkflowHandle[Any, Any]:
    """Start a durable operation after validating its current approval and frozen scope.

    The caller must load the authorization from the tenant-scoped durable store and
    reject revoked records before calling this helper. Each worker Activity independently
    revalidates it again immediately before reading or writing the ARTEX graph adapter.
    """
    current_time = now or datetime.now(timezone.utc)
    validate_operation_against_authorization(
        spec,
        authorization,
        now=current_time,
    )
    initial_state = {
        "operation_id": spec.operation_id,
        "spec": spec.to_payload(),
        "spec_digest": spec.digest(),
        "current_step_index": 0,
        "results": [],
        "status": "submitted",
        "error_code": "",
    }
    return await client.start_workflow(
        SPECOPS_CI_WORKFLOW_TYPE,
        initial_state,
        id=spec.operation_id,
        task_queue=task_queue or os.environ.get(
            "SPECOPS_CI_TASK_QUEUE",
            DEFAULT_TASK_QUEUE,
        ),
    )


__all__ = ["SPECOPS_CI_WORKFLOW_TYPE", "start_operation"]
