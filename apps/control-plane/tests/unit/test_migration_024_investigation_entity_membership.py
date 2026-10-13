"""Migration 024: investigation membership for entities.

Three invariants, at three different levels of exposure:

1. **The revision graph.** 024 must be appended to 023, not spliced into it. Editing a
   released revision is what ``test_migration_forward_only`` exists to prevent, and a
   second head makes ``alembic upgrade head`` ambiguous for whoever runs it next.
2. **Both install paths.** ``Base.metadata.create_all`` and ``alembic upgrade`` build the
   table independently. A divergence between them is invisible until a deployment that
   took the other path hits a column or a constraint the first one never had, so the
   comparison is run against a live PostgreSQL in a throwaway schema -- each path in its
   own -- rather than against recorded DDL.
3. **The vocabulary stays in step.** The CHECK constraint and the migration hold the same
   three basis values, and the migration holds them as SQL literals on purpose: a
   revision that imported a Python value type would change meaning when somebody edited
   that type, and a database that already ran it cannot be re-run. A deliberate
   duplication survives only while a test says the two copies still agree.

The migration creates a table and touches nothing else, which is why it is safe to apply
to a database whose earlier revisions already drifted -- notably the
``frontier_items`` disruption, which belongs to another change.
"""

from __future__ import annotations

import asyncio
import inspect
import re
import sys
from pathlib import Path

import pytest

_APPS = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_APPS / "shared"))
sys.path.insert(0, str(_APPS / "control-plane"))

VERSIONS_DIR = _APPS / "control-plane" / "db" / "migrations" / "versions"
MIGRATION = VERSIONS_DIR / "024_investigation_entity_membership.py"
EXPECTED_TABLE = "investigation_entity_memberships"

_REVISION = re.compile(r'^revision\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)
_DOWN_REVISION = re.compile(r'^down_revision\s*=\s*(.+)$', re.MULTILINE)


def _source() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _load_revision_module():
    """Import 024 as a module so its ``upgrade()`` runs against a bound Alembic context."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("revision_024_under_test", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _body(module, name: str) -> str:
    """Source of one function, with its docstring removed.

    Several assertions below are "this revision does not contain X". Searching the whole
    file would trip over the prose that explains *why* X is absent -- the module
    docstring says "No foreign keys" in as many words. Inspecting the executable body is
    what makes the check mean what it says.
    """
    source = inspect.getsource(getattr(module, name))
    return re.sub(r'""".*?"""', "", source, flags=re.DOTALL)


# --- 1. the revision graph -------------------------------------------------


def test_024_is_appended_to_023_and_is_the_single_head() -> None:
    """024 follows 023, and nothing else claims to be the head."""
    assert MIGRATION.exists(), "migration 024 is missing"

    revisions: dict[str, str | None] = {}
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        rev = _REVISION.search(text)
        assert rev, f"{path.name} has no revision identifier"
        parent = _DOWN_REVISION.search(text)
        assert parent, f"{path.name} has no down_revision"
        raw = parent.group(1).strip()
        if raw == "None":
            revisions[rev.group(1)] = None
            continue
        quoted = re.match(r'^["\']([^"\']+)["\']$', raw)
        assert quoted, f"{path.name} has an unparseable down_revision: {raw!r}"
        revisions[rev.group(1)] = quoted.group(1)

    assert "024_investigation_entity_membership" in revisions
    assert revisions["024_investigation_entity_membership"] == "023_derivation_enforcement", (
        "024 must be appended to the current head; a different parent either forks the "
        "graph or rewrites history"
    )

    roots = [rev for rev, parent in revisions.items() if parent is None]
    assert roots == ["014_temporal_materialization"], roots

    children: dict[str, list[str]] = {}
    for rev, parent in revisions.items():
        if parent is None:
            continue
        assert parent in revisions, f"{rev} points at unknown parent {parent}"
        children.setdefault(parent, []).append(rev)

    branched = sorted(parent for parent, kids in children.items() if len(kids) > 1)
    assert branched == [], f"the revision graph has a branch at {branched}"

    heads = sorted(rev for rev in revisions if rev not in children)
    assert heads == ["024_investigation_entity_membership"], (
        f"024 must be the only head, otherwise `alembic upgrade head` is ambiguous; "
        f"got {heads}"
    )


def test_024_only_creates_its_own_table() -> None:
    """It is additive: no column dropped, no other table touched, reversible.

    A revision that mutated an existing table would be changing history the released
    migrations already wrote -- which is what appending a new revision is for.
    """
    module = _load_revision_module()
    upgrade = _body(module, "upgrade")
    downgrade = _body(module, "downgrade")

    for forbidden in ("op.drop_table", "op.drop_column", "op.alter_column", "op.execute"):
        assert forbidden not in upgrade, (
            f"024 must not run {forbidden}: this revision only creates a table"
        )
    assert "ALTER TABLE" not in upgrade.upper()
    assert "op.drop_table" in downgrade, "a created table must be droppable again"


def test_migration_records_no_foreign_keys() -> None:
    """Documented, not incidental: the entity row and its membership are written by
    different processes on different schedules, so an FK would make write order
    load-bearing. An accidental ``ForeignKey("entities.entity_id")`` would be exactly the
    constraint this design refuses, and it would be invisible in a column list."""
    module = _load_revision_module()
    for name in ("upgrade", "downgrade"):
        body = _body(module, name)
        assert "ForeignKey" not in body, f"{name} declares a foreign key"
        assert "FOREIGN KEY" not in body.upper(), f"{name} declares a foreign key"


# --- 3. the vocabulary stays in step ----------------------------------------


def test_migration_basis_values_match_the_orm() -> None:
    """The SQL literals and the ORM CHECK name the same three values."""
    from db.schema import InvestigationEntityMembership as Membership

    declared: set[str] = set()
    for constraint in Membership.__table__.constraints:
        if constraint.name == "ck_investigation_entity_membership_basis":
            declared = set(re.findall(r"'([A-Z_]+)'", str(constraint.sqltext)))
    assert declared, "the ORM declares no basis CHECK to compare against"
    assert declared == {"EXPLICIT", "ANALYST_ASSERTION", "RELATION_DERIVED"}

    literal_block = re.search(
        r"MEMBERSHIP_BASIS_VALUES[^=]*=\s*\((.*?)\)", _source(), re.DOTALL
    )
    assert literal_block, "024 declares no MEMBERSHIP_BASIS_VALUES"
    literals = set(re.findall(r'"([A-Z_]+)"', literal_block.group(1)))
    assert literals == declared, (
        f"the migration and the ORM disagree on the membership basis vocabulary: "
        f"migration {sorted(literals)} vs ORM {sorted(declared)}"
    )


def test_route_and_orm_share_the_basis_vocabulary() -> None:
    """The route writes ``EXPLICIT``; the database refuses anything outside the CHECK.

    A route that invented a fourth spelling would 500 at write time with a constraint
    violation rather than at the boundary that could have caught it.
    """
    from api.routes.entities import MEMBERSHIP_BASIS_EXPLICIT
    from db.schema import InvestigationEntityMembership as Membership

    declared = {
        value
        for constraint in Membership.__table__.constraints
        if constraint.name == "ck_investigation_entity_membership_basis"
        for value in re.findall(r"'([A-Z_]+)'", str(constraint.sqltext))
    }
    assert MEMBERSHIP_BASIS_EXPLICIT in declared


def test_orm_membership_table_is_shaped_as_the_migration_builds_it() -> None:
    """Column set, nullability, widths and the composite key, from metadata alone."""
    from db.schema import InvestigationEntityMembership as Membership

    table = Membership.__table__
    assert table.name == EXPECTED_TABLE

    columns = {column.name: column for column in table.columns}
    assert set(columns) == {
        "tenant_id",
        "investigation_id",
        "entity_id",
        "basis",
        "established_by",
        "created_at",
    }
    assert columns["entity_id"].type.length == 64, (
        "entity_id must stay 64 wide: every other entity reference in this schema is, and "
        "a truncated address is silent"
    )
    assert not any(column.nullable for column in columns.values()), (
        "a membership is only a membership if all three addresses are present"
    )

    assert sorted(column.name for column in table.primary_key.columns) == [
        "entity_id",
        "investigation_id",
        "tenant_id",
    ], "the composite key is what makes re-establishing membership idempotent"

    by_name = {index.name: index for index in table.indexes}
    assert set(by_name) == {
        "ix_investigation_entity_membership_inv",
        "ix_investigation_entity_membership_entity",
    }
    assert list(by_name["ix_investigation_entity_membership_inv"].columns.keys()) == [
        "tenant_id",
        "investigation_id",
    ], "the read path is investigation-scoped and tenant-led"
    assert list(by_name["ix_investigation_entity_membership_entity"].columns.keys()) == [
        "tenant_id",
        "entity_id",
    ]


def test_base_metadata_registers_the_membership_table() -> None:
    """A fresh install builds this table too -- it is in the shared metadata, not only
    in the migration."""
    from db.schema import Base

    assert EXPECTED_TABLE in Base.metadata.tables


# --- 2. both install paths, against a live PostgreSQL -----------------------


def _skip_without_postgres() -> str:
    from config.settings import get_settings
    from sqlalchemy.exc import DBAPIError, SQLAlchemyError
    from sqlalchemy.ext.asyncio import create_async_engine

    dsn = get_settings().postgres.dsn
    if not dsn:
        return "no Postgres DSN is configured"

    async def _probe() -> str | None:
        engine = create_async_engine(dsn)
        try:
            async with engine.connect() as connection:
                await connection.exec_driver_sql("SELECT 1")
            return None
        except (DBAPIError, SQLAlchemyError, OSError, ValueError) as exc:
            return f"PostgreSQL is not reachable at the configured DSN: {type(exc).__name__}"
        finally:
            await engine.dispose()

    try:
        return asyncio.run(_probe()) or ""
    except (SQLAlchemyError, OSError, ValueError) as exc:
        return f"PostgreSQL probe failed: {type(exc).__name__}: {exc}"


@pytest.mark.integration
def test_both_install_paths_build_one_table_on_a_live_database() -> None:
    """``create_all`` and the revision's own DDL must store the same table.

    Run in a throwaway schema per path so the application's real tables are never
    touched, and so the comparison is against what the server actually stores rather
    than against recorded DDL text.
    """
    reason = _skip_without_postgres()
    if reason:
        pytest.skip(f"{reason} -- live install-path comparison not exercised")

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text

    from db.schema import InvestigationEntityMembership as Membership
    from db.session import make_engine

    revision_module = _load_revision_module()

    column_sql = text(
        "SELECT column_name, is_nullable, data_type, character_maximum_length, "
        "column_default FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = :t "
        "ORDER BY column_name"
    )
    order_sql = text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = :t "
        "ORDER BY ordinal_position"
    )
    index_sql = text(
        "SELECT indexname FROM pg_indexes "
        "WHERE schemaname = current_schema() AND tablename = :t"
    )

    async def _run() -> tuple[list, list, list, list, list, list]:
        engine = make_engine()
        fresh = make_engine()
        upgraded = make_engine()
        try:
            async with engine.begin() as connection:
                for name in ("cp024_fresh", "cp024_upgrade"):
                    await connection.execute(text(f"DROP SCHEMA IF EXISTS {name} CASCADE"))
                    await connection.execute(text(f"CREATE SCHEMA {name}"))

            async with fresh.begin() as connection:
                await connection.execute(text("SET search_path TO cp024_fresh"))
                await connection.run_sync(
                    lambda sync: Membership.__table__.create(sync, checkfirst=False)
                )

            async with upgraded.begin() as connection:
                await connection.execute(text("SET search_path TO cp024_upgrade"))

                def _upgrade(sync_connection) -> None:
                    migration_context = MigrationContext.configure(sync_connection)
                    # `upgrade()` calls the module-level `alembic.op` proxy, which is
                    # inert until a migration context installs into it. Binding one here
                    # runs the revision's real DDL rather than a restatement of it.
                    with Operations.context(migration_context):
                        revision_module.upgrade()

                await connection.run_sync(_upgrade)

            result: dict[str, tuple[list, list, list]] = {}
            async with engine.begin() as connection:
                for key, name in (("fresh", "cp024_fresh"), ("upgrade", "cp024_upgrade")):
                    await connection.execute(text(f"SET search_path TO {name}"))
                    columns = [tuple(row) for row in (await connection.execute(column_sql, {"t": EXPECTED_TABLE})).all()]
                    orders = [row[0] for row in (await connection.execute(order_sql, {"t": EXPECTED_TABLE})).all()]
                    indexes = sorted(row[0] for row in (await connection.execute(index_sql, {"t": EXPECTED_TABLE})).all())
                    result[key] = (columns, orders, indexes)
                for name in ("cp024_fresh", "cp024_upgrade"):
                    await connection.execute(text(f"DROP SCHEMA IF EXISTS {name} CASCADE"))
            return (
                result["fresh"][0],
                result["upgrade"][0],
                result["fresh"][1],
                result["upgrade"][1],
                result["fresh"][2],
                result["upgrade"][2],
            )
        finally:
            for handle in (engine, fresh, upgraded):
                await handle.dispose()

    fresh_columns, upgrade_columns, fresh_order, upgrade_order, fresh_indexes, upgrade_indexes = asyncio.run(_run())

    assert upgrade_columns == fresh_columns, (
        f"live install-path divergence on {EXPECTED_TABLE}: "
        f"upgrade {upgrade_columns} != create_all {fresh_columns}"
    )
    assert upgrade_order == fresh_order, (
        f"live physical column-order divergence: {upgrade_order} != {fresh_order}"
    )
    # The primary key is named in the migration and implied by create_all, so only the
    # two named secondary indexes are compared as a set.
    for index in (
        "ix_investigation_entity_membership_inv",
        "ix_investigation_entity_membership_entity",
    ):
        assert index in fresh_indexes, f"{index} missing from the fresh install: {fresh_indexes}"
        assert index in upgrade_indexes, f"{index} missing from the upgraded install: {upgrade_indexes}"


@pytest.mark.integration
def test_the_closed_basis_vocabulary_is_enforced_by_the_server() -> None:
    """A basis nobody declared must be refused by the database, not by a comment."""
    reason = _skip_without_postgres()
    if reason:
        pytest.skip(f"{reason} -- live CHECK constraint not exercised")

    from sqlalchemy import text

    from db.schema import InvestigationEntityMembership as Membership
    from db.session import make_engine

    async def _probe() -> tuple[bool, bool]:
        engine = make_engine()
        try:
            async with engine.begin() as connection:
                await connection.execute(text("DROP SCHEMA IF EXISTS cp024_check CASCADE"))
                await connection.execute(text("CREATE SCHEMA cp024_check"))
                await connection.execute(text("SET search_path TO cp024_check"))
                await connection.run_sync(
                    lambda sync: Membership.__table__.create(sync, checkfirst=False)
                )
            async with engine.connect() as connection:
                await connection.execute(text("SET search_path TO cp024_check"))
                await connection.execute(
                    text(
                        "INSERT INTO investigation_entity_memberships "
                        "(tenant_id, investigation_id, entity_id, basis) "
                        "VALUES ('t', 'inv', 'ent', 'EXPLICIT')"
                    )
                )
                await connection.commit()
            refused = False
            try:
                async with engine.connect() as connection:
                    await connection.execute(text("SET search_path TO cp024_check"))
                    await connection.execute(
                        text(
                            "INSERT INTO investigation_entity_memberships "
                            "(tenant_id, investigation_id, entity_id, basis) "
                            "VALUES ('t', 'inv', 'ent2', 'MADE_UP')"
                        )
                    )
                    await connection.commit()
            except Exception:  # noqa: BLE001 - the refusal is the assertion
                refused = True
            async with engine.begin() as connection:
                await connection.execute(text("DROP SCHEMA IF EXISTS cp024_check CASCADE"))
            return True, refused
        finally:
            await engine.dispose()

    accepted_valid, refused = asyncio.run(_probe())
    assert accepted_valid, "a declared basis value was refused by the server"
    assert refused, "the server accepted a basis value outside the declared vocabulary"
