"""PostgreSQL persistence for relation hypotheses before claim admission.

This store writes relation_candidate, evidence_context, and semantic_regime only.
It has no method that writes relation_claim: extraction is not admission.
"""
from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.schema import EvidenceContext as EvidenceContextRow
from db.schema import RelationCandidateRow
from db.schema import SemanticRegimeRow
from domain.evidence_context import EvidenceContext
from domain.relation_candidate import RelationCandidate
from semantic.regime import SemanticRegime
from semantic.regime_store import RegimeRecord


class RelationCandidatePersistenceError(RuntimeError):
    """A candidate reference or content-addressed row conflicts with durable state."""


def _json_value(value: Any) -> Any:
    """Convert frozen domain values to JSON-safe, replay-stable material."""
    if isinstance(value, Enum):
        return _json_value(value.value)
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _json_value(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        return [_json_value(item) for item in sorted(value, key=lambda item: str(item))]
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, str | bool | int | float):
        return value
    return str(value)


def candidate_row_values(candidate: RelationCandidate) -> dict[str, Any]:
    """Build the persisted row without making an admission decision."""
    addressed = candidate.with_id()
    hypothesis = addressed.predicate_hypothesis
    if hypothesis is None:
        raise RelationCandidatePersistenceError("candidate has no predicate hypothesis")
    payload = _json_value(addressed)
    if not isinstance(payload, dict):
        raise RelationCandidatePersistenceError("candidate payload did not serialize to an object")
    payload["content_hash"] = addressed.content_hash
    return {
        "candidate_id": addressed.candidate_id,
        "logical_candidate_id": addressed.logical_candidate_id,
        "tenant_id": addressed.tenant_id,
        "subject_mention_ref": addressed.subject_mention_ref,
        "object_mention_ref": addressed.object_mention_ref,
        "arity_mode": str(addressed.arity_mode),
        "relation_ref": str(addressed.relation_ref) if addressed.relation_ref is not None else None,
        "relation_type": addressed.relation_type,
        "relation_surface": addressed.relation_surface or hypothesis.predicate_raw.label,
        "predicate_hypothesis": hypothesis.content_key(),
        "predicate_state": str(hypothesis.resolution_state),
        "context_ref": addressed.context_ref,
        "semantic_regime_ref": addressed.semantic_regime_ref,
        "candidate_status": str(addressed.candidate_status),
        "extraction_method": str(addressed.extraction_method),
        "extractor_version": addressed.extractor_version,
        "extraction_rule_id": addressed.extraction_rule_id,
        "investigation_id": addressed.investigation_id,
        "recorded_by": addressed.recorded_by,
        "observation_refs": list(addressed.observation_refs),
        "evidence_refs": list(addressed.evidence_refs),
        "trigger_span": _json_value(addressed.trigger_span) if addressed.trigger_span is not None else None,
        "supporting_spans": _json_value(addressed.supporting_spans),
        "temporal_hypothesis": _json_value(addressed.temporal_hypothesis),
        "role_assignments": _json_value(addressed.role_assignments),
        "observed_at": addressed.observed_at,
        "candidate_payload": payload,
    }


def _context_row_values(frame: EvidenceContext) -> dict[str, Any]:
    return {
        "context_id": frame.context_id,
        "tenant_id": frame.tenant_id,
        "investigation_id": frame.investigation_id,
        "entity_anchor": frame.entity_anchor,
        "observation_id": frame.observation_id,
        "source_id": frame.source_id,
        "document_id": frame.document_id,
        "segment_id": frame.segment_id,
        "subject_candidate_ids": list(frame.subject_candidate_ids),
        "object_candidate_ids": list(frame.object_candidate_ids),
        "observed_at": frame.observed_at,
        "published_at": frame.published_at,
        "valid_from": frame.valid_from,
        "valid_to": frame.valid_to,
        "source_family": frame.source_family,
        "independence_group": frame.independence_group,
        "language": frame.language,
        "location_context": frame.location_context,
        "extraction_version": frame.extraction_version,
        "normalization_version": frame.normalization_version,
        "ontology_version": frame.ontology_version,
        "completeness": str(frame.completeness),
        "trust_state": str(frame.trust_state),
        "policy_snapshot_ref": frame.policy_snapshot_ref,
        "parent_context_id": frame.parent_context_id,
        "frame_fingerprint": frame.frame_fingerprint,
    }


def _regime_row_values(regime: SemanticRegime) -> dict[str, Any]:
    record = RegimeRecord.from_regime(regime)
    return {
        "regime_id": record.regime_id,
        "tenant_id": record.tenant_id,
        "context_ref": record.context_ref,
        "profile_ref": record.profile_ref,
        "profile_version": record.profile_version,
        "ontology_version": record.ontology_version,
        "mapping_set_id": record.mapping_set_id,
        "mapping_set_version": record.mapping_set_version,
        "validation_profile": record.validation_profile,
        "policy_snapshot_ref": record.policy_snapshot_ref,
        "operator_ref": record.operator_ref,
        "localization": record.localization,
        "language": record.language,
        "temporal_frame_ref": record.temporal_frame_ref,
        "supersedes": record.supersedes,
        "commitment": record.commitment,
        "note": record.note,
        "instruments": list(record.instruments),
        "recorded_at": record.recorded_at,
        "record_fingerprint": record.record_fingerprint,
    }


class SqlRelationCandidateStore:
    """Tenant-scoped PostgreSQL writer for immutable relation candidate revisions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def write(
        self,
        candidate: RelationCandidate,
        frame: EvidenceContext,
        regime: SemanticRegime,
        *,
        source_reading: Mapping[str, Any] | None = None,
    ) -> str:
        candidate = candidate.with_id()
        if candidate.tenant_id != frame.tenant_id or candidate.tenant_id != regime.tenant_id:
            raise RelationCandidatePersistenceError("candidate, context and regime tenants disagree")
        if candidate.context_ref != frame.context_id:
            raise RelationCandidatePersistenceError("candidate context_ref does not match its frame")
        if candidate.semantic_regime_ref != regime.regime_id:
            raise RelationCandidatePersistenceError("candidate regime ref does not match its regime")
        if frame.observation_id and frame.observation_id not in candidate.observation_refs:
            raise RelationCandidatePersistenceError("candidate does not reference its frame observation")

        context_values = _context_row_values(frame)
        await self._session.execute(
            pg_insert(EvidenceContextRow).values(**context_values).on_conflict_do_nothing()
        )
        context_result = await self._session.execute(
            select(EvidenceContextRow).where(
                EvidenceContextRow.tenant_id == frame.tenant_id,
                EvidenceContextRow.context_id == frame.context_id,
            )
        )
        stored_context = context_result.scalar_one_or_none()
        if stored_context is None or stored_context.frame_fingerprint != frame.frame_fingerprint:
            raise RelationCandidatePersistenceError(
                f"content-addressed context {frame.context_id} conflicts with stored content"
            )

        regime_values = _regime_row_values(regime)
        await self._session.execute(
            pg_insert(SemanticRegimeRow).values(**regime_values).on_conflict_do_nothing()
        )
        regime_result = await self._session.execute(
            select(SemanticRegimeRow).where(
                SemanticRegimeRow.tenant_id == regime.tenant_id,
                SemanticRegimeRow.regime_id == regime.regime_id,
            )
        )
        stored_regime = regime_result.scalar_one_or_none()
        if stored_regime is None or stored_regime.record_fingerprint != regime_values["record_fingerprint"]:
            raise RelationCandidatePersistenceError(
                f"content-addressed regime {regime.regime_id} conflicts with stored content"
            )

        values = candidate_row_values(candidate)
        if source_reading:
            values["candidate_payload"]["source_reading"] = _json_value(source_reading)
        await self._session.execute(
            pg_insert(RelationCandidateRow).values(**values).on_conflict_do_nothing()
        )
        stored = await self._session.execute(
            select(RelationCandidateRow).where(
                RelationCandidateRow.tenant_id == candidate.tenant_id,
                RelationCandidateRow.candidate_id == candidate.candidate_id,
            )
        )
        row = stored.scalar_one_or_none()
        if row is None:
            raise RelationCandidatePersistenceError(
                f"candidate {candidate.candidate_id} was not visible after its write"
            )
        if dict(row.candidate_payload or {}) != values["candidate_payload"]:
            raise RelationCandidatePersistenceError(
                f"candidate {candidate.candidate_id} already holds different content"
            )
        if row.context_ref != frame.context_id or row.semantic_regime_ref != regime.regime_id:
            raise RelationCandidatePersistenceError(
                f"candidate {candidate.candidate_id} points at a different context or regime"
            )
        return candidate.candidate_id
