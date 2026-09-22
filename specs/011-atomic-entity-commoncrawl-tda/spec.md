# Feature Specification: Atomic Entity Invariant × Common Crawl Full Pilot × TDA

**Feature Branch**: `011-atomic-entity-commoncrawl-tda`

**Created**: 2026-09-22

**Status**: Draft

**Input**: User concept decision — the platform is process-centric; the atomic entity is a *relational invariant and momentary projection* of the data flow, dynamic, carrying its full lifecycle time series (ClickHouse); simultaneously maximally enriched AND maximally optimal for network analysis / TDA (hypergraph → simplicial complexes); built as REALITY, not naive analyst assumptions; stochastic/dialectical, not Newtonian; LLM excluded from core functionality. Full-pilot phase against Common Crawl (DuckDB + S3 Range over the columnar URL index) with deterministic zero-layer extraction.

## Context & Scope

Closes the loop opened by feature 008 (discovery + search) and the donor cluster 04
decision (topological invariant as the entity's form). Three gaps remain:

1. **Zero-layer enrichment** — Common Crawl's URL index (Parquet) is queried over S3
   Range / HTTP, real WARC/WET byte ranges are pulled, and deterministic extractors
   produce `Observation` records (feature 007). The crawler knows nothing about entities;
   but layer zero **is** the sole substrate for entity existence (interconnection).
2. **Atomic entity as topological object** — the entity already exists as an append-only
   stream (`dynamics.py`), a rebuildable state (`EntityState`), derived `Series`
   (`build_series`), and a typed temporal hypergraph (`hypergraph.py`). What is missing:
   the **invariant** as a dynamic topological signature (persistent homology barcodes),
   and the lifecycle materialized into ClickHouse as a rebuildable projection.
3. **Donor engineering upgrades** — adopt proven engines instead of vendoring research
   forks: giotto-tda/ripser/GUDHI for TDA (incl. directed flag complexes,
   `FlagserPersistence`, Takens time-delay embedding), HypergraphX for higher-order
   measures (statistically validated hyperedges), Raphtory for the temporal graph
   projection plane, ClickHouse `ReplacingMergeTree` for idempotent series rebuild.

**Out of scope**: crawl scheduling policy (ADR-0016), recrawl cadence (ADR-0017), ML
ranking, multiplex embedding, LLM-in-core, anything bypassing source access controls
(Constitution VII).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Zero-layer full pilot against the CC URL index (Priority: P1)

Given a seed domain (or a set of identifiers held by an entity), the platform issues a
**DuckDB query over the Common Crawl columnar index** read *in place* on S3 (Range) or
Hugging Face storage, resolves real WARC/WET byte addresses, and pulls the content —
with no pre-downloaded/processed corpus and no external search service.

**Independent Test**: Seed one domain against a locally-downloaded Parquet fixture
(overriding transport); assert a deterministic, non-empty candidate list (`uri`,
`warc_filename`, `offset`, `length`) and that a real WARC byte range can be pulled via
a faked HTTP range transport.

**Acceptance**:
1. `cc_index_session` issues `WHERE url LIKE '<domain>%'` over the fixture table and
   returns sorted, distinct page records with byte offsets.
2. Range fetch returns exactly the requested bytes (seam-injected transport).
3. Zero network dependence on live CC in tests (fixture parquet; live is gated by config).

### User Story 2 - Lifecycle time series materialized in ClickHouse (Priority: P1)

Every derived `Series` (`build_series`, dynamics.py:916) persists into a columnar table
behind `ReplacingMergeTree`, keyed by (tenant, entity, key, series_hash) with version =
timestamp, so replay/rebuild is idempotent (I-11/I-12) and cross-entity analytics
(velocity, moving average) run over billions of rows.

**Independent Test**: Insert the same series twice (simulating replay); assert the
`FINAL` view converges to a single identical projection (no phantom points), including
`series_hash` verification.

### User Story 3 - Temporal metrics power the invariant (Priority: P1)

`Series` feeds deterministic stochastic features — burstiness B (from inter_arrival),
latency/efficiency, causal fidelity c, characteristic timescale — without ML. These
become the entity's point-cloud dimensions for TDA.

**Independent Test**: From a fixed inter_arrival sequence, assert B=−1 (periodic),
B≈0 (Poisson), B=1 (maximally bursty); assert empty series yield no fabricated points
(honesty, I-3).

### User Story 4 - Topological invariant of the entity (Priority: P1)

From the entity's point cloud (Series + hyperedge fan features), a bounded simplicial
complex is built and persistent homology produces a barcode; the **directed** version
(`FlagserPersistence`) handles typed directed relations; Takens embedding handles the
time-delay structure. Barcodes are compared via bottleneck/Wasserstein (`Amplitude`)
for drift between windows. Output is structural science claims (ADR-0010), never
identity claims (I-6).

**Independent Test**: Fixed point cloud → assert deterministic barcode feature vector
(persistence entropy, amplitude), bounded memory budget enforced, and two identical
clouds produce identical features.

### User Story 5 - Higher-order hypergraph measures (Priority: P2)

Co-mention/co-event hyperedges from observations go through **statistically validated
filtering** (HGX-style) so edges are significant, not naive co-occurrence; order-specific
hyper-Laplacian eigenvalues become entity facets.

**Independent Test**: From a fixture of co-mentions with a strong null model, assert the
filter removes noise hyperedges and the surviving set is deterministic.

### Edge Cases

- URL index record whose WARC range is invalid → candidate skipped with audit, session continues.
- Series with duplicate timestamps (batch observation) → allowed; stable sort keeps arrival order (honesty).
- Frozen entity (I-1) → stream rejects every mutation incl. counters; Series still derives from existing stream.
- Point cloud exceeding memory budget → bounded windowing / witness subsampling, never OOM.
- ClickHouse rebuild while live producers write → idempotent by (key, series_hash, ts).

## Requirements *(mandatory)*

### Functional Requirements

**CC zero-layer**

- **FR-001**: The system MUST query the Common Crawl columnar (Parquet) URL index *in
  place* via DuckDB over S3 Range and over the Hugging Face storage mirror (HTTP,
  `hf://`-style path), no download of the index.
- **FR-002**: The session MUST produce page records (uri, warc_filename, offset, length,
  content-type, crawl id) and MUST support a deterministic subset selection policy.
- **FR-003**: The session MUST pull the referenced WARC/WET byte ranges over range GETs
  and parse WARC/WET headers into transferable records for the deterministic extractor.
- **FR-004**: All CC access MUST go through the existing `SourceRegistration` capability
  registry / adapters; live access gated by configuration; tests inject fixtures.
- **FR-005**: Extraction MUST be deterministic (regex/heuristics, feature 007), LLM-free,
  and emit `Observation` records (immutable, content-addressed, refs-only payload I-5).

**Lifecycle & analyses**

- **FR-006**: `Series` MUST be materially projectable to ClickHouse onto
  `ReplacingMergeTree(version)` keyed by (tenant_id, entity_id, key, series_hash);
  `FINAL` MUST be the canonical read for momentary projections (ADR-0005).
- **FR-007**: Temporal metrics MUST be deterministic and honest: burstiness B
  (inter_arrival σ/μ), latency/efficiency, causal fidelity c, characteristic timescale
  (mode of shortest path duration); empty input → empty output (I-3).
- **FR-008**: The TDA core MUST support Vietoris–Rips over distance matrices of entity
  feature vectors AND directed flag complexes (`FlagserPersistence`) for typed graphs,
  with a bounded memory budget (ADR-0010).
- **FR-009**: The TDA core MUST support Takens time-delay embeddings of univariate
  `Series` so the entity's temporal dynamics enter the topological invariant.
- **FR-010**: Persistence output MUST be compared across windows via bottleneck /
  Wasserstein (amplitude) and reduced to vectorized features (persistence entropy,
  landscapes, Betti curves) that are **content-addressed** for reproducibility.
- **FR-011**: Hyperedge facets MUST be computed with statistical validation (null-model
  filtering); order-specific hyper-Laplacian eigenvalues MUST be available as facets.

**Cross-cutting**

- **FR-012**: All ingests and projections remain rebuildable and never mutate evidence
  (Constitution III, I-12).
- **FR-013**: TDA/science output MUST be structural claims with provenance to the exact
  Series/point-cloud hash analyzed; MUST NOT assert identity (I-6).
- **FR-014**: Adopt libraries where they exist (giotto-tda, ripser, GUDHI, HypergraphX,
  Raphtory) instead of vendoring research forks; pin versions; wrap behind contracts.
- **FR-015**: No new orchestration backbone; reuse Kafka, Observation Gate, Postgres
  frontier, Temporal (ADR-0007).

### Key Entities

- **CCPageRecord**: (uri, warc_filename, offset, length, content_type, crawl) — an
  address of real CC content; not content itself.
- **CCWarcPull**: pulled byte-range + WARC/WET header parse → input to extractor.
- **Observation**: immutable evidence (existing contract), content-addressed in object
  storage; produced by deterministic extraction of the pulled content.
- **SeriesRow**: ClickHouse row (tenant_id, entity_id, key, series_hash, ts, value) —
  lifecycle materialization, rebuildable.
- **TemporalFeatures**: burstiness, latency/efficiency, causal fidelity c, characteristic
  timescale, velocity — deterministic point-cloud dimensions.
- **PersistenceFeature**: vectorized barcode signature (amplitude, entropy, landscapes,
  Betti) with input hash provenance.
- **ValidatedHyperedgeSet**: higher-order edges surviving null-model filtering.

## Success Criteria *(mandatory)*

- **SC-001**: CC session over a fixture parquet returns deterministic, non-empty
  candidate records for ≥90% of seeded domains present in the fixture; live access 100%
  network-free in CI.
- **SC-002**: WARC/WET range pull returns byte-exact content for a seeded record (seam
  transport), parseable to the extractor's input.
- **SC-003**: 100% of extracted content becomes observations content-addressed with
  refs-only payloads (duplicate-pull test: same bytes → same observation id).
- **SC-004**: Re-inserting a series twice into ClickHouse converges to an identical
  `FINAL` projection (0 phantom points; identical series_hash set).
- **SC-005**: Temporal metrics unit tests pass (B∈[−1,1], Poisson ≈ 0, periodic = −1,
  maximal burst = 1; empty → empty).
- **SC-006**: TDA core deterministic on fixtures; memory budget enforced; directed flag
  complex path computes H0/H1; Takens path returns a diagram for a periodic fixture.
- **SC-007**: Persistence features are content-addressed; identical input → identical
  feature hash; drift detection (bottleneck) on a synthetic regime-shift fixture.
- **SC-008**: Stat-validated hyperedge filter removes injected noise and is deterministic
  on fixtures.
- **SC-009**: All paths run in CI with transport-injected fixtures; live-source access
  optional and gated.

## Assumptions

- `duckdb`, `giotto-tda`, `gudhi` already declared in `apps/projection/pyproject.toml`;
  `ricksha`/`hypergraphx`/`raphtory` added as pinned deps behind adapter contracts.
- CC URL index fixture (a small Parquet slice) is committed to test fixtures; live reads
  optional behind config (existing ADR-0019 search stays OpenSearch/Tantivy-compatible).
- The atomic entity domain (dynamics/hypergraph/fabric) is reused unchanged; this feature
  adds the topological/series/ClickHouse *surfaces*, not a second authority.
- Public-interface-only access (Constitution VII) is a hard boundary for every CC source.