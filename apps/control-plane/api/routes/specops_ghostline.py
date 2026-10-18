"""GhostLine API for the CI/SpecOps department (Feature 031).

Every control GhostLine's CLI exposes is served here, so the CLI is a convenience
rather than the only way to operate it:

===============  ==============================================================
``clone``        ``POST   /specops/ghostline/voices/clone``
                 ``POST   /specops/ghostline/voices`` (register a premade id)
``serve``        ``POST   /specops/ghostline/runtime/start``
                 ``POST   /specops/ghostline/runtime/stop``
                 ``GET    /specops/ghostline/status``
``call``         ``POST   /specops/ghostline/calls``
``analytics``    ``GET    /specops/ghostline/analytics``
                 ``GET    /specops/ghostline/analytics/export?format=csv|json``
                 ``GET    /specops/ghostline/calls`` / ``/calls/{id}``
===============  ==============================================================

Plus the two surfaces the CLI has no shape for: ``GET /playbooks`` /
``/playbooks/{id}`` to read a scenario before dialling, and
``POST /playbooks/{id}/simulate`` to run the donor's stage machine over a scripted
transcript.

**The gate is not bypassable from here.** ``POST /calls`` runs
``specops.roe.gate.launch_campaign`` before the donor's Twilio service is touched, so
a missing sign-off is ``409 RoEError`` and an unrostered number is ``422
RosterError`` -- the same codes, in the same order, as the phishing router, because it
is the same gate. ``captured_credentials_count`` is ``0`` on every response in this
module, structurally.

Failures are separated by kind, because they mean different things to an operator and
must not read the same in the UI: ``409``/``422`` are authorisation facts from the
gate, ``424`` is a setup fact from the platform or the provider (a named reason, not
a stack trace), ``404`` is a genuinely absent record, and ``503`` means the donor
subpackage could not be imported at all.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import TenantContext, resolve_tenant

try:
    from specops.ghostline.engine import SimulationUnavailable
    from specops.ghostline.service import GateRefused, Service
    from specops.ghostline.telephony import DialBlocked
    from specops.ghostline.voices import VoiceUnavailable
except Exception:  # noqa: BLE001 - import boundary; the department reports 503, not 500
    Service = None  # type: ignore[assignment,misc]
    GateRefused = Exception  # type: ignore[assignment,misc]
    DialBlocked = Exception  # type: ignore[assignment,misc]
    VoiceUnavailable = Exception  # type: ignore[assignment,misc]
    SimulationUnavailable = Exception  # type: ignore[assignment,misc]

router = APIRouter(prefix="/specops/ghostline", tags=["specops-ghostline"])

#: One facade per process, mirroring the process-wide donor handle and ledger.
_SVC: Any = Service() if Service is not None else None

_TENANT = Annotated[TenantContext, Depends(resolve_tenant)]


def _envelope(**extra: Any) -> dict[str, Any]:
    """The department's standard response shape.

    ``served`` names what answered, ``missing`` names what did not, ``scope`` says
    whether the figures are tenant-wide. GhostLine is a tenant-wide subject: an
    exercise belongs to an engagement, not to one investigation.
    """
    return {"served": ["/specops/ghostline"], "missing": [], "scope": "tenant-wide", **extra}


def _require_service() -> Any:
    if _SVC is None:  # pragma: no cover - defensive
        raise HTTPException(status_code=503, detail="ghostline integration unavailable")
    return _SVC


# ── bodies ────────────────────────────────────────────────────────────


class CloneBody(BaseModel):
    name: str
    #: A sample already present under the configured samples root (the donor CLI's shape).
    sample_ref: str | None = None
    #: An upload: base64 payload plus the filename that carries the suffix.
    sample_base64: str | None = None
    sample_filename: str | None = None


class RegisterVoiceBody(BaseModel):
    voice_id: str
    name: str
    origin: str = "premade"
    notes: str | None = None


class StartBody(BaseModel):
    voice_id: str
    playbook_id: str
    port: int | None = Field(default=None, ge=1, le=65535)


class DialBody(BaseModel):
    #: E.164. Validated again server-side; the browser's check is a convenience.
    target: str
    campaign: str = "drill"
    persona: str = "professional"
    roe_id: str
    #: The supervisor-approved roster. A target outside it is a RosterError.
    approved_roster: list[str]
    playbook_id: str | None = None


class TurnBody(BaseModel):
    role: str
    content: str
    stage: str | None = None
    playbook_id: str | None = None
    sentiment_score: float | None = None
    interest_level: float | None = None
    objection_type: str | None = None
    trigger_used: str | None = None


class CompleteBody(BaseModel):
    outcome: str
    notes: str | None = None


class SimulateBody(BaseModel):
    utterances: list[str] = Field(default_factory=list)


# ── status ────────────────────────────────────────────────────────────


@router.get("/status")
async def get_status(ctx: _TENANT = None) -> dict[str, Any]:
    """One render's worth of readiness: donor, providers, runtime, counts, absences."""
    svc = _require_service()
    return _envelope(**svc.status())


# ── playbooks ─────────────────────────────────────────────────────────


@router.get("/playbooks")
async def list_playbooks(ctx: _TENANT = None) -> dict[str, Any]:
    """The donor's playbook library, as plan summaries."""
    svc = _require_service()
    playbooks = svc.playbooks()
    errors = svc.library.validation_errors()
    missing = list(svc.library.named_absences())
    return _envelope(
        playbooks=playbooks,
        invalid={pid: reason for pid, reason in errors.items()},
        missing=missing + ([] if playbooks else ["GET /specops/ghostline/playbooks (none loaded)"]),
    )


@router.get("/playbooks/{playbook_id}")
async def get_playbook(playbook_id: str, ctx: _TENANT = None) -> dict[str, Any]:
    """One playbook: every stage, its persona, and the platform's ATT&CK mapping."""
    svc = _require_service()
    detail = svc.playbook(playbook_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"playbook {playbook_id!r} is not loaded")
    return _envelope(**detail)


@router.post("/playbooks/reload")
async def reload_playbooks(ctx: _TENANT = None) -> dict[str, Any]:
    """Re-read the donor's playbook tree. Returns the number loaded."""
    svc = _require_service()
    return _envelope(playbook_count=svc.reload_playbooks())


@router.post("/playbooks/{playbook_id}/simulate")
async def simulate_playbook(
    playbook_id: str, body: SimulateBody, ctx: _TENANT = None
) -> dict[str, Any]:
    """Dry-run the donor's stage machine over a scripted transcript.

    Nothing is dialled, nothing is persisted, and the utterances are redacted on the
    way back out. A playbook whose branches are wrong should be found here rather
    than by its target.
    """
    svc = _require_service()
    try:
        result = svc.simulate(playbook_id, list(body.utterances))
    except SimulationUnavailable as exc:
        raise HTTPException(
            status_code=424,
            detail={"error": "SimulationUnavailable", "reason": getattr(exc, "reason", str(exc))},
        ) from exc
    return _envelope(simulation=result)


# ── voices (donor CLI: `clone`) ───────────────────────────────────────


@router.get("/voices")
async def list_voices(ctx: _TENANT = None) -> dict[str, Any]:
    svc = _require_service()
    return _envelope(voices=svc.list_voices(), missing=list(svc.voices.named_absences()))


@router.post("/voices", status_code=201)
async def register_voice(body: RegisterVoiceBody, ctx: _TENANT = None) -> dict[str, Any]:
    """Record a voice id the operator already holds.

    The path the donor's own documentation sends free-tier operators down: cloning
    needs a paid plan, so they pick a stock voice from the provider's console. That id
    is a perfectly good voice; the CLI just has nowhere to put it.
    """
    svc = _require_service()
    try:
        voice = svc.register_voice(
            voice_id=body.voice_id,
            name=body.name,
            origin=body.origin,
            notes=body.notes,
        )
    except VoiceUnavailable as exc:
        raise HTTPException(
            status_code=422, detail={"error": "VoiceUnavailable", "reason": exc.reason}
        ) from exc
    return _envelope(voice=voice.as_dict())


@router.post("/voices/clone", status_code=201)
async def clone_voice(body: CloneBody, ctx: _TENANT = None) -> dict[str, Any]:
    """Clone a voice from a sample through the donor's ElevenLabs service."""
    svc = _require_service()
    try:
        voice = svc.clone_voice(
            name=body.name,
            sample_ref=body.sample_ref,
            sample_bytes=_decode(body.sample_base64) if body.sample_base64 else None,
            sample_filename=body.sample_filename,
        )
    except VoiceUnavailable as exc:
        # 422: the request named a sample the platform refused (format, size, path,
        # missing provider). The reason is operator-actionable and is passed through.
        raise HTTPException(
            status_code=422, detail={"error": "VoiceUnavailable", "reason": exc.reason}
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=424, detail={"error": "VoiceCloneFailed", "reason": str(exc)}
        ) from exc
    return _envelope(voice=voice.as_dict())


@router.delete("/voices/{voice_id}")
async def forget_voice(voice_id: str, ctx: _TENANT = None) -> dict[str, Any]:
    """Forget a registered voice. Refused while a runtime is pinned to it."""
    svc = _require_service()
    state = svc.runtime.state()
    in_use = voice_id if state.voice_id == voice_id and state.state == "running" else None
    try:
        removed = svc.forget_voice(voice_id, in_use_by=in_use)
    except VoiceUnavailable as exc:
        raise HTTPException(
            status_code=409, detail={"error": "VoiceUnavailable", "reason": exc.reason}
        ) from exc
    if not removed:
        raise HTTPException(status_code=404, detail=f"voice {voice_id!r} is not registered")
    return _envelope(removed=voice_id)


# ── runtime (donor CLI: `serve`) ──────────────────────────────────────


@router.post("/runtime/start")
async def start_runtime(body: StartBody, ctx: _TENANT = None) -> dict[str, Any]:
    """Bring the runtime up on a voice and a playbook.

    ``424 Failed Dependency`` when a prerequisite is absent, with every blocker
    named. That is a different thing from an authorisation failure and the UI shows
    them differently: this one is a setup checklist, not a refusal.
    """
    svc = _require_service()
    try:
        state = svc.start_runtime(
            voice_id=body.voice_id, playbook_id=body.playbook_id, port=body.port
        )
    except Exception as exc:
        reason = getattr(exc, "reason", str(exc))
        blockers = list(getattr(exc, "blockers", ()) or ())
        raise HTTPException(
            status_code=424,
            detail={"error": "RuntimeUnavailable", "reason": reason, "blockers": blockers},
        ) from exc
    return _envelope(runtime=state)


@router.post("/runtime/stop")
async def stop_runtime(ctx: _TENANT = None) -> dict[str, Any]:
    """Tear the runtime down and close the tunnel.

    Idempotent: stopping a stopped runtime is the state an operator wants, not an
    error.
    """
    svc = _require_service()
    return _envelope(runtime=svc.stop_runtime())


# ── dialling (donor CLI: `call`) ──────────────────────────────────────


@router.post("/calls", status_code=201)
async def place_call(body: DialBody, ctx: _TENANT = None) -> dict[str, Any]:
    """Place an outbound call. Gated: RoE first, then roster, then the donor.

    ``409 RoEError`` without a confirmed sign-off; ``422 RosterError`` with a target
    the supervisor did not approve; ``424`` when the platform or the provider cannot
    place it. In no case does the donor's Twilio service run before the gate passes.
    """
    svc = _require_service()
    try:
        result = svc.dial(
            target=body.target,
            campaign=body.campaign,
            persona=body.persona,
            roe_id=body.roe_id,
            approved_roster=list(body.approved_roster),
            playbook_id=body.playbook_id,
        )
    except GateRefused as exc:
        # The gate is the platform's own; its verdict is passed through unchanged so
        # the UI renders the reason the supervisor would recognise.
        detail: dict[str, Any] = {"error": exc.code, "reason": exc.reason}
        if exc.rejected:
            detail["rejected_targets"] = exc.rejected
        raise HTTPException(
            status_code=409 if exc.code == "RoEError" else 422, detail=detail
        ) from exc
    except DialBlocked as exc:
        raise HTTPException(
            status_code=424, detail={"error": "DialBlocked", "reason": exc.reason}
        ) from exc
    return _envelope(**result)


@router.get("/calls")
async def list_calls(limit: int = 50, ctx: _TENANT = None) -> dict[str, Any]:
    """Recent calls, most recent first. Transcripts are not inlined."""
    svc = _require_service()
    calls = svc.calls(limit=max(1, min(limit, 500)))
    return _envelope(calls=calls, missing=list(svc.ledger.named_absences()))


@router.get("/calls/{call_id}")
async def get_call(call_id: str, ctx: _TENANT = None) -> dict[str, Any]:
    """One call with its redacted transcript."""
    svc = _require_service()
    record = svc.call(call_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"call {call_id!r} is not in the ledger")
    return _envelope(call=record)


@router.post("/calls/{call_id}/turns", status_code=201)
async def log_turn(call_id: str, body: TurnBody, ctx: _TENANT = None) -> dict[str, Any]:
    """Append a turn to a call. ``content`` is redacted before it is stored.

    This is how a live call's transcript reaches the platform when the donor's own
    media server owns the socket. The redaction is the same one the donor path uses,
    so a turn logged here is indistinguishable from one the donor wrote -- including
    its ``redaction_kinds``.
    """
    svc = _require_service()
    try:
        message = svc.log_turn(
            call_id,
            role=body.role,
            content=body.content,
            stage=body.stage,
            playbook_id=body.playbook_id,
            sentiment_score=body.sentiment_score,
            interest_level=body.interest_level,
            objection_type=body.objection_type,
            trigger_used=body.trigger_used,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"call {call_id!r} is not in the ledger"
        ) from exc
    return _envelope(message=message)


@router.post("/calls/{call_id}/complete")
async def complete_call(call_id: str, body: CompleteBody, ctx: _TENANT = None) -> dict[str, Any]:
    """Close a call with its outcome."""
    svc = _require_service()
    try:
        record = svc.complete_call(call_id, body.outcome, notes=body.notes)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"call {call_id!r} is not in the ledger"
        ) from exc
    except DialBlocked as exc:
        raise HTTPException(
            status_code=422, detail={"error": "DialBlocked", "reason": exc.reason}
        ) from exc
    return _envelope(call=record)


# ── analytics (donor CLI: `analytics`) ────────────────────────────────


@router.get("/analytics")
async def get_analytics(campaign: str | None = None, ctx: _TENANT = None) -> dict[str, Any]:
    """Stage distribution, outcome split and campaign rollups, served."""
    svc = _require_service()
    return _envelope(analytics=svc.analytics(campaign=campaign))


@router.get("/analytics/export")
async def export_analytics(
    format: str = "csv", campaign: str | None = None, ctx: _TENANT = None
) -> dict[str, Any]:
    """The donor's ``analytics`` export, served instead of written to a file.

    Generated from the same aggregate the dashboard renders, so what an operator
    exports is what they saw -- the donor's version is a separate CSV that can drift
    from the dashboard it is meant to describe.
    """
    svc = _require_service()
    try:
        export = svc.analytics_export(campaign=campaign, fmt=format)
    except DialBlocked as exc:
        raise HTTPException(
            status_code=422, detail={"error": "DialBlocked", "reason": exc.reason}
        ) from exc
    return _envelope(export=export)


# ── helpers ───────────────────────────────────────────────────────────


def _decode(payload: str) -> bytes:
    """Decode a base64 upload.

    Decoded in the router so a malformed body is a ``422`` at the HTTP boundary
    rather than a decode error surfacing from inside the voice service.
    """
    import base64
    import binascii

    try:
        return base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "VoiceUnavailable",
                "reason": f"sample_base64 is not valid base64: {exc}",
            },
        ) from exc
