"""The durable store, against a real Postgres.

An in-memory store passing its own tests proves nothing about the property that matters
here, so these run against the running database and the central assertion is the one a
dict could never satisfy: **the context survives losing the connection**.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP.parents[1] / "apps" / "shared"))
sys.path.insert(0, str(APP / "control-plane"))

from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from context_engine.obligations import ContextFrontier  # noqa: E402
from context_engine.postgres_store import PostgresContextStore  # noqa: E402
from context_engine.store import StoreDurability  # noqa: E402
from domain.investigation_context import InvestigationContext  # noqa: E402

DSN = os.environ.get(
    "COGNITIVE_PG_DSN",
    "postgresql+asyncpg://cognitive:cognitive@localhost:5432/cognitive",
)

pytestmark = pytest.mark.asyncio


def _context(investigation_id: str = "INV-pg-1", question: str = "") -> InvestigationContext:
    return InvestigationContext(
        tenant_id="default-tenant",
        investigation_id=investigation_id,
        title="Postgres store probe",
        scope_refs=(investigation_id,),
        question=question,
    )


async def _store() -> tuple[PostgresContextStore, object]:
    engine = create_async_engine(DSN)
    connection = await engine.connect()
    store = PostgresContextStore(connection)
    await store.ensure_schema()
    return store, (connection, engine)


async def test_it_reports_itself_durable() -> None:
    store, held = await _store()
    try:
        assert store.durability() is StoreDurability.DURABLE
    finally:
        await held[0].close()
        await held[1].dispose()


async def test_a_context_survives_a_new_connection() -> None:
    """The whole point. A dict-backed store cannot pass this, which is exactly why the
    test exists."""
    context = _context(question="find everything about the Putin family structure")

    store, held = await _store()
    try:
        await store.put_context(context)
    finally:
        await held[0].close()
        await held[1].dispose()

    engine = create_async_engine(DSN)
    connection = await engine.connect()
    try:
        fresh = PostgresContextStore(connection)
        await fresh.ensure_schema()
        read = await fresh.get_context(context.context_id)
        assert read is not None, "the context did not survive the connection"
        assert read.context_id == context.context_id
        assert read.investigation_id == context.investigation_id
        assert read.question == context.question
        assert read.scope_refs == context.scope_refs
    finally:
        await connection.close()
        await engine.dispose()


async def test_writing_the_same_context_twice_is_one_row() -> None:
    """Content-addressed ids make this idempotent, so a retried create does not fork."""
    context = _context()
    store, held = await _store()
    try:
        await store.put_context(context)
        await store.put_context(context)
        rows = await store.contexts()
        matching = [c for c in rows if c.context_id == context.context_id]
        assert len(matching) == 1
    finally:
        await held[0].close()
        await held[1].dispose()


async def test_missing_context_is_none_and_not_an_error() -> None:
    store, held = await _store()
    try:
        assert await store.get_context("CXI-does-not-exist") is None
    finally:
        await held[0].close()
        await held[1].dispose()


async def test_revisions_are_append_only_and_ordered() -> None:
    from domain.investigation_context import ContextRevision

    context = _context()
    store, held = await _store()
    try:
        await store.put_context(context)
        # ``parent_revision`` is the preceding *number*, not a revision id: the domain
        # refuses a revision whose parent is not ``revision - 1``, which is what makes
        # the chain verifiable rather than merely ordered.
        first = await store.next_revision_number(context.context_id)
        for offset in range(3):
            number = first + offset
            await store.append_revision(
                ContextRevision(
                    context_id=context.context_id,
                    revision=number,
                    parent_revision=number - 1,
                    state=context.state,
                    snapshot={"note": f"revision {number}"},
                )
            )
        revisions = await store.revisions(context.context_id)
        assert [r.revision for r in revisions] == sorted(r.revision for r in revisions)
        assert len(revisions) >= 3
        assert (((((((((((await store.next_revision_number(context.context_id)))))))))))) >= first + 3
        current = await store.current_revision(context.context_id)
        assert current is not None
        assert current.revision == revisions[-1].revision
    finally:
        await held[0].close()
        await held[1].dispose()


async def test_frontier_round_trips() -> None:
    context = _context()
    store, held = await _store()
    try:
        frontier = ContextFrontier(
            context_id=context.context_id,
            state=context.state,
            open_obligations=("OBL-1", "OBL-2"),
            notes=("waiting on archive",),
        )
        await store.put_frontier(frontier)
        read = await store.get_frontier(context.context_id)
        assert read is not None
        assert read.open_obligations == ("OBL-1", "OBL-2")
        assert read.notes == ("waiting on archive",)
        assert read.state == frontier.state
    finally:
        await held[0].close()
        await held[1].dispose()


async def test_the_schema_is_idempotent() -> None:
    """Two workers racing to create the tables must not turn into an error."""
    store, held = await _store()
    try:
        await store.ensure_schema()
        await store.ensure_schema()
    finally:
        await held[0].close()
        await held[1].dispose()