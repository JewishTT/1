"""Migration-graph and shape regressions for relation evidence fabric (016).

The relation fabric is the first schema in this repository that is added purely
additively, and its tables are load-bearing for evidence: a claim row that cannot
be traced to a context, a context that can be duplicated, or a schema created by
Alembic but absent from ``create_all`` all break the trace from relation back to
source (I-2, I-3, FR-042). These tests pin the properties that make that safe:

1. Revision ``015_worldline_reconstruction`` is treated as released and is never
   edited. A deployed database has already run it, so a later edit would leave
   existing installations permanently short of the relation schema -- the exact
   failure that made revision 014 unusable. Its content is pinned by digest.
2. The revision graph stays linear: one root, one head, no branching, so
   "upgrade head" is unambiguous for an operator (SC-010).
3. ``016`` is a child of ``015`` and its own ``upgrade`` honours the ordering
   contract -- tables, columns, backfill, indexes -- so a unique index is never
   built over data that is still unbackfilled.
4. Every column and column width that migration 016 declares is also declared by
   the mapped class in ``db/schema.py``. Alembic and ``Base.metadata.create_all``
   are two independent routes to the same database; when they drift, a fresh
   install and an upgraded install quietly end up with different tables and the
   "both paths reach the same schema" claim stops being true (SC-010).

Digest and shape values cover file content only; they are not a substitute for
running both install paths against a live PostgreSQL.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
from pathlib import Path

import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

APP_DIR = Path(__file__).resolve().parents[2]
VERSIONS_DIR = APP_DIR / "db" / "migrations" / "versions"
MIGRATION_FILE = VERSIONS_DIR / "016_relation_evidence_graph.py"
RELEASED_015 = VERSIONS_DIR / "015_worldline_reconstruction.py"

# SHA-256 of the released revision file, captured at the time 015 was released
# (line endings normalized). Adding a new revision is expected; editing this one
# is not -- an already-deployed database would never receive the change.
RELEASED_015_DIGEST = "377c005fb60192ee09722e98a1da89849bcab2e8e758c8fef0e0d0146ba490fd"

# The five tables of data-model.md section 10.1, in creation order.
EXPECTED_TABLES = (
    "evidence_context",
    "relation_claim",
    "relation_claim_revision",
    "relation_schema_version",
    "claim_context_lineage",
)

# Every index of data-model.md section 10.1, keyed to the columns it covers. The
# key is the index name; uniqueness is required for the ones named ``uq_``.
EXPECTED_INDEXES: dict[str, tuple[str, tuple[str, ...], bool]] = {
    "ix_evidence_context_tenant": ("evidence_context", ("tenant_id",), False),
    "ix_evidence_context_observation": (
        "evidence_context",
        ("tenant_id", "observation_id"),
        False,
    ),
    "ix_evidence_context_source": ("evidence_context", ("tenant_id", "source_id"), False),
    "ix_evidence_context_investigation": (
        "evidence_context",
        ("tenant_id", "investigation_id"),
        False,
    ),
    "uq_evidence_context_fingerprint": (
        "evidence_context",
        ("tenant_id", "frame_fingerprint"),
        True,
    ),
    "ix_relation_claim_tenant": ("relation_claim", ("tenant_id",), False),
    "ix_relation_claim_logical": (
        "relation_claim",
        ("tenant_id", "logical_relation_id"),
        False,
    ),
    "ix_relation_claim_type": ("relation_claim", ("tenant_id", "relation_type"), False),
    "ix_relation_claim_subject": ("relation_claim", ("tenant_id", "subject_ref"), False),
    "ix_relation_claim_object": ("relation_claim", ("tenant_id", "object_ref"), False),
    "ix_relation_claim_context": ("relation_claim", ("context_ref",), False),
    "uq_relation_claim_content": ("relation_claim", ("tenant_id", "content_hash"), True),
    "ix_relation_claim_revision_logical": (
        "relation_claim_revision",
        ("tenant_id", "logical_relation_id", "revision_number"),
        True,
    ),
    "ix_relation_claim_revision_relation": (
        "relation_claim_revision",
        ("relation_id",),
        False,
    ),
    "uq_relation_schema_version": (
        "relation_schema_version",
        ("tenant_id", "relation_type", "schema_version"),
        True,
    ),
    "ix_relation_schema_version_type": (
        "relation_schema_version",
        ("tenant_id", "relation_type"),
        False,
    ),
    "ix_claim_context_lineage_relation": (
        "claim_context_lineage",
        ("tenant_id", "relation_id", "direction"),
        False,
    ),
}

EXPECTED_UNIQUE_INDEXES = tuple(
    name for name, (_, _, unique) in EXPECTED_INDEXES.items() if unique
)

# The numbered section banners of ``016.upgrade()``. Their order is the ordering
# contract of data-model.md section 10.2 and is discovered the same way revision
# 015's own test discovers its add/backfill/index sequence.
SECTION_MARKERS = (
    "# 1. New tables",
    "# 2. New columns",
    "# 3. Backfill",
    "# 4. Indexes",
)

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
    index and table names, and a whole-file search would match those first.
    """
    text = _migration_text()
    return text[text.index("def upgrade()") : text.index("def downgrade()")]


def _downgrade_text() -> str:
    text = _migration_text()
    return text[text.index("def downgrade()") :]


class _OpRecorder:
    """Stand-in for ``alembic.op`` that records the DDL a migration would emit.

    Reading the migration's intent out of the recorded calls -- rather than out
    of its source text -- means a column or index added with a different
    formatting convention, or in a loop, is still compared against the
    declarative schema. Nothing is executed; this is inspection only.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self.tables: dict[str, tuple[sa.Column, ...]] = {}
        self.indexes: dict[str, tuple[str, tuple[str, ...], bool]] = {}
        self.created_tables: list[str] = []
        self.created_indexes: list[str] = []
        self.added_columns: list[tuple[str, str]] = []
        #: ``(table, column, resolved type)`` per ``alter_column``. A widening changes a
        #: column's type without changing its name, so it is the one operation a
        #: name-only comparison cannot see.
        self.altered_columns: list[tuple[str, str, object]] = []

    def create_table(self, name: str, *columns: sa.Column, **kwargs: object) -> None:
        self.calls.append(("create_table", (name,), dict(kwargs)))
        self.tables[name] = tuple(columns)
        self.created_tables.append(name)

    def add_column(self, table_name: str, column: sa.Column, **kwargs: object) -> None:
        self.calls.append(("add_column", (table_name, column.name), dict(kwargs)))
        self.added_columns.append((table_name, column.name))

    def create_index(
        self,
        name: str,
        table_name: str,
        columns: list[str],
        unique: bool = False,
        **kwargs: object,
    ) -> None:
        self.calls.append(("create_index", (name,), dict(kwargs)))
        self.indexes[name] = (table_name, tuple(columns), bool(unique))
        self.created_indexes.append(name)

    def drop_index(self, name: str, table_name: str | None = None, **kwargs: object) -> None:
        self.calls.append(("drop_index", (name, table_name), dict(kwargs)))

    def drop_table(self, name: str, **kwargs: object) -> None:
        self.calls.append(("drop_table", (name,), dict(kwargs)))

    def drop_column(self, table_name: str, column_name: str, **kwargs: object) -> None:
        self.calls.append(("drop_column", (table_name, column_name), dict(kwargs)))

    def alter_column(
        self,
        table_name: str,
        column_name: str,
        *,
        type_: sa.types.TypeEngine | None = None,
        **kwargs: object,
    ) -> None:
        """Record a type change on an existing column.

        Added when revision 020 became the first revision in this repository to widen a
        column rather than add or drop one, and this double is a stand-in for
        ``alembic.op`` - so the method belongs here for the same reason ``add_column`` does.
        Without it the replay in :func:`_columns_added_by_later_revisions` raises
        ``AttributeError`` on a perfectly valid migration, which is the worst failure mode
        a test double can have: it reports a defect in the code under test where there is
        none.

        The resolved type is recorded rather than discarded, because a widening is the one
        operation that can make the two install paths disagree about a column's *type*
        while leaving its name, nullability and count untouched - and that disagreement is
        invisible to a name-only comparison.
        """
        self.calls.append(("alter_column", (table_name, column_name), dict(kwargs)))
        self.altered_columns.append((table_name, column_name, type_))


def _load_migration() -> object:
    spec = importlib.util.spec_from_file_location("migration_016_under_test", MIGRATION_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _recorded(recorder: _OpRecorder, function_name: str) -> _OpRecorder:
    module = _load_migration()
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


def _columns_added_by_later_revisions() -> dict[str, set[str]]:
    """Which columns each table gained from a revision *after* 016, by replay.

    Replayed through a recorder rather than grepped out of the source, so a column
    added in a loop or through a helper is found the same way one added inline is
    -- the same discipline :func:`_recorded` follows for 016 itself.

    This exists because a table 016 *created* is not frozen forever. Revision 019
    appended ``relation_claim.regime_id``, which is a legitimate forward change to
    a table an earlier revision owns, and an exact-equality column comparison
    against 016 alone cannot tell that apart from a real divergence. Keying the
    tolerance on this set is what keeps the relaxation from becoming a loophole: a
    declared column that no later revision adds still fails.
    """
    revision = "016_relation_evidence_graph"
    edges: dict[str, str | None] = {}
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        found = _parse(path)
        edges[found[0]] = found[1]
    children = {down: rev for rev, down in edges.items() if down is not None}
    successors: list[str] = []
    cursor = children.get(revision)
    while cursor is not None:
        successors.append(cursor)
        cursor = children.get(cursor)

    added: dict[str, set[str]] = {}
    for name in successors:
        recorder = _OpRecorder()
        spec = importlib.util.spec_from_file_location(
            f"migration_{name}_under_test", VERSIONS_DIR / f"{name}.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.op = recorder  # type: ignore[attr-defined]
        module.upgrade()
        for table_name, column_name in recorder.added_columns:
            added.setdefault(table_name, set()).add(column_name)
    return added


def _type_signature(column: sa.Column) -> tuple[str, object]:
    """Comparable description of a column type, including ``String(n)`` width."""
    type_ = column.type
    if isinstance(type_, sa.String):
        return ("String", type_.length)
    if isinstance(type_, sa.DateTime):
        return ("DateTime", type_.timezone)
    return (type(type_).__name__, None)


def test_released_revision_015_is_not_edited() -> None:
    """Revision 015 must stay byte-identical to its released state (FR-042)."""
    assert RELEASED_015.exists(), "released revision missing: 015_worldline_reconstruction.py"
    actual = _content_digest(RELEASED_015)
    assert actual == RELEASED_015_DIGEST, (
        f"015_worldline_reconstruction.py was modified after release "
        f"(expected {RELEASED_015_DIGEST}, got {actual}). Released migrations are "
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


def test_relation_evidence_revision_follows_worldline_reconstruction() -> None:
    """016 must be a child of 015, not a replacement or a sibling root."""
    revision, down = _parse(MIGRATION_FILE)
    assert revision == "016_relation_evidence_graph"
    assert down == "015_worldline_reconstruction"


def test_no_later_revision_rewrites_revision_015() -> None:
    """Nothing after 015 may amend 015; 016 is the only permitted successor.

    Editing a released migration is invisible to a database that already ran it,
    so the schema divergence it causes is permanent and silent. A successor
    revision is the only way to reach an already-deployed database.
    """
    successors = []
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        if path.name in {"__init__.py", RELEASED_015.name}:
            continue
        text = path.read_text(encoding="utf-8")
        assert RELEASED_015.name not in text, (
            f"{path.name} references {RELEASED_015.name}; a released revision may "
            f"not be edited, only followed"
        )
        _, down = _parse(path)
        if down == "015_worldline_reconstruction":
            successors.append(path.name)
    assert successors == [MIGRATION_FILE.name], (
        f"expected 016 to be the sole successor of 015, got {successors}"
    )


def test_upgrade_creates_every_table_before_any_index() -> None:
    """Section 1 precedes section 4: no index over a column that does not exist."""
    upgrade = _upgrade_text()

    positions = []
    for marker in SECTION_MARKERS:
        assert marker in upgrade, f"016.upgrade() is missing section {marker!r}"
        positions.append(upgrade.index(marker))
    assert positions == sorted(positions), (
        f"016.upgrade() sections are out of order: {SECTION_MARKERS}"
    )

    tables_block = upgrade[: positions[3]]
    indexes_block = upgrade[positions[3] :]
    for name in EXPECTED_TABLES:
        assert f'"{name}"' in tables_block, (
            f"{name} must be created in section 1, before any index is built"
        )
    for name in EXPECTED_INDEXES:
        assert f'"{name}"' not in tables_block, (
            f"index {name} must not be created alongside the tables"
        )
        assert f'"{name}"' in indexes_block, f"index {name} is not created in section 4"


def test_upgrade_creates_every_data_model_index_with_its_columns() -> None:
    """Index names, targets, columns and uniqueness match data-model.md 10.1."""
    recorder = _recorded(_OpRecorder(), "upgrade")
    assert set(recorder.indexes) == set(EXPECTED_INDEXES), (
        f"unexpected index set: {sorted(set(recorder.indexes) ^ set(EXPECTED_INDEXES))}"
    )
    for name, (table, columns, unique) in EXPECTED_INDEXES.items():
        assert recorder.indexes[name] == (table, columns, unique), (
            f"index {name} must be {unique and 'unique ' or ''}on {table}"
            f"{list(columns)}, got {recorder.indexes[name]}"
        )


def test_upgrade_creates_every_unique_index() -> None:
    """Each content-addressed identity has a unique index behind it.

    Without these, a replayed write produces a second context or a second claim
    row for identical content, and the trace from a relation back to its source
    acquires duplicates.
    """
    recorder = _recorded(_OpRecorder(), "upgrade")
    for name in EXPECTED_UNIQUE_INDEXES:
        assert name in recorder.indexes, f"unique index {name} is missing"
        assert recorder.indexes[name][2], f"index {name} must be created unique"


def test_upgrade_creates_exactly_the_five_data_model_tables() -> None:
    """The five tables, in order, and no column added to an existing table."""
    recorder = _recorded(_OpRecorder(), "upgrade")
    assert tuple(recorder.created_tables) == EXPECTED_TABLES
    assert recorder.added_columns == [], (
        "016 adds only new tables; a column added to an existing table would have "
        f"to be backfilled before the unique indexes, got {recorder.added_columns}"
    )
    module = _load_migration()
    assert set(module._ACTIVE) == set(EXPECTED_TABLES), (
        "the recorded no-op sections must name the tables this revision creates"
    )


def test_upgrade_records_its_backfill_as_an_explicit_no_op() -> None:
    """Section 3 exists and runs between the columns and the indexes."""
    recorder = _recorded(_OpRecorder(), "upgrade")
    order = [name for name, _, _ in recorder.calls]
    # The no-op helpers are plain Python calls, so they are absent from the
    # recorded DDL; their presence in the body is what this test pins.
    upgrade = _upgrade_text()
    assert "_no_new_columns()" in upgrade
    assert "_no_backfill()" in upgrade
    assert upgrade.index("_no_new_columns()") < upgrade.index("_no_backfill()")
    assert upgrade.index("_no_backfill()") < upgrade.index('"ix_evidence_context_tenant"')
    assert order.index("create_table") < order.index("create_index")


def test_downgrade_drops_everything_upgrade_created_in_reverse_order() -> None:
    """downgrade() is the strict reverse: indexes, then tables (data-model 10.2)."""
    recorder = _recorded(_OpRecorder(), "upgrade")
    created_indexes = list(recorder.created_indexes)
    created_tables = list(recorder.created_tables)
    recorder.calls.clear()
    _recorded(recorder, "downgrade")

    dropped_indexes = [
        args[0] for name, args, _ in recorder.calls if name == "drop_index"
    ]
    dropped_tables = [args[0] for name, args, _ in recorder.calls if name == "drop_table"]

    assert set(dropped_indexes) == set(created_indexes)
    assert dropped_indexes == list(reversed(created_indexes)), (
        "downgrade() must drop indexes in the reverse of creation order"
    )
    assert set(dropped_tables) == set(created_tables)
    assert dropped_tables == list(reversed(created_tables)), (
        "downgrade() must drop tables in the reverse of creation order"
    )
    first_table_drop = next(
        i for i, (name, _, _) in enumerate(recorder.calls) if name == "drop_table"
    )
    last_index_drop = max(
        i for i, (name, _, _) in enumerate(recorder.calls) if name == "drop_index"
    )
    assert all(
        name == "drop_index" for name, _, _ in recorder.calls[:last_index_drop + 1]
    ), "downgrade() must drop every index before dropping any table"
    assert all(
        name == "drop_table" for name, _, _ in recorder.calls[first_table_drop:]
    ), "downgrade() must not drop a column or re-create DDL after dropping tables"
    assert last_index_drop < first_table_drop, (
        "downgrade() must drop every index before dropping any table"
    )


def test_downgrade_drops_no_column_that_upgrade_did_not_add() -> None:
    """016 adds no columns, so its downgrade must not drop any."""
    recorder = _recorded(_OpRecorder(), "downgrade")
    assert not [args for name, args, _ in recorder.calls if name == "drop_column"]


def test_migration_columns_match_declarative_schema() -> None:
    """Alembic and ``create_all`` must agree on the column set of every table.

    This is the load-bearing check for SC-010: the two install paths build the
    schema from two different sources, and a column present in only one of them
    makes a fresh install and an upgraded install differ. A column added here
    without being added to ``db/schema.py`` fails the same way, so the two edits
    cannot be made independently.

    The agreement is asserted in the direction 016 is responsible for -- every
    column 016 declares is declared by the mapped class -- plus one narrow
    exception in the other direction. A table 016 created is not frozen: revision
    019 appended ``relation_claim.regime_id``, and a later revision adding a column
    to a table an earlier revision owns is how this repository evolves, not a
    divergence. So an extra declared column is tolerated **only** when a later
    revision adds that same column, which is why the exception is keyed on a
    replay of the successor revisions rather than waved through. A declared column
    that no later revision adds is still a failure, and a column 016 declares that
    the schema lacks is still a failure in both directions.
    """
    recorder = _recorded(_OpRecorder(), "upgrade")
    metadata = _declarative_metadata()
    added_later = _columns_added_by_later_revisions()
    for name in EXPECTED_TABLES:
        assert name in metadata.tables, (
            f"{name} is created by migration 016 but missing from db/schema.py"
        )
        migrated = {column.name for column in recorder.tables[name]}
        declared = set(metadata.tables[name].columns.keys())
        assert not migrated - declared, (
            f"{name} column drift between migration 016 and db/schema.py: "
            f"only in migration {sorted(migrated - declared)}"
        )
        unattributed = (declared - migrated) - added_later.get(name, set())
        assert not unattributed, (
            f"{name} declares {sorted(unattributed)} in db/schema.py that migration "
            f"016 does not create and no later revision adds; a column in one install "
            f"path and not the other is exactly the divergence this test exists for"
        )


def test_migration_column_widths_match_declarative_schema() -> None:
    """Column types and ``String(n)`` widths agree between migration and schema.

    A width that is only tightened in the migration silently truncates a longer
    identifier or role name in an upgraded database while a fresh one keeps the
    full value, which is a data-loss divergence that no column-set comparison
    would catch.
    """
    recorder = _recorded(_OpRecorder(), "upgrade")
    metadata = _declarative_metadata()
    for name in EXPECTED_TABLES:
        table = metadata.tables[name]
        for column in recorder.tables[name]:
            assert column.name in table.columns, (
                f"{name}.{column.name} is in migration 016 but not in db/schema.py; "
                f"the width comparison below assumes the column sets agree"
            )
            migrated = _type_signature(column)
            declared = _type_signature(table.columns[column.name])
            assert migrated == declared, (
                f"{name}.{column.name} type differs between migration 016 and "
                f"db/schema.py: migration {migrated[0]}({migrated[1]}), "
                f"schema {declared[0]}({declared[1]})"
            )


def test_migration_indexes_match_declarative_schema() -> None:
    """Both install paths create the same indexes over the same columns."""
    recorder = _recorded(_OpRecorder(), "upgrade")
    metadata = _declarative_metadata()
    for name in EXPECTED_TABLES:
        table = metadata.tables[name]
        declared = {
            index.name: (tuple(col.name for col in index.columns), index.unique)
            for index in table.indexes
        }
        migrated = {
            index_name: (columns, unique)
            for index_name, (table_name, columns, unique) in recorder.indexes.items()
            if table_name == name
        }
        assert migrated == declared, (
            f"{name} index drift between migration 016 and db/schema.py: "
            f"migration {migrated}, schema {declared}"
        )
