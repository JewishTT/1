"""Real query backends for the search plane (T026, US2).

The search endpoint is answered by two tenant-scoped ``BackendClient``s over the
projections the system already owns:

* ``SearchIndexBackendClient`` -- lexical retrieval over the search projection.
  Every index is reached through ``mappings.alias_name`` (ADR-0004), so a query
  for tenant ``t`` can only ever read ``<kind>-t`` indices, and the ranked core
  is given that same tenant.
* ``GraphBackendClient`` -- structural retrieval over the graph projection,
  ranked lexically and nudged by degree centrality, returning the *same*
  document ids the search projection uses for an entity (FR-014), so one entity
  is one fused result rather than two.

Both are thin by design: they translate ``QueryFilters`` into a projection
query and project what they found into ``BackendHit``. Neither decides what a
failure means. Isolation, the recoverable/unrecoverable verdict and the
failure-versus-empty distinction all stay in ``QueryPlanner``, which raises
``AllBackendsFailed`` for a total outage (Constitution Invariant 9).

Two rules are applied to every hit, in both backends:

* **it resolves to an immutable observation.** A hit whose ``observation_id``
  the ledger does not hold is dropped rather than returned with an empty
  evidence chain -- an evidence link that resolves to nothing is not evidence
  (Constitution I and II, I-1);
* **it belongs to the tenant.** Isolation is a property of the index and the
  store, not a filter applied afterwards, and a record whose owner cannot be
  established is invisible to everyone rather than to the caller who asked
  (fail closed, decision D5).

**Imports.** ``search`` is a contested top-level name: both
``apps/interpretation/search`` and ``apps/projection/search`` claim it, and
whichever directory lands on ``sys.path`` first wins, so ``import search.*``
here would bind a different module depending on the entrypoint. The projection's
two self-contained modules are therefore loaded from their files under private
names, the same reason ``api/routes/network.py`` bridges ``tda`` by path.
``graph`` is uncontested and imported normally.
"""

from __future__ import annotations

import importlib.util
import sys
import threading
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol

import path_shim  # noqa: F401 - keep apps/shared ahead of conflicting dirs
from graph.abstraction import GraphNode, GraphStore, InMemoryGraphStore
from graph.adjacency import adjacency_from_store
from sqlalchemy import select

from db.schema import Observation

# ``_error_text`` is the planner's own bounded ``type: message`` renderer, reused
# rather than reimplemented so a failure this module reports is word-for-word the
# failure the planner reports. ``degradations`` only ever reads it; deciding that
# a failure is recoverable stays with the planner.
from services.query_planner import (
    BackendHit,
    FusedResult,
    QueryFilters,
    QueryPlanner,
    _error_text,
)

# ---------------------------------------------------------------------------
# The search projection, loaded by path
# ---------------------------------------------------------------------------

_PROJECTION_DIR = Path(__file__).resolve().parents[2] / "projection"
_SEARCH_DIR = _PROJECTION_DIR / "search"


def _load_projection_module(name: str) -> ModuleType:
    """Load ``apps/projection/search/<name>.py`` under a private module name."""
    path = _SEARCH_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"projection_search_{name}", path)
    if spec is None or spec.loader is None:  # pragma: no cover - unreadable install
        raise ImportError(f"cannot load the search projection module at {path}")
    module = importlib.util.module_from_spec(spec)
    # Registered before execution so dataclasses defined in the module resolve
    # annotations against a module object that already exists in sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_mappings: ModuleType = _load_projection_module("mappings")
_relevance: ModuleType = _load_projection_module("relevance")

#: The kinds the search projection can hold, from the projection's own mapping.
#: A document of any other kind is unroutable and is refused rather than indexed
#: under a name no index filter would match.
DOC_KINDS: tuple[str, ...] = tuple(_mappings.DOC_KINDS)

#: Tenant-scoped index resolution (ADR-0004). Raises for an unknown kind or an
#: empty tenant, which is what makes a missing tenant fail closed.
alias_name = _mappings.alias_name

tokenize = _relevance.tokenize
RankedInvertedIndex = _relevance.RankedInvertedIndex

#: Result ceiling for one request. The planner slices to the caller's ``limit``
#: after fusing, so this only bounds the work a single query can ask for.
MAX_LIMIT = 200

#: How much wider than the caller's ``limit`` a backend reads before filtering.
#: ``source_ids``/temporal/investigation filters and the observation guard all
#: run *after* ranking, so a pool of exactly ``limit`` would answer "no matches"
#: whenever the first ``limit`` hits happened to be filtered out. A filtered
#: result set is therefore bounded by the pool, not by the limit.
POOL_FACTOR = 10
POOL_MAX = 500

#: Document fields that may carry the instant a projection observed, newest
#: naming first. ``produced_at`` is written by the search projection's publisher
#: on every ingest document, so it is the last resort rather than the first.
_TIMESTAMP_FIELDS = ("observed_at", "timestamp", "produced_at", "ingested_at", "created_at")

#: Node properties searched lexically by the graph backend. A declared list, not
#: a walk over every property: an arbitrary property holding an unrelated id is
#: not a name, and matching on it would return nodes nobody searched for.
_GRAPH_LEXICAL_FIELDS = (
    "name",
    "canonical_name",
    "aliases",
    "label",
    "title",
    "description",
    "value",
)


class TenantScopeError(PermissionError):
    """A query with no tenant to scope it to.

    A ``PermissionError`` rather than a ``ValueError`` because the caller is the
    problem, not the request: an unscoped query would read across every tenant's
    indices, and "it usually works without a tenant" is how that leak happens.
    """


class GraphNodesUnreadable(RuntimeError):
    """The graph store cannot enumerate its nodes and no node ids were supplied.

    Reported rather than answered with an empty result. A store the backend
    cannot read is a broken projection, and ``[]`` from it would be
    indistinguishable from a tenant that genuinely has no entities -- the
    failure/empty conflation Invariant 9 exists to prevent.
    """


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------


def parse_instant(value: Any) -> datetime | None:
    """An ISO-8601 date or instant as an aware UTC datetime, or ``None``.

    A naive value is read as UTC. An unparsable one is ``None`` rather than a
    guess: a caller that sent a bound this function cannot understand must not
    be answered with results filtered by a different bound than it asked for.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text[-1] in ("Z", "z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _document_instant(document: Mapping[str, Any]) -> datetime | None:
    """The instant a projected document is about, or ``None`` if it states none."""
    for field_name in _TIMESTAMP_FIELDS:
        moment = parse_instant(document.get(field_name))
        if moment is not None:
            return moment
    return None


# ---------------------------------------------------------------------------
# Observation ledger
# ---------------------------------------------------------------------------


class ObservationLedger(Protocol):
    """The authority that says an observation exists and is immutable (I-1)."""

    async def get(self, observation_id: str) -> dict[str, Any] | None: ...


@dataclass
class InMemoryObservationLedger:
    """The observations this process holds, keyed by id.

    An in-process registry of the immutable records behind the projection, not
    the ``observations`` table: it answers the only question a hit has to pass
    -- *is this an observation we actually hold?* -- which is what makes a
    dangling ``observation_id`` in an indexed document a dropped hit instead of
    an evidence link that resolves to nothing.

    ``PostgresObservationLedger`` binds the same question to the authoritative
    table; where that table is the authority, bind it on the registry.
    """

    records: dict[str, dict[str, Any]] = field(default_factory=dict)

    def put(self, record: Mapping[str, Any]) -> None:
        """Record one immutable observation. Ids are passed through, never minted."""
        observation_id = str(record.get("observation_id") or "").strip()
        if not observation_id:
            raise ValueError("an observation record requires observation_id")
        self.records[observation_id] = dict(record)

    async def get(self, observation_id: str) -> dict[str, Any] | None:
        record = self.records.get(observation_id)
        return dict(record) if record is not None else None


@dataclass
class PostgresObservationLedger:
    """Observation ledger bound to the authoritative ``observations`` table.

    A row that is not there is a dangling reference, and a row belonging to
    another tenant is not this caller's evidence; both are ``None``, so the hit
    is dropped by the same rule either way.
    """

    session_factory: Any

    async def get(self, observation_id: str) -> dict[str, Any] | None:
        async with self.session_factory() as session:
            result = await session.execute(
                select(Observation).where(Observation.observation_id == observation_id)
            )
            record = result.scalar_one_or_none()
        if record is None:
            return None
        return {
            "observation_id": record.observation_id,
            "uri": record.uri,
            "content_hash": record.content_hash,
            "investigation_id": record.investigation_id,
            "source_id": record.source_id,
            "tenant_id": record.tenant_id,
        }


class ObservationView(Mapping):
    """The observations one query resolved, read by the planner's evidence links.

    Each request builds one and hands the same object to both backends and to the
    planner, so an evidence link can only ever name an observation this very
    query proved it has.

    ``__bool__`` is always ``True`` and that is deliberate wiring, not a claim
    about the results. ``QueryPlanner`` substitutes a fresh dict for a *falsy*
    ``observations`` argument (``observations or {}``), and a view is empty at
    plan time only because nothing has been resolved yet -- the backends fill it
    while they run. A truthful emptiness here would silently detach every
    evidence link from its observation.
    """

    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}

    def record(self, observation_id: str, observation: Mapping[str, Any]) -> None:
        self._records[observation_id] = dict(observation)

    def __getitem__(self, observation_id: str) -> dict[str, Any]:
        return self._records[observation_id]

    def __iter__(self) -> Iterator[str]:
        return iter(self._records)

    def __len__(self) -> int:
        return len(self._records)

    def __bool__(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# The search projection
# ---------------------------------------------------------------------------


@dataclass
class SearchProjectionStore:
    """Ranked retrieval plus the document bodies it scored.

    The ranked core (``relevance.RankedInvertedIndex``, the same dependency-free
    BM25 core ``indexer.default_ranked_index()`` falls back to) owns ranking and
    per-tenant isolation, and deliberately does not hand back the body a document
    was indexed from: ``results()`` returns a ``RelevanceHit``, which carries
    text and a snippet and nothing else. Filtering and evidence need the body --
    ``observation_id``, ``source_id``, ``investigation_id``, the temporal field
    -- so the store keeps it beside the index under the same ``doc_id``, passed
    through unchanged (FR-014).

    The core is injectable: ``SearchProjectionStore(index=BM25SRankedIndex())``
    swaps in the accelerated core without touching anything else.
    """

    index: Any = None
    bodies: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.index is None:
            self.index = RankedInvertedIndex()

    def put(
        self,
        *,
        doc_id: str,
        kind: str,
        body: Mapping[str, Any],
        tenant_id: str,
        provenance: Mapping[str, Any],
    ) -> bool:
        """Index one document under its tenant alias. ``False`` on a duplicate.

        ``alias_name`` is what names the index, so an unknown kind or an empty
        tenant raises here rather than producing a document nothing will ever
        query (FR-011).
        """
        stored = self.index.put(
            doc_id=doc_id,
            index=alias_name(kind, tenant_id),
            body=dict(body),
            tenant_id=tenant_id,
            provenance=dict(provenance),
        )
        if stored:
            self.bodies[doc_id] = {**dict(body), "doc_id": doc_id, "kind": kind, "tenant_id": tenant_id}
        return stored

    def body(self, doc_id: str) -> dict[str, Any] | None:
        record = self.bodies.get(doc_id)
        return dict(record) if record is not None else None

    def results(self, query: str, *, top_k: int, tenant_id: str) -> list[Any]:
        return self.index.results(query, top_k=top_k, tenant_id=tenant_id)

    def aliases(self, tenant_id: str) -> dict[str, str]:
        """``kind -> tenant alias`` for every routable kind.

        Built up front so an unroutable kind is refused before the query runs,
        rather than surfacing as a hit the caller cannot trace back to an index.
        """
        if not tenant_id:
            raise TenantScopeError("a search query requires a tenant")
        return {kind: alias_name(kind, tenant_id) for kind in DOC_KINDS}

    def size(self, tenant_id: str | None = None) -> int:
        return int(self.index.size(tenant_id))

    def clear(self) -> None:
        self.bodies.clear()
        self.index.clear()


# ---------------------------------------------------------------------------
# Shared client plumbing
# ---------------------------------------------------------------------------


def _source_id(document: Mapping[str, Any]) -> str | None:
    """The source a projection attributes, or ``None``.

    ``None`` is not a placeholder to be filled in: ``QueryPlanner`` counts
    distinct non-empty source ids as corroboration, so a hit with no attribution
    earns none (``_composite``), which is the correct outcome for a document that
    does not say where it came from.
    """
    provenance = document.get("provenance")
    candidates = [document.get("source_id")]
    if isinstance(provenance, Mapping):
        candidates.append(provenance.get("source_id"))
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value:
            return value
    return None


def _observation_id(document: Mapping[str, Any]) -> str | None:
    """The observation a projection document is evidence of, or ``None``.

    The ``observations`` index is the projection of the observations themselves,
    so its own document id *is* the observation id -- the one place a document id
    may stand in for one, and only because that index holds nothing else.
    """
    value = str(document.get("observation_id") or "").strip()
    if value:
        return value
    if str(document.get("kind") or "") == "observations":
        return str(document.get("doc_id") or "").strip() or None
    return None


def _matches_filters(document: Mapping[str, Any], filters: QueryFilters) -> bool:
    """Whether one projection document satisfies the caller's filters.

    Every field of ``QueryFilters`` is honoured, and each is **fail closed**: a
    filter the document cannot be checked against does not pass. A caller that
    asked for one investigation, or for a window in time, must not be handed a
    document that is silent on which investigation or when it belongs to -- the
    answer would be indistinguishable from a real match.
    """
    if filters.investigation_id and str(document.get("investigation_id") or "") != filters.investigation_id:
        return False
    if filters.source_ids and (_source_id(document) or "") not in filters.source_ids:
        return False
    if filters.temporal_from or filters.temporal_to:
        instant = _document_instant(document)
        if instant is None:
            return False
        lower = parse_instant(filters.temporal_from) if filters.temporal_from else None
        upper = parse_instant(filters.temporal_to) if filters.temporal_to else None
        if lower is None or upper is None:
            # A bound the filter carries but this module cannot read: refuse
            # rather than answer as if no bound had been asked for.
            return False
        if instant < lower or instant > upper:
            return False
    return True


async def _resolve(
    *,
    ledger: ObservationLedger,
    view: ObservationView,
    observation_id: str,
    tenant_id: str,
) -> dict[str, Any] | None:
    """The observation a hit's evidence chain resolves to, or ``None``.

    ``None`` means the hit is dropped, and it covers both ways a chain can be
    broken: an observation the ledger does not hold, and one held by another
    tenant. A ledger that raises is *not* caught here -- a broken authority
    degrades the whole backend through the planner, which is the honest outcome,
    rather than quietly emptying one result list.
    """
    record = await ledger.get(observation_id)
    if record is None:
        return None
    declared = str(record.get("tenant_id") or "")
    if declared and declared != tenant_id:
        return None
    resolved = {
        "observation_id": str(record.get("observation_id") or observation_id),
        "uri": record.get("uri"),
        "content_hash": record.get("content_hash"),
    }
    view.record(resolved["observation_id"], {**record, **resolved})
    return resolved


class _AuditedClient:
    """Mixin: the calls *this* client raised, for the response body.

    ``QueryPlanner`` decides what a failure means and attaches its own
    ``degraded_backends`` to every result it returns. It cannot attach one to a
    query that returned nothing, though: a partial outage whose healthy backends
    all found no matches has no result to carry the notice. This records that
    the call happened and failed, so ``degradations`` can name it -- nothing
    here decides whether the query was recoverable.
    """

    name: str

    def _record_failure(self, exc: BaseException) -> None:
        self.failures.append(
            {"backend": self.name, "error": _error_text(exc), "recoverable": True}
        )


# ---------------------------------------------------------------------------
# Backend: the search projection
# ---------------------------------------------------------------------------


@dataclass
class SearchIndexBackendClient(_AuditedClient):
    """Lexical retrieval over the search projection, scoped to one tenant."""

    tenant_id: str = ""
    store: SearchProjectionStore | None = None
    ledger: ObservationLedger | None = None
    view: ObservationView | None = None
    name: str = "search"
    failures: list[dict[str, Any]] = field(default_factory=list)

    async def search(self, text: str, filters: QueryFilters, limit: int) -> list[Any]:
        try:
            return await self._search(text, filters, limit)
        except Exception as exc:
            self._record_failure(exc)
            raise

    async def _search(self, text: str, filters: QueryFilters, limit: int) -> list[Any]:
        if self.store is None or self.ledger is None or self.view is None:
            raise ValueError("the search backend needs a store, a ledger and a view")
        if not self.tenant_id:
            raise TenantScopeError("the search backend requires a tenant")

        aliases = self.store.aliases(self.tenant_id)
        pool = min(max(int(limit), 1) * POOL_FACTOR, POOL_MAX)
        found = self.store.results(text, top_k=pool, tenant_id=self.tenant_id)
        best = max((float(hit.score) for hit in found), default=0.0)

        hits: list[Any] = []
        for hit in found:
            document = self.store.body(hit.doc_id)
            if document is None:
                continue  # a ranked hit with no body cannot be filtered or evidenced
            kind = str(document.get("kind") or "")
            if kind not in aliases:
                continue  # unroutable kind: no index filter would ever match it
            if not _matches_filters(document, filters):
                continue
            observation_id = _observation_id(document)
            if observation_id is None:
                continue
            resolved = await _resolve(
                ledger=self.ledger,
                view=self.view,
                observation_id=observation_id,
                tenant_id=self.tenant_id,
            )
            if resolved is None:
                continue
            hits.append(
                BackendHit(
                    doc_id=str(hit.doc_id),
                    kind=kind,
                    # Normalised to the best hit in this result set: BM25 scores
                    # are unbounded and term-frequency dependent, and the planner
                    # fuses a raw score with a support count, so a raw BM25 value
                    # would let a long document outrank a short exact one for
                    # reasons the caller cannot see.
                    score=round(float(hit.score) / best, 6) if best > 0 else 0.0,
                    backend=self.name,
                    observation_id=resolved["observation_id"],
                    source_id=_source_id(document),
                    payload={
                        "reason": f"lexical match in {aliases[kind]}",
                        "text": hit.snippet or hit.text,
                        "investigation_id": document.get("investigation_id"),
                    },
                )
            )
        hits.sort(key=lambda h: (-h.score, h.doc_id))
        return hits[: max(int(limit), 0)]


# ---------------------------------------------------------------------------
# Backend: the graph projection
# ---------------------------------------------------------------------------


@dataclass
class GraphBackendClient(_AuditedClient):
    """Structural retrieval over the graph projection, scoped to one tenant.

    Ranked lexically over a node's declared name-ish properties, then adjusted
    by degree centrality so a well-connected node is reachable by the terms that
    describe it. It shares the search projection's document ids (FR-014), which
    is what lets ``QueryPlanner`` fuse a graph hit and a lexical hit for the same
    entity into one result with two pieces of evidence.
    """

    tenant_id: str = ""
    store: GraphStore | Any = None
    ledger: ObservationLedger | None = None
    view: ObservationView | None = None
    node_ids: tuple[str, ...] | None = None
    edge_types: frozenset[str] | None = None
    degree_weight: float = 0.2
    name: str = "graph"
    failures: list[dict[str, Any]] = field(default_factory=list)

    async def search(self, text: str, filters: QueryFilters, limit: int) -> list[Any]:
        try:
            return await self._search(text, filters, limit)
        except Exception as exc:
            self._record_failure(exc)
            raise

    async def _search(self, text: str, filters: QueryFilters, limit: int) -> list[Any]:
        if self.store is None or self.ledger is None or self.view is None:
            raise ValueError("the graph backend needs a store, a ledger and a view")
        if not self.tenant_id:
            raise TenantScopeError("the graph backend requires a tenant")

        terms = set(tokenize(text))
        if not terms:
            return []

        visible = self._visible_nodes()
        if not visible:
            return []
        # A single requested edge type is pushed into the reader so the store is
        # asked for one type; two or more are left unfiltered here and the
        # reader stamps whatever it is given, exactly as `LinkEdgeProvider` does.
        reader_type = next(iter(self.edge_types)) if self.edge_types and len(self.edge_types) == 1 else None
        view = adjacency_from_store(
            self.store,
            node_ids=[node.node_id for node in visible],
            edge_type=reader_type,
            provenance={"event_id": "services.search_backends", "tenant_id": self.tenant_id},
        )
        centrality = view.degree_centrality()

        hits: list[Any] = []
        for node in visible:
            overlap = len(terms & set(tokenize(_lexical_text(node))))
            if not overlap:
                continue  # a node that does not match the query is not a result
            document = {**node.properties, "doc_id": node.node_id, "kind": _node_kind(node)}
            if not _matches_filters(document, filters):
                continue
            observation_id = _observation_id(document)
            if observation_id is None:
                continue
            resolved = await _resolve(
                ledger=self.ledger,
                view=self.view,
                observation_id=observation_id,
                tenant_id=self.tenant_id,
            )
            if resolved is None:
                continue
            structural = centrality.get(node.node_id, 0) / (centrality.get(node.node_id, 0) + 1)
            lexical = overlap / len(terms)
            hits.append(
                BackendHit(
                    doc_id=node.node_id,
                    kind=_node_kind(node),
                    score=round(
                        (1 - self.degree_weight) * lexical + self.degree_weight * structural, 6
                    ),
                    backend=self.name,
                    observation_id=resolved["observation_id"],
                    source_id=_source_id(node.properties),
                    payload={
                        "reason": f"graph node {node.node_id} matched {overlap}/{len(terms)} terms",
                        "node_type": node.node_type,
                        "investigation_id": node.properties.get("investigation_id"),
                    },
                )
            )
        hits.sort(key=lambda h: (-h.score, h.doc_id))
        return hits[: max(int(limit), 0)]

    def _visible_nodes(self) -> list[GraphNode]:
        """The tenant's nodes, and nothing else.

        A node declaring another tenant is invisible. A node declaring *no*
        tenant is invisible too: an owner that cannot be established cannot
        safely be attributed to the caller, and returning it "usually works"
        fails open -- the same rule ``LinkEdgeProvider`` applies to edges.
        """
        lister = getattr(self.store, "nodes", None)
        if lister is not None:
            nodes = list(lister())
        elif self.node_ids:
            getter = getattr(self.store, "node", None)
            if getter is None:
                raise GraphNodesUnreadable(
                    "the graph store exposes neither nodes() nor node() for the ids supplied"
                )
            nodes = [found for found in (getter(node_id) for node_id in self.node_ids) if found]
        else:
            raise GraphNodesUnreadable(
                "the graph store cannot enumerate nodes; supply node_ids to read it"
            )
        return [
            node
            for node in nodes
            if str((getattr(node, "properties", None) or {}).get("tenant_id") or "") == self.tenant_id
        ]


def _lexical_text(node: GraphNode) -> str:
    """The declared name-ish properties of a node, as one searchable string."""
    properties = node.properties or {}
    parts: list[str] = []
    for name in _GRAPH_LEXICAL_FIELDS:
        value = properties.get(name)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, (list, tuple)):
            parts.extend(str(item) for item in value)
    return " ".join(parts)


def _node_kind(node: GraphNode) -> str:
    """The result kind a graph node is reported as.

    A node type that is a routable document kind is reported as itself; every
    other node type is reported as an ``entity``, which is what a graph node is
    in this system and what the planner's supported routes name.
    """
    node_type = str(node.node_type or "")
    return node_type if node_type in DOC_KINDS else "entity"


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------


def degradations(planner: QueryPlanner, results: list[FusedResult]) -> list[dict[str, Any]]:
    """Every backend that failed this query, for the response body.

    The planner's own list wins, read off the results it returned. The clients'
    recorded failures cover the case the planner cannot express on its own: a
    partial outage whose healthy backends all found nothing, which would
    otherwise answer ``200 {"results": []}`` with no degradation named at all.
    Reading the planner's backend table is deliberate -- it is the same process's
    own map, and re-deriving the backend list from the plan would guess.
    """
    named: dict[str, dict[str, Any]] = {}
    for result in results:
        for entry in result.degraded_backends:
            named[entry["backend"]] = entry
    if named:
        return sorted(named.values(), key=lambda entry: entry["backend"])
    for client in planner._backends.values():
        for entry in getattr(client, "failures", ()):
            named[entry["backend"]] = entry
    return sorted(named.values(), key=lambda entry: entry["backend"])


def build_query_planner(
    tenant_id: str,
    *,
    store: SearchProjectionStore | None = None,
    graph_store: GraphStore | Any | None = None,
    ledger: ObservationLedger | None = None,
) -> QueryPlanner:
    """Assemble one tenant's planner: the lexical client and the graph client.

    The common call is ``build_query_planner(ctx.tenant_id)``, which reads the
    process-wide projection. ``store``/``graph_store``/``ledger`` exist so a
    process can bind its own projections -- Quickwit, Neo4j, the ``observations``
    table -- without this factory knowing about any of them.

    Fresh clients and a fresh observation view per call: nothing one query
    resolved or failed is visible to the next.
    """
    projection = _REGISTRY
    # One read of the current generation: the index and the ledger must come from
    # the same one, or a rebuild landing between two reads would pair a fresh
    # index with a stale ledger and resolve no evidence at all.
    generation = projection.generation
    view = ObservationView()
    return QueryPlanner(
        backends={
            "search": SearchIndexBackendClient(
                tenant_id=tenant_id,
                store=store if store is not None else generation.store,
                ledger=ledger if ledger is not None else generation.observations,
                view=view,
            ),
            "graph": GraphBackendClient(
                tenant_id=tenant_id,
                store=graph_store if graph_store is not None else projection.graph_store,
                ledger=ledger if ledger is not None else generation.observations,
                view=view,
            ),
        },
        observations=view,
    )


@dataclass(frozen=True)
class SearchGeneration:
    """One generation of the search projection: ranked index, bodies, ledger.

    The three move together or not at all. A rebuild publishes a whole new
    generation, so a query can never pair a replayed index with the ledger of the
    generation it replaced -- which would resolve no evidence and look, from the
    outside, exactly like a projection with nothing in it.
    """

    store: SearchProjectionStore
    observations: InMemoryObservationLedger


@dataclass
class SearchProjectionRegistry:
    """The process-wide search projection: generation, graph store.

    The composition root for the search plane. Writers (``index_document``,
    ``record_observation``, ``write_node``, ``write_edge``) go through it, and
    ``replace_generation`` publishes a rebuilt projection in one assignment, so a
    rebuild never leaves a query reading a half-replayed generation.
    """

    generation: SearchGeneration = field(
        default_factory=lambda: SearchGeneration(
            store=SearchProjectionStore(), observations=InMemoryObservationLedger()
        )
    )
    graph_store: GraphStore | Any = field(default_factory=InMemoryGraphStore)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)

    def planner(self, tenant_id: str) -> QueryPlanner:
        return build_query_planner(tenant_id)

    def index_document(
        self,
        *,
        doc_id: str,
        kind: str,
        body: Mapping[str, Any],
        tenant_id: str,
        provenance: Mapping[str, Any],
    ) -> bool:
        """Index one document, and register the observation it *is*.

        ``provenance`` is required and must name the event that produced the
        document (I-12); the observation is filled in from the body when the
        caller did not state it, because the body is where it already lives.

        Only an ``observations`` document registers an observation record. A
        document of any other kind *references* one, and a reference is not a
        registration: letting a citing document vouch for the observation it
        cites would make every reference resolvable by construction and turn the
        evidence guard into a tautology. An observation enters the ledger when the
        observation itself is projected, or when a caller holding the immutable
        record states it through ``record_observation``.
        """
        source = dict(provenance)
        observation = body.get("observation_id") or (doc_id if kind == "observations" else None)
        if observation:
            source.setdefault("observation_id", observation)
        with self._lock:
            if kind == "observations" and observation:
                self.generation.observations.put(
                    _observation_record(observation, body, tenant_id)
                )
            return self.generation.store.put(
                doc_id=doc_id, kind=kind, body=body, tenant_id=tenant_id, provenance=source
            )

    def record_observation(self, record: Mapping[str, Any]) -> None:
        """Register one immutable observation the caller already holds.

        The way an observation enters the ledger without being projected as a
        search document: the writer that received it states the record here, and
        every document that references it can then resolve its evidence chain.
        """
        with self._lock:
            self.generation.observations.put(record)

    def write_node(self, node: GraphNode, provenance: Mapping[str, Any]) -> None:
        with self._lock:
            self.graph_store.write_node(node, dict(provenance))

    def write_edge(self, edge: Any, provenance: Mapping[str, Any]) -> None:
        with self._lock:
            self.graph_store.write_edge(edge, dict(provenance))

    def replace_generation(self, generation: SearchGeneration) -> None:
        """Publish a rebuilt projection. Readers swap over on their next request.

        The generation handed in is published whole and the previous one is
        dropped unread: a rebuild proves the index is a projection by deriving it
        from the event log alone, so consulting what was there before would make
        the result depend on the thing being tested.
        """
        with self._lock:
            self.generation = generation


def _observation_record(
    observation_id: str, body: Mapping[str, Any], tenant_id: str
) -> dict[str, Any]:
    """The ledger record for one projected observation. Ids passed through."""
    return {
        "observation_id": observation_id,
        "uri": body.get("uri"),
        "content_hash": body.get("content_hash"),
        "investigation_id": body.get("investigation_id"),
        "source_id": body.get("source_id"),
        "tenant_id": tenant_id,
    }


_REGISTRY = SearchProjectionRegistry()


def search_projection() -> SearchProjectionRegistry:
    """The process-wide search projection registry."""
    return _REGISTRY


__all__ = [
    "DOC_KINDS",
    "MAX_LIMIT",
    "GraphBackendClient",
    "GraphNodesUnreadable",
    "InMemoryObservationLedger",
    "ObservationLedger",
    "ObservationView",
    "PostgresObservationLedger",
    "SearchGeneration",
    "SearchIndexBackendClient",
    "SearchProjectionRegistry",
    "SearchProjectionStore",
    "TenantScopeError",
    "alias_name",
    "build_query_planner",
    "degradations",
    "parse_instant",
    "search_projection",
]
