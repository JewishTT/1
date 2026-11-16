"""LangGraph operation graph executed through the Temporal LangGraph plugin.

Workflow nodes are deterministic and side-effect free. Database, ARTEX and identity
operations run only in Activity nodes. Every step is re-authorized immediately before
execution and every step has a distinct human approval interrupt.
"""
from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from specops_ci.orchestration.contracts import OperationSpec, SpecStepKind
from specops_ci.orchestration.runtime_ports import get_runtime_ports


GRAPH_NAME = "specops-ci-operation-v1"


class OperationState(TypedDict, total=False):
    operation_id: str
    spec: dict[str, Any]
    spec_digest: str
    current_step_index: int
    results: list[dict[str, Any]]
    last_result: dict[str, Any]
    operator_decision: dict[str, Any]
    authorization_valid: bool
    operator_decision_valid: bool
    status: str
    error_code: str


def _current_step(state: OperationState) -> tuple[OperationSpec, dict[str, Any]]:
    spec = OperationSpec.from_payload(state["spec"])
    index = int(state.get("current_step_index", 0))
    if index < 0 or index >= len(spec.steps):
        raise ValueError("current_step_index is outside the approved operation")
    step = spec.steps[index]
    return spec, {
        "step_id": step.step_id,
        "kind": step.kind.value,
        "target_entity_ids": list(step.target_entity_ids),
        "depends_on": list(step.depends_on),
        "requires_operator_approval": step.requires_operator_approval,
        "authorization_id": spec.authorization_id,
        "operation_expires_at": spec.expires_at.isoformat(),
    }


async def validate_spec_node(state: OperationState) -> dict[str, Any]:
    """Deterministically validate structure and immutable digest before any Activity."""
    spec = OperationSpec.from_payload(state["spec"])
    if state.get("operation_id") != spec.operation_id:
        raise ValueError("operation id does not match the supplied specification")
    if state.get("spec_digest") != spec.digest():
        raise ValueError("operation specification digest mismatch")
    return {
        "status": "validated",
        "current_step_index": 0,
        "results": [],
        "error_code": "",
    }


async def revalidate_authorization_node(state: OperationState) -> dict[str, Any]:
    """Re-check the durable approval and exact scope before each operation step."""
    spec, step = _current_step(state)
    valid = await get_runtime_ports().revalidate_authorization(
        tenant_id=spec.tenant_id,
        authorization_id=spec.authorization_id,
        snapshot_id=spec.snapshot_id,
        operation_expires_at=spec.expires_at.isoformat(),
        target_entity_ids=step["target_entity_ids"],
        step_kind=SpecStepKind(step["kind"]),
    )
    return {"authorization_valid": valid}


async def operator_approval_node(state: OperationState) -> dict[str, Any]:
    """Pause via LangGraph interrupt; Temporal persists the wait and resumes it by signal."""
    spec, step = _current_step(state)
    decision = interrupt(
        {
            "type": "specops_ci_step_approval",
            "operation_id": spec.operation_id,
            "step_id": step["step_id"],
            "step_kind": step["kind"],
            "target_entity_ids": step["target_entity_ids"],
            "spec_digest": spec.digest(),
            "approval_required": True,
        }
    )
    if not isinstance(decision, dict):
        return {"operator_decision": {"approved": False, "reason": "invalid_decision"}}
    return {"operator_decision": decision}


async def validate_operator_decision_node(state: OperationState) -> dict[str, Any]:
    """Delegate reviewer identity, role and decision-reference checks to the trusted gate."""
    spec, step = _current_step(state)
    decision = state.get("operator_decision", {})
    # A well-authenticated rejection is still a rejection; it must never flow into
    # execute_step just because the reviewer's identity was valid.
    if decision.get("approved") is not True:
        return {"operator_decision_valid": False}
    valid = await get_runtime_ports().validate_operator_decision(
        tenant_id=spec.tenant_id,
        operation_id=spec.operation_id,
        spec_digest=spec.digest(),
        step_id=step["step_id"],
        decision=decision,
    )
    return {"operator_decision_valid": valid}


async def execute_step_node(state: OperationState) -> dict[str, Any]:
    """Run one allow-listed, read-only or synthetic assessment activity."""
    spec, step = _current_step(state)
    if not step["requires_operator_approval"]:
        raise PermissionError("unapproved operation steps are forbidden")
    if not state.get("operator_decision_valid"):
        raise PermissionError("a verified operator decision is required")
    result = await get_runtime_ports().execute_safe_step(
        tenant_id=spec.tenant_id,
        operation_id=spec.operation_id,
        spec_digest=spec.digest(),
        snapshot_id=spec.snapshot_id,
        operation_expires_at=spec.expires_at.isoformat(),
        step=step,
    )
    return {"last_result": dict(result), "status": "step_completed"}


async def advance_step_node(state: OperationState) -> dict[str, Any]:
    """Apply a deterministic state transition after an idempotently recorded step."""
    spec = OperationSpec.from_payload(state["spec"])
    results = list(state.get("results", []))
    results.append(dict(state["last_result"]))
    next_index = int(state.get("current_step_index", 0)) + 1
    return {
        "results": results,
        "current_step_index": next_index,
        "operator_decision": {},
        "operator_decision_valid": False,
        "last_result": {},
        "status": "completed" if next_index >= len(spec.steps) else "running",
    }


async def blocked_node(state: OperationState) -> dict[str, Any]:
    del state
    return {"status": "blocked", "error_code": "AUTHORIZATION_INVALID"}


async def rejected_node(state: OperationState) -> dict[str, Any]:
    del state
    return {"status": "rejected", "error_code": "OPERATOR_DECISION_REJECTED"}


async def complete_node(state: OperationState) -> dict[str, Any]:
    del state
    return {"status": "completed", "error_code": ""}


async def _after_authorization(state: OperationState) -> str:
    return "operator_approval" if state.get("authorization_valid") else "blocked"


async def _after_operator_decision(state: OperationState) -> str:
    return "execute_step" if state.get("operator_decision_valid") else "rejected"


async def _after_step(state: OperationState) -> str:
    return "complete" if state.get("status") == "completed" else "revalidate_authorization"


def build_operation_graph() -> StateGraph:
    """Build the versioned SpecOps graph; no planner node can invent new step kinds."""
    graph = StateGraph(OperationState)
    graph.add_node(
        "validate_spec",
        validate_spec_node,
        metadata={"execute_in": "workflow"},
    )
    graph.add_node(
        "revalidate_authorization",
        revalidate_authorization_node,
        metadata={"execute_in": "activity"},
    )
    graph.add_node(
        "operator_approval",
        operator_approval_node,
        metadata={"execute_in": "activity"},
    )
    graph.add_node(
        "validate_operator_decision",
        validate_operator_decision_node,
        metadata={"execute_in": "activity"},
    )
    graph.add_node(
        "execute_step",
        execute_step_node,
        metadata={"execute_in": "activity"},
    )
    graph.add_node(
        "advance_step",
        advance_step_node,
        metadata={"execute_in": "workflow"},
    )
    graph.add_node("blocked", blocked_node, metadata={"execute_in": "workflow"})
    graph.add_node("rejected", rejected_node, metadata={"execute_in": "workflow"})
    graph.add_node("complete", complete_node, metadata={"execute_in": "workflow"})

    graph.add_edge(START, "validate_spec")
    graph.add_edge("validate_spec", "revalidate_authorization")
    graph.add_conditional_edges(
        "revalidate_authorization",
        _after_authorization,
        {"operator_approval": "operator_approval", "blocked": "blocked"},
    )
    graph.add_edge("operator_approval", "validate_operator_decision")
    graph.add_conditional_edges(
        "validate_operator_decision",
        _after_operator_decision,
        {"execute_step": "execute_step", "rejected": "rejected"},
    )
    graph.add_edge("execute_step", "advance_step")
    graph.add_conditional_edges(
        "advance_step",
        _after_step,
        {"revalidate_authorization": "revalidate_authorization", "complete": "complete"},
    )
    graph.add_edge("blocked", END)
    graph.add_edge("rejected", END)
    graph.add_edge("complete", END)
    return graph
