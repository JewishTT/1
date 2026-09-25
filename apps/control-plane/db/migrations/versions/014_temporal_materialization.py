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
        "materialization_outbox",
        sa.Column("outbox_id", sa.String(96), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("workflow_id", sa.String(128), nullable=False),
        sa.Column("identity", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("uq_materialization_outbox_run", "materialization_outbox", ["tenant_id", "run_id"], unique=True)
    op.create_index("ix_materialization_outbox_ready", "materialization_outbox", ["status", "available_at"])
    op.create_index("ix_materialization_outbox_entity", "materialization_outbox", ["tenant_id", "entity_id"])
    op.create_table(
        "materialization_cursors",
        sa.Column("cursor_id", sa.String(96), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("crawl", sa.String(64), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("result_payload", postgresql.JSONB()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_materialization_cursor_scope",
        "materialization_cursors",
        ["tenant_id", "entity_id", "run_id"],
    )
    op.create_index(
        "uq_materialization_cursor_page",
        "materialization_cursors",
        ["tenant_id", "entity_id", "run_id", "crawl", "page"],
        unique=True,
    )
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
        sa.Column("projection_generation", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lifecycle_state", sa.String(24), nullable=False),
        sa.Column("payload", postgresql.JSONB()),
    )
    op.create_index(
        "uq_temporal_window_revision",
        "temporal_window_revisions",
        ["tenant_id", "entity_id", "window_start", "revision_number", "projection_generation"],
        unique=True,
    )
    op.create_table(
        "temporal_history_heads",
        sa.Column("tenant_id", sa.String(36), primary_key=True),
        sa.Column("entity_id", sa.String(64), primary_key=True),
        sa.Column("projection_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("publication_id", sa.String(96)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
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
    op.drop_index("ix_materialization_outbox_entity", table_name="materialization_outbox")
    op.drop_index("ix_materialization_outbox_ready", table_name="materialization_outbox")
    op.drop_index("uq_materialization_outbox_run", table_name="materialization_outbox")
    op.drop_table("materialization_outbox")
    op.drop_index("uq_materialization_cursor_page", table_name="materialization_cursors")
    op.drop_index("ix_materialization_cursor_scope", table_name="materialization_cursors")
    op.drop_table("materialization_cursors")
    op.drop_table("temporal_materialization_audit")
    op.drop_index("uq_temporal_publication_generation", table_name="temporal_history_publications")
    op.drop_table("temporal_history_publications")
    op.drop_table("temporal_history_heads")
    op.drop_index("uq_temporal_window_revision", table_name="temporal_window_revisions")
    op.drop_table("temporal_window_revisions")
    op.drop_index("ix_temporal_run_generation", table_name="temporal_materialization_runs")
    op.drop_table("temporal_materialization_runs")
