# Service Contracts: Discovery & Search Projection Fabric

**Feature**: `008-discovery-search-fabric` | **Date**: 2026-09-26

Status legend: **[EXISTS]** implemented in the tree · **[NEW]** introduced here ·
**[FIX]** exists with a defect this feature corrects.

---

## 1. `DiscoverySource` — **[EXISTS]**

`apps/acquisition/adapters/discovery/contracts.py:71-80`

```python
class DiscoverySource(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def capabilities(self) -> frozenset[str]: ...
    def discover(self, query: str) -> list[Candidate]: ...
```

**Contract rules**

1. `discover` is **total**: it either returns candidates or raises. It never returns `None`
   and never signals failure by returning an empty list — an empty list is a legitimate
   answer ("nothing found"), and conflating the two is what makes a dead source invisible.
2. `capabilities` is drawn from `{"index", "web-graph", "api"}` (FR-001). `index` = a
   data-driven URL index, `web-graph` = a link/adjacency source, `api` = a query interface.
3. A source MUST NOT require authentication, CAPTCHA solving or paywall traversal to answer
   (FR-018, Constitution VII). A source that cannot answer within this constraint MUST be
   refused at registration, not at query time — see §7.
4. `discover` MUST NOT mutate shared state and MUST be safe to call concurrently.
5. Every returned candidate MUST have passed `canonicalize` (non-http(s) dropped).

## 2. `FrontierSink` — **[EXISTS]** (Layer A side)

`registry.py:17-30`. Fixed by decision D3; the production implementation is §3.

```python
class FrontierSink(Protocol):
    def enqueue(self, *, uri: str, tenant_id: str, investigation_id: str,
                source: str, method: str, priority: int = 0,
                provenance: dict[str, Any] | None = None) -> None: ...
```

Sinks MUST be idempotent by canonical `uri` (FR-006). The return value is `None` by design:
callers learn the outcome from `DiscoveryReport.enqueued`, not from a per-call signal.

## 3. `FrontierSinkAdapter` — **[NEW]**

`apps/control-plane/services/discovery_frontier.py`

```python
class FrontierSinkAdapter:
    def __init__(self, frontier: FrontierService, *, host_key_of: Callable[[str], str]) -> None: ...
    def enqueue(self, *, uri: str, tenant_id: str, investigation_id: str,
                source: str, method: str, priority: int = 0,
                provenance: dict[str, Any] | None = None) -> None: ...
```

Bridges §2 to the real frontier (`async enqueue(item: FrontierItem) -> bool`).

**Rules**

1. MUST construct a `FrontierItem` with `uri` = the **canonical** URL, and MUST NOT set
   `state`, `lease_until`, `next_schedule_at` or `retries`. Frontier policy owns those
   (ADR-0016/0017); setting them from discovery would make discovery a scheduler.
2. MUST derive `host_key` via the injected `host_key_of` so per-host budget policy works.
3. MUST write the full `provenance` dict into the new `provenance` column (see
   `data-model.md` → Migration plan). Discarding it is a contract violation of FR-007.
4. `priority` is widened `int → float`; MUST NOT truncate or clamp.
5. Runs the async frontier call on the control-plane event loop. The `enqueue` call is
   **idempotent by `(tenant_id, uri)`** (unique index `uq_frontier_schedule`) and MUST NOT
   raise on the dedup path — a duplicate is a success, not an error.
6. MUST NOT create a second queue, table or cache (FR-017).

## 4. `SearchIndex` — **[EXISTS]**

`apps/projection/search/index.py:26-29`. Three methods, deliberately minimal.

```python
class SearchIndex(Protocol):
    def index_doc(self, doc: IndexedDoc) -> None: ...
    def bulk_index_docs(self, docs: list[IndexedDoc]) -> None: ...
    def search(self, index: str, query: str) -> list[str]: ...
```

**Rules**

1. `index_doc` MUST be idempotent on `doc_id` (FR-010, Invariant 11).
2. `index_doc` MUST reject a document lacking projection provenance
   (`enforce_projection_provenance`, `index.py:44`).
3. Implementations MUST raise `TenantIsolationError` (or a `PermissionError` subclass) on any
   attempt to address another tenant's index scope (FR-011) — **fail closed**, never return
   an empty result to hide a permission error.
4. Implementations MUST NOT hold or mutate relational state; an index is a rebuildable
   projection (FR-016, Constitution III).
5. Implementations MUST NOT publish to Kafka themselves (decision D2) — that is §6.

**Implementations in tree:** `InMemorySearchIndex` (tests/oracle), `QuickwitSearchIndex`
(Kafka-native ingest, object-storage index, `quickwit.py`), `RankedInvertedIndex`
(`relevance.py`, stdlib), `BM25SRankedIndex` (**to be restored**, D1), Tantivy backend
(`tantivy_backend.py`).

## 5. `SearchProjector` — **[EXISTS]**, alias list derived — **[FIX]**

`apps/projection/search/projector.py`

```python
class SearchProjector:
    def __init__(self, index: SearchIndex) -> None: ...
    def project(self, event: SearchEvent) -> None: ...
    def rebuild(self) -> None: ...
    def search(self, kind: str, query: str) -> list[str]: ...
```

**Rules**

1. `INDEX_ALIASES` MUST be derived from `mappings.DOC_KINDS` — one source of truth (D8).
2. `project` MUST reject an unknown kind with `ValueError` (`projector.py:45`).
3. `project` MUST attach provenance `{event_id, observation_id}`, defaulting to `doc_id`
   (`projector.py:50-53`).
4. `rebuild` MUST clear and re-project the durable batch (`projector.py:58-65`) and MUST be
   idempotent: rebuilding twice yields the identical document set (FR-010, SC-003, SC-010).
5. `rebuild` MUST NOT touch evidence or raw objects.

## 6. `SearchProjectionPublisher` — **[NEW]**

`apps/projection/search/publisher.py`

```python
class SearchProjectionPublisher:
    def __init__(self, bus: EventBus, *, topic: str = "search.projected") -> None: ...
    def publish(self, doc: IndexedDoc, kind: str, tenant_id: str) -> None: ...
```

The only new component that touches Kafka for the search plane (D2).

**Rules**

1. MUST emit one envelope per projected document on `search.projected`.
2. MUST reject a document whose body lacks `tenant_id` or `kind`. The Quickwit transform
   filter is `tenant_id == "<t>" && kind == "<k>"` (`mappings.py:150-154`); a document
   missing either is dropped by **every** index — silent, invisible data loss.
3. MUST be **downstream of the index write**. A publication failure MUST NOT roll back or
   fail the index write, and MUST leave the projection rebuildable (FR-016). The event log
   is the rebuild source, not the publisher's success.
4. MUST be idempotent on `(doc_id, tenant_id, kind)` so a replay does not double-emit.
5. MUST NOT block the projector on broker availability beyond the transport's own timeout.

## 7. `DiscoveryRegistry` — **[EXISTS]**

`apps/acquisition/adapters/discovery/registry.py:88-169`

```python
def register(self, source: DiscoverySource) -> None: ...
def discover(self, query: str, *, sources=None, frontier=None,
             tenant_id="default", investigation_id="", priority=0) -> DiscoveryReport: ...
```

**Rules**

1. A raising source MUST be recorded in `sources_failed` and MUST NOT abort the pass
   (`registry.py:128-130`).
2. A source returning nothing MUST be recorded in `empty_sources` — distinct from failure.
3. Coalescing happens before enqueue; one frontier row per canonical URL (FR-006).
4. `register` MUST refuse a source declaring a capability outside `{index, web-graph, api}`,
   and MUST refuse a source whose declared access mode requires bypassing access controls
   (FR-018) — at registration, so the refusal is auditable before any query is issued.
5. MUST NOT own a queue (FR-005, FR-017).

## 8. `LinkEdgeProvider` — **[NEW]** (production binding)

```python
class LinkEdgeProvider(Protocol):
    def edges_from(self, node: str, *, tenant_id: str,
                   limit: int = 1000) -> list[LinkEdge]: ...
```

Satisfied in production by a reader over the graph projection using
`adjacency_from_store` (`adjacency.py:116`). Injected into the existing `linkgraph.py`
source, which already accepts an `edge_provider` seam (D4).

**Rules**

1. MUST return only edges carrying provenance (originating observation id).
2. MUST be tenant-scoped.
3. MUST NOT re-derive entity identity; node ids are the shared keys of FR-014.

## 9. `GraphAdjacencyReader` (TDA) — **[EXISTS]**

`apps/projection/graph/adjacency.py`. FR-013 is satisfied by `AdjacencyView.to_tda_input()`
→ `(nodes, edges)`; this feature adds **tests**, not code (D4).

**Rules**

1. `to_tda_input` MUST return integer index triples over a stable node ordering.
2. `subgraph` MUST NOT re-derive ids.
3. The graph remains a projection: no analytical result is authoritative from it alone
   (Constitution Invariant 6: TDA ≠ truth oracle).

## 10. `BackendClient` — **[EXISTS]**

`apps/control-plane/services/query_planner.py:48-49`

```python
class BackendClient(Protocol):
    async def search(self, text: str, filters: QueryFilters, limit: int) -> list[BackendHit]: ...
```

**Rules**

1. A backend MAY raise. `QueryPlanner.execute` MUST isolate per-backend failures (D7) and
   surface them via `FusedResult.degraded_backends`.
2. If **every** selected backend fails, `execute` MUST raise — not return `[]` (Invariant 9).
3. `BackendHit.observation_id` MUST be resolvable; `_to_evidence` attaches the immutable
   observation (`query_planner.py:111-125`).

## 11. `QueryPlanner` — **[FIX]**

Two defects, both corrected here:

| Defect | Location | Correction |
|---|---|---|
| No failure isolation — `asyncio.gather` without `return_exceptions` | `query_planner.py:85` | per-backend isolation; `degraded_backends` populated; all-failed raises |
| Fusion is a no-op — `EVIDENCE_BASE * max + (1 - EVIDENCE_BASE) * max` ≡ `max` | `query_planner.py:100` | `relevance * (1 + EVIDENCE_BASE * (support - 1))`, with `relevance` and `support` retained separately (D6) |

**Rules**

1. `support` counts distinct `source_id`, never distinct backends — two backends reading one
   source are one piece of evidence (Constitution Governance).
2. `plan.assert_observational()` MUST pass before execution.
3. Fused results MUST be sorted by `composite` descending, deterministically (ties broken by
   `doc_id`) so identical inputs give identical output.

## 12. `IndexConfigRegistry` — **[NEW]** (declarative application)

```python
def all_index_configs(*, tenant: str, kafka_topic: str = "search.projected",
                      s3_bucket: str = "quickwit-indexes",
                      bootstrap_servers: str = "kafka:9092") -> list[dict]: ...
```

Exists (`mappings.py:161-178`) and needs no behaviour change. The contract is the
**invariant**: the generated config list MUST cover exactly `DOC_KINDS`, and each config's
`index_id` MUST equal `physical_index_name(kind, tenant)` and its `index_uri` MUST be under
the configured bucket. Deployment applies this list; it is the declarative artifact of
FR-008/FR-012.
