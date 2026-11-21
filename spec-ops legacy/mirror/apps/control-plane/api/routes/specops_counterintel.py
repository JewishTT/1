"""Counterintelligence subject API for the CI/SpecOps department (027, US4, T035).

Returns a subject and its tracked invariants, each carrying its evidence refs. An
invariant without evidence is served with an empty `evidence_refs` — the surface
renders it as unsupported (FR-008). Investigation-scoped (§VI): a subject belongs
to the case in hand, so the envelope says so.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from api.auth import TenantContext, resolve_tenant

try:
    from specops.counterintel import REGISTRY as SUBJECTS
    from specops.counterintel import to_wire as subject_wire
except Exception:  # pragma: no cover
    SUBJECTS = None  # type: ignore[assignment]
    subject_wire = None  # type: ignore[assignment]

router = APIRouter(prefix="/specops/counterintel", tags=["specops-counterintel"])


@router.get("/subjects/{subject_id}")
async def get_subject(subject_id: str, ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None) -> dict:
    if SUBJECTS is None or subject_wire is None:  # pragma: no cover
        raise HTTPException(status_code=503, detail="specops counterintel unavailable")
    subject = SUBJECTS.get(subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="subject not found")
    return {
        "served": ["/api/v1/specops/counterintel/subjects/{subject_id}"],
        "missing": [
            "CognitiveAttack / DIMA-OntoToolkit / io-coordinated-replies / IO-detecting operators are not connected; the current subject registry is a seeded demo fixture."
        ],
        "scope": "fixture-only",
        "subject": subject_wire(subject),
    }
