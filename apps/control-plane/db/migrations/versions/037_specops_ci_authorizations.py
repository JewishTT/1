"""Add durable tenant-scoped SpecOps&CI authorization records.

Revision ID: 037_specops_ci_authorizations
Revises: 036_candidate_resolution_enum_types

An assessment approval is bound to the exact Intelligence snapshot, subject, target
roster, assessment kinds and validity window. Revocation is append-only metadata;
the original approval is retained for audit.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "037_specops_ci_authorizations"
down_revision = "036_candidate_resolution_enum_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("specops_ci_authorizations"):
        return

    op.create_table(
        "specops_ci_authorizations",
        sa.Column("authorization_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("subject_entity_id", sa.String(length=64), nullable=False),
        sa.Column("source_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("approved_by", sa.String(length=128), nullable=False),
        sa.Column("approval_ref", sa.String(length=256), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_hops", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "allowed_entity_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "allowed_assessments",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.String(length=128), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("tenant_id <> ''", name="ck_specops_ci_auth_tenant"),
        sa.CheckConstraint("approved_by <> ''", name="ck_specops_ci_auth_approver"),
        sa.CheckConstraint("approval_ref <> ''", name="ck_specops_ci_auth_approval_ref"),
        sa.CheckConstraint("expires_at > issued_at", name="ck_specops_ci_auth_window"),
        sa.CheckConstraint("max_hops BETWEEN 0 AND 8", name="ck_specops_ci_auth_hops"),
        sa.CheckConstraint(
            "jsonb_typeof(allowed_entity_ids) = 'array' AND jsonb_array_length(allowed_entity_ids) > 0",
            name="ck_specops_ci_auth_entities",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(allowed_assessments) = 'array' AND jsonb_array_length(allowed_assessments) > 0",
            name="ck_specops_ci_auth_assessments",
        ),
        sa.PrimaryKeyConstraint("authorization_id", name="pk_specops_ci_authorizations"),
    )
    op.create_index(
        "ix_specops_ci_auth_tenant_expiry",
        "specops_ci_authorizations",
        ["tenant_id", "expires_at"],
    )
    op.create_index(
        "ix_specops_ci_auth_snapshot",
        "specops_ci_authorizations",
        ["tenant_id", "source_snapshot_id"],
    )


def downgrade() -> None:
    # Authorization history is audit material; removing it would erase approvals.
    raise RuntimeError(
        "037_specops_ci_authorizations is forward-only; preserve approval and revocation history"
    )
