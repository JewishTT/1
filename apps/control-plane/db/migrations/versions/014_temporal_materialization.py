"""Alembic migration for temporal materialization persistence (feature 014)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "014_temporal_materialization"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "temporal_materialization_runs",
        sa.Column("run_id", sa.String(96), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("source_cut_id", sa.String(96), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("projection_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("integrity_fingerprint", sa.String(64)),
        sa.Column("payload", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_temporal_run_generation",
        "temporal_materialization_runs",
        ["tenant_id", "entity_id", "projection_generation"],
        unique=True,
    )
    op.create_table(
        "temporal_window_revisions",
        sa.Column("revision_id", sa.String(96), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("source_cut_id", sa.String(96), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lifecycle_state", sa.String(24), nullable=False),
        sa.Column("payload", postgresql.JSONB()),
    )
    op.create_index(
        "uq_temporal_window_revision",
        "temporal_window_revisions",
        ["tenant_id", "entity_id", "window_start", "revision_number"],
        unique=True,
    )
    op.create_table(
        "temporal_history_publications",
        sa.Column("publication_id", sa.String(96), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("source_cut_id", sa.String(96), nullable=False),
        sa.Column("projection_generation", sa.Integer(), nullable=False),
        sa.Column("integrity_fingerprint", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB()),
        sa.Column("published_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "uq_temporal_publication_generation",
        "temporal_history_publications",
        ["tenant_id", "entity_id", "projection_generation"],
        unique=True,
    )
    op.create_table(
        "temporal_materialization_audit",
        sa.Column("audit_id", sa.String(96), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("temporal_materialization_audit")
    op.drop_index("uq_temporal_publication_generation", table_name="temporal_history_publications")
    op.drop_table("temporal_history_publications")
    op.drop_index("uq_temporal_window_revision", table_name="temporal_window_revisions")
    op.drop_table("temporal_window_revisions")
    op.drop_index("ix_temporal_run_generation", table_name="temporal_materialization_runs")
    op.drop_table("temporal_materialization_runs")
