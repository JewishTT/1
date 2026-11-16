"""Immutable operation specifications and scope validation.

The spec is intentionally declarative: it contains no commands, URLs, tool names,
credentials, payloads, or executable code. Every step belongs to a small, reviewed
set of read-only or synthetic validation activities.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from specops_ci.domain import (
    AssessmentKind,
    AssessmentScopeError,
    EngagementAuthorization,
)


SPEC_SCHEMA_VERSION = "1"
MAX_OPERATION_TARGETS = 100
MAX_OPERATION_STEPS = 32
_STEP_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


class SpecStepKind(StrEnum):
    EVIDENCE_REVIEW = "evidence_review"
    CONFIGURATION_REVIEW = "configuration_review"
    DETECTION_COVERAGE_REVIEW = "detection_coverage_review"
    LAB_SIMULATION = "lab_simulation"
    REPORT_GENERATION = "report_generation"


_ASSESSMENT_FOR_STEP: dict[SpecStepKind, AssessmentKind] = {
    SpecStepKind.EVIDENCE_REVIEW: AssessmentKind.ASSET_INVENTORY,
    SpecStepKind.CONFIGURATION_REVIEW: AssessmentKind.CONFIGURATION_REVIEW,
    SpecStepKind.DETECTION_COVERAGE_REVIEW: AssessmentKind.DETECTION_VALIDATION,
    SpecStepKind.LAB_SIMULATION: AssessmentKind.DETECTION_VALIDATION,
    SpecStepKind.REPORT_GENERATION: AssessmentKind.ASSET_INVENTORY,
}


def assessment_for_step(kind: SpecStepKind) -> AssessmentKind:
    """Return the narrow authorization capability required by a step."""
    return _ASSESSMENT_FOR_STEP[kind]


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AssessmentScopeError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class SpecStep:
    step_id: str
    kind: SpecStepKind
    target_entity_ids: tuple[str, ...]
    depends_on: tuple[str, ...] = ()
    requires_operator_approval: bool = True

    def validate_structure(self) -> None:
        if not _STEP_ID.fullmatch(self.step_id):
            raise AssessmentScopeError("step_id must be a short lowercase identifier")
        if not self.target_entity_ids:
            raise AssessmentScopeError(f"step {self.step_id} must name explicit targets")
        if len(set(self.target_entity_ids)) != len(self.target_entity_ids):
            raise AssessmentScopeError(f"step {self.step_id} has duplicate targets")
        if any(not value or not value.strip() for value in self.target_entity_ids):
            raise AssessmentScopeError(f"step {self.step_id} has an empty target id")
        if not self.requires_operator_approval:
            raise AssessmentScopeError("every operation step requires explicit operator approval")
        if len(set(self.depends_on)) != len(self.depends_on):
            raise AssessmentScopeError(f"step {self.step_id} has duplicate dependencies")


@dataclass(frozen=True, slots=True)
class OperationSpec:
    operation_id: str
    tenant_id: str
    authorization_id: str
    snapshot_id: str
    title: str
    expires_at: datetime
    target_entity_ids: tuple[str, ...]
    steps: tuple[SpecStep, ...]
    schema_version: str = SPEC_SCHEMA_VERSION

    def validate_structure(self) -> None:
        for value, field_name in (
            (self.operation_id, "operation_id"),
            (self.tenant_id, "tenant_id"),
            (self.authorization_id, "authorization_id"),
            (self.snapshot_id, "snapshot_id"),
            (self.title, "title"),
        ):
            if not value or not value.strip():
                raise AssessmentScopeError(f"{field_name} must be non-empty")
        if len(self.title) > 200:
            raise AssessmentScopeError("title must be at most 200 characters")
        if self.schema_version != SPEC_SCHEMA_VERSION:
            raise AssessmentScopeError("unsupported operation specification version")
        _require_aware(self.expires_at, "expires_at")
        if not self.target_entity_ids or len(self.target_entity_ids) > MAX_OPERATION_TARGETS:
            raise AssessmentScopeError("operation must contain between 1 and 100 targets")
        if len(set(self.target_entity_ids)) != len(self.target_entity_ids):
            raise AssessmentScopeError("operation target ids must be unique")
        if any(not value or not value.strip() for value in self.target_entity_ids):
            raise AssessmentScopeError("operation target ids must be non-empty")
        if not self.steps or len(self.steps) > MAX_OPERATION_STEPS:
            raise AssessmentScopeError("operation must contain between 1 and 32 steps")

        operation_targets = set(self.target_entity_ids)
        previous_steps: set[str] = set()
        seen_steps: set[str] = set()
        for step in self.steps:
            step.validate_structure()
            if step.step_id in seen_steps:
                raise AssessmentScopeError("operation step ids must be unique")
            if not set(step.target_entity_ids).issubset(operation_targets):
                raise AssessmentScopeError(
                    f"step {step.step_id} exceeds the operation target roster"
                )
            # Dependencies must refer only to earlier steps. This is a topological
            # ordering invariant that makes cycles and forward references impossible.
            if not set(step.depends_on).issubset(previous_steps):
                raise AssessmentScopeError(
                    f"step {step.step_id} has an unknown, cyclic, or forward dependency"
                )
            previous_steps.add(step.step_id)
            seen_steps.add(step.step_id)

    def to_payload(self) -> dict[str, Any]:
        """Return a JSON-safe representation suitable for Temporal history."""
        return {
            "schema_version": self.schema_version,
            "operation_id": self.operation_id,
            "tenant_id": self.tenant_id,
            "authorization_id": self.authorization_id,
            "snapshot_id": self.snapshot_id,
            "title": self.title,
            "expires_at": self.expires_at.isoformat(),
            "target_entity_ids": list(self.target_entity_ids),
            "steps": [
                {
                    "step_id": step.step_id,
                    "kind": step.kind.value,
                    "target_entity_ids": list(step.target_entity_ids),
                    "depends_on": list(step.depends_on),
                    "requires_operator_approval": step.requires_operator_approval,
                }
                for step in self.steps
            ],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> OperationSpec:
        """Parse an untrusted JSON-compatible specification and validate its shape."""
        steps = tuple(
            SpecStep(
                step_id=str(item["step_id"]),
                kind=SpecStepKind(item["kind"]),
                target_entity_ids=tuple(str(value) for value in item["target_entity_ids"]),
                depends_on=tuple(str(value) for value in item.get("depends_on", ())),
                requires_operator_approval=bool(item.get("requires_operator_approval", True)),
            )
            for item in payload["steps"]
        )
        spec = cls(
            operation_id=str(payload["operation_id"]),
            tenant_id=str(payload["tenant_id"]),
            authorization_id=str(payload["authorization_id"]),
            snapshot_id=str(payload["snapshot_id"]),
            title=str(payload["title"]),
            expires_at=datetime.fromisoformat(str(payload["expires_at"])),
            target_entity_ids=tuple(str(value) for value in payload["target_entity_ids"]),
            steps=steps,
            schema_version=str(payload.get("schema_version", "")),
        )
        spec.validate_structure()
        return spec

    def digest(self) -> str:
        """Compute a stable SHA-256 digest over the full immutable specification."""
        encoded = json.dumps(
            self.to_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def validate_operation_against_authorization(
    spec: OperationSpec,
    authorization: EngagementAuthorization,
    *,
    now: datetime,
) -> None:
    """Bind the complete spec to the current approval, snapshot, tenant and roster."""
    spec.validate_structure()
    _require_aware(now, "now")
    if spec.tenant_id != authorization.tenant_id:
        raise AssessmentScopeError("operation and authorization tenants differ")
    if spec.authorization_id != authorization.authorization_id:
        raise AssessmentScopeError("operation references a different authorization")
    if spec.snapshot_id != authorization.source_snapshot_id:
        raise AssessmentScopeError("operation is not bound to the approved Intelligence snapshot")
    if not authorization.issued_at <= now < authorization.expires_at:
        raise AssessmentScopeError("engagement authorization is not currently valid")
    if not now < spec.expires_at <= authorization.expires_at:
        raise AssessmentScopeError("operation expiry must be within the active authorization")
    if not set(spec.target_entity_ids).issubset(authorization.allowed_entity_ids):
        raise AssessmentScopeError("operation targets exceed the approved entity roster")
    for step in spec.steps:
        required = assessment_for_step(step.kind)
        if required not in authorization.allowed_assessments:
            raise AssessmentScopeError(
                f"step {step.step_id} requires unapproved assessment kind {required.value}"
            )
        if not set(step.target_entity_ids).issubset(authorization.allowed_entity_ids):
            raise AssessmentScopeError(
                f"step {step.step_id} exceeds the approved entity roster"
            )
