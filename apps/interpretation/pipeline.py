"""Interpretation pipeline (T032-T034, T081, feature 005 US1, US3).

observation.id → parse → extract → normalize → aggregate → verified candidates →
canonical knowledge Statements (domain model). Each stage is a pure transform;
nothing mutates the observation. The aggregated candidates are re-encoded into
the canonical ``Statement`` shape (FR-004) carrying domain ``Property`` values,
and — when a producer is supplied — emitted as ``statement.created`` (refs only,
I-5) so projections rebuild from durable events (I-12). Every parsed observation
also gets an immutable evidence manifest chain (finding → evidence →
observation → raw sha256, feature 005 US3), emitted as
``evidence.manifest_created`` alongside the statements.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field

from domain.entity import Entity
from domain.property import Property
from domain.schema import DEFAULT_REGISTRY
from domain.statement import Statement, build_statement, statement_envelope
from events.topics import topic_for

from aggregation.candidates import Candidate, CandidateAggregator
from evidence.manifest import EvidenceManifest, Finding, build_manifest, sha256_of_bytes
from extractors.registry import ExtractorRegistry, Mention
from normalization.canonical import CanonicalMention, Normalizer
from parsers.registry import ParserRegistry


@dataclass
class InterpretationResult:
    observation_id: str
    candidates: list[Candidate] = field(default_factory=list)
    statements: list[Statement] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    manifests: list[EvidenceManifest] = field(default_factory=list)
    mention_count: int = 0
    source_id: str = field(default_factory=lambda: "INT-" + uuid.uuid4().hex[:12])
    completed: bool = False

    def mark_complete(self) -> None:
        self.completed = True


def _evidence_id(observation_id: str) -> str:
    """Deterministic evidence id per observation (same obs → same evidence ref)."""
    digest = hashlib.sha256(observation_id.encode()).hexdigest()[:16]
    return "EVD-" + digest


def _candidate_entity_id(kind: str, key: str) -> str:
    """Stable entity id per canonical indicator (kind:value)."""
    digest = hashlib.sha256(f"{kind}:{key}".encode()).hexdigest()[:24]
    return "E-" + digest


# Candidate kinds → knowledge schema + property. Kinds without a registered
# schema stay schema-less (""); schema attribution happens at resolution time.
_SCHEMA_BY_KIND: dict[str, tuple[str, str]] = {
    "email": ("Email", "address"),
    "crypto_address": ("CryptoAddress", "publicKey"),
}


class InterpretationPipeline:
    def __init__(
        self,
        parsers: ParserRegistry | None = None,
        extractors: ExtractorRegistry | None = None,
        normalizer: Normalizer | None = None,
        aggregator: CandidateAggregator | None = None,
    ) -> None:
        self._parsers = parsers or ParserRegistry()
        self._extractors = extractors or ExtractorRegistry()
        self._normalizer = normalizer or Normalizer()
        self._aggregator = aggregator or CandidateAggregator()

    def run(
        self,
        observation_id: str,
        body: bytes,
        content_type: str | None = None,
        *,
        dataset_id: str = "",
        producer=None,
        extraction_version: str = "interpretation-pipeline-v1",
        tenant_id: str = "default-tenant",
    ) -> InterpretationResult:
        result = InterpretationResult(observation_id=observation_id)

        segments = self._parsers.parse(body, content_type)
        for seg in segments:
            mentions = self._extractors.extract(seg.text, source_id=result.source_id)
            result.mention_count += len(mentions)
            for m in mentions:
                canon = self._normalize(m)
                self._aggregator.add(canon, source_id=result.source_id, offset=seg.offset)

        result.candidates = self._aggregator.all()
        raw_sha256 = sha256_of_bytes(body)
        evidence_id = _evidence_id(observation_id)
        for candidate in result.candidates:
            stmt, entity = self._encode_candidate(
                candidate,
                dataset_id=dataset_id,
                producer=producer,
                extraction_version=extraction_version,
                tenant_id=tenant_id,
            )
            if stmt is not None:
                result.statements.append(stmt)
            if entity is not None:
                result.entities.append(entity)
            result.manifests.append(
                build_manifest(
                    finding=Finding(kind=candidate.kind, value=candidate.value),
                    evidence_id=evidence_id,
                    observation_id=observation_id,
                    raw_sha256=raw_sha256,
                    tenant_id=tenant_id,
                    producer=producer,
                )
            )
        result.mark_complete()
        return result

    def _encode_candidate(
        self,
        candidate: Candidate,
        *,
        dataset_id: str,
        producer,
        extraction_version: str,
        tenant_id: str,
    ) -> tuple[Statement | None, Entity | None]:
        """Encode a candidate into the canonical Statement (+ Entity when schematised)."""
        mapped = _SCHEMA_BY_KIND.get(candidate.kind)
        schema_name, prop_name = mapped if mapped else ("", "value")
        entity_id = _candidate_entity_id(candidate.kind, candidate.key)
        property = Property(name=prop_name, type="text", value=candidate.value)

        entity: Entity | None = None
        if schema_name:
            entity = Entity.new(
                schema_name,
                registry=DEFAULT_REGISTRY,
                properties={prop_name: [property]},
                dataset_id=dataset_id,
                entities_id=entity_id,
            )
        if not dataset_id:
            # FR-001: without a dataset boundary no durable statement exists.
            return None, entity
        if entity is not None:
            statement = build_statement(
                schema_name=schema_name,
                entity_id=entity_id,
                properties=[property],
                dataset_id=dataset_id,
                original_value=candidate.value,
                extraction_version=extraction_version,
                registry=DEFAULT_REGISTRY,
                provenance={"producer": "interpretation-pipeline", "tenant_id": tenant_id},
                tenant_id=tenant_id,
                producer=producer,
            )
        else:
            statement = Statement(
                entity_id=entity_id,
                schema_name="",
                properties=[property],
                dataset_id=dataset_id,
                original_value=candidate.value,
                extraction_version=extraction_version,
                provenance={"producer": "interpretation-pipeline", "tenant_id": tenant_id},
                tenant_id=tenant_id,
            )
            if producer is not None:
                envelope = statement_envelope(statement)
                producer.produce(
                    topic_for("statement.created"),
                    envelope,
                    key=statement.statement_id,
                )
        return statement, entity

    def _normalize(self, mention: Mention) -> CanonicalMention:
        return self._normalizer.normalize(mention)