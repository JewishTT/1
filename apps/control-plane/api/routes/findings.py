"""Finding overview API (T053, US2, FR-032).

Why detected, structural/semantic evidence, supporting graph region,
assertions, observations and raw sources. Lineage drill-down walks
finding -> feature -> graph/assertion -> evidence -> observation -> source.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from api.auth import TenantContext, resolve_tenant
from services.catalog import Catalog, FindingRecord

router = APIRouter(prefix="/findings", tags=["findings"])

_observations = {
    "OBS-1001": {"observation_id": "OBS-1001", "uri": "http://fixtures.local/report.html", "content_hash": "sha256:aa"},
    "OBS-1002": {"observation_id": "OBS-1002", "uri": "http://fixtures.local/ledger.html", "content_hash": "sha256:bb"},
}
_catalog = Catalog(observations=_observations)
_catalog.put_finding(
    FindingRecord(
        finding_id="FND-5001",
        why_detected="persistent topological loop under account Yard coincides with transfer velocity spike",
        structural_evidence=[{"feature_id": "FEAT-42", "kind": "tda_loop", "persistence": 2.3}],
        semantic_evidence=[{"kind": "named_entity", "value": "Yard"}],
        supporting_graph_region={"subgraph": "Yard cluster", "diameter": 3},
        supporting_assertions=["ASR-9001"],
        observations=["OBS-1001", "OBS-1002"],
        sources=["http://fixtures.local/report.html", "http://fixtures.local/ledger.html"],
        status="open",
    )
)


@router.get("")
async def list_findings(ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None) -> dict:
    return {"findings": [_catalog.finding(fid) | {"tenant_id": ctx.tenant_id} for fid in _catalog.finding_ids() if _catalog.finding(fid) is not None]}


@router.get("/{finding_id}")
async def get_finding(
    finding_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    view = _catalog.finding(finding_id)
    if view is None:
        raise HTTPException(status_code=404, detail="finding not found")
    view["tenant_id"] = ctx.tenant_id
    return view


@router.get("/{finding_id}/lineage")
async def finding_lineage(
    finding_id: str,
    ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None,
) -> dict:
    if _catalog.finding(finding_id) is None:
        raise HTTPException(status_code=404, detail="finding not found")
    chain = _catalog.lineage(finding_id)
    if not chain:
        raise HTTPException(status_code=404, detail="no lineage for finding")
    return {"finding_id": finding_id, "chain": chain, "tenant_id": ctx.tenant_id}