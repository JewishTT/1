"""Add append-only, tenant-scoped SpecOps&CI operator decisions.

Revision ID: 038_specops_ci_operation_decisions
Revises: 037_specops_ci_authorizations

Every approval/rejection is bound to the operation digest, exact step, authorization,
snapshot and authenticated admin. A decision is a durable audit record, while the
Temporal signal is only the wake-up mechanism for the waiting workflow.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "038_specops_ci_operation_decisions"
down_revision = "037_specops_ci_authorizations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    table_exists = inspector.has_table("specops_ci_operation_decisions")

    if not table_exists:
        op.create_table(
        "specops_ci_operation_decisions",
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("operation_id", sa.String(length=64), nullable=False),
        sa.Column("authorization_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("spec_digest", sa.String(length=64), nullable=False),
        sa.Column("step_id", sa.String(length=64), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("reviewer_id", sa.String(length=128), nullable=False),
        sa.Column("reviewer_role", sa.String(length=32), nullable=False),
        sa.Column("approval_ref", sa.String(length=256), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("tenant_id <> ''", name="ck_specops_ci_decision_tenant"),
        sa.CheckConstraint("reviewer_id <> ''", name="ck_specops_ci_decision_reviewer"),
        sa.CheckConstraint("reviewer_role = 'admin'", name="ck_specops_ci_decision_role"),
        sa.CheckConstraint("approval_ref <> ''", name="ck_specops_ci_decision_approval_ref"),
        sa.PrimaryKeyConstraint("decision_id", name="pk_specops_ci_operation_decisions"),
        sa.UniqueConstraint(
            "tenant_id",
            "operation_id",
            "step_id",
            "spec_digest",
            name="uq_specops_ci_operation_step_decision",
        ),
    )
        op.create_index(
            "ix_specops_ci_decision_tenant_operation",
            "specops_ci_operation_decisions",
            ["tenant_id", "operation_id"],
        )
        op.create_index(
            "ix_specops_ci_decision_authorization",
            "specops_ci_operation_decisions",
            ["tenant_id", "authorization_id"],
        )
    else:
        # Base.metadata.create_all may have prepared this table in a test/development
        # environment before Alembic reaches this revision. Keep the DB-enforced
        # immutability trigger in place even when the table already exists.
        existing_indexes = {
            item["name"]
            for item in sa.inspect(op.get_bind()).get_indexes(
                "specops_ci_operation_decisions"
            )
        }
        if "ix_specops_ci_decision_tenant_operation" not in existing_indexes:
            op.create_index(
                "ix_specops_ci_decision_tenant_operation",
                "specops_ci_operation_decisions",
                ["tenant_id", "operation_id"],
            )
        if "ix_specops_ci_decision_authorization" not in existing_indexes:
            op.create_index(
                "ix_specops_ci_decision_authorization",
                "specops_ci_operation_decisions",
                ["tenant_id", "authorization_id"],
            )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_specops_ci_decision_mutation()
        RETURNS trigger AS $specops_ci$
        BEGIN
            RAISE EXCEPTION 'SpecOps&CI operator decisions are immutable';
        END;
        $specops_ci$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_specops_ci_decision_immutable
        ON specops_ci_operation_decisions
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_specops_ci_decision_immutable
        BEFORE UPDATE OR DELETE ON specops_ci_operation_decisions
        FOR EACH ROW EXECUTE FUNCTION reject_specops_ci_decision_mutation()
        """
    )


def downgrade() -> None:
    # These decisions are durable approval/rejection evidence and must not be erased.
    raise RuntimeError(
        "038_specops_ci_operation_decisions is forward-only; preserve decision history"
    )
