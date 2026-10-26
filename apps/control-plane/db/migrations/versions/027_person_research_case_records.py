"""Structured case scope and dispatch idempotency records for Feature 034.

Revision ID: 027_person_research_case_records
Revises: 026_person_research_case_runtime

Case metadata is a first-class record, not a research obligation. Dispatch intents
are durable state transitions bound to tenant, case, scope, policy and action digest.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "027_person_research_case_records"
down_revision = "026_person_research_case_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "person_case_metadata",
        sa.Column("case_id", sa.String(128), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("case_id", name="pk_person_case_metadata"),
        sa.CheckConstraint("case_id <> ''", name="ck_person_case_metadata_case"),
        sa.CheckConstraint("tenant_id <> ''", name="ck_person_case_metadata_tenant"),
    )
    op.create_index(
        "ix_person_case_metadata_tenant",
        "person_case_metadata",
        ["tenant_id", "case_id"],
    )

    op.create_table(
        "person_case_dispatch_intents",
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("case_id", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("scope_digest", sa.String(80), nullable=False),
        sa.Column("policy_digest", sa.String(80), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint(
            "tenant_id", "case_id", "idempotency_key",
            name="pk_person_case_dispatch_intents",
        ),
        sa.UniqueConstraint("run_id", name="uq_person_case_dispatch_run"),
        sa.CheckConstraint("tenant_id <> ''", name="ck_person_case_dispatch_tenant"),
        sa.CheckConstraint("case_id <> ''", name="ck_person_case_dispatch_case"),
        sa.CheckConstraint("idempotency_key <> ''", name="ck_person_case_dispatch_key"),
        sa.CheckConstraint(
            "length(scope_digest) = 71 AND scope_digest LIKE 'sha256:%'",
            name="ck_person_case_dispatch_scope_digest",
        ),
        sa.CheckConstraint(
            "length(policy_digest) = 71 AND policy_digest LIKE 'sha256:%'",
            name="ck_person_case_dispatch_policy_digest",
        ),
    )
    op.create_index(
        "ix_person_case_dispatch_intents_case",
        "person_case_dispatch_intents",
        ["tenant_id", "case_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_person_case_dispatch_intents_case",
        table_name="person_case_dispatch_intents",
    )
    op.drop_table("person_case_dispatch_intents")
    op.drop_index("ix_person_case_metadata_tenant", table_name="person_case_metadata")
    op.drop_table("person_case_metadata")
