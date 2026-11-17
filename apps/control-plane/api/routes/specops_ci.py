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
from db.schema import (
    SpecOpsEngagementAuthorization as AuthorizationRow,
    SpecOpsOperationDecision as DecisionRow,
)
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
from specops_ci.orchestration.client import start_operation
from specops_ci.orchestration.contracts import (
    OperationSpec,
    SpecStep,
    SpecStepKind,
    validate_operation_against_authorization,
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


class OperationStepCreate(BaseModel):
    step_id: str = Field(min_length=1, max_length=64)
    kind: SpecStepKind
    target_entity_ids: list[str] = Field(min_length=1, max_length=100)
    depends_on: list[str] = Field(default_factory=list, max_length=32)
    requires_operator_approval: bool = True


class OperationCreate(BaseModel):
    operation_id: str = Field(pattern=r"^sci-op-[a-f0-9]{32}$")
    authorization_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    target_entity_ids: list[str] = Field(min_length=1, max_length=100)
    expires_at: datetime
    steps: list[OperationStepCreate] = Field(min_length=1, max_length=32)


class OperatorDecisionCreate(BaseModel):
    approved: bool
    approval_ref: str = Field(min_length=3, max_length=256)


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
        raise HTTPException(
            status_code=503,
            detail="durable PostgreSQL session factory is unavailable",
        )
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
    except (
        IntelligenceReadDenied,
        IntelligenceSubjectNotFound,
        IntelligenceEvidenceUnavailable,
        IntelligenceSnapshotBudgetExceeded,
    ) as exc:
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


@router.post("/operations", status_code=202)
async def create_operation(
    body: OperationCreate,
    ctx: Annotated[TenantContext, Depends(require_analyst)],
) -> dict:
    """Submit a declarative, immutable operation bound to an existing authorization."""
    platform = await get_platform(tenant_id=ctx.tenant_id)
    if platform.session_factory is None:
        raise HTTPException(
            status_code=503,
            detail="durable PostgreSQL session factory is unavailable",
        )

    async with platform.session_factory() as session:
        result = await session.execute(select(AuthorizationRow).where(
            AuthorizationRow.authorization_id == body.authorization_id,
            AuthorizationRow.tenant_id == ctx.tenant_id,
        ))
        row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="SpecOps&CI authorization not found")
    if row.revoked_at is not None:
        raise HTTPException(status_code=409, detail="SpecOps&CI authorization has been revoked")

    authorization = _to_domain(row)
    now = datetime.now(timezone.utc)
    spec = OperationSpec(
        operation_id=body.operation_id,
        tenant_id=ctx.tenant_id,
        authorization_id=authorization.authorization_id,
        snapshot_id=authorization.source_snapshot_id,
        title=body.title,
        expires_at=body.expires_at,
        target_entity_ids=tuple(body.target_entity_ids),
        steps=tuple(
            SpecStep(
                step_id=step.step_id,
                kind=step.kind,
                target_entity_ids=tuple(step.target_entity_ids),
                depends_on=tuple(step.depends_on),
                requires_operator_approval=step.requires_operator_approval,
            )
            for step in body.steps
        ),
    )
    try:
        validate_operation_against_authorization(spec, authorization, now=now)
    except AssessmentScopeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        from workflow.client import connect_temporal

        temporal = await connect_temporal()
        try:
            existing = temporal.get_workflow_handle(spec.operation_id)
            await existing.describe()
        except Exception:
            existing = None

        if existing is not None:
            existing_summary = await existing.query("get_operation_summary")
            if (
                not isinstance(existing_summary, dict)
                or existing_summary.get("tenant_id") != ctx.tenant_id
                or existing_summary.get("authorization_id") != spec.authorization_id
                or existing_summary.get("snapshot_id") != spec.snapshot_id
                or existing_summary.get("spec_digest") != spec.digest()
            ):
                raise HTTPException(
                    status_code=409,
                    detail="operation_id is already bound to a different immutable spec",
                )
            return {
                **existing_summary,
                "reused": True,
                "workflow_type": "specops-ci-operation-v1",
                "task_queue": "specops-ci-operations",
            }

        await start_operation(temporal, spec, authorization, now=now)
    except AssessmentScopeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        # A concurrent submitter may win after our initial describe. Adopt it only
        # when the existing workflow proves it has the identical immutable digest.
        try:
            from workflow.client import connect_temporal

            temporal = await connect_temporal()
            existing = temporal.get_workflow_handle(spec.operation_id)
            existing_summary = await existing.query("get_operation_summary")
            if (
                isinstance(existing_summary, dict)
                and existing_summary.get("tenant_id") == ctx.tenant_id
                and existing_summary.get("authorization_id") == spec.authorization_id
                and existing_summary.get("snapshot_id") == spec.snapshot_id
                and existing_summary.get("spec_digest") == spec.digest()
            ):
                return {
                    **existing_summary,
                    "reused": True,
                    "workflow_type": "specops-ci-operation-v1",
                    "task_queue": "specops-ci-operations",
                }
        except Exception:
            pass
        raise HTTPException(
            status_code=503,
            detail={
                "code": "SPECOPS_TEMPORAL_UNAVAILABLE",
                "message": f"operation was not confirmed as started ({type(exc).__name__})",
            },
        ) from exc

    return {
        "operation_id": spec.operation_id,
        "tenant_id": spec.tenant_id,
        "authorization_id": spec.authorization_id,
        "snapshot_id": spec.snapshot_id,
        "spec_digest": spec.digest(),
        "status": "submitted",
        "workflow_type": "specops-ci-operation-v1",
        "task_queue": "specops-ci-operations",
        "step_count": len(spec.steps),
        "target_count": len(spec.target_entity_ids),
    }


async def _get_operation_handles(operation_id: str, tenant_id: str):
    """Resolve and tenant-check the Temporal workflow before returning its handle."""
    try:
        from workflow.client import connect_temporal

        temporal = await connect_temporal()
        handle = temporal.get_workflow_handle(operation_id)
        summary = await handle.query("get_operation_summary")
    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail="SpecOps&CI operation not found or Temporal is unavailable",
        ) from exc
    if not isinstance(summary, dict) or summary.get("tenant_id") != tenant_id:
        raise HTTPException(status_code=404, detail="SpecOps&CI operation not found")
    return handle, summary


@router.get("/operations/{operation_id}/approval")
async def get_operation_approval(
    operation_id: str,
    ctx: Annotated[TenantContext, Depends(require_analyst)],
) -> dict:
    """Read the pending approval challenge for an operation in the current tenant."""
    handle, summary = await _get_operation_handles(operation_id, ctx.tenant_id)
    try:
        pending = await handle.query("get_pending_approval")
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Temporal operation query failed",
        ) from exc
    if pending is not None and (
        not isinstance(pending, dict)
        or pending.get("tenant_id") != ctx.tenant_id
        or pending.get("operation_id") != operation_id
    ):
        raise HTTPException(status_code=404, detail="SpecOps&CI operation not found")
    return {
        "operation_id": operation_id,
        "status": summary.get("status", "unknown"),
        "pending_approval": pending,
    }


@router.post("/operations/{operation_id}/steps/{step_id}/decision")
async def submit_operator_decision(
    operation_id: str,
    step_id: str,
    body: OperatorDecisionCreate,
    ctx: Annotated[TenantContext, Depends(require_admin)],
) -> dict:
    """Persist an admin decision first, then signal the waiting Temporal workflow."""
    platform = await get_platform(tenant_id=ctx.tenant_id)
    if platform.session_factory is None:
        raise HTTPException(
            status_code=503,
            detail="durable PostgreSQL session factory is unavailable",
        )
    handle, summary = await _get_operation_handles(operation_id, ctx.tenant_id)
    try:
        pending = await handle.query("get_pending_approval")
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Temporal approval query failed") from exc
    if not isinstance(pending, dict):
        raise HTTPException(status_code=409, detail="operation has no pending operator approval")
    if (
        pending.get("operation_id") != operation_id
        or pending.get("tenant_id") != ctx.tenant_id
        or pending.get("step_id") != step_id
        or pending.get("authorization_id") != summary.get("authorization_id")
        or pending.get("snapshot_id") != summary.get("snapshot_id")
        or pending.get("spec_digest") != summary.get("spec_digest")
    ):
        raise HTTPException(status_code=409, detail="approval challenge does not match operation step")

    now = datetime.now(timezone.utc)
    approval_ref = body.approval_ref.strip()
    if not approval_ref:
        raise HTTPException(status_code=422, detail="approval_ref must not be blank")
    async with platform.session_factory() as session:
        async with session.begin():
            auth_result = await session.execute(select(AuthorizationRow).where(
                AuthorizationRow.authorization_id == pending["authorization_id"],
                AuthorizationRow.tenant_id == ctx.tenant_id,
            ))
            authorization_row = auth_result.scalar_one_or_none()
            if (
                authorization_row is None
                or authorization_row.revoked_at is not None
                or not authorization_row.issued_at <= now < authorization_row.expires_at
                or authorization_row.source_snapshot_id != pending["snapshot_id"]
            ):
                raise HTTPException(
                    status_code=409,
                    detail="operation authorization is no longer valid",
                )

            decision_result = await session.execute(select(DecisionRow).where(
                DecisionRow.tenant_id == ctx.tenant_id,
                DecisionRow.operation_id == operation_id,
                DecisionRow.step_id == step_id,
                DecisionRow.spec_digest == pending["spec_digest"],
            ).with_for_update())
            decision_row = decision_result.scalar_one_or_none()
            if decision_row is not None:
                if (
                    decision_row.approved != body.approved
                    or decision_row.reviewer_id != ctx.user_id
                    or decision_row.approval_ref != approval_ref
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="a different durable decision already exists for this step",
                    )
                decision_id = decision_row.decision_id
            else:
                decision_id = "scid-" + uuid.uuid4().hex
                session.add(DecisionRow(
                    decision_id=decision_id,
                    tenant_id=ctx.tenant_id,
                    operation_id=operation_id,
                    authorization_id=pending["authorization_id"],
                    snapshot_id=pending["snapshot_id"],
                    spec_digest=pending["spec_digest"],
                    step_id=step_id,
                    approved=body.approved,
                    reviewer_id=ctx.user_id,
                    reviewer_role="admin",
                    approval_ref=approval_ref,
                    decided_at=now,
                ))

    signal_payload = {
        "operation_id": operation_id,
        "tenant_id": ctx.tenant_id,
        "authorization_id": pending["authorization_id"],
        "snapshot_id": pending["snapshot_id"],
        "step_id": step_id,
        "spec_digest": pending["spec_digest"],
        "decision_id": decision_id,
        "approved": body.approved,
        "reviewer_id": ctx.user_id,
        "approval_ref": approval_ref,
    }
    try:
        await handle.signal("provide_operator_decision", signal_payload)
    except Exception as exc:
        # The durable decision row is retained. The same request can safely retry
        # and re-send the signal because the unique decision key is idempotent.
        raise HTTPException(
            status_code=503,
            detail={
                "code": "DECISION_PERSISTED_SIGNAL_PENDING",
                "decision_id": decision_id,
                "message": "decision was saved; retry this request to re-send the workflow signal",
            },
        ) from exc
    return {
        "operation_id": operation_id,
        "step_id": step_id,
        "decision_id": decision_id,
        "approved": body.approved,
        "status": "signal_sent",
    }


__all__ = ["router"]
