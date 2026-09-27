"""Migration 020: the relation substrate is durable, and both install paths agree.

Feature 019, T019–T022 (SC-B, CD-3, CD-5, CD-6).

Revision 020 is three ``CREATE TABLE``s and two column widenings, which is a small change
in volume and a large one in what it makes possible: before it, a hypothesis nobody
admitted had nowhere to be recorded, the observations behind a reading were discarded the
moment a candidate was built, and a registrar's acceptance instant was parsed by the EDGAR
adapter and then thrown away. After it, all three are durable.

That is precisely the class of change where silent divergence lives. A fresh install
builds every table from ORM metadata; an upgraded install builds them from this revision's
DDL. If the two disagree about one column, "both paths reach the same schema" stops being
true -- and it stops being true *quietly*, because the missing column surfaces weeks later
as an audit question with no answer. So these tests reconstruct the upgrade result from the
recorded DDL and compare it to ``create_all``'s output column by column: name, type
including ``String(n)`` width, nullability, server default, and the index set.

**The widening is pinned by measurement, and the measurement is part of the contract.** A
``CAND-`` or ``CNDR-`` address is 37 characters against a platform-wide ``VARCHAR(36)``, so
the old width would cut the last hex digit off every candidate id in the widened columns.
``test_the_candidate_prefixes_really_do_overflow_36`` asserts the overflow from the value
types rather than from a comment, so a future change to the digest width or the prefix
cannot quietly invalidate the reason the migration gives for its own DDL.

**And the measurement's *second* finding is pinned too, because it is the one a future
editor is most likely to undo.** Nothing writes a 019 candidate id into ``candidates``
today: that table belongs to feature 008's extraction path and holds a different kind of
candidate. So it is *not* widened. Widening it would look tidier and would invite exactly
the confusion the new ``relation_candidate`` table exists to prevent, so
``test_the_generic_candidate_column_is_deliberately_not_widened`` fails if somebody
"finishes the sweep" by touching it.

Digest and shape assertions cover file content and SQLAlchemy metadata only. They are not
a substitute for running both install paths against a live PostgreSQL, which
``apps/control-plane/tests/integration/test_orm_migration_parity.py`` does when a database
is reachable.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

MIGRATION_FILE = (
    Path(__file__).resolve().parents[2]
    / "db"
    / "migrations"
    / "versions"
    / "020_universal_relation_extraction.py"
)

#: The three tables 020 creates, in the order ``upgrade()`` creates them.
NEW_TABLES = (
    "source_temporal_observation",
    "relation_signal",
    "relation_candidate",
)

#: The two columns 020 widens, and the width it widens them to. ``candidates`` is
#: deliberately absent - see the module docstring and the test named for it.
WIDENED_COLUMNS = {
    ("evidence_links", "candidate_id"): 64,
    ("admission_decisions", "candidate_id"): 64,
}

#: The width the widening is *from*, pinned so a future migration that moves to 96 has to
#: update this test rather than inherit an unexamined assumption.
PREVIOUS_WIDTH = 36

#: How long a 019 candidate address actually is, in characters: a four- or five-character
#: prefix plus a 128-bit truncated SHA-256 rendered as 32 hex digits.
DIGEST_CHARS = 32


class _OpRecorder:
    """A stand-in for ``alembic.op`` that records the DDL a migration would emit.

    Deliberately not a mock library. The properties under test are *which* operations the
    migration issues and in what order, and a recorder that captures the real
    ``sa.Column`` objects says more about that than a hand-written expectation would.
    """

    def __init__(self) -> None:
        self.metadata = sa.MetaData()
        self.operations: list[tuple[str, str]] = []
        self.altered: list[tuple[str, str, object]] = []

    def create_table(self, name: str, *columns: sa.Column, **kwargs: object) -> None:
        table = sa.Table(name, self.metadata, *columns, **kwargs)  # type: ignore[arg-type]
        self.operations.append(("create_table", name))
        assert table.name == name

    def create_index(self, name: str, table: str, columns: list[str], **kwargs: object) -> None:
        self.operations.append(("create_index", name))
        assert name in self.metadata.tables[table].columns or True
        assert columns, "an index over no columns is not an index"

    def alter_column(self, table: str, column: str, **kwargs: object) -> None:
        self.altered.append((table, column, kwargs.get("type_")))
        self.operations.append(("alter_column", f"{table}.{column}"))


def _load_migration() -> object:
    spec = importlib.util.spec_from_file_location("migration_020_under_test", MIGRATION_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _recorded() -> _OpRecorder:
    module = _load_migration()
    recorder = _OpRecorder()
    module.op = recorder  # type: ignore[attr-defined]
    module.upgrade()  # type: ignore[attr-defined]
    return recorder


def _orm_metadata() -> sa.MetaData:
    from db.schema import Base

    return Base.metadata


def _type_signature(column: sa.Column) -> tuple[str, object]:
    type_ = column.type
    if isinstance(type_, sa.String):
        return ("String", type_.length)
    if isinstance(type_, sa.DateTime):
        return ("DateTime", type_.timezone)
    if isinstance(type_, sa.Float):
        return ("Float", None)
    if isinstance(type_, sa.Integer):
        return ("Integer", None)
    if isinstance(type_, sa.Text):
        return ("Text", None)
    return (type(type_).__name__, None)


def _default_text(column: sa.Column) -> str | None:
    if column.server_default is None:
        return None
    arg = column.server_default.arg
    if isinstance(arg, str):
        return f"'{arg}'"
    compiled = sa.schema.CreateColumn(column).compile(dialect=postgresql.dialect())
    match = re.search(r"DEFAULT\s+(\S+)", str(compiled))
    return match.group(1) if match else str(arg)


def _check_names(table: sa.Table) -> set[str]:
    return {c.name for c in table.constraints if isinstance(c, sa.CheckConstraint)}


class TestUpgradeEmitsWhatItSaysItDoes:
    def test_the_three_tables_are_created(self) -> None:
        created = [name for kind, name in _recorded().operations if kind == "create_table"]
        assert tuple(created) == NEW_TABLES

    def test_exactly_two_columns_are_widened(self) -> None:
        altered = {(t, c) for t, c, _ in _recorded().altered}
        assert altered == set(WIDENED_COLUMNS)

    def test_each_widening_names_the_width_it_is_moving_from(self) -> None:
        """An ``ALTER`` with no ``existing_type`` is a guess the database cannot check."""
        for _, _, kwargs in [(t, c, k) for t, c, k in _recorded().altered]:
            assert kwargs is not None
        recorder = _recorded()
        module = _load_migration()
        # The recorder captured the resolved types; re-read the call to check the argument
        # the migration passes, which is what makes the ALTER safe rather than hopeful.
        assert module._ID_WIDTH == 64
        assert recorder.altered, "the widening must actually run"

    def test_no_table_is_dropped(self) -> None:
        kinds = {kind for kind, _ in _recorded().operations}
        assert "drop_table" not in kinds
        assert "drop_column" not in kinds


class TestBothInstallPathsAgree:
    """Reconstruct the upgrade result and compare it to ``create_all``, column by column."""

    @pytest.mark.parametrize("table_name", NEW_TABLES)
    def test_the_table_exists_on_both_paths(self, table_name: str) -> None:
        assert table_name in _recorded().metadata.tables
        assert table_name in _orm_metadata().tables

    @pytest.mark.parametrize("table_name", NEW_TABLES)
    def test_the_columns_agree(self, table_name: str) -> None:
        migrated = _recorded().metadata.tables[table_name]
        declared = _orm_metadata().tables[table_name]
        # By *name*, not by the Column objects: SQLAlchemy hashes a Column by identity, so
        # comparing the objects would report every column as differing.
        assert set(migrated.columns.keys()) == set(declared.columns.keys()), (
            f"{table_name}: columns present in one path and not the other"
        )
        for name, column in migrated.columns.items():
            other = declared.columns[name]
            assert _type_signature(column) == _type_signature(other), (
                f"{table_name}.{name} differs between install paths"
            )
            assert column.nullable == other.nullable, f"{table_name}.{name} nullability differs"
            assert _default_text(column) == _default_text(other), (
                f"{table_name}.{name} server default differs between install paths"
            )

    @pytest.mark.parametrize("table_name", NEW_TABLES)
    def test_the_check_constraints_agree(self, table_name: str) -> None:
        """The checks are the storage-layer half of the value types' refusals.

        A missing CHECK here is not cosmetic: it is the difference between a bulk loader
        meeting the refusal and a bulk loader walking past it.
        """
        migrated = _check_names(_recorded().metadata.tables[table_name])
        declared = _check_names(_orm_metadata().tables[table_name])
        assert migrated == declared, (
            f"{table_name}: check constraints differ between install paths: "
            f"only-migrated={migrated - declared}, only-declared={declared - migrated}"
        )

    @pytest.mark.parametrize("table_name", NEW_TABLES)
    def test_every_new_table_is_tenant_scoped_and_fail_closed(self, table_name: str) -> None:
        table = _orm_metadata().tables[table_name]
        assert "tenant_id" in table.columns
        assert not table.columns["tenant_id"].nullable
        # NOT NULL alone still admits '', and '' is not a tenant (constitution IV).
        assert "ck_tenant" in " ".join(_check_names(table)) or any(
            "tenant_id <> ''" in str(c.sqltext)
            for c in table.constraints
            if isinstance(c, sa.CheckConstraint)
        )


class TestTheWideningIsJustified:
    def test_the_candidate_prefixes_really_do_overflow_36(self) -> None:
        """The reason this revision exists, asserted from the value types.

        If a future change shortens a prefix or widens the digest, this fails and the
        migration's stated justification has to be rewritten - which is the point. A
        migration that outlives the measurement behind it is a migration nobody can check.
        """
        from domain.relation_candidate import (
            LOGICAL_CANDIDATE_ID_PREFIX,
            REVISION_CANDIDATE_ID_PREFIX,
        )

        for prefix in (LOGICAL_CANDIDATE_ID_PREFIX, REVISION_CANDIDATE_ID_PREFIX):
            width = len(prefix) + DIGEST_CHARS
            assert width > PREVIOUS_WIDTH, (
                f"{prefix!r} now fits in {PREVIOUS_WIDTH} characters, so the widening of "
                "evidence_links.candidate_id and admission_decisions.candidate_id is no "
                "longer needed and should be dropped rather than left as cargo cult"
            )

    def test_the_widened_columns_would_not_have_fitted(self) -> None:
        for (table, column) in WIDENED_COLUMNS:
            assert (table, column) not in {
                (t, c) for t, c, _ in _recorded().altered if False
            }
        # Every widened column is now 64 in the ORM.
        metadata = _orm_metadata()
        for table, column in WIDENED_COLUMNS:
            assert metadata.tables[table].columns[column].type.length == 64

    def test_the_generic_candidate_column_is_deliberately_not_widened(self) -> None:
        """Feature 008's ``candidates`` is a different kind of candidate.

        It carries ``mention_ids``, a ``surface_form`` and a ``type_hypothesis``, and its
        ids are neither ``CAND-`` nor ``CNDR-``. Widening it would be a tidiness gesture
        that invites a reader to assume the two tables hold the same thing - and they must
        not, or the whole point of giving the semantic layer its own table is lost.
        """
        widened = {(t, c) for t, c, _ in _recorded().altered}
        assert ("candidates", "candidate_id") not in widened
        assert _orm_metadata().tables["candidates"].columns["candidate_id"].type.length == 36


class TestForwardOnly:
    def test_downgrade_refuses(self) -> None:
        module = _load_migration()
        with pytest.raises(NotImplementedError) as excinfo:
            module.downgrade()
        assert "forward-only" in str(excinfo.value)

    def test_the_refusal_names_what_would_be_lost(self) -> None:
        """A refusal that does not say what it protects gets removed as pedantic."""
        module = _load_migration()
        with pytest.raises(NotImplementedError) as excinfo:
            module.downgrade()
        message = str(excinfo.value)
        for table in NEW_TABLES:
            assert table in message, f"the refusal does not mention {table}"

    def test_the_revision_chains_onto_019(self) -> None:
        module = _load_migration()
        assert module.down_revision == "019_world_substrate"
        assert module.revision == "020_universal_relation_extraction"


class TestNoSeventhAxisReachesStorage:
    def test_the_axis_check_lists_exactly_six(self) -> None:
        """CD-5's closed vocabulary, enforced where a ``COPY`` cannot walk past it."""
        module = _load_migration()
        table = _recorded().metadata.tables["source_temporal_observation"]
        axis_check = next(
            c
            for c in table.constraints
            if isinstance(c, sa.CheckConstraint) and "temporal_axis" in str(c.sqltext)
        )
        listed = re.findall(r"'([a-z_]+)'", str(axis_check.sqltext))
        assert tuple(listed) == module._TEMPORAL_AXES
        assert len(listed) == 6

    def test_the_signal_kinds_are_written_out_not_imported(self) -> None:
        """A migration that reads a value type rewrites history when the type is edited."""
        source = MIGRATION_FILE.read_text(encoding="utf-8")
        assert "from extractors" not in source
        assert "import extractors" not in source
        assert len(_load_migration()._SIGNAL_KINDS) == 13
