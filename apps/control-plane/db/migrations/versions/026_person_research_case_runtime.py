"""Durable reservation ledger for Feature 034 (revision 026).

Revision ID: 026_person_research_case_runtime
Revises: 025_context_graph

Reservations are committed before the scheduler can publish an acquisition request.
A reservation is scoped to tenant, case, idempotency key, scope digest and policy digest.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "026_person_research_case_runtime"
down_revision = "025_context_graph"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "person_case_budget_reservations",
        sa.Column("reservation_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("case_id", sa.String(128), nullable=False),
        sa.Column("investigation_id", sa.String(128), nullable=False),
        sa.Column("budget_id", sa.String(36), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("scope_digest", sa.String(80), nullable=False),
        sa.Column("policy_digest", sa.String(80), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("raw_bytes", sa.BigInteger(), nullable=False),
        sa.Column("record_count", sa.BigInteger(), nullable=False),
        sa.Column("concurrency", sa.Integer(), nullable=False),
        sa.Column("wall_seconds", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="RESERVED"),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("reservation_id", name="pk_person_case_budget_reservations"),
        sa.UniqueConstraint(
            "tenant_id", "case_id", "idempotency_key",
            name="uq_person_case_budget_reservation_idempotency",
        ),
        sa.CheckConstraint("tenant_id <> ''", name="ck_person_case_budget_reservation_tenant"),
        sa.CheckConstraint("case_id <> ''", name="ck_person_case_budget_reservation_case"),
        sa.CheckConstraint("budget_id <> ''", name="ck_person_case_budget_reservation_budget"),
        sa.CheckConstraint("request_count > 0", name="ck_person_case_budget_reservation_requests"),
        sa.CheckConstraint("raw_bytes > 0", name="ck_person_case_budget_reservation_bytes"),
        sa.CheckConstraint("record_count > 0", name="ck_person_case_budget_reservation_records"),
        sa.CheckConstraint("concurrency > 0", name="ck_person_case_budget_reservation_concurrency"),
        sa.CheckConstraint("wall_seconds > 0", name="ck_person_case_budget_reservation_wall"),
        sa.CheckConstraint(
            "state IN ('RESERVED', 'PUBLISHED', 'RELEASED', 'FAILED')",
            name="ck_person_case_budget_reservation_state",
        ),
    )
    op.create_index(
        "ix_person_case_budget_reservations_budget_state",
        "person_case_budget_reservations",
        ["budget_id", "state"],
    )
    op.create_index(
        "ix_person_case_budget_reservations_case_scope",
        "person_case_budget_reservations",
        ["tenant_id", "case_id", "scope_digest"],
    )


def downgrade() -> None:
    op.drop_index("ix_person_case_budget_reservations_case_scope", table_name="person_case_budget_reservations")
    op.drop_index("ix_person_case_budget_reservations_budget_state", table_name="person_case_budget_reservations")
    op.drop_table("person_case_budget_reservations")
