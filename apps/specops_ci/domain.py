"""Policy-bound SpecOps/Counterintelligence context derived from Intelligence.

This domain layer does not discover or enumerate targets. Every assessment target
must already exist in the supplied tenant-scoped Intelligence snapshot and in a
time-bounded, explicitly approved engagement scope.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable

from shared.contracts.intelligence_feed import (
    IntelligenceEntity,
    IntelligenceSnapshot,
)


class AssessmentScopeError(PermissionError):
    """An assessment request exceeds its approved or evidenced scope."""


class AssessmentKind(str, Enum):
    ASSET_INVENTORY = "asset_inventory"
    CONFIGURATION_REVIEW = "configuration_review"
    VULNERABILITY_VALIDATION = "vulnerability_validation"
    DETECTION_VALIDATION = "detection_validation"
    PURPLE_TEAM_EXERCISE = "purple_team_exercise"


@dataclass(frozen=True, slots=True)
class EngagementAuthorization:
    authorization_id: str
    tenant_id: str
    source_snapshot_id: str
    approved_by: str
    approval_ref: str
    issued_at: datetime
    expires_at: datetime
    allowed_entity_ids: frozenset[str]
    allowed_assessments: frozenset[AssessmentKind]

    def __post_init__(self) -> None:
        for value, field in (
            (self.authorization_id, "authorization_id"),
            (self.tenant_id, "tenant_id"),
            (self.source_snapshot_id, "source_snapshot_id"),
            (self.approved_by, "approved_by"),
            (self.approval_ref, "approval_ref"),
        ):
            if not value or not value.strip():
                raise AssessmentScopeError(f"{field} must be non-empty")
        for value, field in ((self.issued_at, "issued_at"), (self.expires_at, "expires_at")):
            if value.tzinfo is None or value.utcoffset() is None:
                raise AssessmentScopeError(f"{field} must be timezone-aware")
        if self.expires_at <= self.issued_at:
            raise AssessmentScopeError("authorization expires_at must be after issued_at")
        if not self.allowed_entity_ids:
            raise AssessmentScopeError("authorization must enumerate approved entity ids")
        if not self.allowed_assessments:
            raise AssessmentScopeError("authorization must enumerate permitted assessment kinds")


@dataclass(frozen=True, slots=True)
class AssessmentContext:
    tenant_id: str
    snapshot_id: str
    authorization_id: str
    approval_ref: str
    assessment_kind: AssessmentKind
    targets: tuple[IntelligenceEntity, ...]
    prepared_at: datetime


def build_assessment_context(
    *,
    snapshot: IntelligenceSnapshot,
    authorization: EngagementAuthorization,
    target_entity_ids: Iterable[str],
    assessment_kind: AssessmentKind,
    at: datetime | None = None,
) -> AssessmentContext:
    """Bind an assessment to existing intel and exact, currently approved targets."""
    now = at or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise AssessmentScopeError("assessment time must be timezone-aware")
    if snapshot.tenant_id != authorization.tenant_id:
        raise AssessmentScopeError("authorization and Intelligence snapshot tenants differ")
    if snapshot.snapshot_id != authorization.source_snapshot_id:
        raise AssessmentScopeError("authorization is not bound to this Intelligence snapshot")
    if not authorization.issued_at <= now < authorization.expires_at:
        raise AssessmentScopeError("engagement authorization is not currently valid")
    if assessment_kind not in authorization.allowed_assessments:
        raise AssessmentScopeError("assessment kind is outside the approved engagement")
    supplied_targets = tuple(target_entity_ids)
    requested = tuple(dict.fromkeys(supplied_targets))
    if not requested:
        raise AssessmentScopeError("at least one explicit target entity is required")
    if len(requested) != len(supplied_targets):
        raise AssessmentScopeError("duplicate target entity ids are not accepted")
    if not set(requested).issubset(authorization.allowed_entity_ids):
        raise AssessmentScopeError("requested targets exceed the approved entity roster")
    by_id = {entity.entity_id: entity for entity in snapshot.entities}
    if not set(requested).issubset(by_id):
        raise AssessmentScopeError("requested targets are absent from the Intelligence snapshot")
    return AssessmentContext(
        tenant_id=snapshot.tenant_id,
        snapshot_id=snapshot.snapshot_id,
        authorization_id=authorization.authorization_id,
        approval_ref=authorization.approval_ref,
        assessment_kind=assessment_kind,
        targets=tuple(by_id[entity_id] for entity_id in requested),
        prepared_at=now,
    )
