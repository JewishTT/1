# Phase 0 Research: Discovery & Rebuildable Search Projection Fabric

**Feature**: `008-discovery-search-fabric` | **Date**: 2026-09-26

Every decision below is grounded in a file that exists in the tree today. The
distinguishing fact of this feature is that **most of it is already written**: Layer A
(`apps/acquisition/adapters/discovery/`) and Layer B (`apps/projection/search/`) both
exist, and the link-graph adjacency reader exists. What does not exist is the wiring,
the proof, and two pieces of the module graph. This document records what was found,
what was decided, and what was rejected.

---

## D1 — Restore `search/bm25s_backend.py` (it is missing, and its absence is a hard break)

**Finding.** `apps/projection/search/indexer.py:23` executes, at module import time:

```python
from search.bm25s_backend import BM25SRankedIndex
```

`apps/projection/search/bm25s_backend.py` **does not exist**. This is an unconditional
top-level import, not a guarded one, so *every* consumer of `search.indexer` fails at
collection — including `apps/projection/tests/test_relevance.py` and
`apps/projection/tests/test_bm25s_backend.py`, both of which are currently red for this
reason alone. `bm25s>=0.2` is a declared dependency in both
`apps/projection/pyproject.toml:14` and the workspace `pyproject.toml`, so the dependency
is present and the module is genuinely missing, not intentionally removed.

**Decision.** Implement `BM25SRankedIndex` as a real ranked index behind the same
duck-typed surface as `search/relevance.RankedInvertedIndex`, exposing a classmethod
`available() -> bool` and a `backend` tag of `"ranked-bm25s"`.

**Rejected: delete the import and fall back to the stdlib inverted index.** That would
make collection pass, but `test_bm25s_backend.py:136-137` pins
`default_ranked_index()` to return a `BM25SRankedIndex` whenever bm25s is importable.
Deleting the import deletes the test's subject, and the declared dependency becomes dead.
The feature is not "make the suite green"; the suite is the specification.

**Rejected: make the import lazy / optional inside `indexer.py`.** This would restore
collection while leaving `default_ranked_index()` unable to honour its own contract, and
it converts a loud, deterministic failure into a silent behavioural downgrade depending on
environment. A missing module in a declared dependency is a defect, not a configuration
state.

---

## D2 — "Kafka-native ingestion" is declared but never emitted

**Finding.** `apps/shared/events/topics.py` declares four relevant topics
(`discovery.seed` L20, `discovery.discovered` L21, `graph.projected` L47,
`search.projected` L50). A repository-wide search for producers of `discovery.discovered`,
`search.projected` and `graph.projected` returns **zero call sites** — the only hit for
`discovery.seed` is a prose mention in `apps/feedback/engine.py:70`.

Meanwhile the *consumer* side is fully declarative: `search/mappings.py:106-158`
(`index_config`) already emits a Quickwit indexing source of `source_type: "kafka"` bound
to `search.projected`, with `enable_backfill_mode: True` and a tenant/kind transform
filter. So the object-storage-resident, Kafka-native index described by FR-008 exists as a
*config document* with nothing feeding it.

**Decision.** The projector stays backend-agnostic and gains an explicit publish step: a
`SearchProjectionPublisher` that serialises each projected document onto `search.projected`
with `tenant_id` and `kind` intact (the transform filter at `mappings.py:150-154` depends on
both fields). The publisher is the only new component that touches Kafka, and it is
downstream of the idempotent write — publication must never be able to fail an index write,
and never be able to make a projection non-rebuildable.

**Rejected: have the `SearchIndex` implementations publish inline.** That would make the
index backend responsible for event transport, giving every backend (in-memory, bm25s,
Tantivy, Quickwit) a Kafka dependency and a failure mode. It also breaks the Protocol:
`SearchIndex` is deliberately a three-method contract (`index_doc`, `bulk_index_docs`,
`search`).

**Rejected: point Quickwit at the observation topic directly instead of `search.projected`.**
The index must contain *projected documents* (seven kinds, denormalised, provenance-stamped),
not raw observation envelopes. Reusing the observation topic would push document shaping
into a transform filter, where it is untestable and unversioned.

---

## D3 — Two incompatible frontier contracts must be bridged, not merged

**Finding.** Layer A declares its own sink protocol,
`apps/acquisition/adapters/discovery/registry.py:17-30`:

```python
class FrontierSink(Protocol):
    def enqueue(self, *, uri: str, tenant_id: str, investigation_id: str,
                source: str, method: str, priority: int = 0,
                provenance: dict[str, Any] | None = None) -> None: ...
```

The production frontier is
`apps/control-plane/services/frontier.py` — `async def enqueue(self, item: FrontierItem) -> bool`,
keyed on `FrontierItem.schedule_key()`, with dedup that *prefers higher priority* and
returns a bool. The two differ in **four** ways: sync vs async, keyword-args vs entity,
`int` vs the frontier's float priority, and `None` vs `bool` return.

**Decision.** Add `FrontierSinkAdapter` in `apps/control-plane/services/discovery_frontier.py`
implementing the Layer A protocol and delegating to the real frontier by constructing
`FrontierItem` rows. The discovery protocol is treated as fixed.

**Rejected: change `FrontierSink` to take a `FrontierItem`.** It would force every Layer A
test to construct a control-plane ORM row and to become async, destroying the property that
makes FR-005 provable in isolation — a hermetic, in-memory, synchronous sink
(`InMemoryFrontierSink`, registry.py:33-63). FR-005 says discovery enqueues into the durable
frontier; it does not say discovery must know the frontier's row type.

**Rejected: make discovery own a queue.** FR-005 and Constitution Invariant 5
("Kafka != object store") forbid it, and the spec's Out-of-scope section already excludes a
second frontier.

---

## D4 — The link-graph discovery source is already injectable; production must satisfy it

**Finding.** `apps/acquisition/adapters/discovery/linkgraph.py` takes an `edge_provider`
injection seam, and `apps/projection/graph/adjacency.py` already exposes everything a TDA
consumer needs: `AdjacencyView.to_tda_input()` (L42) returning
`(nodes, edges)`, `to_distance_matrix()` (L149), `co_mention_adjacency()` (L173),
`subgraph()` (L69), `degree_centrality()` (L59), and `adjacency_from_store()` (L116).
FR-013 is therefore substantially **already satisfied** — it is untested, not unimplemented.

**Decision.** Add a production `LinkEdgeProvider` that reads edges from the graph
projection via `adjacency_from_store`, and close FR-013 with contract tests over
`to_tda_input` rather than new graph code.

**Rejected: extend `DiscoverySource` with a `discover_from_edges` method.** One protocol,
one `discover(query)` entry point. The link-graph source already models itself as a
source that interprets its query as a node/observation; adding a second entry point
splits the contract for one adapter.

---

## D5 — Tenant isolation is fail-closed in code and must stay that way

**Finding.** `search/mappings.py:75-90` refuses an empty tenant for both
`physical_index_name` and `alias_name`; physical ids are `{kind}-{version}-{tenant}` and
queries resolve through a tenant alias. `search/quickwit.py:146-152` (`_prepare`) raises
`ValueError` on a document lacking `tenant_id`, and `search` raises `TenantIsolationError`
(L93). The behaviour is correct and **completely untested** — there is no `test_mappings.py`
and no `test_quickwit.py`.

**Decision.** Keep the fail-closed design; add the missing tests. No code change to the
isolation logic itself.

**Note on the version string.** `INDEX_VERSION = "v1"` is baked into the *physical index
name* (`mappings.py:81`). This satisfies FR-012's requirement that a generation be
reproducible, but it also means a mapping change requires a new physical index — which is
the correct behaviour for a projection, and worth stating explicitly rather than
discovering later.

---

## D6 — Fusion scoring is a no-op (real bug, contradicts Constitution IV)

**Finding.** `apps/control-plane/services/query_planner.py:100`:

```python
composite = EVIDENCE_BASE * max_score + (1 - EVIDENCE_BASE) * max_score
```

Both terms are `max_score`. The expression is algebraically equal to `max_score`; the
evidence-base weighting has no effect whatsoever. A backend returning a weak hit and a
backend returning overwhelming corroboration for the same `doc_id` fuse to the same score.

**Decision.** Replace with a genuine combination that keeps the components **separate**,
per Constitution IV ("no single score equates to truth"): backend relevance and
independent-support count are computed independently, combined by a declared formula, and
both are retained on `FusedResult` so a reader can re-derive or dispute the composite.

**Rejected: keep `max_score`.** It is simpler and it is already the behaviour — but it is
simplicity that discards evidence strength, and the fusion is the exact place where
"how many independent backends agree" is meaningful. It is also currently dressed up as a
weighted formula, which is worse than either alternative: it reads as deliberate.

---

## D7 — One failing backend currently kills the whole query (real bug, breaks FR-015)

**Finding.** `query_planner.py:85`:

```python
gathered = await asyncio.gather(*tasks.values())
```

No `return_exceptions=True`, and no per-backend `try`. A single backend raising — a Quickwit
timeout, a Neo4j connection refusal — propagates out of `execute()` and the user gets zero
results, including the ones the healthy backends could have answered. This directly
contradicts US5 scenario 2 and FR-015, and SC-006 cannot pass.

**Decision.** Isolate each backend call, record the failure with its exception type, let the
remaining backends contribute, and surface the degradation on the response
(`FusedResult.degraded_backends`) rather than swallowing it. A query that answered from
*zero* healthy backends must still raise — returning an empty result set because
everything failed is indistinguishable from "no matches", which is precisely the
ambiguity Constitution Invariant 9 exists to prevent.

---

## D8 — The document-kind list has already drifted once; make one source authoritative

**Finding.** `mappings.py:15-23` declares seven kinds; `projector.py:28-36` declares seven
`INDEX_ALIASES` — two independent hand-maintained lists that happen to agree today. The
feature's own specification said "six" while enumerating seven, which is the same drift
caught in documentation. There is no test relating the two lists.

**Decision.** `mappings.DOC_KINDS` becomes the single source of truth; the projector derives
`INDEX_ALIASES` from it. A contract test asserts the projector accepts exactly the declared
kinds and that `all_index_configs()` covers all of them, so a new kind cannot be added to one
list and forgotten in the other.

**Rejected: keep both lists and add a test comparing them.** A test that enforces agreement
between two sources is strictly worse than one source, because the second list still has to
be edited. One list plus a contract test is both smaller and safer.

---

## Summary of decisions

| # | Decision | Status in tree |
|---|---|---|
| D1 | Implement `BM25SRankedIndex`; do not delete the import | **missing module — hard break** |
| D2 | Add `SearchProjectionPublisher` → `search.projected` | topic declared, **no producer** |
| D3 | `FrontierSinkAdapter` bridges to the real frontier | protocols **incompatible** |
| D4 | `LinkEdgeProvider` over `adjacency_from_store` | seams exist, **unwired, untested** |
| D5 | Keep fail-closed tenant isolation; add tests | **correct but untested** |
| D6 | Real fusion formula, components stored separately | **no-op bug** |
| D7 | Per-backend failure isolation + surfaced degradation | **no-op bug (fails closed)** |
| D8 | `DOC_KINDS` is the single source of truth | **two lists, no test** |
