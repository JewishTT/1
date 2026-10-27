"""Store validation verdicts and atomically queue admitted graph projections.

Revision ID: 031_relation_claim_projection_outbox
Revises: 030_observation_candidate_hardening
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "031_relation_claim_projection_outbox"
down_revision = "030_observation_candidate_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "relation_claim",
        sa.Column("validation_record", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_table(
        "relation_claim_projection_outbox",
        sa.Column("outbox_id", sa.String(length=96), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("relation_id", sa.String(length=64), nullable=False),
        sa.Column(
            "status", sa.String(length=24), nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "tenant_id", "relation_id",
            name="uq_relation_claim_projection_outbox_claim",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','DISPATCHING','DISPATCHED','FAILED','SKIPPED')",
            name="ck_relation_claim_projection_outbox_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_relation_claim_projection_outbox_attempts"),
    )
    op.create_index(
        "ix_relation_claim_projection_outbox_ready",
        "relation_claim_projection_outbox",
        ["status", "available_at", "lease_expires_at"],
    )


def downgrade() -> None:
    # Validation decisions and their durable projection handoffs are evidence.
    # Removing them silently would make an already-admitted graph unreplayable.
    raise RuntimeError(
        "031_relation_claim_projection_outbox is forward-only; preserve verdicts and outbox rows"
    )
