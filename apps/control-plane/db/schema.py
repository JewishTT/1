"""Postgres operational schema — base models + invariants (T012, T014).

Observation is immutable (I-1, I-5). Mention != Candidate != Entity (I-2).
Assertion != truth (I-3). Entity versions are monotonic (I-4, FR-016).
projection.failure never drops evidence (I-12).
"""

from __future__ import annotations

import enum
from datetime import datetime

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
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


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
    next_schedule_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_frontier_tenant", "tenant_id"),
        Index("ix_frontier_host", "host_key"),
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

    __table_args__ = (Index("ix_mentions_obs", "observation_id"), Index("ix_mentions_tenant", "tenant_id"))


class Candidate(Base):
    __tablename__ = "candidates"

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

    __table_args__ = (
        Index("ix_candidates_tenant", "tenant_id"),
        Index("ix_candidates_state", "state"),
        Index("ix_candidates_epistemic", "epistemic_status"),
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
    candidate_id: Mapped[str | None] = mapped_column(String(36))
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
    candidate_id: Mapped[str | None] = mapped_column(String(36))
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
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

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