"""Read-only Intelligence Silo contract shared by every domain consumer.

The feed carries typed entity/relation projections and immutable evidence references.
Raw source bodies never travel through this contract or the event bus.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class IntelligenceContractError(ValueError):
    """The supplied request or snapshot violates the shared feed contract."""


def _required(value: str, field: str) -> None:
    if not value or not value.strip():
        raise IntelligenceContractError(f"{field} must be non-empty")


def _aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise IntelligenceContractError(f"{field} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """Pointer to immutable evidence; deliberately contains no raw body."""

    tenant_id: str
    observation_id: str
    source_ref: str
    object_uri: str
    sha256: str
    recorded_at: datetime
    observed_at: datetime | None = None
    selector: str | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.tenant_id, "tenant_id"),
            (self.observation_id, "observation_id"),
            (self.source_ref, "source_ref"),
            (self.object_uri, "object_uri"),
        ):
            _required(value, name)
        if not self.object_uri.startswith("s3://"):
            raise IntelligenceContractError("object_uri must be an immutable s3:// reference")
        if re.fullmatch(r"[0-9a-f]{64}", self.sha256) is None:
            raise IntelligenceContractError("sha256 must be 64 lowercase hexadecimal characters")
        _aware(self.recorded_at, "recorded_at")
        if self.observed_at is not None:
            _aware(self.observed_at, "observed_at")


@dataclass(frozen=True, slots=True)
class IntelligenceEntity:
    """Evidence-backed entity projection for downstream domain analysis."""

    entity_id: str
    entity_type: str
    label: str
    evidence: tuple[EvidenceReference, ...]
    attributes: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        for value, name in (
            (self.entity_id, "entity_id"),
            (self.entity_type, "entity_type"),
            (self.label, "label"),
        ):
            _required(value, name)
        if not self.evidence:
            raise IntelligenceContractError("an admitted IntelligenceEntity requires evidence")
        keys = [key for key, _ in self.attributes]
        if len(keys) != len(set(keys)):
            raise IntelligenceContractError("entity attribute keys must be unique")


@dataclass(frozen=True, slots=True)
class IntelligenceRelation:
    """Evidence-backed relationship between two entities in one snapshot."""

    source_entity_id: str
    predicate: str
    target_entity_id: str
    evidence: tuple[EvidenceReference, ...]
    status: str = "unreviewed"
    confidence: float | None = None
    evidence_grade: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.source_entity_id, "source_entity_id"),
            (self.predicate, "predicate"),
            (self.target_entity_id, "target_entity_id"),
        ):
            _required(value, name)
        if self.source_entity_id == self.target_entity_id:
            raise IntelligenceContractError("self-relations must be modelled explicitly, not implied")
        if not self.evidence:
            raise IntelligenceContractError("an IntelligenceRelation requires evidence")
        _required(self.status, "status")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise IntelligenceContractError("confidence must be between 0 and 1")
        for value, name in ((self.valid_from, "valid_from"), (self.valid_to, "valid_to")):
            if value is not None:
                _aware(value, name)
        if self.valid_from is not None and self.valid_to is not None and self.valid_to < self.valid_from:
            raise IntelligenceContractError("valid_to precedes valid_from")


@dataclass(frozen=True, slots=True)
class IntelligenceSnapshot:
    """Immutable, tenant-scoped view over evidence; never the source of truth."""

    tenant_id: str
    snapshot_id: str
    subject_entity_id: str
    created_at: datetime
    entities: tuple[IntelligenceEntity, ...]
    relations: tuple[IntelligenceRelation, ...] = ()

    def __post_init__(self) -> None:
        for value, name in (
            (self.tenant_id, "tenant_id"),
            (self.snapshot_id, "snapshot_id"),
            (self.subject_entity_id, "subject_entity_id"),
        ):
            _required(value, name)
        _aware(self.created_at, "created_at")
        by_id = {entity.entity_id: entity for entity in self.entities}
        if len(by_id) != len(self.entities):
            raise IntelligenceContractError("snapshot entity ids must be unique")
        if self.subject_entity_id not in by_id:
            raise IntelligenceContractError("snapshot subject must exist in entities")
        for entity in self.entities:
            if any(ref.tenant_id != self.tenant_id for ref in entity.evidence):
                raise IntelligenceContractError("entity evidence crosses tenant boundary")
        for relation in self.relations:
            if relation.source_entity_id not in by_id or relation.target_entity_id not in by_id:
                raise IntelligenceContractError("relation endpoints must exist in the same snapshot")
            if any(ref.tenant_id != self.tenant_id for ref in relation.evidence):
                raise IntelligenceContractError("relation evidence crosses tenant boundary")


@dataclass(frozen=True, slots=True)
class IntelligenceQuery:
    """A purpose-bound request to read an existing intelligence projection."""

    tenant_id: str
    subject_ref: str
    purpose: str
    max_hops: int = 2
    as_of: datetime | None = None

    def __post_init__(self) -> None:
        _required(self.tenant_id, "tenant_id")
        _required(self.subject_ref, "subject_ref")
        _required(self.purpose, "purpose")
        if not 0 <= self.max_hops <= 8:
            raise IntelligenceContractError("max_hops must be between 0 and 8")
        if self.as_of is not None:
            _aware(self.as_of, "as_of")


class IntelligenceReadPort(Protocol):
    """Consumer-facing read port; implementations live only in the Intelligence Silo."""

    async def get_snapshot(self, query: IntelligenceQuery) -> IntelligenceSnapshot:
        """Return an evidence-backed snapshot or raise a typed not-found/policy error."""
        ...


__all__ = [
    "EvidenceReference",
    "IntelligenceContractError",
    "IntelligenceEntity",
    "IntelligenceQuery",
    "IntelligenceReadPort",
    "IntelligenceRelation",
    "IntelligenceSnapshot",
]
