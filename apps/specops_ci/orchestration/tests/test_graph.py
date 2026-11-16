"""LangGraph definition and Temporal HITL contract tests."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from specops_ci.domain import AssessmentScopeError
from specops_ci.orchestration.contracts import OperationSpec, SpecStep, SpecStepKind
from specops_ci.orchestration.graph import (
    GRAPH_NAME,
    _after_operator_decision,
    build_operation_graph,
    validate_operator_decision_node,
    validate_spec_node,
)
from specops_ci.orchestration.workflow import SpecOpsOperationWorkflow


def sample_spec() -> OperationSpec:
    return OperationSpec(
        operation_id="operation-graph-test",
        tenant_id="tenant-a",
        authorization_id="authorization-a",
        snapshot_id="snapshot-a",
        title="Review detection coverage",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        target_entity_ids=("entity-a",),
        steps=(
            SpecStep(
                step_id="coverage",
                kind=SpecStepKind.DETECTION_COVERAGE_REVIEW,
                target_entity_ids=("entity-a",),
            ),
        ),
    )


def test_langgraph_builds_the_declared_operation_state_machine() -> None:
    compiled = build_operation_graph().compile()
    assert compiled is not None
    assert GRAPH_NAME == "specops-ci-operation-v1"


def test_spec_validation_node_accepts_only_the_matching_digest() -> None:
    spec = sample_spec()
    result = asyncio.run(validate_spec_node({
        "operation_id": spec.operation_id,
        "spec": spec.to_payload(),
        "spec_digest": spec.digest(),
    }))
    assert result["status"] == "validated"
    assert result["current_step_index"] == 0

    with pytest.raises(ValueError, match="digest mismatch"):
        asyncio.run(validate_spec_node({
            "operation_id": spec.operation_id,
            "spec": spec.to_payload(),
            "spec_digest": "0" * 64,
        }))


def test_operator_rejection_is_verified_but_never_reaches_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DecisionGate:
        async def validate_operator_decision(self, **kwargs: object) -> bool:
            return True

    monkeypatch.setattr(
        "specops_ci.orchestration.graph.get_runtime_ports",
        lambda: DecisionGate(),
    )
    spec = sample_spec()
    state = {
        "operation_id": spec.operation_id,
        "spec": spec.to_payload(),
        "spec_digest": spec.digest(),
        "current_step_index": 0,
        "operator_decision": {
            "operation_id": spec.operation_id,
            "step_id": "coverage",
            "spec_digest": spec.digest(),
            "approved": False,
        },
    }
    result = asyncio.run(validate_operator_decision_node(state))
    assert result["operator_decision_valid"] is True
    assert result["operator_decision_approved"] is False
    assert asyncio.run(_after_operator_decision(result)) == "rejected"


def test_temporal_workflow_exposes_query_and_signal_for_human_review() -> None:
    workflow = SpecOpsOperationWorkflow()
    assert callable(workflow.provide_operator_decision)
    assert callable(workflow.get_pending_approval)
    assert workflow.get_pending_approval() is None
