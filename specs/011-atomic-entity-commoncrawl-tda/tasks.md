# Tasks: 011-atomic-entity-commoncrawl-tda

Status: NO_STARTED. Convention: one task per tracked step; independent tasks may
parallelize. Move to IN_PROGRESS when started; DONE only when its test turns green.

## Phase 1 — Common Crawl zero layer (P1)

- [ ] T1-01 `apps/acquisition/network/commoncrawl/session.py` — `CcIndexSession`
      (DuckDB over url-index parquet; `query_domain(url_pattern, crawl)`; row schema
      uri/warc_filename/offset/length/content_type/crawl; transport seam).
- [ ] T1-02 `apps/acquisition/network/commoncrawl/range_pull.py` — byte-exact WARC/WET
      range pull + header parse (transferable records).
- [ ] T1-03 CC URL-index parquet fixture slice (a few hundred rows) under
      `apps/acquisition/tests/fixtures/cc_index/`.
- [ ] T1-04 Unit tests `test_cc_session.py` (determinism, empty-domain, seam transport)
      + `test_range_pull.py`; SC-001/SC-002 green, network-free.
- [ ] T1-05 Wire `CcIndexSession` behind `adapters/commoncrawl/index.py` shape; docstring
      documents live-vs-fixture gating.

## Phase 2 — Lifecycle (P1)

- [ ] T2-01 `apps/shared/domain/temporal_metrics.py` — `burstiness`, latency/efficiency,
      `causal_fidelity`, `characteristic_timescale`; empty→empty, honesty (I-3).
- [ ] T2-02 `apps/control-plane/services/series_lifecycle.py` — `SeriesProjector` +
      `entity_series` DDL (`ReplacingMergeTree(ts)`, PARTITION BY toYYYYMM(ts),
      ORDER BY (tenant_id, entity_id, key, series_hash, ts)); idempotent ingest, FINAL read.
- [ ] T2-03 Unit tests: `test_temporal_metrics.py` (B periodic/Poisson/max-burst edges,
      SC-005); `test_series_lifecycle.py` (double-insert converges, SC-004).
- [ ] T2-04 Integration: `build_series` → projector → ClickHouse (or in-memory adapter
      for tests) round-trip.

## Phase 3 — Topological invariant (P1)

- [ ] T3-01 `apps/projection/tda/diagram.py` (new) — persistence diagram model +
      content-addressed `diagram_hash`.
- [ ] T3-02 `apps/projection/tda/pipeline.py` — widen `PersistenceProvider` contract;
      add `FlagserProvider` (directed flag complex); add `TakensSeriesComplex`
      (delay embedding → VR). Keep memory budget + bounded windows (ADR-0010).
- [ ] T3-03 `apps/projection/tda/features.py` — amplitude (bottleneck/Wasserstein),
      persistence entropy, landscapes, Betti curve; `drift` between windows.
- [ ] T3-04 `apps/projection/tda/validated.py` — HGX-style statistically validated
      hyperedge filter + order-specific hyper-Laplacian eigenvalues (`eigsh`).
- [ ] T3-05 Tests: `test_pipeline_directed.py` (H0/H1), `test_takens.py` (periodic),
      `test_features.py` (deterministic hashes, drift), `test_validated.py`
      (noise removal determinism) — SC-006/SC-007/SC-008.

## Phase 4 — Contracts & wiring (P2)

- [ ] T4-01 `apps/projection/tda/__init__` exposes `TopologicalInvariant.run()`: Series +
      hyperedge fan → point cloud → barcode → features; structural-only (never identity, I-6).
- [ ] T4-02 Science batch job: ClickHouse `entity_series` → TDA features → claims registry
      with provenance (series_hash/diagram_hash).
- [ ] T4-03 README/ADR notes: pinned deps (`giotto-tda`, `gudhi`, `ripser`, `hypergraphx`
      optional adapter), wrapping rule (C-5), live CC gated.
- [ ] T4-04 Full-suite run: `pytest apps/projection apps/shared apps/control-plane
      apps/acquisition` green; SC-009 verified.

## Done gates
- SC-001/SC-002 (Phase 1), SC-004/SC-005 (Phase 2),
  SC-006/SC-007/SC-008 (Phase 3), SC-009 (Phase 4).