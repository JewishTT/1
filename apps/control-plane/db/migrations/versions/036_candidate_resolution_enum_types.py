
"""Install the native PostgreSQL enums used by the legacy candidates table.

Revision ID: 036_candidate_resolution_enum_types
Revises: 035_interpretation_mentions_and_entity_versions

The legacy candidates table predates Alembic and stores state and epistemic_status
as varchar columns. The ORM maps those columns to native PostgreSQL enums. This
revision creates the exact ORM types and converts the legacy columns without
rewriting existing candidate values.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "036_candidate_resolution_enum_types"
down_revision = "035_interpretation_mentions_and_entity_versions"
branch_labels = None
depends_on = None

_CANDIDATE_RESOLUTION = (
    "OPEN",
    "MATCHED",
    "SUPERSEDED",
    "REJECTED",
    "QUARANTINED",
)
_EPISTEMIC_STATUS = (
    "PROVISIONAL",
    "DEFERRED",
    "QUARANTINED",
    "ACCEPTED",
    "REJECTED",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("candidates"):
        raise RuntimeError("legacy candidates table is required before installing interpretation enums")

    candidate_columns = {column["name"]: column for column in inspector.get_columns("candidates")}
    for column_name in ("state", "epistemic_status"):
        if column_name not in candidate_columns:
            raise RuntimeError(f"legacy candidates table is missing required column {column_name!r}")

    candidate_state = postgresql.ENUM(
        *_CANDIDATE_RESOLUTION,
        name="candidateresolutionstate",
        create_type=False,
    )
    epistemic_status = postgresql.ENUM(
        *_EPISTEMIC_STATUS,
        name="epistemicstatus",
        create_type=False,
    )
    candidate_state.create(bind, checkfirst=True)
    epistemic_status.create(bind, checkfirst=True)

    # The legacy bootstrap declares string defaults. Remove each default before
    # changing its column type, then restore the original expression cast to the
    # new enum. Invalid legacy values fail the conversion rather than being hidden.
    for column_name, enum_type in (
        ("state", candidate_state),
        ("epistemic_status", epistemic_status),
    ):
        column = candidate_columns[column_name]
        current_type = column["type"]
        if getattr(current_type, "name", None) == enum_type.name:
            continue
        default = column.get("default")
        if default is not None:
            op.alter_column("candidates", column_name, server_default=None)
        op.alter_column(
            "candidates",
            column_name,
            existing_type=current_type,
            type_=enum_type,
            postgresql_using=f"{column_name}::text::{enum_type.name}",
        )
        if default is not None:
            op.alter_column(
                "candidates",
                column_name,
                server_default=sa.text(f"({default})::{enum_type.name}"),
            )


def downgrade() -> None:
    # The candidates table uses these native types. Dropping them would invalidate
    # the live ORM mapping and break reads/writes against existing candidate records.
    raise RuntimeError(
        "036_candidate_resolution_enum_types is forward-only; preserve candidate state types"
    )
