"""Context graph persistence: nodes, edges, decisions (025).

Revision ID: 025_context_graph
Revises: 024_investigation_entity_membership

What this revision adopts
-------------------------
``context_nodes``, ``context_edges`` and ``context_decisions`` have been in the dev
database since before this directory had a revision for them. Measured, not inferred:

* no file in ``versions/`` ever mentions ``context_nodes``, ``context_edges`` or
  ``context_decisions`` -- ``grep -n 'context_nodes|context_edges|context_decisions'``
  over ``versions/*.py`` returns nothing;
* ``db/schema.py:3014-3070`` declares the three ``Context*Row`` models;
* the tables exist in the live database with their columns, indexes and constraint
  matching the ORM exactly, and ``context_nodes``/``context_decisions`` hold rows.

The signature of that state is a schema installed by ``Base.metadata.create_all()``,
not by a revision. So the drift was never "a second head": ``alembic heads`` reports
exactly one, and it reported one before this file existed. The drift is that three
tables were outside Alembic's knowledge entirely, which means no ``downgrade``,
no ``upgrade`` on a fresh database, and no way to answer "what created this?" from
the repository alone. That is what this revision fixes.

Why the create is conditional
-----------------------------
These tables are already present on any database that ``create_all`` has touched, so
a bare ``op.create_table`` would fail with ``relation "context_nodes" already exists``
on precisely the databases this revision most needs to run on. Each object is
therefore reconciled independently:

* table absent -> created with its constraint inline (024's rule: a new table has no
  rows to grandfather, so validating eagerly buys nothing);
* table present -> missing columns added, missing indexes and unique constraints
  added, and the one CHECK installed ``NOT VALID`` (023's rule: new rows are checked
  at once, old rows at VALIDATE time).

A migration that cannot be applied against a live database has to be hand-patched
against one, and a hand-patched migration is the state this repository is trying to
leave.

The closed vocabulary, and where it is and is not enforced
-----------------------------------------------------------
``edge_type`` carries a CHECK because the edge vocabulary *is* the graph's grammar:
an edge of a type this build does not define means the reader is looking at a graph
it cannot interpret, and that is worth refusing at the storage layer.

``node_type`` deliberately does not. ``db/schema.py:3001-3006`` explains why -- spec
§3.2 requires ten node types "at minimum", and freezing the list into a constraint
would force a migration for every type the spec explicitly permits. It is validated
at write time by ``context_engine.context_graph.validate``, where an invalid shape can
still be refused. Duplicating that decision in a second place that could disagree
with it would be the drift, not the fix.

``created_at`` has no server default on any of the three, matching the ORM: the
default lives on the Python side (``datetime.now(timezone.utc)`` in the writer), and a
server default added here would produce rows whose timestamps no writer chose.

DDL notes carried forward
-------------------------
* ``postgresql.JSONB``, never ``sa.JSONB`` -- the generic type compiles to a DDL form
  ``CREATE TABLE`` cannot accept on the asyncpg path. Four JSON columns here.
* No foreign keys, for the reason 019 and 024 give: nodes are written by the context
  engine and read by investigations on a different schedule, and an FK would make
  that ordering load-bearing.
* ``downgrade`` drops the tables. That is correct for a revision that created them and
  destructive for one that adopted them, and there is no honest way to distinguish
  the two at downgrade time -- which is the real argument for running this revision
  forward only.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "025_context_graph"
down_revision = "024_investigation_entity_membership"
branch_labels = None
depends_on = None

#: Copied from ``ContextEdgeRow.__table_args__`` rather than imported, for the reason
#: 024 gives for ``MEMBERSHIP_BASIS_VALUES``: a migration that read the value at run
#: time would change meaning when somebody edited the model, and a database that has
#: already run this revision cannot be re-run. ``db.schema`` stays the Python-side
#: authority and the two are compared in tests.
EDGE_TYPE_VALUES: tuple[str, ...] = (
    "asks",
    "scopes",
    "supports",
    "contradicts",
    "refines",
    "delegates",
    "observes",
    "revises",
    "derived_from",
    "supersedes",
)


def _inspector() -> sa.Inspector:
    """A fresh inspector per call.

    Alembic runs the whole revision in one transaction, so an inspector cached at the
    top of ``upgrade()`` would keep reporting a table as absent immediately after the
    same revision created it.
    """
    return sa.inspect(op.get_bind())


def _add_check_not_valid(name: str, table: str, expression: str) -> None:
    """Add a CHECK on a table that predates this revision.

    023's rationale, repeated because the alternative is not "be slightly slower":
    these tables may already hold rows written before this constraint existed, and
    scanning them would fail the migration on exactly the data it was written to
    grandfather in.
    """
    op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({expression}) NOT VALID")


def _ensure_table(
    name: str,
    primary_key: "list[str]",
    columns: "list[sa.Column]",
    indexes: "list[tuple[str, list[str]]]",
    uniques: "list[tuple[str, list[str]]]",
    checks: "list[tuple[str, str]]",
) -> None:
    """Create ``name`` in full, or bring an existing ``name`` up to the declared shape.

    Reconciling per object rather than all-or-nothing is what makes this revision
    applicable to both the dev database (tables already present) and a fresh one
    (tables absent) without a branch outside Alembic.

    ``primary_key`` is create-only: a table that already exists has its PK, and
    adding one to an existing table would be a rebuild rather than a migration.
    """
    if name not in set(_inspector().get_table_names()):
        op.create_table(
            name,
            sa.PrimaryKeyConstraint(*primary_key),
            *columns,
            *(sa.UniqueConstraint(*cols, name=cname) for cname, cols in uniques),
            *(sa.CheckConstraint(expr, name=cname) for cname, expr in checks),
        )
        for iname, icols in indexes:
            op.create_index(iname, name, icols)
        return

    present = {c["name"] for c in _inspector().get_columns(name)}
    for column in columns:
        if column.name not in present:
            op.add_column(name, column.copy())

    present_indexes = {i["name"] for i in _inspector().get_indexes(name)}
    for iname, icols in indexes:
        if iname not in present_indexes:
            op.create_index(iname, name, icols)

    present_uniques = {u["name"] for u in _inspector().get_unique_constraints(name)}
    present_uniques |= present_indexes  # PostgreSQL backs a UNIQUE with a unique index.
    for cname, ccols in uniques:
        if cname not in present_uniques:
            op.create_unique_constraint(cname, name, ccols)

    present_checks = {c["name"] for c in _inspector().get_check_constraints(name)}
    for cname, cexpr in checks:
        if cname not in present_checks:
            _add_check_not_valid(cname, name, cexpr)


def _nodes_columns() -> "list[sa.Column]":
    return [
        # Content-derived id: re-deriving the same node overwrites its own row rather
        # than accumulating duplicates, so there is no sequence and no autoincrement.
        sa.Column("node_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        # Free text on purpose -- see the module docstring on why node_type carries no
        # CHECK while edge_type does.
        sa.Column("node_type", sa.String(32), nullable=False),
        sa.Column("investigation_id", sa.String(64), nullable=False),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _edges_columns() -> "list[sa.Column]":
    return [
        sa.Column("edge_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("edge_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=False),
        sa.Column("weight", sa.Float, nullable=False),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column("observation_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _decisions_columns() -> "list[sa.Column]":
    return [
        sa.Column("decision_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        # What decided, not who. An agent, a rule or an operator all write here, so
        # ``actor`` is an opaque 64-wide reference rather than a user table join.
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("rationale", sa.Text, nullable=False),
        # The decision's effect, kept next to its reason. A graph whose edges exist but
        # cannot be explained is the failure mode Constitution I-2 exists to prevent.
        sa.Column("added_nodes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("added_edges", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    # -- nodes --------------------------------------------------------------
    _ensure_table(
        "context_nodes",
        primary_key=["node_id"],
        columns=_nodes_columns(),
        indexes=[
            # "What does this investigation's graph contain" -- the read the graph route
            # serves. First column is the tenant so every lookup is tenant-scoped.
            ("ix_context_nodes_tenant_inv", ["tenant_id", "investigation_id"]),
            # "Which nodes of this kind are in play" -- the type filter in traversal.
            ("ix_context_nodes_tenant_type", ["tenant_id", "node_type"]),
        ],
        uniques=[],
        checks=[],
    )

    # -- edges --------------------------------------------------------------
    _ensure_table(
        "context_edges",
        primary_key=["edge_id"],
        columns=_edges_columns(),
        indexes=[
            # Traversal is by endpoint; these two are the whole reason the graph is
            # walkable in a query rather than by loading every edge into memory.
            ("ix_context_edges_tenant_source", ["tenant_id", "source_id"]),
            ("ix_context_edges_tenant_target", ["tenant_id", "target_id"]),
        ],
        uniques=[
            # Endpoint uniqueness is what makes re-applying a decision idempotent,
            # exactly as the content-derived ids do for nodes. Without it the same
            # decision applied twice doubles the edge count.
            ("uq_context_edge_endpoints", ["tenant_id", "edge_type", "source_id", "target_id"]),
        ],
        checks=[
            ("ck_context_edges_type", "edge_type IN (" + ", ".join(f"'{v}'" for v in EDGE_TYPE_VALUES) + ")"),
        ],
    )

    # -- decisions ----------------------------------------------------------
    _ensure_table(
        "context_decisions",
        primary_key=["decision_id"],
        columns=_decisions_columns(),
        indexes=[
            # "What was decided in this tenant, in order" -- one index covering both
            # halves of the question rather than an index on each.
            ("ix_context_decisions_tenant", ["tenant_id", "created_at"]),
        ],
        uniques=[],
        checks=[],
    )


def downgrade() -> None:
    # Reverse creation order, and guarded on existence: this revision may have adopted
    # these tables rather than created them, so a downgrade run against a database that
    # has since lost one of them should not fail on the two that remain.
    for table in ("context_decisions", "context_edges", "context_nodes"):
        if table in set(_inspector().get_table_names()):
            op.drop_table(table)
