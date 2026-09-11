"""Claim query / list (T096, US1).

Reads are projections of the event-replayable store: ``list_claims`` filters
the store's ``claims`` collection (status in the payload is the last-applied
status, Supersedes semantics), so queries never mutate state.
"""

from __future__ import annotations

from typing import Any

from claims.model import (
    ClaimStatus,
    CredenceDistribution,
    EvidenceDirection,
    EvidenceLink,
    ScientificClaim,
)
from store import ScienceStore


def list_claims(
    store: ScienceStore,
    *,
    project_id: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """List claim projections, optionally filtered by project and/or status."""
    records = store.all("claims")
    if project_id is not None:
        records = [r for r in records if r.get("project_id") == project_id]
    if status is not None:
        records = [r for r in records if r.get("status") == status]
    return sorted(records, key=lambda r: r.get("_updated_at", ""))


def get_claim(store: ScienceStore, claim_id: str) -> dict[str, Any] | None:
    return store.get("claims", claim_id)


def load_claim(record: dict[str, Any]) -> ScientificClaim:
    """Rebuild a ScientificClaim value object from its projected record."""
    dist = record.get("distribution", {})
    distribution = CredenceDistribution(
        states=list(dist.get("states", [])),
        labels=list(dist.get("labels", [])),
        probs=[float(p) for p in dist.get("probs", [])],
        method=str(dist.get("method", "")),
        calibration_ref=dist.get("calibration_ref"),
    )
    provenance = [
        EvidenceLink(
            link_id=str(ref["link_id"]),
            observation_id=str(ref["observation_id"]),
            raw_sha256=str(ref["raw_sha256"]),
            direction=EvidenceDirection(ref["direction"]),
            weight=0.0,
        )
        for ref in record.get("provenance_refs", [])
    ]
    return ScientificClaim(
        claim_id=str(record["claim_id"]),
        project_id=str(record.get("project_id", "")),
        statement=str(record.get("statement", "")),
        distribution=distribution,
        model_id=str(record.get("model_id", distribution.method)),
        status=ClaimStatus(record.get("status", "draft")),
        provenance=provenance,
        producer_run=record.get("producer_run"),
    )