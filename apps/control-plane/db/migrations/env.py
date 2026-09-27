import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # apps/control-plane
from config.settings import get_settings

from db.schema import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _resolve_url() -> str:
    """Return the SQLAlchemy URL for migrations.

    An explicit ``sqlalchemy.url`` in ``alembic.ini`` wins; otherwise the
    application DSN from ``POSTGRES_*`` settings is used. Without this the empty
    placeholder in ``alembic.ini`` makes every invocation fail with "Connection,
    url, or dialect_name is required", so the migration path could never actually
    be exercised.

    That DSN is ``postgresql+asyncpg://``, so online migrations run through
    Alembic's async support below rather than a sync driver this project does not
    depend on.
    """
    configured = (config.get_main_option("sqlalchemy.url") or "").strip()
    if configured:
        return configured
    return get_settings().postgres.dsn


def run_migrations_offline() -> None:
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    section = config.get_section(config.config_ini_section, {}) or {}
    section["sqlalchemy.url"] = _resolve_url()
    connectable = async_engine_from_config(
        section, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    try:
        async with connectable.connect() as connection:
            await connection.run_sync(_do_run_migrations)
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()