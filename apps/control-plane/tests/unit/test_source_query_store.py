"""Persistence contract tests for the multi-route source query store (US2)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_APPS = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_APPS / "shared"))
sys.path.insert(0, str(_APPS))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from acquisition.entity_search import build_entity_search_surface
from acquisition.source_query_set import build_source_query_set

from db.schema import SourceQuery as SourceQueryRow
from db.schema import SourceQuerySet as SourceQuerySetRow
from db.source_query_store import SqlSourceQueryStore, surface_digest

IDENTITY = {
    "url": "https://acme.test/docs",
    "domain": "acme.test",
    "name": "Acme Corporation",
    "email": "ops@acme.test",
}

CC_ROUTE_KINDS = {
    "exact_url",
    "url_prefix",
    "domain",
    "name",
    "alias",
    "historical_name",
}


class _Result:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self) -> _Result:
        return self

    def all(self) -> list:
        return self._rows


class _Session:
    """Small SQLAlchemy-shaped store matching the repository's query shape."""

    def __init__(self) -> None:
        self.sets: list[SourceQuerySetRow] = []
        self.queries: list[SourceQueryRow] = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, row) -> None:
        if isinstance(row, SourceQuerySetRow):
            self.sets.append(row)
        else:
            self.queries.append(row)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def execute(self, statement) -> _Result:
        params = statement.compile().params
        tenant = params.get("tenant_id_1")
        entity = params.get("entity_id_1")
        # Distinguish which model the statement selects; both share scope params.
        selected = statement.column_descriptions[0]["entity"]
        if selected is SourceQuerySetRow:
            rows = [r for r in self.sets if r.tenant_id == tenant and r.entity_id == entity]
            return _Result(rows)
        rows = [r for r in self.queries if r.tenant_id == tenant and r.entity_id == entity]
        # `.is_(True/False)` compiles to a SQL literal, not a bind param, so the
        # filter is read from the rendered statement rather than from params.
        sql = str(statement.compile())
        if "executable IS true" in sql:
            rows = [r for r in rows if r.executable]
        elif "executable IS false" in sql:
            rows = [r for r in rows if not r.executable]
        return _Result(sorted(rows, key=lambda r: r.ordinal))


def _plan(identity: dict[str, str] = IDENTITY):
    surface = build_entity_search_surface("ENT-1", identity)
    return surface, build_source_query_set(entity_id="ENT-1", surface=surface)



def test_persist_writes_the_set_and_every_route() -> None:
    session, _, query_set = _persisted()

    header = session.sets[0]
    assert header.entity_id == "ENT-1"
    assert header.query_count == len(query_set.queries)
    assert header.executable_count == query_set.executable_count
    assert header.unsupported_count == query_set.unsupported_count
    assert len(session.queries) == len(query_set.queries)


def test_unsupported_routes_are_persisted_not_dropped() -> None:
    """A partially served surface must stay distinguishable (FR-004)."""
    _, store, _ = _persisted()

    unsupported = asyncio.run(store.get_unsupported(tenant_id="t-1", entity_id="ENT-1"))
    kinds = {row.route_kind for row in unsupported}
    assert "email_derived" in kinds
    for row in unsupported:
        assert row.unsupported_reason, f"{row.route_kind} stored without a reason"


def test_executable_routes_exclude_unsupported_ones() -> None:
    _, store, _ = _persisted()

    executable = asyncio.run(store.get_executable(tenant_id="t-1", entity_id="ENT-1"))
    assert executable
    assert all(row.executable for row in executable)
    assert {row.route_kind for row in executable} <= CC_ROUTE_KINDS


def test_persist_is_idempotent_for_the_same_identity() -> None:
    """Re-planning the same identity must not fork the route set."""
    session = _Session()
    surface, query_set = _plan()
    store = SqlSourceQueryStore(session)

    first = asyncio.run(store.persist(tenant_id="t-1", surface=surface, query_set=query_set))
    second = asyncio.run(store.persist(tenant_id="t-1", surface=surface, query_set=query_set))

    assert first is second
    assert len(session.sets) == 1
    assert session.commits == 1


def test_queries_are_returned_in_ordinal_order() -> None:
    _, store, query_set = _persisted()

    rows = asyncio.run(store.get_queries(tenant_id="t-1", entity_id="ENT-1"))
    assert [row.ordinal for row in rows] == sorted(row.ordinal for row in rows)
    assert [row.route_kind for row in rows] == [q.route_kind for q in query_set.queries]


def test_cross_tenant_reads_return_nothing() -> None:
    """Tenant isolation: another tenant's plan is invisible (FR-039)."""
    _, store, _ = _persisted()

    assert asyncio.run(store.get_set(tenant_id="t-2", entity_id="ENT-1")) is None
    assert asyncio.run(store.get_queries(tenant_id="t-2", entity_id="ENT-1")) == ()
    assert asyncio.run(store.get_executable(tenant_id="t-2", entity_id="ENT-1")) == ()


def test_surface_digest_is_stable_and_identity_sensitive() -> None:
    first = build_entity_search_surface("ENT-1", IDENTITY)
    second = build_entity_search_surface("ENT-1", dict(reversed(list(IDENTITY.items()))))
    third = build_entity_search_surface("ENT-1", {**IDENTITY, "domain": "other.test"})

    assert surface_digest(first) == surface_digest(second)
    assert surface_digest(first) != surface_digest(third)


def _persisted():
    session = _Session()
    surface, query_set = _plan()
    store = SqlSourceQueryStore(session)
    asyncio.run(store.persist(tenant_id="t-1", surface=surface, query_set=query_set))
    return session, store, query_set
