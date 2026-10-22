import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DSN = "postgresql+asyncpg://cognitive:cognitive@localhost:5432/cognitive"


async def main() -> None:
    engine = create_async_engine(DSN)
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text("select entity_type, count(*) from entities group by 1 order by 2 desc")
            )
        ).all()
        print("live entity_type values:", rows)
        constraints = (
            await conn.execute(
                text(
                    "select conname, pg_get_constraintdef(oid) from pg_constraint "
                    "where conrelid = 'entities'::regclass and contype = 'c'"
                )
            )
        ).all()
        print("entities check constraints:", constraints)
        whitelist = (
            await conn.execute(
                text(
                    "select table_name from information_schema.tables "
                    "where table_schema in ('public','control_plane') order by 1"
                )
            )
        ).scalars().all()
        print("tables:", len(whitelist), whitelist[:15])
    await engine.dispose()


asyncio.run(main())
