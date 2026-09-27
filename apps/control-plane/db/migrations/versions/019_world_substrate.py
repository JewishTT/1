"""Alembic migration for the world substrate (feature 018).

Closes both ends of the evidence chain and the middle that says what was believed
when. ``specs/018-world-substrate/spec.md`` D1, D2, D3, D4, D6, D-B and FR-001,
FR-003, FR-004, FR-006, FR-009, FR-014, FR-024, FR-025, FR-026; plan decisions D1
and D2. What becomes durable here is where the bytes came from, which mention
introduced which entity and why, and what a reading was interpreted under.

The acquisition half arrived first and is left exactly as written: the chain has
declared a capture hop since feature 016 and nothing in the platform modelled one.
Acquisition emitted observation dicts carrying a bare ``observation_id``, and the
one link with no value type of its own was filled in by a string derived from
``(source_id, observation_id)``. An id computed from the event it is meant to
explain cannot be a fact that came *before* the event, cannot distinguish two
fetches of one target, and cannot say which batch produced it -- so replay,
provenance, batch lineage and capture-level deduplication were all broken by one
missing row. That row is ``captures``, and ``ingest_batches`` and ``data_stream``
are the two tables that make it mean something.

The identity half is appended here, in the sections the scope note below names,
and the reason is mechanical rather than editorial: **two revisions sharing an id
do not load.** Alembic builds its revision map by id, so a second file declaring
``revision = "019_world_substrate"`` is either silently shadowed or a hard
failure, and feature numbering and migration numbering are independent namespaces
that have already collided once in this repository (revision ``018_semantic_fabric``
belongs to feature 017). There is one revision per branch point, not one per
author, so this file is the single place the world-substrate schema is expressed
in DDL.

Three groups, seven structural properties across the six tables:

* **Every table is tenant-scoped, fail-closed.** ``tenant_id`` is NOT NULL on all
  six and additionally checked against the empty string, for the reason 018 gave
  and this revision repeats: NOT NULL alone still admits ``''``, and ``''`` is
  not a tenant (constitution IV).
* **An absent fetch time is named, not null.** ``captures.fetched_at`` is
  nullable and ``captures.capture_time_basis`` is not, and two check constraints
  hold them together: a basis of ``fetch`` requires the timestamp, and a timestamp
  is only ever allowed on a basis of ``fetch``. A Common Crawl row therefore reads
  ``fetched_at IS NULL`` *and* ``capture_time_basis = 'index_observation'`` -- a
  stated absence, distinguishable from a row nobody has written a fetch time into
  -- and a loader that tried to promote an index or publication timestamp into
  ``fetched_at`` is refused by the database, not only by the value type. This is
  the constraint FR-025 and FR-007 are about, expressed where a bulk loader cannot
  bypass it (spec D-B).
* **Batch identity is not content identity.** ``ingest_batches`` exists so FR-009
  has two separable answers: ``captures.capture_id`` answers "is this the same
  fetch event", the payload key answers "have these bytes come back before", and
  neither is the batch. ``ingest_batch_id`` is part of a capture's address, so the
  same payload read in two batches is two captures, and a capture taken outside any
  run carries the ``unbatched`` sentinel rather than an invented batch.
* **A stream must state its axes to exist.** ``data_stream`` records what a source
  supplies of the six time axes and, in ``axis_declarations``, what it cannot
  supply and why -- so the FR-026 refusal has somewhere durable to land, and the
  five gaps a crawl-index stream has are a record rather than five absences in a
  list.
* **The anchor is write-once under two unique constraints, not one.** This is
  the one place where the plan's index set (D1) and the real invariant differ, so
  it is stated here rather than discovered later. UNIQUE
  ``(tenant_id, anchor_mention_id)`` covers "one mention anchors at most one
  entity" and is what makes the anchor structural rather than conventional. It
  does **not** cover "one entity has at most one anchor": a second anchor for an
  already-anchored entity is invisible to it, and an anchor that silently moves is
  the failure FR-001 exists to prevent. UNIQUE ``(tenant_id, entity_id)`` is the
  other half, and between them they are this feature's load-bearing guarantee --
  the one requirement the spec's Gate names. The in-memory store
  (:class:`domain.entity_identity.InMemoryEntityIdentityStore`) reproduces both and
  is where the second half gets a *typed* refusal, which a bare index cannot give a
  caller; the index is what makes the guarantee hold for a loader that never
  constructs the value type.
* **A decision's key is the machine's, never this row's.**
  ``resolution_decision.resolution_decision_id`` is the resolver's own ``RES-``,
  carried verbatim. ``record_fingerprint`` is the *second* address -- this row's
  content digest -- and it is what the unique index is built on, beside
  ``identity_fingerprint`` and ``capture_fingerprint``, for the discipline
  ``evidence_context.frame_fingerprint`` and ``relation_claim.content_hash``
  already state. A migration that computed the primary key from the row would fork
  silently from the machine's ids and every ``ENT-``/``RES-`` pair in the platform
  would stop joining, with the divergence invisible until a reconstruction came
  back empty.
* **A regime is addressed by the pair, and the pair is unique.** The primary key
  is the bare ``regime_id``; the load-bearing constraint is UNIQUE
  ``(tenant_id, regime_id)``. The store refuses cross-tenant reads
  precisely because the pair is the key -- ``regime_for`` raises
  ``CrossTenantRefusal`` when an id this tenant does not hold is held by another --
  and that distinction is only possible if one tenant may hold a record at an
  address another tenant already uses. A bare primary key would merge two tenants'
  instruments into one address, the same reasoning that puts UNIQUE
  ``(tenant_id, entity_id)`` on ``entity_identity``.

Three things are deliberately absent, and all three are decisions:

* **No foreign keys.** Revisions 015, 016 and 018 reference other records by id
  string, and this revision follows them. The concrete cost is that the
  ``captures`` -> ``ingest_batches`` relationship is not enforced by the database,
  so a capture can name a batch that was never opened. The gain is that a capture
  and the batch row accounting for it can be written in either order inside one
  transaction, and that the acquisition path does not have to open a batch before
  it is allowed to record a byte. The identity and regime tables reference the
  most and for the same reason: an anchor names a mention, an observation and a
  capture, and a decision names a mention and a regime, none of which the process
  recording them necessarily holds in the same transaction. Adding the constraints
  is a later revision's decision, made when a reader exists that would notice
  their absence.
* **No wall clock in any content address.** ``created_at``, ``registered_at``,
  ``decided_at`` and ``recorded_at`` record when a row was *written* (or, for a
  decision, when it was taken). None is in ``capture_fingerprint``,
  ``identity_fingerprint``, ``record_fingerprint`` or ``regime_id``; none is in a
  generated column, a trigger or a unique index; and ``recorded_at`` appears in
  exactly one place, a *non-unique* index on ``semantic_regime``, where it orders
  "the current regime for this frame" and constrains nothing. So re-ingesting the
  same fact at a different moment produces the same id and the same row
  (constitution VII, FR-022). ``fetched_at`` *is* inside the capture's address
  material and ``created_at`` is not, and the difference is the whole distinction:
  one is a fact of the event and the other is a fact of the writing. Every
  fingerprint is written by the application and never generated, for the same
  reason: a generated column would have to reproduce the Python canonicalisation
  exactly, and a divergence there would surface as an id that fails to verify
  (I-1, I-11).
* **No ``regime_id`` on ``type_assertions``**, which FR-014's "every candidate,
  type assertion and admitted claim MUST reference it" appears to ask for and
  which this revision deliberately does not do. ``semantic.contracts.TypeAssertion``
  has no such field, so adding a column here means every assertion ever persisted
  would mint a different ``TAR-`` -- a fleet-wide id migration, and a different
  decision from this one. The assertions already carry ``context_ref``, and the
  regime for a context is one ``semantic_regime`` read away, so the reference is
  reachable without touching an address. When the ladder is re-addressed, that is
  the revision that does it deliberately rather than as a side effect.

Two declared absences in the value types are reproduced as columns rather than
nulls, because a null cannot tell "nobody has said" from "not yet written" and
that distinction is what this substrate exists to keep:
``entity_identity.anchor_observation_id`` and ``anchor_capture_id`` are NOT NULL
defaulting to ``''`` because resolution never sees an observation or a capture, so
a caller that has them supplies them and a caller that does not records a
reconstruction hole rather than a fabricated id; and
``entity_identity.created_by_resolution`` is NOT NULL because
``UNATTRIBUTED_RESOLUTION`` is the spelling for "nobody can say". Likewise
``resolution_decision.entity_ref`` is NOT NULL defaulting to ``''``, because an
``ambiguous`` or ``unresolved`` pass names no entity *faithfully* and the empty
string is what makes those rows findable in the same index as the rest -- which is
SC-2, and the reason ``(tenant_id, supersedes)`` exists alongside
``(tenant_id, entity_ref, decided_at)``.

**The two regime columns differ on purpose.**
``candidates.regime_id`` is NOT NULL with ``server_default=''``, because a
candidate is extraction's output rather than an admitted fact and one that never
named a regime has always been a storable thing. ``relation_claim.regime_id`` is
NOT NULL with **no** default, because every writer of that table holds the
candidate the claim was built from and therefore always has a value to copy, and
because a default would let a claim that named no regime be stored as though it
had -- the silent substitution FR-016 forbids. One consequence is a real
operational cost rather than a style note: ``ALTER TABLE ... ADD COLUMN ... NOT
NULL`` with no default fails against a populated ``relation_claim`` table, and the
remedy is a data migration that reads each claim's candidate rather than a schema
default, because inventing the value is the defect this revision exists to end.
That is stated here so nobody meets it as a surprise and "fixes" it with a default.

``axis_declarations`` is an addition to the field list in the spec's Data
Requirements for ``data_stream``, which names ``time_axes_supplied``. The summary
alone answers "which axes does this stream have" and not "why does it not have
the other five", and the second question is the one FR-025 is about. Both columns
are written from one statement: the in-memory registrar refuses a stream whose
summary and declarations disagree, so the two cannot become two different stories
about one source.

The index set is what the read paths need, and there are no others.
``uq_capture_fingerprint`` is idempotency at the database rather than only in
:func:`domain.capture.InMemoryCaptureRegistry`, with ``tenant_id`` leading because
the address is tenant-scoped. ``ix_capture_target`` is the entry point to the
payload-dedup query; ``ix_capture_batch`` is FR-009's batch half; and
``ix_capture_time_basis`` answers SC-16's standing question -- which captures in
this tenant have no fetch time, and from which streams. ``captures.created_at`` is
left unindexed for the reason 017 left ``frontier_items.provenance`` and 018 left
``semantic_profiles.applies_to`` unindexed: nothing queries it, and an index over a
monotonic write clock on the highest-write-volume table in the acquisition path
costs write amplification for a scan nobody runs (ADR-0026). Batches are indexed on
the two read paths that differ by column -- "this source's runs in order" and "what
is still open" -- plus the per-stream question FR-024 asks. A bare tenant scan is
served by the leading column of each of those, so there is no separate tenant index
to keep in step with them.

The identity and regime indexes follow the same rule and cite their own read
paths. ``uq_entity_identity_anchor_mention`` is the resolution hot path and
``uq_entity_identity_entity`` is the write-once half that index set above is
silent about; both are unique, so a bare tenant scan is served by the leading
column of either and no third index is needed.
``ix_resolution_decision_entity`` answers "every decision about this entity, in
order" and ``ix_resolution_decision_supersedes`` answers "what superseded this
decision" -- and the second is not optional: an ``ambiguous`` or ``unresolved``
pass names no entity, so the chain is the only way it reaches the history of the
entity a later pass settled, and a scan per read would make reconstruction linear
in the whole log. ``uq_semantic_regime_tenant_address`` is the resolution hot path,
``uq_semantic_regime_fingerprint`` is idempotency, and
``ix_semantic_regime_current`` is the reconstruction hot path with ``recorded_at``
in the key so "the regime in force for this frame" is an index-ordered maximum and
``regime_id`` last as the tiebreak two processes must agree on (constitution VI).
``relation_claim.regime_id`` is indexed on nothing: a claim's regime is read by the
claim's own primary key, and no read path groups claims by regime.

Feature numbering and migration numbering are independent namespaces: this is
feature 018 and revision 019, because revision ``018_semantic_fabric`` was taken by
feature 017. The collision is harmless and is stated here so a reader does not
spend time on it.

Revision ``018_semantic_fabric`` is treated as already released and is never
edited. This file is the only place the world-substrate schema is expressed in
DDL, and a deployment that already ran 018 reaches it by applying 019 -- not by
amending a migration its database has already executed.

Ordering inside ``upgrade`` follows revisions 015, 016, 017 and 018: create tables,
add columns, backfill, then create indexes. No index is ever built against a column
that does not exist yet. Section 3 is recorded as a near-no-op rather than dropped,
so a reader of the file can see that "there is nothing to reconcile" is a decision
and not an omission.

``downgrade`` deliberately does **not** reverse this revision, and the argument is
where it is written.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "019_world_substrate"
down_revision = "018_semantic_fabric"
branch_labels = None
depends_on = None

# The tables this revision introduces, in creation order. Referenced by the
# section-3 note below so that "there is nothing to reconcile" is recorded as a
# positive statement about this table set rather than as an absence.
_ACTIVE = (
    "captures",
    "ingest_batches",
    "data_stream",
    "entity_identity",
    "resolution_decision",
    "semantic_regime",
)

# The two regime columns added to tables that already exist, in the order they
# are added. Named so the section-2 call site and its section-4 index can be read
# against each other, and so a later revision that widens either has the pair to
# find rather than to rediscover.
_REGIME_COLUMNS = (
    ("candidates", ""),
    ("relation_claim", None),
)

# The sentinel a capture carries when no ingestion run is being attributed. It
# mirrors ``domain.capture.UNBATCHED_INGEST_BATCH`` and is written as a literal on
# both the ORM and the DDL side so a fresh install and an upgraded one agree.
_UNBATCHED = "unbatched"

# The one basis that may carry a ``fetched_at``, and the two checks that keep the
# pair honest. Listed as constants so the constraint text is stated once and the
# forward-only test can assert this revision never weakens either -- a migration
# that dropped ``ck_capture_fetch_time_basis`` would be how a crawl index
# timestamp gets promoted into a fetch time by a later editor who did not know why
# the constraint was there.
_FETCH_BASIS = "fetch"
_FETCH_TIME_PRESENT = "capture_time_basis <> 'fetch' OR fetched_at IS NOT NULL"
_FETCH_TIME_BASIS = "fetched_at IS NULL OR capture_time_basis = 'fetch'"

# The four verdicts ``semantic.resolution.ResolutionVerdict`` admits, and the
# three rungs ``semantic.regime.SemanticCommitment`` admits, as plain text. Both
# vocabularies are closed and both have to be orderable, so both are stated as
# checks here rather than left to a reader of the value types: a row carrying a
# fifth verdict or a fourth rung is a corrupt row, and a CHECK is what makes a bulk
# loader meet the same refusal the value type gives.
_DECISION_VERDICTS = ("resolved", "ambiguous", "unresolved", "conflicted")
_REGIME_COMMITMENTS = ("uncommitted", "typed", "mapped")

# The two machine-owned prefixes, checked at the storage layer rather than only
# by the constructors. A row keyed by a digest of itself is well-formed SQL and
# would join to nothing anywhere in the platform, and the value types that refuse
# it are not on the path a bulk loader takes.
_ENTITY_PREFIX = "ENT-"
_DECISION_PREFIX = "RES-"


def _vocabulary(values: tuple[str, ...]) -> str:
    """One closed vocabulary as a CHECK body, stated once so both tables agree.

    Not ``sa.Enum``: the recent revisions spell their categorical columns as
    checks precisely because a CHECK renders identically in ``create_all`` and in
    the migration, and an ``sa.Enum`` does not. It would also put the vocabulary
    in the type system of the column, where a value type that re-declares the same
    closed set as text -- as both of these do, so a row loads in a process with no
    semantic layer installed -- would then have two places to keep in step.
    """
    return "IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def _add_regime_columns() -> None:
    """Section 2: the two columns this revision adds to tables that already exist.

    Both carry the ``regime_id`` a decision was taken under, and they differ on
    purpose. ``candidates.regime_id`` defaults to ``''`` because a candidate is
    extraction's output rather than an admitted fact, and one that never named a
    regime has always been a storable thing -- the empty string is a *declared*
    absence, and it cannot make one read as a match, because
    ``semantic.resolution.analyse_candidate`` reports ``regime_unevaluated`` for
    an empty side and ``semantic.regime_store`` refuses a blank lookup outright
    (FR-016).

    ``relation_claim.regime_id`` has no default, because every writer of that
    table holds the candidate the claim was built from and therefore always has a
    value to copy: the regime was fixed before the claim existed, so this column
    records no new fact and has nothing to drift. A default would let a claim that
    named no regime be stored as though it had, which is the substitution FR-016
    forbids. The cost is stated in the header rather than hidden here: adding a
    NOT NULL column with no default fails against a populated ``relation_claim``,
    and the fix is a data migration reading each claim's candidate, never a
    schema default -- inventing the value is the defect this revision ends.

    ``observations.capture_id`` is deliberately not here. It is the next hop of
    the same feature and belongs to the orchestrator change that stops fabricating
    a capture id; adding it before the code that populates it would leave a column
    every current writer in the platform still sets to nothing.
    """
    for table, default in _REGIME_COLUMNS:
        # Through the constructor, not by assigning ``.server_default`` afterwards: a
        # bare string assigned to the attribute is not a ``DefaultClause`` and never
        # reaches the DDL, so the default would silently vanish from the emitted
        # ``ALTER`` while still reading as present in the Python.
        declared = {} if default is None else {"server_default": default}
        op.add_column(
            table, sa.Column("regime_id", sa.String(64), nullable=False, **declared)
        )


def _no_backfill() -> None:
    """Section 3: no historical row needs a value written by application code.

    All six tables are new, so there is no pre-existing row to reconcile. That
    matters for ``captures`` in particular: the captures the platform recorded
    before this revision were not rows, they were strings derived from
    ``(source_id, observation_id)``, and there is no honest way to turn one of
    those into a row here. A backfill would have to invent a ``fetched_at``, which
    is the defect this revision exists to end, so those acquisitions stay
    unreconstructable and are recorded as such rather than being filled in.

    The two section-2 columns are *not* a backfill, and the difference is the
    point. ``candidates.regime_id`` is materialised by its own server default, so
    the existing candidates read as naming no regime -- which is what they
    actually are, and which is why the golden path's ``regime_unevaluated`` was
    honest rather than broken. ``relation_claim.regime_id`` is not materialised
    and not defaulted, so a deployment carrying claims must migrate them from the
    candidate each was built from; that is a data migration and it is a later
    revision, because the only honest way to fill the column is to read the fact
    out of the claim's own history.
    """


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. New tables
    # ------------------------------------------------------------------
    op.create_table(
        "captures",
        sa.Column("capture_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("source_family", sa.String(64), nullable=False, server_default=""),
        sa.Column("target_uri", sa.Text(), nullable=False, server_default=""),
        sa.Column("locator", sa.Text(), nullable=False, server_default=""),
        sa.Column("content_digest", sa.String(128), nullable=False),
        sa.Column("content_length", sa.Integer()),
        sa.Column("media_type", sa.String(128), nullable=False, server_default=""),
        sa.Column("fetched_at", sa.DateTime(timezone=True)),
        sa.Column("capture_time_basis", sa.String(24), nullable=False),
        sa.Column("transport", sa.String(32), nullable=False, server_default=""),
        sa.Column("ingest_batch_id", sa.String(64), nullable=False, server_default=_UNBATCHED),
        sa.Column("ingest_attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("recorded_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("capture_fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("tenant_id <> ''", name="ck_capture_tenant"),
        sa.CheckConstraint("content_digest <> ''", name="ck_capture_content_digest"),
        sa.CheckConstraint(_FETCH_TIME_PRESENT, name="ck_capture_fetch_time_present"),
        sa.CheckConstraint(_FETCH_TIME_BASIS, name="ck_capture_fetch_time_basis"),
        sa.CheckConstraint(
            "content_length IS NULL OR content_length >= 0", name="ck_capture_length"
        ),
        sa.CheckConstraint("ingest_attempt >= 1", name="ck_capture_attempt"),
    )
    op.create_table(
        "ingest_batches",
        sa.Column("batch_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("stream_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("opened_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("record_count", sa.Integer()),
        sa.Column("state", sa.String(16), nullable=False, server_default="open"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("tenant_id <> ''", name="ck_ingest_batch_tenant"),
        sa.CheckConstraint(
            "state IN ('open', 'closed', 'aborted')", name="ck_ingest_batch_state"
        ),
        sa.CheckConstraint(
            "record_count IS NULL OR record_count >= 0", name="ck_ingest_batch_count"
        ),
        sa.CheckConstraint(
            "state <> 'closed' OR closed_at IS NOT NULL", name="ck_ingest_batch_close"
        ),
    )
    op.create_table(
        "data_stream",
        sa.Column("stream_id", sa.String(96), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("temporality", sa.String(32), nullable=False),
        sa.Column("time_axes_supplied", postgresql.JSONB(), nullable=False),
        sa.Column("axis_declarations", postgresql.JSONB(), nullable=False),
        sa.Column("adapter_ref", sa.String(255), nullable=False, server_default=""),
        sa.Column(
            "registered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("tenant_id <> ''", name="ck_data_stream_tenant"),
        sa.CheckConstraint("kind <> ''", name="ck_data_stream_kind"),
        sa.CheckConstraint("temporality <> ''", name="ck_data_stream_temporality"),
        sa.CheckConstraint("adapter_ref <> ''", name="ck_data_stream_adapter_ref"),
    )
    # The durable statement of an anchor: which mention introduced this entity,
    # which observation that mention came from, which capture fetched those bytes,
    # and which resolution concluded it. A separate table rather than columns on
    # `entities` because bolt-on columns admit a partial write leaving an entity
    # with no anchor, and the next layer up reads that as a valid entity (D-A).
    #
    # `created_at` carries no server default, and the reason is the value type's:
    # `EntityIdentity.__post_init__` fails closed on an absent creation time,
    # because a module that reads no clock and a row with a defaulted clock would
    # be two answers to one question. Same for `decided_at` below. The write clock
    # is the caller's to state, and the columns that *are* defaulted here are the
    # ones whose absence is a fact rather than an omission.
    op.create_table(
        "entity_identity",
        sa.Column("entity_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("anchor_mention_id", sa.String(64), nullable=False),
        sa.Column("anchor_observation_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("anchor_capture_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_by_resolution", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("identity_fingerprint", sa.String(64), nullable=False),
        sa.CheckConstraint("tenant_id <> ''", name="ck_entity_identity_tenant"),
        sa.CheckConstraint(
            "anchor_mention_id <> ''", name="ck_entity_identity_anchor_mention"
        ),
        sa.CheckConstraint("created_by_resolution <> ''", name="ck_entity_identity_creator"),
        sa.CheckConstraint(
            f"entity_id LIKE '{_ENTITY_PREFIX}%'", name="ck_entity_identity_entity_prefix"
        ),
    )
    # The whole reasoning behind an identity, field for field with
    # `domain.entity_identity.ResolutionDecisionRecord`, so the row is a faithful
    # image and not a summary (FR-003, D2). `resolution_decision_id` is the
    # resolver's own `RES-` and is never computed from this row; see the header.
    #
    # The six ordered projections are JSONB sequences rather than normalised child
    # tables, and the ordering is the reason: `reasons` is the order the
    # compatibility layers produced it in, and a reordering would change the
    # address of a decision whose reasoning did not change. `blocking`,
    # `collective` and `hypothesis` are nullable because the machine may have run
    # no collective pass at all, and an empty object would read as "ran and found
    # nothing" -- a different fact.
    op.create_table(
        "resolution_decision",
        sa.Column("resolution_decision_id", sa.String(64), primary_key=True),
        sa.Column("record_fingerprint", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("mention_id", sa.String(64), nullable=False),
        sa.Column("surface", sa.Text(), nullable=False),
        sa.Column("verdict", sa.String(16), nullable=False),
        sa.Column("entity_ref", sa.String(64), nullable=False, server_default=""),
        sa.Column("anchor_mention_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("anchor_key", sa.Text(), nullable=False, server_default=""),
        sa.Column("merged_mentions", postgresql.JSONB(), nullable=False),
        sa.Column("considered", postgresql.JSONB(), nullable=False),
        sa.Column("surviving", postgresql.JSONB(), nullable=False),
        sa.Column("scored", postgresql.JSONB(), nullable=False),
        sa.Column("corroboration", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("confidence_parts", postgresql.JSONB(), nullable=False),
        sa.Column("normalization", postgresql.JSONB(), nullable=False),
        sa.Column("notes", postgresql.JSONB(), nullable=False),
        sa.Column("resolution_scope_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("operator_ref", sa.String(64), nullable=False, server_default=""),
        sa.Column("normalization_version", sa.String(32), nullable=False, server_default=""),
        sa.Column("ontology_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("regime_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("reasons", postgresql.JSONB(), nullable=False),
        sa.Column("blocked_out", postgresql.JSONB(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("blocking", postgresql.JSONB()),
        sa.Column("collective", postgresql.JSONB()),
        sa.Column("hypothesis", postgresql.JSONB()),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("supersedes", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint("tenant_id <> ''", name="ck_resolution_decision_tenant"),
        sa.CheckConstraint("mention_id <> ''", name="ck_resolution_decision_mention"),
        sa.CheckConstraint(
            f"resolution_decision_id LIKE '{_DECISION_PREFIX}%'",
            name="ck_resolution_decision_id_prefix",
        ),
        sa.CheckConstraint(
            f"verdict {_vocabulary(_DECISION_VERDICTS)}",
            name="ck_resolution_decision_verdict",
        ),
        # The machine clamps every contribution into 0.0..1.0, so a stored
        # confidence outside it is a corrupt row rather than a surprising one.
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_resolution_decision_confidence",
        ),
    )
    # The instruments a reading was interpreted under, which is the input the
    # platform was missing: `regime_id` was in no table, so every compatibility
    # check against a candidate's regime returned UNEVALUATED on the golden path
    # on every run (D6, FR-014).
    #
    # `recorded_at` is the one nullable timestamp in this revision, and it is
    # nullable because the value type's is: an unrecorded time is an absence
    # rather than a minimum, and it sorts last in the recency order rather than
    # displacing a dated regime. `context_ref` may also be empty -- a regime read
    # under no instrument at all is a first-class state under FR-014, not a hole,
    # and refusing it would make the no-commitment path the one regime that could
    # not be written down.
    op.create_table(
        "semantic_regime",
        sa.Column("regime_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("context_ref", sa.String(64), nullable=False),
        sa.Column("profile_ref", sa.String(96), nullable=False),
        sa.Column("profile_version", sa.String(32), nullable=False),
        sa.Column("ontology_version", sa.String(64), nullable=False),
        sa.Column("mapping_set_id", sa.String(64), nullable=False),
        sa.Column("mapping_set_version", sa.String(32), nullable=False),
        sa.Column("validation_profile", sa.String(64), nullable=False),
        sa.Column("policy_snapshot_ref", sa.String(96), nullable=False),
        sa.Column("operator_ref", sa.String(64), nullable=False),
        sa.Column("localization", sa.String(128), nullable=False),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("temporal_frame_ref", sa.String(64), nullable=False),
        sa.Column("supersedes", sa.String(128), nullable=False, server_default=""),
        sa.Column("commitment", sa.String(16), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("instruments", postgresql.JSONB(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True)),
        sa.Column("record_fingerprint", sa.String(64), nullable=False),
        sa.CheckConstraint("tenant_id <> ''", name="ck_semantic_regime_tenant"),
        sa.CheckConstraint(
            f"commitment {_vocabulary(_REGIME_COMMITMENTS)}",
            name="ck_semantic_regime_commitment",
        ),
    )

    # ------------------------------------------------------------------
    # 2. New columns on tables that already exist
    # ------------------------------------------------------------------
    _add_regime_columns()

    # ------------------------------------------------------------------
    # 3. Backfill (none required; all six tables are created empty)
    # ------------------------------------------------------------------
    _no_backfill()

    # ------------------------------------------------------------------
    # 4. Indexes (last, so every column they reference already exists)
    # ------------------------------------------------------------------
    # Idempotency at the database rather than only in the in-memory registry
    # (I-11). Tenant leads because the address is tenant-scoped: two tenants
    # fetching identical bytes must never collide on one id (constitution IV).
    op.create_index(
        "uq_capture_fingerprint",
        "captures",
        ["tenant_id", "capture_fingerprint"],
        unique=True,
    )
    # The entry point to the payload-dedup query: every capture of one target, from
    # which the payload key is computed over the small candidate set. The payload
    # key itself is deliberately not a column -- it is a function of five columns
    # that are already here, and storing a derived value is one more writer that
    # can disagree with the content address.
    op.create_index("ix_capture_target", "captures", ["tenant_id", "target_uri"])
    # FR-009's batch half: what did this ingestion run fetch.
    op.create_index("ix_capture_batch", "captures", ["tenant_id", "ingest_batch_id"])
    # SC-16's standing question: which captures in this tenant have no fetch time,
    # and from which streams.
    op.create_index(
        "ix_capture_time_basis", "captures", ["tenant_id", "capture_time_basis"]
    )
    # This source's runs in order, and what is still running -- two read paths
    # through two different columns, so two indexes.
    op.create_index(
        "ix_ingest_batch_source", "ingest_batches", ["tenant_id", "source_id", "opened_at"]
    )
    op.create_index("ix_ingest_batch_state", "ingest_batches", ["tenant_id", "state"])
    # FR-024's per-stream question: which acquisition events a registered stream
    # produced.
    op.create_index("ix_ingest_batch_stream", "ingest_batches", ["tenant_id", "stream_id"])
    # The registry read. `stream_id` is the primary key, so a name lookup is a
    # single indexed read and this index serves the "which streams does this tenant
    # run" question, with the temporality filter applied on top.
    op.create_index("ix_data_stream_temporality", "data_stream", ["tenant_id", "temporality"])
    # The resolution hot path: "does this mention already anchor an entity?". Unique,
    # which is what makes the anchor write-once structurally rather than by
    # convention -- the load is on `anchor_for_mention` and the constraint is the
    # same two columns (D-A, SC-17).
    op.create_index(
        "uq_entity_identity_anchor_mention",
        "entity_identity",
        ["tenant_id", "anchor_mention_id"],
        unique=True,
    )
    # The other half of "write-once", and the one the plan's index set does not
    # have: "one entity has at most one anchor". A second anchor for a
    # known entity is invisible to the index above, and an anchor that moves
    # silently is exactly the failure FR-001 forbids. Together the two are this
    # feature's load-bearing guarantee, and the in-memory store is where the
    # second half gets a typed `entity_reanchored` refusal as well.
    op.create_index(
        "uq_entity_identity_entity",
        "entity_identity",
        ["tenant_id", "entity_id"],
        unique=True,
    )
    # Idempotency at the database rather than only in the in-memory store (I-11).
    # `created_at` is deliberately absent from this key: re-binding one anchor at a
    # different moment is the same write, and a write clock in a unique key would
    # make it a different one (constitution VII, FR-022).
    op.create_index(
        "uq_entity_identity_fingerprint",
        "entity_identity",
        ["tenant_id", "identity_fingerprint"],
        unique=True,
    )
    # The reconstruction hot path: every decision about one entity, oldest first,
    # with `decided_at` in the key so the order is the index's order rather than a
    # sort. The `entity_ref = ''` rows are in this index too, which is what makes
    # the passes that named no entity findable at all.
    op.create_index(
        "ix_resolution_decision_entity",
        "resolution_decision",
        ["tenant_id", "entity_ref", "decided_at"],
    )
    # The reverse edge of the `supersedes` chain, and the reason SC-2 is reachable.
    # An `ambiguous` or `unresolved` pass names no entity, so it cannot be filed
    # under one without a record lying about what the resolver concluded; the
    # chain is what puts it in the history of the entity a later pass settled
    # (FR-004). Without this index `history_for` is a scan per read and
    # reconstruction is linear in the whole log.
    op.create_index(
        "ix_resolution_decision_supersedes",
        "resolution_decision",
        ["tenant_id", "supersedes"],
    )
    # Idempotency at the database, decided on the content address rather than on
    # row equality: the same reasoning about the same mention is one decision
    # however often it is replayed, and a different record under one address is a
    # conflict rather than an overwrite (FR-003, I-11).
    op.create_index(
        "uq_resolution_decision_fingerprint",
        "resolution_decision",
        ["tenant_id", "record_fingerprint"],
        unique=True,
    )
    # The regime named by the `regime_id` on a candidate -- the read that turns
    # `regime_unevaluated` into `regime_compatible` on the golden path. UNIQUE
    # rather than the bare primary key because the *pair* is the store's key: the
    # cross-tenant refusal exists only if two tenants may hold different records at
    # the same address (constitution IV, FR-005).
    op.create_index(
        "uq_semantic_regime_tenant_address",
        "semantic_regime",
        ["tenant_id", "regime_id"],
        unique=True,
    )
    # "What did we believe when we read this frame?", as an index-ordered maximum
    # rather than a sort: `recorded_at` is in the key, descending, and `regime_id`
    # last as the tiebreak two processes must agree on (constitution VI). This is
    # the only place a write clock appears in an index in this revision, and it is
    # deliberately non-unique -- a plain index orders, a unique one constrains, and
    # constraining on a clock would break the replay fixed point.
    op.create_index(
        "ix_semantic_regime_current",
        "semantic_regime",
        ["tenant_id", "context_ref", sa.text("recorded_at DESC"), "regime_id"],
    )
    # Idempotency at the database rather than only in the in-memory store (I-11).
    op.create_index(
        "uq_semantic_regime_fingerprint",
        "semantic_regime",
        ["tenant_id", "record_fingerprint"],
        unique=True,
    )
    # Every candidate read under one regime, which is the population a
    # re-interpretation has to revisit. `relation_claim.regime_id` is indexed on
    # nothing: a claim's regime is read by the claim's own primary key, and no
    # read path groups claims by regime.
    op.create_index("ix_candidates_regime", "candidates", ["tenant_id", "regime_id"])


def downgrade() -> None:
    """Refuse. This revision's tables are the record of what was believed.

    015 and 016 reverse their own upgrades and 017 drops the single column it
    added, and for all three that is the right answer: they reshape storage, so
    undoing them undoes the reshaping. Neither answer is available here. Dropping
    ``captures`` would delete the only record of which bytes this platform ever
    obtained; dropping ``ingest_batches`` would delete the run boundaries that
    make a capture distinguishable from a re-read of the same payload; dropping
    ``entity_identity`` would delete every anchor, so the next batch would mint a
    fresh ``ENT-`` for an entity that already had one; dropping
    ``resolution_decision`` would delete the reasoning behind every identity,
    including the passes that concluded ``ambiguous`` and therefore named none;
    and dropping ``semantic_regime`` would delete the record of what each reading
    was interpreted under, which is the input FR-014 exists to store. A downgrade
    would then be the only operation in the platform able to remove an identity or
    a reasoning, on the strength of a schema version number.

    A reverse that destroys the substrate's central guarantee is worse than no
    reverse, so this raises. Rolling back is a forward operation: add revision 020
    that states what the schema becomes instead.
    """
    raise NotImplementedError(
        "019_world_substrate is forward-only: captures is the only record of which "
        "bytes were obtained, ingest_batches is what keeps a capture "
        "distinguishable from a re-read of the same payload, entity_identity is "
        "the only record of which mention introduced an entity, resolution_decision "
        "is the only record of why one, and semantic_regime is the only record of "
        "what a reading was interpreted under, so a downgrade would destroy "
        "exactly what this revision exists to make durable. Add a new forward "
        "revision instead."
    )
