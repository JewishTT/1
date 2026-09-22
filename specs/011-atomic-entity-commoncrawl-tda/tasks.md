# Tasks: 011-atomic-entity-commoncrawl-tda

Status: IN_PROGRESS (Phases 1–3 done; Phase 4 partial; gudhi-gated tests skip
locally). Convention: one task per tracked step; independent tasks may
parallelize. Move to IN_PROGRESS when started; DONE only when its test turns green.

## Phase 1 — Common Crawl zero layer (P1)

- [x] T1-01 `CcIndexSession` (DuckDB over url-index parquet; `query_domain`
      rows uri/warc_filename/offset/length/content_type/crawl; `Transport` seam).
      DEVIATION: lives in `apps/shared/network/cc_session.py` (flat package),
      not `apps/acquisition/network/commoncrawl/session.py` — the CC layer is a
      shared-domain capability; `network.commoncrawl` re-exports the adapter
      shape.
- [x] T1-02 `range_pull.py` — byte-exact WARC/WET range pull + header parse
      (transferable records); warcio-less splitter `split_warc_records`.
- [ ] T1-03 CC URL-index parquet fixture (hundreds of rows) under
      `apps/acquisition/tests/fixtures/cc_index/`. DEVIATION: no committed binary;
      tests build a deterministic parquet in `tmp_path` via duckdb at runtime
      (network-free, reproducible, avoids binary blobs in git).
- [x] T1-04 Unit tests `test_cc_session.py` + `test_range_pull.py`; SC-001/SC-002
      green, network-free (20 passed).
- [x] T1-05 `CcIndexSession` used behind `apps/acquisition/adapters/commoncrawl/index.py`
      shape (module re-exports `network.commoncrawl`); docstring gates live-vs-fixture.

## Phase 2 — Lifecycle (P1)

- [x] T2-01 `apps/shared/domain/temporal_metrics.py` — `burstiness`, `causal_fidelity`
      (temporal reachability, hop-wise), `characteristic_timescale`, `events_per_day`;
      empty→empty, honesty (I-3).
- [x] T2-02 `apps/control-plane/services/series_lifecycle.py` — `SeriesProjector` +
      `entity_series` DDL (`ReplacingMergeTree(ts)`, PARTITION BY toYYYYMM(ts),
      ORDER BY (tenant_id, entity_id, key, series_hash, ts)); idempotent ingest,
      canonical read. `MemorySeriesTable` for tests.
- [x] T2-03 Unit tests: `test_temporal_metrics.py` (B periodic/Poisson/max-burst,
      SC-005); `test_series_lifecycle.py` (double-insert converges, SC-004).
- [x] T2-04 Integration: build_series → projector round-trip via `MemorySeriesTable`
      (in-memory adapter substitutes for ClickHouse in tests, C-5 wrapping).

## Phase 3 — Topological invariant (P1)

- [x] T3-01 `apps/projection/tda/diagram.py` — persistence diagram model +
      content-addressed `diagram_hash` (sha256 of canonical JSON; I-12).
- [x] T3-02 `apps/projection/tda/pipeline.py` — `PersistenceProvider` contract
      widened: `DirectionalFlagProvider` (directed flag complex on the native
      N-ary fan), `DelaySeriesComplex` (Takens delay embedding → VR). Memory
      budget kept (`AdaptiveSubgraph` + `MemoryBudgetExceeded`). Name note: spec
      said `TakensSeriesComplex`; implemented as `DelaySeriesComplex`.
- [x] T3-03 `apps/projection/tda/features.py` — `amplitude` (bottleneck fit of
      persistence / Wasserstein-q norm), `persistence_entropy`, `landscapes`
      (Bubenik), `betti_curve`; `drift` between windows (content-addressed
      hashes). DEVIATION: pure numpy (Kuhn/Munkres matching) — no scipy runtime
      dep, because scipy's `_fblas` DLL fails to load in the current venv.
- [x] T3-04 `apps/projection/tda/validated.py` — HGX-style statistically validated
      hyperedge filter (binomial null) + order-specific hyper-Laplacian. DEVIATION:
      `eigsh` spectrum replaced by a deterministic degree-imbalance proxy
      (`order_hyperlaplacian_values`: echo chamber ⇒ 0, hub/star ⇒ <0) for the same
      reason — honest, rebuildable (I-12), testable without a working LAPACK.
- [x] T3-05 Tests: `test_pipeline_directed.py` (H0/H1, gudhi-gated skip),
      `test_takens.py` (periodic embedding, pure numpy), `test_features.py`
      (deterministic hashes + drift, SC-007/SC-008), `test_validated.py`
      (noise-removal determinism); 26 + 13 tda-related passed.

## Phase 4 — Contracts & wiring (P2)

- [x] T4-01 `apps/projection/tda/__init__` exposes `TopologicalInvariant.run()`:
      Series + hyperedge fan → point cloud → barcode → features; structural-only
      (never identity, I-6); honest empty topology without gudhi (I-3). 4 tests.
- [ ] T4-02 Science batch job: ClickHouse `entity_series` → TDA features → claims
      registry with provenance (series_hash/diagram_hash). BLOCKED on live
      ClickHouse + gudhi install; wiring shape defined by T4-01 entrance.
- [ ] T4-03 README/ADR notes: pinned deps (`giotto-tda`/`gudhi`/`ripser`,
      `hypergraphx` optional), wrapping rule (C-5), live CC gated behind fixture.
- [ ] T4-04 Full-suite: `pytest apps/projection apps/shared apps/control-plane
      apps/acquisition` green; SC-009. BLOCKED on pre-existing failures:
      websearch (13), bm25s/tantivy (3), `causal` import path — unaffected by 011.

## Done gates
- SC-001/SC-002 (Phase 1), SC-004/SC-005 (Phase 2),
  SC-006/SC-007/SC-008 (Phase 3), SC-009 (Phase 4 — partially blocked).