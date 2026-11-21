"""Temporal Workflow entrypoint for the versioned LangGraph SpecOps operation.

HITL is implemented with a Temporal query (pending approval), signal (decision),
and LangGraph Command(resume=...). The Workflow may wait indefinitely without
occupying an Activity worker.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.types import Command
    from temporalio.langgraph import graph as temporal_graph

    from specops_ci.orchestration.graph import GRAPH_NAME


@workflow.defn(name=GRAPH_NAME)
class SpecOpsOperationWorkflow:
    """Durably execute an immutable Spec Graph with Activity retries and HITL signals."""

    def __init__(self) -> None:
        self._pending_approval: dict[str, Any] | None = None
        self._operator_decision: dict[str, Any] | None = None
        self._summary: dict[str, Any] = {}

    @workflow.signal
    async def provide_operator_decision(self, decision: dict[str, Any]) -> None:
        """Accept only a decision correlated to the currently pending graph interrupt."""
        pending = self._pending_approval
        if pending is None or not isinstance(decision, dict):
            return
        # Correlation is not authentication. The downstream Activity still verifies
        # reviewer identity, role, approval reference and signature via the trusted gate.
        if (
            decision.get("operation_id") != pending.get("operation_id")
            or decision.get("tenant_id") != pending.get("tenant_id")
            or decision.get("authorization_id") != pending.get("authorization_id")
            or decision.get("snapshot_id") != pending.get("snapshot_id")
            or decision.get("step_id") != pending.get("step_id")
            or decision.get("spec_digest") != pending.get("spec_digest")
            or not isinstance(decision.get("approved"), bool)
        ):
            return
        self._operator_decision = dict(decision)

    @workflow.query
    def get_pending_approval(self) -> dict[str, Any] | None:
        """Expose the exact approval challenge for the operator UI."""
        return dict(self._pending_approval) if self._pending_approval is not None else None

    @workflow.query
    def get_operation_summary(self) -> dict[str, Any]:
        """Expose a tenant-checkable operation status without leaking raw evidence."""
        return dict(self._summary)

    @workflow.run
    async def run(self, initial_state: dict[str, Any]) -> dict[str, Any]:
        operation_id = str(initial_state["operation_id"])
        spec_payload = initial_state["spec"]
        self._summary = {
            "operation_id": operation_id,
            "tenant_id": str(spec_payload["tenant_id"]),
            "authorization_id": str(spec_payload["authorization_id"]),
            "snapshot_id": str(spec_payload["snapshot_id"]),
            "spec_digest": str(initial_state["spec_digest"]),
            "status": "running",
            "current_step_index": 0,
            "step_count": len(spec_payload["steps"]),
        }
        app = temporal_graph(GRAPH_NAME).compile(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": operation_id}}

        # Each interrupt pauses the workflow. Temporal keeps the Workflow history
        # while the graph's Activity workers are free to serve other operations.
        result = await app.ainvoke(initial_state, config, version="v2")
        while True:
            interrupts = getattr(result, "interrupts", ())
            if not interrupts:
                output = getattr(result, "value", result)
                if not isinstance(output, dict):
                    raise TypeError("LangGraph returned a non-object operation result")
                self._pending_approval = None
                self._operator_decision = None
                self._summary["status"] = str(output.get("status", "completed"))
                self._summary["current_step_index"] = int(
                    output.get("current_step_index", self._summary["step_count"])
                )
                return output

            interrupt_value = interrupts[0].value
            if not isinstance(interrupt_value, dict):
                raise TypeError("SpecOps&CI graph emitted an invalid approval challenge")
            self._pending_approval = dict(interrupt_value)
            self._operator_decision = None
            self._summary["status"] = "awaiting_approval"
            current_value = getattr(result, "value", {})
            if isinstance(current_value, dict):
                self._summary["current_step_index"] = int(
                    current_value.get("current_step_index", self._summary["current_step_index"])
                )
            self._summary["pending_step_id"] = str(interrupt_value["step_id"])

            expires_at = datetime.fromisoformat(str(self._pending_approval["expires_at"]))
            remaining = expires_at - workflow.now()
            if remaining.total_seconds() <= 0:
                self._operator_decision = {
                    "operation_id": self._pending_approval["operation_id"],
                    "tenant_id": self._pending_approval["tenant_id"],
                    "authorization_id": self._pending_approval["authorization_id"],
                    "snapshot_id": self._pending_approval["snapshot_id"],
                    "step_id": self._pending_approval["step_id"],
                    "spec_digest": self._pending_approval["spec_digest"],
                    "approved": False,
                    "reason": "operation_expired",
                }
            else:
                try:
                    await workflow.wait_condition(
                        lambda: self._operator_decision is not None,
                        timeout=remaining,
                    )
                except TimeoutError:
                    # Expiry is a deterministic terminal rejection, not an approval.
                    self._operator_decision = {
                        "operation_id": self._pending_approval["operation_id"],
                        "tenant_id": self._pending_approval["tenant_id"],
                        "authorization_id": self._pending_approval["authorization_id"],
                        "snapshot_id": self._pending_approval["snapshot_id"],
                        "step_id": self._pending_approval["step_id"],
                        "spec_digest": self._pending_approval["spec_digest"],
                        "approved": False,
                        "reason": "operation_expired",
                    }
            decision = dict(self._operator_decision or {})
            self._pending_approval = None
            self._operator_decision = None
            self._summary["status"] = "running"
            self._summary.pop("pending_step_id", None)

            result = await app.ainvoke(
                Command(resume=decision),
                config,
                version="v2",
            )


__all__ = ["SpecOpsOperationWorkflow"]
