"""Contract tests for durable, approval-gated SpecOps operation specifications."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from specops_ci.domain import (
    AssessmentKind,
    AssessmentScopeError,
    EngagementAuthorization,
)
from specops_ci.orchestration.contracts import (
    OperationSpec,
    SpecStep,
    SpecStepKind,
    validate_operation_against_authorization,
)


NOW = datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc)


def make_authorization(
    *,
    entities: frozenset[str] = frozenset({"entity-a", "entity-b"}),
    assessments: frozenset[AssessmentKind] = frozenset({
        AssessmentKind.ASSET_INVENTORY,
        AssessmentKind.CONFIGURATION_REVIEW,
        AssessmentKind.DETECTION_VALIDATION,
    }),
) -> EngagementAuthorization:
    return EngagementAuthorization(
        authorization_id="auth-123",
        tenant_id="tenant-a",
        source_snapshot_id="snapshot-123",
        approved_by="operator-1",
        approval_ref="change:CHG-123",
        issued_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(hours=2),
        allowed_entity_ids=entities,
        allowed_assessments=assessments,
    )


def make_spec(
    *,
    targets: tuple[str, ...] = ("entity-a",),
    expires_at: datetime | None = None,
    steps: tuple[SpecStep, ...] | None = None,
) -> OperationSpec:
    return OperationSpec(
        operation_id="op-123",
        tenant_id="tenant-a",
        authorization_id="auth-123",
        snapshot_id="snapshot-123",
        title="Detection coverage review",
        expires_at=expires_at or (NOW + timedelta(hours=1)),
        target_entity_ids=targets,
        steps=steps or (
            SpecStep(
                step_id="review",
                kind=SpecStepKind.DETECTION_COVERAGE_REVIEW,
                target_entity_ids=("entity-a",),
            ),
        ),
    )


def test_operation_spec_round_trips_and_has_stable_digest() -> None:
    spec = make_spec()
    restored = OperationSpec.from_payload(spec.to_payload())
    assert restored == spec
    assert restored.digest() == spec.digest()
    assert len(spec.digest()) == 64


def test_operation_must_be_bound_to_the_same_authorization_and_snapshot() -> None:
    spec = make_spec()
    authorization = make_authorization()
    validate_operation_against_authorization(spec, authorization, now=NOW)

    with pytest.raises(AssessmentScopeError, match="different authorization"):
        validate_operation_against_authorization(
            OperationSpec(
                **{
                    **spec.__dict__,
                    "authorization_id": "other-auth",
                }
            ),
            authorization,
            now=NOW,
        )


def test_operation_cannot_expand_the_approved_target_roster() -> None:
    spec = make_spec(
        targets=("entity-a", "entity-c"),
        steps=(
            SpecStep(
                step_id="review",
                kind=SpecStepKind.EVIDENCE_REVIEW,
                target_entity_ids=("entity-a", "entity-c"),
            ),
        ),
    )
    with pytest.raises(AssessmentScopeError, match="approved entity roster"):
        validate_operation_against_authorization(spec, make_authorization(), now=NOW)


def test_step_kind_must_be_explicitly_allowed() -> None:
    spec = make_spec(
        steps=(
            SpecStep(
                step_id="config",
                kind=SpecStepKind.CONFIGURATION_REVIEW,
                target_entity_ids=("entity-a",),
            ),
        ),
    )
    authorization = make_authorization(
        assessments=frozenset({AssessmentKind.ASSET_INVENTORY})
    )
    with pytest.raises(AssessmentScopeError, match="unapproved assessment kind"):
        validate_operation_against_authorization(spec, authorization, now=NOW)


def test_operation_expiry_must_fit_inside_authorization_window() -> None:
    spec = make_spec(expires_at=NOW + timedelta(days=3))
    with pytest.raises(AssessmentScopeError, match="within the active authorization"):
        validate_operation_against_authorization(spec, make_authorization(), now=NOW)


@pytest.mark.parametrize(
    "steps, message",
    [
        (
            (
                SpecStep(
                    step_id="second",
                    kind=SpecStepKind.EVIDENCE_REVIEW,
                    target_entity_ids=("entity-a",),
                    depends_on=("first",),
                ),
                SpecStep(
                    step_id="first",
                    kind=SpecStepKind.REPORT_GENERATION,
                    target_entity_ids=("entity-a",),
                ),
            ),
            "unknown, cyclic, or forward dependency",
        ),
        (
            (
                SpecStep(
                    step_id="first",
                    kind=SpecStepKind.EVIDENCE_REVIEW,
                    target_entity_ids=("entity-a",),
                    requires_operator_approval=False,
                ),
            ),
            "every operation step requires explicit operator approval",
        ),
    ],
)
def test_invalid_dependencies_and_missing_approval_are_rejected(
    steps: tuple[SpecStep, ...],
    message: str,
) -> None:
    with pytest.raises(AssessmentScopeError, match=message):
        make_spec(steps=steps).validate_structure()


def test_payload_does_not_accept_string_false_as_approval() -> None:
    payload = make_spec().to_payload()
    payload["steps"][0]["requires_operator_approval"] = "false"
    with pytest.raises(AssessmentScopeError, match="must be a boolean"):
        OperationSpec.from_payload(payload)


def test_unknown_step_kind_is_rejected() -> None:
    payload = make_spec().to_payload()
    payload["steps"][0]["kind"] = "arbitrary_shell_command"
    with pytest.raises(ValueError):
        OperationSpec.from_payload(payload)
