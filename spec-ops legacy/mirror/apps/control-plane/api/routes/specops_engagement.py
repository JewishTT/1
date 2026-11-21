"""Engagement fabric API (Feature 032).

One lifecycle for every SpecOps channel. The department's email channel (phishing) and
voice channel (GhostLine) now report into the same log, so ``GET /engagement/board`` is
the first thing in the department that can answer "who engaged, how deep, in what
order, across channels" — a question neither channel could answer alone.

Status codes follow the same discipline as the rest of the department:

``200`` / ``201``  served
``404``            a named campaign does not exist
``422``            a malformed or refused request — including a credential-bearing
                   payload, which is ``422 PayloadRefused`` rather than a silent strip
``503``            the ``specops.engagement`` subpackage could not be imported

The envelope carries ``served`` / ``missing`` / ``scope`` like every other department
route. ``scope`` is ``tenant-wide``: an engagement programme spans investigations, and
tying it to one would make the cross-campaign view — the whole point — impossible.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import TenantContext, resolve_tenant

try:
    from specops.engagement import (
        DEFINITIONS,
        DONT_HERITATE,
        EventKind,
        PayloadRefused,
        fabric,
        project,
        subject_profiles,
    )
    from specops.engagement.config import engagement_dir
except Exception:  # noqa: BLE001 - import boundary; the department reports 503
    fabric = None  # type: ignore[assignment]
    project = None  # type: ignore[assignment]
    subject_profiles = None  # type: ignore[assignment]
    DEFINITIONS = None  # type: ignore[assignment]
    DONT_HERITATE = None  # type: ignore[assignment]
    EventKind = None  # type: ignore[assignment]
    PayloadRefused = Exception  # type: ignore[assignment,misc]
    engagement_dir = None  # type: ignore[assignment]

router = APIRouter(prefix="/specops/engagement", tags=["specops-engagement"])

_TENANT = Annotated[TenantContext, Depends(resolve_tenant)]


def _envelope(**extra: Any) -> dict[str, Any]:
    return {"served": ["/specops/engagement"], "missing": [], "scope": "tenant-wide", **extra}


def _require() -> Any:
    """The process-wide fabric INSTANCE.

    ``fabric`` is the accessor function, not the object — returning the function would
    make every call site fail at the first attribute access, which is the kind of error
    that only shows up on the first write.
    """
    if fabric is None:  # pragma: no cover - defensive
        raise HTTPException(status_code=503, detail="engagement fabric unavailable")
    return fabric()


# ── bodies ────────────────────────────────────────────────────────────


class EventBody(BaseModel):
    campaign_id: str
    channel: str
    kind: str
    subject_ref: str | None = None
    #: Refused outright for a credential-bearing event. See ``specops.engagement``.
    payload: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    ip: str | None = None
    user_agent: str | None = None
    anonymized: bool = False


class AnonymizeBody(BaseModel):
    campaign_id: str


# ── reads ─────────────────────────────────────────────────────────────


@router.get("/taxonomy")
async def get_taxonomy(ctx: _TENANT = None) -> dict[str, Any]:
    """The closed event vocabulary, the ladder, and what was refused from the donor.

    Served rather than documented in a file, because an operator integrating a new
    channel needs the vocabulary and the ladder together, and needs to know which of the
    donor's ideas were deliberately not taken.
    """
    _require()
    return _envelope(
        events=[definition.as_dict() for definition in DEFINITIONS.values()],
        stages=project([]).as_dict()["stages"],
        dont_heritage=list(DONT_HERITATE),
        log_path=str(engagement_dir()),
    )


@router.get("/board")
async def get_board(ctx: _TENANT = None) -> dict[str, Any]:
    """The whole board: per-campaign funnels plus the cross-campaign subject profiles.

    Two tracks, never one number — ``training`` and the adversarial funnel are separate
    fields because adding them produces a figure that describes neither.
    """
    _require()
    return _envelope(projection=project(fabric().all_events()).as_dict())


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str, ctx: _TENANT = None) -> dict[str, Any]:
    """One campaign's funnel, its events, and its subjects."""
    log = _require()
    events = log.for_campaign(campaign_id)
    if not events:
        raise HTTPException(status_code=404, detail=f"campaign {campaign_id!r} has no events")
    from specops.engagement import campaign_funnel

    return _envelope(
        campaign=campaign_funnel(campaign_id, events).as_dict(),
        events=[e.as_dict() for e in sorted(events, key=lambda e: e.occurred_at)],
    )


@router.get("/timeline")
async def get_timeline(
    limit: int = Query(default=100, ge=1, le=1000), ctx: _TENANT = None
) -> dict[str, Any]:
    """The cross-channel event timeline, most recent first."""
    log = _require()
    events = log.timeline(limit=limit)
    return _envelope(
        events=[e.as_dict() for e in events],
        # Named rather than an empty list: a deployment where no channel reports is a
        # different thing from one where nothing happened today.
        missing=[
            (
                "GET /specops/engagement/timeline (no channel has reported an event — "
                "the email and voice channels both push into this log)"
            )
        ]
        if not events
        else [],
    )


@router.get("/subjects")
async def get_subjects(ctx: _TENANT = None) -> dict[str, Any]:
    """Every subject across every campaign — the view neither channel could produce."""
    _require()
    profiles = subject_profiles(fabric().all_events())
    return _envelope(subjects=[p.as_dict() for p in profiles])


# ── writes ────────────────────────────────────────────────────────────


@router.post("/events", status_code=201)
async def record_event(body: EventBody, ctx: _TENANT = None) -> dict[str, Any]:
    """Record one engagement event.

    ``422 PayloadRefused`` for ``submitted_data`` and ``stage_matched`` when a payload
    is offered. The refusal is an error rather than a silent strip because a caller
    that believes its payload was redacted will go on to log it somewhere else.
    """
    log = _require()
    try:
        kind = EventKind(body.kind)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "UnknownEvent",
                "reason": f"{body.kind!r} is not in the closed vocabulary; see GET /taxonomy",
            },
        ) from None
    try:
        event = log.record(
            campaign_id=body.campaign_id,
            channel=body.channel,
            kind=kind,
            subject_ref=body.subject_ref,
            payload=body.payload,
            metadata=body.metadata,
            ip=body.ip,
            user_agent=body.user_agent,
            anonymized=body.anonymized,
        )
    except PayloadRefused as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "PayloadRefused", "reason": str(exc), "kind": exc.kind.value},
        ) from exc
    return _envelope(event=event.as_dict())


@router.post("/anonymize")
async def anonymize(body: AnonymizeBody, ctx: _TENANT = None) -> dict[str, Any]:
    """Strip identity from a campaign's events, keeping the counts exact.

    The response reports how many rows changed so the caller can record that the
    retention action happened — an anonymisation nobody can account for is not one.
    """
    log = _require()
    changed = log.anonymize_campaign(body.campaign_id)
    return _envelope(campaign_id=body.campaign_id, anonymized=changed)
