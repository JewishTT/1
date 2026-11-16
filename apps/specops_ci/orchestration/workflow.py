"""Temporal Workflow entrypoint for the versioned LangGraph SpecOps operation."""
from __future__ import annotations

from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from langgraph.checkpoint.memory import InMemorySaver
    from temporalio.langgraph import graph as temporal_graph

from specops_ci.orchestration.graph import GRAPH_NAME


@workflow.defn(name=GRAPH_NAME)
class SpecOpsOperationWorkflow:
    """Durably execute an immutable Spec Graph with Activity retries and HITL interrupts."""

    @workflow.run
    async def run(self, initial_state: dict[str, Any]) -> dict[str, Any]:
        operation_id = str(initial_state["operation_id"])
        app = temporal_graph(GRAPH_NAME).compile(checkpointer=InMemorySaver())
        return await app.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": operation_id}},
        )


__all__ = ["SpecOpsOperationWorkflow"]
