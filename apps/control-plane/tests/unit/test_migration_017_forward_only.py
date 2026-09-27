"""Migration regressions for discovery provenance on the frontier (017).

``frontier_items`` gained exactly one column in revision 017. That is a small
change, and small additive changes are where silent divergence lives: a fresh
install builds the table from ORM metadata while an upgraded install builds it
from this file, and if the two disagree about one column, "both paths reach the
same schema" stops being true (SC-010) -- and it does so quietly, because a
missing provenance column surfaces weeks later as an audit question with no
answer.

These tests pin the properties that make the change safe:

1. Revision ``016_relation_evidence_graph`` is treated as released and is never
   edited. A database that already ran it can only ever reach 017 by applying
   017, so amending 016 leaves every deployed installation permanently short of
   the column. Its content is pinned by digest.
2. The revision graph stays linear: one root, one head, no branching, so
   "upgrade head" stays unambiguous for an operator (SC-010). 016 must also
   remain the *sole* successor of 015 -- adding 017 on top of 016 does not
   re-parent anything.
3. The upgrade is add-column only: no table is created, no index is created, and
   exactly one column is added. Anything else is scope creep, and one specific
   thing is forbidden outright: ``uq_frontier_schedule (tenant_id, uri)`` is the
   dedup key discovery idempotency depends on (FR-006), so rebuilding it under
   concurrent load would take the guarantee away.
4. **Both install paths.** The fresh-create path is ``Base.metadata.create_all``
   (ORM metadata); the upgrade path is this revision's recorded DDL. Rather than
   pinning each side separately and hoping they meet, the test reconstructs the
   upgrade result -- the declarative table as it stood at 016, with 017's own
   recorded column applied to it -- and compares it to what ``create_all`` emits,
   column by column: name, type, nullability, server default and index set. That
   is the property SC-010 actually claims.
5. The provenance column is not indexed, and no existing column changed.

Digest and shape values cover file content and SQLAlchemy metadata only. They are
not a substitute for running both install paths against a live PostgreSQL, which
:func:`test_both_install_paths_reach_one_schema_against_a_live_database` does when
a database is reachable and skips with a stated reason when one is not.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import re
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

APP_DIR = Path(__file__).resolve().parents[2]
VERSIONS_DIR = APP_DIR / "db" / "migrations" / "versions"
MIGRATION_FILE = VERSIONS_DIR / "017_discovery_provenance.py"
RELEASED_016 = VERSIONS_DIR / "016_relation_evidence_graph.py"
RELEASED_015 = VERSIONS_DIR / "015_worldline_reconstruction.py"

# SHA-256 of the released revision file, captured when 016 was released (line
# endings normalized). Adding 017 is expected; editing 016 is not -- an
# already-deployed database would never receive the change. The value was taken
# with the same normalization the 015 pin uses, which is itself verified by
# ``test_migration_016_forward_only.py`` and by
# :func:`test_016_digest_matches_the_pin_in_the_016_regression_suite` below.
RELEASED_016_DIGEST = "6032c29c24db6016bd7e2f590cc328c9d1654b5789207c48fbe4361cc6167552"

# The 015 pin, restated so the 017 suite independently proves its own digest
# method rather than trusting a constant copied from the 016 suite.
RELEASED_015_DIGEST = "377c005fb60192ee09722e98a1da89849bcab2e8e758c8fef0e0d0146ba490fd"

# The single table and column of data-model.md "Migration plan" row 1.
EXPECTED_TABLE = "frontier_items"
EXPECTED_COLUMN = "provenance"

# FR-006 discovery idempotency. This revision must never name it.
SCHEDULE_KEY_INDEX = "uq_frontier_schedule"

# The numbered section banners of ``017.upgrade()``. Their order is the ordering
# contract revisions 015 and 016 established: create tables, add columns,
# backfill, then create indexes.
SECTION_MARKERS = (
    "# 1. New tables",
    "# 2. New columns",
    "# 3. Backfill",
    "# 4. Indexes",
)

# Columns the adapter is forbidden to set, because they are frontier policy
# (ADR-0016/0017). Pinned here because the *schema* is where their absence is
# observable: 017 must not alter them, so a future revision that gives discovery
# a say in scheduling has to say so in the DDL where it can be seen.
FORBIDDEN_COLUMNS = ("state", "retries", "lease_until", "next_schedule_at", "partition")

_REVISION = re.compile(r'^revision\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)
_DOWN_REVISION = re.compile(r'^down_revision\s*=\s*(.+)$', re.MULTILINE)


def _parse(path: Path) -> tuple[str, str | None]:
    text = path.read_text(encoding="utf-8")
    revision = _REVISION.search(text)
    assert revision, f"{path.name} has no revision identifier"
    down_match = _DOWN_REVISION.search(text)
    assert down_match, f"{path.name} has no down_revision"
    raw = down_match.group(1).strip()
    if raw == "None":
        return revision.group(1), None
    quoted = re.match(r'^["\']([^"\']+)["\']$', raw)
    assert quoted, f"{path.name} has an unparseable down_revision: {raw!r}"
    return revision.group(1), quoted.group(1)


def _content_digest(path: Path) -> str:
    """SHA-256 of file content with line endings normalized.

    The repository sets ``core.autocrlf=true``, so the same committed file is
    CRLF in a Windows working tree and LF on CI. Hashing raw bytes would make
    this regression fail spuriously on one platform or the other, so newlines
    are normalized before hashing. Line-ending-only churn is not the edit this
    test exists to catch; a content change is.
    """
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _migration_text() -> str:
    return MIGRATION_FILE.read_text(encoding="utf-8")


def _upgrade_text() -> str:
    """The body of ``upgrade()``.

    Anchored on the function because helper docstrings above it mention the same
    table and column names, and a whole-file search would match those first.
    """
    text = _migration_text()
    return text[text.index("def upgrade()") : text.index("def downgrade()")]


class _OpRecorder:
    """Stand-in for ``alembic.op`` that records the DDL a migration would emit.

    Reading the migration's intent out of the recorded calls -- rather than out
    of its source text -- means a column added with a different formatting
    convention, or in a loop, is still compared against the declarative schema.
    Nothing is executed; this is inspection only.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self.added_columns: list[tuple[str, sa.Column]] = []
        self.dropped_columns: list[tuple[str, str]] = []
        self.created_tables: list[str] = []
        self.created_indexes: list[str] = []
        self.dropped_indexes: list[str] = []

    def create_table(self, name: str, *columns: sa.Column, **kwargs: object) -> None:
        self.calls.append(("create_table", (name,), dict(kwargs)))
        self.created_tables.append(name)

    def add_column(self, table_name: str, column: sa.Column, **kwargs: object) -> None:
        self.calls.append(("add_column", (table_name, column.name), dict(kwargs)))
        self.added_columns.append((table_name, column))

    def create_index(
        self,
        name: str,
        table_name: str,
        columns: list[str],
        unique: bool = False,
        **kwargs: object,
    ) -> None:
        self.calls.append(("create_index", (name,), dict(kwargs)))
        self.created_indexes.append(name)

    def drop_index(self, name: str, table_name: str | None = None, **kwargs: object) -> None:
        self.calls.append(("drop_index", (name, table_name), dict(kwargs)))
        self.dropped_indexes.append(name)

    def drop_table(self, name: str, **kwargs: object) -> None:
        self.calls.append(("drop_table", (name,), dict(kwargs)))

    def drop_column(self, table_name: str, column_name: str, **kwargs: object) -> None:
        self.calls.append(("drop_column", (table_name, column_name), dict(kwargs)))
        self.dropped_columns.append((table_name, column_name))


def _load_migration() -> object:
    spec = importlib.util.spec_from_file_location("migration_017_under_test", MIGRATION_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _recorded(function_name: str) -> _OpRecorder:
    module = _load_migration()
    recorder = _OpRecorder()
    module.op = recorder  # type: ignore[attr-defined]
    getattr(module, function_name)()
    return recorder


def _declarative_metadata() -> sa.MetaData:
    """Return ``Base.metadata`` from the application schema.

    Imported inside the function so it resolves after the ``sys.path`` entry
    above rather than at import time.
    """
    from db.schema import Base

    return Base.metadata


def _type_signature(column: sa.Column) -> tuple[str, object]:
    """Comparable description of a column type, including ``String(n)`` width."""
    type_ = column.type
    if isinstance(type_, sa.String):
        return ("String", type_.length)
    if isinstance(type_, sa.DateTime):
        return ("DateTime", type_.timezone)
    return (type(type_).__name__, None)


def _default_text(column: sa.Column) -> str | None:
    """The server default of a column as SQL, or ``None`` when it has none."""
    if column.server_default is None:
        return None
    arg = column.server_default.arg
    if isinstance(arg, str):
        return f"'{arg}'"
    compiled = sa.schema.CreateColumn(column).compile(dialect=postgresql.dialect())
    match = re.search(r"DEFAULT\s+(\S+)", str(compiled))
    return match.group(1) if match else str(arg)


def _column_shape(column: sa.Column) -> tuple[str, tuple[str, object], bool, str | None]:
    """Everything about a column that a fresh install and an upgrade must agree on."""
    return (
        column.name,
        _type_signature(column),
        bool(column.nullable),
        _default_text(column),
    )


def _index_shape(table: sa.Table) -> dict[str, tuple[tuple[str, ...], bool]]:
    return {
        index.name: (tuple(col.name for col in index.columns), bool(index.unique))
        for index in sorted(_indexes_of(table).values(), key=lambda i: i.name)
    }


def _copy_column(column: sa.Column) -> sa.Column:
    """A standalone copy of ``column``.

    ``Column.copy()`` is deprecated, and the attributes worth carrying are
    exactly the ones the two-path comparison reads: type, nullability and
    server default. Copying them explicitly also means a new mapped attribute
    cannot silently travel into the reconstructed "before" table and make the
    comparison vacuous.
    """
    return sa.Column(
        column.name,
        column.type,
        nullable=column.nullable,
        server_default=column.server_default,
        primary_key=column.primary_key,
    )


def _indexes_of(table: sa.Table) -> dict[str, sa.Index]:
    """Index name -> index. ``Table.indexes`` is an unordered set in SA 2.0."""
    return {index.name: index for index in table.indexes}


def _table_at_016() -> sa.Table:
    """``frontier_items`` as revision 016 left it: the pre-017 column set.

    Built by cloning the declarative table -- columns *and* indexes -- and
    removing the one column 017 adds. Deriving the "before" state this way,
    rather than hard-coding fifteen column names, means the comparison below
    cannot pass by both sides drifting together: the "after" side is the table as
    declared *now*, and the "before" side is that same table minus exactly the
    column under test. The indexes are carried over because the live test below
    creates this table and then compares index sets across the two install paths.
    """
    metadata = _declarative_metadata()
    source = metadata.tables[EXPECTED_TABLE]
    for index in _indexes_of(source).values():
        assert EXPECTED_COLUMN not in [col.name for col in index.columns], (
            f"{EXPECTED_COLUMN} is indexed by {index.name}; the unindexed claim is "
            "checked directly instead, and the 'before' state stays reconstructable"
        )
    clone = sa.Table(
        EXPECTED_TABLE,
        sa.MetaData(),
        *[_copy_column(col) for name, col in source.columns.items() if name != EXPECTED_COLUMN],
    )
    for index in _indexes_of(source).values():
        sa.Index(
            index.name,
            *[clone.c[col.name] for col in index.columns],
            unique=bool(index.unique),
        )
    return clone


# ---------------------------------------------------------------------------
# 1. Released revisions stay immutable; the graph stays linear
# ---------------------------------------------------------------------------


def test_016_digest_matches_the_pin_in_the_016_regression_suite() -> None:
    """Cross-check this suite's digest method against the one 016 already uses.

    ``test_migration_016_forward_only.py`` pins 015 by digest. If the
    normalization here were different, this suite could pin 016 with a value
    that has nothing to do with the 016 suite's notion of content, and the two
    immutability guarantees would disagree about the same bytes. Recomputing 015
    with this file's method and comparing it to the 016 suite's constant makes
    the disagreement impossible to miss.
    """
    sixteen_suite = (Path(__file__).parent / "test_migration_016_forward_only.py").read_text(
        encoding="utf-8"
    )
    assert f'"{RELEASED_015_DIGEST}"' in sixteen_suite, (
        "the 016 regression suite's 015 pin no longer matches the constant restated "
        "here; the two suites' digest methods have diverged"
    )
    assert _content_digest(RELEASED_015) == RELEASED_015_DIGEST


def test_released_revision_016_is_not_edited() -> None:
    """Revision 016 must stay byte-identical to its released state (FR-042)."""
    assert RELEASED_016.exists(), "released revision missing: 016_relation_evidence_graph.py"
    actual = _content_digest(RELEASED_016)
    assert actual == RELEASED_016_DIGEST, (
        f"016_relation_evidence_graph.py was modified after release "
        f"(expected {RELEASED_016_DIGEST}, got {actual}). Released migrations are "
        f"immutable: add a new forward-only revision instead."
    )


def test_revision_graph_is_linear_and_has_a_single_head() -> None:
    """Exactly one root and one head; no branching (SC-010)."""
    graph: dict[str, str | None] = {}
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        revision, down = _parse(path)
        assert revision not in graph, f"duplicate revision id: {revision}"
        graph[revision] = down

    roots = [rev for rev, down in graph.items() if down is None]
    assert len(roots) == 1, f"expected exactly one root revision, got {roots}"

    children: dict[str, list[str]] = {}
    for rev, down in graph.items():
        if down is not None:
            assert down in graph, f"{rev} points at unknown parent {down}"
            children.setdefault(down, []).append(rev)
    for parent, kids in children.items():
        assert len(kids) == 1, f"revision {parent} has multiple children: {kids}"

    heads = [rev for rev in graph if rev not in children]
    assert len(heads) == 1, f"expected exactly one head revision, got {heads}"
    # 018 (semantic fabric) now sits on top of 017. The invariant under test is
    # "exactly one unambiguous head", not "017 is it" -- pinning the revision id
    # would make every later migration fail this suite for being added at all.
    assert heads == ["018_semantic_fabric"], (
        f"018 must be the head so `alembic upgrade head` reaches the latest schema, got {heads}"
    )
    # 017 must still be reachable, and still immediately before the head.
    assert "017_discovery_provenance" in graph, "017 is no longer in the revision graph"
    assert children["017_discovery_provenance"] == ["018_semantic_fabric"]


def test_discovery_provenance_follows_relation_evidence_graph() -> None:
    """017 must be a child of 016, not a replacement or a sibling root."""
    revision, down = _parse(MIGRATION_FILE)
    assert revision == "017_discovery_provenance"
    assert down == "016_relation_evidence_graph"


def test_016_remains_the_sole_successor_of_015() -> None:
    """Adding 017 on top of 016 must not re-parent 015.

    ``test_migration_016_forward_only.py`` asserts 016 is the only child of 015.
    017's ``down_revision`` is 016, so that stays true -- but only if this suite
    checks it from the other direction, because a future 018 that pointed
    straight at 015 would fork the graph without either suite noticing.
    """
    successors = [
        path.name
        for path in sorted(VERSIONS_DIR.glob("*.py"))
        if path.name not in {"__init__.py", RELEASED_015.name} and _parse(path)[1] == "015_worldline_reconstruction"
    ]
    assert successors == [RELEASED_016.name], (
        f"expected 016 to be the sole successor of 015, got {successors}"
    )


# ---------------------------------------------------------------------------
# 2. The upgrade is add-column only, in the established order
# ---------------------------------------------------------------------------


def test_upgrade_adds_exactly_one_column_and_nothing_else() -> None:
    """One ``add_column``; no table, no index, no drop (FR-017)."""
    recorder = _recorded("upgrade")
    assert [(table, column.name) for table, column in recorder.added_columns] == [
        (EXPECTED_TABLE, EXPECTED_COLUMN)
    ]
    assert recorder.created_tables == [], (
        f"017 creates no table; a provenance side-table would be a second place "
        f"discovery state lives, got {recorder.created_tables}"
    )
    assert recorder.created_indexes == [], (
        f"017 creates no index; provenance is read for audit, never queried, got "
        f"{recorder.created_indexes}"
    )
    assert [name for name, _, _ in recorder.calls if name == "drop_table"] == []
    assert [name for name, _, _ in recorder.calls if name == "drop_index"] == []
    assert [name for name, _, _ in recorder.calls if name == "drop_column"] == []


def test_upgrade_never_names_the_schedule_key_index() -> None:
    """``uq_frontier_schedule`` is FR-006 idempotency and must not be rebuilt.

    Dropping and re-creating this index removes uniqueness for the duration of
    the rebuild, which is precisely the window in which a concurrent discovery
    pass would insert a second row for the same canonical URL. The check is on
    the whole file, not just the ``add_column`` call, so a
    ``create_index``/``drop_index`` pair anywhere in the revision fails here.
    """
    text = _migration_text()
    assert f'op.drop_index("{SCHEDULE_KEY_INDEX}"' not in text
    assert f'op.create_index("{SCHEDULE_KEY_INDEX}"' not in text
    recorder = _recorded("upgrade")
    assert SCHEDULE_KEY_INDEX not in recorder.created_indexes
    assert SCHEDULE_KEY_INDEX not in recorder.dropped_indexes
    assert SCHEDULE_KEY_INDEX not in recorder.dropped_columns


def test_upgrade_sections_are_in_the_established_order() -> None:
    """Tables, columns, backfill, indexes -- sections 1/3/4 are recorded no-ops.

    A section that is merely absent is indistinguishable from one that was
    forgotten. The ordering contract only means something if "there is nothing to
    do here" is written down, and if the column add sits between section 1 and
    the index section it would stay true if 017 ever grew an index.
    """
    upgrade = _upgrade_text()
    positions = []
    for marker in SECTION_MARKERS:
        assert marker in upgrade, f"017.upgrade() is missing section {marker!r}"
        positions.append(upgrade.index(marker))
    assert positions == sorted(positions), f"017.upgrade() sections out of order: {SECTION_MARKERS}"

    add_column = upgrade.index("op.add_column")
    assert positions[0] < add_column < positions[2], (
        "the column must be added after the tables section and before the backfill "
        "section, so a future index in section 4 can never precede its column"
    )
    for helper in ("_no_new_tables()", "_no_backfill()", "_no_new_indexes()"):
        assert helper in upgrade, f"{helper} is not called; a recorded no-op must be called"
    assert (
        upgrade.index("_no_backfill()") < upgrade.index("_no_new_indexes()")
    ), "the backfill section must precede the index section"


def test_downgrade_drops_exactly_the_column_upgrade_added() -> None:
    """The reverse of ``upgrade``, and nothing else (data-model migration plan)."""
    upgraded = _recorded("upgrade")
    recorder = _recorded("downgrade")
    assert recorder.dropped_columns == [(table, column.name) for table, column in upgraded.added_columns]
    assert [name for name, _, _ in recorder.calls if name == "drop_table"] == []
    assert [name for name, _, _ in recorder.calls if name == "drop_index"] == []
    assert [name for name, _, _ in recorder.calls if name == "add_column"] == []


# ---------------------------------------------------------------------------
# 3. Both install paths reach the same schema
# ---------------------------------------------------------------------------


def test_upgrade_column_matches_the_declarative_column() -> None:
    """Type, nullability and server default agree between migration and schema.

    A default that differs between the two paths is the sharpest version of this
    bug: pre-017 rows written by the migration get ``'{}'`` while pre-017 rows in
    a fresh install get something else, and no column-set comparison catches it.
    """
    recorded = _recorded("upgrade").added_columns
    assert len(recorded) == 1
    _, migrated = recorded[0]
    declared = _declarative_metadata().tables[EXPECTED_TABLE].columns[EXPECTED_COLUMN]
    assert _column_shape(migrated) == _column_shape(declared), (
        f"{EXPECTED_TABLE}.{EXPECTED_COLUMN} differs between migration 017 and "
        f"db/schema.py: migration {_column_shape(migrated)}, schema {_column_shape(declared)}"
    )


def test_both_install_paths_reach_one_schema() -> None:
    """Upgrade-from-head and fresh-create produce the same table (SC-010).

    The upgrade result is reconstructed by applying 017's *own recorded column*
    to the pre-017 column set, and then compared, column for column and index for
    index, against what ``Base.metadata.create_all`` would emit. This is the
    property SC-010 claims; asserting each side separately would only prove both
    sides are internally consistent.
    """
    before = _table_at_016()
    after = _declarative_metadata().tables[EXPECTED_TABLE]
    _, added = _recorded("upgrade").added_columns[0]

    upgraded_meta = sa.MetaData()
    upgraded_table = before.to_metadata(upgraded_meta)
    upgraded_table.append_column(_copy_column(added))

    fresh_shapes = [_column_shape(col) for col in after.columns]
    upgraded_shapes = [_column_shape(col) for col in upgraded_table.columns]
    assert upgraded_shapes == fresh_shapes, (
        f"{EXPECTED_TABLE} column drift between the upgrade path and the fresh-create "
        f"path: only in upgrade "
        f"{sorted(set(upgraded_shapes) - set(fresh_shapes))}, "
        f"only in create_all {sorted(set(fresh_shapes) - set(upgraded_shapes))}"
    )
    assert _index_shape(upgraded_table) == _index_shape(after), (
        "the upgrade path must leave the index set of the table exactly as the "
        "fresh-create path declares it"
    )


def test_both_install_paths_agree_on_physical_column_order() -> None:
    """Not just the column *set*: the physical order must match too.

    ``ALTER TABLE ... ADD COLUMN`` always appends at the end of the table, so an
    add-column revision makes the two install paths differ in physical order
    unless the ORM declares the new attribute last. Nothing in the application
    can observe the difference -- every statement in this codebase names its
    columns -- but a physical dump, a ``SELECT *`` in a psql session and a
    column-order-sensitive tool all can, and a schema that differs between a
    fresh and an upgraded install is a schema whose difference has to be
    explained for as long as the migration exists.

    The pin is that ``provenance`` is the last mapped attribute, so ``create_all``
    appends it in the same position ``ADD COLUMN`` does.
    """
    after = _declarative_metadata().tables[EXPECTED_TABLE]
    # `.keys()`, because iterating a ColumnCollection yields Column objects, not
    # names. Bound to a list once so the order assertions below read as a
    # statement about column order rather than about SQLAlchemy's API.
    declared = list(after.columns.keys())
    assert declared[-1] == EXPECTED_COLUMN, (
        f"{EXPECTED_TABLE}: {EXPECTED_COLUMN} must be declared last so create_all "
        f"places it where ADD COLUMN does; got {declared}"
    )
    upgraded_names = [name for name in declared if name != EXPECTED_COLUMN]
    upgraded_names.append(EXPECTED_COLUMN)
    assert declared == upgraded_names


def test_upgrade_leaves_every_existing_column_untouched() -> None:
    """The 15 pre-existing columns keep their name, type, nullability and default.

    The upgrade path is a clone of the pre-017 table plus one column, so a
    mutation of an existing column could only come from the clone itself. This
    test therefore compares the *migration's own view* of the table -- the
    columns it must not mention -- against the declared ones, and fails if 017
    ever starts touching scheduling state (ADR-0016/0017).
    """
    text = _migration_text()
    for column in FORBIDDEN_COLUMNS:
        assert f'sa.Column("{column}"' not in text, (
            f"017 must not redefine {EXPECTED_TABLE}.{column}: scheduling policy is "
            "the frontier's (ADR-0016/0017), not a migration's"
        )
    before = _table_at_016()
    declared = _declarative_metadata().tables[EXPECTED_TABLE]
    for name in [column.name for column in before.columns]:
        assert _column_shape(before.columns[name]) == _column_shape(declared.columns[name]), (
            f"{EXPECTED_TABLE}.{name} changed shape; 017 is add-column only"
        )


def test_provenance_column_is_not_indexed() -> None:
    """Read for audit, never queried -- so no index (ADR-0026, T039).

    A GIN index over a document that grows with every coalesced ``seen_by[]``
    entry would cost write amplification on the hottest table in the system for
    a query nobody runs. The check runs on the declared table, which is the side
    an operator actually gets, and on the migration, so both paths agree.
    """
    table = _declarative_metadata().tables[EXPECTED_TABLE]
    for index in _indexes_of(table).values():
        assert EXPECTED_COLUMN not in [col.name for col in index.columns], (
            f"{index.name} indexes {EXPECTED_COLUMN}; provenance must stay unindexed"
        )
    assert f'"{EXPECTED_COLUMN}"' not in _upgrade_text()


def test_schedule_key_index_is_still_unique_on_tenant_and_uri() -> None:
    """FR-006 idempotency survives the schema change intact."""
    table = _declarative_metadata().tables[EXPECTED_TABLE]
    index = _indexes_of(table)[SCHEDULE_KEY_INDEX]
    assert index.unique is True
    assert tuple(col.name for col in index.columns) == ("tenant_id", "uri")


# ---------------------------------------------------------------------------
# 4. The same claim, against a live PostgreSQL
# ---------------------------------------------------------------------------


def _postgres_dsn() -> str:
    """The application's DSN, resolved the same way the application resolves it."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "shared"))
    from config.settings import get_settings

    return get_settings().postgres.dsn


def _skip_without_postgres() -> str:
    """Return a skip reason unless a PostgreSQL server answers the configured DSN.

    Every assertion above is metadata- and source-level and runs anywhere. This
    guard exists only so the live-database proof skips *loudly* on a machine
    without Postgres instead of erroring, because an ERROR reads as a broken
    suite and a skip reads as an absent proof, and those are different facts.
    """
    from sqlalchemy.exc import DBAPIError, SQLAlchemyError
    from sqlalchemy.ext.asyncio import create_async_engine

    dsn = _postgres_dsn()
    if not dsn:
        return "no Postgres DSN is configured"

    async def _probe() -> str | None:
        engine = create_async_engine(dsn)
        try:
            async with engine.connect() as connection:
                await connection.exec_driver_sql("SELECT 1")
            return None
        except (DBAPIError, SQLAlchemyError, OSError, ValueError) as exc:
            return (
                f"PostgreSQL is not reachable at the configured DSN "
                f"({dsn.rsplit('@', 1)[-1]}): {type(exc).__name__}"
            )
        finally:
            await engine.dispose()

    try:
        return asyncio.run(_probe()) or ""
    except (SQLAlchemyError, OSError, ValueError) as exc:
        return f"PostgreSQL probe failed: {type(exc).__name__}: {exc}"


@pytest.mark.integration
def test_both_install_paths_reach_one_schema_against_a_live_database() -> None:
    """Compare the real table Postgres builds on each path, column by column.

    The metadata-level comparison above is the load-bearing regression; this is
    the check the 016 suite's docstring says no digest can replace -- what the
    server actually stores. Each path gets its own throwaway schema, so the test
    never touches the application's real tables.
    """
    reason = _skip_without_postgres()
    if reason:
        pytest.skip(f"{reason} -- live install-path comparison not exercised")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    dsn = _postgres_dsn()
    _, added = _recorded("upgrade").added_columns[0]
    table = _declarative_metadata().tables[EXPECTED_TABLE]

    column_sql = text(
        "SELECT column_name, is_nullable, data_type, column_default "
        "FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = :t "
        "ORDER BY column_name"
    )
    index_sql = text(
        "SELECT indexname FROM pg_indexes "
        "WHERE schemaname = current_schema() AND tablename = :t ORDER BY indexname"
    )

    async def _run() -> tuple[list, list, list, list, tuple[list, list]]:
        fresh_engine = create_async_engine(dsn)
        upgrade_engine = create_async_engine(dsn)
        try:
            async with (
                fresh_engine.connect() as fresh,
                upgrade_engine.connect() as upgrade,
            ):
                for connection, name in ((fresh, "cp017_fresh"), (upgrade, "cp017_upgrade")):
                    await connection.execute(text(f"DROP SCHEMA IF EXISTS {name} CASCADE"))
                    await connection.execute(text(f"CREATE SCHEMA {name}"))
                    await connection.commit()

                # Path 1 -- fresh create, straight from ORM metadata.
                await fresh.execute(text("SET search_path TO cp017_fresh"))
                await fresh.run_sync(
                    lambda sync: table.create(sync, checkfirst=False)
                )
                await fresh.commit()

                # Path 2 -- upgrade. Build the table exactly as revision 016 left
                # it, then apply 017's own recorded column definition to it.
                #
                # The default is taken from the same compiler the offline
                # comparison trusts rather than interpolated by hand: the
                # migration's `server_default` is `sa.text("'{}'")`, so wrapping
                # `str(arg)` in another pair of quotes would emit
                # `DEFAULT ''{}''` -- double-quoted, and a syntax error or a
                # different default depending on the server's parser.
                before = _table_at_016()
                default_sql = _default_text(added)
                assert default_sql is not None, "017 declares a server default"
                await upgrade.execute(text("SET search_path TO cp017_upgrade"))
                await upgrade.run_sync(lambda sync: before.create(sync, checkfirst=False))
                await upgrade.commit()
                await upgrade.execute(
                    text(
                        f"ALTER TABLE {EXPECTED_TABLE} ADD COLUMN {EXPECTED_COLUMN} "
                        f"JSONB NOT NULL DEFAULT {default_sql}"
                    )
                )
                await upgrade.commit()

                fresh_columns = [
                    tuple(row) for row in (await fresh.execute(column_sql, {"t": EXPECTED_TABLE})).all()
                ]
                upgrade_columns = [
                    tuple(row) for row in (await upgrade.execute(column_sql, {"t": EXPECTED_TABLE})).all()
                ]
                fresh_order = [
                    row[0]
                    for row in (
                        await fresh.execute(
                            text(
                                "SELECT column_name FROM information_schema.columns "
                                "WHERE table_schema = current_schema() AND table_name = :t "
                                "ORDER BY ordinal_position"
                            ),
                            {"t": EXPECTED_TABLE},
                        )
                    ).all()
                ]
                upgrade_order = [
                    row[0]
                    for row in (
                        await upgrade.execute(
                            text(
                                "SELECT column_name FROM information_schema.columns "
                                "WHERE table_schema = current_schema() AND table_name = :t "
                                "ORDER BY ordinal_position"
                            ),
                            {"t": EXPECTED_TABLE},
                        )
                    ).all()
                ]
                fresh_indexes = [row[0] for row in (await fresh.execute(index_sql, {"t": EXPECTED_TABLE})).all()]
                upgrade_indexes = [
                    row[0] for row in (await upgrade.execute(index_sql, {"t": EXPECTED_TABLE})).all()
                ]

                for connection, name in ((fresh, "cp017_fresh"), (upgrade, "cp017_upgrade")):
                    await connection.execute(text(f"DROP SCHEMA IF EXISTS {name} CASCADE"))
                    await connection.commit()
                return fresh_columns, upgrade_columns, fresh_indexes, upgrade_indexes, (
                    fresh_order,
                    upgrade_order,
                )
        finally:
            await fresh_engine.dispose()
            await upgrade_engine.dispose()

    fresh_columns, upgrade_columns, fresh_indexes, upgrade_indexes, orders = asyncio.run(_run())
    assert upgrade_columns == fresh_columns, (
        "live install-path divergence on frontier_items: "
        f"upgrade {upgrade_columns} != create_all {fresh_columns}"
    )
    assert orders[1] == orders[0], (
        f"live physical column order divergence: upgrade {orders[1]} != create_all {orders[0]}"
    )
    assert upgrade_indexes == fresh_indexes, (
        f"live index-set divergence: upgrade {upgrade_indexes} != create_all {fresh_indexes}"
    )
    assert SCHEDULE_KEY_INDEX in fresh_indexes, (
        f"the unique schedule key {SCHEDULE_KEY_INDEX} must exist on a live install; "
        f"got {fresh_indexes}"
    )
    assert EXPECTED_COLUMN not in fresh_indexes, (
        f"provenance must stay unindexed against a live database too, got {fresh_indexes}"
    )


def test_017_is_reachable_from_the_migration_directory() -> None:
    """Alembic must be able to *find* the revision, not merely have it on disk.

    A version file that no ``script_location`` covers is invisible to
    ``alembic upgrade head``: the file exists, the test above passes, and the
    column is never created in any deployment. ``ScriptDirectory`` is the object
    Alembic itself walks, so resolving the head through it is the same lookup an
    operator's ``alembic upgrade head`` performs -- and, unlike invoking the
    CLI, it needs no database.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    migrations_dir = APP_DIR / "db" / "migrations"
    assert (migrations_dir / "env.py").exists(), "migration environment missing"
    config = Config(str(APP_DIR / "alembic.ini"))
    # Set after loading: the ini's own `script_location` is a path relative to
    # the process CWD, and pytest runs from the workspace root, not from
    # apps/control-plane, so the ini value would not resolve.
    config.set_main_option("script_location", str(migrations_dir))
    script = ScriptDirectory.from_config(config)
    assert script.get_current_head() == "018_semantic_fabric", (
        f"alembic resolves the head as {script.get_current_head()}, so `alembic upgrade "
        "head` would stop before the semantic fabric tables are applied"
    )
    # walk_revisions() yields head-first, so this is the chain an operator walks
    # backwards from head to base -- the same one `alembic history` prints.
    assert [rev.revision for rev in script.walk_revisions()] == [
        "018_semantic_fabric",
        "017_discovery_provenance",
        "016_relation_evidence_graph",
        "015_worldline_reconstruction",
        "014_temporal_materialization",
    ]
