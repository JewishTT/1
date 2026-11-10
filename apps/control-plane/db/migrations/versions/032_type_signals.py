"""Persist source-originated type observations independently of assertions.

Revision ID: 032_type_signals
Revises: 031_relation_claim_projection_outbox
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "032_type_signals"
down_revision = "031_relation_claim_projection_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "type_signals",
        sa.Column("signal_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("mention_ref", sa.String(length=36), nullable=False),
        sa.Column("source_vocab", sa.String(length=255), nullable=True),
        sa.Column("surface", sa.Text(), nullable=False),
        sa.Column("structural_path", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("observation_refs", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("evidence_refs", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("producer_ref", sa.String(length=128), nullable=False),
        sa.Column("mapping_candidates", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("tenant_id <> ''", name="ck_type_signal_tenant"),
        sa.CheckConstraint("producer_ref <> ''", name="ck_type_signal_producer"),
    )
    op.create_index(
        "ix_type_signals_mention", "type_signals", ["tenant_id", "mention_ref"]
    )
    op.create_index(
        "ix_type_signals_producer", "type_signals", ["tenant_id", "producer_ref"]
    )


def downgrade() -> None:
    raise RuntimeError(
        "032_type_signals is forward-only; source observations are evidence and must be preserved"
    )
