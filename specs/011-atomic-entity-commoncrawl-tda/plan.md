# Implementation Plan: Atomic Entity Invariant × Common Crawl Full Pilot × TDA

**Branch**: `011-atomic-entity-commoncrawl-tda` | **Date**: 2026-09-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/011-atomic-entity-commoncrawl-tda/spec.md`

## Summary

Adds three surfaces on top of the existing fabric, all reuse-not-reinvent:

1. **Common Crawl zero layer** — DuckDB-over-HTTP/S3-Range against the columnar URL
   index (no download), byte-range pulls of WARC/WET, deterministic LLM-free extraction
   into content-addressed `Observation`s.
2. **Atomic entity lifecycle** — `Series` materialized in ClickHouse behind
   `ReplacingMergeTree(ts)` keyed by (tenant, entity, key, series_hash); deterministic
   temporal metrics (burstiness B, latency/efficiency, causal fidelity c, characteristic
   timescale) as point-cloud dimensions.
3. **Topological invariant** — TDA core over gudhi/giotto/ripser: VR over distance
   matrices, directed flag complexes (`FlagserPersistence`), Takens embeddings of Series;
   content-addressed persistence features; bottleneck/Wasserstein drift; HGX-style
   statistically validated hyperedge facets.

## Existing state (verified 2026-09-22)

- `apps/shared/domain/dynamics.py` — stream identity, fold, `Series`/`build_series`
  (cumulative/inter_arrival). Reuse unchanged.
- `apps/shared/domain/hypergraph.py` — typed temporal hypergraph, `hyperedge_id`.
- `apps/shared/domain/fabric.py`, `apps/shared/domain/stream_events.py` — fabric facade.
- `apps/control-plane/db/schema.py:742` — `entity_stream` life-stream table.
- `apps/projection/tda/pipeline.py` — GUDHI SimplexTree VR only; extend with
  directed flag complexes + a provider contract already present (`PersistenceProvider`).
- `apps/acquisition/adapters/commoncrawl/index.py` — CC index adapter (T092); re-export
  of a `network.commoncrawl` module. DuckDB session is new.
- `apps/projection/pyproject.toml` already has `duckdb`, `giotto-tda`, `gudhi`.
- ClickHouse: ADR-0005 accepted; no series projection exists yet.

## Phase 1 — Common Crawl zero layer

- `apps/acquisition/network/commoncrawl/` (new package):
  - `session.py` — `CcIndexSession`: DuckDB connect (`motherduck`-free, local-wide),
    `query_domain(url_pattern, crawl)` over the URL-index parquet table, deterministic
    record selection; transport seam for HTTP/S3-range.
  - `range_pull.py` — `pull_warc_range(locator, transport)`: byte-exact range GET of
    `warc_filename@offset,length`; parse WARC/WET headers into transferables.
  - fixture parquet slice under `apps/acquisition/tests/fixtures/cc_index/`.
- Reuse `adapters/commoncrawl/index.py` surface: shape unchanged, session behind it.

## Phase 2 — Lifecycle: ClickHouse projection + temporal metrics

- `apps/control-plane/services/series_lifecycle.py` (or shared): `SeriesProjector`
  writing to `entity_series` table:
  ```sql
  ENGINE = ReplacingMergeTree(ts)
  PARTITION BY toYYYYMM(ts)
  ORDER BY (tenant_id, entity_id, key, series_hash, ts)
  ```
  ingest idempotent on (key, series_hash, ts); `FINAL` canonical read.
- `apps/shared/domain/temporal_metrics.py`:
  - `burstiness(inter_arrival)` → B∈[−1,1] (periodic=−1, Poisson≈0, max-burst=1);
  - `latency/efficiency` over time respecting paths (Series adjacency),
  - `causal_fidelity(temp_paths, static_paths)` → c,
  - `characteristic_timescale(mode of shortest-path durations)`;
  empty input → empty output (I-3).

## Phase 3 — Topological invariant

- `apps/projection/tda/pipeline.py` (extend):
  - `GudhiProvider` stays; add `FlagserProvider` (directed flag complex) behind the
    existing `PersistenceProvider` contract (protocol widened to accept `directed`);
  - `TakensSeriesComplex` — delay embedding of a `Series` → point cloud → VR.
- `apps/projection/tda/features.py`:
  - `persistence_vectorize`: amplitude (bottleneck/Wasserstein), persistence entropy,
    landscapes, Betti curve; content-addressed via `series_hash`/input hash.
  - `drift`: bottleneck/Wasserstein between two windows' diagrams.
- `apps/projection/tda/validated.py` — `statistically_validated_hyperedges(hypergraph,
  null_model)` HGX-style filtering; order-specific hyper-Laplacian eigenvalues
  (`eigsh` on order-L_k) as facets.
- `apps/projection/tda/tests/` — deterministic fixtures, memory-budget enforcement,
  directed H0/H1, Takens periodic, noise-injected hyperedge filter.

## Phase 4 — Contracts & wiring

- `projection` exports a `tda/` science surface: `TopologicalInvariant` reads Series
  + hyperedge fan → point cloud → barcode → `PersistenceFeature` claims (structural
  only, never identity).
- ClickHouse projector consumed from `science/` batch jobs; results registered on
  claims registry with provenance (record hashes / series hash).
- No new orchestration backbone; Temporal drives batch jobs.

## Constitution Check

- **I-1/I-3/I-5** — observations immutable, empty series stay empty, refs-only payloads. ✓
- **I-6** — TDA/science never issues identity claims. ✓
- **I-11/I-12** — Series/ClickHouse/TDA features all rebuildable, content-addressed. ✓
- **C-5** — libraries (gudhi/giotto/ripser/HGX) wrapped behind contracts, no domain imports. ✓
- **C-6/C-7** — process-centric; CC sources public-interface only. ✓