"""Production bindings between Layer A discovery and the durable frontier (008).

Layer A (``apps/acquisition/adapters/discovery``) is deliberately hermetic: a
synchronous, in-memory, dependency-free set of contracts, so that canonicalisation
and coalescing are provable without Postgres. The durable frontier
(``services/frontier.py``) is the opposite: async, Postgres-authoritative, and
the owner of scheduling policy. This module is the seam between them and holds
exactly two bindings:

``FrontierSinkAdapter``
    Implements Layer A's ``FrontierSink`` protocol by handing one
    ``services.frontier.FrontierItem`` to ``PgFrontier.enqueue`` -- the single
    writer of ``frontier_items`` -- carrying the discovery's provenance.

``LinkEdgeProvider``
    Satisfies the ``edge_provider`` seam that ``discovery/linkgraph.py`` already
    accepts, reading the graph projection.

Neither creates a queue, a table or a cache (FR-017). Kafka is never the frontier
queue (Invariant 5): the durable frontier *is* ``frontier_items``.

--------------------------------------------------------------------------
One write path, not two
--------------------------------------------------------------------------

The adapter emits no SQL of its own. It builds a ``FrontierItem`` and awaits
``PgFrontier.enqueue`` (``services/frontier.py``), which owns the single INSERT
into ``frontier_items``; the module holds the import of no ``pg_insert``, no
``update`` and no ORM row type, so there is nothing here that could drift from
the frontier's.

That is a change from this module's first shape, which performed the durable
INSERT itself. The reason was structural, not stylistic: ``FrontierItem`` had no
``provenance`` field and ``PgFrontier.enqueue``'s INSERT had no ``provenance``
column, so a delegating adapter carried the dict in memory, handed the row over,
and watched it fall on the floor at the boundary -- FR-007 satisfied in the
adapter and lost in the database, which is the exact failure the provenance
column exists to close. The second writer solved that loss by forking the write
path, and a forked write path is the "second authority" the constitution forbids
(SC-012) and the component inventory (FR-017) is written to catch. So the
frontier was made provenance-aware instead: the column is now on the dataclass
and on the INSERT, and this module delegates.

The guarantees are unchanged, and they are now properties of the one statement
rather than of two:

* ``uri`` is the **canonical** URL, so dedup is by canonical URL (FR-006).
* ``provenance`` is the FULL dict, verbatim, with ``source`` and ``method``
  filled in where the caller left them out -- never filtered (FR-007).
* ``priority`` is widened int -> float, unclamped and untruncated.
* ``host_key`` comes from the injected callable, which is the per-host budget
  policy's to derive (ADR-0016).
* ``state``, ``retries``, ``lease_until`` and ``next_schedule_at`` are left at
  the dataclass defaults and never assigned here. They are frontier policy
  (ADR-0016/0017), and ``PgFrontier.enqueue`` names its own values for them
  regardless of what an item carries, so a producer cannot schedule even by
  trying: deferral, budget exhaustion, lease expiry and recrawl cadence stay the
  frontier's decisions.

The dedup rule is now the frontier's alone, which is the point of delegating.
The behaviour a re-discovered URL gets -- priority raised while the known row is
still actionable, ``state='READY'`` written alongside it, and the stored
``provenance`` left alone (first write wins) -- is ``PgFrontier``'s existing
rule, applied here exactly as it is for every other producer, rather than a
discovery-specific variant of it.

--------------------------------------------------------------------------
Sync -> async
--------------------------------------------------------------------------

Layer A's ``FrontierSink.enqueue`` is synchronous (``registry.py:20``) because the
whole Layer A pass is a blocking function: ``DiscoveryRegistry.discover`` loops
over coalesced candidates calling ``enqueue`` in a plain ``for`` body
(``registry.py:146``). Making Layer A async would force every hermetic Layer A
test to build a Postgres session and become async, destroying the property that
makes FR-005/FR-006 provable in isolation (decision D3). So the protocol stays
sync and the adapter absorbs the asynchrony.

The adapter owns **one dedicated event loop on one daemon thread**, created
lazily on first use, and submits each enqueue with
``asyncio.run_coroutine_threadsafe`` from the calling thread, blocking on the
result. The alternatives were both worse:

* ``asyncio.run(...)`` -- refuses outright when a loop is already running in the
  thread, which is exactly the case for a FastAPI route (T028) that runs a
  discovery pass. It would turn a supported call site into a ``RuntimeError``.
* Blocking on the *caller's own* running loop (``future.result()`` on a coroutine
  submitted to the current loop) -- a hard deadlock: the thread that must run the
  coroutine is the thread blocked waiting for it. This is the classic way a sync
  shim over async code hangs a request forever.

A private loop thread avoids both. It works from a plain synchronous caller
(fast discovery) and from inside a running loop (a request handler), and it never
deadlocks, because the work is always scheduled onto a loop that is not the
caller's.

The cost is honest and worth stating: a caller already inside an event loop will
have *its* loop thread blocked for the duration of the database round-trip.
Discovery enqueue is a low-rate, write-once-per-candidate path called in a loop
over a handful of candidates, so serialising it is correct and cheap. A
high-throughput caller should drive ``enqueue_async`` instead and never block a
loop. The loop is therefore private but not hidden -- ``enqueue_async`` is public
and is the same coroutine ``enqueue`` wraps, so there is one implementation.

Errors are not swallowed. Only two outcomes are non-raising: a duplicate (the
unique index did its job -- success, per contract) and a concurrency race that
surfaces the same duplicate as a constraint violation. A timeout is raised as
``FrontierEnqueueTimeout`` rather than returned as a silent drop, because a
frontier row that may or may not exist is not a state a caller can act on; every
other database error, including any integrity error that is not the dedup index,
propagates untouched (see ``services.frontier._is_dedup_violation``).
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from adapters.discovery import canonicalize
from graph.adjacency import AdjacencyEdge, adjacency_from_store

from services.frontier import FrontierItem, PgFrontier


class FrontierEnqueueTimeout(TimeoutError):
    """The durable enqueue did not confirm within the adapter's deadline.

    Deliberately not a silent drop: a caller cannot distinguish "the row is
    there" from "the row was never written" if the answer is ``None``, and
    discovery's own dedup makes the retry free (FR-006).
    """


@dataclass
class FrontierSinkAdapter:
    """Layer A ``FrontierSink`` bound to the durable ``frontier_items`` table.

    Implements ``adapters.discovery.registry.FrontierSink`` structurally -- the
    protocol is not imported or subclassed, so Layer A and the control plane stay
    decoupled in both directions.

    The adapter owns the *bridge* and nothing else: no SQL, no table, no queue.
    Every durable write is ``PgFrontier.enqueue``'s, so the frontier stays the
    single authority over ``frontier_items`` (SC-012).

    Fields
    ------
    session_factory
        An ``async_sessionmaker``, the same collaborator ``PgFrontier`` takes.
        Held rather than an ``async enqueue`` callable so this module can absorb
        the asynchrony for a synchronous Layer A caller; ``PgFrontier`` is
        constructed per enqueue from it, which is free -- the service is a
        stateless wrapper over the factory.
    host_key_of
        ``canonical_uri -> host key``. Injected rather than computed here: the
        per-host budget and cooldown policy that consume ``host_key`` is frontier
        policy (ADR-0016/0017), and a discovery adapter that invents its own host
        key would quietly fork that policy.
    timeout_s
        Deadline for the durable write, so a wedged database surfaces as a
        ``FrontierEnqueueTimeout`` instead of a thread blocked forever.
    """

    session_factory: Callable[[], Any]
    host_key_of: Callable[[str], str]
    timeout_s: float = 10.0

    _loop: asyncio.AbstractEventLoop | None = field(default=None, init=False, repr=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _loop_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    # -- Layer A FrontierSink protocol (synchronous, by contract) ----------

    def enqueue(
        self,
        *,
        uri: str,
        tenant_id: str,
        investigation_id: str,
        source: str,
        method: str,
        priority: int = 0,
        provenance: dict[str, Any] | None = None,
    ) -> None:
        """Enqueue one discovered candidate. Never raises on the dedup path.

        ``uri`` is canonicalised before it is used as the dedup key, so a caller
        that hands over a raw URL still cannot create a second row for a URL the
        frontier already holds. A non-http(s) URI is refused rather than
        enqueued: ``canonicalize`` returns ``None`` for it, and a frontier row
        that acquisition can never fetch is worse than no row at all.
        """
        canonical = canonicalize(uri)
        if canonical is None:
            return
        self._submit(
            self.enqueue_async(
                uri=canonical,
                tenant_id=tenant_id,
                investigation_id=investigation_id,
                source=source,
                method=method,
                priority=priority,
                provenance=provenance,
            )
        )

    # -- the same enqueue, awaitable ---------------------------------------

    async def enqueue_async(
        self,
        *,
        uri: str,
        tenant_id: str,
        investigation_id: str,
        source: str,
        method: str,
        priority: int = 0,
        provenance: dict[str, Any] | None = None,
    ) -> bool:
        """Write the row. Returns whether a new row was created.

        ``True`` means this call created the frontier item; ``False`` means the
        unique index ``uq_frontier_schedule (tenant_id, uri)`` already had one.
        ``False`` is a success, not an error (FR-006) -- the Layer A protocol
        returns ``None`` precisely because callers learn the outcome from
        ``DiscoveryReport.enqueued`` instead of a per-call signal.

        Everything durable is ``PgFrontier.enqueue``'s. What this method owns is
        the translation from Layer A's keyword protocol to one ``FrontierItem``:

        ``uri``
            the **canonical** URL, so dedup is by canonical URL and no spelling of
            one page can produce two rows.
        ``priority``
            widened int -> float, unclamped and untruncated, because ``priority``
            is ``float8`` in the table and the dataclass declares it as a float.
        ``host_key``
            from the injected callable, never invented here.
        ``provenance``
            the FULL dict, verbatim, with the two protocol arguments that have no
            column of their own filled in where the caller left them out.
        ``state`` / ``retries`` / ``lease_until`` / ``next_schedule_at``
            **not assigned.** They stay at the dataclass defaults and
            ``PgFrontier.enqueue`` names its own values for them whatever the
            item carries, so deferral, budget exhaustion, lease expiry and recrawl
            cadence remain the frontier's policy (ADR-0016/0017) and this adapter
            cannot become a second scheduler even by mistake.
        """
        canonical = canonicalize(uri)
        if canonical is None:
            return False

        item = FrontierItem(
            # Proposed identity only. The durable identity of a frontier item is
            # (tenant_id, uri); a concurrent writer that wins the ON CONFLICT
            # race keeps its own frontier_id and this one is discarded, so the
            # value need not be deterministic and is not treated as an identity.
            frontier_id=str(uuid.uuid4()),
            uri=canonical,
            tenant_id=tenant_id,
            investigation_id=investigation_id,
            # `source` is a discovery-source *name*, not a sources-row id; the
            # column is the only place it can live, and it is nullable so a
            # non-discovery enqueue is not forced to invent one.
            source_id=source,
            host_key=self.host_key_of(canonical),
            # int -> float widening only. Every int up to 2**53 is exactly
            # representable, so the widening is lossless over the range the
            # frontier actually orders by; a larger int rounds rather than
            # raising, because a priority is a ranking hint and a caller must not
            # be handed an exception for a large number. Clamping or truncating
            # here would silently reorder the frontier relative to what the caller
            # asked for.
            priority=float(priority),
            # FR-007, carried on the item so the frontier's own INSERT persists
            # it: filtering it to a known subset anywhere on this path is the
            # boundary failure the column exists to prevent -- a `seen_by[]` entry
            # dropped at the bridge is a source that will never be re-queried for a
            # corroboration that already exists.
            provenance=_provenance_document(provenance, source=source, method=method),
        )
        return await PgFrontier(self.session_factory).enqueue(item)

    # -- event loop plumbing ----------------------------------------------

    def _submit(self, coro: Awaitable[None]) -> None:
        """Run ``coro`` on the adapter's private loop and wait for it."""
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)  # type: ignore[arg-type]
        try:
            future.result(timeout=self.timeout_s)
        except TimeoutError:
            if future.done():
                # The coroutine itself timed out (a driver-level timeout), not
                # the wait. Relabelling it as a missed deadline would send the
                # caller looking in the wrong place.
                raise
            future.cancel()
            raise FrontierEnqueueTimeout(
                f"frontier enqueue did not confirm within {self.timeout_s}s"
            ) from None

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        """Create the private loop thread on first use; return the loop after.

        One loop, one thread, for the lifetime of the adapter: a second loop would
        mean a second set of connection state, and the database driver is happier
        with one.
        """
        if self._loop is not None and not self._loop.is_closed():
            return self._loop
        with self._loop_lock:
            if self._loop is None or self._loop.is_closed():
                loop = asyncio.new_event_loop()
                thread = threading.Thread(
                    target=_run_loop,
                    args=(loop,),
                    name="discovery-frontier-enqueue",
                    daemon=True,
                )
                thread.start()
                self._loop, self._thread = loop, thread
        return self._loop  # type: ignore[return-value]

    def close(self) -> None:
        """Stop the private loop. Safe to call more than once.

        Only for a process that is shutting the adapter down; a live adapter
        should keep its loop, since re-creating it per pass would be the "second
        queue" this module is not allowed to build.
        """
        loop, thread = self._loop, self._thread
        self._loop = self._thread = None
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(loop.stop)
        if thread is not None:
            thread.join(timeout=self.timeout_s)


def _run_loop(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    loop.run_forever()


def _provenance_document(
    provenance: dict[str, Any] | None, *, source: str, method: str
) -> dict[str, Any]:
    """The full provenance dict, copied, with the protocol's own answers filled in.

    Two jobs, and the distinction matters:

    *Never filter.* Whatever the caller passed is carried through whole, nested
    lists and all. Dropping an unrecognised key here is the boundary loss FR-007
    exists to prevent, and it is unrecoverable afterwards: nothing downstream can
    know what was discarded.

    *Never lose an argument.* ``FrontierSink.enqueue`` takes ``source`` and
    ``method`` as separate parameters, and neither has a column of its own
    (``source_id`` records the source; no column records the method at all). A
    caller that passes ``provenance={}`` would therefore persist a frontier item
    with no record of how it was found, while having told the adapter exactly
    how. ``DiscoveryRegistry`` happens to duplicate the method into
    ``provenance["discovery"]`` before calling, but this is the binding any other
    Layer A caller uses, so the guarantee is made here rather than assumed.

    Filling is ``setdefault`` and never overwrite: a value the caller stated
    wins, so the document keeps describing the discovery that actually happened
    even when it disagrees with the argument passed alongside it.
    """
    document = dict(provenance) if provenance else {}
    document.setdefault("method", method)
    document.setdefault("source", source)
    return document


# ---------------------------------------------------------------------------
# LinkEdgeProvider — the production binding for the link-graph source
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LinkEdge:
    """One provenance-bearing directed edge, as the graph projection holds it.

    ``observation_id`` is not optional and not defaulted to ``""``: an edge whose
    originating observation cannot be named is not admitted by
    :meth:`LinkEdgeProvider.edges_from` at all (Constitution II,
    evidence-first), so there is no value a caller could construct here that
    would be a lie. ``edge_id`` is carried through untouched -- the store owns
    edge identity and this module never mints one (FR-014).
    """

    source: str
    target: str
    edge_type: str
    observation_id: str
    edge_id: str = ""


class LinkEdgeProvider:
    """Reads link edges from the graph projection for discovery expansion (FR-004).

    Satisfies both surfaces the seam has:

    * ``edges_from(node, *, tenant_id, limit) -> list[LinkEdge]`` --
      ``service-contracts.md`` section 8.
    * ``__call__() -> list[tuple[str, str, str]]`` -- the ``EdgeProvider`` alias
      in ``discovery/linkgraph.py:16``, which is a zero-argument callable
      returning ``(source, target, edge_type)`` triples. Passing this object as
      ``LinkGraphSource(edge_provider=...)`` therefore works directly, and the
      triple is built by dropping the fields that surface does not carry rather
      than by inventing a second traversal.

    Three rules are load-bearing, and each is a filter applied before an edge
    leaves this class:

    1. **Provenance required.** An edge is returned only if it names the
       observation it came from. An edge with no such reference has no path back
       to a raw object, so admitting it would let an unauditable claim into
       discovery (Constitution II).
    2. **Tenant-scoped, fail closed.** An edge is visible only to the tenant it
       declares. An edge that declares no tenant is visible to nobody, because a
       row whose owner cannot be established cannot safely be attributed to the
       caller -- returning it "usually works" and fails open, which is how
       cross-tenant leakage happens (decision D5).
    3. **No re-derivation of identity.** Node ids are read from the store and
       passed through. Nothing here canonicalises, hashes, re-keys or re-orders
       them, so a node id here is the same id the search projection and the TDA
       adjacency use (FR-014).
    """

    def __init__(
        self,
        store: Any,
        *,
        tenant_id: str,
        node: str | None = None,
        limit: int = 1000,
        edge_types: frozenset[str] | None = None,
    ) -> None:
        if not tenant_id:
            raise ValueError("LinkEdgeProvider requires a non-empty tenant_id")
        self._store = store
        self._tenant_id = tenant_id
        self._node = node
        self._limit = limit
        self._edge_types = edge_types

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    def __call__(self) -> list[tuple[str, str, str]]:
        """The ``edge_provider`` seam: ``(source, target, edge_type)`` triples."""
        return [
            (edge.source, edge.target, edge.edge_type)
            for edge in self.edges_from(self._node or "", limit=self._limit)
        ]

    def edges_from(
        self, node: str, *, tenant_id: str | None = None, limit: int | None = None
    ) -> list[LinkEdge]:
        """Provenance-bearing, tenant-visible edges incident to ``node``.

        ``node=""`` (or the ``None`` default) means graph-wide expansion, which
        is what ``linkgraph.py`` wants for an empty query: the frontier's
        per-host budget (ADR-0016) bounds the work, not this reader.

        ``tenant_id=None`` uses the tenant the provider was built for; an
        explicitly empty one is refused. ``limit=None`` uses the configured
        limit, a negative limit means no limit, and a non-negative one is the
        number of edges returned.

        The structural neighbourhood comes from ``adjacency_from_store`` -- the
        production reader, and the reason this module needs no vendor client
        (Constitution V). That reader emits ``(source, target, edge_type)`` with
        empty ``properties``, so the originating observation is recovered by
        joining each emitted pair back to the store's own edges. Deriving it
        anywhere else would mean a second, divergent notion of which edges exist.
        """
        tenant = self._tenant_id if tenant_id is None else tenant_id
        if not tenant:
            # An explicit empty tenant is a caller bug, and silently answering it
            # with the configured tenant would hand back another tenant's edges to
            # someone who has not identified themselves. `None` means "use yours";
            # `""` means "I have no tenant", which is refused.
            raise ValueError("edges_from requires a non-empty tenant_id")
        if node and not self._node_is_visible(node, tenant):
            return []

        # A single requested type is pushed into the reader so the store is asked
        # for one type and the emitted triples carry it. Two or more are left to
        # the stored-edge filter below: the reader stamps whatever type it was
        # given, so passing a set would mean passing a type that exists on no
        # edge, and the filter would then be applied against a value no edge can
        # ever match.
        reader_type = next(iter(self._edge_types)) if self._edge_types and len(self._edge_types) == 1 else None

        # node_ids=None enumerates the whole store; the reader de-duplicates on
        # (source, target, edge_type) and returns a deterministic sorted view.
        view = adjacency_from_store(
            self._store,
            node_ids=None if not node else [node],
            edge_type=reader_type,
            provenance={
                "event_id": "discovery.link_edge_provider",
                "tenant_id": tenant,
            },
        )
        by_pair = self._edges_by_pair()
        emitted: list[LinkEdge] = []
        # De-duplicated on the *resolved* edge, not on the emitted triple. The
        # reader visits both sides of an undirected relation, so the same stored
        # edge arrives twice under two different triples; keying on the triple
        # would let one relation be returned twice and, in a discovery pass that
        # enqueues per edge, queue the same neighbour twice. A store holding two
        # genuinely distinct parallel edges between the same pair keeps both,
        # because their edge_ids differ.
        seen: set[tuple[str, str, str, str]] = set()
        for edge in view.edges:
            resolved = self._resolve(edge, by_pair, tenant)
            if resolved is None:
                continue
            identity = (resolved.edge_id, resolved.source, resolved.target, resolved.edge_type)
            if identity in seen:
                continue
            seen.add(identity)
            emitted.append(resolved)
        emitted.sort(key=lambda e: (e.source, e.target, e.edge_type, e.edge_id))
        bound = self._limit if limit is None else limit
        return emitted[:bound] if bound >= 0 else emitted

    # -- internals ---------------------------------------------------------

    def _node_is_visible(self, node: str, tenant: str) -> bool:
        """A node that declares a different tenant is invisible, not an error.

        Refusing rather than raising keeps one foreign node in a shared graph
        from aborting a whole discovery pass, while still never returning that
        node's edges. A node that declares no tenant is not a cross-tenant node;
        the edge-level check in :meth:`_resolve` is what governs scope.

        A store that *raises* is allowed to propagate. A driver error from a
        Neo4j-backed store is a broken projection, and reporting it as "this node
        has no visible edges" would be indistinguishable from a real answer --
        which is the failure/empty conflation that ``DiscoveryReport`` exists to
        keep apart.
        """
        getter = getattr(self._store, "node", None)
        if getter is None:
            return True
        record = getter(node)
        if record is None:
            return False
        declared = (getattr(record, "properties", None) or {}).get("tenant_id")
        return declared in (None, tenant)

    def _edges_by_pair(self) -> dict[tuple[str, str], list[Any]]:
        """Index the store's own edges by unordered endpoint pair.

        The adjacency reader emits one entry per *side*, so a link from A to B
        and the same pair reported B to A must both be findable from one bucket;
        keying on the sorted endpoint pair is what makes that lookup work
        regardless of which side the reader happened to visit. Direction is
        re-established per edge in :meth:`_resolve`, because a bucket holding
        both A->B and B->A is the normal shape for a graph with parallel edges
        and dropping the distinction there would silently reverse half of them.
        """
        lister = getattr(self._store, "edges", None)
        if lister is None:
            return {}
        index: dict[tuple[str, str], list[Any]] = {}
        for edge in lister():
            pair = tuple(sorted((str(edge.source), str(edge.target))))
            index.setdefault(pair, []).append(edge)
        return index

    def _resolve(
        self, emitted: AdjacencyEdge, by_pair: dict[tuple[str, str], list[Any]], tenant: str
    ) -> LinkEdge | None:
        """Match one adjacency triple to a stored edge, or refuse it.

        The stored edge's own ``edge_type`` is what the ``edge_types`` filter is
        applied to, never the adjacency triple's: the reader stamps an empty
        type when it was not told one, and filtering against that would reject
        every edge the store actually holds.

        The stored edge with the same *direction* wins; the reverse direction is
        only consulted if the store has no forward one, which is what an
        undirected store looks like. Without that ordering a graph holding both
        A->B and B->A -- two different edges that both must be returned -- would
        hand back whichever sorted first, reversing one of them.

        ``None`` is returned for every reason the edge must not be emitted: no
        stored edge behind the pair, another tenant's edge, a filtered edge type,
        or an edge with no originating observation. Returning nothing is the
        point -- the alternative, an edge with an empty provenance string, is the
        shape that makes an unauditable edge indistinguishable from a
        well-formed one.
        """
        forward = (str(emitted.source), str(emitted.target))
        reverse = (forward[1], forward[0])
        bucket = by_pair.get(tuple(sorted(forward)), [])
        candidates = [edge for edge in bucket if _endpoints(edge) == forward]
        if not candidates:
            candidates = [edge for edge in bucket if _endpoints(edge) == reverse]
        if self._edge_types is not None:
            candidates = [edge for edge in candidates if str(edge.edge_type) in self._edge_types]
        candidates.sort(key=lambda edge: str(getattr(edge, "edge_id", "")))
        for edge in candidates:
            properties = getattr(edge, "properties", None) or {}
            if str(properties.get("tenant_id", "")) != tenant:
                continue  # fail closed: unowned or foreign
            observation_id = _observation_id(properties)
            if not observation_id:
                continue  # Constitution II: no path back to a raw object
            return LinkEdge(
                source=str(edge.source),
                target=str(edge.target),
                edge_type=str(edge.edge_type),
                observation_id=observation_id,
                edge_id=str(getattr(edge, "edge_id", "")),
            )
        return None


def _endpoints(edge: Any) -> tuple[str, str]:
    return (str(getattr(edge, "source", "")), str(getattr(edge, "target", "")))


def _observation_id(properties: dict[str, Any]) -> str:
    """The originating observation of an edge, or ``""`` if it has none.

    ``observation_id`` is the key the graph projection already writes
    (``adjacency.co_mention_adjacency``, ``graph/snapshot.py``), so it is the
    one this reader requires. A ``provenance`` sub-dict is accepted because a
    store that nests it has still named its evidence; a missing or blank value
    is not a provenance-bearing edge, whichever shape it was looked for in.
    """
    for source in (properties, properties.get("provenance") or {}):
        value = source.get("observation_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
        values = source.get("observation_ids")
        if isinstance(values, (list, tuple)) and values:
            first = str(values[0]).strip()
            if first:
                return first
    return ""


def canonical_host(uri: str) -> str:
    """Host of a canonical URL, or ``""`` -- a default ``host_key_of`` seam.

    Provided as the obvious implementation, not as a default: the injection point
    exists because the per-host budget policy owns host-key derivation, and
    silently binding this would let the adapter and the policy disagree about
    what "one host" means. Pass it explicitly:
    ``FrontierSinkAdapter(factory, host_key_of=canonical_host)``.
    """
    try:
        return (urlsplit(uri).hostname or "").lower()
    except ValueError:
        return ""
