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

    **A promotion is a new row, never an update.** ``assertion_id`` is the digest
    of the *whole* claim -- status, evidence, ``raw_surface`` and ``hypothesis``
    included -- so moving a claim from ``observed`` up to ``validated`` yields a
    different id and both rows survive side by side. That is what makes FR-004
    structural rather than aspirational: the ladder
    ``raw -> surface -> hypothesis -> mapped concept`` is reconstructable from
    these rows alone, with no prior state overwritten to record the newer one.

    ``(tenant_id, entity_ref, type_ref, scope)`` is the *claim's* identity, and it
    is deliberately left unconstrained: a unique constraint over it would forbid
    the very second row a promotion needs. Idempotency comes from the primary key
    instead, which catches "the same claim recorded twice" without catching "the
    same claim promoted". What is indexed is the read path -- every scope of one
    entity (US2) and the entity's whole typing history (US9) -- and two processes
    recording the same claim at the same rung are two pieces of evidence for it,
    so both are kept.

    ``observed_at`` is when the platform learned the claim; ``valid_from`` and
    ``valid_to`` are when it was true. Three separate columns, never merged
    (constitution V). Mirrors migration 018 exactly.
    """

    __tablename__ = "type_assertions"

    assertion_id: Mapped[str] = mapped_column(String(64), primary_key=True)
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
