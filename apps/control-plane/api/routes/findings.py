"""Finding overview API (T053, US2, FR-032).

Why detected, structural/semantic evidence, supporting graph region,
assertions, observations and raw sources. Lineage drill-down walks
finding -> feature -> graph/assertion -> evidence -> observation -> source.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from api.auth import TenantContext, resolve_tenant
from contracts.evidence_span import (
    CharSpan,
    EvidenceSpanRef,
    JsonPathSpan,
    SourceLocator,
)
from services.catalog import Catalog, FindingRecord

router = APIRouter(prefix="/findings", tags=["findings"])


def _digest(seed: str) -> str:
    """A full-length content address; the contract rejects anything else."""
    return "sha256:" + (seed * 64)[:64]


REPORT_LOCATOR = SourceLocator(uri="http://fixtures.local/report.html")
LEDGER_LOCATOR = SourceLocator(uri="http://fixtures.local/ledger.html")

#: The typed spans that ground FND-5001. Serialised through the contract rather than
#: hand-written dicts, so the fixture cannot invent a shape the reader refuses.
FND_5001_EVIDENCE = (
    EvidenceSpanRef(
        observation_ref="OBS-1001",
        blob_digest=_digest("a"),
        selector=CharSpan(start=812, end=869, encoding="utf-8", units="document_char"),
        source_locator=REPORT_LOCATOR,
        selector_semantics_version="char_span/1",
    ),
    EvidenceSpanRef(
        observation_ref="OBS-1002",
        blob_digest=_digest("b"),
        selector=JsonPathSpan(pointer="/transfers/17/amount"),
        source_locator=LEDGER_LOCATOR,
        selector_semantics_version="json_path/1",
    ),
)

_observations = {
    "OBS-1001": {
        "observation_id": "OBS-1001",
        "uri": "http://fixtures.local/report.html",
        "content_hash": _digest("a"),
    },
    "OBS-1002": {
        "observation_id": "OBS-1002",
        "uri": "http://fixtures.local/ledger.html",
        "content_hash": _digest("b"),
    },
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
        evidence_chain=[span.as_dict() for span in FND_5001_EVIDENCE],
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