"""Assertion extractor + EvidenceLink builder (T037, FR-015/FR-016).

Builds Assertion from observation mentions: an assertion is a subject →
relation → object claim with evidence refs and observed/valid time. Tracks
`publication_count` (distinct docs) distinctly from `independent_support`
(filled by T087). The assertion always carries evidence_refs; original
observation refs are preserved.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from domain.statement import Statement  # canonical knowledge model (FR-001)
from events.kafka import build_envelope
from events.topics import topic_for

_EMISSION_PRODUCER = "admission.assertion-extractor"
_EMISSION_VERSION = "0.1.0"


@dataclass
class EvidenceRef:
    observation_id: str
    mention_id: str | None = None
    source_id: str | None = None

    @property
    def document_id(self) -> str:
        return self.observation_id


@dataclass
class EvidenceLink:
    link_id: str = field(default_factory=lambda: "EV-" + uuid.uuid4().hex[:12])
    assertion_id: str | None = None
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    publication_count: int = 0
    independent_support: float = 0.0
    independent_evidence_chains: list[tuple[str, str]] = field(default_factory=list)
    independent_source_count: int = 0


@dataclass
class ExtractedAssertion:
    assertion_id: str = field(default_factory=lambda: "A-" + uuid.uuid4().hex[:12])
    subject_candidate_id: str | None = None
    relation: str = ""
    object_value: str = ""
    evidence: EvidenceLink = field(default_factory=EvidenceLink)
    observed_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    claimed: bool = True  # I-3: assertion is a claim, never truth
    statement: Statement | None = None

    def publication_count(self) -> int:
        return len({e.document_id for e in self.evidence.evidence_refs})


class AssertionExtractor:
    """Builds ExtractedAssertion and its EvidenceLink from observation evidence."""

    def extract(
        self,
        *,
        subject_candidate_id: str,
        relation: str,
        object_value: str,
        refs: list[EvidenceRef],
        dataset_id: str = "",
        extraction_version: str = "extractor-v1",
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
        tenant_id: str = "default-tenant",
        statement_id: str | None = None,
        producer=None,
    ) -> ExtractedAssertion:
        link = EvidenceLink(assertion_id=None, evidence_refs=list(refs))
        link.publication_count = len({e.document_id for e in refs})
        observed_at = datetime.now(UTC)
        assertion_id = "A-" + uuid.uuid4().hex[:12]
        assertion = ExtractedAssertion(
            assertion_id=assertion_id,
            subject_candidate_id=subject_candidate_id,
            relation=relation,
            object_value=object_value,
            evidence=link,
            observed_at=observed_at,
            valid_from=valid_from,
            valid_to=valid_to,
        )
        link.assertion_id = assertion_id
        # FR-001: attach the canonical knowledge Statement carrying dataset
        # provenance. Schema attribution happens at resolution time, so the
        # statement is created schema-agnostic (schema_name="") here.
        assertion.statement = self._build_statement(
            subject_candidate_id=subject_candidate_id,
            observed_at=observed_at,
            dataset_id=dataset_id,
            extraction_version=extraction_version,
            object_value=object_value,
            valid_from=valid_from,
            valid_to=valid_to,
            tenant_id=tenant_id,
            statement_id=statement_id,
        )
        if producer is not None and assertion.statement is not None:
            # statement.created envelope — projections rebuild statements from
            # durable events (I-12). Payload carries refs/fields, not blobs.
            envelope = build_envelope(
                event_type="statement.created",
                event_version="1.0",
                producer=_EMISSION_PRODUCER,
                producer_version=_EMISSION_VERSION,
                payload=json.dumps(assertion.statement.to_dict(), default=str).encode("utf-8"),
                entity_id=subject_candidate_id,
                event_id=f"evt-{assertion.statement.statement_id}",
            )
            producer.produce(
                topic_for("statement.created"),
                envelope,
                key=assertion.statement.statement_id,
            )
        return assertion

    def _build_statement(
        self,
        *,
        subject_candidate_id: str,
        observed_at: datetime,
        dataset_id: str,
        extraction_version: str,
        object_value: str,
        valid_from: datetime | None,
        valid_to: datetime | None,
        tenant_id: str,
        statement_id: str | None,
    ) -> Statement | None:
        # FR-001 provenance is mandatory: without a dataset boundary there is no
        # durable statement record (observations stay claim-only, I-3).
        if not dataset_id or not object_value or not extraction_version:
            return None
        return Statement(
            statement_id=statement_id or "ST-" + uuid.uuid4().hex[:12],
            entity_id=subject_candidate_id,
            schema_name="",
            dataset_id=dataset_id,
            original_value=object_value,
            extraction_version=extraction_version,
            first_seen=observed_at,
            last_seen=observed_at,
            valid_from=valid_from,
            valid_until=valid_to,
            provenance={"producer": "assertion-extractor", "tenant_id": tenant_id},
            tenant_id=tenant_id,
        )