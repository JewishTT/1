"""Person Research Case API routes (Feature 034).

Follows existing FastAPI router, auth (TenantContext / resolve_tenant), error
schema and API version conventions. Handlers call domain/services, never write
directly to raw DB or model provider.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.auth import Role, TenantContext, resolve_tenant
from services.research_case_policy import PersonCasePolicy, PolicyDecision
from services.research_case_service import (
    BudgetNotReserved,
    CaseNotApproved,
    CaseNotFound,
    CaseServiceError,
    ResearchCaseService,
)

router = APIRouter(prefix="/research-cases", tags=["research-cases"])

_service: ResearchCaseService | None = None
_policy: PersonCasePolicy | None = None


def configure(service: ResearchCaseService, policy: PersonCasePolicy | None = None) -> None:
    global _service, _policy
    _service = service
    _policy = policy


def _get_service() -> ResearchCaseService:
    if _service is None:
        raise HTTPException(status_code=503, detail="research case service not configured")
    return _service


# -- request/response schemas -------------------------------------------------


class SubjectAnchor(BaseModel):
    kind: str = Field(..., description="public_name|orcid|openalex_author_id|doi_author_record|official_profile_url")
    value: str
    evidence_ref: str | None = None


class ValidTime(BaseModel):
    from_: str | None = Field(None, alias="from")
    until: str | None = None
    precision: str = "unknown"


class CreateCaseRequest(BaseModel):
    purpose_code: str = Field(..., description="PUBLIC_PROFESSIONAL|PUBLIC_ROLE_REVIEW|CONSENTED_RECORDS")
    purpose_text: str = Field(..., min_length=1, max_length=2000)
    basis_ref: str = Field(..., min_length=1)
    launch_profile: str = "PUBLIC_PROFESSIONAL"
    subject_anchors: list[SubjectAnchor] = Field(default_factory=list, min_length=1)
    jurisdictions: list[str] = Field(default_factory=list)
    valid_time: ValidTime = Field(default_factory=ValidTime)
    claim_families: list[str] = Field(default_factory=list)
    allowed_source_ids: list[str] = Field(default_factory=list)
    denied_claim_families: list[str] = Field(default_factory=list)
    budget_ref: str | None = None
    expires_at: str | None = None
    questions: list[str] = Field(default_factory=list)


class ApproveCaseRequest(BaseModel):
    scope_digest: str = Field(..., pattern="^sha256:[0-9a-f]{64}$")
    scope_revision: int = Field(default=1, ge=1)


class ReviseScopeRequest(BaseModel):
    purpose_code: str = Field(..., min_length=1, max_length=100)
    purpose_text: str = Field(..., min_length=1, max_length=2000)
    basis_ref: str = Field(..., min_length=1, max_length=500)
    launch_profile: str = "PUBLIC_PROFESSIONAL"
    subject_anchors: list[SubjectAnchor] = Field(..., min_length=1, max_length=100)
    jurisdictions: list[str] = Field(default_factory=list, max_length=50)
    valid_time: ValidTime = Field(default_factory=ValidTime)
    claim_families: list[str] = Field(default_factory=list, max_length=100)
    allowed_source_ids: list[str] = Field(default_factory=list, max_length=100)
    denied_claim_families: list[str] = Field(default_factory=list, max_length=100)
    budget_ref: str | None = None
    expires_at: str | None = None


class PlanCaseResponse(BaseModel):
    case_id: str
    tenant_id: str
    scope_digest: str
    scope_revision: int
    obligations: list[dict]
    capabilities_preview: list[str]
    no_network_side_effects: bool = True


class RunCaseRequest(BaseModel):
    idempotency_key: str = Field(..., min_length=1)
    approved_action_refs: list[str] = Field(default_factory=list)


class PauseCaseResponse(BaseModel):
    case_id: str
    state: str


class CloseCaseRequest(BaseModel):
    disposition: str = Field(..., pattern="^(COMPLETE|PARTIAL|BLOCKED|CANCELLED|CLOSED_WITH_NO_FINDING)$")
    report: dict | None = None


# -- routes -----------------------------------------------------------------


@router.post("", status_code=201)
async def create_research_case(
    body: CreateCaseRequest,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """Create a draft research case. No collection."""
    ctx.require_role(Role.ANALYST, Role.ADMIN)
    svc = _get_service()
    try:
        return await svc.create_case(
            tenant_id=ctx.tenant_id,
            created_by=ctx.user_id,
            purpose_code=body.purpose_code,
            purpose_text=body.purpose_text,
            basis_ref=body.basis_ref,
            launch_profile=body.launch_profile,
            subject_anchors=[a.model_dump() for a in body.subject_anchors],
            jurisdictions=body.jurisdictions,
            valid_time=body.valid_time.model_dump(by_alias=True),
            claim_families=body.claim_families,
            allowed_source_ids=body.allowed_source_ids,
            denied_claim_families=body.denied_claim_families,
            budget_ref=body.budget_ref,
            expires_at=body.expires_at,
            questions=body.questions,
        )
    except CaseServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{case_id}")
async def get_research_case(
    case_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """Read a tenant-scoped case through its application service."""
    svc = _get_service()
    try:
        return await svc.get_case(case_id=case_id, tenant_id=ctx.tenant_id)
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc


@router.patch("/{case_id}/scope")
async def propose_scope_revision(
    case_id: str,
    body: ReviseScopeRequest,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """Append a new scope revision and invalidate the previous approval."""
    ctx.require_role(Role.ANALYST, Role.ADMIN)
    svc = _get_service()
    try:
        return await svc.revise_scope(
            case_id=case_id,
            tenant_id=ctx.tenant_id,
            actor_id=ctx.user_id,
            purpose_code=body.purpose_code,
            purpose_text=body.purpose_text,
            basis_ref=body.basis_ref,
            launch_profile=body.launch_profile,
            subject_anchors=[anchor.model_dump() for anchor in body.subject_anchors],
            jurisdictions=body.jurisdictions,
            valid_time=body.valid_time.model_dump(by_alias=True),
            claim_families=body.claim_families,
            allowed_source_ids=body.allowed_source_ids,
            denied_claim_families=body.denied_claim_families,
            budget_ref=body.budget_ref,
            expires_at=body.expires_at,
        )
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc
    except CaseServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{case_id}/approve")
async def approve_research_case(
    case_id: str,
    body: ApproveCaseRequest,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """Approver stamps authority/scope/policy digest."""
    ctx.require_role(Role.ADMIN)
    svc = _get_service()
    try:
        return await svc.approve_case(
            case_id=case_id,
            tenant_id=ctx.tenant_id,
            approver_id=ctx.user_id,
            scope_digest=body.scope_digest,
            scope_revision=body.scope_revision,
        )
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CaseServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{case_id}/plan", response_model=PlanCaseResponse)
async def plan_research_case(
    case_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> PlanCaseResponse:
    """Compile questions and return preview obligations/capabilities/cost. No network side effects."""
    ctx.require_role(Role.VIEWER, Role.ANALYST, Role.ADMIN)
    svc = _get_service()
    try:
        result = await svc.plan_case(case_id=case_id, tenant_id=ctx.tenant_id)
        return PlanCaseResponse(**result)
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CaseNotApproved as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except CaseServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{case_id}/run")
async def run_research_case(
    case_id: str,
    body: RunCaseRequest,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """Enqueue only approved plan/action refs; idempotent request key required."""
    ctx.require_role(Role.ANALYST, Role.ADMIN)
    svc = _get_service()
    try:
        return await svc.run_case(
            case_id=case_id,
            tenant_id=ctx.tenant_id,
            idempotency_key=body.idempotency_key,
            approved_action_refs=body.approved_action_refs,
        )
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CaseNotApproved as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except BudgetNotReserved as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except CaseServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{case_id}/pause", response_model=PauseCaseResponse)
async def pause_research_case(
    case_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> PauseCaseResponse:
    """Cancel or pause dispatch; preserve partial results."""
    ctx.require_role(Role.ANALYST, Role.ADMIN)
    svc = _get_service()
    try:
        return await svc.pause_case(case_id=case_id, tenant_id=ctx.tenant_id)
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CaseServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{case_id}/obligations")
async def list_obligations(
    case_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """Obligations plus current state, refs, blocker reason."""
    svc = _get_service()
    context = await svc._store.get_context(case_id)  # type: ignore[attr-defined]
    if context is None or context.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="case not found")
    obligations = await svc._store.open_obligations(case_id)  # type: ignore[attr-defined]
    return {
        "case_id": case_id,
        "tenant_id": ctx.tenant_id,
        "obligations": [
            {
                "obligation_id": o.obligation_id,
                "question": o.question,
                "claim_family": o.claim_family,
                "state": o.status.value,
                "required_capabilities": list(o.required_capabilities),
                "satisfaction_condition": o.satisfaction_condition,
                "scope_condition": o.scope_condition,
                "priority": o.priority,
                "priority_basis": o.priority_basis,
            }
            for o in obligations
        ],
    }


@router.get("/{case_id}/coverage")
async def get_coverage(
    case_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """Source/claim-family/temporal coverage ledger."""
    svc = _get_service()
    context = await svc._store.get_context(case_id)  # type: ignore[attr-defined]
    if context is None or context.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="case not found")
    coverage = await svc._store.coverage_ledger(case_id)  # type: ignore[attr-defined]
    return {"case_id": case_id, "scope_revision": context.scope_revision, "coverage": coverage}


@router.get("/{case_id}/claims")
async def list_claims(
    case_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
    limit: int = Query(50, ge=1, le=500),
    cursor: str | None = None,
) -> dict:
    """Claims/contradictions with stable pagination and evidence refs."""
    svc = _get_service()
    context = await svc._store.get_context(case_id)  # type: ignore[attr-defined]
    if context is None or context.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="case not found")
    claims = await svc._store.list_claims(case_id, limit=limit, cursor=cursor)  # type: ignore[attr-defined]
    return {"case_id": case_id, "claims": claims}


@router.get("/{case_id}/timeline")
async def get_timeline(
    case_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
    valid_from: str | None = None,
    valid_until: str | None = None,
    as_of: str | None = None,
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    """Dual-temporal query: valid time and observation/capture time."""
    svc = _get_service()
    context = await svc._store.get_context(case_id)  # type: ignore[attr-defined]
    if context is None or context.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="case not found")
    timeline = await svc._store.timeline(  # type: ignore[attr-defined]
        case_id=case_id,
        valid_from=valid_from,
        valid_until=valid_until,
        as_of=as_of,
        limit=limit,
    )
    return {"case_id": case_id, "timeline": timeline}


@router.get("/{case_id}/graph")
async def get_graph(
    case_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
    as_of: str | None = None,
    depth: int = Query(1, ge=1, le=3),
    kinds: str | None = None,
) -> dict:
    """Case-scoped nodes/edges; hard max depth and node count."""
    svc = _get_service()
    context = await svc._store.get_context(case_id)  # type: ignore[attr-defined]
    if context is None or context.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="case not found")
    graph = await svc._store.graph(  # type: ignore[attr-defined]
        case_id=case_id,
        as_of=as_of,
        depth=depth,
        kinds=kinds.split(",") if kinds else None,
    )
    return graph


@router.post("/{case_id}/identity-reviews")
async def create_identity_review(
    case_id: str,
    body: dict,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """Append review decision and rationale; no direct merge side effect."""
    ctx.require_role(Role.ANALYST, Role.ADMIN)
    svc = _get_service()
    context = await svc._store.get_context(case_id)  # type: ignore[attr-defined]
    if context is None or context.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="case not found")
    review_id = await svc._store.record_identity_review(  # type: ignore[attr-defined]
        case_id=case_id,
        tenant_id=ctx.tenant_id,
        decision=body.get("decision"),
        rationale=body.get("rationale", ""),
        reviewer=ctx.user_id,
    )
    return {"review_id": review_id, "event": "identity_review.recorded"}


@router.post("/{case_id}/claim-disputes")
async def create_claim_dispute(
    case_id: str,
    body: dict,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """Contest/retract/qualify a claim with reason; append-only."""
    ctx.require_role(Role.ANALYST, Role.ADMIN)
    svc = _get_service()
    context = await svc._store.get_context(case_id)  # type: ignore[attr-defined]
    if context is None or context.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="case not found")
    dispute_id = await svc._store.record_claim_dispute(  # type: ignore[attr-defined]
        case_id=case_id,
        claim_id=body.get("claim_id"),
        action=body.get("action"),
        reason=body.get("reason", ""),
        actor=ctx.user_id,
    )
    return {"dispute_id": dispute_id, "event": "claim_dispute.recorded"}


@router.post("/{case_id}/report")
async def generate_report(
    case_id: str,
    body: dict,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """Generate report from admitted claims/coverage; model synthesis optional."""
    ctx.require_role(Role.ANALYST, Role.ADMIN)
    svc = _get_service()
    context = await svc._store.get_context(case_id)  # type: ignore[attr-defined]
    if context is None or context.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="case not found")
    report_id = await svc._store.generate_report(  # type: ignore[attr-defined]
        case_id=case_id,
        tenant_id=ctx.tenant_id,
        approved_finding_ids=body.get("approved_finding_ids", []),
    )
    return {"report_id": report_id, "case_id": case_id}


@router.post("/{case_id}/close")
async def close_research_case(
    case_id: str,
    body: CloseCaseRequest,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """Terminal state + CompletionReport; requires open obligations dispositioned."""
    ctx.require_role(Role.ANALYST, Role.ADMIN)
    svc = _get_service()
    try:
        return await svc.close_case(
            case_id=case_id,
            tenant_id=ctx.tenant_id,
            disposition=body.disposition,
            report=body.report,
        )
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CaseServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{case_id}/retention-action")
async def retention_action(
    case_id: str,
    body: dict,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """Policy-governed export/redaction/retention/delete workflow with audit trail."""
    ctx.require_role(Role.ADMIN)
    svc = _get_service()
    context = await svc._store.get_context(case_id)  # type: ignore[attr-defined]
    if context is None or context.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="case not found")
    action_id = await svc._store.retention_action(  # type: ignore[attr-defined]
        case_id=case_id,
        tenant_id=ctx.tenant_id,
        action=body.get("action"),
        actor=ctx.user_id,
    )
    return {"action_id": action_id, "case_id": case_id}


__all__ = ["router", "configure"]
