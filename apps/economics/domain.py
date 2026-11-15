"""Economic domain model over Intelligence Silo snapshots.

This module analyses economic subjects and evidenced financial flows. It does not
discover targets, crawl sources, or own a second recon/acquisition pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable
import re

from shared.contracts.intelligence_feed import (
    EvidenceReference,
    IntelligenceSnapshot,
)


class EconomicDomainError(ValueError):
    """An economic record is inconsistent with its tenant or evidence context."""


@dataclass(frozen=True, slots=True)
class EconomicSubject:
    entity_id: str
    kind: str
    label: str
    source_snapshot_id: str
    evidence: tuple[EvidenceReference, ...]

    @classmethod
    def from_intelligence(cls, snapshot: IntelligenceSnapshot, entity_id: str) -> "EconomicSubject":
        entity = next((item for item in snapshot.entities if item.entity_id == entity_id), None)
        if entity is None:
            raise EconomicDomainError(
                f"entity {entity_id!r} is absent from the Intelligence snapshot"
            )
        return cls(
            entity_id=entity.entity_id,
            kind=entity.entity_type,
            label=entity.label,
            source_snapshot_id=snapshot.snapshot_id,
            evidence=entity.evidence,
        )


@dataclass(frozen=True, slots=True)
class FinancialFlow:
    """A financial movement between two evidenced economic subjects.

    Amount may be unknown; unknown amounts are retained but excluded from numeric
    aggregation. A flow with no evidence is never admitted to this domain model.
    """

    flow_id: str
    tenant_id: str
    source_snapshot_id: str
    payer_entity_id: str
    payee_entity_id: str
    amount: Decimal | None
    currency: str | None
    occurred_at: datetime
    evidence: tuple[EvidenceReference, ...]

    def __post_init__(self) -> None:
        for value, field in (
            (self.flow_id, "flow_id"),
            (self.tenant_id, "tenant_id"),
            (self.source_snapshot_id, "source_snapshot_id"),
            (self.payer_entity_id, "payer_entity_id"),
            (self.payee_entity_id, "payee_entity_id"),
        ):
            if not value or not value.strip():
                raise EconomicDomainError(f"{field} must be non-empty")
        if self.payer_entity_id == self.payee_entity_id:
            raise EconomicDomainError("payer and payee must be distinct entities")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise EconomicDomainError("occurred_at must be timezone-aware")
        if not self.evidence:
            raise EconomicDomainError("financial flows require evidence references")
        if any(ref.tenant_id != self.tenant_id for ref in self.evidence):
            raise EconomicDomainError("financial-flow evidence crosses tenant boundary")
        if self.amount is not None:
            if not self.amount.is_finite() or self.amount < Decimal("0"):
                raise EconomicDomainError("amount must be finite and non-negative")
        if self.currency is not None and re.fullmatch(r"[A-Z]{3}", self.currency) is None:
            raise EconomicDomainError("currency must be a three-letter uppercase code")


@dataclass(frozen=True, slots=True)
class FinancialFlowAggregate:
    tenant_id: str
    source_snapshot_id: str
    entity_id: str
    currency: str
    inflow: Decimal
    outflow: Decimal
    net_flow: Decimal
    flow_count: int
    evidence: tuple[EvidenceReference, ...]


def subjects_from_snapshot(snapshot: IntelligenceSnapshot) -> tuple[EconomicSubject, ...]:
    """Project known Intelligence entities into the Economics domain, preserving evidence."""
    return tuple(
        EconomicSubject.from_intelligence(snapshot, entity.entity_id)
        for entity in snapshot.entities
    )


def aggregate_flows(
    snapshot: IntelligenceSnapshot,
    flows: Iterable[FinancialFlow],
) -> tuple[FinancialFlowAggregate, ...]:
    """Aggregate evidenced flows per entity/currency without mixing tenants or snapshots.

    Flows whose amount or currency is unknown remain in the source ledger but are
    not included in numeric totals. No FX conversion or inferred valuation occurs.
    """
    known_entities = {entity.entity_id for entity in snapshot.entities}
    totals: dict[tuple[str, str], dict[str, object]] = {}

    for flow in flows:
        if flow.tenant_id != snapshot.tenant_id:
            raise EconomicDomainError("flow belongs to another tenant")
        if flow.source_snapshot_id != snapshot.snapshot_id:
            raise EconomicDomainError("flow was derived from a different Intelligence snapshot")
        if flow.payer_entity_id not in known_entities or flow.payee_entity_id not in known_entities:
            raise EconomicDomainError("flow endpoint is absent from the Intelligence snapshot")
        if flow.amount is None or flow.currency is None:
            continue

        for entity_id, direction in (
            (flow.payer_entity_id, "outflow"),
            (flow.payee_entity_id, "inflow"),
        ):
            key = (entity_id, flow.currency)
            entry = totals.setdefault(key, {
                "inflow": Decimal("0"),
                "outflow": Decimal("0"),
                "flow_count": 0,
                "evidence": [],
            })
            entry[direction] = entry[direction] + flow.amount
            entry["flow_count"] = int(entry["flow_count"]) + 1
            entry["evidence"].extend(flow.evidence)

    result = []
    for (entity_id, currency), values in sorted(totals.items()):
        evidence_by_id = {
            ref.observation_id: ref for ref in values["evidence"]
        }
        inflow = values["inflow"]
        outflow = values["outflow"]
        result.append(FinancialFlowAggregate(
            tenant_id=snapshot.tenant_id,
            source_snapshot_id=snapshot.snapshot_id,
            entity_id=entity_id,
            currency=currency,
            inflow=inflow,
            outflow=outflow,
            net_flow=inflow - outflow,
            flow_count=int(values["flow_count"]),
            evidence=tuple(evidence_by_id[key] for key in sorted(evidence_by_id)),
        ))
    return tuple(result)
