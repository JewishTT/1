"""The platform's own control surface: health, and a tick on demand.

Everything here exists because the assembled platform was previously unobservable. A
developer could see that the API answered and that a context row existed, with no way to ask
whether a cycle could run at all -- which is exactly the state the platform was in before
:mod:`composition`: durable context on disk, nothing consuming it.

``health`` reports which components came up and why the others did not. It is a
``200`` even when the durable authority is absent, because a degraded platform is more
useful than a refused probe, and a monitoring system that gets a ``503`` learns nothing
about which part to fix. ``ready`` and ``cycles`` carry the verdict.

``tick`` runs one pass for a context the caller names. It is deliberately exposed rather
than hidden behind the Temporal worker: an investigation's cycle should be drivable without
a workflow server, so a developer can watch a context deepen on a machine that has only
PostgreSQL. When Temporal *is* available the worker drives the same service, and the two
cannot diverge because it is the same object.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import TenantContext, resolve_tenant

log = logging.getLogger(__name__)

router = APIRouter(prefix="/platform", tags=["platform"])


async def resolve_platform() -> Any:
    """The process-wide assembly, or a 503 naming what failed to come up.

    Distinct from :func:`composition.Platform.build`, which never raises: by the time a
    request arrives, an unusable platform should say why rather than pretend.
    """
    from composition import get_platform

    platform = await get_platform()
    if not platform.health.ready:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "the durable authority is unavailable; no cycle can run",
                "health": platform.health.as_dict(),
            },
        )
    return platform


class TickRequest(BaseModel):
    """Which context to run a pass over."""

    context_id: str = ""
    #: Ticks run against a context this tenant owns. Resolved by id when ``context_id`` is
    #: given, and otherwise rejected rather than guessed at: running a tick against another
    #: tenant's context would both read and write their state.
    investigation_id: str = ""
    #: Whether to drain the frontier first. Off by default, because draining consumes leases
    #: and a probe that mutated the acquisition queue would be a surprising side effect of a
    #: read-shaped call.
    drain: bool = False


async def _resolve_context(store: Any, body: TickRequest, tenant_id: str) -> Any:
    """Find the context this request names, within the caller's tenant.

    Filtering by tenant happens here rather than at the call site, so the route cannot
    accidentally tick another tenant's context by leaving the check out. The store exposes
    ``contexts()`` rather than a lookup by id, so this scans the tenant's contexts -- the
    set is small, and adding an id lookup to the store for one route would be premature.
    """
    try:
        contexts = await store.contexts()
    except Exception as exc:  # noqa: BLE001 - reported as 404
        log.debug("context read failed: %s", exc)
        return None
    for context in contexts:
        if str(getattr(context, "tenant_id", "")) != tenant_id:
            continue
        if body.context_id and getattr(context, "context_id", "") == body.context_id:
            return context
        if body.investigation_id and (
            getattr(context, "investigation_id", "") == body.investigation_id
        ):
            return context
    return None


@router.get("/health")
async def platform_health(
    platform: Annotated[Any, Depends(resolve_platform)] = None,
) -> dict:
    """Which components are up."""
    if platform is None:  # pragma: no cover - dependency always provides one
        raise HTTPException(status_code=503, detail="platform unavailable")
    return {
        "platform": platform.as_dict(),
        "components": platform.health.as_dict(),
    }


@router.get("/sources")
async def platform_sources(
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
    platform: Annotated[Any, Depends(resolve_platform)] = None,
) -> dict:
    """The declarative catalogue and what the router can reach through it."""
    if platform is None:  # pragma: no cover
        raise HTTPException(status_code=503, detail="platform unavailable")
    descriptors = platform.bridge.descriptors() if platform.bridge else ()
    return {
        "tenant_id": ctx.tenant_id,
        "sources_loaded": platform.sources,
        "runtimes": sorted({descriptor.runtime_ref for descriptor in descriptors}),
        "capabilities": sorted(platform.bridge.capability_index()) if platform.bridge else [],
    }


@router.post("/tick")
async def platform_tick(
    body: TickRequest,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)],
    platform: Annotated[Any, Depends(resolve_platform)] = None,
) -> dict:
    """Run one cycle pass over a context and report what moved."""
    if platform is None:  # pragma: no cover
        raise HTTPException(status_code=503, detail="platform unavailable")
    service = platform.tick_service()
    if service is None:
        raise HTTPException(
            status_code=503,
            detail="the cycle cannot run: no fabric runner is wired",
        )

    context = await _resolve_context(platform.store, body, ctx.tenant_id)

    if context is None:
        raise HTTPException(
            status_code=404,
            detail="no such context for this tenant; supply context_id or investigation_id",
        )
    if str(getattr(context, "tenant_id", "")) != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="no such context for this tenant")

    results = (
        service.drain_frontier(
            tenant_id=ctx.tenant_id,
            investigation_id=str(getattr(context, "investigation_id", "") or ""),
        )
        if body.drain
        else []
    )

    report = await service.run_tick(
        context, results=results, tenant_id=ctx.tenant_id
    )
    return {"tenant_id": ctx.tenant_id, "tick": report.as_dict()}
