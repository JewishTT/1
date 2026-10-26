"""Durable processing ledger for immutable observations.

Revision ID: 028_observation_processing_results
Revises: 027_person_research_case_records
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "028_observation_processing_results"
down_revision = "027_person_research_case_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "processing_results",
        sa.Column("processing_result_id", sa.String(64), primary_key=True),
        sa.Column("processing_run_id", sa.String(96), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("investigation_id", sa.String(36)),
        sa.Column("observation_id", sa.String(36), nullable=False),
        sa.Column("capture_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("raw_ref", sa.Text(), nullable=False, server_default=""),
        sa.Column("consumer", sa.String(128), nullable=False),
        sa.Column("consumer_version", sa.String(32), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("derived_ref", sa.Text(), nullable=False, server_default=""),
        sa.Column("locator", sa.Text(), nullable=False, server_default=""),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mention_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("failure_code", sa.String(64), nullable=False, server_default=""),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("normalization", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("interpretation", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "tenant_id", "observation_id", "consumer", "consumer_version",
            name="uq_processing_result_observation_consumer",
        ),
        sa.CheckConstraint("tenant_id <> ''", name="ck_processing_result_tenant"),
        sa.CheckConstraint("observation_id <> ''", name="ck_processing_result_observation"),
        sa.CheckConstraint("consumer <> ''", name="ck_processing_result_consumer"),
        sa.CheckConstraint("consumer_version <> ''", name="ck_processing_result_consumer_version"),
        sa.CheckConstraint(
            "status IN ('processed','skipped_replay','refused')",
            name="ck_processing_result_status",
        ),
        sa.CheckConstraint(
            "record_count >= 0 AND mention_count >= 0",
            name="ck_processing_result_counts",
        ),
    )
    op.create_index(
        "ix_processing_result_tenant_case",
        "processing_results",
        ["tenant_id", "investigation_id", "processed_at"],
    )
    op.create_index(
        "ix_processing_result_status",
        "processing_results",
        ["tenant_id", "status", "processed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_processing_result_status", table_name="processing_results")
    op.drop_index("ix_processing_result_tenant_case", table_name="processing_results")
    op.drop_table("processing_results")
