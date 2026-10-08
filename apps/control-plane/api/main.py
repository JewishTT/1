"""FastAPI application entrypoint for the COGNITIVE control plane (T024, US1).

Assembles routers and starts the platform. The lifespan is no longer a placeholder: it
builds the composition root, so a running API has a durable context store, a fabric that
can grow a context, a query cycle that can plan acquisition, and the catalogue those plans
route against. Startup failures are recorded in ``/api/v1/platform/health`` rather than
raised, so a deployment missing one subsystem still serves the rest.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api import sse
from api.routes import (
    connectors,
    discovery,
    entities,
    fabric,
    findings,
    investigation_context,
    investigations,
    manual_assertions,
    metrics,
    network,
    platform,
    quarantine,
    resolutions,
    science_causal,
    science_claims,
    science_hypotheses,
    science_review,
    science_robustness,
    science_structure,
    science_tda,
    science_temporal,
    search,
    search_rebuild,
    temporal_materializations,
    tools,
)

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the platform once, for the life of the process.

    Never raises. A composition root that aborts startup would take the whole API down for
    one missing subsystem, and the operator would see a boot failure rather than a
    diagnosis. Components that came up, and those that did not, are reported by
    ``GET /api/v1/platform/health``.
    """
    try:
        from composition import close_platform, get_platform

        assembled = await get_platform()
        log.info(
            "platform assembled: durable=%s fabric=%s sources=%d cycles=%s",
            assembled.health.durable,
            assembled.health.fabric,
            assembled.sources,
            assembled.health.cycles,
        )
        for note in assembled.health.notes:
            log.warning("platform: %s", note)
    except Exception as exc:  # noqa: BLE001 - boot must survive a partial platform
        log.error("platform assembly failed: %s", exc)
    try:
        yield
    finally:
        try:
            from composition import close_platform

            await close_platform()
        except Exception as exc:  # noqa: BLE001 - shutdown is best effort
            log.warning("platform shutdown: %s", exc)


app = FastAPI(title="COGNITIVE Control Plane", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers under `/api/v1/` to match the Vite proxy + test clients.
for _router in (
    investigations.router,
    search.router,
    search_rebuild.router,
    discovery.router,
    entities.router,
    findings.router,
    quarantine.router,
    metrics.router,
    connectors.router,
    resolutions.router,
    fabric.router,
    network.router,
    tools.router,
):
    app.include_router(_router, prefix="/api/v1")
app.include_router(temporal_materializations.router, prefix="/api/v1")
# The platform's own surface: component health and a cycle tick on demand. Mounted beside
# the context routes because a tick *is* the thing the context routes describe.
app.include_router(platform.router, prefix="/api/v1")
# The Context Engine's door. Mounted under /api/v1 with the rest of the control plane:
# an investigation's context is part of the investigation, not a separate surface.
app.include_router(investigation_context.router, prefix="/api/v1")
# Manual analyst assertions, scoped to an investigation. Mounted here so a hand-typed
# entity or relation is reachable from the investigation workspace rather than only from
# the legacy global routes.
app.include_router(manual_assertions.router, prefix="/api/v1")

# Science fabric routes carry their own `/api/science` prefix (science-api.md).
app.include_router(science_claims.router)
app.include_router(science_hypotheses.router)
app.include_router(science_structure.router)
app.include_router(science_robustness.router)
app.include_router(science_review.router)
app.include_router(science_causal.router)
app.include_router(science_temporal.router)
app.include_router(science_tda.router)
app.include_router(sse.router)


# Health probe
@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "control-plane"}


# Built webapp console: served from the same origin as the API so the SPA needs
# no dev proxy. Mounted last so it never shadows an API route.
_WEBAPP_DIST = Path(__file__).resolve().parents[2] / "webapp" / "dist"

if _WEBAPP_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_WEBAPP_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        candidate = _WEBAPP_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_WEBAPP_DIST / "index.html")
