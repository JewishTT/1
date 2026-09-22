"""FastAPI application entrypoint for the COGNITIVE control plane (T024, US1).

Assembles routers and shared lifespan. Serves the investigation API used by the
smoke/quickstart scenario.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import sse
from api.routes import (
    connectors,
    entities,
    fabric,
    findings,
    investigations,
    metrics,
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
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: telemetry + schema guarantees would be initialised here.
    yield


app = FastAPI(title="COGNITIVE Control Plane", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers under `/api/v1/` to match the Vite proxy + test clients.
for _router in (investigations.router, search.router, entities.router,
                findings.router, quarantine.router, metrics.router,
                connectors.router, resolutions.router, fabric.router):
    app.include_router(_router, prefix="/api/v1")

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