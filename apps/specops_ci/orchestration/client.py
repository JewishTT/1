"""Submission helpers for immutable SpecOps&CI operations.

Authorization must be loaded from the durable store and checked for revocation by
the calling application before this helper is called. Every step revalidates it again
inside the worker immediately before touching the ARTEX adapter.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from temporalio.client import Client, WorkflowHandle

from specops_ci.domain import EngagementAuthorization
from specops_ci.orchestration.contracts import (
    OperationSpec,
    validate_operation_against_authorization,
)
from specops_ci.orchestration.workflow import SpecOpsOperationWorkflow


async def start_operation(
    client: Client,
    spec: OperationSpec,
    authorization: EngagementAuthorization,
    *,
    now: datetime | None = None,
    task_queue: str | None = None,
) -> WorkflowHandle[Any, Any]:
    """Start a durable operation after validating its current approval and frozen scope."""
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
        SpecOpsOperationWorkflow.run,
        initial_state,
        id=spec.operation_id,
        task_queue=task_queue or os.environ.get(
            "SPECOPS_CI_TASK_QUEUE",
            "specops-ci-operations",
        ),
    )
