"""Create the durable policy-budget ledger when it is not part of the legacy baseline.

Revision ID: 033_durable_case_budgets
Revises: 032_type_signals
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "033_durable_case_budgets"
down_revision = "032_type_signals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Older installations may already have the platform's pre-Alembic budgets
    # table. Preserve it; fresh installations need the ORM-compatible table.
    bind = op.get_bind()
    if sa.inspect(bind).has_table("budgets"):
        return

    op.create_table(
        "budgets",
        sa.Column("budget_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=True),
        sa.Column("limits", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("current_usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("budget_id", name="pk_budgets"),
    )


def downgrade() -> None:
    # Budget rows are durable accounting/reservation state. Dropping the table
    # would erase operational history, so this migration is forward-only.
    raise RuntimeError(
        "033_durable_case_budgets is forward-only; preserve budget accounting state"
    )
