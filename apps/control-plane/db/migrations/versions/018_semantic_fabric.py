"""Alembic migration for semantic fabric persistence (feature 017).

Creates the durable substrate the semantic layer attaches beside the graph with:
layered typing claims, the profiles that scope them, recorded cross-vocabulary
alignments, and the graded findings validation produces (FR-003, FR-007, FR-009,
FR-012). The graph's own foundation is untouched by this revision -- typing, not
identity, is what becomes durable here.

Four properties are structural in the DDL rather than left to a caller, because
each of them is a promise the feature makes and a store is where a promise is
either kept or quietly broken:

* **Nothing here is a gate.** There is no column that says what may exist, no
  ``allows_*``/``permits``/``valid`` field, and no unique constraint that could
  make a second claim a duplicate. An entity typed by a term no profile, pack or
  ontology declares is stored here with no error at all (FR-001, US1).
* **A promotion is a new row.** ``assertion_id`` is the digest of the whole
  ``TypeAssertion`` claim, so re-asserting a typing at a higher status produces a
  different id and both rows survive. This is why the identity of a claim --
  ``(tenant_id, entity_ref, type_ref, scope)`` -- is deliberately *not* a unique
  constraint here: it would forbid the second row a promotion needs and make
  FR-004 unimplementable at the storage layer. Idempotency comes from the primary
  key instead, which is where "the same claim recorded twice" is caught without
  catching "the same claim promoted". ``supersedes`` does the same job for a
  re-evaluated mapping, as a new row naming its predecessor.
* **Every table is tenant-scoped, fail-closed.** ``tenant_id`` is NOT NULL on all
  four and additionally checked against the empty string. There is deliberately
  no nullable or global tenant column: a semantic term is a reading of one
  tenant's data, and a row any tenant could read would leak which instruments that
  tenant had. The check exists because NOT NULL alone still admits ``''``, and
  ``''`` is not a tenant (constitution IV).
* **Three clocks, never merged.** ``observed_at`` is when the platform learned a
  claim; ``valid_from``/``valid_to`` are when it was true; ``created_at`` is when
  the row was written. They are distinct columns because a reader asking "what did
  we believe at time T" needs them distinguishable (constitution V).

One DDL detail is spelled out here that the ORM's annotation would otherwise have
implied. ``op.create_table`` defaults a column to nullable, while
``db/schema.py``'s non-optional ``Mapped[datetime]`` means ``NOT NULL``, so a
``created_at`` written without ``nullable=False`` is nullable in an upgraded
database and not nullable in a fresh one -- and autogenerate reports exactly that
as drift. Revisions 015 and 016 spell those columns without the flag; repeating
that here would import the divergence into the tables this revision owns, so it
is written out on all four.

The index set is what the read paths need and nothing more. ``(tenant_id,
entity_ref, scope)`` answers both "every layer of this entity" (US2) and "the
whole typing history of this entity" (US9) with one index. Mappings are indexed
in both directions because alignment is asked in both directions. Findings are
indexed on the assertion they name and on the verdict, which are the two
questions an operator actually asks. ``semantic_profiles.applies_to`` is left
unindexed deliberately: it is read once per resolution over a small per-tenant
set, and a GIN index there would cost write amplification on every profile write
for a scan nobody runs -- the same call revision 017 made for ``provenance``
(ADR-0026).

Revision ``017_discovery_provenance`` is treated as already released and is never
edited. This file is the only place the semantic fabric schema is expressed in
DDL, and a deployment that already ran 017 reaches it by applying 018 -- not by
amending a migration its database has already executed.

Ordering inside ``upgrade`` follows revisions 015, 016 and 017: create tables, add
columns, backfill, then create indexes. No index is ever built against a column
that does not exist yet. Sections 2 and 3 are recorded no-ops rather than dropped,
so a reader of the file can see that "there is nothing to add" and "there is
nothing to reconcile" are decisions and not omissions.

``downgrade`` deliberately does **not** reverse this revision, which is a
departure from 016 and 017 and is argued where it is written.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "018_semantic_fabric"
down_revision = "017_discovery_provenance"
branch_labels = None
depends_on = None

# The tables this revision introduces, in creation order. Referenced by the
# no-op sections below so that "there is no column to add" and "there is nothing
# to backfill" are recorded as positive statements about this table set rather
# than as an absence.
_ACTIVE = (
    "type_assertions",
    "semantic_profiles",
    "semantic_mappings",
    "validation_findings",
)


def _no_new_columns() -> None:
    """Section 2: no existing table gains a column from this revision.

    Every column introduced here belongs to a table in ``_ACTIVE``, which section 1
    creates whole. A future revision that widens a semantic column -- adding an
    ``ontology_version`` to a typing claim, say -- adds its column here and indexes
    it in section 4, keeping any backfill of that column between them.
    """


def _no_backfill() -> None:
    """Section 3: no historical row needs a value written by application code.

    All four tables are new, so there is no pre-existing row to reconcile, and the
    unique index in section 4 covers columns that only rows written from now on can
    populate. A revision that did add a unique index over a backfilled column would
    have to run that backfill here instead.
    """


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. New tables
    # ------------------------------------------------------------------
    op.create_table(
        "type_assertions",
        sa.Column("assertion_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("entity_ref", sa.String(64), nullable=False),
        sa.Column("type_ref", sa.String(255), nullable=False),
        sa.Column("type_scheme", sa.String(16), nullable=False),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("raw_surface", sa.Text(), nullable=False, server_default=""),
        sa.Column("hypothesis", sa.String(255), nullable=False, server_default=""),
        sa.Column("source_ref", sa.String(64), nullable=False, server_default=""),
        sa.Column("extractor_ref", sa.String(64), nullable=False, server_default=""),
        sa.Column("context_ref", sa.String(64), nullable=False, server_default=""),
        sa.Column("profile_ref", sa.String(96), nullable=False, server_default=""),
        sa.Column("mapping_ref", sa.String(96), nullable=False, server_default=""),
        sa.Column("evidence_refs", postgresql.JSONB(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("observed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("tenant_id <> ''", name="ck_type_assertion_tenant"),
    )
    op.create_table(
        "semantic_profiles",
        sa.Column("profile_row_id", sa.String(96), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("profile_id", sa.String(96), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("parent_profile", sa.String(128)),
        sa.Column("type_refs", postgresql.JSONB(), nullable=False),
        sa.Column("relation_refs", postgresql.JSONB(), nullable=False),
        sa.Column("vocabulary_refs", postgresql.JSONB(), nullable=False),
        sa.Column("constraint_refs", postgresql.JSONB(), nullable=False),
        sa.Column("mapping_refs", postgresql.JSONB(), nullable=False),
        sa.Column("applies_to", postgresql.JSONB(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("content_key", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("tenant_id <> ''", name="ck_semantic_profile_tenant"),
    )
    op.create_table(
        "semantic_mappings",
        sa.Column("mapping_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("subject_ref", sa.String(255), nullable=False),
        sa.Column("object_ref", sa.String(255), nullable=False),
        sa.Column("subject_scheme", sa.String(16), nullable=False),
        sa.Column("object_scheme", sa.String(16), nullable=False),
        sa.Column("predicate", sa.String(32), nullable=False),
        sa.Column("mapping_set_id", sa.String(64), nullable=False),
        sa.Column("mapping_set_version", sa.String(32), nullable=False),
        sa.Column("mapping_source", sa.String(64), nullable=False, server_default=""),
        sa.Column("mapping_version", sa.String(32), nullable=False, server_default=""),
        sa.Column("justification", sa.String(24), nullable=False),
        sa.Column("provenance", postgresql.JSONB(), nullable=False),
        sa.Column("supersedes", postgresql.JSONB(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("observed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("tenant_id <> ''", name="ck_semantic_mapping_tenant"),
    )
    op.create_table(
        "validation_findings",
        sa.Column("finding_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("assertion_ref", sa.String(64), nullable=False),
        sa.Column("stage", sa.String(24), nullable=False),
        sa.Column("verdict", sa.String(16), nullable=False),
        sa.Column("code", sa.String(64), nullable=False, server_default=""),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("constraint_ref", sa.String(96), nullable=False, server_default=""),
        sa.Column("profile_ref", sa.String(96), nullable=False, server_default=""),
        sa.Column("context_ref", sa.String(64), nullable=False, server_default=""),
        sa.Column("evidence_refs", postgresql.JSONB(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("tenant_id <> ''", name="ck_validation_finding_tenant"),
    )

    # ------------------------------------------------------------------
    # 2. New columns (none: every table above is new in this revision)
    # ------------------------------------------------------------------
    _no_new_columns()

    # ------------------------------------------------------------------
    # 3. Backfill (none required; all four tables are created empty)
    # ------------------------------------------------------------------
    _no_backfill()

    # ------------------------------------------------------------------
    # 4. Indexes (last, so every column they reference already exists)
    # ------------------------------------------------------------------
    # One index serves both layered-typing reads: every scope of one entity (US2)
    # and the entity's whole typing history (US9).
    op.create_index(
        "ix_type_assertion_entity",
        "type_assertions",
        ["tenant_id", "entity_ref", "scope"],
    )
    # The addressable key of a profile. A bare tenant scan is served by its leading
    # column, so there is no separate tenant index to keep in step with this one.
    op.create_index(
        "uq_semantic_profile_version",
        "semantic_profiles",
        ["tenant_id", "profile_id", "version"],
        unique=True,
    )
    # Alignment is read in both directions, and a process that records a pair in
    # either order is making the same claim about it.
    op.create_index(
        "ix_semantic_mapping_subject",
        "semantic_mappings",
        ["tenant_id", "subject_ref"],
    )
    op.create_index(
        "ix_semantic_mapping_object",
        "semantic_mappings",
        ["tenant_id", "object_ref"],
    )
    op.create_index(
        "ix_validation_finding_assertion",
        "validation_findings",
        ["tenant_id", "assertion_ref"],
    )
    op.create_index(
        "ix_validation_finding_verdict",
        "validation_findings",
        ["tenant_id", "verdict"],
    )


def downgrade() -> None:
    """Refuse. This revision's tables are permanent records, not reversible state.

    016's downgrade is the strict reverse of its upgrade and 017's drops the single
    column it added, and for both that is the right answer: they reshape storage,
    so undoing them undoes the reshaping. Neither answer is available here.
    Dropping ``type_assertions`` would delete the typing history FR-004 requires to
    be retained, and dropping ``validation_findings`` would delete the findings
    FR-012 says must outlive a verdict about them -- a downgrade would then be the
    only operation in the platform able to remove a record on the strength of a
    check that merely failed.

    A reverse that destroys the feature's central guarantee is worse than no
    reverse, so this raises. Rolling back is a forward operation: add revision 019
    that states what the schema becomes instead.
    """
    raise NotImplementedError(
        "018_semantic_fabric is forward-only: type_assertions retains the typing "
        "history FR-004 requires and validation_findings retains findings that "
        "FR-012 forbids deleting, so a downgrade would destroy exactly what this "
        "revision exists to keep. Add a new forward revision instead."
    )
