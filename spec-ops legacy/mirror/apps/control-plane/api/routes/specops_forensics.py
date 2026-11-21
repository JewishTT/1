"""APT forensics API for the CI/SpecOps department (027, US6, T046).

For a completed emulation run, returns the expected-vs-actual telemetry comparison,
the detection gaps, and the derived ATT&CK coverage. Coverage is computed from the
comparison — never a separately served number — so it cannot disagree with the gaps.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from api.auth import TenantContext, resolve_tenant

try:
    from specops.emulation import REGISTRY as EMULATION
    from specops.forensics import build as build_forensics
    from specops.forensics import to_wire as forensics_wire
except Exception:  # pragma: no cover
    EMULATION = None  # type: ignore[assignment]
    build_forensics = None  # type: ignore[assignment]
    forensics_wire = None  # type: ignore[assignment]

router = APIRouter(prefix="/specops/forensics", tags=["specops-forensics"])


@router.get("/operations/{operation_id}")
async def get_forensics(operation_id: str, ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None) -> dict:
    if EMULATION is None or build_forensics is None:  # pragma: no cover
        raise HTTPException(status_code=503, detail="specops forensics unavailable")
    op = EMULATION.get(operation_id)
    if op is None:
        raise HTTPException(status_code=404, detail="operation not found")
    row = build_forensics(op)
    return {
        "served": ["/specops/forensics"],
        "missing": [],
        "scope": "tenant-wide",
        "forensics": forensics_wire(row),
        "coverage": {"techniques": row.coverage},
    }
