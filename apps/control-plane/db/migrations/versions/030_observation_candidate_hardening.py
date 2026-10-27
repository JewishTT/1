"""Persist relation hypotheses truthfully and make entity-stream replay idempotent.

Revision ID: 030_observation_candidate_hardening
Revises: 029_person_case_artifacts_reports
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "030_observation_candidate_hardening"
down_revision = "029_person_case_artifacts_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PredicateSignature is the sole source of logical_candidate_id. Until an
    # extraction has such a structural signature, the domain intentionally stores
    # an empty logical id and addresses the reading by candidate_id alone.
    op.drop_constraint("ck_relation_candidate_logical", "relation_candidate", type_="check")
    op.add_column(
        "relation_candidate",
        sa.Column(
            "candidate_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    # Existing append-only rows may contain duplicates from old consumer
    # retries. Do not delete/rewrite them, and do not build a unique index over
    # their old dimensions. Only newly keyed source events participate.
    op.add_column(
        "entity_stream",
        sa.Column("source_event_id", sa.String(64), nullable=False, server_default=""),
    )
    op.create_index(
        "uq_entity_stream_source_event",
        "entity_stream",
        ["tenant_id", "source_event_id"],
        unique=True,
        postgresql_where=sa.text("source_event_id <> ''"),
    )


def downgrade() -> None:
    # Candidate and stream rows are durable evidence. Reinstating the prior
    # CHECK would make valid unaddressed candidates unloadable; dropping payloads
    # would erase the record needed for future interpretation. Roll back forward.
    raise RuntimeError(
        "030_observation_candidate_hardening is forward-only: relation candidates "
        "and stream replay identities are durable evidence"
    )
