# Feature Specification: Event-Driven Discovery & Rebuildable Search Projection Fabric

**Feature Branch**: `008-discovery-search-fabric`

**Created**: 2026-09-19

**Status**: Draft

**Input**: User description: "Event-driven discovery and rebuildable search projection fabric" — Layer A (discovery before crawl: data-driven web indexes + our own link-graph feed the frontier, no manual search) and Layer B (search index as a rebuildable projection, Kafka-native, object-storage-first) integrated with TDA / entity-network analysis.

## Context & Scope

This feature closes the two missing halves of the collection loop that feature 001 left
abstract and that field validation exposed:

1. **Discovery (pre-crawl)** — given a seed/entity/domain, produce URL *candidates* for the
   frontier with no human searching. Today the platform can fetch a URL it already knows,
   but has no mechanism to *find* URLs. This is the "indexing before crawling" layer.
2. **Search projection (post-crawl)** — make the collected corpus searchable as a
   **rebuildable projection** (Constitution III/IV, Invariant 9/12), not as a primary store.

Both are wired strictly through the existing contracts: `SourceRegistration` capability
registry, the Observation Gate, Kafka topics, and the Postgres frontier (ADR-0015).
No new orchestration backbone, no second authority.

**Out of scope**: crawl scheduling policy changes (ADR-0016), recrawl cadence (ADR-0017),
ML ranking, and any mechanism bypassing source access controls (Constitution VII).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Discovery before crawl (Priority: P1)

An investigation is seeded with a domain or an entity name. The platform resolves it into a
set of candidate URLs using data-driven web indexes (Common Crawl columnar index, Wayback CDX,
certificate-transparency subdomains) plus its own accumulated link-graph — with **no manual
search** — and enqueues them into the durable frontier.

**Why this priority**: Without discovery, the entire acquisition plane has nothing to fetch.
This is the highest-value gap: it turns the fabric from "parse known pages" into "find, then
parse".

**Independent Test**: Seed one domain; assert that discovery produces a deterministic,
non-empty candidate set (from an injected fixture index) and that every candidate is enqueued
into the frontier exactly once (idempotent by canonical URL).

**Acceptance Scenarios**:

1. **Given** a registered discovery source with the `index`/`web-graph` capability, **When** a
   `discovery.seed` event for a domain arrives, **Then** the source emits `discovery.discovered`
   candidates and each is enqueued into the frontier with its provenance (source + query).
2. **Given** two investigations seed the same domain, **When** discovery runs, **Then**
   candidates are coalesced by canonical URL (one acquisition, many waiters) — no duplicate work.
3. **Given** a source that returns nothing, **When** discovery runs, **Then** the outcome is an
   empty, audited result (never a silent hang) and the investigation continues with other sources.

---

### User Story 2 - Rebuildable search projection (Priority: P1)

Every accepted observation, mention, candidate, entity, assertion and finding becomes searchable
through a search projection that is **rebuildable from Kafka events** and stores its index on
object storage (S3/MinIO), consistent with Constitution III ("projection failure must never
destroy evidence") and the tech baseline (Kafka + object storage).

**Why this priority**: It completes the read side of the fabric and is the platform's answer to
"index the pages we have". It must exist before any analyst-facing search.

**Independent Test**: Replay a fixed event log through the projector into a fresh index; assert
the resulting index is identical to the first build (idempotent rebuild, I-11/I-12), including
per-tenant isolation and provenance on every document.

**Acceptance Scenarios**:

1. **Given** an `observation.created` event, **When** the search projector consumes it, **Then**
   exactly one document of the correct kind is indexed, carrying `doc_id = observation_id` and
   full projection provenance.
2. **Given** the same event replayed, **When** the projector runs again, **Then** the document
   is not duplicated (idempotent on `doc_id`).
3. **Given** a projection store failure, **When** the projector retries, **Then** evidence is
   untouched and the index converges on replay (never the reverse).

---

### User Story 3 - Link-graph expansion loop (Priority: P2)

Links extracted from already-fetched content, and edges materialized in the graph projection,
feed **back** into discovery as new candidates — the crawl self-expands without external search.

**Why this priority**: It is what makes discovery asymptotically cheap: after warm-up the
platform mostly finds new URLs in its own corpus rather than querying external indexes.

**Independent Test**: Given a fetched page that links to two unseen URLs, assert both are
emitted as `discovery.discovered` candidates with `source=link-graph` and enqueued to the frontier.

**Acceptance Scenarios**:

1. **Given** a page whose extracted links include unseen URLs, **When** link-graph discovery runs,
   **Then** each unseen URL is enqueued with provenance pointing at the originating observation.
2. **Given** a link to an already-known URL, **When** link-graph discovery runs, **Then** no new
   frontier item is created (dedup by canonical URL).

---

### User Story 4 - TDA / entity-network analysis compatibility (Priority: P2)

The graph and search projections must expose the structures that TDA and network analysis need
(entities, mentions, co-mention edges, co-occurrence) so structural signals can be computed from
projections **without** introducing a new source of truth (Constitution IV, Invariant 6/9).

**Why this priority**: It proves the fabric composes with the platform's analytical planes; the
data model must not block them later.

**Independent Test**: From a fixture graph of N entities and co-mention edges, assert the graph
reader returns adjacency usable to build a (nodes, edges) matrix for TDA, and that the search
projection returns per-entity mentions with the same identifiers.

**Acceptance Scenarios**:

1. **Given** entities and co-mention edges in the graph projection, **When** the network reader
   runs, **Then** it returns a (nodes, edges) adjacency compatible with TDA input, with no loss
   of provenance.
2. **Given** an entity, **When** search is queried, **Then** its mentions resolve to the same
   entity/observation identifiers used by the graph (shared keys, no re-derivation).

---

### User Story 5 - Federated query surface (Priority: P3)

An analyst issues one query and receives fused results from search, graph and analytics, each
with an evidence link whose chain resolves to immutable raw objects — the existing query-planner
contract, extended to the new backends.

**Why this priority**: It is the analyst-facing payoff; it depends on US1–US4 being in place.

**Independent Test**: Issue one query with a search backend + graph backend; assert fused,
de-duplicated results each carry a resolvable evidence chain.

**Acceptance Scenarios**:

1. **Given** search and graph backends, **When** a query is issued, **Then** results from both
   are fused behind one surface with evidence links.
2. **Given** one backend is down, **When** a query is issued, **Then** the other backends still
   return results (graceful degradation), and the failure is surfaced.

---

### Edge Cases

- Discovery source returns malformed/huge payload → rejected into quarantine, never silently dropped.
- Index segment referenced by a crawl yet unavailable (404) → candidate skipped with audit, discovery continues.
- Same canonical URL discovered by three sources in one batch → exactly one frontier item, provenance merged.
- Projection rebuild while producers are live → replay is idempotent; no duplicate documents.
- Tenant-scoped query tries to read another tenant's index alias → fail-closed (no cross-tenant result).
- Link extraction yields a non-http(s) scheme → excluded from candidates.
- A candidate exceeds the frontier's per-host budget → deferred, not dropped (frontier policy owns it).

## Requirements *(mandatory)*

### Functional Requirements

**Discovery (Layer A)**

- **FR-001**: The system MUST expose discovery sources through the existing `SourceRegistration`
  capability registry, declaring execution class + capabilities (`index`, `web-graph`, `api`).
- **FR-002**: The system MUST provide a data-driven discovery source that queries the **Common
  Crawl columnar (Parquet) index** on object storage by domain/URL pattern, running locally with
  no external query service.
- **FR-003**: The system MUST provide a historical-URL discovery source (Wayback CDX) and a
  subdomain discovery source (certificate transparency), both read-only and public-interface only.
- **FR-004**: The system MUST provide a **link-graph** discovery source that reads edges from the
  graph projection and turns unseen targets into candidates.
- **FR-005**: Discovery MUST emit `discovery.discovered` candidates and enqueue them into the
  **Postgres frontier** (ADR-0015) — Kafka is never the queue, and discovery MUST NOT own a queue.
- **FR-006**: Discovery MUST be idempotent by canonical URL and MUST coalesce duplicate candidates
  within a batch (one frontier item, merged provenance).
- **FR-007**: Discovery MUST carry provenance on every candidate: originating source, query/seed,
  and (for link-graph) the originating observation id.

**Search projection (Layer B)**

- **FR-008**: The system MUST implement the existing `SearchIndex` contract with a backend that is
  **Kafka-native for ingestion** and stores its index on **object storage** (S3/MinIO).
- **FR-009**: The search projection MUST index the six canonical document kinds already defined by
  the projector (observation/document, mentions, candidates, entities, assertions, findings).
- **FR-010**: The search projection MUST be **rebuildable from Kafka event history**; replaying the
  same events MUST produce an identical index (idempotent on `doc_id`).
- **FR-011**: Every indexed document MUST carry projection provenance and MUST be isolated per
  tenant via tenant-scoped index aliases; cross-tenant reads MUST fail closed.
- **FR-012**: Index mappings/templates MUST be versioned and reproducible (declarative, in-repo).

**Graph projection & analysis compatibility**

- **FR-013**: The graph projection MUST provide a reader returning an adjacency structure
  (nodes + edges) sufficient to build TDA / network-analysis inputs, preserving provenance.
- **FR-014**: Search and graph projections MUST share identifiers (entity/observation/mention ids)
  so analytical results can be cross-referenced without re-derivation.

**Query surface**

- **FR-015**: The query planner MUST support a search backend and a graph backend behind one
  surface, fusing results and attaching evidence links; single-backend failure MUST degrade
  gracefully.

**Cross-cutting**

- **FR-016**: All projection writes MUST remain rebuildable and MUST never mutate or destroy
  evidence (Constitution III, I-12).
- **FR-017**: The feature MUST NOT introduce a new orchestration backbone or a second frontier;
  it MUST reuse Kafka, the Observation Gate, the frontier and the graph abstraction.
- **FR-018**: Discovery sources MUST operate only through sources' public interfaces
  (Constitution VII) — no authentication/CAPTCHA/paywall bypass.

### Key Entities *(include if feature involves data)*

- **DiscoverySource**: a registered, capability-declaring source of URL candidates (Common Crawl
  index, Wayback CDX, certificate transparency, link-graph). Attributes: name, capabilities,
  execution class, provenance contract.
- **Candidate**: a discovered URL with provenance (source, query/seed, originating observation),
  canonical URL, and priority hint. Becomes a frontier item; is not an observation.
- **SearchDocument**: a projected, searchable document (one of six kinds) with `doc_id`, tenant
  alias, body, and projection provenance. Rebuildable; never a source of truth.
- **LinkEdge**: a directed link/co-mention edge in the graph projection (source → target), with
  type and provenance; input to discovery expansion and to TDA/network analysis.
- **AdjacencyView**: a (nodes, edges) view of the graph projection for analytical consumption.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Given a seed domain, discovery returns a non-empty candidate set for ≥90% of domains
  that exist in the fixture index, with zero manual searching.
- **SC-002**: 100% of discovered candidates reach the frontier exactly once (idempotent by
  canonical URL) in the dedup/coalesce test suite.
- **SC-003**: Replaying a fixed event log produces an index identical to the first build (0
  duplicate documents; identical doc-id set) — verified by the rebuild test.
- **SC-004**: Cross-tenant search reads return 0 foreign results (fail-closed) in the isolation test.
- **SC-005**: The graph reader returns adjacency sufficient to construct a TDA input for a fixture
  graph of ≥100 entities with no provenance loss.
- **SC-006**: A one-backend-down query still returns results from the remaining backends (graceful
  degradation test passes).
- **SC-007**: All discovery and projection paths are covered by contract/integration tests that run
  green in CI without network access (transport-injected fixtures).

## Assumptions

- The existing Kafka transport, Observation Gate, Postgres frontier (ADR-0015) and graph
  abstraction (ADR-0008/0009) are reused unchanged; this feature adds sources and projections, not
  backbone.
- Common Crawl columnar index is read from object storage fixtures in tests; live reads are
  optional and gated behind configuration.
- Search backend choice (Kafka-native, object-storage index) is captured in a dedicated ADR
  (ADR-0019) as an evolution of ADR-0004; OpenSearch remains an alternative adapter behind the
  same `SearchIndex` contract.
- TDA consumption uses the existing analytical plane; this feature only guarantees compatible
  projection output, not TDA algorithms.
- Public-interface-only access (Constitution VII) is a hard boundary for every discovery source.