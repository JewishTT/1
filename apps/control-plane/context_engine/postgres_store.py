"""PostgreSQL-backed :class:`~context_engine.store.ContextStore`.

Why this exists
---------------
``InMemoryContextStore`` is the reference implementation and 112 tests run against it.
It is also, by its own ``durability()``, *memory* -- an investigation's context, its
revisions, its obligations, its actions and its action memory all vanish when the process
does. For a platform whose subject is long-running reconnaissance that is not a
limitation, it is a contradiction: an investigation that forgets what it was asked is a
different investigation.

This store keeps the **contract** and changes only where the bytes live. It is written
against the abstract interface, so the engine cannot tell the two apart, and
``require_durable=True`` in :class:`ContextEngine` now refuses to run against memory --
which is the point: a caller that demands durability and quietly receives a dict loses
the investigation at restart instead of at write time.

Two wirings, one implementation
------------------------------
``__init__`` takes either a fixed ``connection`` (batch and test code, which owns the
lifetime) or a ``connection_factory`` (the API, which needs one connection per operation
so a request-scoped engine pins nothing between requests).

An earlier version subclassed this class to swap the connection strategy. That does not
work and failed loudly: every method here reads ``self._db``, so a subclass without one
raised ``AttributeError`` at the first query and the traceback pointed at a missing method
rather than at the inheritance mistake. One implementation with two wirings is the
correct shape.

Design
------
Contexts, obligations, actions and memory are stored as their own ``to_dict`` payload in
JSONB, keyed by their content-addressed id. Revisions are append-only with a unique
``(context_id, revision_number)``, which is what makes "the current revision" a query
rather than a field someone has to remember to update. Nothing here re-decides domain
semantics: the engine still computes, this only remembers.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from domain.investigation_context import ContextRevision, InvestigationContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from context_engine.obligations import (
    ActionMemoryEntry,
    ContextFrontier,
    ResearchAction,
    ResearchObligation,
)
from context_engine.store import ContextStore, StoreDurability

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS investigation_contexts (
        context_id       TEXT PRIMARY KEY,
        tenant_id        TEXT NOT NULL,
        investigation_id TEXT NOT NULL,
        identity_schema  TEXT NOT NULL,
        payload          JSONB NOT NULL,
        created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_contexts_tenant
        ON investigation_contexts (tenant_id, investigation_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS context_revisions (
        context_id      TEXT NOT NULL,
        revision_number INTEGER NOT NULL,
        payload         JSONB NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (context_id, revision_number)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_obligations (
        obligation_id TEXT PRIMARY KEY,
        context_id    TEXT NOT NULL,
        tenant_id     TEXT NOT NULL,
        payload       JSONB NOT NULL,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_obligations_context
        ON research_obligations (context_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS research_actions (
        action_id     TEXT PRIMARY KEY,
        obligation_id TEXT NOT NULL,
        tenant_id     TEXT NOT NULL,
        payload       JSONB NOT NULL,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_actions_obligation
        ON research_actions (obligation_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS context_frontiers (
        context_id TEXT PRIMARY KEY,
        tenant_id  TEXT NOT NULL,
        payload    JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS context_action_memory (
        memory_id     TEXT PRIMARY KEY,
        obligation_id TEXT NOT NULL,
        tenant_id     TEXT NOT NULL,
        payload       JSONB NOT NULL,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    # An earlier revision of this store named the column ``context_id`` and had nothing
    # to put in it: ``ActionMemoryEntry`` carries no context, and the engine buckets
    # memory by obligation (``memory_for(obligation_id)``). Renaming is a guess-free fix;
    # the guard keeps it idempotent for databases created by the old code.
    """
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'context_action_memory' AND column_name = 'context_id'
        ) THEN
            ALTER TABLE context_action_memory RENAME COLUMN context_id TO obligation_id;
        END IF;
    END $$
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_memory_obligation
        ON context_action_memory (obligation_id)
    """,
)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _decode_json_columns(row: dict[str, Any]) -> dict[str, Any]:
    """Turn JSON columns that arrived as text back into Python objects.

    ``asyncpg`` decodes ``jsonb`` only in the simple query protocol. The moment a
    statement carries a parameter it goes through the extended protocol, where the
    result is returned as ``str`` regardless of ``set_type_codec`` -- verified against
    ``set_type_codec`` by type name and by OID, with and without ``format``. That
    surfaced as ``AttributeError: 'str' object has no attribute 'get'`` inside the first
    domain ``from_dict`` it reached, which reads as a domain bug and is not one.

    Normalising here keeps one code path for both drivers: SQLAlchemy already decodes
    ``jsonb``, so this is a no-op there, and it cannot misfire on our own rows because
    every JSON column in this schema is written by :func:`_json` and is therefore valid
    JSON text on the way back out.
    """
    for key, value in row.items():
        if not isinstance(value, str):
            continue
        head = value.lstrip()[:1]
        if head not in ("{", "["):
            continue
        try:
            row[key] = json.loads(value)
        except (TypeError, ValueError):
            # Not JSON after all -- a plain text column that happens to start with a brace.
            continue
    return row


def _unwrap(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the ``payload`` column, not the row that carries it.

    Every read here selects ``payload`` and hands the result straight to a
    ``from_dict``. Returning the whole row passed ``{"payload": {...}}`` where the domain
    object wanted the payload itself, and it surfaced as a ``KeyError`` for the first
    identity field -- a long way from the actual mistake.
    """
    if row is None:
        return None
    if "payload" in row:
        payload = row["payload"]
        return dict(payload) if isinstance(payload, Mapping) else payload
    return row


class _FixedSession:
    """Re-enter a connection the caller owns. Yields it; closes nothing."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._conn = connection

    async def __aenter__(self) -> Any:
        return self._conn

    async def __aexit__(self, *exc: object) -> None:
        return None


class _FactorySession:
    """Open a connection for one operation, then close it.

    Two factory shapes are accepted, because callers reasonably provide either one:
    ``asyncpg.connect(dsn)`` -- a coroutine -- or an async context manager, as
    ``sqlalchemy.ext.asyncio`` and psycopg produce. The former must be awaited and
    then wrapped, because awaiting a coroutine yields a bare connection with no
    ``__aenter__`` to drive, which is the failure this shape check exists to prevent.
    """

    def __init__(self, factory: Any) -> None:
        self._factory = factory
        self._conn: Any = None
        self._cm: Any = None

    async def __aenter__(self) -> Any:
        produced = self._factory()
        if hasattr(produced, "__aenter__"):
            self._cm = produced
            self._conn = await produced.__aenter__()
        else:
            # A coroutine or awaitable: connect, then drive its lifecycle manually.
            self._conn = await produced
        return self._conn

    async def __aexit__(self, *exc: object) -> None:
        try:
            if self._cm is not None:
                await self._cm.__aexit__(*exc)
            elif self._conn is not None:
                close = getattr(self._conn, "close", None)
                if close is not None:
                    result = close()
                    if hasattr(result, "__await__"):
                        await result
        finally:
            self._conn = None
            self._cm = None


class PostgresContextStore(ContextStore):
    """The durable store. Async, because the engine is async and every read here is on
    the request path."""

    def __init__(
        self,
        connection: AsyncConnection | None = None,
        *,
        tenant_id: str = "",
        connection_factory: Any = None,
    ) -> None:
        if connection is None and connection_factory is None:
            raise ValueError("PostgresContextStore needs a connection or a factory")
        self._db = connection
        self._factory = connection_factory
        self._tenant_id = tenant_id
        self._ready = False

    # -- plumbing -----------------------------------------------------------

    def _session(self) -> Any:
        if self._db is not None:
            return _FixedSession(self._db)
        return _FactorySession(self._factory)

    def durability(self) -> StoreDurability:
        return StoreDurability.DURABLE

    async def ensure_schema(self) -> None:
        """Idempotent, so a concurrent first run does not become a duplicate-table
        error."""
        if self._ready:
            return
        async with self._session() as conn:
            for statement in _DDL:
                await self._exec(conn, statement, None)
        self._ready = True

    @staticmethod
    def _to_positional(sql: str, params: Mapping[str, Any]) -> tuple[str, list[Any]]:
        """Rewrite ``:name`` placeholders as ``$n`` for a positional-parameter driver.

        The store's SQL is written in the named style, which reads the same on either
        driver. ``asyncpg`` speaks ``$1`` exclusively, so the translation happens here
        rather than in every statement -- a mechanical rewrite in 40 places would drift.

        The pattern refuses a leading ``::``, because a PostgreSQL cast is not a
        placeholder: ``SELECT $1::jsonb`` must survive intact, and a naive ``:name``
        pattern turns it into ``$1:$1``.
        """
        ordered: list[Any] = []
        mapping: dict[str, int] = {}

        def _substitute(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in mapping:
                mapping[name] = len(ordered) + 1
                ordered.append(params.get(name))
            return f"${mapping[name]}"

        rewritten = re.sub(r"(?<![:\w]):([A-Za-z_][A-Za-z0-9_]*)", _substitute, sql)
        return rewritten, ordered

    @classmethod
    async def _exec(cls, conn: Any, sql: str, params: Mapping[str, Any] | None) -> Any:
        """Execute against whichever driver the session holds.

        The store is documented as pluggable (Constitution V), and the two supported
        drivers disagree on both the statement type and the parameter style: SQLAlchemy
        async drivers want a ``TextClause`` with ``:name`` parameters, while ``asyncpg``
        wants a plain ``str`` with ``$n`` parameters.

        The driver is detected *before* executing, not by catching ``TypeError``: by the
        time that error surfaces the statement has already reached the protocol, and a
        retry on the same connection fails on a closed socket rather than the real
        mismatch.
        """
        bound = dict(params or {})
        if type(conn).__module__.startswith("asyncpg"):
            if not bound:
                return await conn.execute(sql)
            statement, positional = cls._to_positional(sql, bound)
            return await conn.execute(statement, *positional)
        clause = text(sql)
        return await conn.execute(clause, bound) if bound else await conn.execute(clause)

    @staticmethod
    def _rows(result: Any) -> list[dict[str, Any]]:
        """Normalise a driver result into plain dicts.

        ``asyncpg`` returns a ``Record`` list, SQLAlchemy returns a buffered result
        with ``.mappings()``. Both are reduced here so the read paths stay identical.
        """
        if hasattr(result, "mappings"):
            return [dict(row) for row in result.mappings()]
        return [dict(row) for row in result]

    @classmethod
    async def _fetch(cls, conn: Any, sql: str, params: Mapping[str, Any] | None) -> list[dict[str, Any]]:
        """Run a query and return its rows, whichever driver is in play.

        Reads cannot reuse ``_exec``: ``asyncpg.Connection.execute`` is for statements
        and returns a status string such as ``"SELECT 3"`` for a SELECT, so iterating
        that result yields characters, not records. ``asyncpg`` has a separate ``fetch``
        for exactly this; SQLAlchemy funnels reads and writes through one ``execute``.
        """
        bound = dict(params or {})
        if type(conn).__module__.startswith("asyncpg"):
            if not bound:
                records = await conn.fetch(sql)
            else:
                statement, positional = cls._to_positional(sql, bound)
                records = await conn.fetch(statement, *positional)
            return [_decode_json_columns(dict(record)) for record in records]
        clause = text(sql)
        result = await conn.execute(clause, bound) if bound else await conn.execute(clause)
        return [_decode_json_columns(row) for row in cls._rows(result)]

    async def _one(self, sql: str, params: Mapping[str, Any]) -> dict[str, Any] | None:
        async with self._session() as conn:
            rows = await self._fetch(conn, sql, params)
        return rows[0] if rows else None

    async def _first(self, sql: str, params: Mapping[str, Any]) -> dict[str, Any] | None:
        return _unwrap(await self._one(sql, params))

    async def _all(self, sql: str, params: Mapping[str, Any]) -> list[dict[str, Any]]:
        async with self._session() as conn:
            return [_unwrap(row) for row in await self._fetch(conn, sql, params)]

    async def _write(self, sql: str, params: Mapping[str, Any]) -> None:
        """Execute and commit.

        The commit belongs inside the session scope. Left outside it, it referenced
        ``self._db``, which does not exist when the store is wired by factory -- and the
        failure appeared at commit time, far from the missing connection.

        ``_commit`` is driver-aware for the same reason ``_exec`` is: ``asyncpg`` has no
        ``commit`` (it commits per statement), while a SQLAlchemy session needs one or
        the write is invisible to the next connection.
        """
        async with self._session() as conn:
            await self._exec(conn, sql, params)
            await self._commit(conn)

    @staticmethod
    async def _commit(conn: Any) -> None:
        """Commit only where the driver has transactions to close."""
        commit = getattr(conn, "commit", None)
        if commit is None:
            return
        result = commit()
        if hasattr(result, "__await__"):
            await result

    # -- contexts -----------------------------------------------------------

    async def put_context(self, context: InvestigationContext) -> None:
        await self.ensure_schema()
        await self._write(
            """
            INSERT INTO investigation_contexts
                (context_id, tenant_id, investigation_id, identity_schema, payload)
            VALUES (:cid, :tenant, :inv, :schema, CAST(:payload AS jsonb))
            ON CONFLICT (context_id) DO UPDATE SET payload = EXCLUDED.payload
            """,
            {
                "cid": context.context_id,
                "tenant": context.tenant_id or self._tenant_id,
                "inv": context.investigation_id,
                "schema": context.identity_schema,
                "payload": _json(context.to_dict()),
            },
        )

    async def get_context(self, context_id: str) -> InvestigationContext | None:
        await self.ensure_schema()
        row = await self._first(
            "SELECT payload FROM investigation_contexts WHERE context_id = :cid",
            {"cid": context_id},
        )
        return InvestigationContext.from_dict(row) if row else None

    async def contexts(self) -> tuple[InvestigationContext, ...]:
        await self.ensure_schema()
        rows = await self._all(
            "SELECT payload FROM investigation_contexts"
            + (" WHERE tenant_id = :tenant" if self._tenant_id else "")
            + " ORDER BY created_at",
            {"tenant": self._tenant_id},
        )
        return tuple(InvestigationContext.from_dict(r) for r in rows)

    # -- revisions (append-only) --------------------------------------------

    async def append_revision(self, revision: ContextRevision) -> None:
        await self.ensure_schema()
        await self._write(
            """
            INSERT INTO context_revisions (context_id, revision_number, payload)
            VALUES (:cid, :n, CAST(:payload AS jsonb))
            ON CONFLICT (context_id, revision_number) DO NOTHING
            """,
            {
                "cid": revision.context_id,
                "n": int(revision.revision),
                "payload": _json(revision.to_dict()),
            },
        )

    async def revisions(self, context_id: str) -> tuple[ContextRevision, ...]:
        await self.ensure_schema()
        rows = await self._all(
            "SELECT payload FROM context_revisions WHERE context_id = :cid ORDER BY revision_number",
            {"cid": context_id},
        )
        return tuple(ContextRevision.from_dict(r) for r in rows)

    async def current_revision(self, context_id: str) -> ContextRevision | None:
        rows = await self.revisions(context_id)
        return rows[-1] if rows else None

    async def next_revision_number(self, context_id: str) -> int:
        await self.ensure_schema()
        row = await self._one(
            "SELECT COALESCE(MAX(revision_number), 0) + 1 AS nxt "
            "FROM context_revisions WHERE context_id = :cid",
            {"cid": context_id},
        )
        return int(row["nxt"]) if row else 1

    # -- obligations --------------------------------------------------------

    async def put_obligation(self, obligation: ResearchObligation) -> None:
        await self.ensure_schema()
        await self._write(
            """
            INSERT INTO research_obligations
                (obligation_id, context_id, tenant_id, payload)
            VALUES (:oid, :cid, :tenant, CAST(:payload AS jsonb))
            ON CONFLICT (obligation_id) DO UPDATE SET payload = EXCLUDED.payload
            """,
            {
                "oid": obligation.obligation_id,
                "cid": obligation.context_id,
                # ResearchObligation carries no tenant of its own -- tenancy belongs to the
                # store, which is already bound to one.
                "tenant": self._tenant_id,
                "payload": _json(obligation.to_dict()),
            },
        )

    async def get_obligation(self, obligation_id: str) -> ResearchObligation | None:
        await self.ensure_schema()
        row = await self._first(
            "SELECT payload FROM research_obligations WHERE obligation_id = :oid",
            {"oid": obligation_id},
        )
        return ResearchObligation.from_dict(row) if row else None

    async def obligations(self, context_id: str) -> tuple[ResearchObligation, ...]:
        await self.ensure_schema()
        rows = await self._all(
            "SELECT payload FROM research_obligations WHERE context_id = :cid ORDER BY created_at",
            {"cid": context_id},
        )
        return tuple(ResearchObligation.from_dict(r) for r in rows)

    # -- actions ------------------------------------------------------------

    async def put_action(self, action: ResearchAction) -> None:
        await self.ensure_schema()
        await self._write(
            """
            INSERT INTO research_actions (action_id, obligation_id, tenant_id, payload)
            VALUES (:aid, :oid, :tenant, CAST(:payload AS jsonb))
            ON CONFLICT (action_id) DO UPDATE SET payload = EXCLUDED.payload
            """,
            {
                "aid": action.action_id,
                "oid": action.obligation_id,
                "tenant": self._tenant_id,
                "payload": _json(action.to_dict()),
            },
        )

    async def actions(self, obligation_id: str) -> tuple[ResearchAction, ...]:
        await self.ensure_schema()
        rows = await self._all(
            "SELECT payload FROM research_actions WHERE obligation_id = :oid ORDER BY created_at",
            {"oid": obligation_id},
        )
        return tuple(ResearchAction.from_dict(r) for r in rows)

    # -- action memory ------------------------------------------------------

    async def remember(self, entry: ActionMemoryEntry) -> None:
        await self.ensure_schema()
        payload = _json(entry.to_dict() if hasattr(entry, "to_dict") else dict(entry))
        await self._write(
            """
            INSERT INTO context_action_memory (memory_id, obligation_id, tenant_id, payload)
            VALUES (:mid, :oid, :tenant, CAST(:payload AS jsonb))
            ON CONFLICT (memory_id) DO UPDATE SET payload = EXCLUDED.payload
            """,
            {
                "mid": entry.entry_id,
                "oid": entry.obligation_id,
                "tenant": self._tenant_id,
                "payload": payload,
            },
        )

    async def memory_for(self, context_id: str) -> tuple[ActionMemoryEntry, ...]:
        """Keyed by obligation id, matching the contract's ``memory_for(obligation_id)``.

        The parameter is named ``context_id`` because the abstract interface says so; the
        in-memory store buckets on ``entry.obligation_id``, and this one follows it.
        """
        await self.ensure_schema()
        rows = await self._all(
            "SELECT payload FROM context_action_memory WHERE obligation_id = :oid ORDER BY created_at",
            {"oid": context_id},
        )
        return tuple(ActionMemoryEntry.from_dict(r) for r in rows)

    # -- frontier -----------------------------------------------------------

    async def put_frontier(self, frontier: ContextFrontier) -> None:
        await self.ensure_schema()
        await self._write(
            """
            INSERT INTO context_frontiers (context_id, tenant_id, payload)
            VALUES (:cid, :tenant, CAST(:payload AS jsonb))
            ON CONFLICT (context_id) DO UPDATE SET payload = EXCLUDED.payload
            """,
            {
                "cid": frontier.context_id,
                "tenant": self._tenant_id,
                "payload": _json(frontier.to_dict()),
            },
        )

    async def get_frontier(self, context_id: str) -> ContextFrontier | None:
        await self.ensure_schema()
        row = await self._first(
            "SELECT payload FROM context_frontiers WHERE context_id = :cid",
            {"cid": context_id},
        )
        return ContextFrontier.from_dict(row) if row else None

    async def observation_entity_rows(
        self, tenant_id: str, *, limit: int = 5_000
    ) -> list[dict[str, Any]]:
        """Observation/entity/type triples for one tenant, from the durable stream.

        This is what a scope lattice is computed over. The join is on
        ``(tenant_id, entity_id)`` because ``entity_stream`` and ``entities`` are separately
        tenant-scoped and an inner join across them without the tenant predicate would attach
        another tenant's type to this tenant's observation -- a cross-tenant leak that looks
        like a correct result.

        Returns only rows whose observation actually carries a stream entry. An observation
        with no entity has no lattice position, and inventing one by left-joining would let
        the lattice claim coverage it does not have.
        """
        await self.ensure_schema()
        return await self._all(
            "SELECT es.observation_id AS observation_ref, "
            "       es.entity_id AS entity_ref, "
            "       COALESCE(e.entity_type, 'unknown') AS entity_type "
            "FROM entity_stream es "
            "JOIN entities e "
            "  ON e.entity_id = es.entity_id AND e.tenant_id = es.tenant_id "
            "WHERE es.tenant_id = :tenant "
            "  AND es.observation_id IS NOT NULL "
            "ORDER BY es.observation_id, es.entity_id "
            "LIMIT :limit",
            {"tenant": str(tenant_id), "limit": int(limit)},
        )


__all__ = ["PostgresContextStore", "StoreDurability"]