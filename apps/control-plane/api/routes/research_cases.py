"""Person Research Case API routes (Feature 034).

Follows existing FastAPI router, auth (TenantContext / resolve_tenant), error
schema and API version conventions. Handlers call domain/services, never write
directly to raw DB or model provider.
"""

from __future__ import annotations

from typing import Annotated, Literal
from urllib.parse import quote, unquote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
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
_artifact_service: Any = None
_report_service: Any = None


def configure(
    service: ResearchCaseService,
    policy: PersonCasePolicy | None = None,
    *,
    artifact_service: Any = None,
    report_service: Any = None,
) -> None:
    global _service, _policy, _artifact_service, _report_service
    _service = service
    _policy = policy
    _artifact_service = artifact_service
    _report_service = report_service


def _get_service() -> ResearchCaseService:
    if _service is None:
        raise HTTPException(status_code=503, detail="research case service not configured")
    return _service


# -- request/response schemas -------------------------------------------------


class SubjectAnchor(BaseModel):
    kind: Literal["public_name", "orcid", "openalex_author_id", "doi_author_record", "official_profile_url"]
    value: str
    evidence_ref: str | None = None


class ContextAmendmentRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=4000)
    rationale: str = Field(default="", max_length=2000)
    kind: Literal["context", "query_hint", "constraint", "question"] = "context"


class DynamicInvariantAnchorRequest(BaseModel):
    kind: Literal[
        "public_name", "orcid", "openalex_author_id", "doi_author_record",
        "official_profile_url", "public_organization", "publication", "public_role",
    ]
    value: str = Field(..., min_length=1, max_length=1000)
    evidence_ref: str = Field(default="", max_length=1000)
    note: str = Field(default="", max_length=2000)


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
    required_capabilities: list[str] = Field(default_factory=list)
    capabilities_preview: list[str]
    capability_gaps: list[dict] = Field(default_factory=list)
    actions: list[dict] = Field(default_factory=list)
    policy_digest: str = ""
    rejected_catalogue_definitions: dict = Field(default_factory=dict)
    plan_state: str
    ready_to_dispatch: bool
    no_network_side_effects: bool = True


class RunCaseRequest(BaseModel):
    idempotency_key: str = Field(..., min_length=1, max_length=200)
    approved_action_refs: list[str] = Field(default_factory=list, min_length=1, max_length=100)


class ApproveActionsRequest(BaseModel):
    action_refs: list[str] = Field(..., min_length=1, max_length=100)


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


@router.post("/{case_id}/context/amendments", status_code=201)
async def append_context_amendment(
    case_id: str,
    body: ContextAmendmentRequest,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """Append an immutable context amendment and invalidate stale approval."""
    ctx.require_role(Role.ANALYST, Role.ADMIN)
    svc = _get_service()
    try:
        return await svc.append_context_amendment(
            case_id=case_id,
            tenant_id=ctx.tenant_id,
            actor_id=ctx.user_id,
            body=body.body,
            rationale=body.rationale,
            kind=body.kind,
        )
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc
    except CaseServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{case_id}/invariants", status_code=201)
async def add_dynamic_invariant_anchor(
    case_id: str,
    body: DynamicInvariantAnchorRequest,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """Append an unresolved dynamic anchor; canonical admission stays a separate decision."""
    ctx.require_role(Role.ANALYST, Role.ADMIN)
    svc = _get_service()
    try:
        return await svc.add_dynamic_invariant_anchor(
            case_id=case_id,
            tenant_id=ctx.tenant_id,
            actor_id=ctx.user_id,
            kind=body.kind,
            value=body.value,
            evidence_ref=body.evidence_ref,
            note=body.note,
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


@router.get("/{case_id}/actions")
async def list_research_case_actions(
    case_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """List current action leaves for analyst review; stale proposal versions are hidden."""
    svc = _get_service()
    try:
        return await svc.list_actions(case_id=case_id, tenant_id=ctx.tenant_id)
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc


@router.post("/{case_id}/actions/approve")
async def approve_research_case_actions(
    case_id: str,
    body: ApproveActionsRequest,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """Admin approval creates immutable action versions tied to current scope and policy."""
    ctx.require_role(Role.ADMIN)
    svc = _get_service()
    try:
        return await svc.approve_actions(
            case_id=case_id,
            tenant_id=ctx.tenant_id,
            approver_id=ctx.user_id,
            action_refs=body.action_refs,
        )
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc
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


@router.post("/{case_id}/artifacts", status_code=201)
async def upload_case_artifact(
    case_id: str,
    request: Request,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """Upload exact original bytes through the existing raw-first ArtifactSink."""
    ctx.require_role(Role.ANALYST, Role.ADMIN)
    if _artifact_service is None:
        raise HTTPException(status_code=503, detail="case artifact service is not composed")

    from services.research_case_artifacts import MAX_ARTIFACT_BYTES, CaseArtifactError

    body = bytearray()
    async for chunk in request.stream():
        if not chunk:
            continue
        if len(body) + len(chunk) > MAX_ARTIFACT_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"artifact exceeds the {MAX_ARTIFACT_BYTES}-byte upload limit",
            )
        body.extend(chunk)

    filename = unquote(request.headers.get("x-artifact-filename", "attachment.bin"))
    caption = unquote(request.headers.get("x-artifact-caption", ""))
    content_type = request.headers.get("content-type", "application/octet-stream")
    try:
        return await _artifact_service.upload(
            case_id=case_id,
            tenant_id=ctx.tenant_id,
            actor_id=ctx.user_id,
            filename=filename,
            content_type=content_type,
            caption=caption,
            body=bytes(body),
        )
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail="case or artifact not found") from exc
    except CaseArtifactError as exc:
        detail = str(exc)
        status_code = (
            413 if "upload limit" in detail or "exceeds the" in detail
            else 400 if "empty" in detail or "actor is required" in detail
            else 503
        )
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/{case_id}/artifacts")
async def list_case_artifacts(
    case_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """List case attachments by tenant-scoped canonical evidence metadata."""
    ctx.require_role(Role.VIEWER, Role.ANALYST, Role.ADMIN)
    if _artifact_service is None:
        raise HTTPException(status_code=503, detail="case artifact service is not composed")
    try:
        return await _artifact_service.list_artifacts(
            case_id=case_id, tenant_id=ctx.tenant_id
        )
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc


@router.get("/{case_id}/artifacts/{artifact_id}/download")
async def download_case_artifact(
    case_id: str,
    artifact_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> Response:
    """Return the verified raw bytes; never serve a cross-tenant object reference."""
    ctx.require_role(Role.VIEWER, Role.ANALYST, Role.ADMIN)
    if _artifact_service is None:
        raise HTTPException(status_code=503, detail="case artifact service is not composed")
    try:
        artifact, body = await _artifact_service.download(
            case_id=case_id, artifact_id=artifact_id, tenant_id=ctx.tenant_id
        )
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail="artifact not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"artifact verification failed: {exc}") from exc
    filename = str(artifact.get("filename") or "artifact.bin")
    return Response(
        content=body,
        media_type=str(artifact.get("content_type") or "application/octet-stream"),
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "X-Content-SHA256": str(artifact.get("content_digest") or ""),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/{case_id}/obligations")
async def list_obligations(
    case_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """Read canonical obligations; family labels come from the case profile criteria."""
    svc = _get_service()
    try:
        case_view = await svc.get_case(case_id=case_id, tenant_id=ctx.tenant_id)
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc
    obligations = await svc._store.obligations(case_id)  # type: ignore[attr-defined]
    from context_engine.person_case_profile import profile_for

    profile = profile_for(case_view["launch_profile"])
    family_by_criterion = {
        template.code: template.claim_family for template in profile.obligations
    }
    return {
        "case_id": case_id,
        "tenant_id": ctx.tenant_id,
        "scope_revision": case_view["scope_revision"],
        "obligations": [
            {
                "obligation_id": obligation.obligation_id,
                "question": obligation.question,
                "claim_families": sorted({
                    family_by_criterion[criterion.criterion_id]
                    for criterion in obligation.acceptance_criteria
                    if criterion.criterion_id in family_by_criterion
                }),
                "state": obligation.status.value,
                "required_capabilities": list(obligation.required_capabilities),
                "eligible_capabilities": list(obligation.eligible_capabilities),
                "satisfaction_criteria": list(obligation.satisfaction_criteria),
                "rationale": obligation.rationale,
                "priority": obligation.priority,
                "priority_basis": obligation.priority_basis,
            }
            for obligation in obligations
        ],
    }


def _require_projection(svc: ResearchCaseService, name: str):
    provider = getattr(svc, "_projection_provider", None)
    method = getattr(provider, name, None) if provider is not None else None
    if not callable(method):
        raise HTTPException(
            status_code=503,
            detail=f"{name} projection is not composed; refusing to return synthetic data",
        )
    return method


async def _read_projection(awaitable):
    """Map known projection failures to explicit API status codes, not fake results."""
    from services.research_case_projection import ProjectionUnavailable

    try:
        return await awaitable
    except ProjectionUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{case_id}/coverage")
async def get_coverage(
    case_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """Source/claim-family/temporal coverage ledger."""
    svc = _get_service()
    case_view = await svc.get_case(case_id=case_id, tenant_id=ctx.tenant_id)
    reader = _require_projection(svc, "coverage_ledger")
    coverage = await _read_projection(
        reader(case_id=case_id, tenant_id=ctx.tenant_id)
    )
    return coverage


@router.get("/{case_id}/claims")
async def list_claims(
    case_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
    limit: int = Query(50, ge=1, le=500),
    cursor: str | None = None,
) -> dict:
    """Claims/contradictions with stable pagination and evidence refs."""
    svc = _get_service()
    await svc.get_case(case_id=case_id, tenant_id=ctx.tenant_id)
    reader = _require_projection(svc, "list_claims")
    claims = await _read_projection(
        reader(case_id=case_id, tenant_id=ctx.tenant_id, limit=limit, cursor=cursor)
    )
    return {"case_id": case_id, **claims}


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
    await svc.get_case(case_id=case_id, tenant_id=ctx.tenant_id)
    reader = _require_projection(svc, "timeline")
    return await _read_projection(
        reader(
            case_id=case_id, tenant_id=ctx.tenant_id,
            valid_from=valid_from, valid_until=valid_until, as_of=as_of, limit=limit,
        )
    )


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
    await svc.get_case(case_id=case_id, tenant_id=ctx.tenant_id)
    reader = _require_projection(svc, "graph")
    return await _read_projection(
        reader(
            case_id=case_id, tenant_id=ctx.tenant_id, as_of=as_of,
            depth=depth, kinds=kinds.split(",") if kinds else None,
        )
    )


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
    if not callable(getattr(svc._store, "record_identity_review", None)):
        raise HTTPException(status_code=503, detail="record_identity_review is not backed by a durable canonical store implementation")
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
    if not callable(getattr(svc._store, "record_claim_dispute", None)):
        raise HTTPException(status_code=503, detail="record_claim_dispute is not backed by a durable canonical store implementation")
    dispute_id = await svc._store.record_claim_dispute(  # type: ignore[attr-defined]
        case_id=case_id,
        claim_id=body.get("claim_id"),
        action=body.get("action"),
        reason=body.get("reason", ""),
        actor=ctx.user_id,
    )
    return {"dispute_id": dispute_id, "event": "claim_dispute.recorded"}


@router.post("/{case_id}/report", status_code=201)
async def generate_report(
    case_id: str,
    body: dict,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """Build and store a reproducible report from canonical observations, spans and claims."""
    ctx.require_role(Role.ANALYST, Role.ADMIN)
    if _report_service is None:
        raise HTTPException(status_code=503, detail="case report service is not composed")
    try:
        return await _report_service.generate(
            case_id=case_id, tenant_id=ctx.tenant_id, actor_id=ctx.user_id
        )
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc
    except Exception as exc:
        from services.research_case_reports import CaseReportError
        if isinstance(exc, CaseReportError):
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        raise


@router.get("/{case_id}/reports/{report_id}")
async def get_case_report(
    case_id: str,
    report_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
) -> dict:
    """Retrieve one immutable tenant-scoped completion report."""
    ctx.require_role(Role.VIEWER, Role.ANALYST, Role.ADMIN)
    if _report_service is None:
        raise HTTPException(status_code=503, detail="case report service is not composed")
    try:
        return await _report_service.get_report(
            case_id=case_id, report_id=report_id, tenant_id=ctx.tenant_id
        )
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail="report not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"report retrieval failed: {exc}") from exc


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
    if not callable(getattr(svc._store, "retention_action", None)):
        raise HTTPException(status_code=503, detail="retention_action is not backed by a durable canonical store implementation")
    action_id = await svc._store.retention_action(  # type: ignore[attr-defined]
        case_id=case_id,
        tenant_id=ctx.tenant_id,
        action=body.get("action"),
        actor=ctx.user_id,
    )
    return {"action_id": action_id, "case_id": case_id}


__all__ = ["router", "configure"]
