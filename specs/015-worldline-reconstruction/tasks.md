# Tasks: Worldline Reconstruction

**Input**: Design documents from `specs/015-worldline-reconstruction/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Tests**: Tests are included and are written first for each task group, per
`docs/CONTRIBUTING.md`.

**Organization**: Tasks are grouped by user story so each story can be implemented,
tested and delivered as an independent increment. Phase 0 is a hard gate: no application
code is written before the migration is proven on both paths.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependencies)
- **[Story]**: which user story the task belongs to

## Critical sequencing rules

1. Phase 0 completes before any application code. Editing revision `014` is forbidden.
2. Phase 1 (US2, query set) precedes Phase 2 (US1, frontier): frontier entries are keyed
   by query.
3. Phase 3 (US3, projection) follows Phases 1-2: assertions reference observations.
4. Phase 4 (US4/US5) is independent of Phase 3 and may proceed in parallel.
5. Phase 5 (US6, scale) is last: the pairwise oracle must exist before the indexed
   derivation can be proven equivalent to it.

---

## Phase 0: Setup and architectural gates (blocking)

**Purpose**: Accept the required ADRs and prove the forward-only migration on both
installation paths before any feature code is written.

- [x] T001 [P] Write ADR for the per-entity, run-independent reconstruction frontier, covering why `MaterializationCursor` is retained alongside it rather than re-keyed. Store under `docs/adr/`. -> `docs/adr/0019-reconstruction-frontier.md`
- [x] T002 [P] Write ADR for outbox lease, reclaim and `available_at` filtering semantics. -> `docs/adr/0020-outbox-lease-and-reclaim.md`
- [x] T003 [P] Write ADR for atomic per-entity stream sequence allocation via a counter row and `INSERT ... ON CONFLICT ... RETURNING`. -> `docs/adr/0021-atomic-stream-sequence.md`
- [x] T004 [P] Write ADR for indexed temporal relation derivation (sweep line plus ordered adjacency) with the pairwise implementation retained as a test oracle. -> `docs/adr/0022-indexed-worldline-relations.md`
- [x] T005 Confirm revision `014_temporal_materialization.py` is unmodified relative to its applied state; treat it as immutable from here on.
- [x] T006 Add forward-only migration `015_worldline_reconstruction` creating `source_query_set`, `source_query`, `reconstruction_frontier`, `entity_stream_sequence`, and adding the four outbox columns plus the partial unique index, per `data-model.md` section 10. -> `apps/control-plane/db/migrations/versions/015_worldline_reconstruction.py`
- [x] T007 Backfill `materialization_outbox.identity_fingerprint` from the existing `identity` JSONB before creating the partial unique index.
- [x] T008 Verify the migration on a fresh database applying all revisions in order.
- [x] T009 Verify the migration on a database that already has `014` applied, then compare both resulting schemas programmatically and assert equality.
- [x] T010 Add a regression test asserting revision `014` is not modified by any revision after it. -> `apps/control-plane/tests/unit/test_migration_forward_only.py`
- [x] T104 Repair the Alembic environment so migrations can actually run. **Discovered during Phase 0**, so numbered last to avoid renumbering 93 existing cross-references.

### T104 — discovered blocker: the migration path had never worked

`alembic upgrade` failed unconditionally with `Exception: Connection, url, or
dialect_name is required` for two independent reasons, which is why every code path in
this repository bootstraps via `Base.metadata.create_all` instead:

1. `alembic.ini` ships an empty `sqlalchemy.url` placeholder and `migrations/env.py`
   never injected one, despite a comment claiming it was injected from the environment.
2. No synchronous PostgreSQL driver is declared; the project has `asyncpg` only.

Fixed by resolving the URL from `POSTGRES_*` settings in `env.py` and running online
migrations through Alembic's async support, reusing the DSN the application already
uses. This adds no new dependency. Without this, T008 and T009 are unexecutable and the
"production DDL is left to Alembic" claim in `db/session.py` is false.

**Checkpoint**: ADRs accepted, migration proven on both paths. Only then may feature code
begin. Proves FR-033, SC-012.

---

## Phase 1: User Story 2 - Execute Every Search Route (P1)

**Goal**: Replace single-plan execution with an ordered, deduplicated, multi-route query
set that declares unsupported routes explicitly.

**Independent Test**: An identity with a URL, domain, alias, former name, username and
email produces one query per route; equivalent identities produce byte-identical sets;
routes with no provider appear as unsupported with a reason.

### Tests for User Story 2

- [ ] T011 [P] [US2] Test that a multi-route identity yields one `SourceQuery` per route kind in `apps/acquisition/tests/unit/test_source_query_set.py`.
- [ ] T012 [P] [US2] Test determinism under permuted identity key ordering: byte-identical query set.
- [ ] T013 [P] [US2] Test deduplication: two attributes normalizing to the same route produce one query listing both `origin_refs`.
- [ ] T014 [P] [US2] Test that a route with no registered provider appears in `unsupported` with `no_provider_for_route` and is never silently dropped.
- [ ] T015 [P] [US2] Test that an identity with no executable route yields an empty `executable` tuple and does not raise at plan time.
- [ ] T016 [US2] Test that the legacy `build_cc_plan` path remains reachable and unchanged for backward compatibility.

### Implementation for User Story 2

- [ ] T017 [P] [US2] Add `SourceQuery`, `SourceQuerySet`, `RouteProvider` and the `unsupported_reason` vocabulary in `apps/acquisition/source_query_set.py`.
- [ ] T018 [US2] Implement `build_source_query_set(surface, providers)` deriving all route kinds from the full `EntitySearchSurface`, with canonical ordering and deduplication (depends on T017).
- [ ] T019 [P] [US2] Add the `source_query_set` and `source_query` tables to `apps/control-plane/db/schema.py` (depends on T006).
- [ ] T020 [US2] Add `SqlSourceQueryStore` with tenant-scoped persist and read in `apps/control-plane/db/source_query_store.py` (depends on T019).
- [ ] T021 [US2] Wire the Temporal activity to execute every executable query rather than only `surface.cc_plan` in `apps/control-plane/workflows/temporal_materialization.py` (depends on T018).
- [ ] T022 [US2] Record per-run executed, pending and unsupported route state in the run result payload.

**Checkpoint**: All search routes execute; unsupported routes are declared. Proves FR-001
to FR-006, AS-006 to AS-009, SC-001.

---

## Phase 2: User Story 1 - Reconstruct the Whole Available History (P1)

**Goal**: Make history exhaustive and durable through a per-entity frontier, with
per-run budgets that defer rather than truncate.

**Independent Test**: With a budget smaller than the available work, repeated invocations
drive every frontier entry to a terminal state; an empty page is not exhaustion; a
transient failure stays open; an identical repeated page stops paging; resume performs no
re-fetch.

### Tests for User Story 1

- [ ] T023 [P] [US1] Test that exhausting the per-invocation budget leaves remaining entries open and returns `complete: false` with non-empty `remaining_work` in `apps/control-plane/tests/unit/test_reconstruction_frontier.py`.
- [ ] T024 [P] [US1] Test that repeated invocations eventually drive all entries to a terminal state.
- [ ] T025 [P] [US1] Test that a confirmed empty response marks `EXHAUSTED` while an empty response after a transient error does not.
- [ ] T026 [P] [US1] Test that a transport error leaves the entry `RETRYABLE` and does not mark the run complete.
- [ ] T027 [P] [US1] Test that a page identical to the previous page digest yields `EXHAUSTED_NO_PROGRESS` and stops paging.
- [ ] T028 [P] [US1] Test that `ensure_entries` is idempotent and never re-opens a terminal entry.
- [ ] T029 [P] [US1] Test that a newly advertised partition is added as open work while exhausted partitions stay exhausted.
- [ ] T030 [P] [US1] Test tenant isolation: a cross-tenant entity id resolves to no frontier rows.

### Implementation for User Story 1

- [ ] T031 [P] [US1] Add the `reconstruction_frontier` table and its indexes to `apps/control-plane/db/schema.py` (depends on T006).
- [ ] T032 [US1] Add `FrontierEntry`, `FrontierBudget`, `FrontierCounts` and the frontier state vocabulary in `apps/control-plane/db/reconstruction_frontier.py` (depends on T031).
- [ ] T033 [US1] Implement `ensure_entries`, `extend`, `claim_batch`, and the four terminal transitions in `SqlReconstructionFrontierStore` (depends on T032).
- [ ] T034 [US1] Implement `is_terminal` and `counts` as the completeness authority (depends on T033).
- [ ] T035 [US1] Classify provider outcomes into confirmed-empty, results, transient and malformed in `apps/shared/network/commoncrawl.py` (depends on T030).
- [ ] T036 [US1] Replace the in-memory partition slice in `apps/control-plane/services/cc_cursor_materialization.py` with frontier-driven selection under the per-invocation budget (depends on T033, T035).
- [ ] T037 [US1] Persist the per-page digest and enforce the no-forward-progress guard in the materialization loop (depends on T036).
- [ ] T038 [US1] Return `complete`, `budget_hit` and `remaining_work` in the run result and stop publishing a new generation when the frontier is non-terminal (depends on T034, T036).
- [ ] T039 [US1] Preserve the run-scoped cursor prepare/append replay path unchanged so crash recovery stays intact (depends on T036).

**Checkpoint**: History is eventually exhaustive and budgets defer. Proves FR-007 to
FR-014, FR-025, AS-001 to AS-005, SC-002, SC-003, SC-004.

---

## Phase 3: User Story 3 - Property-Change Worldline, Not Capture Log (P1)

**Goal**: Make the worldline fold over admitted assertions, with observations, assertions
and events as independently identified levels.

**Independent Test**: A capture yielding several relations plus one rejected relation
produces one event per admitted assertion with before/after state, no event for the
rejected relation, and a still-retrievable observation.

### Tests for User Story 3

- [ ] T040 [P] [US3] Test that a capture with several admitted relations produces one `entity.event` per admitted relation in `apps/shared/tests/unit/domain/test_assertion_worldline.py`.
- [ ] T041 [P] [US3] Test that a rejected, deferred or quarantined claim produces zero events, zero relations and zero state transitions.
- [ ] T042 [P] [US3] Test that the rejected claim remains retrievable with its decision, reason codes and score vector.
- [ ] T043 [P] [US3] Test that an observation yielding no admitted assertion is still written and yields an explicitly empty worldline interval.
- [ ] T044 [P] [US3] Test that an untrustworthy capture (revisit, truncated, digest mismatch) cannot alone produce an admitted assertion.
- [ ] T045 [P] [US3] Test that permuting the accepted assertion set yields an identical worldline, ordering, state transitions and fingerprint.
- [ ] T046 [P] [US3] Test that `cc.capture` is never folded as an assertion-level event and that `level` labelling distinguishes observation from assertion timelines.

### Implementation for User Story 3

- [ ] T047 [P] [US3] Add the `cc.observation`, `entity.assertion` and `entity.event` payload builders with deterministic identities in `apps/control-plane/services/capture_interpretation.py`.
- [ ] T048 [US3] Emit an observation record for every capture, including captures with no admitted claim (depends on T047).
- [ ] T049 [US3] Emit one assertion record per extracted claim carrying its admission decision, reason codes and score vector (depends on T047).
- [ ] T050 [US3] Gate event emission on an accepted admission decision and compute before/after state from accepted assertions only (depends on T049).
- [ ] T051 [US3] Continue writing `cc.capture` for backward compatibility while removing it as the worldline fold unit (depends on T048).
- [ ] T052 [US3] Add assertion-level folding with canonical ordering to `apps/shared/domain/temporal_worldline.py` (depends on T050).
- [ ] T053 [US3] Add explicit level labelling and level-aware reads to `apps/shared/domain/temporal_worldline_store.py` (depends on T052).
- [ ] T054 [US3] Carry accepted, rejected, deferred and quarantined counts into publication in `apps/control-plane/db/temporal_materialization.py` (depends on T050, T052).

**Checkpoint**: The worldline reports property changes, not captures; rejected claims
contribute nothing but stay visible. Proves FR-015 to FR-024, AS-010 to AS-014, SC-005,
SC-006.

---

## Phase 4: User Story 4 - Durable Request Boundary and Reliable Dispatch (P2)

**Goal**: Make entity creation the transactional boundary of the reconstruction request,
and make dispatch leased, reclaimable and honest about partial failure.

**Independent Test**: Creating an entity with no worker running leaves exactly one durable
pending request; a relay killed between claim and dispatch is reclaimed after lease expiry
and dispatched exactly once; a future `available_at` is not claimed early.

### Tests for User Story 4

- [ ] T055 [P] [US4] Test that entity creation commits the entity and exactly one pending request atomically in `apps/control-plane/tests/unit/test_reconstruction_request.py`.
- [ ] T056 [P] [US4] Test that a replayed creation with the same identity fingerprint does not create a second active request.
- [ ] T057 [P] [US4] Test that a claim stamped `DISPATCHING` with an expired lease is reclaimable and increments `reclaim_count`.
- [ ] T058 [P] [US4] Test that a row with `available_at` in the future is not claimed.
- [ ] T059 [P] [US4] Test that a partially failed dispatch batch reports per-row outcomes and is not reported as a full success.
- [ ] T060 [P] [US4] Test that the create-entity request path performs no inline dispatch and spawns no in-process pipeline task.
- [ ] T061 [P] [US4] Test that dispatching the same request twice does not start two concurrent reconstructions of one entity.

### Implementation for User Story 4

- [ ] T062 [P] [US4] Add `identity_fingerprint`, `lease_owner`, `lease_expires_at`, `reclaim_count` and `last_outcome` handling to `apps/control-plane/db/materialization_outbox.py`.
- [ ] T063 [US4] Filter `available_at <= now()` and reclaim expired `DISPATCHING` leases inside `claim_ready` (depends on T062).
- [ ] T064 [US4] Clear the lease on successful dispatch and schedule a future `available_at` on failure (depends on T063).
- [ ] T065 [US4] Make `create_entity` write the entity and the request in one transaction and remove the inline dispatch and in-process pipeline fallback in `apps/control-plane/api/routes/entities.py` (depends on T055, T062).
- [ ] T066 [US4] Make the relay the only dispatcher and report `dispatched`, `failed` and `reclaimed` per interval in `apps/control-plane/services/materialization_outbox_relay.py` (depends on T063).
- [ ] T067 [US4] Remove the `COGNITIVE_DURABLE_SQL` gate so durable SQL is the default, keeping in-memory strictly as an explicit test/dev fallback in `apps/control-plane/workflows/temporal_materialization.py`.
- [ ] T068 [US4] Make dispatch idempotent by request id so a reclaimed request cannot start a duplicate workflow.

**Checkpoint**: No entity exists without a durable request; no dispatch is stranded.
Proves FR-026 to FR-030, AS-015 to AS-018, SC-009, SC-010.

---

## Phase 5: User Story 5 - Honest Coverage and Partial Failures (P2)

**Goal**: Make coverage, partial failure and staleness queryable, and ensure a partial run
never presents as final.

**Independent Test**: Forcing one partition to fail while others succeed yields
`complete: false`, names the failing partition, keeps the previous publication current
with a staleness label, and exposes the state through the coverage endpoint.

### Tests for User Story 5

- [ ] T069 [P] [US5] Test that one failing partition with others succeeding yields `complete: false` and names the failing partition with its reason in `apps/control-plane/tests/unit/test_coverage_report.py`.
- [ ] T070 [P] [US5] Test that a partial run does not advance the publication head.
- [ ] T071 [P] [US5] Test that after a failing run the worldline returns the last valid publication with a staleness label.
- [ ] T072 [P] [US5] Test that the coverage report distinguishes `EXHAUSTED` from `EXHAUSTED_NO_PROGRESS`.
- [ ] T073 [P] [US5] Test that admission counts appear in the coverage report and in publication.
- [ ] T074 [P] [US5] Test that every new read endpoint denies cross-tenant access and returns no cross-tenant rows.

### Implementation for User Story 5

- [ ] T075 [P] [US5] Add the coverage report assembler over frontier, request and publication in `apps/control-plane/services/coverage_report.py`.
- [ ] T076 [US5] Gate publication on `is_terminal` and retain the previous generation with a staleness label otherwise (depends on T075, T038).
- [ ] T077 [US5] Add `GET /api/v1/entities/{id}/coverage` in `apps/control-plane/api/routes/entities.py` (depends on T075).
- [ ] T078 [P] [US5] Add `GET /api/v1/entities/{id}/queries` exposing executed and unsupported routes (depends on T077).
- [ ] T079 [P] [US5] Add `GET /api/v1/entities/{id}/observations` and `GET /api/v1/entities/{id}/assertions` in `apps/control-plane/api/routes/entities.py` (depends on T077).
- [ ] T080 [P] [US5] Add `GET /api/v1/entities/{id}/events` and `GET /api/v1/entities/{id}/materialization` in `apps/control-plane/api/routes/entities.py` (depends on T077).
- [ ] T081 [US5] Extend `GET /api/v1/entities/{id}/worldline` with `level`, completeness, staleness and degradation fields (depends on T052, T076).
- [ ] T082 [US5] Return `404` rather than another tenant's data for every new and changed endpoint (depends on T077).

**Checkpoint**: Coverage and partial failure are honest and queryable. Proves FR-014,
FR-024, FR-025, FR-038 to FR-040, AS-019 to AS-021, SC-013, SC-014.

---

## Phase 6: User Story 6 - Scale the Worldline (P3)

**Goal**: Replace the quadratic relation loop with indexed derivation, keeping the pairwise
implementation as an equivalence oracle.

**Independent Test**: A 10,000-event history derives successfully, matches the retained
pairwise oracle exactly, and stays within the performance budget; exceeding the relation
budget degrades with an explicit label.

### Tests for User Story 6

- [ ] T083 [P] [US6] Test indexed derivation equals the retained pairwise oracle on randomized interval sets in `apps/shared/tests/unit/domain/test_worldline_relations_index.py`.
- [ ] T084 [P] [US6] Test the 10,000-event fixture derives without a size-related failure and matches the oracle.
- [ ] T085 [P] [US6] Test that exceeding the relation budget yields explicit labelled degradation naming what was not computed, and never raises.
- [ ] T086 [P] [US6] Test that the pairwise oracle remains callable and is not removed.

### Implementation for User Story 6

- [ ] T087 [P] [US6] Add the indexed derivation with a single sort for `precedes`/`follows` and a sweep line for `overlaps` in `apps/shared/domain/worldline_relations_index.py`.
- [ ] T088 [US6] Integrate the indexed derivation as the production path in `apps/shared/domain/temporal_worldline.py`, retaining `derive_temporal_relations` unchanged as the oracle (depends on T087, T052).
- [ ] T089 [US6] Replace the `max_events` hard failure with a soft budget and labelled degradation in the build result (depends on T088).
- [ ] T090 [US6] Surface `degradation` in the worldline response and add the p95 timing assertion for a 10,000-event entity (depends on T089, T081).

**Checkpoint**: Large histories succeed with semantics identical to the oracle. Proves
FR-034 to FR-037, AS-022 to AS-024, SC-007, SC-008.

---

## Phase 7: Concurrency and consistency

- [ ] T091 [P] Add the `entity_stream_sequence` table and implement atomic range allocation inside the append transaction in `apps/control-plane/db/entity_stream.py` (depends on T006).
- [ ] T092 [P] Remove client-side `max(sequence) + 1` computation and the sequence-recomputing recovery path from `apps/control-plane/services/cc_cursor_materialization.py`.
- [ ] T093 [P] Add a concurrent same-entity append test proving no lost or duplicated records and no sequence collisions on live PostgreSQL.
- [ ] T094 [P] Add a crash-between-prepare-and-append test proving exact replay with no re-fetch.

**Checkpoint**: Concurrency and crash recovery are proven. Proves FR-031, FR-032, SC-011.

---

## Phase 8: Polish and validation

- [ ] T095 Run `ruff check` and `ruff format --check` over all touched packages.
- [ ] T096 Run `python -m compileall` over the touched packages.
- [ ] T097 Run the full focused pytest suites: acquisition, shared domain, control-plane.
- [ ] T098 Run quickstart Phases 0 to 5 (offline and live PostgreSQL) and record results.
- [ ] T099 Run quickstart Phase 6 live Common Crawl end to end, including the repeated scheduler cycle proving SC-002, and capture the coverage output.
- [ ] T100 Run quickstart Phase 7 tenant isolation and staleness checks.
- [ ] T101 Run quickstart Phase 8 full regression gate.
- [ ] T102 Verify no raw evidence mutation, no rejected claim producing an event, no false `complete: true`, and no re-fetched work on resume.
- [ ] T103 Record acceptance evidence per success criterion against `contracts/operations.md`.

**Checkpoint**: Feature is validated end to end with recorded evidence for every success
criterion.

---

## Requirement coverage by task

| Requirement | Tasks |
| --- | --- |
| FR-001 to FR-006 | T011 to T022 |
| FR-007 to FR-014 | T023 to T039, T075 |
| FR-015 to FR-022 | T040 to T053, T087 to T090 |
| FR-023 to FR-025 | T041, T054, T070, T076 |
| FR-026 to FR-030 | T055 to T068 |
| FR-031 to FR-032 | T091 to T094 |
| FR-033 | T005 to T010 |
| FR-034 to FR-037 | T083 to T090 |
| FR-038 to FR-040 | T069 to T082 |

## Success criterion coverage by task

| Criterion | Verified by |
| --- | --- |
| SC-001 | T011 to T016, quickstart Phase 6 |
| SC-002 | T023, T024, quickstart Phase 6 repeated scheduler cycle |
| SC-003 | T028, T039, T094 |
| SC-004 | T025, T026 |
| SC-005 | T041, T042 |
| SC-006 | T045 |
| SC-007 | T084 |
| SC-008 | T090 |
| SC-009 | T055, quickstart Phase 4 |
| SC-010 | T057, quickstart Phase 3 |
| SC-011 | T093, quickstart Phase 3 |
| SC-012 | T008, T009 |
| SC-013 | T074, T082, quickstart Phase 7 |
| SC-014 | T071, quickstart Phase 7 |

