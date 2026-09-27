"""Alembic migration for relation & evidence graph fabric persistence (feature 016).

Creates the durable substrate for claims, evidence contexts, the schema registry
and lineage traces (FR-042). A relation is not truth: it is a claim carrying its
own provenance, its arity and its evidence grade, and every persisted row keeps
those dimensions separate (constitution IV, I-3). SC-010 requires that this
revision reach the same schema state whether it is applied to a fresh database or
on top of a database that already has revision 015, which is only true if the
revision is additive and forward-only.

Revision ``015_worldline_reconstruction`` is therefore treated as already
released and is never edited: this file is the only place the relation fabric
schema is expressed, and deployments reach it by applying 016 after 015 rather
than by amending a migration that live databases have already run.

Ordering inside ``upgrade`` is deliberate and matches revision 015: create
tables, add columns, backfill, then create indexes. No index is ever built
against a column that does not exist yet, and no unique index is created while
rows that would collide inside it are still unbackfilled. Sections 2 and 3 are
recorded no-ops rather than dropped, so a reader of the file -- and the ordering
test -- can see that "nothing to add" is a decision and not an omission.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "016_relation_evidence_graph"
down_revision = "015_worldline_reconstruction"
branch_labels = None
depends_on = None

# The tables this revision introduces, in creation order. Referenced by the
# no-op sections below so that "there is no column to add" and "there is nothing
# to backfill" are recorded as positive statements about this table set rather
# than as an absence.
_ACTIVE = (
    "evidence_context",
    "relation_claim",
    "relation_claim_revision",
    "relation_schema_version",
    "claim_context_lineage",
)


def _no_new_columns() -> None:
    """Section 2: no existing table gains a column from this revision.

    Every column introduced here belongs to a table in ``_ACTIVE``, which
    section 1 creates whole. A future revision that extends an existing relation
    table -- adding an attribution weight, say -- adds its column here and
    indexes it in section 4, keeping the backfill of that column between them.
    """


def _no_backfill() -> None:
    """Section 3: no historical row needs a value from a new column.

    Recorded as an explicit step because the unique indexes in section 4 are
    created after it. They are unique over columns that only rows written from
    now on can populate, so there is nothing to reconcile first; a revision that
    did add a unique index over a backfilled column would have to run that
    backfill here instead.
    """


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. New tables
    # ------------------------------------------------------------------
    op.create_table(
        "evidence_context",
        sa.Column("context_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("investigation_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("entity_anchor", sa.String(64), nullable=False, server_default=""),
        sa.Column("observation_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("source_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("document_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("segment_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("subject_candidate_ids", postgresql.JSONB(), nullable=False),
        sa.Column("object_candidate_ids", postgresql.JSONB(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("source_family", sa.String(64), nullable=False, server_default=""),
        sa.Column("independence_group", sa.String(64), nullable=False, server_default=""),
        sa.Column("language", sa.String(8), nullable=False, server_default=""),
        sa.Column("location_context", sa.String(128), nullable=False, server_default=""),
        sa.Column("extraction_version", sa.String(32), nullable=False, server_default=""),
        sa.Column("normalization_version", sa.String(32), nullable=False, server_default=""),
        sa.Column("ontology_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("completeness", sa.String(16), nullable=False, server_default="complete"),
        sa.Column("trust_state", sa.String(16), nullable=False, server_default="unverified"),
        sa.Column("policy_snapshot_ref", sa.String(96), nullable=False, server_default=""),
        sa.Column("parent_context_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("frame_fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "relation_claim",
        sa.Column("relation_id", sa.String(64), primary_key=True),
        sa.Column("logical_relation_id", sa.String(64), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("investigation_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("relation_type", sa.String(128), nullable=False),
        sa.Column("arity_mode", sa.String(16), nullable=False),
        sa.Column("subject_ref", sa.String(64), nullable=False),
        sa.Column("object_ref", sa.String(64), nullable=False),
        sa.Column("role_bindings", postgresql.JSONB(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("observed_at", sa.DateTime(timezone=True)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("known_from", sa.DateTime(timezone=True)),
        sa.Column("known_until", sa.DateTime(timezone=True)),
        sa.Column("assertion_refs", postgresql.JSONB(), nullable=False),
        sa.Column("observation_refs", postgresql.JSONB(), nullable=False),
        sa.Column("context_ref", sa.String(64), nullable=False),
        sa.Column("source_independence_groups", postgresql.JSONB(), nullable=False),
        sa.Column("extraction_version", sa.String(32), nullable=False, server_default=""),
        sa.Column("normalization_version", sa.String(32), nullable=False, server_default=""),
        sa.Column("ontology_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("schema_version", sa.String(32), nullable=False, server_default=""),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("evidence_grade", sa.String(16), nullable=False, server_default="ungraded"),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("supersedes", sa.String(64), nullable=False, server_default=""),
        sa.Column("contradicts", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # Append-only revision ledger: a revised claim gets a new relation_id and the
    # same logical_relation_id, so the chain is reconstructed from these rows and
    # the current claim row is never rewritten (I-1, I-3).
    op.create_table(
        "relation_claim_revision",
        sa.Column("revision_row_id", sa.String(96), primary_key=True),
        sa.Column("relation_id", sa.String(64), nullable=False),
        sa.Column("logical_relation_id", sa.String(64), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("context_ref", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("evidence_grade", sa.String(16), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "relation_schema_version",
        sa.Column("schema_row_id", sa.String(96), primary_key=True),
        sa.Column("relation_type", sa.String(128), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("arity_mode", sa.String(16), nullable=False),
        sa.Column("temporal_semantics", sa.String(24), nullable=False),
        sa.Column("admission_rule_id", sa.String(64), nullable=False),
        sa.Column("definition", postgresql.JSONB(), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "claim_context_lineage",
        sa.Column("lineage_id", sa.String(128), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("relation_id", sa.String(64), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("hops", postgresql.JSONB(), nullable=False),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column("first_unresolved_hop", sa.String(24)),
        sa.Column("unresolved_node_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # 2. New columns (none: every table above is new in this revision)
    # ------------------------------------------------------------------
    _no_new_columns()

    # ------------------------------------------------------------------
    # 3. Backfill (none required; the unique indexes below cover columns only
    #    new rows can populate)
    # ------------------------------------------------------------------
    _no_backfill()

    # ------------------------------------------------------------------
    # 4. Indexes (last, so every column they reference already exists)
    # ------------------------------------------------------------------
    op.create_index("ix_evidence_context_tenant", "evidence_context", ["tenant_id"])
    op.create_index(
        "ix_evidence_context_observation",
        "evidence_context",
        ["tenant_id", "observation_id"],
    )
    op.create_index(
        "ix_evidence_context_source",
        "evidence_context",
        ["tenant_id", "source_id"],
    )
    op.create_index(
        "ix_evidence_context_investigation",
        "evidence_context",
        ["tenant_id", "investigation_id"],
    )
    # Content-addressed frames: re-registering an identical context is a no-op
    # rather than a duplicate row, which is what makes the in-memory resolver's
    # register() idempotent against the database.
    op.create_index(
        "uq_evidence_context_fingerprint",
        "evidence_context",
        ["tenant_id", "frame_fingerprint"],
        unique=True,
    )
    op.create_index("ix_relation_claim_tenant", "relation_claim", ["tenant_id"])
    op.create_index(
        "ix_relation_claim_logical",
        "relation_claim",
        ["tenant_id", "logical_relation_id"],
    )
    op.create_index(
        "ix_relation_claim_type",
        "relation_claim",
        ["tenant_id", "relation_type"],
    )
    op.create_index(
        "ix_relation_claim_subject",
        "relation_claim",
        ["tenant_id", "subject_ref"],
    )
    op.create_index(
        "ix_relation_claim_object",
        "relation_claim",
        ["tenant_id", "object_ref"],
    )
    op.create_index("ix_relation_claim_context", "relation_claim", ["context_ref"])
    op.create_index(
        "uq_relation_claim_content",
        "relation_claim",
        ["tenant_id", "content_hash"],
        unique=True,
    )
    op.create_index(
        "ix_relation_claim_revision_logical",
        "relation_claim_revision",
        ["tenant_id", "logical_relation_id", "revision_number"],
        unique=True,
    )
    op.create_index(
        "ix_relation_claim_revision_relation",
        "relation_claim_revision",
        ["relation_id"],
    )
    op.create_index(
        "uq_relation_schema_version",
        "relation_schema_version",
        ["tenant_id", "relation_type", "schema_version"],
        unique=True,
    )
    op.create_index(
        "ix_relation_schema_version_type",
        "relation_schema_version",
        ["tenant_id", "relation_type"],
    )
    op.create_index(
        "ix_claim_context_lineage_relation",
        "claim_context_lineage",
        ["tenant_id", "relation_id", "direction"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_claim_context_lineage_relation", table_name="claim_context_lineage"
    )
    op.drop_index("ix_relation_schema_version_type", table_name="relation_schema_version")
    op.drop_index("uq_relation_schema_version", table_name="relation_schema_version")
    op.drop_index("ix_relation_claim_revision_relation", table_name="relation_claim_revision")
    op.drop_index("ix_relation_claim_revision_logical", table_name="relation_claim_revision")
    op.drop_index("uq_relation_claim_content", table_name="relation_claim")
    op.drop_index("ix_relation_claim_context", table_name="relation_claim")
    op.drop_index("ix_relation_claim_object", table_name="relation_claim")
    op.drop_index("ix_relation_claim_subject", table_name="relation_claim")
    op.drop_index("ix_relation_claim_type", table_name="relation_claim")
    op.drop_index("ix_relation_claim_logical", table_name="relation_claim")
    op.drop_index("ix_relation_claim_tenant", table_name="relation_claim")
    op.drop_index("uq_evidence_context_fingerprint", table_name="evidence_context")
    op.drop_index("ix_evidence_context_investigation", table_name="evidence_context")
    op.drop_index("ix_evidence_context_source", table_name="evidence_context")
    op.drop_index("ix_evidence_context_observation", table_name="evidence_context")
    op.drop_index("ix_evidence_context_tenant", table_name="evidence_context")
    op.drop_table("claim_context_lineage")
    op.drop_table("relation_schema_version")
    op.drop_table("relation_claim_revision")
    op.drop_table("relation_claim")
    op.drop_table("evidence_context")
