"""Alembic migration for the universal relation extraction substrate (feature 019).

``specs/019-universal-relation-extraction/spec.md`` CD-1, CD-3, CD-5, CD-6, CD-7 and
FR-018, FR-019, FR-034, FR-041…FR-043. What becomes durable here is the part of the
relation lifecycle that had no home: a hypothesis nobody admitted, the observations that
produced it, and the instants the sources stated.

Three new tables, in dependency order, and one widening:

* :meth:`_upgrade_source_temporal_observation` - the instants sources state. CD-5's whole
  argument is that these are not capture fields: a registrar's acceptance datetime is a
  fact about the world, a capture is a record of an act of retrieval, and one document may
  state several instants at several precisions. ``capture_ref`` is indexed but is
  deliberately **not** a foreign key, because the fact a filing carries does not evaporate
  because we re-ingested the index it came from - and a foreign key would make re-ingest
  order a correctness question instead of a housekeeping one.

* :meth:`_upgrade_relation_signal` - what producers saw, *below* the candidate. Storing
  only the candidate would throw the observations away, and FR-034's independence count is
  computed over observations, so a claim three sources corroborate would otherwise have to
  take its corroboration on trust from a single row. Three CHECK constraints do the work
  the value type does in memory, so a bulk loader meets the same refusals:
  a non-empty tenant, a stated predicate of some kind, and a confidence inside ``[0, 1]``.

* :meth:`_upgrade_relation_candidate` - the first durable home for a
  :class:`domain.relation_candidate.RelationCandidate`. SC-B is this table: a hypothesis
  nobody admitted can now be stored, read back and shown. Keyed by the *revision* address
  (``CNDR-``) because a row is one reading, with the logical address carried alongside so
  "what did we make of this hypothesis?" is an indexed read.

* :meth:`_widen_candidate_references` - CD-3, and the reason this revision exists as well
  as three ``CREATE TABLE``s. **The widening was measured before it was written**, and the
  measurement changed the shape of the job: a ``CAND-`` or ``CNDR-`` address is 37
  characters, so the platform-wide ``VARCHAR(36)`` would cut the last hex digit off every
  candidate id in these columns. What the measurement *also* showed is that nothing writes
  one today - ``candidates`` belongs to feature 008's extraction path and holds a
  different kind of candidate, with ``mention_ids`` and a ``type_hypothesis`` and no
  operator identity at all. So ``candidates.candidate_id`` is **not** widened: it is a
  different column about a different thing, and widening it would invite exactly the
  confusion the new ``relation_candidate`` table exists to prevent. Only the two columns
  that would actually carry a semantic-layer reference are widened, and they are widened
  now so the reference is *possible* when 019 begins making it.

Every table is tenant-scoped and fail-closed: ``tenant_id`` is NOT NULL and additionally
checked against ``''``, for the reason 018 and 019 both gave and this revision repeats.
NOT NULL alone still admits ``''``, and ``''`` is not a tenant (constitution IV).

Forward-only, like 019 and for the same reason. Dropping ``relation_candidate`` would
delete every reading the platform formed about a relation, including the ones it then
refused; dropping ``relation_signal`` would delete the observations, so the candidates that
remain would lose their basis and FR-034's independence count would become a number
nobody could check; dropping ``source_temporal_observation`` would delete the stated
instants, and the next ingest would write them again with different precision conventions
and no record that the first reading existed.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "020_universal_relation_extraction"
down_revision = "019_world_substrate"

#: The prefix that identifies a 019 candidate address in a column too narrow for it.
#: Written as a literal rather than imported, because a migration that reads a value type
#: is a migration whose meaning changes when that type is edited. 018 and 019 both take
#: this stance and this one follows it.
_CANDIDATE_PREFIXES = ("CAND-", "CNDR-")

#: The two columns that would carry a semantic-layer candidate reference, and the width
#: they move to. Named so the call site and the note in ``db/schema.py`` can be read
#: against each other.
_CANDIDATE_REFERENCE_COLUMNS = (
    ("evidence_links", "candidate_id"),
    ("admission_decisions", "candidate_id"),
)

#: The width. 64 rather than 37 because a column sized to today's exact address is a
#: column that has to be migrated the first time a digest gets wider or a prefix gets a
#: character, and a migration is a place where somebody can be wrong. A too-wide column
#: costs a few bytes a row; a too-narrow one silently corrupts an address.
_ID_WIDTH = 64

#: The four verdicts ``domain.relation_candidate.CandidateStatus`` admits, and the four
#: rungs ``domain.predicate_hypothesis.PredicateResolutionState`` admits, as plain text.
#: Both vocabularies are closed, so both are stated as checks rather than left to a reader
#: of the value types: a row carrying a fifth verdict is a corrupt row, and a CHECK is what
#: makes a bulk loader meet the refusal the value type gives.
_CANDIDATE_STATUSES = ("propose", "supported", "contradicted", "rejected")
_PREDICATE_STATES = ("known", "unknown", "ambiguous", "conflicting")

#: The thirteen signal kinds ``extractors.signals.signal.SignalKind`` admits, written out
#: rather than imported. A migration that reads a value type is a migration whose meaning
#: changes when somebody edits that type: renaming a member would silently rewrite history,
#: and adding one would leave every already-migrated database refusing rows the code
#: believes are valid. The duplication is deliberate and is the same stance 019 took.
#:
#: The list is the honest record of what the platform can notice. It is a capability
#: surface, so it is stated here where a reviewer will see it, rather than derived from
#: somewhere it would look incidental.
_SIGNAL_KINDS = (
    "lexical",
    "link",
    "reference",
    "table",
    "list",
    "metadata",
    "attribute",
    "hierarchy",
    "schema",
    "co_occurrence",
    "coreference",
    "quantity",
    "negation",
)

#: The four direction hypotheses, likewise. `ambiguous` is in the list because a producer
#: that found a marker it could read two ways must be able to say so at the storage layer
#: too - a table that could only hold a resolved direction would push the choice into the
#: producer, which is the fabrication CD-6 is about.
_DIRECTIONS = (
    "subject_to_object",
    "object_to_subject",
    "undirected",
    "ambiguous",
)

#: The six temporal axes, and the single basis that means "the source had no such field".
#: The pair is what makes a stated emptiness a stated emptiness: a row with
#: ``basis='absent'`` and no value is a source that had no such date, which is different
#: from a row nobody has finished writing.
_TEMPORAL_AXES = (
    "fetched_at",
    "observed_at",
    "published_at",
    "valid_from",
    "valid_to",
    "known_from",
)
_ABSENT_BASIS = "absent"

#: The three checks that keep a temporal observation honest. Each has a counterpart in
#: :meth:`domain.temporal_observation.SourceTemporalObservation.__post_init__`, and the
#: duplication is the point: a constraint that exists only in Python is a constraint a
#: ``COPY`` walks straight past.
_VALUE_PRESENT = f"basis <> '{_ABSENT_BASIS}' OR stated_value IS NOT NULL"
_ABSENT_HAS_NO_VALUE = f"stated_value IS NULL OR basis <> '{_ABSENT_BASIS}'"
_RANGE_START = "stated_value_end IS NULL OR stated_value IS NOT NULL"
_RANGE_ORDER = "stated_value_end IS NULL OR stated_value_end >= stated_value"

#: The one direction a stated-predicate check may refuse. A reading may name an operator
#: and no surface; it may not be a surface with nothing saying whether it resolved. The
#: reverse - a row asserting no predicate at all - is refused by the value type, and the
#: database's job is only to catch a loader that skipped it.
_CANDIDATE_ASSERTS = "relation_surface <> '' OR relation_ref IS NOT NULL"
_SIGNAL_ASSERTS = "relation_surface <> '' OR relation_ref IS NOT NULL"


def _in(column: str, values: tuple[str, ...]) -> str:
    """A closed-vocabulary membership test, quoted so the DDL is readable in a log."""
    allowed = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({allowed})"


def _widen_candidate_references() -> None:
    """CD-3: take every column that can hold a candidate address to VARCHAR(64).

    ``ALTER TABLE ... ALTER COLUMN ... TYPE VARCHAR(64)`` rather than a drop-and-add, so
    the operation is metadata-only on Postgres for these types and existing rows keep
    their values. That matters more than it sounds: this column may already hold
    references, and a rewrite that dropped and re-added the column would be a chance to
    lose them.
    """
    for table, column in _CANDIDATE_REFERENCE_COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.String(_ID_WIDTH),
            existing_type=sa.String(36),
            existing_nullable=True,
        )


def _upgrade_source_temporal_observation() -> None:
    op.create_table(
        "source_temporal_observation",
        sa.Column("observation_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("capture_ref", sa.String(64), nullable=False),
        sa.Column("temporal_axis", sa.String(24), nullable=False),
        sa.Column("stated_value", sa.DateTime(timezone=True)),
        sa.Column("stated_value_end", sa.DateTime(timezone=True)),
        sa.Column("raw_value", sa.Text(), nullable=False, server_default=""),
        sa.Column("precision", sa.String(16), nullable=False),
        sa.Column("basis", sa.String(24), nullable=False),
        sa.Column("evidence_location", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("tenant_id <> ''", name="ck_temporal_observation_tenant"),
        sa.CheckConstraint("capture_ref <> ''", name="ck_temporal_observation_capture"),
        sa.CheckConstraint(
            "evidence_location <> ''", name="ck_temporal_observation_location"
        ),
        sa.CheckConstraint(
            _VALUE_PRESENT, name="ck_temporal_observation_value_present"
        ),
        sa.CheckConstraint(
            _ABSENT_HAS_NO_VALUE, name="ck_temporal_observation_absent_basis"
        ),
        sa.CheckConstraint(_RANGE_START, name="ck_temporal_observation_range_start"),
        sa.CheckConstraint(_RANGE_ORDER, name="ck_temporal_observation_range_order"),
        sa.CheckConstraint(
            _in("temporal_axis", _TEMPORAL_AXES), name="ck_temporal_observation_axis"
        ),
    )
    op.create_index(
        "ix_temporal_observation_tenant",
        "source_temporal_observation",
        ["tenant_id"],
    )
    op.create_index(
        "ix_temporal_observation_capture",
        "source_temporal_observation",
        ["tenant_id", "capture_ref"],
    )
    op.create_index(
        "ix_temporal_observation_axis",
        "source_temporal_observation",
        ["tenant_id", "temporal_axis"],
    )


def _upgrade_relation_signal() -> None:
    op.create_table(
        "relation_signal",
        sa.Column("signal_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("subject_mention_ref", sa.String(64), nullable=False),
        sa.Column("object_mention_ref", sa.String(64), nullable=False),
        sa.Column("signal_kind", sa.String(24), nullable=False),
        sa.Column("direction", sa.String(24), nullable=False),
        sa.Column("relation_ref", sa.String(96)),
        sa.Column("relation_surface", sa.Text(), nullable=False, server_default=""),
        sa.Column("predicate_hypothesis", sa.String(64), nullable=False, server_default=""),
        sa.Column("predicate_state", sa.String(16), nullable=False),
        sa.Column("producer_ref", sa.String(96), nullable=False, server_default=""),
        sa.Column("producer_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("context_ref", sa.String(64), nullable=False, server_default=""),
        sa.Column("semantic_regime_ref", sa.String(64), nullable=False, server_default=""),
        sa.Column("capture_ref", sa.String(64), nullable=False, server_default=""),
        sa.Column("neighbourhood", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("trigger_span", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("supporting_spans", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("stated_axes", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column(
            "producer_confidence", sa.Float(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("signal_ordinal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("tenant_id <> ''", name="ck_relation_signal_tenant"),
        sa.CheckConstraint(_SIGNAL_ASSERTS, name="ck_relation_signal_asserts_something"),
        sa.CheckConstraint(
            "producer_confidence >= 0 AND producer_confidence <= 1",
            name="ck_relation_signal_confidence",
        ),
        sa.CheckConstraint(
            "subject_mention_ref <> object_mention_ref", name="ck_relation_signal_distinct"
        ),
        sa.CheckConstraint(_in("signal_kind", _SIGNAL_KINDS), name="ck_relation_signal_kind"),
        sa.CheckConstraint(
            _in("direction", _DIRECTIONS), name="ck_relation_signal_direction"
        ),
        sa.CheckConstraint(
            _in("predicate_state", _PREDICATE_STATES), name="ck_relation_signal_predicate_state"
        ),
    )
    op.create_index("ix_relation_signal_tenant", "relation_signal", ["tenant_id"])
    op.create_index(
        "ix_relation_signal_pair",
        "relation_signal",
        ["tenant_id", "subject_mention_ref", "object_mention_ref"],
    )
    op.create_index(
        "ix_relation_signal_producer", "relation_signal", ["tenant_id", "producer_ref"]
    )


def _upgrade_relation_candidate() -> None:
    op.create_table(
        "relation_candidate",
        sa.Column("candidate_id", sa.String(64), primary_key=True),
        sa.Column("logical_candidate_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("subject_mention_ref", sa.String(64), nullable=False),
        sa.Column("object_mention_ref", sa.String(64), nullable=False),
        sa.Column("arity_mode", sa.String(16), nullable=False),
        sa.Column("relation_ref", sa.String(96)),
        sa.Column("relation_type", sa.String(64), nullable=False, server_default=""),
        sa.Column("relation_surface", sa.Text(), nullable=False, server_default=""),
        sa.Column("predicate_hypothesis", sa.String(64), nullable=False),
        sa.Column("predicate_state", sa.String(16), nullable=False),
        sa.Column("context_ref", sa.String(64), nullable=False),
        sa.Column("semantic_regime_ref", sa.String(64), nullable=False),
        sa.Column("candidate_status", sa.String(16), nullable=False),
        sa.Column("extraction_method", sa.String(32), nullable=False),
        sa.Column("extractor_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("extraction_rule_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("investigation_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("recorded_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("observation_refs", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("evidence_refs", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("trigger_span", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("supporting_spans", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("temporal_hypothesis", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("role_assignments", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("observed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("tenant_id <> ''", name="ck_relation_candidate_tenant"),
        sa.CheckConstraint(
            "logical_candidate_id <> ''", name="ck_relation_candidate_logical"
        ),
        sa.CheckConstraint(
            "subject_mention_ref <> object_mention_ref", name="ck_relation_candidate_distinct"
        ),
        sa.CheckConstraint(_CANDIDATE_ASSERTS, name="ck_relation_candidate_asserts_something"),
        sa.CheckConstraint("context_ref <> ''", name="ck_relation_candidate_context"),
        sa.CheckConstraint(
            "semantic_regime_ref <> ''", name="ck_relation_candidate_regime"
        ),
        sa.CheckConstraint(
            _in("candidate_status", _CANDIDATE_STATUSES), name="ck_relation_candidate_status"
        ),
        sa.CheckConstraint(
            _in("predicate_state", _PREDICATE_STATES), name="ck_relation_candidate_predicate_state"
        ),
        sa.CheckConstraint(
            _in("arity_mode", ("directed", "undirected", "nary")),
            name="ck_relation_candidate_arity",
        ),
    )
    op.create_index("ix_relation_candidate_tenant", "relation_candidate", ["tenant_id"])
    op.create_index(
        "ix_relation_candidate_logical",
        "relation_candidate",
        ["tenant_id", "logical_candidate_id"],
    )
    op.create_index(
        "ix_relation_candidate_pair",
        "relation_candidate",
        ["tenant_id", "subject_mention_ref", "object_mention_ref"],
    )
    op.create_index(
        "uq_relation_candidate_address",
        "relation_candidate",
        ["tenant_id", "candidate_id"],
        unique=True,
    )


def upgrade() -> None:
    _widen_candidate_references()
    _upgrade_source_temporal_observation()
    _upgrade_relation_signal()
    _upgrade_relation_candidate()


def downgrade() -> None:
    """Refuse. This revision's tables are the record of what was seen and believed.

    015, 016 and 017 reverse their own upgrades, and for all three that is right: they
    reshape storage, so undoing them undoes the reshaping. Neither answer is available
    here.

    Dropping ``source_temporal_observation`` deletes every instant a source stated, and the
    next ingest would write them again under whatever precision convention the code
    happened to hold that day - so a downgrade would not restore the old state, it would
    replace a recorded reading with a recomputed one and leave nothing to show the
    difference. Dropping ``relation_signal`` deletes the observations, which is worse than
    it looks: the ``relation_candidate`` rows would survive with their evidence removed, and
    FR-034's independence count would keep answering from rows that no longer have anything
    to count. Dropping ``relation_candidate`` deletes every reading the platform formed
    about a relation - including, especially, the readings it formed and then refused to
    admit, which are the only record that a hypothesis was considered and rejected (I-3,
    FR-006).

    So a downgrade would be the only operation in the platform able to remove a
    consideration, on the strength of a schema version number. That is worse than having
    no reverse at all. Rolling back is a forward operation: add revision 021 that states
    what the schema becomes instead.
    """
    raise NotImplementedError(
        "020_universal_relation_extraction is forward-only: relation_candidate is the "
        "record of every reading formed about a relation including the ones refused, "
        "relation_signal is the record of the observations those readings rest on and of "
        "FR-034's independence count, and source_temporal_observation is the record of the "
        "instants the sources stated. Dropping any of them deletes a consideration or an "
        "observation rather than reshaping storage. Add a forward revision instead."
    )
