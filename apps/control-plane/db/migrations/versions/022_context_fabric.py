"""Context fabric persistence (spec 025 §7, §13, §15.3, §33).

Revision ID: 022_context_fabric
Revises: 021_analyst_assertions

Why these tables exist
----------------------
The fabric in ``apps/science/context/`` derives cells, propositions,
contradictions and hypothesis spaces. Before this, those objects existed only for the
duration of a function call: each pass started from nothing, so a contradiction found
on tick 3 was invisible on tick 4 and a cell hierarchy could never deepen past a single
tick. Derivation without persistence is a function, not an engine.

``context_cells`` is the load-bearing one. Cells are the substrate every other
artifact is located against, and ``parent_cell`` is the edge that makes "everything
under X" answerable -- a long investigation deepens by accumulating cells across
ticks, so this table is what turns repeated passes into one growing structure.

``fabric_reports`` stores the whole pass verbatim. Constitution I-12 requires every
projection to be rebuildable from the event log, and I-2 requires every analytical
result to trace to source evidence; keeping the report lets a reader ask *why* the
obligation ledger says what it says without re-deriving it.

Parity
------
``db.schema.ContextCell`` / ``FabricReport`` and this file must emit the same column
set, because the two install paths -- ``create_all`` for a fresh database and
``alembic upgrade head`` for an existing one -- must not diverge.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "022_context_fabric"
down_revision = "021_analyst_assertions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "context_cells",
        # Content-addressed: the cell id is a digest over context, kind, scope and
        # parent, so it is stable across ticks and a re-derived cell overwrites its
        # own row rather than accumulating duplicates.
        sa.Column("cell_id", sa.String(length=64), nullable=False),
        sa.Column("context_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        # The ancestry edge. Nullable for a root cell; indexed because every
        # "everything under X" query is a descent through it.
        sa.Column("parent_cell", sa.String(length=64), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("cell_id"),
        # A context has exactly one cell per identity, and a cell has one parent.
        sa.UniqueConstraint("context_id", "cell_id", name="uq_context_cells_identity"),
    )
    op.create_index("ix_context_cells_context", "context_cells", ["context_id"], unique=False)
    op.create_index("ix_context_cells_parent", "context_cells", ["parent_cell"], unique=False)
    op.create_index("ix_context_cells_tenant", "context_cells", ["tenant_id"], unique=False)

    op.create_table(
        "fabric_reports",
        sa.Column("report_id", sa.String(length=64), nullable=False),
        sa.Column("context_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        # The revision this pass was computed at, so a report can be tied to the
        # exact state it reasoned over rather than to "some" state.
        sa.Column("revision_id", sa.String(length=64), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("report_id"),
    )
    op.create_index("ix_fabric_reports_context", "fabric_reports", ["context_id"], unique=False)
    op.create_index("ix_fabric_reports_tenant", "fabric_reports", ["tenant_id"], unique=False)
    op.create_index(
        "ix_fabric_reports_context_created",
        "fabric_reports",
        ["context_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "context_propositions",
        sa.Column("proposition_id", sa.String(length=64), nullable=False),
        sa.Column("context_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        # The four-valued state is stored as its own column, never as a boolean
        # pair folded into a score. §13.4: truth_state and confidence are
        # independent, and collapsing them here would lose the distinction at the
        # only place it was still intact.
        sa.Column("truth_state", sa.String(length=16), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("proposition_id"),
    )
    op.create_index(
        "ix_context_propositions_context", "context_propositions", ["context_id"], unique=False
    )
    op.create_index(
        "ix_context_propositions_truth", "context_propositions", ["truth_state"], unique=False
    )

    op.create_table(
        "context_contradictions",
        sa.Column("contradiction_id", sa.String(length=64), nullable=False),
        sa.Column("proposition_id", sa.String(length=64), nullable=False),
        sa.Column("context_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("contradiction_id"),
    )
    op.create_index(
        "ix_context_contradictions_proposition",
        "context_contradictions",
        ["proposition_id"],
        unique=False,
    )
    op.create_index(
        "ix_context_contradictions_context",
        "context_contradictions",
        ["context_id"],
        unique=False,
    )
    op.create_index(
        "ix_context_contradictions_status", "context_contradictions", ["status"], unique=False
    )

    # The context fabric resolves observation -> entities on every tick to decide which
    # cell an observation belongs to. The stream's own key is (tenant, entity, sequence),
    # so without this the lookup is a scan of the whole tenant per pass -- and it is the
    # lookup that lets the context deepen at all.
    op.create_index(
        "ix_entity_stream_observation",
        "entity_stream",
        ["tenant_id", "observation_id"],
        unique=False,
    )


def downgrade() -> None:
    # Forward-only in practice: these tables hold the only record of what a pass
    # concluded. Dropping them would destroy the derivation history, which is the
    # history Constitution I-2 promises to keep. The indexes go with the tables so a
    # partial downgrade cannot leave an unqueryable table behind.
    op.drop_table("context_contradictions")
    op.drop_table("context_propositions")
    op.drop_table("fabric_reports")
    op.drop_index("ix_entity_stream_observation", table_name="entity_stream")
    op.drop_table("context_cells")