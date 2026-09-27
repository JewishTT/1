# Tasks: Discovery & Rebuildable Search Projection Fabric

**Input**: Design documents from `/specs/008-discovery-search-fabric/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: included and **mandatory** — SC-007 makes a green offline suite an exit criterion,
and the largest single item in this feature *is* the missing test surface.

**Baseline (recorded 2026-09-26, run from `1/`)**:

```bash
uv run --project apps/projection pytest apps/projection/tests -q
#   ERROR test_bm25s_backend.py, ERROR test_relevance.py — Interrupted: 2 errors during collection
uv run --project apps/acquisition pytest apps/acquisition/tests apps/shared/tests/unit/websearch -q
#   15 failed, 134 passed, 10 skipped
uv run --project apps/acquisition pytest apps/shared/tests/unit/websearch -q
#   2 failed, 21 passed      <-- the 13 extra failures are cross-suite pollution (T033)
```

**Organization**: Phase 0 unblocks everything. Phases 1, 3 and 4 touch disjoint files and run
concurrently. Within a phase, `[P]` tasks are concurrent.

---

## Phase 0: Unblock (BLOCKS EVERYTHING)

**Purpose**: `search/indexer.py:23` imports a module that does not exist. Until this lands, no
search-plane test can be collected and no other phase in this feature can be verified.

- [ ] **T001** Create `apps/projection/search/bm25s_backend.py` with `BM25SRankedIndex`
      implementing the same duck-typed surface as `search/relevance.py::RankedInvertedIndex`:
      `available() -> bool` classmethod, a `backend` tag of `"ranked-bm25s"`, and the
      `search`/`index_doc` surface that `search/indexer.py:28-31,44,110,125` depends on.
      Ranked (BM25) retrieval, not term intersection. Pure ranking: no tenant logic.
- [ ] **T002** Verify the projection suite collects and runs:
      `uv run --project apps/projection pytest apps/projection/tests -q` → no collection errors.
      `default_ranked_index()` (indexer.py:28) MUST return a `BM25SRankedIndex` when bm25s is
      importable — `test_bm25s_backend.py:136-137` pins this.
- [ ] **T003** `[P]` Run `uv run --project apps/projection ruff check apps/projection` and fix
      only issues introduced by T001.

**Checkpoint**: `164 collected` becomes a real, passing suite. Every later phase is verifiable.

---

## Phase 1: Query-surface defects (independent of everything below)

**Goal**: fix the two real bugs on FR-015 / Constitution IV. Touches one file, no overlap with
any other phase.

- [ ] **T004** `[P]` `apps/control-plane/tests/unit/test_query_fusion.py` — **write first, watch
      it fail.** Assert that two hits for the same `doc_id` from *different sources* score
      differently from two hits from the *same source* (Constitution Governance: publication
      count is not independent-source count), and that `FusedResult` retains `relevance` and
      `support` separately so a client can re-derive the composite.
- [ ] **T005** `[P]` `apps/control-plane/tests/unit/test_query_degradation.py` — **write first.**
      (a) one raising backend still returns the healthy backend's results with
      `degraded_backends` naming the failure; (b) **all** backends failing raises
      `AllBackendsFailed`, it does **not** return `[]`; (c) the error is `type: message`,
      truncated, no traceback.
- [ ] **T006** Fix the fusion no-op at `apps/control-plane/services/query_planner.py:100`
      (`EVIDENCE_BASE * max + (1 - EVIDENCE_BASE) * max` ≡ `max`). Replace with
      `relevance * (1 + EVIDENCE_BASE * (support - 1))` where `support` counts distinct
      `source_id`. Add `relevance` and `support` to `FusedResult`. Do **not** collapse them into
      a stored single score (Constitution IV). T004 must go green.
- [ ] **T007** Fix failure isolation at `query_planner.py:85` (`asyncio.gather` with no
      `return_exceptions`). Isolate per backend, populate `degraded_backends`, add
      `AllBackendsFailed` for the total-outage case. T005 must go green.
- [ ] **T008** Make fused ordering deterministic: sort by `composite` desc, ties broken by
      `doc_id`, so identical inputs give identical output.

**Checkpoint**: FR-015 and SC-006 are provable. Nothing else in this phase touches this file.

---

## Phase 2: Migration + frontier bridge

**⚠️ Sequential within the phase** — T011 needs the column from T009.

- [ ] **T009** `apps/control-plane/db/schema.py` — add to `FrontierItem`:
      `provenance: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")`.
      Do **not** touch `uq_frontier_schedule (tenant_id, uri)` — FR-006 idempotency depends on
      that unique index and rebuilding it under load is a self-inflicted outage. Not indexed:
      provenance is read for audit, never queried.
- [ ] **T010** `apps/control-plane/db/migrations/versions/017_discovery_provenance.py` —
      forward-only, add-column only. Previous revision immutable (precedent: `014`, `015`,
      `016`).
- [ ] **T011** `[P]` `apps/control-plane/tests/unit/test_migration_017_forward_only.py` — prove
      **both** paths: upgrade from head, and fresh create. Follow
      `test_migration_016_forward_only.py`.
- [ ] **T012** `apps/control-plane/services/discovery_frontier.py` — `FrontierSinkAdapter`
      implementing the Layer A `FrontierSink` protocol (contract §3). MUST: feed the
      **canonical** URL; write full `provenance` to the new column; widen `priority`
      `int → float` without clamping; derive `host_key` via an injected callable; **never** set
      `state`, `lease_until`, `next_schedule_at` or `retries` (ADR-0016/0017 — setting them
      makes discovery a scheduler); must not raise on the dedup path (a duplicate is success).
- [ ] **T013** `apps/control-plane/tests/integration/test_frontier_provenance.py` — FR-007
      survives the bridge: `method`, `query`, `seen_by[]` all readable from the row; a second
      `enqueue` of the same canonical URL creates **no** second row; `state` is `READY` and no
      schedule field was written.

**Checkpoint**: discovery can reach the durable frontier with provenance intact. US1 scenario 1
is provable end to end.

---

## Phase 3: Layer A proof (no new adapter logic)

**Goal**: the discovery package has **zero** tests today. It is also the package with the most
subtle logic (canonicalisation, coalesce ordering, source-failure auditing).

- [ ] **T014** `[P]` `apps/acquisition/tests/unit/test_discovery_contracts.py` — the
      canonicalisation table from `quickstart.md` §1 as explicit cases: scheme/host lowercasing,
      trailing-dot strip, default-port drop, fragment drop, **trailing slash preserved**,
      query preserved, non-http(s) → `None`. Plus `coalesce` determinism: first-wins scalars,
      `confidence` = max, `seen_by` accumulates in encounter order, output sorted by canonical
      URL, and **replaying the same input twice yields identical output**.
- [ ] **T015** `[P]` `apps/acquisition/tests/unit/test_discovery_registry.py` — dedup to one
      frontier row per canonical URL across three sources with merged provenance (SC-002);
      a raising source lands in `sources_failed` and the pass still completes (US1 scenario 3);
      an empty source lands in `empty_sources` and is kept **distinct** from failure;
      `report` is byte-identical on replay.
- [ ] **T016** `[P]` `apps/acquisition/tests/unit/test_discovery_sources.py` — all four sources
      (`commoncrawl_index`, `wayback_cdx`, `crtsh`, `linkgraph`) driven through their existing
      injection seams (`query_fn` / `transport` / `edge_provider`). Zero network. Assert each
      returns `Candidate`s with provenance and drops non-http(s).
- [ ] **T017** `[P]` `apps/control-plane/tests/unit/test_discovery_registration.py` — FR-018 /
      SC-008: a source declaring a capability outside `{index, web-graph, api}` is refused at
      `register()`; a source declaring it needs auth/CAPTCHA/paywall is refused **at
      registration**, and the refusal is auditable before any query is issued. This is a
      `registry.py` change: add the guard, do not add a network call.
- [ ] **T018** `apps/control-plane/services/discovery_frontier.py` — add `LinkEdgeProvider`
      reading the graph projection via `adjacency_from_store`. MUST return only
      provenance-bearing edges, MUST be tenant-scoped, MUST NOT re-derive entity identity
      (FR-014).
- [ ] **T019** `[P]` `apps/acquisition/tests/unit/test_link_edge_provider.py` — edges without
      provenance are **not** returned (Constitution II); cross-tenant node is refused; node ids
      are the same identifiers the search projection uses (FR-014); `to_tda_input()` returns
      stable integer index triples over a stable ordering (FR-013).

**Checkpoint**: FR-002 – FR-007, FR-013, FR-014, FR-018 provable offline.

---

## Phase 4: Layer B proof (concurrent with Phase 3 — disjoint files)

- [ ] **T020** `[P]` `apps/projection/tests/test_mappings.py` — `physical_index_name` /
      `alias_name` naming and the empty-tenant `ValueError` guards; `doc_mapping` field
      ordering is deterministic; `index_config` carries a `kafka` source bound to
      `search.projected` with `enable_backfill_mode` and an `s3://` `index_uri`;
      `all_index_configs` covers exactly `DOC_KINDS` (7, not 6).
- [ ] **T021** `[P]` `apps/projection/tests/test_quickwit.py` — `_prepare` raises on a document
      without `tenant_id` (`quickwit.py:152`); `search` raises `TenantIsolationError` on a
      cross-tenant scope (L93) and **never** degrades to an empty list; `rebuild` is idempotent.
- [ ] **T022** `[P]` `apps/projection/tests/test_publisher.py` — depends on T024 existing, so
      **write it first and watch it fail**. A document without `tenant_id` or `kind` is
      **rejected, not published** (the Quickwit filter `mappings.py:150-154` would drop it from
      every index — silent data loss); publication is idempotent on
      `(doc_id, tenant_id, kind)`; a broker failure does not propagate to the index write.
- [ ] **T023** `apps/projection/search/projector.py` — derive `INDEX_ALIASES` from
      `mappings.DOC_KINDS` (D8). One source of truth; a new kind cannot be added to one list
      and forgotten in the other.
- [ ] **T024** `apps/projection/search/publisher.py` — `SearchProjectionPublisher` (contract §6).
      MUST: reject a doc missing `tenant_id`/`kind`; sit **downstream of the index write** so a
      publication failure can never fail or roll back the write; be idempotent on
      `(doc_id, tenant_id, kind)`; partition by `tenant_id`; never block the projector beyond
      the transport timeout.
- [ ] **T025** `apps/projection/tests/test_projection.py` — upgrade the smoke test into a real
      determinism proof: build → rebuild → build → rebuild ×2, comparing the **full document id
      set and a digest** (SC-003, SC-010). Assert 0 duplicates. Also assert the projector
      accepts exactly `DOC_KINDS` and rejects an unknown kind.

**Checkpoint**: FR-008 – FR-012, SC-003, SC-010 provable.

---

## Phase 5: Producer wiring + query bindings + routes

- [ ] **T026** `[P]` `apps/control-plane/services/search_backends.py` — real `BackendClient`
      adapters over the search projection and the graph projection, replacing the
      `MemoryBackend` fixtures. Both tenant-scoped. A hit whose `observation_id` does not
      resolve MUST be dropped, not returned with a null observation.
- [ ] **T027** `apps/control-plane/api/routes/search.py` — bind the real planner. Add
      `degraded_backends` to the response. HTTP **503** on total backend failure, never
      `200 {"results": []}`. Remove the tenant-ignoring fixture path from the request path.
- [ ] **T028** `[P]` `apps/control-plane/api/routes/discovery.py` — `POST /discovery/run`
      (contract api.md §3). Returns the `DiscoveryReport` verbatim. `candidates` capped at
      100 / max 1000 with `candidates_found` reporting the **true** total — a silent truncation
      would make the report lie. `sources_failed` errors truncated, no tracebacks.
- [ ] **T029** `[P]` `apps/control-plane/api/routes/search_rebuild.py` —
      `POST /search/rebuild` (admin, tenant-scoped, rate-limited). Rebuilds from the **log
      only** and MUST NOT read the previous generation — that is what proves it is a projection.
      Reports `duplicates` rather than asserting zero.
- [ ] **T030** `[P]` `apps/control-plane/tests/integration/test_discovery_api.py` — seed →
      candidates → exactly-once frontier rows; partial source failure still returns 200 with
      failures in the body; unauthorised is a non-2xx.
- [ ] **T031** `[P]` `apps/control-plane/tests/integration/test_search_rebuild.py` — delete the
      generation, rebuild from the log, identical document set, 0 duplicates; rebuild is safe
      while producers are live.
- [ ] **T032** Emit the four events. `discovery.discovered` from `DiscoveryRegistry` (one
      envelope per coalesced candidate; `tenant_id`/`investigation_id` in the **envelope**;
      deterministic `event_id` from `(tenant_id, canonical_url, source-set)`);
      `search.projected` from T024. `discovery.seed` from Investigation creation;
      `graph.projected` is **explicitly out of scope** — record it in
      `docs/adr/0025-*.md` as owned by the graph projection, do not build it here.

---

## Phase 6: Test isolation + governance + polish

- [ ] **T033** Fix the cross-suite pollution: 2 websearch failures alone vs **13** when any
      acquisition test file is co-collected. Both `conftest.py` files are empty, so it is an
      import-time global in an acquisition module, not a fixture. Reproduce with:
      `uv run --project apps/acquisition pytest apps/acquisition/tests/unit/test_cc_plan.py apps/shared/tests/unit/websearch -q`
      → must go from 13 failed to 2. Do **not** paper over it with `-p no:randomly` or by
      skipping tests.
- [ ] **T034** `[P]` Triage the 2 residual websearch failures (pre-existing, not this feature's
      requirements): `TestQueryBuilder::test_name_becomes_quoted_entity_query_first`,
      `TestDiscoverySink::test_host_diversity_caps_one_source`. Determine per failure whether
      the **test** or the **source** is wrong, and fix the right side. Do not absorb these into
      this feature's exit criteria without saying so explicitly.
- [ ] **T035** `[P]` `docs/adr/0025-kafka-native-search-projection.md` — evolution of ADR-0004:
      Kafka ingest + object-storage-resident index, why the publisher is a separate component
      rather than inside `SearchIndex`, and the alias-swap generation lifecycle. Required by
      Constitution Governance. Record `graph.projected` as owned by the graph projection.
- [ ] **T036** `[P]` `docs/adr/0026-frontier-provenance.md` — why provenance moves to the
      frontier row, and why it is deliberately **not** indexed.
- [ ] **T037** `[P]` Observability per `contracts/operations.md` §4. **Hard rule:** never label
      a metric by URL — unbounded cardinality is a denial-of-service vector against the metrics
      store (Constitution VII). `search.projected.publish.skipped_no_tenant` must exist and must
      read 0.
- [ ] **T038** Full-workspace regression run and record the new baseline in `quickstart.md` §6.
      Confirm the projection suite is no longer interrupted and the combined
      acquisition+websearch run matches the expected table.
- [ ] **T039** Component-inventory diff for SC-012 / FR-017: exactly one new table column, zero
      new tables, zero new queues, zero new orchestration components. If anything else appeared,
      justify it in `plan.md` Complexity Tracking or remove it.
- [ ] **T040** `[P]` Update `docs/architecture/overview.md` + `fabric-collection.md` with the
      discovery → frontier → acquisition flow now that it is actually wired.

---

## Dependencies & Execution Order

```text
Phase 0 (T001-T003)  ── BLOCKS EVERYTHING (collection is interrupted without it)
     │
     ├──► Phase 1 (T004-T008)          query defects          ─┐
     │                                                           │ independent
     ├──► Phase 2 (T009-T013)  ─► Phase 5a (T026-T027)         │
     │        migration+bridge          query bindings          │
     │                                                           │
     ├──► Phase 3 (T014-T019)  ──► Phase 5b (T028, T030)       │
     │        Layer A proof              discovery route        │
     │                                                           │
     └──► Phase 4 (T020-T025)  ──► Phase 5c (T029, T031, T032) │
              Layer B proof              publisher + rebuild    │
                                        │
                              Phase 6 (T033-T040)  isolation, ADRs, baseline
```

- **Phase 1, Phase 3, Phase 4 are mutually independent** — disjoint files, run concurrently.
- **Phase 2 is internally sequential**: T012/T013 need T009's column.
- **Phase 4 is internally sequential**: T022 must be written before T024 exists.
- **Phase 5 depends on Phases 1, 2, 3 and 4** but its three halves are independent of each other.

### Parallel opportunities

- T003, T004, T005, T011, T014, T015, T016, T017, T019, T020, T021, T022, T026, T028, T029,
  T030, T031, T034, T035, T036, T037, T040 — all `[P]`, all disjoint files.
- After Phase 0 lands, Phases 1 + 3 + 4 can run as three concurrent workstreams.
- **Test-first is mandatory in Phase 1 and T022**: T004, T005 and T022 must be observed failing
  before T006, T007 and T024 are written. A test written after the fix proves nothing.

---

## Implementation Strategy

### MVP = Phase 0 + Phase 1

Phase 0 alone converts an interrupted suite into a green one — that is the fastest possible
real delivery and it is pure restoration. Phase 1 fixes two production bugs on FR-015. Together
they are a shippable, independently valuable increment.

### Then the proof layer

Phases 3 and 4 add no new behaviour; they make ~8 existing modules provable for the first time.
This is the bulk of the feature by volume and it is what turns the spec's success criteria from
assertions into checks.

### Then the wiring

Phase 5 makes the fabric reachable: real query backends, a discovery route, a rebuild route, and
the missing event producers. Only now is "Kafka-native" true rather than declarative.

### MVP First (Phase 0 + Phase 1 only)

1. Phase 0 → verify the projection suite collects
2. Phase 1 → verify both query tests fail, then pass
3. **STOP and validate**
