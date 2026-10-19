"""Investigation membership for entities (024).

Revision ID: 024_investigation_entity_membership
Revises: 023_derivation_enforcement

Why this revision exists
------------------------
``GET /api/v1/entities?investigation_id=...`` ignored the filter. The route did not
declare the parameter at all, so *every* investigation received the whole catalog --
measured, not guessed: five investigations all answered ``ENT-2001..ENT-2005``. The
underlying cause is not in the route. ``entities`` has never carried an investigation
reference, so there was nothing for the route to filter on; ``/entities/graph`` works
around it by deriving membership from the investigation's relation claims, which is
correct for a mature investigation and empty for every fresh one.

What this revision adds
-----------------------
One table, ``investigation_entity_memberships``: which investigations an entity is part
of, with the basis on which that came to be true.

Why a table rather than ``entities.investigation_id``
-----------------------------------------------------
Every neighbouring table carries a single ``investigation_id``, and this one does not,
deliberately. Those tables hold facts, and a fact is produced by one investigation. An
entity is an identity, not a fact: ``api/routes/manual_assertions.py`` derives an
``entity_id`` from ``(tenant_id, canonical_identity)`` with no investigation in the
digest, so two investigations asserting the same subject already resolve to ONE
``entities`` row. A single column would make that row belong to whichever investigation
wrote last, and the other investigation would silently lose the entity. That is
last-writer-wins on the one table in this schema whose purpose is to be overwritten
never. The membership table also matches the constitution's process-centric shape
(§VI): the investigation is the unit of scoping, and an entity that several
investigations share is a fact about the world rather than a conflict between them.

Durability, not a projection
----------------------------
The table lives in ``apps/control-plane``/PostgreSQL because membership is operational
state an operator must be able to query after the fact; the graph remains a rebuildable
projection (constitution III), and ``/entities/graph`` keeps deriving its node set from
relation claims.

No foreign keys, for the reason 019 gives: the entity row and the membership that names
it are written by different processes on different schedules, and an FK would make that
ordering load-bearing.

DDL notes carried forward from earlier revisions
-----------------------------------------------
* ``postgresql.JSONB``, never ``sa.JSONB`` -- the generic type compiles to a DDL form
  ``CREATE TABLE`` cannot accept on the asyncpg path. This table carries no JSON column;
  the rule is recorded because it is the first thing a later revision adding one hits.
* The ``basis`` vocabulary is closed and enforced with a CHECK. A *new* table has no
  pre-existing rows to grandfather, so the constraint is declared inline rather than
  installed ``NOT VALID`` the way 023 installs its four on ``entities``/``entity_stream``/
  ``observations``/``relation_claims``. ``NOT VALID`` exists there to avoid a table
  rewrite over rows that predate the vocabulary, and paying for that machinery on an
  empty table would buy nothing.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "024_investigation_entity_membership"
down_revision = "023_derivation_enforcement"
branch_labels = None
depends_on = None

#: The vocabulary as SQL literals, copied rather than imported from ``db/schema.py``.
#: A migration that read the value type would change meaning when somebody edited that
#: type, and a database that already ran this revision cannot be re-run -- the same rule
#: 023 states for the entity-type vocabulary it installs. ``db.schema`` holds the
#: Python-side authority, and
#: ``tests/unit/test_migration_024_investigation_entity_membership.py`` asserts the two
#: agree, which is the only way a deliberate duplication stays honest.
MEMBERSHIP_BASIS_VALUES: tuple[str, ...] = (
    "EXPLICIT",
    "ANALYST_ASSERTION",
    "RELATION_DERIVED",
)


def upgrade() -> None:
    op.create_table(
        "investigation_entity_memberships",
        # Composite key rather than a surrogate id: a membership *is* the triple, so a
        # separate id would add a second identity to answer "is this already recorded?".
        # Re-establishing membership therefore collides at the database instead of
        # growing a second identical row (I-11).
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("investigation_id", sa.String(36), nullable=False),
        # 64 wide for the measured reason ``evidence_links.candidate_id`` gives in 019:
        # every other entity reference in this schema is 64 wide, and truncating an
        # address silently is worse than storing a few spare characters.
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("basis", sa.String(32), nullable=False),
        sa.Column("established_by", sa.String(128), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id", "investigation_id", "entity_id",
            name="pk_investigation_entity_memberships",
        ),
        # NOT NULL alone still admits '', and '' is not a tenant, an investigation or an
        # entity -- the correction 018 and 019 applied to their own tables.
        sa.CheckConstraint("tenant_id <> ''", name="ck_investigation_entity_membership_tenant"),
        sa.CheckConstraint(
            "investigation_id <> ''", name="ck_investigation_entity_membership_investigation"
        ),
        sa.CheckConstraint("entity_id <> ''", name="ck_investigation_entity_membership_entity"),
        sa.CheckConstraint(
            "basis IN (" + ", ".join(f"'{v}'" for v in MEMBERSHIP_BASIS_VALUES) + ")",
            name="ck_investigation_entity_membership_basis",
        ),
    )
    # "What does this investigation contain" -- the read the route could not serve.
    op.create_index(
        "ix_investigation_entity_membership_inv",
        "investigation_entity_memberships",
        ["tenant_id", "investigation_id"],
    )
    # "Which investigations is this entity in" -- the detail view's question.
    op.create_index(
        "ix_investigation_entity_membership_entity",
        "investigation_entity_memberships",
        ["tenant_id", "entity_id"],
    )


def downgrade() -> None:
    # Dropped with its indexes rather than one at a time: PostgreSQL refuses to drop a
    # table that still has dependent indexes, so the reverse order of upgrade() is the
    # order that actually runs.
    op.drop_table("investigation_entity_memberships")
