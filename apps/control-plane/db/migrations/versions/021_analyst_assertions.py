"""Analyst assertions (025 FR-025-077, ADR-0038).

Revision ID: 021_analyst_assertions
Revises: 020_universal_relation_extraction

Why this table exists
---------------------
Manual entities and relations were writable only through the legacy global routes, which
carry no investigation reference. An analyst's statement therefore landed in a pool with no
record of which question prompted it -- and there was nowhere to record *who* asserted it,
*when*, or *on what basis*.

This table stores the statement, not the fact. It is deliberately not a claim, not a
relation and not a revision: promoting an assertion into any of those is evaluation's job,
and doing it on write would let a human statement enter the world model as an admitted fact.

Parity
------
``db.schema.AnalystAssertion`` and this file must emit the same column set and the same
indexes, because the two install paths -- ``Base.metadata.create_all`` for a fresh install
and ``alembic upgrade head`` for an existing one -- must not diverge. ``tests/unit/
test_migration_016_forward_only.py`` style parity checks cover the relation tables; the
column order below is the one ``create_all`` produces for the mapped class.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "021_analyst_assertions"
down_revision = "020_universal_relation_extraction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analyst_assertions",
        sa.Column("assertion_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("entity_ref", sa.String(length=64), nullable=True),
        sa.Column("relation_ref", sa.String(length=64), nullable=True),
        sa.Column("statement", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("basis", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("assertion_id"),
    )
    op.create_index(
        "ix_analyst_assertions_tenant", "analyst_assertions", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_analyst_assertions_investigation",
        "analyst_assertions",
        ["investigation_id"],
        unique=False,
    )
    op.create_index(
        "ix_analyst_assertions_entity", "analyst_assertions", ["entity_ref"], unique=False
    )
    op.create_index(
        "ix_analyst_assertions_relation", "analyst_assertions", ["relation_ref"], unique=False
    )
    op.create_index(
        "ix_analyst_assertions_inv_created",
        "analyst_assertions",
        ["investigation_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    # Forward-only in practice: dropping this table would delete the only record of what an
    # analyst asserted, which is exactly the history the platform promises to keep. The
    # indexes go with it so a partial downgrade cannot leave a table that cannot be queried.
    op.drop_index("ix_analyst_assertions_inv_created", table_name="analyst_assertions")
    op.drop_index("ix_analyst_assertions_relation", table_name="analyst_assertions")
    op.drop_index("ix_analyst_assertions_entity", table_name="analyst_assertions")
    op.drop_index("ix_analyst_assertions_investigation", table_name="analyst_assertions")
    op.drop_index("ix_analyst_assertions_tenant", table_name="analyst_assertions")
    op.drop_table("analyst_assertions")