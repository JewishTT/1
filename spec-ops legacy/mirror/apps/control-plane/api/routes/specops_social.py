"""Social-reaction projection API for the CI/SpecOps department (027, US5, T041).

Runs a projection of a modeled population's reaction to a narrative/shock over a
horizon and returns reach/polarization trajectories, a phase-transition risk
indicator, and a confidence that is LOW when the population or narrative is sparse.
Deterministic: same inputs ⇒ same projection.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import TenantContext, resolve_tenant

try:
    from specops.social import project as run_projection
    from specops.social import to_wire as projection_wire
except Exception:  # pragma: no cover
    run_projection = None  # type: ignore[assignment]
    projection_wire = None  # type: ignore[assignment]

router = APIRouter(prefix="/specops/social", tags=["specops-social"])


class ProjectionBody(BaseModel):
    population_ref: str
    narrative_input: str
    horizon: int


@router.post("/projections", status_code=200)
async def create_projection(body: ProjectionBody, ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None) -> dict:
    if run_projection is None or projection_wire is None:  # pragma: no cover
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="specops social unavailable")
    projection = run_projection(
        population_ref=body.population_ref,
        narrative_input=body.narrative_input,
        horizon=body.horizon,
    )
    return {
        "served": ["/specops/social"],
        "missing": [],
        "scope": "investigation-scoped",
        "projection": projection_wire(projection),
    }
