"""Assert the ORM schema and migration 015 agree.

``create_tables()`` builds from ORM metadata while deployments build from
migrations, so a silent divergence between the two would make the dev loop and
production disagree. Alembic autogenerate against a database already at head
must therefore report no changes: any difference is drift.

The comparison runs through the project's async engine (``asyncpg``). No
synchronous PostgreSQL driver is a declared dependency, so a plain
``create_engine`` would not work here.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

_APPS = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_APPS / "shared"))
sys.path.insert(0, str(_APPS))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from config.settings import get_settings
from sqlalchemy.ext.asyncio import create_async_engine

from db.schema import Base

#: Tables this feature owns. Unrelated pre-existing drift is out of scope for
#: feature 015 and would otherwise mask a real regression.
#:
#: ``frontier_items`` joined the list with migration 017, which added the
#: ``provenance`` column. It has to be in here: this is the only check that the
#: column the ORM declares is the column the migration adds, so leaving the table
#: out means a drift in it -- a renamed column, a dropped NOT NULL, a different
#: server default -- is invisible to CI, and a missing provenance column surfaces
#: weeks later as an audit question with no answer.
#:
#: The four semantic-fabric tables joined it with migration 018 for the same
#: reason. They are the durable record of a typing, a profile, an alignment and a
#: finding, and a fresh install (``create_all``) building them differently from an
#: upgraded one (``018_semantic_fabric.py``) is a divergence in the one place where
#: monotonic history and tenant scoping are supposed to be structural.
OWNED_TABLES = {
    "source_query_set",
    "source_query",
    "reconstruction_frontier",
    "entity_stream_sequence",
    "materialization_outbox",
    "frontier_items",
    "type_assertions",
    "semantic_profiles",
    "semantic_mappings",
    "validation_findings",
}


def _table_of(diff_entry) -> str:
    if isinstance(diff_entry, tuple):
        return str(diff_entry[0])
    return str(getattr(diff_entry, "table", ""))


async def _diff() -> list:
    engine = create_async_engine(get_settings().postgres.dsn)
    try:
        async with engine.connect() as connection:

            def _compare(sync_connection):
                context = MigrationContext.configure(sync_connection)
                return compare_metadata(context, Base.metadata)

            return await connection.run_sync(_compare)
    finally:
        await engine.dispose()


def test_orm_metadata_matches_migration_015() -> None:
    """No autogenerate drift between ORM models and the applied schema."""
    try:
        diff = asyncio.run(_diff())
    except (OSError, ConnectionError) as exc:
        pytest.skip(f"PostgreSQL is not reachable at the configured DSN: {exc}")
    relevant = [entry for entry in diff if _table_of(entry) in OWNED_TABLES]
    assert relevant == [], f"ORM/migration drift on feature 015 tables: {relevant}"

