"""FR-007 survives the bridge from Layer A discovery to the durable frontier.

The provenance a discovery pass accumulates -- which source found the URL, under
which method, for which query, and which other sources had already seen it -- is
only useful if it is still attached to the frontier item weeks later, when
somebody asks why this URL was ever fetched. That is FR-007, and the failure mode
is specific: everything works, the report says ``enqueued: 3``, and the
provenance is gone, because the dict was carried in memory and the durable row
had nowhere to put it. A requirement satisfied in the adapter and lost at the
boundary is not a requirement.

So this suite has two tiers.

**Offline, always runs.** The adapter is driven against a recording session that
captures the statement it would execute, and the assertions are about the
*emitted DDL*: the frontier's single INSERT names ``provenance`` and none of the
five scheduling fields come from the caller; the conflict target is
``(tenant_id, uri)``; the full provenance dict is bound, nested lists and all;
``priority`` is widened to float rather than truncated; ``uri`` is the canonical
form. These are the properties that make the boundary loss impossible, and they
are checkable without a database.

**Live, requires PostgreSQL.** The same enqueue, executed for real, and the row
read back out of ``frontier_items``: ``provenance["method"]``, ``["query"]`` and
``["seen_by"]`` all present, a second enqueue of the same canonical URL creating
no second row, ``state == "READY"`` with ``next_schedule_at``/``lease_until``
still NULL and ``retries`` still 0. Each test skips with a stated reason when no
server answers, so an absent proof reads as absent rather than as a failure.

The adapter takes a session factory and builds a ``PgFrontier`` over it rather
than holding a frontier service, because the whole Layer A pass is synchronous
and the adapter -- not the caller -- absorbs the asynchrony; the argument is in
``services/discovery_frontier.py``. It writes no SQL of its own: the INSERT it
produces is ``PgFrontier.enqueue``'s, and the tests below assert that there is
exactly one of them and that it lives in ``services/frontier.py``.

A third section covers ``LinkEdgeProvider``, the other production binding in that
module. It is here rather than in a file of its own because this is the only
owned test file that can import the module, and the property it protects -- an
edge without a named originating observation never leaves the provider -- is the
same evidence-first rule the rest of this suite is about.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import sys
import threading
import tokenize
from pathlib import Path
from typing import Any, Self

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

APP_DIR = Path(__file__).resolve().parents[2]
ADAPTER_MODULE = APP_DIR / "services" / "discovery_frontier.py"
FRONTIER_MODULE = APP_DIR / "services" / "frontier.py"

from adapters.discovery import Candidate, DiscoveryRegistry

from services.discovery_frontier import (
    FrontierSinkAdapter,
    LinkEdgeProvider,
    canonical_host,
)

TABLE = "frontier_items"
PROVENANCE_COLUMN = "provenance"
SCHEDULE_KEY_INDEX = "uq_frontier_schedule"

# The columns the frontier's INSERT takes from the item it is handed: what
# discovery owns, plus ``partition`` for the per-region dispatchers (T119).
# Everything else on the row belongs to frontier policy (ADR-0016/0017) and must
# not appear among them.
FRONTIER_INSERT_COLUMNS = frozenset(
    {
        "frontier_id",
        "tenant_id",
        "investigation_id",
        "source_id",
        "uri",
        "host_key",
        "partition",
        "priority",
        PROVENANCE_COLUMN,
    }
)

# Frontier policy. Listed so the failure has a name: an INSERT that lets a caller
# choose any of these has made discovery a second scheduler whose rules nobody
# can find.
FORBIDDEN_IN_INSERT = frozenset({"state", "retries", "lease_until", "next_schedule_at"})

# Exactly what ``DiscoveryRegistry.discover`` builds for one coalesced candidate:
# the source's own provenance plus the ``seen_by``/``sources`` lists ``coalesce``
# accumulated, plus the ``discovery`` block the registry stamps on before enqueue.
FULL_PROVENANCE: dict[str, Any] = {
    "method": "index-query",
    "source": "cc-index",
    "query": "example.org",
    "seen_by": [
        {"source": "ct-log", "method": "ct-log"},
        {"source": "wayback-cdx", "method": "cdx"},
    ],
    "sources": ["cc-index", "ct-log", "wayback-cdx"],
    "confidence": 0.72,
    "provider": "graph-projection",
    "from_uri": "https://example.org/hub",
    "edge_type": "link",
    "discovery": {
        "source": "cc-index",
        "method": "index-query",
        "query": "example.org",
    },
}


# ---------------------------------------------------------------------------
# Recording session: what the adapter would actually execute
# ---------------------------------------------------------------------------


class _RecordingResult:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class _RecordingSession:
    """Captures the statements the adapter executes. Executes nothing.

    ``rowcount`` is the value the driver reports for the INSERT, so the dedup
    path (0) and the create path (1) are both reachable without a unique index.
    ``raises`` models a driver error on the *first* statement only: a real driver
    reports one error per statement it is handed, and the adapter is expected to
    carry on and issue its follow-up.
    """

    def __init__(self, *, rowcount: int = 1, raises: Exception | None = None) -> None:
        self._rowcount = rowcount
        self._raises = raises
        self.statements: list[Any] = []
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def execute(self, statement: Any) -> _RecordingResult:
        self.statements.append(statement)
        if self._raises is not None and len(self.statements) == 1:
            raise self._raises
        return _RecordingResult(self._rowcount)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def _integrity_error(sqlstate: str, constraint: str) -> IntegrityError:
    """A driver-level error shaped the way asyncpg shapes one."""

    class _DriverError(Exception):
        def __init__(self) -> None:
            super().__init__(
                f'duplicate key value violates unique constraint "{constraint}"'
                if sqlstate == "23505"
                else f'null value in column "{constraint}" violates not-null constraint'
            )
            self.sqlstate = sqlstate
            self.pgcode = sqlstate

    return IntegrityError("INSERT", {}, _DriverError())


def _adapter_for(session: _RecordingSession, **kwargs: Any) -> FrontierSinkAdapter:
    options: dict[str, Any] = {"host_key_of": canonical_host}
    options.update(kwargs)
    return FrontierSinkAdapter(lambda: session, **options)


def _insert_params(statement: Any) -> dict[str, Any]:
    return dict(statement.compile(dialect=postgresql.dialect()).params)


def _insert(statement: Any) -> Any:
    return str(statement.compile(dialect=postgresql.dialect()))


def _enqueue(adapter: FrontierSinkAdapter, **overrides: Any) -> None:
    kwargs: dict[str, Any] = {
        "uri": "HTTPS://Example.ORG:443/reports/?q=1#top",
        "tenant_id": "tenant-a",
        "investigation_id": "inv-1",
        "source": "cc-index",
        "method": "index-query",
        "priority": 7,
        "provenance": dict(FULL_PROVENANCE),
    }
    kwargs.update(overrides)
    adapter.enqueue(**kwargs)


# ---------------------------------------------------------------------------
# Tier 1 -- offline: the emitted statement
# ---------------------------------------------------------------------------


def _provenance_inserts(module: Path) -> list[dict[str, ast.expr]]:
    """Every ``values(...)`` in ``module`` that binds a provenance document.

    Returned as ``column -> value expression``, because the value is the part that
    answers "did the caller choose this, or did the frontier?".
    """
    tree = ast.parse(module.read_text(encoding="utf-8"))
    return [
        {keyword.arg: keyword.value for keyword in node.keywords if keyword.arg}
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "values"
        and any(keyword.arg == PROVENANCE_COLUMN for keyword in node.keywords)
    ]


def _read_off_the_item(value: ast.expr, root: str = "item") -> bool:
    """Whether the expression takes its value from the caller's item.

    Looks for the name anywhere in the expression rather than for a bare
    ``item.<field>``, because the frontier writes ``item.provenance or {}`` and
    ``item.partition or "global"``: both are the caller's value with a default
    beside it, and a check that only understood the bare attribute form would
    report a caller-supplied column as the frontier's own.
    """
    return any(isinstance(node, ast.Name) and node.id == root for node in ast.walk(value))


def test_exactly_one_write_path_exists_and_it_is_the_frontiers() -> None:
    """One INSERT for the whole tree, and the adapter is not it (SC-012).

    The adapter used to carry its own INSERT because the frontier's had no
    ``provenance`` column. That fixed the boundary loss and created a second
    authority over ``frontier_items``: two statements that could drift, each with
    its own dedup rule. The claim under test is the structural one -- there is one
    ``INSERT`` that binds provenance in the whole write path, it is
    ``PgFrontier.enqueue``'s, and the adapter holds no statement of its own.

    A return to the forked shape fails twice over: the adapter's INSERT comes
    back, and the count stops being one.
    """
    adapter_inserts = _provenance_inserts(ADAPTER_MODULE)
    frontier_inserts = _provenance_inserts(FRONTIER_MODULE)
    assert adapter_inserts == [], (
        "the adapter builds its own INSERT; the frontier is the only writer of "
        "frontier_items, and a second INSERT is the second authority SC-012 forbids"
    )
    assert len(frontier_inserts) == 1, (
        f"expected one frontier INSERT, found {len(frontier_inserts)}"
    )
    insert = frontier_inserts[0]
    assert PROVENANCE_COLUMN in insert, (
        "PgFrontier.enqueue's INSERT must bind provenance; without it every "
        "delegating producer's provenance is dropped at the boundary (FR-007)"
    )
    # The scheduling columns may be *named* -- the frontier has to write them --
    # but never read off the item, so a caller cannot schedule by setting them.
    # A producer that is handed a FrontierItem and asks for state='DONE' gets
    # the frontier's 'READY' (ADR-0016/0017).
    assert not (FORBIDDEN_IN_INSERT & {k for k, v in insert.items() if _read_off_the_item(v)}), (
        "the frontier INSERT reads "
        f"{sorted(FORBIDDEN_IN_INSERT & {k for k, v in insert.items() if _read_off_the_item(v)})} "
        "from the caller's item; deferral, lease, retry and recrawl cadence are "
        "frontier policy and must be the frontier's own values"
    )
    from_item = {column for column, value in insert.items() if _read_off_the_item(value)}
    assert from_item == FRONTIER_INSERT_COLUMNS, (
        f"the frontier INSERT takes {sorted(from_item)} from the item; it may take "
        f"{sorted(FRONTIER_INSERT_COLUMNS)}"
    )


def test_adapter_never_assigns_a_scheduling_field_anywhere() -> None:

    """No ``state=``/``retries=``/``lease_until=``/``next_schedule_at=`` in code.

    Belt and braces over the call-site check: a refactor that moved the insert
    into a helper would pass the previous test and fail this one. Scanned over
    tokenised source with strings and comments removed, so the prose in the
    docstrings -- which *has* to name these fields to explain why it omits them
    -- cannot be mistaken for an assignment.
    """
    code: list[str] = []
    with tokenize.open(ADAPTER_MODULE) as handle:
        for token in tokenize.generate_tokens(handle.readline):
            if token.type in (tokenize.STRING, tokenize.COMMENT):
                continue
            code.append(token.string)
    joined = " ".join(code)
    for name in ("state=", "retries=", "lease_until=", "next_schedule_at="):
        assert name not in joined, f"adapter assigns {name} somewhere in its code"


def test_uri_is_canonicalised_before_it_is_used_as_the_dedup_key() -> None:
    """The canonical URL is the ``uri``, so dedup is by canonical URL (FR-006).

    The caller hands over an upper-cased URL with a default port and a fragment.
    An adapter that stored it verbatim would key the frontier on a string no
    other component produces, and the same page would acquire a second row the
    moment any other enqueue path canonicalised.
    """
    session = _RecordingSession()
    _enqueue(_adapter_for(session))
    assert _insert_params(session.statements[0])["uri"] == "https://example.org/reports/?q=1"
    assert _insert(session.statements[0]).startswith("INSERT INTO frontier_items")


def test_dedup_key_is_tenant_and_uri() -> None:
    """``ON CONFLICT (tenant_id, uri) DO NOTHING`` -- the existing unique index."""
    session = _RecordingSession()
    _enqueue(_adapter_for(session))
    sql = _insert(session.statements[0]).upper()
    assert "ON CONFLICT" in sql and "DO NOTHING" in sql
    # The conflict target is inferred onto the table's own columns by the
    # statement object, not spelled out in free text, so it is asserted there --
    # where a change to the target would actually have to be made.
    on_conflict = session.statements[0]._post_values_clause
    assert on_conflict is not None
    assert list(on_conflict.inferred_target_elements) == ["tenant_id", "uri"]
    assert on_conflict.constraint_target is None, (
        "the conflict target is the unique index's columns, not a named constraint; "
        "naming one would duplicate uq_frontier_schedule in the statement"
    )


def test_priority_is_widened_to_float_without_truncation_or_clamping() -> None:
    """int -> float, exactly, across the range the protocol can express."""
    for value in (0, 1, 7, -3, 2**53, -(2**53)):
        session = _RecordingSession()
        _enqueue(_adapter_for(session), priority=value)
        bound = _insert_params(session.statements[0])["priority"]
        assert isinstance(bound, float), f"priority {value} bound as {type(bound).__name__}"
        assert bound == float(value) == value, f"priority {value} was clamped or truncated to {bound}"


def test_priority_beyond_the_exactly_representable_range_rounds_rather_than_wrapping() -> None:
    """``priority`` is ``float8``; the loss is recorded, not hidden.

    An int above 2**53 has no exact float8 form, so the widening rounds. The
    alternative -- leaving the column a string, or raising on a large int -- would
    either break the frontier's ordering queries or turn a caller's legitimate
    priority into an exception, so the round is accepted and pinned here. What
    must never happen is a wrap to a *negative* priority, which would silently
    move the item to the back of the queue.
    """
    session = _RecordingSession()
    _enqueue(_adapter_for(session), priority=2**53 + 1)
    bound = _insert_params(session.statements[0])["priority"]
    assert bound == float(2**53 + 1) == 9007199254740992.0
    assert bound > 0, f"{bound} must not wrap to a negative priority"


def test_host_key_comes_from_the_injected_callable_with_the_canonical_url() -> None:
    """The seam receives the canonical URL and its answer is used verbatim."""
    seen: list[str] = []

    def host_key_of(uri: str) -> str:
        seen.append(uri)
        return f"budget:{uri}"

    session = _RecordingSession()
    _enqueue(_adapter_for(session, host_key_of=host_key_of))
    assert seen == ["https://example.org/reports/?q=1"]
    assert _insert_params(session.statements[0])["host_key"] == "budget:https://example.org/reports/?q=1"


def test_full_provenance_is_bound_verbatim() -> None:
    """Nothing is filtered out of the provenance dict (FR-007).

    A whitelist at this boundary is the exact failure FR-007 is written against:
    the adapter would look correct, the report would look correct, and the
    ``seen_by`` entries that let a second source corroborate a first would be
    gone. The comparison is on the whole dict, not on the three keys the spec
    names, so a future key added upstream arrives here too.
    """
    session = _RecordingSession()
    _enqueue(_adapter_for(session))
    bound = _insert_params(session.statements[0])[PROVENANCE_COLUMN]
    assert bound == FULL_PROVENANCE, (
        f"provenance was altered at the bridge: {bound} != {FULL_PROVENANCE}"
    )
    assert bound["seen_by"] == FULL_PROVENANCE["seen_by"]
    assert bound["discovery"]["method"] == "index-query"
    assert bound["discovery"]["query"] == "example.org"


def test_provenance_is_copied_not_aliased() -> None:
    """A later mutation by the caller must not change what is bound."""
    payload: dict[str, Any] = {"method": "index-query", "query": "example.org", "seen_by": []}
    session = _RecordingSession()
    _enqueue(_adapter_for(session), provenance=payload)
    payload["method"] = "mutated-after-enqueue"
    assert _insert_params(session.statements[0])[PROVENANCE_COLUMN]["method"] == "index-query"


def test_the_protocols_own_source_and_method_are_never_lost() -> None:
    """``enqueue`` takes ``source`` and ``method``; no column records the method.

    A caller that passes ``provenance={}`` has still told the adapter how the
    candidate was found. Persisting a frontier item with no record of that would
    be the same loss FR-007 describes, arriving through an empty dict instead of
    a filter.
    """
    session = _RecordingSession()
    _enqueue(_adapter_for(session), provenance={})
    bound = _insert_params(session.statements[0])[PROVENANCE_COLUMN]
    assert bound == {"method": "index-query", "source": "cc-index"}


def test_a_value_the_caller_stated_wins_over_the_filling() -> None:
    """Filling is ``setdefault``, so the document stays truthful.

    If the provenance names a different method than the argument passed beside
    it -- a coalesced candidate reported by a second source, say -- the recorded
    document must describe the candidate, not the last caller.
    """
    session = _RecordingSession()
    _enqueue(
        _adapter_for(session),
        provenance={"method": "cdx", "source": "wayback-cdx"},
    )
    bound = _insert_params(session.statements[0])[PROVENANCE_COLUMN]
    assert bound["method"] == "cdx"
    assert bound["source"] == "wayback-cdx"


def test_none_provenance_becomes_an_empty_document_not_a_null() -> None:
    """The column is ``NOT NULL``; a caller passing ``None`` is not a schema error."""
    session = _RecordingSession()
    _enqueue(_adapter_for(session), provenance=None)
    bound = _insert_params(session.statements[0])[PROVENANCE_COLUMN]
    assert bound == {"method": "index-query", "source": "cc-index"}


def test_non_http_uri_is_refused_rather_than_enqueued() -> None:
    """A frontier item nothing can fetch is worse than no frontier item."""
    session = _RecordingSession()
    _enqueue(_adapter_for(session), uri="mailto:someone@example.org")
    assert session.statements == [], "a non-http(s) URI reached the database"


def test_first_enqueue_commits_and_raises_nothing() -> None:
    session = _RecordingSession(rowcount=1)
    assert _enqueue(_adapter_for(session)) is None, (
        "the Layer A protocol returns None; callers read DiscoveryReport.enqueued"
    )
    assert len(session.statements) == 1
    assert session.commits == 1


def test_duplicate_does_not_raise_and_upgrades_priority_only_when_higher() -> None:
    """rowcount 0 is the dedup path: success, plus the documented priority rule."""
    session = _RecordingSession(rowcount=0)
    _enqueue(_adapter_for(session), priority=7)
    assert len(session.statements) == 2, "expected the INSERT and the priority upgrade"
    upgrade = session.statements[1]
    sql = _insert(upgrade)
    assert "UPDATE frontier_items" in sql
    assert "frontier_items.priority <" in sql
    assert "frontier_items.state IN" in sql
    assert _insert_params(upgrade)["priority"] == 7.0
    assert session.commits == 1


def test_duplicate_leaves_the_stored_provenance_untouched() -> None:
    """First write wins; a second pass must not erase the first pass's evidence.

    Overwriting ``provenance`` on the dedup path would let a later discovery pass
    silently drop the ``seen_by``/``sources`` the first one accumulated -- the
    loss FR-007 exists to prevent, arriving through the *dedup* path instead of
    the bridge. Within one pass the registry has already merged those lists via
    ``coalesce``, so there is nothing to gain by overwriting.
    """
    session = _RecordingSession(rowcount=0)
    _enqueue(_adapter_for(session))
    upgrade = _insert(session.statements[1]).upper()
    assert "PROVENANCE" not in upgrade, (
        "the priority upgrade must not touch the provenance column; first write wins"
    )


def test_unique_violation_on_the_dedup_index_is_treated_as_a_duplicate() -> None:
    """The same dedup arriving as an IntegrityError must also be a success.

    ``ON CONFLICT`` absorbs the ordinary duplicate; this is the race where a
    concurrent transaction committed first and the driver reports the violation
    instead. It is still "already known", so still success (FR-006).
    """
    session = _RecordingSession(rowcount=1, raises=_integrity_error("23505", SCHEDULE_KEY_INDEX))
    adapter = _adapter_for(session)
    assert _enqueue(adapter) is None, "a duplicate is success, not an error (FR-006)"
    assert session.rollbacks == 1, "the failed statement's transaction must be rolled back"
    assert session.commits == 1, "the priority upgrade still commits"
    assert len(session.statements) == 2


def test_a_different_integrity_error_is_not_disguised_as_a_duplicate() -> None:
    """A NOT NULL violation must reach the caller, not be reported as "known".

    ``except IntegrityError: pass`` would turn a missing required column into a
    silent dedup, and the caller would report a URL as already-enqueued when no
    row exists anywhere. That is the one lie this adapter must not tell.
    """
    session = _RecordingSession(rowcount=1, raises=_integrity_error("23502", "frontier_items"))
    with pytest.raises(IntegrityError):
        _enqueue(_adapter_for(session))
    assert session.rollbacks == 0
    assert len(session.statements) == 1, "no priority upgrade without a duplicate"


def test_a_different_unique_constraint_is_not_disguised_as_a_duplicate() -> None:
    """A unique violation on some *other* index is a different bug.

    Same SQLSTATE, different constraint: the dedup index is the only unique
    constraint on ``frontier_items``, so anything else means the schema or the
    statement is wrong, and swallowing it hides that.
    """
    session = _RecordingSession(rowcount=1, raises=_integrity_error("23505", "uq_something_else"))
    with pytest.raises(IntegrityError):
        _enqueue(_adapter_for(session))


def test_an_integrity_error_without_a_sqlstate_is_not_guessed_at() -> None:
    """No SQLSTATE, no claim. Re-raising beats guessing which rule fired."""

    class _Opaque(Exception):
        pass

    session = _RecordingSession(rowcount=1, raises=IntegrityError("INSERT", {}, _Opaque("nope")))
    with pytest.raises(IntegrityError):
        _enqueue(_adapter_for(session))


def test_other_database_errors_are_not_disguised_as_duplicates() -> None:
    """Only the unique-violation path is swallowed; everything else propagates."""

    class _Boom(RuntimeError):
        pass

    session = _RecordingSession(rowcount=1, raises=_Boom("connection reset"))
    with pytest.raises(_Boom, match="connection reset"):
        _enqueue(_adapter_for(session))


def test_adapter_satisfies_the_layer_a_sink_protocol() -> None:
    """Structural conformance, checked the way the protocol is consumed.

    ``registry.py`` calls ``frontier.enqueue(...)`` with keyword arguments only
    and ignores the return value, so signature equality -- names, kinds and
    defaults -- is the property that decides whether a discovery pass runs. The
    protocol is not ``@runtime_checkable``, so the comparison is on the
    signatures rather than on ``isinstance``.
    """
    from adapters.discovery.registry import FrontierSink

    adapter = _adapter_for(_RecordingSession())
    # The protocol's `enqueue` is looked up unbound, so it carries `self`.
    expected = dict(inspect.signature(FrontierSink.enqueue).parameters)
    expected.pop("self")
    actual = inspect.signature(adapter.enqueue).parameters
    assert list(actual) == list(expected), (
        f"enqueue takes {list(actual)}, the protocol declares {list(expected)}"
    )
    for name, parameter in expected.items():
        mine = actual[name]
        assert mine.kind == parameter.kind, f"{name} is a {mine.kind}, the protocol says {parameter.kind}"
        assert mine.default == parameter.default, (
            f"{name} defaults to {mine.default!r}, the protocol says {parameter.default!r}"
        )
    assert adapter.enqueue.__annotations__ == FrontierSink.enqueue.__annotations__


def test_enqueue_works_from_a_plain_synchronous_caller() -> None:
    """The Layer A pass is a blocking loop; the adapter must not need a loop."""
    session = _RecordingSession()
    _enqueue(_adapter_for(session))
    assert len(session.statements) == 1
    assert threading.current_thread() is threading.main_thread()


def test_enqueue_works_from_inside_a_running_event_loop() -> None:
    """A route handler (T028) runs discovery inside a live loop.

    This is the case that rules out ``asyncio.run`` (it refuses outright) and
    rules out blocking on the caller's own loop (that deadlocks). The assertion
    is that it completes at all; a deadlock shows up as the test hanging, which
    is why the coroutine carries its own timeout.
    """

    async def _caller() -> None:
        session = _RecordingSession()
        adapter = _adapter_for(session)
        loop = asyncio.get_running_loop()
        await asyncio.wait_for(asyncio.to_thread(_enqueue, adapter), timeout=15.0)
        assert len(session.statements) == 1
        assert loop.is_running()

    asyncio.run(_caller())


def test_concurrent_enqueues_from_several_threads_all_reach_the_database() -> None:
    """The private loop serialises them instead of rejecting the second caller.

    One adapter, many threads: if the loop were created per call, or if
    ``asyncio.run`` were used, everything past the first call would fail. Each
    call must still produce exactly one statement.
    """
    session = _RecordingSession()
    adapter = _adapter_for(session)
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            adapter.enqueue(
                uri=f"https://example.org/page-{index}",
                tenant_id="tenant-a",
                investigation_id="inv-1",
                source="cc-index",
                method="index-query",
                priority=index,
                provenance={"method": "index-query", "query": "example.org"},
            )
        except BaseException as exc:  # noqa: BLE001 - the test asserts on this
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15.0)

    assert errors == [], f"concurrent enqueues failed: {errors!r}"
    assert len(session.statements) == 8
    assert len({_insert_params(s)["uri"] for s in session.statements}) == 8


# ---------------------------------------------------------------------------
# Tier 2 -- live: the row that actually lands in frontier_items
# ---------------------------------------------------------------------------


def _postgres_dsn() -> str:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "shared"))
    from config.settings import get_settings

    return get_settings().postgres.dsn


def _skip_without_postgres() -> str:
    """Return a skip reason unless a PostgreSQL server answers the DSN.

    The offline tier above already pins the emitted statement; this tier exists
    to pin the stored row. When there is no server, saying so plainly is the
    honest outcome: an ERROR would read as a broken suite, a skip reads as an
    unexercised proof, and only the second one is true.
    """
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.ext.asyncio import create_async_engine

    try:
        dsn = _postgres_dsn()
    except Exception as exc:  # noqa: BLE001 - any settings failure is a skip
        return f"no Postgres DSN is available: {type(exc).__name__}: {exc}"
    if not dsn:
        return "no Postgres DSN is configured"

    async def _probe() -> str | None:
        engine = create_async_engine(dsn)
        try:
            async with engine.connect() as connection:
                await connection.exec_driver_sql("SELECT 1")
            return None
        except (SQLAlchemyError, OSError, ValueError) as exc:
            return (
                f"PostgreSQL is not reachable at the configured DSN "
                f"({dsn.rsplit('@', 1)[-1]}): {type(exc).__name__}"
            )
        finally:
            await engine.dispose()

    try:
        return asyncio.run(_probe()) or ""
    except (SQLAlchemyError, OSError, ValueError) as exc:
        return f"PostgreSQL probe failed: {type(exc).__name__}: {exc}"


SCHEMA = "cp017_frontier"


class _SchemaSessionFactory:
    """Session factory whose every connection is pinned to the throwaway schema.

    The adapter takes a session factory, so the test owns one and can guarantee
    the ``search_path`` on *each* connection -- the pool may hand out a different
    one for the second enqueue, and an unpinned second connection would write to
    ``public``. The application tables are never touched either way.
    """

    def __init__(self, factory: Any, schema: str = SCHEMA) -> None:
        self._factory = factory
        self._schema = schema

    def __call__(self) -> Any:
        return self._pinned()

    def _pinned(self) -> Any:
        owner = self

        class _Pinned:
            async def __aenter__(self) -> Any:
                self._session = owner._factory()
                await self._session.__aenter__()
                from sqlalchemy import text

                await self._session.execute(text(f"SET search_path TO {owner._schema}"))
                return self._session

            async def __aexit__(self, *exc: object) -> bool:
                return bool(await self._session.__aexit__(*exc))

        return _Pinned()


@pytest.fixture
def live_frontier():
    """``frontier_items`` in a throwaway schema, or a skip with a reason.

    The table is created from ORM metadata -- the *fresh-install* path -- and
    dropped again afterwards. The upgrade path over the same table is covered by
    ``test_migration_017_forward_only.py``; between them, both install routes and
    the adapter that depends on the column are exercised.
    """
    reason = _skip_without_postgres()
    if reason:
        pytest.skip(f"{reason} -- live frontier row not exercised")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from db.schema import FrontierItem as Row

    dsn = _postgres_dsn()

    async def _setup() -> Any:
        engine = create_async_engine(dsn)
        async with engine.connect() as connection:
            await connection.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
            await connection.execute(text(f"CREATE SCHEMA {SCHEMA}"))
            await connection.commit()
            await connection.execute(text(f"SET search_path TO {SCHEMA}"))
            await connection.run_sync(lambda sync: Row.__table__.create(sync, checkfirst=False))
            await connection.commit()
        factory = async_sessionmaker(engine, expire_on_commit=False)
        return engine, _SchemaSessionFactory(factory)

    engine, factory = asyncio.run(_setup())
    try:
        yield factory
    finally:
        async def _teardown() -> None:
            async with engine.connect() as connection:
                await connection.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
                await connection.commit()

        asyncio.run(_teardown())
        asyncio.run(engine.dispose())


def _rows(factory: Any) -> list[Any]:
    from sqlalchemy import select

    from db.schema import FrontierItem as Row

    async def _read() -> list[Any]:
        async with factory() as session:
            result = await session.execute(select(Row).order_by(Row.uri))
            return list(result.scalars().all())

    return asyncio.run(_read())


@pytest.mark.integration
def test_provenance_is_readable_back_from_the_row(live_frontier) -> None:
    """FR-007, end to end: the dict is in the row, not just in the adapter."""
    from db.schema import FrontierItem as Row

    adapter = FrontierSinkAdapter(live_frontier, host_key_of=canonical_host)
    try:
        _enqueue(adapter)
    finally:
        adapter.close()

    rows = _rows(live_frontier)
    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row, Row)
    assert row.provenance == FULL_PROVENANCE, (
        f"provenance did not survive the round trip: {row.provenance}"
    )
    assert row.provenance["method"] == "index-query", (
        f"provenance['method'] did not survive: {row.provenance}"
    )
    assert row.provenance["query"] == "example.org"
    assert row.provenance["discovery"]["method"] == "index-query"
    assert row.provenance["discovery"]["query"] == "example.org"
    assert row.provenance["seen_by"] == FULL_PROVENANCE["seen_by"], (
        "seen_by is the record that a second source saw the URL first; losing it "
        "means the corroboration can never be re-derived"
    )
    assert row.provenance["sources"] == FULL_PROVENANCE["sources"]
    assert row.provenance["confidence"] == pytest.approx(0.72)


@pytest.mark.integration
def test_second_enqueue_of_the_same_canonical_url_creates_no_second_row(live_frontier) -> None:
    """FR-006 idempotency at the boundary, on the real unique index."""
    adapter = FrontierSinkAdapter(live_frontier, host_key_of=canonical_host)
    try:
        _enqueue(adapter)
        first = _rows(live_frontier)
        assert len(first) == 1

        # A different spelling of the same URL: same canonical form, so the same
        # dedup key. If the adapter stored either spelling verbatim this would
        # produce a second row.
        _enqueue(adapter, uri="https://example.org/reports/?q=1")
        assert len(_rows(live_frontier)) == 1
    finally:
        adapter.close()


@pytest.mark.integration
def test_row_is_ready_and_the_adapter_wrote_no_schedule_field(live_frontier) -> None:
    """``state == "READY"`` and every scheduling field left at its default.

    The point is not the value ``READY`` -- that is what the frontier and the
    adapter agree on -- it is that the adapter *chose* none of it. ``lease_until``
    and ``next_schedule_at`` must still be NULL and ``retries`` still 0, which
    is what "deferral, budget exhaustion, lease and recrawl cadence are the
    frontier's policy" (ADR-0016/0017) looks like on a real row.
    """
    adapter = FrontierSinkAdapter(live_frontier, host_key_of=canonical_host)
    try:
        _enqueue(adapter)
    finally:
        adapter.close()

    rows = _rows(live_frontier)
    assert len(rows) == 1
    row = rows[0]
    assert row.state == "READY"
    assert row.retries == 0
    assert row.lease_until is None, "the adapter must not lease an item it does not own"
    assert row.next_schedule_at is None, (
        "the adapter must not schedule an item; next_schedule_at belongs to frontier policy"
    )
    assert row.partition == "global"
    assert row.last_digest is None and row.last_etag is None
    assert row.host_key == "example.org"
    assert row.source_id == "cc-index"
    assert row.priority == pytest.approx(7.0)
    assert row.uri == "https://example.org/reports/?q=1"


@pytest.mark.integration
def test_a_discovery_registry_pass_lands_one_row_per_canonical_url_with_merged_provenance(
    live_frontier,
) -> None:
    """The whole path, not just the adapter: three sources, one URL, one row.

    Each stub source is a ``DiscoverySource`` -- ``name``, ``capabilities``,
    ``discover`` -- so this is the real registry driving the real adapter. The
    two sources that report the same canonical URL force ``coalesce`` to
    accumulate ``seen_by``, which is the list T013 requires to survive; the third
    reports a URL only one source has, which must become its own row.

    The second source's ``url`` keeps the trailing slash it would really have
    fetched, but its ``canonical_url`` is the same string as the first source's --
    ``coalesce`` keys on that string verbatim rather than re-canonicalising, which
    is precisely why the canonical form has to be computed at the edge where the
    URL is found and not left to the frontier.
    """
    shared = Candidate(
        url="https://example.org/shared",
        canonical_url="https://example.org/shared",
        source="cc-index",
        method="index-query",
        confidence=0.7,
        query="example.org",
        provenance={"seen_by": [], "sources": ["cc-index"]},
    )
    solo = Candidate(
        url="https://example.org/only-in-ct",
        canonical_url="https://example.org/only-in-ct",
        source="ct-log",
        method="ct-log",
        confidence=0.9,
        query="example.org",
        provenance={},
    )

    class _Stub:
        def __init__(self, name: str, found: list[Candidate]) -> None:
            self._name = name
            self._found = found

        @property
        def name(self) -> str:
            return self._name

        @property
        def capabilities(self) -> frozenset[str]:
            return frozenset({"index"})

        def discover(self, query: str) -> list[Candidate]:
            return list(self._found)

    registry = DiscoveryRegistry()
    registry.register(_Stub("cc-index", [shared, solo]))
    registry.register(
        _Stub(
            "wayback-cdx",
            [
                Candidate(
                    url="https://example.org/shared/",
                    canonical_url="https://example.org/shared",
                    source="wayback-cdx",
                    method="cdx",
                    confidence=0.4,
                    query="example.org",
                    provenance={},
                )
            ],
        )
    )

    adapter = FrontierSinkAdapter(live_frontier, host_key_of=canonical_host)
    try:
        report = registry.discover(
            "example.org",
            sources=["cc-index", "wayback-cdx"],
            frontier=adapter,
            tenant_id="tenant-a",
            investigation_id="inv-1",
        )
    finally:
        adapter.close()

    assert report.candidates_found == 2
    rows = {row.uri: row for row in _rows(live_frontier)}
    assert set(rows) == {"https://example.org/shared", "https://example.org/only-in-ct"}, (
        f"expected one row per canonical URL, got {sorted(rows)}"
    )

    merged = rows["https://example.org/shared"].provenance
    assert merged["discovery"]["method"] == "index-query", "first source wins for scalars"
    assert merged["sources"] == ["cc-index", "wayback-cdx"]
    assert merged["seen_by"] == [{"source": "wayback-cdx", "method": "cdx"}], (
        f"coalesce's seen_by did not survive the bridge: {merged.get('seen_by')}"
    )
    assert rows["https://example.org/only-in-ct"].provenance["discovery"]["method"] == "ct-log"
    for row in rows.values():
        assert row.state == "READY"
        assert row.next_schedule_at is None


# ---------------------------------------------------------------------------
# LinkEdgeProvider — an edge that cannot name its evidence does not leave
# ---------------------------------------------------------------------------

WRITE_PROVENANCE = {"observation_id": "obs-1", "event_id": "cp017.test"}


def _store(*edges: Any) -> Any:
    """An in-memory graph store holding exactly ``edges``, endpoints created."""
    from graph.abstraction import GraphNode, InMemoryGraphStore

    store = InMemoryGraphStore()
    node_ids = sorted({e.source for e in edges} | {e.target for e in edges})
    for node_id in node_ids:
        store.write_node(GraphNode(node_id=node_id, node_type="url"), dict(WRITE_PROVENANCE))
    for edge in edges:
        store.write_edge(edge, dict(WRITE_PROVENANCE))
    return store


def _edge(edge_id: str, source: str, target: str, **properties: Any) -> Any:
    from graph.abstraction import GraphEdge

    return GraphEdge(
        edge_id=edge_id,
        edge_type=properties.pop("edge_type", "link"),
        source=source,
        target=target,
        properties=properties,
    )


def test_only_provenance_bearing_tenant_visible_edges_are_returned() -> None:
    """Three of four stored edges come back, and the fourth is the interesting one.

    The rejections are the point: another tenant's edge, and an edge with no
    originating observation. Both would otherwise enter discovery as URLs, and
    neither could be traced back to a raw object if a finding ever rested on it.
    """
    store = _store(
        _edge("e-good", "a", "b", tenant_id="tenant-a", observation_id="obs-1"),
        _edge("e-other-tenant", "a", "c", tenant_id="tenant-b", observation_id="obs-1"),
        _edge("e-no-observation", "a", "d", tenant_id="tenant-a"),
        _edge("e-unowned", "a", "e", observation_id="obs-1"),
    )
    provider = LinkEdgeProvider(store, tenant_id="tenant-a")
    returned = provider.edges_from("a", tenant_id="tenant-a")
    assert [(e.source, e.target) for e in returned] == [("a", "b")]
    edge = returned[0]
    assert edge.observation_id == "obs-1"
    assert edge.edge_id == "e-good", "the store owns edge identity; it is passed through, not minted"
    assert edge.edge_type == "link"


def test_an_observation_id_nested_under_provenance_still_counts() -> None:
    """A store that nests its evidence has still named it; shape is not the test."""
    store = _store(
        _edge("e-nested", "a", "b", tenant_id="tenant-a", provenance={"observation_id": "obs-9"})
    )
    provider = LinkEdgeProvider(store, tenant_id="tenant-a")
    assert [e.observation_id for e in provider.edges_from("a", tenant_id="tenant-a")] == ["obs-9"]


def test_an_observation_id_list_takes_its_first_entry() -> None:
    """Some projections name several observations per edge; the first is stable."""
    store = _store(
        _edge("e-many", "a", "b", tenant_id="tenant-a", observation_ids=["obs-1", "obs-2"])
    )
    provider = LinkEdgeProvider(store, tenant_id="tenant-a")
    assert [e.observation_id for e in provider.edges_from("a", tenant_id="tenant-a")] == ["obs-1"]


def test_node_identity_is_passed_through_unchanged() -> None:
    """No canonicalisation, hashing or re-keying (FR-014).

    A node id minted here would not match the search projection's, and a finding
    reached through discovery would not be joinable back to the observation that
    produced it.
    """
    store = _store(_edge("e1", "Obs-Alpha/é", "obs/beta#frag", tenant_id="t", observation_id="o1"))
    provider = LinkEdgeProvider(store, tenant_id="t")
    edge = provider.edges_from("Obs-Alpha/é", tenant_id="t")[0]
    assert (edge.source, edge.target) == ("Obs-Alpha/é", "obs/beta#frag")


def test_parallel_edges_in_both_directions_keep_their_own_direction() -> None:
    """A->B and B->A are two relations and both come back the right way round.

    A single-node read cannot show both: the reader hands back neighbour *ids*,
    so visiting ``a`` yields the triple ``(a, b)`` once no matter how many
    distinct relations connect the two nodes, and the forward edge is the right
    one to resolve it to. Graph-wide expansion visits both nodes, so both
    relations surface -- and the direction of each must match the store.
    """
    store = _store(
        _edge("e-ab", "a", "b", tenant_id="t", observation_id="o1"),
        _edge("e-ba", "b", "a", tenant_id="t", observation_id="o2"),
    )
    provider = LinkEdgeProvider(store, tenant_id="t")
    from_a = provider.edges_from("a", tenant_id="t")
    assert [(e.source, e.target, e.edge_id) for e in from_a] == [("a", "b", "e-ab")], (
        "a single-node read resolves to the forward edge, never the reverse one"
    )
    everywhere = {
        (e.source, e.target, e.edge_id) for e in provider.edges_from("", tenant_id="t")
    }
    assert everywhere == {("a", "b", "e-ab"), ("b", "a", "e-ba")}


def test_an_undirected_store_still_resolves_to_the_stored_edge() -> None:
    """The reader visits A and reports neighbour B; the store recorded B -> A.

    An undirected store is a legitimate shape, so the reverse lookup has to
    succeed -- and it returns the stored edge's own direction rather than
    inventing one, so the caller still sees the direction the store holds.
    """
    store = _store(_edge("e-stored-ba", "b", "a", tenant_id="t", observation_id="o1"))
    provider = LinkEdgeProvider(store, tenant_id="t")
    edge = provider.edges_from("a", tenant_id="t")[0]
    assert (edge.source, edge.target, edge.edge_id) == ("b", "a", "e-stored-ba")


def test_the_edge_type_filter_matches_stored_edge_types() -> None:
    """A regression guard on the filter's subject.

    The adjacency reader stamps an empty ``edge_type`` when it was not told one,
    so filtering the emitted triple against the requested types rejects
    everything. The filter has to be applied to the stored edge, which is the one
    that actually carries a type.
    """
    store = _store(
        _edge("e-link", "a", "b", edge_type="link", tenant_id="t", observation_id="o1"),
        _edge("e-mention", "a", "c", edge_type="co_mention", tenant_id="t", observation_id="o1"),
    )
    only_link = LinkEdgeProvider(store, tenant_id="t", edge_types=frozenset({"link"}))
    assert [e.edge_id for e in only_link.edges_from("a", tenant_id="t")] == ["e-link"]

    both = LinkEdgeProvider(store, tenant_id="t", edge_types=frozenset({"link", "co_mention"}))
    assert sorted(e.edge_id for e in both.edges_from("a", tenant_id="t")) == ["e-link", "e-mention"]

    nothing = LinkEdgeProvider(store, tenant_id="t", edge_types=frozenset({"hyperlink"}))
    assert nothing.edges_from("a", tenant_id="t") == []


def test_an_empty_node_reads_the_whole_graph_and_a_limit_bounds_it() -> None:
    """Graph-wide expansion, bounded by the caller's limit.

    ``limit=None`` means "use the configured limit"; a negative limit is the way
    to ask for no bound at all.
    """
    store = _store(
        *[
            _edge(f"e{index}", "a", f"n{index}", tenant_id="t", observation_id="o1")
            for index in range(5)
        ]
    )
    provider = LinkEdgeProvider(store, tenant_id="t", node=None, limit=3)
    everything = provider.edges_from("", tenant_id="t", limit=-1)
    assert len(everything) == 5
    assert len(provider.edges_from("", tenant_id="t")) == 3, "the configured limit bounds a pass"
    assert len(provider.edges_from("", tenant_id="t", limit=1)) == 1, "an explicit limit wins"


def test_a_node_declaring_another_tenant_yields_nothing() -> None:
    """A foreign node is invisible, not an error.

    Refusing rather than raising keeps one foreign node in a shared graph from
    aborting a whole discovery pass, while still never returning its edges.
    """
    from graph.abstraction import GraphNode

    store = _store(_edge("e1", "a", "b", tenant_id="t", observation_id="o1"))
    store.write_node(
        GraphNode(node_id="foreign", node_type="url", properties={"tenant_id": "other"}),
        dict(WRITE_PROVENANCE),
    )
    store.write_edge(
        _edge("e-foreign", "foreign", "a", tenant_id="other", observation_id="o2"),
        dict(WRITE_PROVENANCE),
    )
    provider = LinkEdgeProvider(store, tenant_id="t")
    assert provider.edges_from("foreign", tenant_id="t") == []
    assert provider.edges_from("nobody", tenant_id="t") == [], "an unknown node has no visible edges"


def test_the_call_surface_yields_triples_for_the_link_graph_source() -> None:
    """``__call__`` is the zero-argument ``EdgeProvider`` seam."""
    store = _store(_edge("e1", "a", "b", tenant_id="t", observation_id="o1"))
    provider = LinkEdgeProvider(store, tenant_id="t")
    assert provider() == [("a", "b", "link")]


def test_a_provider_cannot_be_built_without_a_tenant() -> None:
    """Fail closed at construction, and on an explicit empty tenant.

    ``None`` means "use the tenant you were built for"; ``""`` is a caller that
    has not identified itself, and answering it with the configured tenant would
    hand that caller's request another tenant's edges.
    """
    store = _store(_edge("e1", "a", "b", tenant_id="t", observation_id="o1"))
    with pytest.raises(ValueError, match="tenant"):
        LinkEdgeProvider(store, tenant_id="")
    provider = LinkEdgeProvider(store, tenant_id="t")
    with pytest.raises(ValueError, match="tenant"):
        provider.edges_from("a", tenant_id="")
    assert provider.edges_from("a", tenant_id=None), "None falls back to the configured tenant"
