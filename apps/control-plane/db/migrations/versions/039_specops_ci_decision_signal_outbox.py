"""Add durable, leased Temporal signal outbox for SpecOps&CI decisions.

Revision ID: 039_specops_ci_decision_signal_outbox
Revises: 038_specops_ci_operation_decisions

A committed decision and its signal-delivery intent are written in one transaction.
A relay can recover after API, process or Temporal failures without losing the decision.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "039_specops_ci_decision_signal_outbox"
down_revision = "038_specops_ci_operation_decisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("specops_ci_decision_signal_outbox"):
        return

    op.create_table(
        "specops_ci_decision_signal_outbox",
        sa.Column("outbox_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("operation_id", sa.String(length=64), nullable=False),
        sa.Column("step_id", sa.String(length=64), nullable=False),
        sa.Column("spec_digest", sa.String(length=64), nullable=False),
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("signal_name", sa.String(length=64), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("tenant_id <> ''", name="ck_specops_ci_outbox_tenant"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'DISPATCHING', 'FAILED', 'DISPATCHED')",
            name="ck_specops_ci_outbox_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_specops_ci_outbox_attempts"),
        sa.PrimaryKeyConstraint("outbox_id", name="pk_specops_ci_decision_signal_outbox"),
        sa.UniqueConstraint("decision_id", name="uq_specops_ci_outbox_decision"),
        sa.UniqueConstraint(
            "tenant_id",
            "operation_id",
            "step_id",
            "spec_digest",
            name="uq_specops_ci_outbox_step_digest",
        ),
    )
    op.create_index(
        "ix_specops_ci_outbox_ready",
        "specops_ci_decision_signal_outbox",
        ["status", "available_at", "lease_until"],
    )
    op.create_index(
        "ix_specops_ci_outbox_tenant_operation",
        "specops_ci_decision_signal_outbox",
        ["tenant_id", "operation_id"],
    )


def downgrade() -> None:
    # Delivery evidence is part of the operator-decision audit chain.
    raise RuntimeError(
        "039_specops_ci_decision_signal_outbox is forward-only; preserve delivery history"
    )
