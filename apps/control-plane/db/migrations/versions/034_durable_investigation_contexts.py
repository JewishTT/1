"""Put the durable investigation-context store under Alembic ownership.

Revision ID: 034_durable_investigation_contexts
Revises: 033_durable_case_budgets
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "034_durable_investigation_contexts"
down_revision = "033_durable_case_budgets"
branch_labels = None
depends_on = None


def _has_table(bind: sa.engine.Connection, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _ensure_index(
    bind: sa.engine.Connection,
    *,
    name: str,
    table: str,
    columns: list[str],
) -> None:
    existing = {item["name"] for item in sa.inspect(bind).get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, columns)


def upgrade() -> None:
    bind = op.get_bind()
    jsonb = postgresql.JSONB(astext_type=sa.Text())

    # These tables have historically been created as an application-side DDL
    # side effect by PostgresContextStore.ensure_schema(). The durable platform
    # schema must exist before any service or worker starts, including code paths
    # that write through SQLAlchemy directly and never instantiate that store.
    if not _has_table(bind, "investigation_contexts"):
        op.create_table(
            "investigation_contexts",
            sa.Column("context_id", sa.Text(), nullable=False),
            sa.Column("tenant_id", sa.Text(), nullable=False),
            sa.Column("investigation_id", sa.Text(), nullable=False),
            sa.Column("identity_schema", sa.Text(), nullable=False),
            sa.Column("payload", jsonb, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("context_id", name="pk_investigation_contexts"),
        )
    _ensure_index(
        bind,
        name="ix_contexts_tenant",
        table="investigation_contexts",
        columns=["tenant_id", "investigation_id"],
    )

    if not _has_table(bind, "context_revisions"):
        op.create_table(
            "context_revisions",
            sa.Column("context_id", sa.Text(), nullable=False),
            sa.Column("revision_number", sa.Integer(), nullable=False),
            sa.Column("payload", jsonb, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint(
                "context_id",
                "revision_number",
                name="pk_context_revisions",
            ),
        )

    if not _has_table(bind, "research_obligations"):
        op.create_table(
            "research_obligations",
            sa.Column("obligation_id", sa.Text(), nullable=False),
            sa.Column("context_id", sa.Text(), nullable=False),
            sa.Column("tenant_id", sa.Text(), nullable=False),
            sa.Column("payload", jsonb, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("obligation_id", name="pk_research_obligations"),
        )
    _ensure_index(
        bind,
        name="ix_obligations_context",
        table="research_obligations",
        columns=["context_id"],
    )

    if not _has_table(bind, "research_actions"):
        op.create_table(
            "research_actions",
            sa.Column("action_id", sa.Text(), nullable=False),
            sa.Column("obligation_id", sa.Text(), nullable=False),
            sa.Column("tenant_id", sa.Text(), nullable=False),
            sa.Column("payload", jsonb, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("action_id", name="pk_research_actions"),
        )
    _ensure_index(
        bind,
        name="ix_actions_obligation",
        table="research_actions",
        columns=["obligation_id"],
    )

    if not _has_table(bind, "context_frontiers"):
        op.create_table(
            "context_frontiers",
            sa.Column("context_id", sa.Text(), nullable=False),
            sa.Column("tenant_id", sa.Text(), nullable=False),
            sa.Column("payload", jsonb, nullable=False),
            sa.PrimaryKeyConstraint("context_id", name="pk_context_frontiers"),
        )

    if not _has_table(bind, "context_action_memory"):
        op.create_table(
            "context_action_memory",
            sa.Column("memory_id", sa.Text(), nullable=False),
            sa.Column("obligation_id", sa.Text(), nullable=False),
            sa.Column("tenant_id", sa.Text(), nullable=False),
            sa.Column("payload", jsonb, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("memory_id", name="pk_context_action_memory"),
        )
    else:
        # Compatibility with the original store schema, which named the
        # obligation key context_id even though reads/writes use obligation_id.
        columns = {column["name"] for column in sa.inspect(bind).get_columns("context_action_memory")}
        if "context_id" in columns and "obligation_id" not in columns:
            op.alter_column(
                "context_action_memory",
                "context_id",
                new_column_name="obligation_id",
            )
    _ensure_index(
        bind,
        name="ix_memory_obligation",
        table="context_action_memory",
        columns=["obligation_id"],
    )


def downgrade() -> None:
    # These rows preserve investigation intent, revisions, obligations, action
    # history and durable frontiers. Removing them makes accepted cases
    # unrecoverable, so this schema is forward-only.
    raise RuntimeError(
        "034_durable_investigation_contexts is forward-only; preserve context history"
    )
