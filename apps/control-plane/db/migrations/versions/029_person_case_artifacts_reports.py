"""Durable static case artifacts and evidence-linked completion reports.

Revision ID: 029_person_case_artifacts_reports
Revises: 028_observation_processing_results
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "029_person_case_artifacts_reports"
down_revision = "028_observation_processing_results"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "person_case_artifacts",
        sa.Column("artifact_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("case_id", sa.String(128), nullable=False),
        sa.Column("scope_revision", sa.Integer(), nullable=False),
        sa.Column("capture_id", sa.String(64), nullable=False),
        sa.Column("observation_id", sa.String(36), nullable=False),
        sa.Column("raw_ref", sa.Text(), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("byte_length", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False, server_default="application/octet-stream"),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("caption", sa.Text(), nullable=False, server_default=""),
        sa.Column("artifact_kind", sa.String(32), nullable=False, server_default="static_attachment"),
        sa.Column("uploaded_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("artifact_id", name="pk_person_case_artifacts"),
        sa.UniqueConstraint("tenant_id", "observation_id", name="uq_person_case_artifact_observation"),
        sa.CheckConstraint("tenant_id <> ''", name="ck_person_case_artifact_tenant"),
        sa.CheckConstraint("case_id <> ''", name="ck_person_case_artifact_case"),
        sa.CheckConstraint("content_digest ~ '^[0-9a-f]{64}$'", name="ck_person_case_artifact_digest"),
        sa.CheckConstraint("byte_length > 0", name="ck_person_case_artifact_length"),
        sa.CheckConstraint("filename <> ''", name="ck_person_case_artifact_filename"),
    )
    op.create_index(
        "ix_person_case_artifacts_case",
        "person_case_artifacts",
        ["tenant_id", "case_id", "created_at", "artifact_id"],
    )
    op.create_index(
        "ix_person_case_artifacts_capture",
        "person_case_artifacts",
        ["tenant_id", "capture_id"],
    )

    op.create_table(
        "person_case_reports",
        sa.Column("report_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("case_id", sa.String(128), nullable=False),
        sa.Column("scope_digest", sa.String(71), nullable=False),
        sa.Column("report_digest", sa.String(71), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("report_id", name="pk_person_case_reports"),
        sa.UniqueConstraint("tenant_id", "case_id", "report_digest", name="uq_person_case_report_digest"),
        sa.CheckConstraint("tenant_id <> ''", name="ck_person_case_report_tenant"),
        sa.CheckConstraint("case_id <> ''", name="ck_person_case_report_case"),
        sa.CheckConstraint("length(scope_digest) = 71 AND scope_digest LIKE 'sha256:%'", name="ck_person_case_report_scope_digest"),
        sa.CheckConstraint("length(report_digest) = 71 AND report_digest LIKE 'sha256:%'", name="ck_person_case_report_digest"),
        sa.CheckConstraint("status IN ('COMPLETE','PARTIAL','BLOCKED')", name="ck_person_case_report_status"),
    )
    op.create_index(
        "ix_person_case_reports_case",
        "person_case_reports",
        ["tenant_id", "case_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_person_case_reports_case", table_name="person_case_reports")
    op.drop_table("person_case_reports")
    op.drop_index("ix_person_case_artifacts_capture", table_name="person_case_artifacts")
    op.drop_index("ix_person_case_artifacts_case", table_name="person_case_artifacts")
    op.drop_table("person_case_artifacts")
