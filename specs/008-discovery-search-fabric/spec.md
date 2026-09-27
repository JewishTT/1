# Feature Specification: Event-Driven Discovery & Rebuildable Search Projection Fabric

**Feature Branch**: `008-discovery-search-fabric`

**Created**: 2026-09-19

**Status**: Draft (validated 2026-09-26)

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

**Traceability note**: component names used below (event backbone, object storage, operational
state store, search projection, link-graph backend) are constitution-fixed baseline
(Technology Baseline, Invariants 4/5/9/12, Principles III/IV/V) and are named for traceability to
existing decisions only. Every requirement below is stated as a capability and an observable
outcome, never as a component choice; the link-graph projection targets the reference graph
backend for the pilot while remaining swappable behind its contract.

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

Every accepted observation, document, mention, candidate, entity, assertion and finding becomes
searchable through a search projection that is **rebuildable from Kafka events** and stores its
index on object storage (S3/MinIO), consistent with Constitution III ("projection failure must never
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
4. **Given** a tenant-scoped query, **When** it is issued, **Then** only documents belonging to that
   tenant are returned, and any attempt to address another tenant's index scope fails closed.
5. **Given** an index generation built from a recorded event-log position, **When** the mapping
   version applied to that generation is inspected, **Then** the exact mapping is identifiable and
   the generation can be reproduced byte-for-byte from the same position.
6. **Given** an index generation is discarded, **When** it is rebuilt from event history alone,
   **Then** the rebuild succeeds without reading the discarded generation.

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
3. **Given** a link-graph projection discarded and rebuilt from event history alone, **When** the
   rebuild completes, **Then** the node and edge sets are identical to the discarded generation
   (projections are artifacts, never a source of truth).

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
- A discovery source would require authentication, CAPTCHA solving, or paywall traversal to answer
  → the source is refused at registration time and the request is never issued (Constitution VII).
- Two discovery sources and the link-graph source report the same canonical URL within one batch →
  one frontier item, provenance lists all three origins.
- The event log is compacted or a projection offset is lost → the affected index generation is
  rebuilt from the earliest retained position rather than partially patched.

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
- **FR-009**: The search projection MUST index the seven canonical document kinds defined by the
  projector and mapping registry (observations, documents, mentions, candidates, entities,
  assertions, findings); the kind list MUST be declared in exactly one place and both the projector
  and the mapping generator MUST read it, so the two cannot drift.
- **FR-010**: The search projection MUST be **rebuildable from Kafka event history**; replaying the
  same events MUST produce an identical index (idempotent on `doc_id`).
- **FR-011**: Every indexed document MUST carry projection provenance and MUST be isolated per
  tenant via tenant-scoped index aliases; cross-tenant reads MUST fail closed.
- **FR-012**: Index mappings/templates MUST be versioned and reproducible (declarative, in-repo);
  the mapping version applied to an index generation MUST be recorded with that generation so the
  same generation can be reproduced from a given event-log position.

**Graph projection & analysis compatibility**

- **FR-013**: The graph projection MUST provide a reader returning stable node identifiers plus
  typed, provenance-carrying edges in a form that can be materialised directly as a
  nodes-and-edges input for TDA / network analysis, with no identifier re-derivation.
- **FR-014**: Search and graph projections MUST share identifiers (entity/observation/mention ids)
  so analytical results can be cross-referenced without re-derivation.

**Query surface**

- **FR-015**: The query planner MUST accept a search backend and a graph backend within a single
  query, MUST return fused and de-duplicated results, and MUST attach to every result an evidence
  link resolvable to the immutable raw object; the failure of one backend MUST NOT prevent the
  remaining backends from answering, and that failure MUST be surfaced to the caller.

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
- **SearchDocument**: a projected, searchable document (one of seven kinds) with `doc_id`, tenant
  alias, body, and projection provenance. Rebuildable; never a source of truth.
- **LinkEdge**: a directed link/co-mention edge in the graph projection (source → target), with
  type and provenance; input to discovery expansion and to TDA/network analysis.
- **AdjacencyView**: a (nodes, edges) view of the graph projection for analytical consumption.

### Requirement Traceability

| Requirements | Verified by |
|---|---|
| FR-001 – FR-004 | US1 scenarios 1–3; US3 scenario 1 |
| FR-005 – FR-007 | US1 scenarios 1–3; US3 scenarios 1–2; Edge cases (dedup, budget, scheme) |
| FR-008 – FR-010 | US2 scenarios 1–3, 6; SC-003 |
| FR-011 | US2 scenario 4; SC-004 |
| FR-012 | US2 scenario 5 |
| FR-013 – FR-014 | US4 scenarios 1–3; SC-005 |
| FR-015 | US5 scenarios 1–2; SC-006 |
| FR-016 | US2 scenario 3; US4 scenario 3; SC-010 |
| FR-017 | SC-012; Edge cases (offset loss) |
| FR-018 | Edge cases (access-control refusal); SC-008 |

### Dependencies

- The durable event/evidence substrate (event backbone, object storage, operational state store)
  and the existing `SourceRegistration` capability registry, Observation Gate, frontier and graph
  abstraction must be available and stable before this feature can be validated.
- A readable, queryable public web index of URLs with capture metadata must be reachable for the
  discovery layer to produce candidates; without it, discovery is limited to the link-graph source.
- An existing entity/mention identity model is required so that shared identifiers across the
  search and graph projections resolve to the same keys.
- Analytical (TDA) consumers are downstream dependents: they require the adjacency contract, not
  changes to this feature.
- The link-graph backend choice for the pilot requires an architectural decision record before
  implementation begins.

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
- **SC-008**: 0 discovery or projection capabilities are capable of bypassing authentication,
  CAPTCHA, paywall, or any other access control; a source requiring them is refused at
  registration (verified by capability review plus a registration-refusal test).
- **SC-009**: 100% of malformed, oversized or policy-uncertain payloads land in quarantine with an
  auditable reason, and 0 are silently dropped or auto-deleted.
- **SC-010**: A full drill in which the search and link-graph index generations are deleted and
  rebuilt from event history alone reproduces identical document and edge sets, 0 duplicates.
- **SC-011**: Every functional requirement is covered by at least one automated verification, and
  the traceability table resolves each requirement to the scenario or criterion that proves it.
- **SC-012**: 0 new orchestration backends, 0 secondary frontier or candidate stores, and 0 second
  authorities are introduced; a component inventory taken before and after the feature differs only
  by discovery sources and projection adapters.

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