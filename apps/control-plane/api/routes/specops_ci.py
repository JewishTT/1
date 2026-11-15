"""Authorization-bound SpecOps&CI preparation API.

This surface reads targets from the Intelligence silo and persists explicit approvals.
It prepares a bounded assessment context only; execution adapters are separate and
must not add discovery, crawling or target expansion.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from api.auth import TenantContext, require_admin, require_analyst
from composition import get_platform
from db.schema import SpecOpsEngagementAuthorization as AuthorizationRow
from services.intelligence_access import intelligence_port
from services.intelligence_reader import (
    IntelligenceEvidenceUnavailable,
    IntelligenceReadDenied,
    IntelligenceSnapshotBudgetExceeded,
    IntelligenceSubjectNotFound,
)
from shared.contracts.intelligence_feed import IntelligenceQuery
from specops_ci.domain import (
    AssessmentKind,
    AssessmentScopeError,
    EngagementAuthorization,
)
from specops_ci.service import SPECOPS_CI_PURPOSE, prepare_assessment

router = APIRouter(prefix="/specops-ci", tags=["specops-ci-silo"])
MAX_AUTHORIZATION_WINDOW = timedelta(days=30)
MAX_AUTHORIZED_TARGETS = 100


class AuthorizationCreate(BaseModel):
    subject_ref: str = Field(min_length=1, max_length=128)
    target_entity_ids: list[str] = Field(min_length=1, max_length=MAX_AUTHORIZED_TARGETS)
    assessment_kinds: list[AssessmentKind] = Field(min_length=1)
    approval_ref: str = Field(min_length=3, max_length=256)
    expires_at: datetime
    max_hops: int = Field(default=1, ge=0, le=8)


class AssessmentPrepare(BaseModel):
    authorization_id: str = Field(min_length=1, max_length=64)
    target_entity_ids: list[str] = Field(min_length=1, max_length=MAX_AUTHORIZED_TARGETS)
    assessment_kind: AssessmentKind


def _raise_read_error(exc: Exception) -> None:
    if isinstance(exc, IntelligenceReadDenied):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, IntelligenceSubjectNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, IntelligenceEvidenceUnavailable):
        raise HTTPException(
            status_code=409,
            detail={"code": "EVIDENCE_UNAVAILABLE", "message": str(exc)},
        ) from exc
    if isinstance(exc, IntelligenceSnapshotBudgetExceeded):
        raise HTTPException(
            status_code=413,
            detail={"code": "SNAPSHOT_BUDGET_EXCEEDED", "message": str(exc)},
        ) from exc
    if isinstance(exc, RuntimeError):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    raise exc


def _to_domain(row: AuthorizationRow) -> EngagementAuthorization:
    try:
        kinds = frozenset(AssessmentKind(value) for value in (row.allowed_assessments or []))
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail="stored authorization has an unknown assessment type",
        ) from exc
    return EngagementAuthorization(
        authorization_id=row.authorization_id,
        tenant_id=row.tenant_id,
        source_snapshot_id=row.source_snapshot_id,
        approved_by=row.approved_by,
        approval_ref=row.approval_ref,
        issued_at=row.issued_at,
        expires_at=row.expires_at,
        allowed_entity_ids=frozenset(row.allowed_entity_ids or []),
        allowed_assessments=kinds,
    )


@router.post("/authorizations", status_code=201)
async def create_authorization(
    body: AuthorizationCreate,
    ctx: Annotated[TenantContext, Depends(require_admin)],
) -> dict:
    """An authenticated administrator approves exact targets from a fresh Intelligence view."""
    now = datetime.now(timezone.utc)
    if body.expires_at.tzinfo is None or body.expires_at.utcoffset() is None:
        raise HTTPException(status_code=422, detail="expires_at must include a timezone")
    expiry = body.expires_at.astimezone(timezone.utc)
    if not now < expiry <= now + MAX_AUTHORIZATION_WINDOW:
        raise HTTPException(status_code=422, detail="expires_at must be within the next 30 days")
    if len(set(body.target_entity_ids)) != len(body.target_entity_ids):
        raise HTTPException(status_code=422, detail="target_entity_ids must be unique")
    if len(set(body.assessment_kinds)) != len(body.assessment_kinds):
        raise HTTPException(status_code=422, detail="assessment_kinds must be unique")

    try:
        reader = await intelligence_port(ctx, purpose=SPECOPS_CI_PURPOSE)
        snapshot = await reader.get_snapshot(IntelligenceQuery(
            tenant_id=ctx.tenant_id,
            subject_ref=body.subject_ref,
            purpose=SPECOPS_CI_PURPOSE,
            max_hops=body.max_hops,
        ))
        authorization = EngagementAuthorization(
            authorization_id="sci-" + uuid.uuid4().hex,
            tenant_id=ctx.tenant_id,
            source_snapshot_id=snapshot.snapshot_id,
            approved_by=ctx.user_id,
            approval_ref=body.approval_ref.strip(),
            issued_at=now,
            expires_at=expiry,
            allowed_entity_ids=frozenset(body.target_entity_ids),
            allowed_assessments=frozenset(body.assessment_kinds),
        )
        # Validation refuses any target that is not present in this exact snapshot.
        from specops_ci.domain import build_assessment_context

        build_assessment_context(
            snapshot=snapshot,
            authorization=authorization,
            target_entity_ids=body.target_entity_ids,
            assessment_kind=body.assessment_kinds[0],
            at=now,
        )
    except (
        IntelligenceReadDenied,
        IntelligenceSubjectNotFound,
        IntelligenceEvidenceUnavailable,
        IntelligenceSnapshotBudgetExceeded,
    ) as exc:
        _raise_read_error(exc)
    except AssessmentScopeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    platform = await get_platform(tenant_id=ctx.tenant_id)
    if platform.session_factory is None:
        raise HTTPException(
            status_code=503,
            detail="durable PostgreSQL session factory is unavailable",
        )
    row = AuthorizationRow(
        authorization_id=authorization.authorization_id,
        tenant_id=authorization.tenant_id,
        subject_entity_id=body.subject_ref,
        source_snapshot_id=authorization.source_snapshot_id,
        approved_by=authorization.approved_by,
        approval_ref=authorization.approval_ref,
        issued_at=authorization.issued_at,
        expires_at=authorization.expires_at,
        max_hops=body.max_hops,
        allowed_entity_ids=sorted(authorization.allowed_entity_ids),
        allowed_assessments=sorted(kind.value for kind in authorization.allowed_assessments),
    )
    async with platform.session_factory() as session:
        async with session.begin():
            session.add(row)
    return {
        "authorization_id": row.authorization_id,
        "tenant_id": row.tenant_id,
        "subject_entity_id": row.subject_entity_id,
        "source_snapshot_id": row.source_snapshot_id,
        "approved_by": row.approved_by,
        "approval_ref": row.approval_ref,
        "allowed_entity_ids": row.allowed_entity_ids,
        "allowed_assessments": row.allowed_assessments,
        "issued_at": row.issued_at.isoformat(),
        "expires_at": row.expires_at.isoformat(),
        "revoked": False,
    }


@router.post("/assessments/prepare")
async def prepare_authorized_assessment(
    body: AssessmentPrepare,
    ctx: Annotated[TenantContext, Depends(require_analyst)],
) -> dict:
    """Prepare a context from an existing snapshot and a durable, unrevoked approval."""
    platform = await get_platform(tenant_id=ctx.tenant_id)
    if platform.session_factory is None:
        raise HTTPException(status_code=503, detail="durable PostgreSQL session factory is unavailable")
    async with platform.session_factory() as session:
        result = await session.execute(select(AuthorizationRow).where(
            AuthorizationRow.authorization_id == body.authorization_id,
            AuthorizationRow.tenant_id == ctx.tenant_id,
        ))
        row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="SpecOps&CI authorization not found")
    now = datetime.now(timezone.utc)
    if row.revoked_at is not None:
        raise HTTPException(status_code=409, detail="SpecOps&CI authorization has been revoked")
    if not row.issued_at <= now < row.expires_at:
        raise HTTPException(
            status_code=409,
            detail="SpecOps&CI authorization is not currently valid",
        )

    authorization = _to_domain(row)
    try:
        reader = await intelligence_port(ctx, purpose=SPECOPS_CI_PURPOSE)
        context = await prepare_assessment(
            intelligence=reader,
            query=IntelligenceQuery(
                tenant_id=ctx.tenant_id,
                subject_ref=row.subject_entity_id,
                purpose=SPECOPS_CI_PURPOSE,
                max_hops=row.max_hops,
            ),
            authorization=authorization,
            target_entity_ids=body.target_entity_ids,
            assessment_kind=body.assessment_kind,
            at=now,
        )
    except (IntelligenceReadDenied, IntelligenceSubjectNotFound, IntelligenceEvidenceUnavailable, IntelligenceSnapshotBudgetExceeded) as exc:
        _raise_read_error(exc)
    except AssessmentScopeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "tenant_id": context.tenant_id,
        "source_snapshot_id": context.snapshot_id,
        "authorization_id": context.authorization_id,
        "approval_ref": context.approval_ref,
        "assessment_kind": context.assessment_kind.value,
        "targets": [
            {
                "entity_id": target.entity_id,
                "entity_type": target.entity_type,
                "label": target.label,
                "evidence": [ref.observation_id for ref in target.evidence],
            }
            for target in context.targets
        ],
        "prepared_at": context.prepared_at.isoformat(),
        "execution": "not_started",
    }


@router.post("/authorizations/{authorization_id}/revoke")
async def revoke_authorization(
    authorization_id: str,
    ctx: Annotated[TenantContext, Depends(require_admin)],
) -> dict:
    """Revoke a tenant-owned approval without deleting its audit record."""
    platform = await get_platform(tenant_id=ctx.tenant_id)
    if platform.session_factory is None:
        raise HTTPException(status_code=503, detail="durable PostgreSQL session factory is unavailable")
    now = datetime.now(timezone.utc)
    async with platform.session_factory() as session:
        async with session.begin():
            result = await session.execute(select(AuthorizationRow).where(
                AuthorizationRow.authorization_id == authorization_id,
                AuthorizationRow.tenant_id == ctx.tenant_id,
            ).with_for_update())
            row = result.scalar_one_or_none()
            if row is None:
                raise HTTPException(status_code=404, detail="SpecOps&CI authorization not found")
            if row.revoked_at is None:
                row.revoked_at = now
                row.revoked_by = ctx.user_id
    return {
        "authorization_id": row.authorization_id,
        "revoked": True,
        "revoked_at": row.revoked_at.isoformat(),
        "revoked_by": row.revoked_by,
    }


__all__ = ["router"]
