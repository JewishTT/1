from datetime import datetime, timezone
from decimal import Decimal

import pytest

from apps.economics.domain import EconomicDomainError, FinancialFlow, aggregate_flows, subjects_from_snapshot
from shared.contracts.intelligence_feed import EvidenceReference, IntelligenceEntity, IntelligenceSnapshot


NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)


def ref(observation_id: str) -> EvidenceReference:
    return EvidenceReference(
        tenant_id="tenant-a",
        observation_id=observation_id,
        source_ref="source:filing",
        object_uri=f"s3://knowledge/raw/tenant-a/2026/11/{observation_id}",
        sha256="b" * 64,
        observed_at=NOW,
    )


def snapshot() -> IntelligenceSnapshot:
    return IntelligenceSnapshot(
        tenant_id="tenant-a",
        snapshot_id="snapshot-1",
        subject_entity_id="company-a",
        created_at=NOW,
        entities=(
            IntelligenceEntity("company-a", "company", "Company A", (ref("obs-a"),)),
            IntelligenceEntity("company-b", "company", "Company B", (ref("obs-b"),)),
        ),
    )


def flow(flow_id: str, payer: str, payee: str, amount: str, evidence_id: str) -> FinancialFlow:
    return FinancialFlow(
        flow_id=flow_id,
        tenant_id="tenant-a",
        source_snapshot_id="snapshot-1",
        payer_entity_id=payer,
        payee_entity_id=payee,
        amount=Decimal(amount),
        currency="USD",
        occurred_at=NOW,
        evidence=(ref(evidence_id),),
    )


def test_economic_subjects_are_derived_from_intelligence() -> None:
    subjects = subjects_from_snapshot(snapshot())
    assert [subject.entity_id for subject in subjects] == ["company-a", "company-b"]
    assert all(subject.source_snapshot_id == "snapshot-1" for subject in subjects)


def test_flow_aggregation_is_per_entity_and_currency() -> None:
    result = aggregate_flows(
        snapshot(),
        (
            flow("f-1", "company-a", "company-b", "120.00", "obs-1"),
            flow("f-2", "company-b", "company-a", "30.00", "obs-2"),
        ),
    )
    by_entity = {item.entity_id: item for item in result}
    assert by_entity["company-a"].inflow == Decimal("30.00")
    assert by_entity["company-a"].outflow == Decimal("120.00")
    assert by_entity["company-a"].net_flow == Decimal("-90.00")
    assert by_entity["company-b"].net_flow == Decimal("90.00")


def test_flows_cannot_escape_snapshot_scope() -> None:
    invalid = flow("f-3", "company-a", "not-in-snapshot", "1", "obs-3")
    with pytest.raises(EconomicDomainError, match="endpoint"):
        aggregate_flows(snapshot(), (invalid,))
