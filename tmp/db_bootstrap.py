"""Create the control-plane schema in the live dev Postgres and report row counts."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "control-plane"))

from sqlalchemy import text  # noqa: E402

from db.schema import Base  # noqa: E402
from db.session import make_engine  # noqa: E402


async def main() -> int:
    engine = make_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print(f"created {len(Base.metadata.tables)} tables")

    async with engine.connect() as conn:
        names = [
            row[0]
            for row in (
                await conn.execute(
                    text(
                        "select table_name from information_schema.tables "
                        "where table_schema='public' order by table_name"
                    )
                )
            ).all()
        ]
        print(f"{len(names)} tables present in the live database")
        total = 0
        for name in names:
            count = (await conn.execute(text(f'select count(*) from "{name}"'))).scalar_one()
            total += int(count)
            if int(count):
                print(f"  {name}: {count}")
        print(f"total rows across all tables: {total}")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
