
"""Install the native PostgreSQL enums used by the legacy candidates table.

Revision ID: 036_candidate_resolution_enum_types
Revises: 035_interpretation_mentions_and_entity_versions

The legacy candidates table predates Alembic and stores state and epistemic_status
as varchar columns. The ORM has always mapped those columns to native PostgreSQL
enums, but no released migration created the types. This revision makes the
database contract explicit without rewriting existing rows.
"""
from __future__ import annotations

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
    # Existing legacy candidate rows remain untouched. The ORM writes these values
    # using PostgreSQL's native enum protocol, so both named types must exist before
    # InterpretationBridge can persist a Candidate.
    postgresql.ENUM(
        *_CANDIDATE_RESOLUTION,
        name="candidateresolutionstate",
        create_type=False,
    ).create(bind, checkfirst=True)
    postgresql.ENUM(
        *_EPISTEMIC_STATUS,
        name="epistemicstatus",
        create_type=False,
    ).create(bind, checkfirst=True)


def downgrade() -> None:
    # The legacy candidates table uses these native types. Dropping them would
    # invalidate the live ORM mapping and break reads/writes against existing rows.
    raise RuntimeError(
        "036_candidate_resolution_enum_types is forward-only; preserve candidate state types"
    )
