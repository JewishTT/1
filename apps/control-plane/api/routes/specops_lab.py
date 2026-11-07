"""SpecOps Red-Team Lab API (Feature 036).

The lab is deliberately a separate router from `/specops/phishing` and
`/specops/emulation`: it runs in full red-team mode, every mutation is gated by a
confirmed RoE and the lab boundary, and the full Phishing Club donor is reachable through
the authenticated adapter below. Errors keep the department's vocabulary: `409`
authorization, `422` target, `424` setup, `404` absent (including cross-tenant).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from api.auth import TenantContext, resolve_tenant

try:
    from specops.lab.phishingclub import forward as phishingclub_forward
    from specops.lab.phishingclub import health as phishingclub_health_check
except Exception:  # pragma: no cover - adapter is optional at import time
    phishingclub_forward = None  # type: ignore[assignment]
    phishingclub_health_check = None  # type: ignore[assignment]

try:
    from specops.lab import LAB, LabError
    from specops.roe.gate import RoEError, RosterError
except Exception:  # pragma: no cover - import boundary; the department reports 503
    LAB = None  # type: ignore[assignment]
    LabError = Exception  # type: ignore[assignment,misc]
    RoEError = Exception  # type: ignore[assignment,misc]
    RosterError = Exception  # type: ignore[assignment,misc]

router = APIRouter(prefix="/specops/lab", tags=["specops-lab"])

_TENANT = Annotated[TenantContext, Depends(resolve_tenant)]


def _envelope(**extra: Any) -> dict[str, Any]:
    return {
        "served": ["/specops/lab"],
        "missing": [],
        "scope": "red-team",
        **extra,
    }


def _require() -> Any:
    if LAB is None:  # pragma: no cover - defensive
        raise HTTPException(status_code=503, detail="specops lab unavailable")
    return LAB


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, LabError):
        detail: dict[str, Any] = {"error": type(exc).__name__, "reason": exc.reason}
        if exc.rejected:
            detail["rejected"] = exc.rejected
        raise HTTPException(status_code=exc.status_code, detail=detail) from exc
    if isinstance(exc, RosterError):
        raise HTTPException(
            status_code=422,
            detail={"error": "RosterError", "reason": exc.reason, "rejected_targets": exc.rejected},
        ) from exc
    if isinstance(exc, RoEError):
        raise HTTPException(
            status_code=409, detail={"error": "RoEError", "reason": exc.reason}
        ) from exc
    raise exc


# ── bodies ────────────────────────────────────────────────────────────────


class TemplateBody(BaseModel):
    name: str
    stages: list[str] = Field(min_length=1)
    assets: list[str] = []
    variables: dict[str, str] = {}


class SenderBody(BaseModel):
    name: str
    host: str
    tls: bool = True
    dns_ready: bool = True
    credential_ref: str | None = None


class CampaignBody(BaseModel):
    name: str
    template_id: str = "tpl-lure"
    sender_id: str | None = "snd-lab"
    roster: list[str] = Field(min_length=1)
    attack_mapping: list[str] = []
    retention_days: int = 30


class LaunchBody(BaseModel):
    roe_id: str


class SessionBody(BaseModel):
    mode: str
    target_host: str
    roe_id: str
    retention_hours: int = 24


class CaptureBody(BaseModel):
    kind: str
    secret: str
    label: str = ""


class OperationBody(BaseModel):
    plan_id: str
    lab_fixture: str = "specops/lab-target"
    roe_id: str


class AssessmentBody(BaseModel):
    campaign_id: str
    operation_id: str


# ── reads ─────────────────────────────────────────────────────────────────


@router.get("")
async def overview(ctx: _TENANT) -> dict[str, Any]:
    lab = _require()
    view = lab.overview(ctx)
    return _envelope(**view, missing=list(view["readiness"]["blockers"]))


@router.get("/phishingclub/health")
async def phishingclub_health(ctx: _TENANT) -> dict[str, Any]:
    if phishingclub_health_check is None:  # pragma: no cover - defensive
        raise HTTPException(status_code=503, detail="Phishing Club adapter unavailable")
    status = await phishingclub_health_check()
    return _envelope(phishingclub=status)


@router.api_route(
    "/phishingclub/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def phishingclub_proxy(path: str, request: Request, ctx: _TENANT) -> Response:
    if phishingclub_forward is None:  # pragma: no cover - defensive
        raise HTTPException(status_code=503, detail="Phishing Club adapter unavailable")
    status, headers, body = await phishingclub_forward(
        request.method,
        path,
        query=str(request.query_params),
        headers={key.lower(): value for key, value in request.headers.items()},
        body=await request.body(),
    )
    return Response(content=body, status_code=status, headers=headers)


@router.get("/audit")
async def audit(
    ctx: _TENANT, limit: int = Query(default=100, ge=1, le=500)
) -> dict[str, Any]:
    lab = _require()
    return _envelope(**lab.audit_view(ctx, limit=limit))


@router.get("/templates")
async def list_templates(ctx: _TENANT) -> dict[str, Any]:
    lab = _require()
    return _envelope(templates=lab.overview(ctx)["templates"])


@router.get("/senders")
async def list_senders(ctx: _TENANT) -> dict[str, Any]:
    lab = _require()
    return _envelope(senders=lab.overview(ctx)["senders"])


@router.get("/campaigns")
async def list_campaigns(ctx: _TENANT) -> dict[str, Any]:
    lab = _require()
    return _envelope(campaigns=lab.list_campaigns(ctx))


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str, ctx: _TENANT) -> dict[str, Any]:
    lab = _require()
    try:
        return _envelope(campaign=lab.get_campaign(ctx, campaign_id))
    except Exception as exc:  # noqa: BLE001 - mapped to the department vocabulary
        _raise_http(exc)
        raise  # pragma: no cover


@router.get("/aitm/sessions")
async def list_sessions(ctx: _TENANT) -> dict[str, Any]:
    lab = _require()
    return _envelope(sessions=lab.list_sessions(ctx))


@router.get("/aitm/sessions/{session_id}")
async def get_session(session_id: str, ctx: _TENANT) -> dict[str, Any]:
    lab = _require()
    try:
        return _envelope(session=lab.get_session(ctx, session_id))
    except Exception as exc:  # noqa: BLE001
        _raise_http(exc)
        raise  # pragma: no cover


@router.get("/reports/{campaign_id}")
async def get_report(campaign_id: str, ctx: _TENANT) -> dict[str, Any]:
    lab = _require()
    try:
        return _envelope(report=lab.get_report(ctx, campaign_id))
    except Exception as exc:  # noqa: BLE001
        _raise_http(exc)
        raise  # pragma: no cover


# ── writes ────────────────────────────────────────────────────────────────


@router.post("/templates", status_code=200)
async def create_template(body: TemplateBody, ctx: _TENANT) -> dict[str, Any]:
    lab = _require()
    try:
        return _envelope(
            template=lab.create_template(
                ctx,
                name=body.name,
                stages=body.stages,
                assets=body.assets,
                variables=body.variables,
            )
        )
    except Exception as exc:  # noqa: BLE001
        _raise_http(exc)
        raise  # pragma: no cover


@router.post("/senders", status_code=200)
async def create_sender(body: SenderBody, ctx: _TENANT) -> dict[str, Any]:
    lab = _require()
    try:
        return _envelope(
            sender=lab.create_sender(
                ctx,
                name=body.name,
                host=body.host,
                tls=body.tls,
                dns_ready=body.dns_ready,
                credential_ref=body.credential_ref,
            )
        )
    except Exception as exc:  # noqa: BLE001
        _raise_http(exc)
        raise  # pragma: no cover


@router.post("/campaigns", status_code=200)
async def create_campaign(body: CampaignBody, ctx: _TENANT) -> dict[str, Any]:
    lab = _require()
    try:
        return _envelope(
            campaign=lab.create_campaign(
                ctx,
                name=body.name,
                template_id=body.template_id,
                sender_id=body.sender_id,
                roster=body.roster,
                attack_mapping=body.attack_mapping,
                retention_days=body.retention_days,
            )
        )
    except Exception as exc:  # noqa: BLE001
        _raise_http(exc)
        raise  # pragma: no cover


@router.post("/campaigns/{campaign_id}/launch", status_code=200)
async def launch_campaign(campaign_id: str, body: LaunchBody, ctx: _TENANT) -> dict[str, Any]:
    lab = _require()
    try:
        return _envelope(
            campaign=lab.launch_campaign(ctx, campaign_id=campaign_id, roe_id=body.roe_id)
        )
    except Exception as exc:  # noqa: BLE001
        _raise_http(exc)
        raise  # pragma: no cover


@router.post("/aitm/sessions", status_code=200)
async def start_session(body: SessionBody, ctx: _TENANT) -> dict[str, Any]:
    lab = _require()
    try:
        return _envelope(
            session=lab.start_session(
                ctx,
                mode=body.mode,
                target_host=body.target_host,
                roe_id=body.roe_id,
                retention_hours=body.retention_hours,
            )
        )
    except Exception as exc:  # noqa: BLE001
        _raise_http(exc)
        raise  # pragma: no cover


@router.post("/aitm/sessions/{session_id}/capture", status_code=200)
async def capture(session_id: str, body: CaptureBody, ctx: _TENANT) -> dict[str, Any]:
    lab = _require()
    try:
        return _envelope(
            artifact=lab.capture(
                ctx,
                session_id=session_id,
                kind=body.kind,
                secret=body.secret,
                label=body.label,
            )
        )
    except Exception as exc:  # noqa: BLE001
        _raise_http(exc)
        raise  # pragma: no cover


@router.post("/aitm/sessions/{session_id}/stop", status_code=200)
async def stop_session(session_id: str, ctx: _TENANT) -> dict[str, Any]:
    lab = _require()
    try:
        return _envelope(session=lab.stop_session(ctx, session_id))
    except Exception as exc:  # noqa: BLE001
        _raise_http(exc)
        raise  # pragma: no cover


@router.post("/operations", status_code=200)
async def launch_operation(body: OperationBody, ctx: _TENANT) -> dict[str, Any]:
    lab = _require()
    try:
        return _envelope(
            operation=lab.launch_operation(
                ctx, plan_id=body.plan_id, lab_fixture=body.lab_fixture, roe_id=body.roe_id
            )
        )
    except Exception as exc:  # noqa: BLE001
        _raise_http(exc)
        raise  # pragma: no cover


@router.post("/assessments", status_code=200)
async def link_assessment(body: AssessmentBody, ctx: _TENANT) -> dict[str, Any]:
    lab = _require()
    try:
        return _envelope(
            assessment=lab.link_assessment(
                ctx, campaign_id=body.campaign_id, operation_id=body.operation_id
            )
        )
    except Exception as exc:  # noqa: BLE001
        _raise_http(exc)
        raise  # pragma: no cover


@router.post("/reports/{campaign_id}", status_code=200)
async def generate_report(campaign_id: str, ctx: _TENANT) -> dict[str, Any]:
    lab = _require()
    try:
        return _envelope(report=lab.generate_report(ctx, campaign_id))
    except Exception as exc:  # noqa: BLE001
        _raise_http(exc)
        raise  # pragma: no cover


@router.post("/reports/{campaign_id}/export", status_code=200)
async def export_report(campaign_id: str, ctx: _TENANT) -> dict[str, Any]:
    lab = _require()
    try:
        return _envelope(export=lab.export_report(ctx, campaign_id))
    except Exception as exc:  # noqa: BLE001
        _raise_http(exc)
        raise  # pragma: no cover


@router.post("/kill-switch", status_code=200)
async def kill_switch(ctx: _TENANT) -> dict[str, Any]:
    lab = _require()
    try:
        return _envelope(**lab.kill_switch(ctx))
    except Exception as exc:  # noqa: BLE001
        _raise_http(exc)
        raise  # pragma: no cover


@router.post("/teardown", status_code=200)
async def teardown(ctx: _TENANT) -> dict[str, Any]:
    lab = _require()
    try:
        return _envelope(**lab.teardown(ctx))
    except Exception as exc:  # noqa: BLE001
        _raise_http(exc)
        raise  # pragma: no cover


@router.post("/reset", status_code=200)
async def reset(ctx: _TENANT) -> dict[str, Any]:
    lab = _require()
    try:
        return _envelope(lab=lab.reset(ctx))
    except Exception as exc:  # noqa: BLE001
        _raise_http(exc)
        raise  # pragma: no cover
