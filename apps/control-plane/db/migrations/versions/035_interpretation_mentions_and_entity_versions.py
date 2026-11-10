"""Create the canonical interpretation mention and entity-version tables.

Revision ID: 035_interpretation_mentions_and_entity_versions
Revises: 034_durable_investigation_contexts
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "035_interpretation_mentions_and_entity_versions"
down_revision = "034_durable_investigation_contexts"
branch_labels = None
depends_on = None


def _ensure_index(
    bind: sa.engine.Connection,
    *,
    name: str,
    table: str,
    columns: list[str],
) -> None:
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes(table)}
    if name not in indexes:
        op.create_index(name, table, columns)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    jsonb = postgresql.JSONB(astext_type=sa.Text())

    # InterpretationBridge persists these canonical rows in the same transaction
    # as Observation, TypeSignal, Entity and relation-candidate evidence. They were
    # declared in the ORM but omitted from the pre-Alembic legacy bootstrap and from
    # every released revision through 034.
    if not inspector.has_table("mentions"):
        op.create_table(
            "mentions",
            sa.Column("mention_id", sa.String(length=36), nullable=False),
            sa.Column(
                "observation_id",
                sa.String(length=36),
                sa.ForeignKey("observations.observation_id"),
                nullable=False,
            ),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column("surface_form", sa.Text(), nullable=False),
            sa.Column("normalized_form", sa.Text(), nullable=True),
            sa.Column("transliteration_variants", jsonb, nullable=True),
            sa.Column("script", sa.String(length=8), nullable=True),
            sa.Column("language", sa.String(length=8), nullable=True),
            sa.Column("normalization_version", sa.String(length=32), nullable=True),
            sa.Column("type_hypothesis", sa.String(length=32), nullable=True),
            sa.Column("extractor_version", sa.String(length=32), nullable=True),
            sa.Column("offsets", jsonb, nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.PrimaryKeyConstraint("mention_id", name="pk_mentions"),
        )
    _ensure_index(
        bind,
        name="ix_mentions_obs",
        table="mentions",
        columns=["observation_id"],
    )
    _ensure_index(
        bind,
        name="ix_mentions_tenant",
        table="mentions",
        columns=["tenant_id"],
    )

    if not inspector.has_table("entity_versions"):
        op.create_table(
            "entity_versions",
            sa.Column("version_id", sa.String(length=36), nullable=False),
            sa.Column(
                "entity_id",
                sa.String(length=36),
                sa.ForeignKey("entities.entity_id"),
                nullable=False,
            ),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("canonical_name", sa.Text(), nullable=True),
            sa.Column("attributes", jsonb, nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.PrimaryKeyConstraint("version_id", name="pk_entity_versions"),
        )
    _ensure_index(
        bind,
        name="ix_entity_versions_entity",
        table="entity_versions",
        columns=["entity_id"],
    )
    _ensure_index(
        bind,
        name="ix_entity_versions_tenant",
        table="entity_versions",
        columns=["tenant_id"],
    )


def downgrade() -> None:
    # These rows are canonical interpretation lineage. Removing them would
    # silently erase which source spans produced a mention and how an entity
    # changed over time, so this migration is forward-only.
    raise RuntimeError(
        "035_interpretation_mentions_and_entity_versions is forward-only; "
        "preserve canonical interpretation lineage"
    )
