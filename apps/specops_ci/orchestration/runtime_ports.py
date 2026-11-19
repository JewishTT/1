"""Ports connecting the durable planner to authorization and ARTEX graph stores.

The repository currently has no ARTEX Asset Graph / Exploration Graph implementation.
This module is the explicit adapter boundary; production workers must register a
concrete adapter and fail closed when none is configured.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from specops_ci.domain import AssessmentKind
from specops_ci.orchestration.contracts import (
    SpecStepKind,
    assessment_for_step,
)


class AuthorizationGatePort(Protocol):
    """Authoritative, live authorization and operator identity checks."""

    async def revalidate(
        self,
        *,
        tenant_id: str,
        authorization_id: str,
        snapshot_id: str,
        operation_expires_at: str,
        target_entity_ids: Sequence[str],
        assessment_kind: AssessmentKind,
    ) -> bool: ...

    async def verify_operator_decision(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        spec_digest: str,
        step_id: str,
        decision: Mapping[str, Any],
    ) -> bool: ...


class ArtexGraphPort(Protocol):
    """Narrow adapter over ARTEX Asset Graph and Exploration Graph stores."""

    async def read_asset_graph(
        self,
        *,
        tenant_id: str,
        snapshot_id: str,
        target_entity_ids: Sequence[str],
    ) -> Mapping[str, Any]: ...

    async def read_exploration_graph(
        self,
        *,
        tenant_id: str,
        operation_id: str,
    ) -> Mapping[str, Any]: ...

    async def append_exploration_result(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        step_id: str,
        idempotency_key: str,
        result: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


class ReadOnlyAssessmentEngine(Protocol):
    """Evaluator for read-only reviews and synthetic lab validation only."""

    async def evaluate(
        self,
        *,
        kind: SpecStepKind,
        target_entity_ids: Sequence[str],
        asset_graph: Mapping[str, Any],
        exploration_graph: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


class SpecOpsRuntimePorts(Protocol):
    """Activity-side dependencies registered by the deployment's Worker factory."""

    async def revalidate_authorization(
        self,
        *,
        tenant_id: str,
        authorization_id: str,
        snapshot_id: str,
        operation_expires_at: str,
        target_entity_ids: Sequence[str],
        step_kind: SpecStepKind,
    ) -> bool: ...

    async def validate_operator_decision(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        spec_digest: str,
        step_id: str,
        decision: Mapping[str, Any],
    ) -> bool: ...

    async def execute_safe_step(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        spec_digest: str,
        snapshot_id: str,
        operation_expires_at: str,
        step: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


class ArtexSpecOpsRuntime:
    """Compose live authorization checks with bounded ARTEX graph read/write ports."""

    def __init__(
        self,
        *,
        authorization: AuthorizationGatePort,
        graphs: ArtexGraphPort,
        evaluator: ReadOnlyAssessmentEngine,
    ) -> None:
        self._authorization = authorization
        self._graphs = graphs
        self._evaluator = evaluator

    async def revalidate_authorization(
        self,
        *,
        tenant_id: str,
        authorization_id: str,
        snapshot_id: str,
        operation_expires_at: str,
        target_entity_ids: Sequence[str],
        step_kind: SpecStepKind,
    ) -> bool:
        try:
            expires_at = datetime.fromisoformat(operation_expires_at)
        except ValueError:
            return False
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            return False
        if not datetime.now(UTC) < expires_at:
            return False
        return await self._authorization.revalidate(
            tenant_id=tenant_id,
            authorization_id=authorization_id,
            snapshot_id=snapshot_id,
            operation_expires_at=operation_expires_at,
            target_entity_ids=target_entity_ids,
            assessment_kind=assessment_for_step(step_kind),
        )

    async def validate_operator_decision(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        spec_digest: str,
        step_id: str,
        decision: Mapping[str, Any],
    ) -> bool:
        return await self._authorization.verify_operator_decision(
            tenant_id=tenant_id,
            operation_id=operation_id,
            spec_digest=spec_digest,
            step_id=step_id,
            decision=decision,
        )

    async def execute_safe_step(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        spec_digest: str,
        snapshot_id: str,
        operation_expires_at: str,
        step: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        kind = SpecStepKind(str(step["kind"]))
        targets = tuple(str(value) for value in step["target_entity_ids"])
        authorization_id = str(step["authorization_id"])
        if not await self.revalidate_authorization(
            tenant_id=tenant_id,
            authorization_id=authorization_id,
            snapshot_id=snapshot_id,
            operation_expires_at=operation_expires_at,
            target_entity_ids=targets,
            step_kind=kind,
        ):
            raise PermissionError("authorization was revoked or no longer matches the step")

        asset_graph = await self._graphs.read_asset_graph(
            tenant_id=tenant_id,
            snapshot_id=snapshot_id,
            target_entity_ids=targets,
        )
        exploration_graph = await self._graphs.read_exploration_graph(
            tenant_id=tenant_id,
            operation_id=operation_id,
        )
        raw_result = await self._evaluator.evaluate(
            kind=kind,
            target_entity_ids=targets,
            asset_graph=asset_graph,
            exploration_graph=exploration_graph,
        )
        result = _bounded_result(raw_result)
        idempotency_key = f"{operation_id}:{step['step_id']}:{spec_digest}"
        canonical_result = await self._graphs.append_exploration_result(
            tenant_id=tenant_id,
            operation_id=operation_id,
            step_id=str(step["step_id"]),
            idempotency_key=idempotency_key,
            result=result,
        )
        # The adapter must return the stored value for an existing idempotency key.
        # Returning the freshly evaluated value would make Temporal replay disagree
        # with the authoritative Exploration Graph after an ambiguous Activity retry.
        return _bounded_result(canonical_result)


def _bounded_result(value: Mapping[str, Any]) -> dict[str, Any]:
    """Allow only compact findings metadata into Workflow history and graph writes."""
    status = str(value.get("status", ""))
    if status not in {"completed", "no_findings", "needs_review"}:
        raise ValueError("assessment adapter returned an unsupported result status")
    result_id = value.get("result_id")
    summary = value.get("summary", "")
    evidence_refs = value.get("evidence_refs", ())
    if not isinstance(result_id, str) or not result_id or len(result_id) > 128:
        raise ValueError("assessment result must include a bounded result_id")
    if not isinstance(summary, str) or len(summary) > 2000:
        raise ValueError("assessment summary must be a string of at most 2000 characters")
    if not isinstance(evidence_refs, (list, tuple)) or len(evidence_refs) > 128:
        raise ValueError("assessment evidence_refs must be a bounded list")
    refs = []
    for ref in evidence_refs:
        if not isinstance(ref, str) or not ref or len(ref) > 256:
            raise ValueError("assessment evidence references must be short opaque identifiers")
        refs.append(ref)
    return {
        "result_id": result_id,
        "status": status,
        "summary": summary,
        "evidence_refs": refs,
    }


_RUNTIME_PORTS: SpecOpsRuntimePorts | None = None


def configure_runtime_ports(ports: SpecOpsRuntimePorts) -> None:
    """Install deployment-specific ports before the Temporal Worker starts."""
    global _RUNTIME_PORTS
    required = (
        "revalidate_authorization",
        "validate_operator_decision",
        "execute_safe_step",
    )
    if any(not callable(getattr(ports, name, None)) for name in required):
        raise TypeError("runtime factory returned an incomplete SpecOpsRuntimePorts adapter")
    _RUNTIME_PORTS = ports


def get_runtime_ports() -> SpecOpsRuntimePorts:
    """Return configured ports or fail closed before any assessment work."""
    if _RUNTIME_PORTS is None:
        raise RuntimeError("SpecOps&CI runtime ports are not configured")
    return _RUNTIME_PORTS
