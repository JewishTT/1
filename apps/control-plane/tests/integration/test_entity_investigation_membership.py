"""Investigation membership is first-class on ``GET/POST /api/v1/entities``.

The defect this file exists for was measured, not suspected: the route never declared
``investigation_id``, so FastAPI dropped the query parameter and **every** investigation
received the same tenant-wide list. Five different investigations all answered with the
same five entities. Underneath the route, ``entities`` had never carried an
investigation reference, so there was nothing to filter on.

What is proved here, against a real PostgreSQL:

* two entities, one in each of two investigations, give two different lists;
* an entity created under an ``investigation_id`` is visible only under that id;
* an entity created without one belongs to no investigation but is still listed
  unscoped -- the model has always allowed that, and requirement 3 says so explicitly;
* the membership is a row, not a process-local note: it is written durably, it carries
  the basis it was established on, and re-establishing it collides at the primary key
  rather than growing a second identical row.

    The database is a throwaway schema, so the application's real tables are never touched.
Everything that does not need a database is in the unit-level sibling file.

``NullPool`` is not a tuning choice. Starlette's ``TestClient`` runs each request on a
fresh event loop, and an asyncpg connection is bound to the loop that opened it, so a
pooled connection handed to the second request is a connection to a loop that has been
closed -- ``RuntimeError: Event loop is closed`` from inside a query. Disabling pooling
makes every request open its own connection, which is the only arrangement that is
correct under this client.
"""


from __future__ import annotations

import asyncio
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

_APPS = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_APPS / "shared"))
sys.path.insert(0, str(_APPS / "control-plane"))

from fastapi.testclient import TestClient

from api.main import app
from api.routes import entities as entities_route

SCHEMA = "cp024_api"
TENANT = "cp024-tenant"
OTHER_TENANT = "cp024-other-tenant"

#: Only what these routes read. The rest of the schema is irrelevant here and creating
#: it would be slower and no more honest.
_TABLES = ("investigations", "entities", "investigation_entity_memberships")


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


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    """A client whose entity routes read a private schema.

    The route caches one session factory at module import, so the swap has to happen
    there rather than through a request header. Everything is restored afterwards --
    including the in-process catalog, which is genuinely global and would otherwise leak
    this file's tenants into whatever ran next.
    """
    reason = _skip_without_postgres()
    if reason:
        pytest.skip(f"{reason} -- investigation membership not exercised")

    from config.settings import get_settings
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from db.schema import Base

    dsn = get_settings().postgres.dsn
    tables = [Base.metadata.tables[name] for name in _TABLES]

    async def _prepare() -> None:
        bootstrap = create_async_engine(dsn)
        try:
            async with bootstrap.begin() as connection:
                await connection.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
                await connection.execute(text(f"CREATE SCHEMA {SCHEMA}"))
                await connection.execute(text(f"SET search_path TO {SCHEMA}"))
                for table in tables:
                    await connection.run_sync(
                        lambda sync, table=table: table.create(sync, checkfirst=False)
                    )
        finally:
            await bootstrap.dispose()

    asyncio.run(_prepare())

    engine = create_async_engine(
        dsn,
        connect_args={"server_settings": {"search_path": SCHEMA}},
        poolclass=NullPool,
    )
    previous_factory = list(entities_route._pg_factory)
    # ``getattr`` rather than a direct attribute read: the ownership map is part of the
    # fix under test, and a fixture that dies on its absence would replace the real
    # failure (the route answering unfiltered) with an unrelated error, which is the one
    # thing a red-then-green measurement must not do.
    previous_owners = dict(getattr(entities_route, "_entity_owner", {}) or {})
    previous_catalog_ids = set(entities_route._catalog.entity_ids())
    entities_route._pg_factory.clear()
    entities_route._pg_factory.append(async_sessionmaker(engine, expire_on_commit=False))

    try:
        # Deliberately NOT used as a context manager: entering it runs the application
        # lifespan, which assembles the whole platform (transport, search, storage) and
        # belongs to tests about the platform. These are route-level assertions, and the
        # rest of the suite drives the same app the same way.
        yield TestClient(app)
    finally:
        entities_route._pg_factory.clear()
        entities_route._pg_factory.extend(previous_factory)
        owners = getattr(entities_route, "_entity_owner", None)
        if owners is not None:
            owners.clear()
            owners.update(previous_owners)
        for entity_id in set(entities_route._catalog.entity_ids()) - previous_catalog_ids:
            entities_route._catalog._entities.pop(entity_id, None)
            if owners is not None:
                owners.pop(entity_id, None)
        entities_route._entity_streams.clear()


        async def _teardown() -> None:
            await engine.dispose()
            cleaner = create_async_engine(dsn)
            try:
                async with cleaner.begin() as connection:
                    await connection.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
            finally:
                await cleaner.dispose()

        asyncio.run(_teardown())


def _investigation(investigation_id: str, *, tenant_id: str = TENANT) -> None:
    """Create an investigation row directly, the way the investigations API would."""
    from sqlalchemy import text

    from db.session import make_engine

    async def _run() -> None:
        engine = make_engine()
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET search_path TO cp024_api"))
                await connection.execute(
                    text(
                        "INSERT INTO investigations "
                        "(investigation_id, name, tenant_id, state) "
                        "VALUES (:inv, :name, :tenant, 'DRAFT')"
                    ),
                    {"inv": investigation_id, "name": investigation_id, "tenant": tenant_id},
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def _membership_rows(investigation_id: str = "") -> list[dict]:
    from sqlalchemy import text

    from db.session import make_engine

    async def _run() -> list[dict]:
        engine = make_engine()
        columns = (
            "SELECT tenant_id, investigation_id, entity_id, basis, established_by "
            "FROM investigation_entity_memberships"
        )
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SET search_path TO cp024_api"))
                params: dict = {}
                statement = columns
                if investigation_id:
                    statement += " WHERE investigation_id = :inv"
                    params = {"inv": investigation_id}
                rows = (
                    await connection.execute(text(statement + " ORDER BY entity_id"), params)
                ).mappings().all()
                return [dict(row) for row in rows]
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def _create_entity(
    client: TestClient,
    label: str,
    investigation_id: str | None,
    *,
    tenant_id: str = TENANT,
) -> str:
    body: dict = {"canonical_identity": {"handle": label}}
    if investigation_id is not None:
        body["investigation_id"] = investigation_id
    response = client.post(
        "/api/v1/entities", json=body, headers={"X-Tenant-Id": tenant_id}
    )
    assert response.status_code == 202, response.text
    return response.json()["entity"]["entity_id"]


def _listed_ids(client: TestClient, investigation_id: str | None = None) -> set[str]:
    url = "/api/v1/entities"
    if investigation_id is not None:
        url = f"{url}?investigation_id={investigation_id}"
    response = client.get(url, headers={"X-Tenant-Id": TENANT})
    assert response.status_code == 200, response.text
    return {view["entity_id"] for view in response.json()["entities"]}


def _body(client: TestClient, investigation_id: str | None = None) -> dict:
    url = "/api/v1/entities"
    if investigation_id is not None:
        url = f"{url}?investigation_id={investigation_id}"
    return client.get(url, headers={"X-Tenant-Id": TENANT}).json()


@pytest.mark.integration
def test_two_investigations_return_two_different_lists(client: TestClient) -> None:
    """The measured defect, inverted: the filter separates what it used to merge."""
    _investigation("INV-A")
    _investigation("INV-B")
    in_a = _create_entity(client, "alpha", "INV-A")
    in_b = _create_entity(client, "beta", "INV-B")
    assert in_a != in_b

    listed_a = _listed_ids(client, "INV-A")
    listed_b = _listed_ids(client, "INV-B")

    assert in_a in listed_a
    assert in_a not in listed_b, "INV-B answered with INV-A's entity"
    assert in_b in listed_b
    assert in_b not in listed_a, "INV-A answered with INV-B's entity"
    assert listed_a != listed_b, "the filter collapsed both investigations into one list"


@pytest.mark.integration
def test_an_entity_created_under_an_investigation_is_visible_only_there(
    client: TestClient,
) -> None:
    """POST records the membership, and GET honours it for every other investigation."""
    _investigation("INV-ONLY")
    _investigation("INV-ELSEWHERE")
    entity_id = _create_entity(client, "solo", "INV-ONLY")

    assert entity_id in _listed_ids(client, "INV-ONLY")
    assert entity_id not in _listed_ids(client, "INV-ELSEWHERE")
    assert entity_id not in _listed_ids(client, "INV-NEVER-EXISTED")


@pytest.mark.integration
def test_without_a_filter_every_entity_of_the_tenant_is_returned(
    client: TestClient,
) -> None:
    """No filter is not an empty filter: the whole tenant, scoped by nothing."""
    _investigation("INV-ALL-A")
    _investigation("INV-ALL-B")
    first = _create_entity(client, "gamma", "INV-ALL-A")
    second = _create_entity(client, "delta", "INV-ALL-B")
    loose = _create_entity(client, "epsilon", None)

    body = _body(client)
    listed = {view["entity_id"] for view in body["entities"]}

    assert {first, second, loose} <= listed
    assert body["scoped"] is False
    assert "investigation_id" not in body
    # The unscoped set is the union of the two investigations, not either one of them.
    assert listed >= _listed_ids(client, "INV-ALL-A") | _listed_ids(client, "INV-ALL-B")


@pytest.mark.integration
def test_an_entity_created_without_an_investigation_belongs_to_none(
    client: TestClient,
) -> None:
    """The existing model permits an investigation-free entity, so POST still does.

    What it may not do is file the entity under an investigation that was not named --
    that is the bug. An entity nobody filed belongs to nobody and is still listed.
    """
    _investigation("INV-ORPHAN")
    entity_id = _create_entity(client, "floating", None)

    assert entity_id not in _listed_ids(client, "INV-ORPHAN")
    assert entity_id in _listed_ids(client)
    assert _membership_rows() == [] or all(
        row["entity_id"] != entity_id for row in _membership_rows()
    )


@pytest.mark.integration
def test_membership_is_durable_and_states_its_basis(client: TestClient) -> None:
    """A membership is a row with provenance, not a process-local association."""
    _investigation("INV-DURABLE")
    entity_id = _create_entity(client, "durable", "INV-DURABLE")

    rows = [row for row in _membership_rows("INV-DURABLE") if row["entity_id"] == entity_id]
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["tenant_id"] == TENANT
    assert row["basis"] == "EXPLICIT"
    assert row["established_by"], "a membership records who established it"


@pytest.mark.integration
def test_re_establishing_a_membership_is_idempotent_at_the_database(
    client: TestClient,
) -> None:
    """The composite primary key is the guarantee, not the request handler.

    ``ON CONFLICT DO NOTHING`` would pass a single-threaded replay even without a unique
    constraint, so the check here is that the constraint itself refuses the second row.
    """
    _investigation("INV-IDEMPOTENT")
    entity_id = _create_entity(client, "replayed", "INV-IDEMPOTENT")
    before = len(_membership_rows("INV-IDEMPOTENT"))

    from sqlalchemy import text

    from db.session import make_engine

    async def _replay() -> str:
        engine = make_engine()
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SET search_path TO cp024_api"))
                await connection.execute(
                    text(
                        "INSERT INTO investigation_entity_memberships "
                        "(tenant_id, investigation_id, entity_id, basis) "
                        "VALUES (:tenant, :inv, :entity, 'EXPLICIT')"
                    ),
                    {"tenant": TENANT, "inv": "INV-IDEMPOTENT", "entity": entity_id},
                )
                await connection.commit()
            return "inserted"
        except Exception as exc:  # noqa: BLE001 - the refusal is the assertion
            return type(exc).__name__
        finally:
            await engine.dispose()

    outcome = asyncio.run(_replay())
    assert outcome != "inserted", (
        "a second identical membership row was accepted; the composite primary key is "
        "what makes a replayed POST a no-op instead of a second row"
    )
    assert len(_membership_rows("INV-IDEMPOTENT")) == before


@pytest.mark.integration
def test_creating_under_an_investigation_that_does_not_exist_is_refused(
    client: TestClient,
) -> None:
    """Fail closed: a membership naming nothing is a lie a scoped read would repeat."""
    response = client.post(
        "/api/v1/entities",
        json={"canonical_identity": {"handle": "nowhere"}, "investigation_id": "INV-GHOST"},
        headers={"X-Tenant-Id": TENANT},
    )
    assert response.status_code == 404, response.text
    assert all(row["investigation_id"] != "INV-GHOST" for row in _membership_rows())


@pytest.mark.integration
def test_another_tenants_entities_are_never_listed(client: TestClient) -> None:
    """Membership is tenant-scoped; a cross-tenant id is a different entity.

    Both the catalog and the durable registry are filtered by tenant, and so is the
    membership read -- an investigation id that names one tenant's investigation is not
    a way to read another tenant's entity list.
    """
    _investigation("INV-TENANT-SCOPED", tenant_id=OTHER_TENANT)
    theirs = _create_entity(
        client, "theirs", "INV-TENANT-SCOPED", tenant_id=OTHER_TENANT
    )

    mine = _listed_ids(client)
    theirs_view = client.get(
        "/api/v1/entities?investigation_id=INV-TENANT-SCOPED",
        headers={"X-Tenant-Id": OTHER_TENANT},
    )
    assert theirs_view.status_code == 200, theirs_view.text
    assert theirs in {view["entity_id"] for view in theirs_view.json()["entities"]}

    assert theirs not in mine, "another tenant's entity reached this tenant's list"
    assert theirs not in _listed_ids(client, "INV-TENANT-SCOPED")


@pytest.mark.integration
def test_a_membership_without_an_entity_row_is_reported_not_hidden(
    client: TestClient,
) -> None:
    """An id can be a member before anything can render a view for it.

    The membership is written by a different process from the entity row and the table
    carries no foreign key for exactly that reason. Reporting such a member as though
    the investigation held nothing would be the same class of lie as returning
    everything.
    """
    _investigation("INV-ORPHAN-MEMBER")
    from sqlalchemy import text

    from db.session import make_engine

    async def _record() -> None:
        engine = make_engine()
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET search_path TO cp024_api"))
                await connection.execute(
                    text(
                        "INSERT INTO investigation_entity_memberships "
                        "(tenant_id, investigation_id, entity_id, basis) "
                        "VALUES (:tenant, 'INV-ORPHAN-MEMBER', 'ENT-NEVER-MATERIALISED', "
                        "'RELATION_DERIVED')"
                    ),
                    {"tenant": TENANT},
                )
        finally:
            await engine.dispose()

    asyncio.run(_record())

    body = _body(client, "INV-ORPHAN-MEMBER")
    assert "ENT-NEVER-MATERIALISED" in {view["entity_id"] for view in body["entities"]}
    assert body.get("unresolved_memberships") == ["ENT-NEVER-MATERIALISED"]
    assert body.get("note"), "an unresolved member must say so rather than render bare"
