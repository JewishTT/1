"""Unit tests for the fail-closed ARTEX adapter boundary."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from specops_ci.domain import AssessmentKind
from specops_ci.orchestration.contracts import SpecStepKind
from specops_ci.orchestration.runtime_ports import (
    ArtexSpecOpsRuntime,
    _bounded_result,
)


class FakeAuthorization:
    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    async def revalidate(self, **kwargs: Any) -> bool:
        self.calls.append(kwargs)
        return self.result

    async def verify_operator_decision(self, **kwargs: Any) -> bool:
        return True


class FakeGraphs:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def read_asset_graph(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("asset", kwargs))
        return {"snapshot_id": kwargs["snapshot_id"]}

    async def read_exploration_graph(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("exploration", kwargs))
        return {"operation_id": kwargs["operation_id"]}

    async def append_exploration_result(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("append", kwargs))
        return dict(kwargs["result"])


class FakeEvaluator:
    async def evaluate(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "result_id": "result-1",
            "status": "completed",
            "summary": "Reviewed the supplied detection coverage evidence.",
            "evidence_refs": ["observation-1"],
        }


def sample_step() -> dict[str, Any]:
    return {
        "step_id": "coverage",
        "kind": SpecStepKind.DETECTION_COVERAGE_REVIEW.value,
        "target_entity_ids": ["entity-a"],
        "authorization_id": "auth-1",
    }


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_runtime_revalidates_scope_and_records_idempotent_graph_result() -> None:
    authorization = FakeAuthorization()
    graphs = FakeGraphs()
    runtime = ArtexSpecOpsRuntime(
        authorization=authorization,  # type: ignore[arg-type]
        graphs=graphs,  # type: ignore[arg-type]
        evaluator=FakeEvaluator(),  # type: ignore[arg-type]
    )
    result = run(runtime.execute_safe_step(
        tenant_id="tenant-a",
        operation_id="operation-1",
        spec_digest="a" * 64,
        snapshot_id="snapshot-1",
        operation_expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        step=sample_step(),
    ))

    assert result["result_id"] == "result-1"
    assert authorization.calls[0]["assessment_kind"] == AssessmentKind.DETECTION_VALIDATION
    assert [item[0] for item in graphs.calls] == ["asset", "exploration", "append"]
    append = graphs.calls[-1][1]
    assert append["idempotency_key"] == f"operation-1:coverage:{'a' * 64}"
    assert append["result"] == result


def test_revoked_authorization_fails_before_any_graph_or_evaluator_call() -> None:
    authorization = FakeAuthorization(result=False)
    graphs = FakeGraphs()
    runtime = ArtexSpecOpsRuntime(
        authorization=authorization,  # type: ignore[arg-type]
        graphs=graphs,  # type: ignore[arg-type]
        evaluator=FakeEvaluator(),  # type: ignore[arg-type]
    )
    with pytest.raises(PermissionError, match="revoked or no longer matches"):
        run(runtime.execute_safe_step(
            tenant_id="tenant-a",
            operation_id="operation-1",
            spec_digest="a" * 64,
            snapshot_id="snapshot-1",
            operation_expires_at="2026-11-16T12:00:00+00:00",
            step=sample_step(),
        ))
    assert graphs.calls == []


def test_expired_operation_fails_closed_before_authorization_lookup() -> None:
    authorization = FakeAuthorization()
    graphs = FakeGraphs()
    runtime = ArtexSpecOpsRuntime(
        authorization=authorization,  # type: ignore[arg-type]
        graphs=graphs,  # type: ignore[arg-type]
        evaluator=FakeEvaluator(),  # type: ignore[arg-type]
    )
    with pytest.raises(PermissionError):
        run(runtime.execute_safe_step(
            tenant_id="tenant-a",
            operation_id="operation-1",
            spec_digest="a" * 64,
            snapshot_id="snapshot-1",
            operation_expires_at="2020-01-01T00:00:00+00:00",
            step=sample_step(),
        ))
    assert authorization.calls == []
    assert graphs.calls == []


@pytest.mark.parametrize(
    "payload",
    [
        {"result_id": "id", "status": "arbitrary", "summary": "", "evidence_refs": []},
        {"result_id": "id", "status": "completed", "summary": "x" * 2001, "evidence_refs": []},
        {"result_id": "id", "status": "completed", "summary": "", "evidence_refs": ["x" * 257]},
    ],
)
def test_result_payload_is_bounded(payload: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        _bounded_result(payload)
