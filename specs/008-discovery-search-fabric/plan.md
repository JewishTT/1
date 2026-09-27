# Implementation Plan: Discovery & Rebuildable Search Projection Fabric

**Branch**: `008-discovery-search-fabric` | **Date**: 2026-09-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/008-discovery-search-fabric/spec.md`

## Summary

Close the two remaining halves of the collection loop — finding URLs before crawling them, and
making what was collected searchable — but do it as **wiring, proof and two bug fixes**, not as
new subsystems. Both layers already exist in the tree:

- **Layer A** — `apps/acquisition/adapters/discovery/` already provides `Candidate`,
  `canonicalize`, `coalesce`, `DiscoveryRegistry`, `InMemoryFrontierSink` and four sources
  (Common Crawl columnar index, Wayback CDX, certificate transparency, link-graph).
- **Layer B** — `apps/projection/search/` already provides the `SearchIndex` contract, the
  `SearchProjector` with seven document kinds, versioned declarative mappings
  (`mappings.index_config()` already generates a **Kafka-source, S3-resident** index config),
  and a Quickwit backend with fail-closed tenant isolation.

What does not exist is the part that makes any of it true: **no producer for three declared
topics**, **no production binding from discovery to the real frontier**, **no production
`LinkEdgeProvider`**, and **no tests at all** for the discovery package, the mappings, or the
Quickwit backend. Two production defects also sit directly on this feature's requirements.

Three things are broken or missing **right now**, verified by running the suite:

| # | Finding | Evidence |
|---|---|---|
| 1 | `search/indexer.py:23` imports `search.bm25s_backend`, which **does not exist** → `ModuleNotFoundError` interrupts collection of the whole projection suite (2 errors, 164 tests collected) | `uv run --project apps/projection pytest apps/projection/tests --collect-only -q` |
| 2 | `QueryPlanner.execute` has no per-backend failure isolation (`query_planner.py:85`) → one sick backend returns **zero** results, breaking FR-015 / SC-006 | code read |
| 3 | Fusion scoring is algebraically a no-op: `EVIDENCE_BASE * max + (1 - EVIDENCE_BASE) * max` ≡ `max` (`query_planner.py:100`) → evidence strength is discarded, against Constitution IV | code read |

Plus one data-loss gap: `frontier_items` has **no provenance column**, so FR-007's provenance
cannot survive the Layer A → frontier bridge.

So the work is: restore the missing module, fix the two defects, add the producer, add the two
production bindings, add the migration, and — the largest single item by volume — **write the
tests that make any of the existing code provable**. `frontier_items.provenance` is the only
schema change.

## Technical Context

**Language/Version**: Python 3.11+ (all touched apps), TypeScript 5.5 strict (not touched —
this feature has no frontend surface)

**Primary Dependencies**: no new runtime dependency. `bm25s>=0.2` is **already declared**
(`apps/projection/pyproject.toml:14`) — the module that uses it is missing, not the package.
Existing: FastAPI, SQLAlchemy 2.0, asyncpg, httpx, Neo4j driver, pytest + pytest-asyncio
(`asyncio_mode = "auto"`).

**Storage**: PostgreSQL (frontier — one new JSONB column), Neo4j (graph projection, unchanged),
S3-compatible object storage (search index generations), Kafka/Redpanda (event backbone).

**Testing**: `uv run --project apps/<app> pytest apps/<app>/tests -q` (per-app uv workspace)

**Target Platform**: Linux server + Docker/Kubernetes (existing deployment)

**Project Type**: Python monorepo (`apps/*` uv workspace members)

**Performance Goals**: the publisher must sit **off** the projector's critical path — a
broker hiccup may never delay or fail an index write, because the event log is the rebuild
source. Discovery dedup is pure and in-memory; canonicalisation must stay allocation-light
(it runs per candidate).

**Constraints**: no new orchestration backbone and no second frontier (FR-017); no access-control
bypass (FR-018, Constitution VII); every projection write rebuildable and provenance-bearing
(FR-016); the previous Alembic revision is immutable; discovery MUST NOT become a scheduler —
`state`, `lease_until`, `next_schedule_at` belong to frontier policy (ADR-0016/0017).

**Scale/Scope**: 4 discovery sources, 7 document kinds, 1 migration column, 3 new modules,
2 new route groups, 1 new publisher, 2 defect fixes, ~10 new test modules.

## Constitution Check

| Gate | Result |
|---|---|
| **I. Observation-Immutable Evidence Substrate** | PASS — nothing writes observations. Discovery produces *candidates* (Invariant 2: ≠ observation); the index is a projection. |
| **II. Evidence-First** | PASS — provenance is a **precondition of write** (`enforce_projection_provenance`, `index.py:44`), not an optional field, and is extended to the frontier by the new column. |
| **III. Projection-First Knowledge Architecture** | PASS — the feature *is* this principle. The search index and the graph are rebuildable artifacts; the event log is the rebuild source; publication failure never invalidates a write. |
| **IV. No Single Store / Graph / Score** | PASS after the D6 fix — `relevance` and `support` are computed and **retained separately** on `FusedResult`; the composite is derived, never stored alone. Graph stays a projection. |
| **V. Plugability by Contract** | PASS — `SearchIndex` stays a 3-method Protocol; the publisher is a separate component precisely so no backend gains a Kafka dependency. `FrontierSinkAdapter` isolates the control-plane row type from Layer A. Neo4j/Cypher stays behind the adapter. |
| **VI. Process-Centric** | PASS — every candidate and every document is tenant- and investigation-scoped; `investigation_id` is carried in the envelope, not the payload. |
| **VII. Security-First** | PASS — tenant isolation fail-closed; a source needing auth/CAPTCHA/paywall is refused **at registration**; malformed payloads quarantined, never dropped; metrics never labelled by URL (unbounded cardinality). |
| **No MVP/mini-architecture** | PASS — publisher, both bindings, the migration, the restore and the full test surface land in one feature. |
| **Backpressure** | PASS — publication is downstream and bounded by the transport timeout; it cannot grow an unbounded backlog that feeds back into acquisition. |
| **Idempotency** | PASS — `doc_id` is the index idempotency key; `(tenant_id, uri)` is the frontier's unique key; the publisher is idempotent on `(doc_id, tenant_id, kind)`. |
| **Dead letter / quarantine** | PASS — `DiscoveryReport.sources_failed` and `.empty_sources` preserve failures and empties **separately**; rejected candidates are never auto-deleted. |
| **Governance (ADR required)** | ACTION — one ADR needed: the Kafka-native search projection backend (Kafka ingest + object-storage index as an evolution of ADR-0004), plus the publisher's position in the write path. |

**Complexity Tracking**:

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| A separate `SearchProjectionPublisher` instead of publishing inside `SearchIndex` implementations | Ingest must be Kafka-native while the index contract stays 3 methods and backend-agnostic | Publishing inside the backend gives every backend (in-memory, bm25s, Tantivy, Quickwit) a broker dependency and a failure mode, and couples an index write to transport |
| `FrontierSinkAdapter` rather than changing `FrontierSink` to take a `FrontierItem` | Layer A's sink must stay synchronous, hermetic and constructible in a unit test without Postgres | Matching the ORM row type would force every Layer A test to build a control-plane row and go async, destroying the property that makes FR-005 provable in isolation |
| A new `provenance` JSONB column on `frontier_items` | FR-007 requires provenance to survive to the frontier; there is no column to hold it | Dropping provenance at the bridge would satisfy FR-007 in memory and lose it at the boundary — the requirement would be untestable and untrue |
| Restoring `bm25s_backend.py` rather than deleting its import | The dependency is declared and `default_ranked_index()` is contractually required to prefer it | Deleting the import deletes the test's subject and leaves a declared dependency dead; it converts a loud failure into a silent environment-dependent downgrade |

## Architecture

### What already exists vs. what is missing

```text
LAYER A — discovery (exists, unwired, untested)
  seed ──► DiscoveryRegistry.discover(query)
              │
              ├─ cc-index      ─┐
              ├─ wayback-cdx   ─┤ 4 sources, all transport-injected
              ├─ crtsh         ─┤
              └─ linkgraph ────┘  edge_provider seam  ◄── [NEW] LinkEdgeProvider
                                    │                        (over adjacency_from_store)
              ▼
        coalesce() by canonical_url            (exists, correct, untested)
              ▼
        FrontierSink (protocol)  ─────────►  [NEW] FrontierSinkAdapter
                                              └─► Postgres frontier  [NEW COLUMN provenance]
              ▼
        discovery.discovered                  topic exists  [NEW] producer

LAYER B — search projection (exists, one module missing, untested)
  events ──► SearchProjector.project(SearchEvent)
                │  INDEX_ALIASES derived from mappings.DOC_KINDS   [FIX: drift]
                ▼
           SearchIndex (3-method Protocol)
             ├── InMemorySearchIndex      (tests / oracle)
             ├── BM25SRankedIndex         [RESTORE — file missing, breaks collection]
             ├── RankedInvertedIndex      (stdlib)
             ├── Tantivy backend
             └── QuickwitSearchIndex      fail-closed tenant isolation  [TESTS MISSING]
                ▲
                └── [NEW] SearchProjectionPublisher ──► search.projected
                                                          (declarative consumer already exists
                                                           in mappings.index_config())

GRAPH + TDA (exists, untested)
  adjacency_from_store ──► AdjacencyView.to_tda_input()  ──► (nodes, edges) ──► TDA

QUERY (exists, two defects)
  QueryPlanner: fusion [FIX D6] + failure isolation [FIX D7]
                 ▲
                 └── currently bound to MemoryBackend fixtures; [NEW] real search + graph clients
```

### Phase strategy

1. **Phase 0 — unblock** (nothing else can be tested until this lands): restore
   `bm25s_backend.py`. This alone converts an interrupted collection into a green suite.
2. **Phase 1 — defects**: fix fusion (D6) and failure isolation (D7). Independent files, no
   overlap with Phase 2.
3. **Phase 2 — migration + frontier bridge**: `provenance` column, proven on both paths, plus
   `FrontierSinkAdapter`. Sequential within the phase (the adapter needs the column).
4. **Phase 3 — Layer A proof**: tests for `canonicalize`, `coalesce`, `InMemoryFrontierSink`
   idempotency, the fail-closed/failed/empty audit, and all four sources via their existing
   injection seams. Plus the production `LinkEdgeProvider`. No new adapter logic.
5. **Phase 4 — Layer B proof**: tests for `mappings`, `quickwit` (tenant isolation), projector
   rebuild determinism, the `DOC_KINDS` ↔ alias contract, and a real double-replay digest
   comparison. Parallel with Phase 3 — disjoint files.
6. **Phase 5 — producer + query bindings**: `SearchProjectionPublisher` and the real
   `BackendClient` adapters; then the two new route groups. Depends on Phases 1 and 4.
7. **Phase 6 — test-isolation defect + polish**: fix the cross-suite pollution, run the full
   workspace, record the baseline.

Phases 1, 3 and 4 are mutually independent. Phase 5's two halves are independent of each other.
Within every phase, `[P]`-marked tasks touch disjoint files and run concurrently.

## Project Structure

### Documentation (this feature)

```text
specs/008-discovery-search-fabric/
├── spec.md                       # input specification
├── plan.md                       # this file
├── research.md                   # D1–D8 decisions with file:line evidence
├── data-model.md                 # entities, canonicalisation rules, fusion derivation, migration
├── quickstart.md                 # verified commands + worked examples
├── contracts/
│   ├── service-contracts.md      # 12 protocols: what exists, what's new, what's fixed
│   ├── events.md                 # 4 topics, 3 producers missing
│   ├── api.md                    # /search rebind, /discovery/run, /search/rebuild
│   └── operations.md             # migration, generation lifecycle, rebuild, metrics, runbook
├── checklists/
│   └── requirements.md           # 16/16 quality items pass
└── tasks.md                      # phase-grouped tasks
```

### Source Code (planned)

```text
apps/projection/search/
├── bm25s_backend.py              # NEW  RESTORE: BM25SRankedIndex, available(), backend tag
├── indexer.py                    # (unchanged — its import becomes valid again)
├── projector.py                  # MOD  derive INDEX_ALIASES from mappings.DOC_KINDS (D8)
├── publisher.py                  # NEW  SearchProjectionPublisher → search.projected
├── mappings.py                   # unchanged (authoritative DOC_KINDS)
├── quickwit.py                   # unchanged (fail-closed; gains tests only)
└── tests/
    ├── test_mappings.py          # NEW  naming, tenant guards, config ↔ DOC_KINDS parity
    ├── test_quickwit.py          # NEW  tenant isolation, _prepare guard, rebuild
    ├── test_publisher.py         # NEW  mandatory tenant/kind, idempotency, write-independence
    └── test_projection.py        # MOD  double-replay + digest comparison (SC-003/SC-010)

apps/acquisition/adapters/discovery/
├── contracts.py                  # unchanged (canonicalize/coalesce are correct)
├── registry.py                   # MOD  refuse out-of-capability / access-control sources at register
├── commoncrawl_index.py          # unchanged (gains tests)
├── wayback_cdx.py                # unchanged (gains tests)
├── crtsh.py                      # unchanged (gains tests)
├── linkgraph.py                  # unchanged (gains tests + production provider)
└── tests/unit/
    ├── test_discovery_contracts.py   # NEW  canonicalisation table, coalesce determinism
    ├── test_discovery_registry.py    # NEW  dedup, failed vs empty, registration refusal
    ├── test_discovery_sources.py     # NEW  all four sources via injection seams
    └── test_link_edge_provider.py    # NEW  provenance required, tenant scoping

apps/control-plane/
├── db/
│   ├── schema.py                 # MOD  frontier_items.provenance JSONB
│   ├── migrations/versions/017_discovery_provenance.py   # NEW  forward-only
│   └── tests/unit/test_migration_017_forward_only.py     # NEW  both-path proof
├── services/
│   ├── discovery_frontier.py     # NEW  FrontierSinkAdapter + LinkEdgeProvider
│   ├── query_planner.py          # FIX  D6 fusion formula, D7 failure isolation
│   └── search_backends.py        # NEW  real search + graph BackendClient adapters
├── api/routes/
│   ├── search.py                 # MOD  bind real backends; 503 on total failure
│   ├── discovery.py              # NEW  POST /discovery/run
│   └── search_rebuild.py         # NEW  POST /search/rebuild (admin)
└── tests/
    ├── unit/test_query_fusion.py       # NEW  D6: support changes the composite
    ├── unit/test_query_degradation.py  # NEW  D7: isolation, degrade, all-failed raises
    ├── integration/test_discovery_api.py      # NEW
    ├── integration/test_search_rebuild.py     # NEW
    └── integration/test_frontier_provenance.py # NEW  FR-007 survives the bridge
```

**Structure Decision**: Layer A code stays in `apps/acquisition/adapters/discovery/` — it is an
acquisition concern and its contract is deliberately independent of the control-plane row type.
Everything that needs to know about Postgres, the event bus or HTTP lives in
`apps/control-plane/`. The `LinkEdgeProvider` goes in `apps/control-plane/services/` because it
reads a projection owned there, while the discovery-side `linkgraph.py` keeps only its
`edge_provider` seam. No frontend change: this feature has no UI surface.

## Complexity Tracking

See the Constitution Check table. One further note:

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| `DOC_KINDS` becomes the single source of truth rather than two lists plus a comparison test | A test enforcing agreement between two hand-maintained lists still requires editing both; the second list remains a drift surface | The drift already happened once — this feature's own spec said "six" kinds while enumerating seven, matching neither list exactly |
