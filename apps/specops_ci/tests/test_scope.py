from datetime import datetime, timedelta, timezone

import pytest

from shared.contracts.intelligence_feed import (
    EvidenceReference,
    IntelligenceEntity,
    IntelligenceSnapshot,
)
from apps.specops_ci.domain import (
    AssessmentKind,
    AssessmentScopeError,
    EngagementAuthorization,
    build_assessment_context,
)


NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)


def snapshot() -> IntelligenceSnapshot:
    ref = EvidenceReference(
        tenant_id="tenant-a",
        observation_id="obs-host",
        source_ref="source:asset-register",
        object_uri="s3://knowledge/raw/tenant-a/2026/11/obs-host",
        sha256="c" * 64,
        recorded_at=NOW,
    )
    return IntelligenceSnapshot(
        tenant_id="tenant-a",
        snapshot_id="snapshot-1",
        subject_entity_id="host-1",
        created_at=NOW,
        entities=(IntelligenceEntity("host-1", "host", "host-1.example", (ref,)),),
    )


def authorization() -> EngagementAuthorization:
    return EngagementAuthorization(
        authorization_id="roe-1",
        tenant_id="tenant-a",
        source_snapshot_id="snapshot-1",
        approved_by="security-owner",
        approval_ref="change:CHG-123",
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
        allowed_entity_ids=frozenset({"host-1"}),
        allowed_assessments=frozenset({AssessmentKind.DETECTION_VALIDATION}),
    )


def test_assessment_context_uses_only_previously_discovered_entities() -> None:
    context = build_assessment_context(
        snapshot=snapshot(),
        authorization=authorization(),
        target_entity_ids=("host-1",),
        assessment_kind=AssessmentKind.DETECTION_VALIDATION,
        at=NOW,
    )
    assert context.snapshot_id == "snapshot-1"
    assert [target.entity_id for target in context.targets] == ["host-1"]


def test_recon_cannot_expand_the_approved_roster() -> None:
    with pytest.raises(AssessmentScopeError, match="approved entity roster"):
        build_assessment_context(
            snapshot=snapshot(),
            authorization=authorization(),
            target_entity_ids=("host-1", "host-2"),
            assessment_kind=AssessmentKind.DETECTION_VALIDATION,
            at=NOW,
        )


def test_expired_authorization_is_rejected() -> None:
    expired = EngagementAuthorization(
        authorization_id="roe-expired",
        tenant_id="tenant-a",
        source_snapshot_id="snapshot-1",
        approved_by="security-owner",
        approval_ref="change:CHG-OLD",
        issued_at=NOW - timedelta(hours=2),
        expires_at=NOW - timedelta(hours=1),
        allowed_entity_ids=frozenset({"host-1"}),
        allowed_assessments=frozenset({AssessmentKind.DETECTION_VALIDATION}),
    )
    with pytest.raises(AssessmentScopeError, match="not currently valid"):
        build_assessment_context(
            snapshot=snapshot(),
            authorization=expired,
            target_entity_ids=("host-1",),
            assessment_kind=AssessmentKind.DETECTION_VALIDATION,
            at=NOW,
        )
