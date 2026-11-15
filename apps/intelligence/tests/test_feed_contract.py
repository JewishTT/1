from datetime import datetime, timezone

import pytest

from shared.contracts.intelligence_feed import (
    EvidenceReference,
    IntelligenceContractError,
    IntelligenceEntity,
    IntelligenceQuery,
    IntelligenceRelation,
    IntelligenceSnapshot,
)


NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)


def evidence(tenant_id: str = "tenant-a", observation_id: str = "obs-1") -> EvidenceReference:
    return EvidenceReference(
        tenant_id=tenant_id,
        observation_id=observation_id,
        source_ref="source:public-registry",
        object_uri=f"s3://knowledge/raw/{tenant_id}/2026/11/{observation_id}",
        sha256="a" * 64,
        observed_at=NOW,
    )


def test_snapshot_is_tenant_scoped_and_keeps_evidence_references() -> None:
    ref = evidence()
    subject = IntelligenceEntity("company-1", "company", "Example Ltd", (ref,))
    counterparty = IntelligenceEntity("bank-1", "bank", "Example Bank", (ref,))
    relation = IntelligenceRelation("company-1", "banks_with", "bank-1", (ref,))

    snapshot = IntelligenceSnapshot(
        tenant_id="tenant-a",
        snapshot_id="snapshot-1",
        subject_entity_id="company-1",
        created_at=NOW,
        entities=(subject, counterparty),
        relations=(relation,),
    )

    assert snapshot.subject_entity_id == "company-1"
    assert snapshot.relations[0].evidence[0].observation_id == "obs-1"
    assert not hasattr(snapshot, "raw_body")


def test_snapshot_rejects_cross_tenant_evidence() -> None:
    subject = IntelligenceEntity("company-1", "company", "Example Ltd", (evidence("tenant-b"),))
    with pytest.raises(IntelligenceContractError, match="tenant boundary"):
        IntelligenceSnapshot(
            tenant_id="tenant-a",
            snapshot_id="snapshot-1",
            subject_entity_id="company-1",
            created_at=NOW,
            entities=(subject,),
        )


def test_query_bounds_recon_expansion_and_requires_purpose() -> None:
    with pytest.raises(IntelligenceContractError, match="max_hops"):
        IntelligenceQuery("tenant-a", "company-1", "economic_analysis", max_hops=9)
    with pytest.raises(IntelligenceContractError, match="purpose"):
        IntelligenceQuery("tenant-a", "company-1", " ")
