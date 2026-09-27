"""Alembic migration for discovery provenance on the frontier (feature 008).

`frontier_items` had no column able to carry provenance, so the bridge from
Layer A discovery to the durable frontier had to *discard* the provenance it is
required to carry: FR-007 (source, method, query/seed and, for link-graph, the
originating observation) would have been satisfied in memory and lost at the
boundary. This revision adds exactly one column and changes nothing else.

The change is one additive column, ``provenance JSONB NOT NULL DEFAULT '{}'``,
and is deliberately minimal:

* ``uq_frontier_schedule (tenant_id, uri)`` is **not** touched. Discovery
  idempotency (FR-006) is that unique index; rebuilding it under load is a
  self-inflicted outage, so this revision creates, drops and re-creates no index
  at all.
* The column is **not** indexed. Provenance is read for audit and replay, never
  queried, and a GIN index over a document that grows with every coalesced
  ``seen_by[]`` entry would cost write amplification on the hottest table in the
  system for a query nobody runs (ADR-0026).
* ``NOT NULL DEFAULT '{}'`` is the safe direction for an existing table: rows
  written before this revision exist, and a nullable column would leave the
  "every discovered candidate carries provenance" claim true only for rows
  written after the upgrade. A pre-017 row therefore reads as ``{}`` -- "the
  discovery that produced this row did not record its provenance" -- which is
  false rather than unknown.

Section 3 records that no backfill is required: the column has a server default,
so every pre-existing row is materialised with a value by ``ADD COLUMN`` itself,
which is also what keeps the statement non-blocking on a large table.

Revision ``016_relation_evidence_graph`` is treated as already released and is
never edited. This file is the only place the frontier provenance column is
expressed in DDL, and a deployment that already ran 016 reaches it by applying
017 -- not by amending a migration its database has already executed.

Ordering inside ``upgrade`` follows revisions 015 and 016: create tables, add
columns, backfill, then create indexes. Sections 1 and 4 are recorded no-ops
rather than dropped, so a reader of the file -- and the ordering test -- can see
that "there is nothing to create" and "there is nothing to index" are decisions
and not omissions.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "017_discovery_provenance"
down_revision = "016_relation_evidence_graph"
branch_labels = None
depends_on = None

# The single column this revision introduces, and the single table it touches.
# Named so the recorded no-op sections below can state the revision's scope
# positively rather than by omission.
_ACTIVE_TABLE = "frontier_items"
_ACTIVE_COLUMN = "provenance"

# The unique index discovery idempotency depends on (FR-006). Listed as a
# constant so the forward-only test can assert this revision never names it --
# a migration that dropped and re-created it would rebuild the index under
# concurrent load and take a uniqueness guarantee with it.
_SCHEDULE_KEY_INDEX = "uq_frontier_schedule"


def _provenance_column() -> sa.Column:
    """The one column added, built fresh on every call.

    A ``sa.Column`` carries compile-time state, so returning a shared instance
    from a module constant would let a second execution of ``upgrade()`` in the
    same interpreter reuse an already-attached column. Building it in the
    function keeps the revision re-runnable and keeps the column definition
    visible in one place.
    """
    return sa.Column(
        _ACTIVE_COLUMN,
        postgresql.JSONB(),
        nullable=False,
        # Rendered as the bare literal rather than ``'{}'::jsonb`` so this DDL is
        # byte-identical to the one ``db/schema.py`` emits for the same column.
        # A fresh install (``create_all``) and an upgraded install (this file)
        # must produce the same table, and the cheapest way to keep them equal is
        # for the default to be spelled the same way on both routes.
        server_default=sa.text("'{}'"),
    )


def _no_new_tables() -> None:
    """Section 1: no table is created; ``frontier_items`` already exists.

    Recorded explicitly because "this revision creates no table" is the property
    that keeps the component inventory at one new *column* and zero new tables
    (FR-017): a provenance side-table would be a second place discovery state
    lives, and a frontier item whose provenance is somewhere other than its own
    row cannot be audited from that row.
    """


def _no_backfill() -> None:
    """Section 3: no historical row needs a value written by application code.

    ``ADD COLUMN ... NOT NULL DEFAULT '{}'`` rewrites each pre-existing row with
    the default in the same statement, so every row that exists at upgrade time
    is already non-null and valid. An ``UPDATE`` pass would be a second full
    scan of the busiest table in the system to write a value the DDL has
    already written -- and a window in which a partially-applied backfill is
    indistinguishable from a complete one.
    """


def _no_new_indexes() -> None:
    """Section 4: no index is created, and ``uq_frontier_schedule`` is untouched.

    The provenance column is read for audit and never queried, so indexing it
    would buy nothing and cost write amplification on every enqueue. More
    importantly this revision must not name ``uq_frontier_schedule``: FR-006
    idempotency is that unique index, and dropping and re-creating it takes the
    guarantee away for the duration of the rebuild.
    """


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. New tables (none: the frontier table predates this feature)
    # ------------------------------------------------------------------
    _no_new_tables()

    # ------------------------------------------------------------------
    # 2. New columns: the one this revision exists for
    # ------------------------------------------------------------------
    op.add_column(_ACTIVE_TABLE, _provenance_column())

    # ------------------------------------------------------------------
    # 3. Backfill (none required; the server default materialises existing rows)
    # ------------------------------------------------------------------
    _no_backfill()

    # ------------------------------------------------------------------
    # 4. Indexes (none: provenance is read for audit, never queried)
    # ------------------------------------------------------------------
    _no_new_indexes()


def downgrade() -> None:
    op.drop_column(_ACTIVE_TABLE, _ACTIVE_COLUMN)
