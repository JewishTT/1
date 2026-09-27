"""Postgres operational schema — base models + invariants (T012, T014).

Observation is immutable (I-1, I-5). Mention != Candidate != Entity (I-2).
Assertion != truth (I-3). Entity versions are monotonic (I-4, FR-016).
projection.failure never drops evidence (I-12).
"""

from __future__ import annotations

import enum
from datetime import datetime

# The closed vocabularies the 019 tables check, imported rather than written out. This is
# the opposite stance from ``db/migrations/versions/020_universal_relation_extraction.py``,
# and the difference is deliberate rather than inconsistent: *application* code should
# follow the value type, because when the value type gains a member the fresh-install path
# must gain the CHECK with it or the two install paths diverge. A *migration* must not
# import it, because a revision that reads a value type changes meaning when somebody edits
# that type, and a database that already ran the revision cannot be re-run. So the
# literals live in the migration and the references live here, and
# `tests/unit/test_migration_020_universal_relation.py` asserts the two agree - which is
# the only way a deliberate duplication stays honest.
from domain.predicate_hypothesis import PredicateResolutionState
from domain.relation_candidate import CandidateStatus
from domain.relation_identity import RelationArityMode
from domain.temporal_observation import TemporalAxis
from extractors.signals.signal import DirectionHypothesis, SignalKind
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    desc,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _in(column: str, values: object) -> str:
    """A closed-vocabulary membership test, rendered for a CHECK constraint.

    Takes the enum class rather than a list of strings so the CHECK cannot drift from the
    vocabulary: adding a member to the enum adds it here, which is the whole reason the
    import exists.
    """
    allowed = ", ".join(f"'{member.value}'" for member in values)  # type: ignore[attr-defined]
    return f"{column} IN ({allowed})"


class Base(DeclarativeBase):
    pass


class LifecycleState(str, enum.Enum):
    ASSERTED = "ASSERTED"
    SUPERSEDED = "SUPERSEDED"
    RETRACTED = "RETRACTED"
    CONTRADICTED = "CONTRADICTED"
    EXPIRED = "EXPIRED"


class CandidateResolutionState(str, enum.Enum):
    OPEN = "OPEN"
    MATCHED = "MATCHED"
    SUPERSEDED = "SUPERSEDED"
    REJECTED = "REJECTED"
    QUARANTINED = "QUARANTINED"


class EpistemicStatus(str, enum.Enum):
    PROVISIONAL = "PROVISIONAL"
    DEFERRED = "DEFERRED"
    QUARANTINED = "QUARANTINED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class AdmissionDecision(str, enum.Enum):
    ACCEPT_NEW = "ACCEPT_NEW"
    ACCEPT_EXISTING = "ACCEPT_EXISTING"
    DEFER = "DEFER"
    REJECT = "REJECT"
    QUARANTINE = "QUARANTINE"


class InvestigationState(str, enum.Enum):
    DRAFT = "DRAFT"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class TemporalPolicy(str, enum.Enum):
    SINGLE = "single"
    MULTI = "multi"
    INTERVAL = "interval"
    APPEND_ONLY = "append_only"
    SUPERSADABLE = "supersedable"
    CONTRADICTORY = "contradictory"


class CalibrationStatus(str, enum.Enum):
    UNCALIBRATED = "UNCALIBRATED"
    CALIBRATED = "CALIBRATED"


# --- Investigation / control plane ---


class Investigation(Base):
    __tablename__ = "investigations"

    investigation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    tenant_id: Mapped[str] = mapped_column(String(36))
    objective: Mapped[dict | None] = mapped_column(JSONB)
    seeds: Mapped[list | None] = mapped_column(JSONB)
    scope: Mapped[dict | None] = mapped_column(JSONB)
    policy_id: Mapped[str | None] = mapped_column(String(36))
    state: Mapped[InvestigationState] = mapped_column(
        Enum(InvestigationState), default=InvestigationState.DRAFT
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_investigations_tenant", "tenant_id"),
        Index("ix_investigations_state", "state"),
    )


class Source(Base):
    __tablename__ = "sources"

    source_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    investigation_id: Mapped[str | None] = mapped_column(String(36))
    uri: Mapped[str] = mapped_column(Text)
    source_class: Mapped[str] = mapped_column(String(32))
    capabilities: Mapped[dict | None] = mapped_column(JSONB)
    quality_profile: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_sources_tenant", "tenant_id"),)


class Policy(Base):
    __tablename__ = "policies"

    policy_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    name: Mapped[str] = mapped_column(String(255))
    rules: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Budget(Base):
    __tablename__ = "budgets"

    budget_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    investigation_id: Mapped[str | None] = mapped_column(String(36))
    limits: Mapped[dict | None] = mapped_column(JSONB)
    current_usage: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --- Frontier / Acquisition ---


class FrontierItem(Base):
    __tablename__ = "frontier_items"

    frontier_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    investigation_id: Mapped[str | None] = mapped_column(String(36))
    source_id: Mapped[str | None] = mapped_column(String(36))
    uri: Mapped[str] = mapped_column(Text)
    host_key: Mapped[str | None] = mapped_column(String(255))
    priority: Mapped[float] = mapped_column(Float, default=0.0)
    state: Mapped[str] = mapped_column(String(32), default="READY")
    retries: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_digest: Mapped[str | None] = mapped_column(String(64))
    last_etag: Mapped[str | None] = mapped_column(String(255))
    partition: Mapped[str] = mapped_column(String(64), default="global")
    next_schedule_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # FR-007: a discovered candidate carries the provenance of its discovery
    # (source, method, query/seed, and for link-graph the originating
    # observation). Read for audit, never queried -- deliberately unindexed
    # (see migration 017 and ADR-0026). Written by the discovery bridge, not by
    # frontier policy, which owns state/retries/lease/schedule only.
    #
    # Declared LAST on purpose. An ALTER TABLE ... ADD COLUMN always appends at
    # the end of the physical table, so a fresh install (create_all, this
    # order) and an upgraded install (017, appended last) only agree on physical
    # column order if this attribute is last as well. Declaring it earlier would
    # make the two install paths differ in a way nothing in the application can
    # observe but everything that reads the physical table would see.
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    __table_args__ = (
        Index("ix_frontier_tenant", "tenant_id"),
        Index("ix_frontier_host", "host_key"),
        Index("ix_frontier_partition", "partition"),
        # FR-005: Postgres is authoritative; dedup lives here as a unique
        # schedule key (one live frontier item per tenant+uri). FR-006 discovery
        # idempotency depends on this index, so it must never be rebuilt.
        Index("uq_frontier_schedule", "tenant_id", "uri", unique=True),
    )


class AcquisitionTask(Base):
    __tablename__ = "acquisition_tasks"

    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    investigation_id: Mapped[str | None] = mapped_column(String(36))
    frontier_id: Mapped[str] = mapped_column(String(36))
    worker_class: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(32), default="PENDING")
    retries: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_acq_tasks_tenant", "tenant_id"),)


# --- Observation (immutable, I-1) ---


class Observation(Base):
    __tablename__ = "observations"

    observation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    investigation_id: Mapped[str | None] = mapped_column(String(36))
    source_id: Mapped[str | None] = mapped_column(String(36))
    task_id: Mapped[str | None] = mapped_column(String(36))
    uri: Mapped[str] = mapped_column(Text)
    raw_ref: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    content_type: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="created")
    duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    provenance: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_obs_tenant", "tenant_id"),
        CheckConstraint("duplicate IS NOT NULL", name="ck_obs_immutable_guard"),
    )


# --- Interpretation ---


class Mention(Base):
    __tablename__ = "mentions"

    mention_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    observation_id: Mapped[str] = mapped_column(ForeignKey("observations.observation_id"))
    tenant_id: Mapped[str] = mapped_column(String(36))
    surface_form: Mapped[str] = mapped_column(Text)
    normalized_form: Mapped[str | None] = mapped_column(Text)
    transliteration_variants: Mapped[list | None] = mapped_column(JSONB)
    script: Mapped[str | None] = mapped_column(String(8))
    language: Mapped[str | None] = mapped_column(String(8))
    normalization_version: Mapped[str | None] = mapped_column(String(32))
    type_hypothesis: Mapped[str | None] = mapped_column(String(32))
    extractor_version: Mapped[str | None] = mapped_column(String(32))
    offsets: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_mentions_obs", "observation_id"),
        Index("ix_mentions_tenant", "tenant_id"),
    )


class Candidate(Base):
    __tablename__ = "candidates"

    # NOT widened. This is the 008 extraction layer's generic attribute candidate - it
    # carries `mention_ids`, a `surface_form` and a `type_hypothesis`, none of which
    # `domain.relation_candidate.RelationCandidate` has - and its ids are not `CAND-` or
    # `CNDR-`. Feature 019 gives the semantic layer its own `relation_candidate` table
    # rather than overloading this one, so the two kinds of candidate cannot be confused
    # by reading a row.
    candidate_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    mention_ids: Mapped[list | None] = mapped_column(JSONB)
    surface_form: Mapped[str | None] = mapped_column(Text)
    normalized_form: Mapped[str | None] = mapped_column(Text)
    type_hypothesis: Mapped[str | None] = mapped_column(String(32))
    state: Mapped[CandidateResolutionState] = mapped_column(
        Enum(CandidateResolutionState), default=CandidateResolutionState.OPEN
    )
    epistemic_status: Mapped[EpistemicStatus] = mapped_column(
        Enum(EpistemicStatus), default=EpistemicStatus.PROVISIONAL
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # FR-014's missing half. `regime_id` was written in memory by the semantic
    # path and persisted in no table, so every compatibility check against a
    # candidate's regime returned UNEVALUATED -- on the golden path, on every
    # run (spec D6). Defaults to `''`, which is the *declared* absence rather
    # than a substitute: `semantic.regime_store.regime_for` refuses a blank id
    # and the compatibility layer reports `regime_unevaluated` for an empty
    # side, so a default here cannot make an absent regime read as a match
    # (FR-016). It is a default rather than a backfill because a candidate is
    # extraction's output, not an admitted fact, and a candidate that never
    # named a regime has always been a storable thing.
    regime_id: Mapped[str] = mapped_column(String(64), server_default="")

    __table_args__ = (
        Index("ix_candidates_tenant", "tenant_id"),
        Index("ix_candidates_state", "state"),
        Index("ix_candidates_epistemic", "epistemic_status"),
        # The resolution hot path's other half: every candidate read under one
        # regime, which is the population a re-interpretation has to revisit.
        Index("ix_candidates_regime", "tenant_id", "regime_id"),
    )


# --- Admission / Resolution ---


class Entity(Base):
    __tablename__ = "entities"

    entity_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    entity_type: Mapped[str] = mapped_column(String(32))
    canonical_name: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict | None] = mapped_column(JSONB)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_entities_tenant", "tenant_id"),
        Index("ix_entities_type", "entity_type"),
    )


class EntityVersion(Base):
    __tablename__ = "entity_versions"

    version_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.entity_id"))
    tenant_id: Mapped[str] = mapped_column(String(36))
    version_number: Mapped[int] = mapped_column(Integer)
    canonical_name: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_entity_versions_entity", "entity_id"),
        Index("ix_entity_versions_tenant", "tenant_id"),
    )


class Assertion(Base):
    __tablename__ = "assertions"

    assertion_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    subject_entity_id: Mapped[str] = mapped_column(ForeignKey("entities.entity_id"))
    predicate: Mapped[str] = mapped_column(String(128))
    object_entity_id: Mapped[str | None] = mapped_column(ForeignKey("entities.entity_id"))
    evidence_refs: Mapped[dict | None] = mapped_column(JSONB)
    extractor_version: Mapped[str | None] = mapped_column(String(32))
    provenance: Mapped[dict | None] = mapped_column(JSONB)
    state: Mapped[LifecycleState] = mapped_column(
        Enum(LifecycleState), default=LifecycleState.ASSERTED
    )
    temporal_policy: Mapped[TemporalPolicy] = mapped_column(
        Enum(TemporalPolicy), default=TemporalPolicy.SINGLE
    )
    supersedes_id: Mapped[str | None] = mapped_column(String(36))
    replacement_id: Mapped[str | None] = mapped_column(String(36))
    valid_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    system_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_assertions_tenant", "tenant_id"),
        Index("ix_assertions_state", "state"),
        Index("ix_assertions_subject", "subject_entity_id"),
    )


class EvidenceLink(Base):
    __tablename__ = "evidence_links"

    evidence_link_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    assertion_id: Mapped[str | None] = mapped_column(String(36))
    # Widened by feature 019 (CD-3, T020) from String(36). Measured, not assumed: a
    # `CNDR-` revision id is 37 characters, so the old width would have cut the last hex
    # digit off every candidate this column could be asked to hold. Nothing writes one here
    # yet - the generic `candidates` table belongs to the 008 extraction path and holds a
    # different kind of candidate - and it is widened anyway so the column is *capable* of
    # the reference when 019 starts making it. A too-wide column costs nothing; a too-narrow
    # one corrupts an address silently.
    candidate_id: Mapped[str | None] = mapped_column(String(64))
    tenant_id: Mapped[str] = mapped_column(String(36))
    observation_ids: Mapped[list | None] = mapped_column(JSONB)
    publication_count: Mapped[int] = mapped_column(Integer, default=0)
    independent_sources: Mapped[int] = mapped_column(Integer, default=0)
    independent_evidence_chains: Mapped[int] = mapped_column(Integer, default=0)
    source_independence_refs: Mapped[dict | None] = mapped_column(JSONB)
    provenance: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_evidence_links_tenant", "tenant_id"),
        Index("ix_evidence_links_assertion", "assertion_id"),
    )


class AdmissionDecisionRow(Base):
    __tablename__ = "admission_decisions"

    decision_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    # Widened by feature 019 (CD-3, T020) for the same measured reason as
    # `evidence_links.candidate_id`: a 37-character `CAND-`/`CNDR-` address does not fit
    # in 36. An admission decision names the candidate it was taken about, and a decision
    # whose subject cannot be spelled is a decision nobody can trace.
    candidate_id: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(36))
    decision: Mapped[AdmissionDecision] = mapped_column(Enum(AdmissionDecision))
    score_vector: Mapped[dict | None] = mapped_column(JSONB)
    reasons: Mapped[list | None] = mapped_column(JSONB)
    model_version: Mapped[str | None] = mapped_column(String(32))
    policy_version: Mapped[str | None] = mapped_column(String(32))
    profile_id: Mapped[str | None] = mapped_column(String(36))
    evidence_refs: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_admission_decisions_tenant", "tenant_id"),
        Index("ix_admission_decisions_decision", "decision"),
    )


class CalibrationProfile(Base):
    __tablename__ = "calibration_profiles"

    profile_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    entity_type: Mapped[str] = mapped_column(String(32))
    language: Mapped[str | None] = mapped_column(String(8))
    script: Mapped[str | None] = mapped_column(String(8))
    resolver_version: Mapped[str | None] = mapped_column(String(32))
    calibration_version: Mapped[str | None] = mapped_column(String(32))
    feature_schema_version: Mapped[str | None] = mapped_column(String(32))
    policy_version: Mapped[str | None] = mapped_column(String(32))
    calibration_status: Mapped[CalibrationStatus] = mapped_column(
        Enum(CalibrationStatus), default=CalibrationStatus.UNCALIBRATED
    )
    source: Mapped[str] = mapped_column(String(64), default="bootstrap_policy")
    auto_accept_threshold: Mapped[float] = mapped_column(Float)
    defer_threshold: Mapped[float] = mapped_column(Float)
    reject_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    hard_reject_rules: Mapped[dict | None] = mapped_column(JSONB)
    provenance: Mapped[dict | None] = mapped_column(JSONB)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tagged_provisional: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_cal_profiles_tenant_type", "tenant_id", "entity_type"),
        Index("ix_cal_profiles_status", "calibration_status"),
    )


# --- Projections ---


class Projection(Base):
    __tablename__ = "projections"

    projection_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    projection_type: Mapped[str] = mapped_column(String(32))
    projection_name: Mapped[str] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(32), default="pending")
    kafka_offsets: Mapped[dict | None] = mapped_column(JSONB)
    checksum: Mapped[str | None] = mapped_column(String(64))
    node_count: Mapped[int] = mapped_column(Integer, default=0)
    edge_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_projections_tenant", "tenant_id"),
        Index("ix_projections_type", "projection_type"),
    )


class TopologicalFeature(Base):
    __tablename__ = "topological_features"

    feature_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    investigation_id: Mapped[str | None] = mapped_column(String(36))
    dimension: Mapped[int] = mapped_column(Integer)
    birth: Mapped[float] = mapped_column(Float)
    death: Mapped[float | None] = mapped_column(Float, nullable=True)
    persistence: Mapped[float | None] = mapped_column(Float, nullable=True)
    supporting_nodes: Mapped[list | None] = mapped_column(JSONB)
    supporting_edges: Mapped[list | None] = mapped_column(JSONB)
    algorithm_version: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_tda_features_tenant", "tenant_id"),
        Index("ix_tda_features_investigation", "investigation_id"),
    )


class Finding(Base):
    __tablename__ = "findings"

    finding_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    investigation_id: Mapped[str | None] = mapped_column(String(36))
    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    feature_ids: Mapped[list | None] = mapped_column(JSONB)
    evidence_chain: Mapped[list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_findings_tenant", "tenant_id"),
        Index("ix_findings_investigation", "investigation_id"),
    )


class ModelVersion(Base):
    __tablename__ = "model_versions"

    model_version_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    model_type: Mapped[str] = mapped_column(String(32))
    version: Mapped[str] = mapped_column(String(32))
    artifact_uri: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DecisionLog(Base):
    __tablename__ = "decision_logs"

    log_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    decision_type: Mapped[str] = mapped_column(String(32))
    decision_id: Mapped[str] = mapped_column(String(36))
    context: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HostState(Base):
    __tablename__ = "host_states"

    host_state_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    host_key: Mapped[str] = mapped_column(String(255))
    ewma_latency: Mapped[float] = mapped_column(Float, default=0.0)
    ewma_error_rate: Mapped[float] = mapped_column(Float, default=0.0)
    ewma_payload: Mapped[float] = mapped_column(Float, default=0.0)
    success_rate: Mapped[float] = mapped_column(Float, default=1.0)
    discovery_yield: Mapped[float] = mapped_column(Float, default=0.0)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_host_states_tenant", "tenant_id"),
        Index("ix_host_states_host", "tenant_id", "host_key", unique=True),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    log_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    actor: Mapped[str | None] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(128))
    resource_type: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str | None] = mapped_column(String(36))
    context: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_audit_logs_tenant", "tenant_id"),)


class MaterializationRunState(str, enum.Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    QUARANTINED = "QUARANTINED"


class TemporalMaterializationRun(Base):
    __tablename__ = "temporal_materialization_runs"

    run_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    source_cut_id: Mapped[str] = mapped_column(String(96), index=True)
    state: Mapped[MaterializationRunState] = mapped_column(
        Enum(MaterializationRunState), default=MaterializationRunState.QUEUED
    )
    projection_generation: Mapped[int] = mapped_column(Integer, default=0)
    integrity_fingerprint: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index(
            "uq_temporal_run_generation",
            "tenant_id",
            "entity_id",
            "projection_generation",
            unique=True,
        ),
    )


class TemporalWindowRevision(Base):
    __tablename__ = "temporal_window_revisions"

    revision_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    source_cut_id: Mapped[str] = mapped_column(String(96), index=True)
    revision_number: Mapped[int] = mapped_column(Integer)
    projection_generation: Mapped[int] = mapped_column(Integer, default=1)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lifecycle_state: Mapped[str] = mapped_column(String(24))
    payload: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (
        Index(
            "uq_temporal_window_revision",
            "tenant_id",
            "entity_id",
            "window_start",
            "revision_number",
            "projection_generation",
            unique=True,
        ),
    )


class TemporalHistoryPublication(Base):
    __tablename__ = "temporal_history_publications"

    publication_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    source_cut_id: Mapped[str] = mapped_column(String(96), index=True)
    projection_generation: Mapped[int] = mapped_column(Integer)
    integrity_fingerprint: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict | None] = mapped_column(JSONB)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index(
            "uq_temporal_publication_generation",
            "tenant_id",
            "entity_id",
            "projection_generation",
            unique=True,
        ),
    )


class TemporalHistoryHead(Base):
    """One serialized generation head per tenant/entity."""

    __tablename__ = "temporal_history_heads"

    tenant_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    entity_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    projection_generation: Mapped[int] = mapped_column(Integer, default=0)
    publication_id: Mapped[str | None] = mapped_column(String(96))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TemporalMaterializationAudit(Base):
    __tablename__ = "temporal_materialization_audit"

    audit_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    action: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Donor-pattern tables (feature 002: donor-pattern-integration)
# ---------------------------------------------------------------------------


class CorrelationEdgeState(str, enum.Enum):
    OPEN = "OPEN"
    REVIEWED = "REVIEWED"
    RESOLVED = "RESOLVED"


class ReviewDecisionKind(str, enum.Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    UNCERTAIN = "UNCERTAIN"


class ReviewTargetType(str, enum.Enum):
    CANDIDATE = "candidate"
    ASSERTION = "assertion"
    CORRELATION_EDGE = "correlation_edge"
    FINDING = "finding"


class ConnectorStatus(str, enum.Enum):
    REGISTERED = "REGISTERED"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class ReconPlanStatus(str, enum.Enum):
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class OntologyPackStatusState(str, enum.Enum):
    DRAFT = "DRAFT"
    REGISTERED = "REGISTERED"
    ACTIVE = "ACTIVE"


class ClaimVerdictState(str, enum.Enum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNCERTAIN = "UNCERTAIN"


class Statement(Base):
    """FTM-style statement record extending assertions (FR-001/FR-003)."""

    __tablename__ = "statements"

    statement_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    assertion_id: Mapped[str | None] = mapped_column(String(36))
    dataset_id: Mapped[str] = mapped_column(Text)  # provenance boundary
    original_value: Mapped[str] = mapped_column(Text)  # immutable (I-1)
    extraction_version: Mapped[str] = mapped_column(String(64))
    first_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provenance: Mapped[dict | None] = mapped_column(JSONB)
    tenant_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("dataset_id <> ''", name="ck_statement_dataset"),
        CheckConstraint("extraction_version <> ''", name="ck_statement_extraction_version"),
        Index("ix_statements_tenant", "tenant_id"),
        Index("ix_statements_dataset", "dataset_id"),
    )


class CorrelationEdge(Base):
    """possible_match edges between candidates — no auto-merge (FR-004, I-2)."""

    __tablename__ = "correlation_edges"

    edge_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    candidate_a: Mapped[str] = mapped_column(String(36))
    candidate_b: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(24), default="possible_match")
    raw_pair_score: Mapped[float] = mapped_column(Float, default=0.0)
    collective_score: Mapped[float | None] = mapped_column(Float)
    reasons: Mapped[list | None] = mapped_column(JSONB)
    state: Mapped[CorrelationEdgeState] = mapped_column(
        Enum(CorrelationEdgeState), default=CorrelationEdgeState.OPEN
    )
    tenant_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_correlation_edges_tenant", "tenant_id"),
        Index("ix_correlation_edges_pair", "candidate_a", "candidate_b"),
    )


class ReviewDecision(Base):
    """Analyst review ACCEPT/REJECT/UNCERTAIN as immutable provenance (FR-006)."""

    __tablename__ = "review_decisions"

    review_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    target_type: Mapped[ReviewTargetType] = mapped_column(Enum(ReviewTargetType))
    target_id: Mapped[str] = mapped_column(String(36))
    decision: Mapped[ReviewDecisionKind] = mapped_column(Enum(ReviewDecisionKind))
    analyst_id: Mapped[str] = mapped_column(String(128))
    reasoning: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provenance: Mapped[dict | None] = mapped_column(JSONB)
    tenant_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_reviews_tenant", "tenant_id"),
        Index("ix_reviews_target", "target_type", "target_id"),
    )


class Connector(Base):
    """Source connector registry (FR-008, SpiderFoot pattern)."""

    __tablename__ = "connectors"

    connector_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    source_types: Mapped[list | None] = mapped_column(JSONB)
    capabilities: Mapped[dict | None] = mapped_column(JSONB)
    policy_id: Mapped[str | None] = mapped_column(String(36))
    version: Mapped[str] = mapped_column(String(32))
    status: Mapped[ConnectorStatus] = mapped_column(
        Enum(ConnectorStatus), default=ConnectorStatus.REGISTERED
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_connectors_tenant", "tenant_id"),)


class ReconPlan(Base):
    """ReNgine-style recon orchestration over acquisition tasks (FR-009)."""

    __tablename__ = "recon_plans"

    plan_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    investigation_id: Mapped[str | None] = mapped_column(String(36))
    tenant_id: Mapped[str] = mapped_column(String(36))
    strategy: Mapped[dict | None] = mapped_column(JSONB)
    task_ids: Mapped[list | None] = mapped_column(JSONB)
    status: Mapped[ReconPlanStatus] = mapped_column(
        Enum(ReconPlanStatus), default=ReconPlanStatus.PLANNED
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_recon_plans_tenant", "tenant_id"),
        Index("ix_recon_plans_investigation", "investigation_id"),
    )


class OntologyPack(Base):
    """Versioned ontology/schema pack (FR-012, kafSIEM pattern)."""

    __tablename__ = "ontology_packs"

    pack_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    pack_version: Mapped[str] = mapped_column(String(64), unique=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    entity_types: Mapped[list | None] = mapped_column(JSONB)
    properties: Mapped[dict | None] = mapped_column(JSONB)
    relations: Mapped[list | None] = mapped_column(JSONB)
    status: Mapped[OntologyPackStatusState] = mapped_column(
        Enum(OntologyPackStatusState), default=OntologyPackStatusState.DRAFT
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (Index("ix_ontology_packs_tenant", "tenant_id"),)


class Claim(Base):
    """Claim verdict / storyline from independence chains (FR-011, investigator)."""

    __tablename__ = "claims"

    claim_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    assertion_refs: Mapped[list | None] = mapped_column(JSONB)
    verdict: Mapped[ClaimVerdictState] = mapped_column(
        Enum(ClaimVerdictState), default=ClaimVerdictState.UNCERTAIN
    )
    corroboration: Mapped[float] = mapped_column(Float, default=0.0)
    independent_chain_count: Mapped[int] = mapped_column(Integer, default=0)
    publication_count: Mapped[int] = mapped_column(Integer, default=0)
    triangulation: Mapped[dict | None] = mapped_column(JSONB)
    storyline_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_claims_tenant", "tenant_id"),
        Index("ix_claims_verdict", "verdict"),
    )


class EntityStreamRow(Base):
    """Atomic entity fabric substrate (feature 009, block A): append-only.

    The ALL capital of the platform — the atomic entity's life-stream. Every
    mutation is one immutable row; state/series/hypergraph are rebuildable
    projections of this flow (I-11/I-12). Never updated or deleted: a row is
    identified by ``record_hash`` (content-addressed) and its stream order is
    enforced by the composite key (tenant, entity, sequence).

    Payload carries refs only (I-5): raw evidence stays in object storage and
    is reachable via ``observation_id``.
    """

    __tablename__ = "entity_stream"

    tenant_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    entity_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_hash: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(32))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSONB)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observation_id: Mapped[str] = mapped_column(String(64), default="")
    dataset_id: Mapped[str] = mapped_column(String(64), default="")
    extraction_version: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_entity_stream_tenant", "tenant_id"),
        Index("ix_entity_stream_entity", "entity_id"),
        Index("ix_entity_stream_hash", "record_hash"),
    )


class MaterializationOutbox(Base):
    """Durable hand-off between entity creation and Temporal launch."""

    __tablename__ = "materialization_outbox"

    outbox_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    entity_id: Mapped[str] = mapped_column(String(64))
    run_id: Mapped[str] = mapped_column(String(96))
    workflow_id: Mapped[str] = mapped_column(String(128))
    identity: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(24), default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("uq_materialization_outbox_run", "tenant_id", "run_id", unique=True),
        Index("ix_materialization_outbox_ready", "status", "available_at"),
        Index("ix_materialization_outbox_entity", "tenant_id", "entity_id"),
    )


class MaterializationCursor(Base):
    """Durable checkpoint for a bounded Common Crawl materialization run.

    The cursor is a per-(tenant, entity, run, partition, page) work item.  It is
    intentionally append-friendly at the repository boundary: a completed page
    may be retried safely, while the cursor lets a later Temporal attempt resume
    after the last durable page instead of restarting the whole crawl scan.
    """

    __tablename__ = "materialization_cursors"

    cursor_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    entity_id: Mapped[str] = mapped_column(String(64))
    run_id: Mapped[str] = mapped_column(String(96))
    crawl: Mapped[str] = mapped_column(String(64))
    page: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="PENDING")
    last_error: Mapped[str] = mapped_column(Text, default="")
    result_payload: Mapped[dict | None] = mapped_column(JSONB)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_materialization_cursor_scope", "tenant_id", "entity_id", "run_id"),
        Index("uq_materialization_cursor_page", "tenant_id", "entity_id", "run_id", "crawl", "page", unique=True),
    )


class SourceQuerySet(Base):
    """Persisted multi-route plan for one entity (feature 015, US2).

    Planning is deterministic and pure, but persisting it makes the executed
    route set inspectable and lets frontier entries reference a stable query
    identity across runs. Mirrors migration 015 exactly.
    """

    __tablename__ = "source_query_set"

    query_set_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    entity_id: Mapped[str] = mapped_column(String(64))
    identity_fingerprint: Mapped[str] = mapped_column(String(64))
    surface_digest: Mapped[str] = mapped_column(String(64))
    query_count: Mapped[int] = mapped_column(Integer, default=0)
    executable_count: Mapped[int] = mapped_column(Integer, default=0)
    unsupported_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index(
            "uq_source_query_set_scope",
            "tenant_id",
            "entity_id",
            "identity_fingerprint",
            unique=True,
        ),
        Index("ix_source_query_set_tenant", "tenant_id"),
    )


class SourceQuery(Base):
    """One route in a :class:`SourceQuerySet`, executable or declared-unsupported.

    Unsupported rows are persisted rather than omitted so that a partially
    served search surface is distinguishable from a fully served one (FR-004).
    """

    __tablename__ = "source_query"

    query_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    query_set_id: Mapped[str] = mapped_column(String(96))
    tenant_id: Mapped[str] = mapped_column(String(36))
    entity_id: Mapped[str] = mapped_column(String(64))
    ordinal: Mapped[int] = mapped_column(Integer)
    route_kind: Mapped[str] = mapped_column(String(32))
    query_value: Mapped[str] = mapped_column(String(512))
    match_type: Mapped[str] = mapped_column(String(16))
    surt_prefix: Mapped[str | None] = mapped_column(String(255))
    provider: Mapped[str | None] = mapped_column(String(32))
    executable: Mapped[bool] = mapped_column(Boolean, default=True)
    unsupported_reason: Mapped[str | None] = mapped_column(String(64))
    origin_refs: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index(
            "uq_source_query_identity",
            "query_set_id",
            "route_kind",
            "query_value",
            unique=True,
        ),
        Index("ix_source_query_entity", "tenant_id", "entity_id"),
        Index("ix_source_query_executable", "tenant_id", "entity_id", "executable"),
    )


class EvidenceContext(Base):
    """Immutable evidence frame a claim is interpreted inside (feature 016, US3).

    A context is the observation, its source, its document segment and the
    candidate mentions it grounds, addressed by content: ``context_id`` is a
    digest of the frame's own fields, so re-registering an identical frame is a
    no-op rather than a duplicate (I-11). Never substituted with a default frame
    when resolution fails -- an unresolved context yields an explicit
    ``context_unresolved`` reason instead. Mirrors migration 016 exactly.
    """

    __tablename__ = "evidence_context"

    context_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    investigation_id: Mapped[str] = mapped_column(String(36), server_default="")
    entity_anchor: Mapped[str] = mapped_column(String(64), server_default="")
    observation_id: Mapped[str] = mapped_column(String(64), server_default="")
    source_id: Mapped[str] = mapped_column(String(64), server_default="")
    document_id: Mapped[str] = mapped_column(String(96), server_default="")
    segment_id: Mapped[str] = mapped_column(String(96), server_default="")
    subject_candidate_ids: Mapped[list] = mapped_column(JSONB)
    object_candidate_ids: Mapped[list] = mapped_column(JSONB)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_family: Mapped[str] = mapped_column(String(64), server_default="")
    independence_group: Mapped[str] = mapped_column(String(64), server_default="")
    language: Mapped[str] = mapped_column(String(8), server_default="")
    location_context: Mapped[str] = mapped_column(String(128), server_default="")
    extraction_version: Mapped[str] = mapped_column(String(32), server_default="")
    normalization_version: Mapped[str] = mapped_column(String(32), server_default="")
    ontology_version: Mapped[str] = mapped_column(String(64), server_default="")
    completeness: Mapped[str] = mapped_column(String(16), server_default="complete")
    trust_state: Mapped[str] = mapped_column(String(16), server_default="unverified")
    policy_snapshot_ref: Mapped[str] = mapped_column(String(96), server_default="")
    parent_context_id: Mapped[str] = mapped_column(String(64), server_default="")
    frame_fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_evidence_context_tenant", "tenant_id"),
        Index("ix_evidence_context_observation", "tenant_id", "observation_id"),
        Index("ix_evidence_context_source", "tenant_id", "source_id"),
        Index("ix_evidence_context_investigation", "tenant_id", "investigation_id"),
        Index(
            "uq_evidence_context_fingerprint",
            "tenant_id",
            "frame_fingerprint",
            unique=True,
        ),
    )


class RelationClaim(Base):
    """A single revision of an asserted relation, with its own provenance (016, US2).

    Identity is two-level: ``logical_relation_id`` names the relation and stays
    constant across revisions, while ``relation_id`` covers this revision's
    content and changes when the claim is revised. A claim is not truth (I-3) --
    ``confidence``, ``evidence_grade`` and the source independence groups are
    stored separately and never collapsed into one number (constitution IV).
    Mirrors migration 016 exactly.
    """

    __tablename__ = "relation_claim"

    relation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    logical_relation_id: Mapped[str] = mapped_column(String(64))
    revision_number: Mapped[int] = mapped_column(Integer, server_default="1")
    tenant_id: Mapped[str] = mapped_column(String(36))
    investigation_id: Mapped[str] = mapped_column(String(36), server_default="")
    relation_type: Mapped[str] = mapped_column(String(128))
    arity_mode: Mapped[str] = mapped_column(String(16))
    subject_ref: Mapped[str] = mapped_column(String(64))
    object_ref: Mapped[str] = mapped_column(String(64))
    role_bindings: Mapped[list] = mapped_column(JSONB)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    known_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    known_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assertion_refs: Mapped[list] = mapped_column(JSONB)
    observation_refs: Mapped[list] = mapped_column(JSONB)
    context_ref: Mapped[str] = mapped_column(String(64))
    source_independence_groups: Mapped[list] = mapped_column(JSONB)
    extraction_version: Mapped[str] = mapped_column(String(32), server_default="")
    normalization_version: Mapped[str] = mapped_column(String(32), server_default="")
    ontology_version: Mapped[str] = mapped_column(String(64), server_default="")
    schema_version: Mapped[str] = mapped_column(String(32), server_default="")
    status: Mapped[str] = mapped_column(String(24), server_default="active")
    confidence: Mapped[float] = mapped_column(Float, server_default="0.5")
    evidence_grade: Mapped[str] = mapped_column(String(16), server_default="ungraded")
    created_by: Mapped[str] = mapped_column(String(128), server_default="")
    supersedes: Mapped[str] = mapped_column(String(64), server_default="")
    contradicts: Mapped[list] = mapped_column(JSONB)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # The instruments this claim was interpreted under, copied from the
    # candidate's `semantic_regime_ref` at admit time (FR-014). A copy, not a new
    # fact: the regime was already fixed by the candidate the claim was built
    # from, so this column has nothing to decide and nothing that can drift from
    # the candidate.
    #
    # NOT NULL and with **no** server default, which is the one asymmetry with
    # `candidates.regime_id` in this revision and is deliberate on both sides.
    # Every writer of this table holds the candidate, so there is never a moment
    # at which the value is genuinely unknown; and a default would let a claim
    # that named no regime be stored as though it had, which is the silent
    # substitution FR-016 forbids. The declared absence is a *refusal* here, not
    # a value. Nothing is indexed on it: reconstruction reads a claim's regime
    # by the claim's own primary key, and no read path groups claims by regime.
    regime_id: Mapped[str] = mapped_column(String(64))

    __table_args__ = (
        Index("ix_relation_claim_tenant", "tenant_id"),
        Index("ix_relation_claim_logical", "tenant_id", "logical_relation_id"),
        Index("ix_relation_claim_type", "tenant_id", "relation_type"),
        Index("ix_relation_claim_subject", "tenant_id", "subject_ref"),
        Index("ix_relation_claim_object", "tenant_id", "object_ref"),
        Index("ix_relation_claim_context", "context_ref"),
        Index("uq_relation_claim_content", "tenant_id", "content_hash", unique=True),
    )


class RelationClaimRevision(Base):
    """Append-only ledger of a logical relation's revision chain (feature 016, US2).

    A revised claim is written as a new row rather than an update, so the chain
    that ``revisions_of`` returns can be reconstructed exactly as it was recorded
    (I-1). Mirrors migration 016 exactly.
    """

    __tablename__ = "relation_claim_revision"

    revision_row_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    relation_id: Mapped[str] = mapped_column(String(64))
    logical_relation_id: Mapped[str] = mapped_column(String(64))
    revision_number: Mapped[int] = mapped_column(Integer)
    tenant_id: Mapped[str] = mapped_column(String(36))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    context_ref: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24))
    evidence_grade: Mapped[str] = mapped_column(String(16))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index(
            "ix_relation_claim_revision_logical",
            "tenant_id",
            "logical_relation_id",
            "revision_number",
            unique=True,
        ),
        Index("ix_relation_claim_revision_relation", "relation_id"),
    )


class RelationSchemaVersion(Base):
    """One registered version of a relation schema (feature 016, US5).

    Relation semantics are data, not code: arity, allowed participant classes,
    role bindings, admissible evidence patterns and temporal semantics are all
    recorded so a verdict rendered against one version stays interpretable after
    the vocabulary moves on. Mirrors migration 016 exactly.
    """

    __tablename__ = "relation_schema_version"

    schema_row_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    relation_type: Mapped[str] = mapped_column(String(128))
    schema_version: Mapped[str] = mapped_column(String(32))
    arity_mode: Mapped[str] = mapped_column(String(16))
    temporal_semantics: Mapped[str] = mapped_column(String(24))
    admission_rule_id: Mapped[str] = mapped_column(String(64))
    definition: Mapped[dict] = mapped_column(JSONB)
    tenant_id: Mapped[str] = mapped_column(String(36))
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index(
            "uq_relation_schema_version",
            "tenant_id",
            "relation_type",
            "schema_version",
            unique=True,
        ),
        Index("ix_relation_schema_version_type", "tenant_id", "relation_type"),
    )


class ClaimContextLineage(Base):
    """A persisted lineage trace for one claim in one direction (feature 016, US6).

    Traces stop at the first missing hop and say so: ``complete`` is false and
    ``first_unresolved_hop`` names where the walk stopped, so an incomplete chain
    is stored as incomplete rather than reported as an empty one (FR-033).
    Mirrors migration 016 exactly.
    """

    __tablename__ = "claim_context_lineage"

    lineage_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    relation_id: Mapped[str] = mapped_column(String(64))
    direction: Mapped[str] = mapped_column(String(16))
    hops: Mapped[list] = mapped_column(JSONB)
    complete: Mapped[bool] = mapped_column(Boolean)
    first_unresolved_hop: Mapped[str | None] = mapped_column(String(24))
    unresolved_node_id: Mapped[str] = mapped_column(String(64), server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_claim_context_lineage_relation", "tenant_id", "relation_id", "direction"),
    )


# ---------------------------------------------------------------------------
# Semantic fabric (feature 017: semantic-fabric)
#
# Four tenant-scoped tables holding the semantic layer beside the graph rather
# than inside it: layered typing claims, the profiles that scope them, the
# recorded cross-vocabulary alignments, and the graded findings validation
# produces. None of them is an admission gate and none of them may delete: a
# typing is a claim, a mapping is a correspondence somebody asserted, and a
# finding is a verdict about a check rather than about the record (FR-012).
#
# Every table carries ``tenant_id`` NOT NULL with a check that it is not the
# empty string. There is deliberately no nullable or global tenant: a semantic
# term is a reading of one tenant's data, and a row readable by every tenant
# would leak what instruments that tenant had (constitution IV, fail-closed).
# ---------------------------------------------------------------------------


class TypeAssertionRow(Base):
    """One rung of the typing ladder for one entity, with its evidence (017, US2).

    Layered typing (FR-003). ``scope`` says which layer a claim belongs to --
    ``observed``, ``inferred``, ``mapped`` or ``context`` -- and ``status`` says
    how far up the commitment ladder that layer has been taken. One entity holds
    all four at once, which is the whole point: this table exists so the single
    categorical ``Entity.schema_name`` no longer has to be the only typing there
    is.

    **A promotion is a new row, never an update.** ``type_assertion_id`` is the
    digest of the *whole* claim -- status, evidence, ``raw_surface`` and
    ``hypothesis`` included -- so moving a claim from ``observed`` up to
    ``validated`` yields a different id and both rows survive side by side. That is
    what makes FR-004 structural rather than aspirational: the ladder
    ``raw -> surface -> hypothesis -> mapped concept`` is reconstructable from
    these rows alone, with no prior state overwritten to record the newer one.

    ``logical_type_assertion_id`` is the claim's own identity -- the digest of
    (tenant, entity, type, scope) -- and every revision of that claim shares it, so
    "all states of this typing" is one indexed lookup rather than a scan. The pair
    mirrors ``logical_relation_id`` / ``relation_id`` on ``relation_claims`` and
    ``logical_candidate_id`` on candidates: the semantic layer and the relation
    layer share one versioning philosophy rather than each inventing one. Grouping
    the revisions is therefore a plain equality filter, and it is left
    unconstrained -- a unique constraint over the claim identity would forbid the
    very second row a promotion needs. Idempotency comes from the revision primary
    key instead, which catches "the same revision recorded twice" without catching
    "the same claim promoted". What is indexed is the read path: every scope of one
    entity (US2) and the revisions of one claim (FR-018).


    ``observed_at`` is when the platform learned the claim; ``valid_from`` and
    ``valid_to`` are when it was true. Three separate columns, never merged
    (constitution V). Mirrors migration 018 exactly.
    """

    __tablename__ = "type_assertions"

    type_assertion_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    logical_type_assertion_id: Mapped[str] = mapped_column(String(64))
    tenant_id: Mapped[str] = mapped_column(String(36))
    entity_ref: Mapped[str] = mapped_column(String(64))
    type_ref: Mapped[str] = mapped_column(String(255))
    type_scheme: Mapped[str] = mapped_column(String(16))
    scope: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24))
    raw_surface: Mapped[str] = mapped_column(Text, server_default="")
    hypothesis: Mapped[str] = mapped_column(String(255), server_default="")
    source_ref: Mapped[str] = mapped_column(String(64), server_default="")
    extractor_ref: Mapped[str] = mapped_column(String(64), server_default="")
    context_ref: Mapped[str] = mapped_column(String(64), server_default="")
    profile_ref: Mapped[str] = mapped_column(String(96), server_default="")
    mapping_ref: Mapped[str] = mapped_column(String(96), server_default="")
    evidence_refs: Mapped[list] = mapped_column(JSONB)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("tenant_id <> ''", name="ck_type_assertion_tenant"),
        Index("ix_type_assertion_entity", "tenant_id", "entity_ref", "scope"),
        Index(
            "ix_type_assertion_revisions",
            "tenant_id",
            "logical_type_assertion_id",
        ),
    )


class SemanticProfileRow(Base):
    """One versioned, scoped bundle of semantic instruments (feature 017, US2).

    A profile says "under this regime, these types, relations, vocabularies,
    constraints and mappings were in play". It says nothing about what may exist:
    the five ref collections are references to instruments, and no column here can
    assert that two of them denote one thing (spec scope guard, FR-007).
    ``parent_profile`` chains inheritance, and ``applies_to`` scopes the bundle to
    a source, a domain, an extractor or an investigation.

    Two keys, deliberately. ``(tenant_id, profile_id, version)`` is the *address* a
    caller resolves, and is the unique one -- a versioned key is never rebound.
    ``content_key`` is the digest of the whole bundle including the parent, so
    "this key was already registered with a different bundle" is a decidable
    question rather than a silent overwrite (constitution VII). It is a collision
    guard, not a lookup key, so it carries no index.

    ``applies_to`` is deliberately unindexed: a profile store is small per tenant
    and a GIN index over a document read once per resolution would cost write
    amplification on every profile write for a scan nobody runs (ADR-0026, the
    same call migration 017 made for provenance). Mirrors migration 018 exactly.
    """

    __tablename__ = "semantic_profiles"

    profile_row_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    profile_id: Mapped[str] = mapped_column(String(96))
    version: Mapped[str] = mapped_column(String(32))
    parent_profile: Mapped[str | None] = mapped_column(String(128))
    type_refs: Mapped[list] = mapped_column(JSONB)
    relation_refs: Mapped[list] = mapped_column(JSONB)
    vocabulary_refs: Mapped[list] = mapped_column(JSONB)
    constraint_refs: Mapped[list] = mapped_column(JSONB)
    mapping_refs: Mapped[list] = mapped_column(JSONB)
    applies_to: Mapped[list] = mapped_column(JSONB)
    description: Mapped[str] = mapped_column(Text, server_default="")
    content_key: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("tenant_id <> ''", name="ck_semantic_profile_tenant"),
        # A bare tenant scan is served by this index's leading column, so there
        # is no separate tenant index to keep in step with it.
        Index(
            "uq_semantic_profile_version",
            "tenant_id",
            "profile_id",
            "version",
            unique=True,
        ),
    )


class SemanticMappingRow(Base):
    """One recorded correspondence between an internal term and an external one (017, US10).

    A mapping is a claim a mapping process made, and it is stored as one (FR-009).
    ``predicate`` is how that process characterised the relationship -- not how the
    platform treats the two references, which is the difference between this row
    and an identity assertion. ``mapping_source``, ``mapping_version`` and
    ``justification`` say who produced the claim and on what grounds, so the
    alignment can be audited, re-evaluated and cited as evidence rather than
    living in a hardcoded dict.

    ``mapping_id`` is the digest of the whole claim, which makes re-recording
    identical content a no-op at the primary key and makes a *re-evaluation* a new
    row that names its predecessor in ``supersedes`` (FR-004). Nothing is ever
    overwritten or withdrawn in place.

    Both directions are indexed because both are real read paths: "what do we
    align this internal concept to" and "what does this external term align to
    here" are asked in opposite directions, and a mapping process that aligns a
    pair in either order is claiming the same correspondence. ``observed_at`` is
    when the platform learned the mapping, which is not when the mapping became
    true (constitution V). Mirrors migration 018 exactly.
    """

    __tablename__ = "semantic_mappings"

    mapping_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    subject_ref: Mapped[str] = mapped_column(String(255))
    object_ref: Mapped[str] = mapped_column(String(255))
    subject_scheme: Mapped[str] = mapped_column(String(16))
    object_scheme: Mapped[str] = mapped_column(String(16))
    predicate: Mapped[str] = mapped_column(String(32))
    mapping_set_id: Mapped[str] = mapped_column(String(64))
    mapping_set_version: Mapped[str] = mapped_column(String(32))
    mapping_source: Mapped[str] = mapped_column(String(64), server_default="")
    mapping_version: Mapped[str] = mapped_column(String(32), server_default="")
    justification: Mapped[str] = mapped_column(String(24))
    provenance: Mapped[list] = mapped_column(JSONB)
    supersedes: Mapped[list] = mapped_column(JSONB)
    # The server default is the domain default: a mapping process that states no
    # confidence is asserting full correspondence, and the DDL saying anything
    # weaker would let a mapping be stored at a strength nobody claimed.
    confidence: Mapped[float] = mapped_column(Float, server_default="1.0")
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("tenant_id <> ''", name="ck_semantic_mapping_tenant"),
        Index("ix_semantic_mapping_subject", "tenant_id", "subject_ref"),
        Index("ix_semantic_mapping_object", "tenant_id", "object_ref"),
    )


class ValidationFindingRow(Base):
    """A graded result attached to an assertion; it has no authority to delete (017, US5).

    Layered validation (FR-011): ``stage`` is where in the fixed order
    structural -> semantic -> temporal -> provenance -> cross-source -> graph-level
    the check ran, and ``verdict`` is its grade. The grade is not a boolean and
    ``unknown``/``unsupported`` are explicitly not failures -- they mean the
    platform could not evaluate the claim, which is a different fact with a
    different consequence from being wrong (SC-9).

    Note what is absent. There is no severity column and no fatal flag, because
    either could be mapped onto a rejection by a later caller, and a finding that
    can delete is not a finding (FR-012). The assertion a finding names stays in
    the graph, stays queryable, and keeps its evidence; this row travels with it.
    Mirrors migration 018 exactly.
    """

    __tablename__ = "validation_findings"

    finding_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    assertion_ref: Mapped[str] = mapped_column(String(64))
    stage: Mapped[str] = mapped_column(String(24))
    verdict: Mapped[str] = mapped_column(String(16))
    code: Mapped[str] = mapped_column(String(64), server_default="")
    message: Mapped[str] = mapped_column(Text, server_default="")
    constraint_ref: Mapped[str] = mapped_column(String(96), server_default="")
    profile_ref: Mapped[str] = mapped_column(String(96), server_default="")
    context_ref: Mapped[str] = mapped_column(String(64), server_default="")
    evidence_refs: Mapped[list] = mapped_column(JSONB)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("tenant_id <> ''", name="ck_validation_finding_tenant"),
        # "what did validation say about this assertion" and "what is failing in
        # this tenant" are the two questions an operator actually asks, and they
        # read the table through completely different columns.
        Index("ix_validation_finding_assertion", "tenant_id", "assertion_ref"),
        Index("ix_validation_finding_verdict", "tenant_id", "verdict"),
    )


# ---------------------------------------------------------------------------
# World substrate (feature 018: world-substrate)
#
# Six tables, in three groups, closing the two ends of the evidence chain and
# the middle that says what was believed when.
#
# **Where the bytes came from.** The acquisition event itself (``captures``), the
# ingestion run that produced it (``ingest_batches``), and the registry of
# streams that can produce one at all (``data_stream``). The graph's own
# foundation is untouched by this group; what becomes durable here is where the
# bytes came from and what it is honest to say about when.
#
# **Why an identity is what it is.** The durable statement of the anchor
# (``entity_identity``) and the append-only log of the reasoning that elected and
# re-examined it (``resolution_decision``). This is the group the feature's gate
# requirement is about: before it, ``ENT-`` was deterministic only as long as
# the caller still held its ``ResolutionScope``.
#
# **What was believed when.** The regime a reading was interpreted under
# (``semantic_regime``), plus the ``regime_id`` column on ``candidates`` and
# ``relation_claim`` that makes it reachable from the graph.
#
# Every table carries ``tenant_id`` NOT NULL with a check that it is not the
# empty string, for the reason migration 018 gave and this revision repeats: NOT
# NULL alone still admits ``''``, and ``''`` is not a tenant (constitution IV).
#
# Two things are deliberately absent from all six, and both absences are
# load-bearing rather than omissions:
#
# * **No foreign keys.** The three most recent revisions (015, 016, 018) reference
#   other records by id string and add no FK, so an ``ingest_batches`` row can be
#   written in the same transaction as the ``captures`` rows it accounts for,
#   whichever order the writer chooses, and a capture of a batch that has not been
#   opened is still storable rather than being an unorderable write. Adding an FK
#   here would be a schema decision this feature has not earned. The identity and
#   regime groups reference the most, and for the same reason: a resolution
#   decision and an anchor are recorded by a process that may not hold the
#   mentions, captures or frames they name in the same transaction.
# * **No wall clock in any content address.** ``created_at``/``registered_at``/
#   ``recorded_at`` record when the row was *written*; they are not in
#   ``capture_fingerprint``, ``identity_fingerprint``, ``record_fingerprint`` or
#   ``regime_id``, not in a generated column and not in any unique index, so
#   re-ingesting the same fact at a different moment produces the same id and the
#   same row (constitution VII, FR-022). ``fetched_at`` *is* in the capture's
#   address and ``created_at`` is not, and the difference is that one is a fact
#   of the event and the other is a fact of the writing.
# ---------------------------------------------------------------------------


class CaptureRow(Base):
    """One acquisition event: bytes were obtained, from somewhere, in a batch (FR-006).

    A capture is a fact of *acquisition*. An ``observations`` row is a fact of
    *having observed* content, and the two were conflated for the whole life of the
    platform: the orchestrator had no honest capture to record and derived a
    ``capture_id`` from ``(source_id, observation_id)`` instead, which is an id
    computed from the event it is supposed to explain (spec D3).

    ``fetched_at`` is nullable and ``capture_time_basis`` is not, and that pairing
    is the design (spec D-B, FR-025). A crawl index genuinely has no fetch time,
    so a Common Crawl row reads ``fetched_at IS NULL`` with
    ``capture_time_basis = 'index_observation'`` — a *stated* absence, recorded by
    name, which is what keeps it distinguishable from a row whose fetch time has
    not been written yet. The two check constraints make the pairing structural in
    the DDL as well as in :class:`domain.capture.Capture`: a basis of ``fetch``
    requires the timestamp, and a timestamp is only ever allowed on a basis of
    ``fetch``. A loader that tried to promote an index or publication timestamp into
    ``fetched_at`` is refused by the database, not only by the value type.

    ``capture_fingerprint`` is the same discipline as ``evidence_context.frame_fingerprint``
    and ``relation_claim.content_hash``: an application-computed digest of the
    record's own address material, stored beside the id so registration is
    idempotent at the database and not only in memory. It is written by the
    application and never generated, because a generated column would have to
    reproduce the Python canonicalisation exactly and a divergence would be
    invisible until an id failed to verify (I-1, I-11).

    ``captures`` deliberately holds no list of the observations it produced.
    Identity flows capture -> observation by reference; folding a downstream
    result into an upstream event's address would make the fetch change identity
    the moment extraction ran.

    ``content_length``, ``media_type`` and ``fetched_at`` are nullable because a
    real stream does not always have them — a crawl index row reports no media
    type, and no stream that is not performing its own retrieval has a fetch time
    — and a value type is the only thing that can say which of the two a null
    means. Mirrors migration 019 exactly.
    """

    __tablename__ = "captures"

    capture_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    source_id: Mapped[str] = mapped_column(String(64))
    source_family: Mapped[str] = mapped_column(String(64), server_default="")
    target_uri: Mapped[str] = mapped_column(Text, server_default="")
    locator: Mapped[str] = mapped_column(Text, server_default="")
    content_digest: Mapped[str] = mapped_column(String(128))
    content_length: Mapped[int | None] = mapped_column(Integer)
    media_type: Mapped[str] = mapped_column(String(128), server_default="")
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    capture_time_basis: Mapped[str] = mapped_column(String(24))
    transport: Mapped[str] = mapped_column(String(32), server_default="")
    ingest_batch_id: Mapped[str] = mapped_column(String(64), server_default="unbatched")
    ingest_attempt: Mapped[int] = mapped_column(Integer, server_default="1")
    recorded_by: Mapped[str] = mapped_column(String(128), server_default="")
    capture_fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("tenant_id <> ''", name="ck_capture_tenant"),
        CheckConstraint("content_digest <> ''", name="ck_capture_content_digest"),
        # A basis of `fetch` is a claim that this platform measured the retrieval,
        # so the measurement has to be there.
        CheckConstraint(
            "capture_time_basis <> 'fetch' OR fetched_at IS NOT NULL",
            name="ck_capture_fetch_time_present",
        ),
        # And the converse, which is the one FR-025 is about: a populated
        # `fetched_at` is a measured fetch time, and no other basis may carry one.
        CheckConstraint(
            "fetched_at IS NULL OR capture_time_basis = 'fetch'",
            name="ck_capture_fetch_time_basis",
        ),
        CheckConstraint("content_length IS NULL OR content_length >= 0", name="ck_capture_length"),
        CheckConstraint("ingest_attempt >= 1", name="ck_capture_attempt"),
        # Idempotency at the database, not only in InMemoryCaptureRegistry (I-11).
        # Tenant leads because the address is tenant-scoped: two tenants fetching
        # identical bytes must never collide on one id (constitution IV).
        Index("uq_capture_fingerprint", "tenant_id", "capture_fingerprint", unique=True),
        # "Every capture of this target" is the entry point to the payload-dedup
        # query, and the target column is the only part of `payload_key` that is
        # selective across a whole tenant.
        Index("ix_capture_target", "tenant_id", "target_uri"),
        # "What did this ingestion batch fetch", which is FR-009's batch half: the
        # batch is a run, and a re-ingest of one payload under a new batch is a new
        # capture of a known payload rather than a new payload.
        Index("ix_capture_batch", "tenant_id", "ingest_batch_id"),
        # SC-16's standing question — how many captures in this tenant have no
        # fetch time, and which streams are they from. Unindexed, the answer is a
        # full scan of the acquisition table.
        Index("ix_capture_time_basis", "tenant_id", "capture_time_basis"),
    )


class IngestBatchRow(Base):
    """One ingestion run: a named window of acquisition over a source (FR-009).

    A batch is what makes FR-009's two questions separable. *Is this the same
    fetch event?* is the capture id; *have these bytes come back before?* is the
    payload key. Neither is the batch, and this table is the reason they cannot be
    conflated — a batch id is in the capture's address material, so the same
    payload read in two batches is two captures, and a capture written outside any
    run carries :data:`~domain.capture.UNBATCHED_INGEST_BATCH` rather than an
    invented batch.

    ``record_count`` is nullable because a batch that is still open has not counted
    its records. Storing zero instead would make "nothing has arrived yet" and
    "nothing arrived" the same row, which is the kind of conflation this table
    exists to prevent; the state column already says which of the two it is.

    ``opened_at`` is a fact of the run and ``closed_at`` is a fact of the run
    finishing, and neither is a content address — they are not in any index beyond
    the ones below, and no id is derived from them.

    The state vocabulary is closed by a check rather than by an enum column,
    matching how the three recent revisions spell their categorical columns: a
    CHECK renders identically in ``create_all`` and in the migration, and a
    ``sa.Enum`` would not. Mirrors migration 019 exactly.
    """

    __tablename__ = "ingest_batches"

    batch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    source_id: Mapped[str] = mapped_column(String(64))
    stream_id: Mapped[str] = mapped_column(String(96), server_default="")
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    record_count: Mapped[int | None] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(16), server_default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("tenant_id <> ''", name="ck_ingest_batch_tenant"),
        CheckConstraint(
            "state IN ('open', 'closed', 'aborted')",
            name="ck_ingest_batch_state",
        ),
        CheckConstraint(
            "record_count IS NULL OR record_count >= 0", name="ck_ingest_batch_count"
        ),
        # A closed batch has an end; an open one has not got one yet. Stated as a
        # check so a writer cannot close a batch without recording when, which is
        # the difference between a run you can reconstruct and a run you can only
        # date approximately.
        CheckConstraint("state <> 'closed' OR closed_at IS NOT NULL", name="ck_ingest_batch_close"),
        # "Every run over this source, in order" — the read that reconstructs how
        # one source's acquisitions were ordered and batched.
        Index("ix_ingest_batch_source", "tenant_id", "source_id", "opened_at"),
        # "What is still running" is asked on every ingest cycle and is a
        # different column from the one above.
        Index("ix_ingest_batch_state", "tenant_id", "state"),
        # "Every run of this stream" is FR-024's per-stream question: given a
        # registered stream, which acquisition events did it produce.
        Index("ix_ingest_batch_stream", "tenant_id", "stream_id"),
    )


class DataStreamRow(Base):
    """The registry of streams that may produce a capture, and what they claim (FR-026).

    This table is the FR-026 refusal made durable. A stream that cannot state
    which of the six time axes it supplies is not registrable, and the place that
    decision is recorded is here rather than in each adapter's docstring — so the
    set of axes a source has, and the set it has said it has, are one indexed read
    apart from each other.

    ``time_axes_supplied`` is the summary: the axes this stream supplies, as names.
    It is the column an index and a query read, and it is a summary of
    ``axis_declarations`` rather than a second independent claim — the writer
    derives one from the other and the in-memory registrar refuses a pair that
    disagrees, so the two cannot drift into two different stories about the same
    stream.

    ``axis_declarations`` is why the summary alone is not enough, and it is an
    addition to the field list in the spec's Data Requirements. All six axes are
    recorded, including the ones this stream states it cannot supply, each with the
    reason and, where supplied, the raw field it is read from. Without it, "which
    axes does this stream have" is answerable and "why does it not have the other
    five" is not — and the second question is the one FR-025 is about. A summary
    holding only the supplied axes would drop the gaps, and a gap that is not
    recorded is a gap that gets re-litigated per adapter.

    ``adapter_ref`` is a dotted path to the module and class implementing the
    contract, never an instance, so the row stays serialisable and a deployment can
    resolve the adapter a stream was registered with (I-1, I-5).

    ``registered_at`` is the row's write clock. It is in no index and in no
    generated column and derives no id, so re-registering a stream later does not
    change the row's identity. Mirrors migration 019 exactly.
    """

    __tablename__ = "data_stream"

    stream_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(32))
    temporality: Mapped[str] = mapped_column(String(32))
    time_axes_supplied: Mapped[list] = mapped_column(JSONB)
    axis_declarations: Mapped[list] = mapped_column(JSONB)
    adapter_ref: Mapped[str] = mapped_column(String(255), server_default="")
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("tenant_id <> ''", name="ck_data_stream_tenant"),
        CheckConstraint("kind <> ''", name="ck_data_stream_kind"),
        CheckConstraint("temporality <> ''", name="ck_data_stream_temporality"),
        CheckConstraint("adapter_ref <> ''", name="ck_data_stream_adapter_ref"),
        # The registry is a name -> declaration map, and the name is the primary
        # key. A bare tenant scan is served by this index's leading column, so
        # there is no separate tenant index to keep in step with it — the same call
        # migration 018 made for uq_semantic_profile_version.
        Index("ix_data_stream_temporality", "tenant_id", "temporality"),
    )


class EntityIdentityRow(Base):
    """One entity's durable identity statement: the mention that introduced it (FR-001).

    The gate requirement of the feature. ``ENT-`` was technically deterministic
    only as long as the caller still held its ``ResolutionScope``: a caller that
    dropped the scope had the next batch mint a fresh anchor, and the same entity
    got a new id (spec D1). This table is what makes the loss a missed
    optimisation instead of an identity change, and it is a **separate** table
    rather than columns on ``entities`` for the reason the spec's D-A gives --
    bolt-on columns admit a partial write leaving an entity with no anchor, and
    the next layer up reads that as a valid entity. It also leaves
    ``entities.entity_type`` a projection instead of a second truth.

    **A separate table, shaped for the two read paths above it**, and those two
    paths are the entire index set. ``anchor_for_mention`` is the resolution hot
    path ("does this mention already anchor an entity?"); ``identity_for_entity``
    and ``history`` are the reconstruction hot path ("which mention introduced
    this entity, and what has been decided about it since?"). Read-path shaping
    decided the schema here, not entity tidiness (plan D1, SC-17).

    **The write-once anchor needs TWO unique constraints, and this is the one
    place where the plan's index set and the real invariant differ.** UNIQUE
    ``(tenant_id, anchor_mention_id)`` covers "one mention anchors one entity"
    and is what makes the anchor write-once by construction rather than by
    convention. It does **not** cover "one entity has one anchor": a second
    anchor for an already-anchored entity is invisible to it, and an anchor that
    silently moves is precisely the failure FR-001 forbids. So UNIQUE
    ``(tenant_id, entity_id)`` is the other half, and between them they are the
    feature's load-bearing guarantee. ``InMemoryEntityIdentityStore.bind``
    reproduces both in memory and is where the second half gets a *typed*
    refusal -- ``entity_reanchored`` -- which a bare index cannot give a caller.
    This is the one gap the agent that wrote ``domain.entity_identity`` named and
    it is closed here rather than deferred.

    **Two-level identity, and the primary key is the logical one.**
    ``entity_id`` is the resolver's own ``ENT-``, carried verbatim and never
    re-derived: a machine that owns an address must be the only thing that mints
    it, and re-minting it here would mean re-deriving an anchor, which is the
    defect. ``identity_fingerprint`` is *this row's* content address over every
    write-once field, and it is stored beside the id so the row can be verified
    rather than trusted -- the same discipline as ``captures.capture_fingerprint``
    and ``evidence_context.frame_fingerprint``, and it is written by the
    application and never generated, because a generated column would have to
    reproduce the Python canonicalisation exactly and a divergence would surface
    as an identity that fails to verify (I-1, I-11).

    ``created_at`` is excluded from the fingerprint, and the third unique index
    is on the fingerprint rather than on any pair of facts, for the reason
    ``domain.entity_identity.ENTITY_IDENTITY_MUTABLE_PROJECTION_FIELDS`` gives:
    it is a write clock, so folding it in would make a re-ingest of one anchor at
    a different moment address to something else and FR-022's replay fixed point
    would fail (constitution VII).

    ``anchor_observation_id`` and ``anchor_capture_id`` are NOT NULL defaulting
    to ``''``, which is a **declared absence** and not a hole: they are optional
    in the value type precisely because resolution never sees an observation or a
    capture, and a caller that has them supplies them while a caller that does not
    records a reconstruction hole rather than a fabricated id. ``created_by_
    resolution`` is NOT NULL because who created an anchor is part of the identity
    statement, and ``domain.entity_identity.UNATTRIBUTED_RESOLUTION`` is the
    spelling for "nobody can say" -- a declared absence rather than a null.
    Mirrors migration 019 exactly.
    """

    __tablename__ = "entity_identity"

    entity_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    anchor_mention_id: Mapped[str] = mapped_column(String(64))
    anchor_observation_id: Mapped[str] = mapped_column(String(64), server_default="")
    anchor_capture_id: Mapped[str] = mapped_column(String(64), server_default="")
    created_by_resolution: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    identity_fingerprint: Mapped[str] = mapped_column(String(64))

    __table_args__ = (
        CheckConstraint("tenant_id <> ''", name="ck_entity_identity_tenant"),
        CheckConstraint("anchor_mention_id <> ''", name="ck_entity_identity_anchor_mention"),
        CheckConstraint("created_by_resolution <> ''", name="ck_entity_identity_creator"),
        # A record keyed by anything but an ENT- would never join the decisions
        # that name it, and that is the one failure a value type catches at
        # construction but a bulk loader does not go through.
        CheckConstraint("entity_id LIKE 'ENT-%'", name="ck_entity_identity_entity_prefix"),
        # The anchor, write-once. Half one: one mention anchors at most one entity.
        Index(
            "uq_entity_identity_anchor_mention",
            "tenant_id",
            "anchor_mention_id",
            unique=True,
        ),
        # The anchor, write-once. Half two: one entity has at most one anchor.
        # Absent from the plan's index set and load-bearing anyway -- without it a
        # second anchor for a known entity is invisible to the database, and an
        # anchor that moves silently is the failure FR-001 exists to prevent.
        Index("uq_entity_identity_entity", "tenant_id", "entity_id", unique=True),
        # Idempotency at the database rather than only in the in-memory store
        # (I-11): re-binding one anchor is one row however often it happens, and
        # two records differing on any write-once field are a conflict. Tenant
        # leads because the address is tenant-scoped (constitution IV).
        Index(
            "uq_entity_identity_fingerprint",
            "tenant_id",
            "identity_fingerprint",
            unique=True,
        ),
    )


class ResolutionDecisionRow(Base):
    """One resolution's durable record: what was decided, and the whole reasoning (FR-003).

    The platform knew how to *make* a decision and could not say why it had made
    one. ``RES-`` was a content address of a value that lived in memory for the
    length of a batch, and ``merged_mentions``, the surviving candidates, the
    per-candidate compatibility reasons, the corroboration, the collective
    outcome and the verdict were all unrecorded -- so re-running resolution next
    week produced a new ``RES-`` with no way to tell whether it had reasoned the
    same way (spec D2). This table is that record, and it carries every field
    the value type carries, so the row is a faithful image rather than a summary.

    **Append-only, and the schema says so by having no way to say otherwise.**
    Growth of knowledge adds a row that supersedes an earlier one; there is no
    revision column, no status and no state, because a decision is never edited
    and a schema that could express an edit would eventually be used for one
    (US3).

    **The primary key is the resolver's own ``RES-``, never a digest of this
    row.** ``record_fingerprint`` is the second address -- this record's own
    content digest over every reasoning field, stored so a tampered row cannot
    load -- but it is *not* the key, and a migration that computed the key from
    the row would silently fork from the machine's ids: every ``ENT-``/``RES-``
    pair in the platform would stop joining, and the divergence would be invisible
    until a reconstruction came back empty. The resolver owns that address and
    this table carries it verbatim (I-1, I-11).

    **Ambiguous and unresolved decisions are rows too**, which is what makes
    SC-2 possible. ``entity_ref`` is then empty -- faithfully, because the
    resolver declined to name an entity and a record that invented one would be
    the silent coin-flip the architecture forbids -- and what links such a
    decision to an entity is ``supersedes``, which is the reason the second index
    exists. ``entity_ref`` is NOT NULL defaulting to ``''`` for that reason: the
    absence is a *stated* absence, and it is what makes those rows findable in
    the same index as the ones that did name an entity.

    **The projection columns are JSONB because the projections are already
    plain values.** ``merged_mentions``, ``considered``, ``surviving``,
    ``scored``, ``normalization``, ``notes``, ``reasons``, ``blocked_out`` and
    ``evidence`` are ordered tuples, and the ordering is load-bearing: ``reasons``
    is the order the compatibility layers produced them in, and a reordering
    would change the address of a decision whose reasoning did not change. A
    sequence is the right shape for that; a JSON array preserves it where a
    normalised join table would have to earn it back. ``blocking``,
    ``collective`` and ``hypothesis`` are nullable because the machine may have
    run no collective pass at all, and an empty object would read as "ran and
    found nothing" (FR-004).

    ``decided_at`` is excluded from ``record_fingerprint`` and from the unique
    index, for the reason ``RESOLUTION_DECISION_MUTABLE_PROJECTION_FIELDS`` gives:
    it is a write clock, and folding it in would make an identical decision run
    next week address to something other than this week's (constitution VII,
    FR-022). It is a column and it is the tiebreak in the history order, and
    ``confidence`` is checked into ``0.0..1.0`` because
    :func:`semantic.resolution.ResolutionDecision` clamps it there and a
    confidence outside the range is a corrupt row rather than a surprising one.
    Mirrors migration 019 exactly.
    """

    __tablename__ = "resolution_decision"

    resolution_decision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    record_fingerprint: Mapped[str] = mapped_column(String(64))
    tenant_id: Mapped[str] = mapped_column(String(36))
    mention_id: Mapped[str] = mapped_column(String(64))
    surface: Mapped[str] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(String(16))
    entity_ref: Mapped[str] = mapped_column(String(64), server_default="")
    anchor_mention_id: Mapped[str] = mapped_column(String(64), server_default="")
    anchor_key: Mapped[str] = mapped_column(Text, server_default="")
    merged_mentions: Mapped[list] = mapped_column(JSONB)
    considered: Mapped[list] = mapped_column(JSONB)
    surviving: Mapped[list] = mapped_column(JSONB)
    scored: Mapped[list] = mapped_column(JSONB)
    corroboration: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float)
    confidence_parts: Mapped[list] = mapped_column(JSONB)
    normalization: Mapped[list] = mapped_column(JSONB)
    notes: Mapped[list] = mapped_column(JSONB)
    resolution_scope_id: Mapped[str] = mapped_column(String(64), server_default="")
    operator_ref: Mapped[str] = mapped_column(String(64), server_default="")
    normalization_version: Mapped[str] = mapped_column(String(32), server_default="")
    ontology_version: Mapped[str] = mapped_column(String(64), server_default="")
    regime_id: Mapped[str] = mapped_column(String(64), server_default="")
    reasons: Mapped[list] = mapped_column(JSONB)
    blocked_out: Mapped[list] = mapped_column(JSONB)
    evidence: Mapped[list] = mapped_column(JSONB)
    blocking: Mapped[dict | None] = mapped_column(JSONB)
    collective: Mapped[dict | None] = mapped_column(JSONB)
    hypothesis: Mapped[dict | None] = mapped_column(JSONB)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    supersedes: Mapped[list] = mapped_column(JSONB)

    __table_args__ = (
        CheckConstraint("tenant_id <> ''", name="ck_resolution_decision_tenant"),
        CheckConstraint("mention_id <> ''", name="ck_resolution_decision_mention"),
        # The resolver mints this and nothing else may, so the prefix is the whole
        # of the guarantee at the storage layer: a row keyed by a digest of
        # itself would be well-formed here and would join to nothing anywhere.
        CheckConstraint(
            "resolution_decision_id LIKE 'RES-%'",
            name="ck_resolution_decision_id_prefix",
        ),
        # A closed vocabulary, and a fifth verdict must not be mistakable for one
        # of four. The value type refuses an unknown one for the same reason.
        CheckConstraint(
            "verdict IN ('resolved', 'ambiguous', 'unresolved', 'conflicted')",
            name="ck_resolution_decision_verdict",
        ),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_resolution_decision_confidence",
        ),
        # The reconstruction hot path's ordered read: every decision about one
        # entity, oldest first, with the timestamp in the key so the order is the
        # index's order rather than a sort. The empty-string rows are in it too,
        # which is what lets "the passes that named no entity" be found.
        Index("ix_resolution_decision_entity", "tenant_id", "entity_ref", "decided_at"),
        # The reverse edge, and the reason SC-2 is reachable at all. A decision
        # that named no entity cannot be filed under one without a record lying
        # about what the resolver concluded, so `history_for` walks `supersedes`
        # in both directions: backwards from a root to what it revised, forwards
        # to the successors that either name this entity or name none. Without
        # this index the ambiguous and unresolved passes in an entity's history
        # are unreachable, which is exactly the requirement they exist to meet.
        Index("ix_resolution_decision_supersedes", "tenant_id", "supersedes"),
        # Idempotency at the database, decided on the content address rather than
        # on row equality: the same reasoning about the same mention is one
        # decision however often it is replayed, and a *different* record under
        # one address is a conflict rather than an overwrite (FR-003, I-11).
        Index(
            "uq_resolution_decision_fingerprint",
            "tenant_id",
            "record_fingerprint",
            unique=True,
        ),
    )


class SemanticRegimeRow(Base):
    """The instruments in play when one assertion was read, as a durable row (FR-014).

    The regime was structurally present and permanently unevaluated: ``regime_id``
    was written in memory by the semantic path and persisted in **no** table, so
    every compatibility check against a candidate's regime returned
    ``UNEVALUATED`` -- on the golden path, on every run (spec D6). The fix the
    spec names is to *supply the input, not to stop reporting the absence*, and
    this table is that input. Reporting the absence was correct;
    :func:`semantic.resolution.analyse_candidate` emits ``regime_unevaluated``
    exactly when one side of the comparison carries no regime, and that branch is
    still the honest answer for a record that names none.

    **Two-level identity again, and the direction is the same as everywhere
    else.** ``regime_id`` is :class:`semantic.regime.SemanticRegime`'s own content
    address, carried verbatim and never re-derived here.
    ``record_fingerprint`` is *this row's* address, over every identity field and
    neither derived one, so a tampered projection cannot load.

    **The primary key is the bare ``regime_id``; the load-bearing uniqueness is
    UNIQUE ``(tenant_id, regime_id)`` and the two are not the same thing.** The
    store refuses cross-tenant reads precisely because the *pair* is the key:
    ``regime_for`` raises :class:`~domain.entity_identity.CrossTenantRefusal` when
    an id this tenant does not hold is held by another, and that distinction is
    only possible if one tenant can hold a record at an address another tenant
    already uses. A bare primary key would forbid that and silently merge two
    tenants' instruments into one address -- the same reasoning that makes
    ``entity_identity`` carry UNIQUE ``(tenant_id, entity_id)``, and the same
    discipline ``captures`` states for ``uq_capture_fingerprint``.

    **Two read paths, and two indexes, and no third.**
    ``(tenant_id, regime_id)`` is the resolution hot path -- the regime named by
    the ``regime_id`` on a candidate, which on the golden path is what turns
    ``regime_unevaluated`` into ``regime_compatible`` (FR-015, D6).
    ``(tenant_id, context_ref, recorded_at DESC, regime_id)`` is the
    reconstruction hot path -- "what did we believe when we read this frame?" --
    with ``recorded_at`` inside the key so the "current" regime is an
    index-ordered ``LIMIT 1`` rather than a sort, and ``regime_id`` last so the
    tiebreak is deterministic in every process (constitution VI). The second index
    is why ``recorded_at`` is here in a *non-unique* key and is absent from the
    unique one: a plain index orders, a unique index constrains, and a write clock
    in a unique key would make replay non-deterministic (constitution VII).

    ``instruments`` is a stored projection of
    :meth:`semantic.regime.SemanticRegime.instruments` -- the single most useful
    query on a regime, "what was in play here?", which a method answers only for a
    regime somebody still holds in memory. It is verified against the fields it
    projects at construction, so it cannot drift into a second opinion, and
    ``semantic.regime_store.RegimeStore.unresolved_reads`` is the count that keeps
    FR-015's "MUST be counted" mechanical: a run whose count is zero executed its
    regime, and there is no code path that produces a substitute regime instead
    (FR-016).

    ``recorded_at`` is nullable because
    :attr:`semantic.regime.SemanticRegime.recorded_at` is: an unrecorded time is an
    absence rather than a minimum, and it sorts last in the recency order rather
    than displacing a dated regime. Every other field is NOT NULL because the
    regime's own ``__post_init__`` canonicalises them to text and an empty
    reference means "no instrument of that kind was bound", which is a real and
    different situation from having no regime at all. ``commitment`` is checked
    against its three rungs rather than being an ``Enum`` column, matching how the
    recent revisions spell their categorical columns: a CHECK renders identically
    in ``create_all`` and in the migration and a ``sa.Enum`` does not, and the rung
    is a platform vocabulary the platform must be able to *order* to refuse a
    downgrade. ``localization``, ``language`` and ``temporal_frame_ref`` are
    references and not copies of the parent frame's values, because copying them
    would create two homes for one fact and a second thing to drift.
    Mirrors migration 019 exactly.
    """

    __tablename__ = "semantic_regime"

    regime_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    context_ref: Mapped[str] = mapped_column(String(64))
    profile_ref: Mapped[str] = mapped_column(String(96))
    profile_version: Mapped[str] = mapped_column(String(32))
    ontology_version: Mapped[str] = mapped_column(String(64))
    mapping_set_id: Mapped[str] = mapped_column(String(64))
    mapping_set_version: Mapped[str] = mapped_column(String(32))
    validation_profile: Mapped[str] = mapped_column(String(64))
    policy_snapshot_ref: Mapped[str] = mapped_column(String(96))
    operator_ref: Mapped[str] = mapped_column(String(64))
    localization: Mapped[str] = mapped_column(String(128))
    language: Mapped[str] = mapped_column(String(16))
    temporal_frame_ref: Mapped[str] = mapped_column(String(64))
    supersedes: Mapped[str] = mapped_column(String(128), server_default="")
    commitment: Mapped[str] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(Text, server_default="")
    instruments: Mapped[list] = mapped_column(JSONB)
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    record_fingerprint: Mapped[str] = mapped_column(String(64))

    __table_args__ = (
        CheckConstraint("tenant_id <> ''", name="ck_semantic_regime_tenant"),
        # The three rungs of the platform's own commitment ladder. A fourth must
        # not be mistakable for one of three, and the rung has to be orderable to
        # refuse a downgrade -- which is why it is a closed CHECK rather than free
        # text.
        CheckConstraint(
            "commitment IN ('uncommitted', 'typed', 'mapped')",
            name="ck_semantic_regime_commitment",
        ),
        # The resolution hot path's key. UNIQUE rather than the bare primary key,
        # because the pair is the store's key: the cross-tenant refusal exists
        # only if two tenants may hold different records at the same address
        # (constitution IV, FR-005).
        Index("uq_semantic_regime_tenant_address", "tenant_id", "regime_id", unique=True),
        # The reconstruction hot path: the regime in force for this frame, as an
        # index-ordered maximum. `recorded_at` is in the key so the latest is
        # readable without a sort, and `regime_id` last as the deterministic
        # tiebreak two processes must agree on (constitution VI).
        Index(
            "ix_semantic_regime_current",
            "tenant_id",
            "context_ref",
            desc("recorded_at"),
            "regime_id",
        ),
        # Idempotency at the database rather than only in the in-memory store
        # (I-11). `recorded_at` is deliberately absent from this key: a re-ingest
        # of one regime at a different moment is the same write, and a write clock
        # in a unique key would make it a different one (constitution VII, FR-022).
        Index(
            "uq_semantic_regime_fingerprint",
            "tenant_id",
            "record_fingerprint",
            unique=True,
        ),
    )


# ---------------------------------------------------------------------------
# Feature 019 — the universal relation extraction substrate.
#
# Three tables, and the reason each one exists is a gap rather than a convenience.
#
# ``relation_candidate`` is the first durable home for a
# :class:`domain.relation_candidate.RelationCandidate`. Until now a candidate existed only
# in memory and reached the database only by becoming a claim, so a hypothesis nobody
# admitted had nowhere to be recorded — and a platform that cannot store a rejected or an
# unresolved hypothesis cannot show its work. SC-B is this table: a candidate with no claim
# survives.
#
# ``relation_signal`` is below the candidate rather than beside it. A signal is what a
# producer *saw*; a candidate is an assembled reading of one or more of them. Storing only
# the candidate would throw away the observations, and FR-034's independence count is
# computed over observations — so a claim that three sources corroborate would have to
# take that on trust from a single row.
#
# ``source_temporal_observation`` is a table rather than columns on ``captures`` for the
# reason CD-5 gives: a registrar's acceptance instant is a fact about the world and a
# capture is a record of an act of retrieval. One document may state several instants, each
# at its own precision, and an index observation and a publication are not the same kind of
# fact.
#
# **Every id column here is `String(64)`, and the reason is measured rather than
# assumed (CD-3).** ``CAND-`` and ``CNDR-`` are each 37 characters with a 128-bit truncated
# SHA-256, so the platform-wide `VARCHAR(36)` would cut the last hex digit off every
# candidate id. 64 leaves room for a wider digest or a longer prefix without a second
# migration, and a column that is too wide costs nothing while one that is too narrow
# corrupts an address.
# ---------------------------------------------------------------------------


class RelationCandidateRow(Base):
    """One durable reading of one relation hypothesis (feature 019, T019, SC-B).

    Keyed by ``candidate_id`` - the *revision* address, ``CNDR-`` - not by the logical
    ``CAND-``, because a row is one reading. The logical id is carried as a column so that
    "what did we make of this hypothesis?" is one indexed read rather than a full scan
    over every reading ever taken, which is the question FR-039 makes unavoidable the
    moment a surface can be resolved later.

    ``relation_ref`` is nullable and ``relation_surface`` is not optional, which is CD-6 at
    the storage layer: an untyped relation is storable, keeps the words that produced it,
    and is distinguishable from a row nobody wrote. A CHECK keeps the pair honest in the
    same way one direction only, matching
    :class:`domain.temporal_observation.SourceTemporalObservation` - a row may claim a
    type and no surface, but never a surface and no way to say whether it was resolved.
    """

    __tablename__ = "relation_candidate"

    candidate_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    logical_candidate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)

    subject_mention_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    object_mention_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    arity_mode: Mapped[str] = mapped_column(String(16), nullable=False)

    relation_ref: Mapped[str | None] = mapped_column(String(96))
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    relation_surface: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    predicate_hypothesis: Mapped[str] = mapped_column(String(64), nullable=False)
    predicate_state: Mapped[str] = mapped_column(String(16), nullable=False)

    context_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    semantic_regime_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_status: Mapped[str] = mapped_column(String(16), nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(32), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    extraction_rule_id: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    investigation_id: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    recorded_by: Mapped[str] = mapped_column(String(128), nullable=False, server_default="")

    observation_refs: Mapped[list | None] = mapped_column(JSONB)
    evidence_refs: Mapped[list | None] = mapped_column(JSONB)
    trigger_span: Mapped[dict | None] = mapped_column(JSONB)
    supporting_spans: Mapped[list | None] = mapped_column(JSONB)
    temporal_hypothesis: Mapped[dict | None] = mapped_column(JSONB)
    role_assignments: Mapped[list | None] = mapped_column(JSONB)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_relation_candidate_tenant", "tenant_id"),
        # The "what did we make of this hypothesis?" read, and the one that grows with
        # readings rather than with hypotheses.
        Index("ix_relation_candidate_logical", "tenant_id", "logical_candidate_id"),
        # Pair lookup: the assembler groups signals by the pair they share, and the
        # projection asks the same question.
        Index("ix_relation_candidate_pair", "tenant_id", "subject_mention_ref", "object_mention_ref"),
        Index("uq_relation_candidate_address", "tenant_id", "candidate_id", unique=True),
        CheckConstraint("tenant_id <> ''", name="ck_relation_candidate_tenant"),
        CheckConstraint("logical_candidate_id <> ''", name="ck_relation_candidate_logical"),
        CheckConstraint(
            "subject_mention_ref <> object_mention_ref", name="ck_relation_candidate_distinct"
        ),
        # CD-6 at the storage layer, in the same one-direction-only shape the temporal
        # observation uses: a reading may name an operator and no surface, but never a
        # surface and nothing that says whether it was resolved. The row that must not be
        # storable is the one that asserts no predicate at all - and that is refused by the
        # value type, so the database only has to catch a bulk loader that skipped it.
        CheckConstraint(
            "relation_surface <> '' OR relation_ref IS NOT NULL",
            name="ck_relation_candidate_asserts_something",
        ),
        # A candidate naming no context or no regime is a reading that cannot say what
        # frame it was read in or which instruments interpreted it, and both are
        # references somebody else's decision (FR-015, FR-016).
        CheckConstraint("context_ref <> ''", name="ck_relation_candidate_context"),
        CheckConstraint("semantic_regime_ref <> ''", name="ck_relation_candidate_regime"),
        # Closed vocabularies, checked rather than trusted. A row carrying a fifth
        # disposition or a fourth resolution state is a corrupt row, and a bulk loader
        # that never called the value type is exactly how one arrives.
        CheckConstraint(
            _in("candidate_status", CandidateStatus), name="ck_relation_candidate_status"
        ),
        CheckConstraint(
            _in("arity_mode", RelationArityMode), name="ck_relation_candidate_arity"
        ),
        CheckConstraint(
            _in("predicate_state", PredicateResolutionState),
            name="ck_relation_candidate_predicate_state",
        ),
    )


class RelationSignalRow(Base):
    """One observation a producer made (feature 019, T019, FR-019, FR-034).

    A signal has no entity, no relation status and no admission verdict, and the absence of
    those columns is the point: a table that could record them would invite a producer to
    fill them in, and a producer that writes ``candidate_status`` is a producer that has
    started deciding.

    ``producer_confidence`` is stored but is **not** part of ``signal_id``'s material -
    the value type already excludes it, and the column is here so a reader can see how sure
    the producer was without that certainty being able to manufacture corroboration.

    ``neighbourhood`` is a required JSONB column, not an optional one. FR-041…FR-043 make a
    producer's extent load-bearing, and a nullable extent is an extent nobody stated.
    """

    __tablename__ = "relation_signal"

    signal_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)

    subject_mention_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    object_mention_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    signal_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    direction: Mapped[str] = mapped_column(String(24), nullable=False)

    relation_ref: Mapped[str | None] = mapped_column(String(96))
    relation_surface: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    predicate_hypothesis: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    predicate_state: Mapped[str] = mapped_column(String(16), nullable=False)

    producer_ref: Mapped[str] = mapped_column(String(96), nullable=False, server_default="")
    producer_version: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    context_ref: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    semantic_regime_ref: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    capture_ref: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")

    neighbourhood: Mapped[dict] = mapped_column(JSONB, nullable=False)
    trigger_span: Mapped[dict | None] = mapped_column(JSONB)
    supporting_spans: Mapped[list | None] = mapped_column(JSONB)
    stated_axes: Mapped[list | None] = mapped_column(JSONB)
    extra: Mapped[dict | None] = mapped_column(JSONB)
    producer_confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    signal_ordinal: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_relation_signal_tenant", "tenant_id"),
        # The assembler's grouping key, and the index that keeps assembly from degrading
        # into a scan as producers multiply.
        Index(
            "ix_relation_signal_pair",
            "tenant_id",
            "subject_mention_ref",
            "object_mention_ref",
        ),
        # Which observations back one candidate, and FR-034's independence count read
        # without touching the candidates table at all.
        Index("ix_relation_signal_producer", "tenant_id", "producer_ref"),
        CheckConstraint("tenant_id <> ''", name="ck_relation_signal_tenant"),
        CheckConstraint(
            "relation_surface <> '' OR relation_ref IS NOT NULL",
            name="ck_relation_signal_asserts_something",
        ),
        CheckConstraint(
            "producer_confidence >= 0 AND producer_confidence <= 1",
            name="ck_relation_signal_confidence",
        ),
        CheckConstraint("subject_mention_ref <> object_mention_ref", name="ck_relation_signal_distinct"),
        # The kinds are the platform's whole capacity for noticing a relation, so they are
        # stated in the schema where a reviewer reads them rather than derived from
        # somewhere they would look incidental. `negation` being here is load-bearing:
        # without it, "Acme did not acquire Beta" is either dropped - losing an observed
        # fact - or recorded as an acquisition, which is a lie with a schema.
        CheckConstraint(_in("signal_kind", SignalKind), name="ck_relation_signal_kind"),
        # `ambiguous` is a member because a producer that found a marker it could read two
        # ways must be able to say so here too; a column that could only hold a resolved
        # direction would push the choice into the producer, which is the fabrication CD-6
        # exists to prevent.
        CheckConstraint(_in("direction", DirectionHypothesis), name="ck_relation_signal_direction"),
        CheckConstraint(
            _in("predicate_state", PredicateResolutionState),
            name="ck_relation_signal_predicate_state",
        ),
    )


class SourceTemporalObservationRow(Base):
    """One instant a source stated (feature 019, T019, T015, CD-5, FR-018).

    The columns are grouped the way the value type is, and one of them carries more weight
    than its type suggests. :attr:`stated_value` is a timestamptz, which can hold only one
    of the two things a stated fact is: *when*, and *how precisely*. The answer to the
    second is :attr:`precision` plus the verbatim :attr:`raw_value`, and a loader that
    inserted a day-precision date as a timestamptz without either would leave a reader
    unable to tell an observed midnight from a stated one. Both are NOT NULL for a row
    that carries a value, which is what makes the check below possible.

    ``capture_ref`` is NOT NULL and indexed: a stated instant with no retrieval behind it
    cannot be checked against anything anybody actually fetched, and an unlinked row would
    be exactly that.
    """

    __tablename__ = "source_temporal_observation"

    observation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    capture_ref: Mapped[str] = mapped_column(String(64), nullable=False)

    temporal_axis: Mapped[str] = mapped_column(String(24), nullable=False)
    stated_value: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stated_value_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_value: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    precision: Mapped[str] = mapped_column(String(16), nullable=False)
    basis: Mapped[str] = mapped_column(String(24), nullable=False)
    evidence_location: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_temporal_observation_tenant", "tenant_id"),
        # The retrieval a fact was read from. Not a foreign key because `captures` is
        # written by the same migration chain but a temporal observation can legitimately
        # outlive a re-ingest of the capture it came from - the *fact* about the filing
        # does not evaporate because we fetched the index again.
        Index("ix_temporal_observation_capture", "tenant_id", "capture_ref"),
        # "What did this source say about when?" - the query that was impossible before
        # CD-5 and is the reason this table exists.
        Index("ix_temporal_observation_axis", "tenant_id", "temporal_axis"),
        CheckConstraint("tenant_id <> ''", name="ck_temporal_observation_tenant"),
        CheckConstraint("capture_ref <> ''", name="ck_temporal_observation_capture"),
        CheckConstraint("evidence_location <> ''", name="ck_temporal_observation_location"),
        # The pair that keeps a stated emptiness a stated emptiness: an absent basis with
        # a value, or a value with no basis saying so, is a corrupt row.
        CheckConstraint(
            "basis = 'absent' OR stated_value IS NOT NULL",
            name="ck_temporal_observation_value_present",
        ),
        CheckConstraint(
            "stated_value IS NULL OR basis <> 'absent'",
            name="ck_temporal_observation_absent_basis",
        ),
        # A range's open end cannot precede its start, and cannot exist without one.
        CheckConstraint(
            "stated_value_end IS NULL OR stated_value IS NOT NULL",
            name="ck_temporal_observation_range_start",
        ),
        CheckConstraint(
            "stated_value_end IS NULL OR stated_value_end >= stated_value",
            name="ck_temporal_observation_range_order",
        ),
        # The six axes, closed (CD-5). Stated here so a row cannot carry a seventh, and
        # so the open end of `known_from` is a `stated_value_end` on an existing axis
        # rather than an invented axis of its own.
        CheckConstraint(
            _in("temporal_axis", TemporalAxis), name="ck_temporal_observation_axis"
        ),
    )


