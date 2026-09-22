"""Async Postgres bootstrap for the control plane (dev topology).

One async engine/session factory bound to :mod:`config.settings`; tables are
created idempotently for the dev loop (`create_tables`). Production DDL is left
to Alembic migrations (``alembic.ini`` + ``db/migrations``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from config.settings import get_settings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SessionFactory = Callable[[], Awaitable[AsyncSession]]


def _async_dsn(dsn: str | None) -> str | None:
    if dsn and "://" in dsn and "+" not in dsn.split("://", 1)[0]:
        return dsn.replace("://", "+asyncpg://", 1)
    return dsn


def make_session_factory(dsn: str | None = None):
    """Return an ``async_sessionmaker`` usable as ``async with factory() as s``."""
    engine = create_async_engine(_async_dsn(dsn) or get_settings().postgres.dsn, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


def make_engine(dsn: str | None = None):
    return create_async_engine(_async_dsn(dsn) or get_settings().postgres.dsn, pool_pre_ping=True)


async def create_tables(dsn: str | None = None) -> None:
    """Idempotent DDL so dev/integration environments boot without a migration."""
    from db.schema import Base

    engine = make_engine(dsn)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


async def drop_tables(dsn: str | None = None) -> None:
    """Teardown for hermetic integration tests only."""
    from db.schema import Base

    engine = make_engine(dsn)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()