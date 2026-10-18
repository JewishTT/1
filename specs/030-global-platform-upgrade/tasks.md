---

description: "Task list for COGNITIVE Global Platform Upgrade — Context Engine as Research Process Kernel"
---

# Tasks: COGNITIVE Global Platform Upgrade

**Input**: Design documents from `/specs/030-global-platform-upgrade/`

**Prerequisites**: [`plan.md`](./plan.md), [`spec.md`](./spec.md), [`research.md`](./research.md),
[`data-model.md`](./data-model.md), [`contracts/`](./contracts/), [`quickstart.md`](./quickstart.md)

**Tests**: INCLUDED — mandatory. The specification's acceptance criteria (`SC-001`…`SC-017`) are only
satisfied by a machine-verifiable test or a checkable operational artifact. Every task marked
`[x]` requires evidence: a file:line reference or a recorded command with exit status.

**Organization**: Tasks are grouped by user story so each is independently implementable, testable
and shippable. The **work-package order (WP0→WP12) in `plan.md` is authoritative**; phases here map
onto it and are listed in the Dependencies section.

---

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel — different files, no dependency on an incomplete task
- **[Story]**: `[US1]`…`[US7]` map to the user stories in `spec.md`
- Exact file paths in every description

### Status markers (from `plan.md` §Notes)

| Marker | Meaning |
|---|---|
| `[ ]` | Not executed |
| `[~]` | Partial — works, incomplete |
| `[x]` | **Verified implemented** — code present, called from a live path, contract test passing |
| `[!]` | **Blocked** — requires a named dependency, owner and next action |

`[x]` is never justified by "the code was written". It requires evidence in the task row.

---

## Repo conventions this task list inherits

**[MEASURED] 2026-10-14** — violating any of these breaks the suite silently:

| Rule | Why |
|---|---|
| `pyproject.toml:36` — `testpaths = ["apps"]` | without it: 6769 tests, **831 collection errors** from `donors/` |
| `pyproject.toml:79` — `asyncio_mode = "auto"` | without it: 71 context-engine tests fail only under the root config |
| `pyproject.toml:88` — `--import-mode=importlib` | without it: **98 passing tests hidden**, incl. 3 transport-critical |
| `bench` must not share a collection root with `apps` | `ImportError: cannot import name 'harness' from 'bench'` |
| Kernel path is `apps/control-plane/context_engine/` | do **not** create `apps/context-engine/` |
| No `specs/030*` number reuse | `001`–`029` occupied |

---

# Phase 1: Setup — Trustful Baseline (WP0)

**Purpose**: Prove what exists before changing anything. Nothing architecture-changing starts here.

- [ ] T001 Resolve the port conflict: identify what holds `localhost:5432` and `localhost:9000` (owner is pid 12640 `com.docker.backend`, `docker ps` returns empty) and release it, or point the suite at a working instance via `COGNITIVE_PG_DSN` — record the outcome in `specs/030-global-platform-upgrade/current-state-audit.md §0`. **If unresolved, mark every affected test BLOCKED, never PASS** (SC-016)
- [ ] T002 Record the verified starting point into `specs/030-global-platform-upgrade/current-state-audit.md §0`: `git rev-parse HEAD`, `git branch --show-current`, `git status --porcelain` (147 entries at HEAD `608c3ad8`), `python --version`, `uv --version`, `node --version`, lockfile digests
- [ ] T003 [P] Run and record the full baseline: `.venv\Scripts\python.exe -m pytest -q` from `1/` → `specs/030-global-platform-upgrade/current-state-audit.md §1`. Classify every failure/skip/error as PASS/FAIL/BLOCKED/NOT-RUN with the exit status preserved. Compare against `specs/029-research-closed-loop-upgrade/quickstart.md` (`22 failed, 4288 passed, 27 skipped`) — a different failure set is a regression
- [ ] T004 [P] Run and record collection-only: `.venv\Scripts\python.exe -m pytest --co -q` → expect `4336 collected, 0 errors`. Any error from `donors/` or `tmp/` means `pyproject.toml` `testpaths`/`norecursedirs` was lost
- [ ] T005 [P] Run and record the bench suite separately from `1/bench/`: `..\.venv\Scripts\python.exe -m pytest -q` — never alongside `apps/`
- [ ] T006 Build the capability matrix in `specs/030-global-platform-upgrade/current-state-audit.md §2` with columns `Capability | Spec claim | Implementation path | Real callers | Persistence | Unit | Contract | Integration | E2E | Operational service | Known defects | Verified commit`. Every row cites a `file:line` or a test. Mark plainly any function returning constant success, unused registry, ignored projection id, test-only consumer, or unreachable service config
- [ ] T007 [P] Trace one end-to-end investigation through **real calls** — API → context engine → `query_cycle.py` → acquisition → `return_path.py` → `invariant_reducer.py` → projection → findings — and record the actual state/event/data path in `current-state-audit.md §3`. A grep hit is not a caller
- [ ] T008 [P] Build the authoritative-store ownership map in `current-state-audit.md §4`: for each field, exactly one owner. Flag any same-field dual authority, including the `neo4j` driver declared in `apps/control-plane/pyproject.toml` with no matching configuration variable in `.env.example`
- [ ] T009 [P] Measure real scale figures in `current-state-audit.md §5`: corpus size, tenant count, event volume, graph cardinality, observation count. These are **[UNVERIFIED]** in `research.md §1.5` — no capacity claim may be made until they exist
- [ ] T010 [P] Identify retention/erasure policy in `current-state-audit.md §6`: locate it relative to `apps/shared/isolation.py`. Feeds `ADR-030-11`
- [ ] T011 Map graph/TDA/temporal duplicate execution paths and name **one production owner per operation** — resolve `U-01` and `U-02` from `research.md §8`. Three TDA trees exist (`apps/projection/tda/`, `apps/science/scitda/`, `GraphInvariant.to_tda_input`) and both `gudhi` and `giotto-tda` are installed; record which is actually called and from where
- [ ] T012 Produce the giotto-tada licence disposition in `current-state-audit.md §7`: it is **AGPL-3.0** and was installed as an `apps/projection` dependency with no recorded disposition. Verdict: canonical / isolate as sidecar / remove. Feeds `ADR-030-09`
- [ ] T013 Extend the verified donor matrix from `specs/029-research-closed-loop-upgrade/donors/donor-matrix.md` into `specs/030-global-platform-upgrade/donor-matrix.md`. Carry forward the 9 REJECT verdicts (ranknexus, fuse, QUANTA, IntelShed, worker-browser, Stablerank, OptLLM, lcc, nax), the 6 AMBIGUOUS, RCL no-licence, Phoenix Elastic-2.0, Common Crawl data indemnity. Add `apps/projection`'s **already-installed** gudhi/giotto-tda/duckdb/bm25s dispositions
- [ ] T014 Reconcile `specs/024`, `specs/025`, `specs/026`, `specs/028`, `specs/029` and `docs/README.md` against the executing commit in `current-state-audit.md §8`. Correct historical claims that conflict with code rather than copying them forward

**Checkpoint**: A source-backed baseline exists. **No architecture-changing work starts before this.**

---

# Phase 2: Foundational — Governance and Contracts (WP1 + WP2)

**Purpose**: The blocking prerequisites. **No user story work begins until this completes.**

**⚠️ CRITICAL**: Every story depends on the contracts below. Building a story on an unversioned
contract is how two authorities appear.

## 2.1 Governance

- [ ] T015 [P] Fill `.specify/memory/constitution.md` — currently **[MEASURED]** 50 lines of unfilled template (`[PRINCIPLE_1_NAME]`, `[SECTION_2_CONTENT]`, `[CONSTITUTION_VERSION] | [RATIFICATION_DATE]`, all verbatim). Encode the 15 principles enforced in `plan.md §Constitution Check`. Set `Version` and `Ratified`
- [ ] T016 [P] Write `docs/adr/ADR-030-01-context-graph-authority.md` — ContextGraph is authoritative durable state for research-process relationships only, backed by `PostgresContextGraphStore`; it is not authoritative for real-world entity relations (FR-030, P8)
- [ ] T017 [P] Write `docs/adr/ADR-030-02-observation-membership-outbox.md` — transaction boundary reusing the **existing** outbox at `apps/control-plane/db/materialization_outbox.py` + `apps/control-plane/services/materialization_outbox_relay.py`; no second consistency mechanism (FR-063, FR-062)
- [ ] T018 [P] Write `docs/adr/ADR-030-03-identity-merge-split.md` — append-only resolution decisions; merge/split supersede, never rewrite (FR-080–084)
- [ ] T019 Write `docs/adr/ADR-030-04-bitemporal-model.md` — eight typed clocks; `CURRENT`/`AS_OF(known-time)`/`INTERVAL(valid-time)` are three distinct dimensions (FR-020–023). Include the `U-03` finding from T037
- [ ] T020 [P] Write `docs/adr/ADR-030-05-search-fusion-default.md` — existing lexical path stays default; RRF is a comparison candidate built clean-room; vector is an optional profile because **no vector dependency exists** in any workspace member (FR-061)
- [ ] T021 [P] Write `docs/adr/ADR-030-06-canonical-matcher.md` — existing matcher canonical; Splink benchmark-only behind the same contract until the gate and span defects close (FR-110)
- [ ] T022 Write `docs/adr/ADR-030-07-operation-ownership.md` — fill from T011. Exactly one production owner per graph/TDA/temporal operation (FR-070, P9)
- [ ] T023 [P] Write `docs/adr/ADR-030-08-adaptive-layer-boundary.md` — only the deterministic core decides; adaptive components may reorder and are disableable. **No provider dependency exists in any workspace member** — record this (FR-044)
- [ ] T024 [P] Write `docs/adr/ADR-030-09-donor-licensing-deployment.md` — copyleft permitted via reviewed deployment; process separation is **not** a legal conclusion. Include the T012 giotto-tada disposition (FR-113)
- [ ] T025 Write `docs/adr/ADR-030-10-determinism-and-replay-modes.md` — `deterministic` vs `result_replay`; must preserve the `InvariantReducer.restore(stream, history=)` mitigation and `test_a_cold_fold_is_not_equivalent_to_a_restore` (FR-036, P10)
- [ ] T026 [P] Write `docs/adr/ADR-030-11-retention-and-erasure.md` — fill from T010 (FR-096)
- [ ] T027 [P] Write `docs/adr/ADR-030-12-observation-placement.md` — no guessed placement; `UNPLACED` is a durable visible state that does not count toward coverage (FR-062)

## 2.2 Contracts — implementation

Implementations of the eight contracts in `contracts/`.

- [ ] T028 [P] Implement `EvidenceSpanRef` typed union in `apps/shared/domain/evidence_span.py` — 8 selector variants plus mandatory `selector_semantics_version`; reject a bare integer. Contract 02
- [ ] T029 [P] Implement `OperatorResult` in `apps/shared/contracts/operator_result.py` — all fields per contract 01, both replay modes, `CapacityGap` alongside. Never allow empty output to carry a status
- [ ] T030 [P] Implement stage outcomes + failure classes in `apps/shared/contracts/stage_outcome.py` — 9 statuses, 17 error classes, retry semantics per contract 03
- [ ] T031 [P] Implement stable error codes in `apps/shared/contracts/error_codes.py` — three categories (expected-negative / retryable / defect); cross-tenant returns the same shape as genuinely-absent. Contract 07
- [ ] T032 Implement `ProjectionManifest` in `apps/shared/contracts/projection_manifest.py` — the eleven declarations; `rebuildable=true` requires a tested rebuild route. Contract 06
- [ ] T033 [P] Implement canonical serialization and digest helpers in `apps/shared/contracts/canonical.py` — stable key ordering, normalized timestamps/timezones, no uncontrolled `repr()`/memory-address stringification in identity-critical hashes (P10, FR-032)
- [ ] T034 Contract tests in `apps/shared/tests/contract/test_evidence_span.py` — every selector variant round-trips against a stored blob; mismatched `selector_semantics_version` **refuses** rather than converting. NOTE: package is named `contract`, so `--import-mode=importlib` is mandatory
- [ ] T035 [P] Contract tests in `apps/shared/tests/contract/test_operator_result.py` — the validation table from contract 01: digest present iff succeeded/partial, `error_code` present iff failed/blocked/quarantined, `deterministic=true` ⇒ `model_fingerprint=null`
- [ ] T036 [P] Contract tests in `apps/shared/tests/contract/test_stage_outcome.py` — `no_result` ≠ `unsupported`; `failed` ≠ succeeded-with-empty; `no_result` carries a coverage statement
- [ ] T037 [P] Verify and fix `recorded_at` flow from migration into ORM and query layer — Alembic migration at `apps/control-plane/db/migrations/versions/` (latest `015_worldline_reconstruction.py`), schema at `apps/control-plane/db/schema.py`. Resolves **[UNVERIFIED U-03]** from `research.md §8`. Blocks SC-008
- [ ] T038 [CONDITIONAL — only if T037 finds a gap] Add an Alembic migration `016_<timestamp>_<slug>.py` in `apps/control-plane/db/migrations/versions/` for any schema change from T028–T037 — forward-only, matching the existing 014/015 pattern; add the parity test at `apps/control-plane/tests/integration/test_orm_migration_parity.py`
- [ ] T039 Create `donors/registry.yaml` — **the file does not exist** (**[MEASURED]**). Reconcile the 11 existing catalogues in `docs/architecture/donors/00-INDEX.md`…`10-ZERO-LAYER.md` and the 40+ vendored checkouts under `donors/` into one machine-readable registry (FR-113, FR-115)
- [ ] T040 [P] Add a CI check that every declared dependency and vendored donor has a licence/version manifest entry in `donors/registry.yaml` — fail the build on a new dependency lacking one (FR-113)

**Checkpoint**: Contracts versioned, ADRs written, governance real. Stories may now begin.

---

# Phase 3: User Story 1 — The loop works the problem and explains its next move (P1) 🎯 MVP

**Goal**: An investigation reaches a terminal state for a recorded reason, persists a revision chain,
and its proposed next action changes when new evidence arrives.

**Independent test**: Start an investigation with one obligation; deliver one independently-sourced
observation; assert the obligation reaches a terminal state, the stop report names the reason, the
durable revision chain advanced, and the proposed next action changed with a recorded justification.
Runnable on a clean stack with **no donor component present**.

**Maps to**: SC-001, SC-002. Requirements: FR-036–FR-049, FR-060–FR-069.

### Tests — write first, watch them fail

- [ ] T041 [P] [US1] Test: empty question emits an obligation with trigger, acceptance criteria and required capability — never an "absent" state. `apps/control-plane/tests/integration/test_loop_closure.py`
- [ ] T042 [P] [US1] Test: source failure does **not** satisfy the obligation; status is `blocked` naming the missing capability. Same file
- [ ] T043 [P] [US1] Test: two sources disagree → both supports persist, contradiction opens, obligation stays open, no stop reason. `apps/control-plane/tests/integration/test_loop_closure.py`
- [ ] T044 [P] [US1] Test: terminal state carries a reason from the allowed table — not empty results, task count, exhausted retries or model confidence. `apps/control-plane/tests/integration/test_loop_closure.py`
- [ ] T045 [P] [US1] Test: repeated no-gain action is suppressed with a reason and explicit re-open conditions; a declared condition change lifts suppression. `apps/control-plane/tests/unit/test_action_memory.py`

### Implementation

- [ ] T046 [P] [US1] Extend `ResearchObligation` in `apps/control-plane/context_engine/obligations.py` with the full trigger block — kind, event id, rule id + version, exact reason, evidence refs. The five responsibilities already exist separately in `engine.py` (`ObligationGenerator:100`, `SatisfactionEvaluator:185`, `ActionProposer:264`, `DecisionRecorder:345`, `RevisionManager:407`) — **extend, do not re-create**
- [ ] T047 [P] [US1] Make unestimated priority components `null`, never `0.0` — `obligations.py` + `apps/control-plane/context_engine/engine.py:118` (`ObligationGenerator.generate`)
- [ ] T048 [US1] Implement the satisfaction evaluator against declared acceptance criteria only — `engine.py:191` (`SatisfactionEvaluator.evaluate`). A raw hit count must never satisfy. Returns verdict + reasons + evidence refs + evaluator version + explicit blockers
- [ ] T049 [US1] Implement action memory and suppression in `apps/control-plane/context_engine/obligations.py`, persisting via `ContextStore.remember()` at `apps/control-plane/context_engine/store.py:91`. Failure and no-result are **different** memory states
- [ ] T050 [US1] Wire `ContextEngine.reopen()` at `engine.py:746` and `termination_report()` at `engine.py:699` so every stop carries a reason plus residual unknowns and unexecuted scope
- [ ] T051 [US1] Emit obligation/action/decision changes through the existing outbox (`apps/control-plane/db/materialization_outbox.py`) rather than a new publication path
- [ ] T052 [US1] End-to-end test: a new observation advances the invariant revision **and** the context revision **and** changes the recommended next action. `apps/control-plane/tests/integration/test_observation_changes_next_action.py`

**Checkpoint**: SC-001 and SC-002 demonstrable on a clean stack. This is the MVP.

---

# Phase 4: User Story 2 — Every conclusion opens its source, byte for byte (P1)

**Goal**: Any accepted claim, relation or finding resolves to a content address and an exact span
in the stored raw bytes; incomplete chains are labelled, never presented as grounded.

**Independent test**: A document with a table and a paginated document; a finding derived from a
table cell resolves to that cell's byte range, and a coordinate-bearing document keeps page and box.

**Maps to**: SC-004, SC-005. Requirements: FR-001–FR-007.

**⚠️ The known defect**: `Segment.offset` means byte offset in one parser, segment index in another,
and is always `0` in a third — all three summed into one field at
`apps/interpretation/…/extractors/lane.py:82-86`. `document_adapter.py:271-300` consumes the span
to mint `mention_id` then discards it. `ResolutionMention` has no span field. **This phase fixes the
producer.**

### Tests

- [ ] T053 [P] [US2] Test: every accepted claim's lineage resolves to a content address + span matching the stored bytes. `apps/interpretation/tests/contract/test_span_lineage.py`
- [ ] T054 [P] [US2] Test: two producers with different `selector_semantics_version` are refused, not conflated. Same file
- [ ] T055 [P] [US2] Test: raw blob digest unchanged after parser upgrade, reprocessing, rollback and donor disable. `apps/interpretation/tests/contract/test_raw_immutability.py`
- [ ] T056 [P] [US2] Test: a parser rerun at a new version creates a **new** derived revision and leaves the prior interpretation retrievable. `apps/interpretation/tests/contract/test_reparse_supersession.py`
- [ ] T057 [P] [US2] Test: a finding with an unresolvable chain renders as partial/unsupported, never grounded. `apps/interpretation/tests/contract/test_ungrounded_rendering.py`

### Implementation

- [ ] T058 [US2] Replace the conflated positional field in `apps/interpretation/extractors/lane.py:82-86` with the `EvidenceSpanRef` union from T028. **This is the defect fix** — every downstream span is wrong until it lands
- [ ] T059 [US2] Stop discarding the span in `apps/interpretation/document_adapter.py:271-300` — persist it on the mention
- [ ] T060 [P] [US2] Add a span field to `ResolutionMention` in `apps/admission/resolution/` so identity candidates show their evidence
- [ ] T061 [P] [US2] Update every parser under `apps/interpretation/parsers/registry.py` to emit typed spans with `selector_semantics_version`
- [ ] T062 [P] [US2] Enforce immutability of raw objects at the storage layer in `apps/shared/storage/` — an attempted write raises `IMMUTABLE_VIOLATION` (release blocker, contract 07)
- [ ] T063 [US2] Add `DerivedArtifact` persistence in `apps/shared/domain/` carrying operator manifest, input digest set, output digest, method/parameter/model fingerprints (FR-007)

**Checkpoint**: SC-004 and SC-005 demonstrable. **US4 is unblocked** — it depends on this phase.

---

# Phase 4.5: Projections That Are Real (WP7) — added by analyze A2

> **Why this phase exists**: `/speckit.analyze` found `plan.md` gating on "WP7 — Projections that are
> real" with **no corresponding phase**. Only T032 (manifest schema) and T120 (staleness UI) touched
> projections; FR-072…FR-079 had zero owning tasks. `plan.md` places this **after the operator
> envelope and before open-world**, because a projection that cannot be reproduced is not a
> projection.

**Goal**: Every projection family declares its 11 properties, rebuilds to the same digest, and never
destroys evidence on failure.

**Independent test**: Kill each projection mid-build → source evidence intact, manifest reports
`failed` with a reason, and rebuild reproduces the recorded `output_digest`.

**Maps to**: FR-070, FR-071, FR-072, FR-073, FR-074, FR-075, FR-076, FR-077, FR-078, FR-079.

### Tests

- [ ] T146 [P] [US3] Test: every registered projection carries all eleven declarations. `apps/projection/tests/contract/test_projection_declarations.py` (FR-070)
- [ ] T147 [P] [US3] Test: a rebuild reproduces the manifest's recorded `output_digest` on fixtures, for graph, search, temporal, TDA and spatial. `apps/projection/tests/integration/test_projection_rebuild.py` (FR-071, SC-006)
- [ ] T148 [P] [US3] Test: a failed or crashed projection deletes no evidence and mutates no canonical claim. `apps/projection/tests/integration/test_projection_rebuild.py` (FR-079)
- [ ] T149 [P] [US3] Test: `rebuildable = true` is refused when no tested rebuild route exists. Same file (FR-071)
- [ ] T150 [P] [US3] Test: graph traversal enforces depth/fan-out/scope/time/tenant/budget and returns truncation metadata plus the derivation path. `apps/projection/tests/contract/test_graph_traversal_bounds.py` (FR-074)
- [ ] T151 [P] [US3] Test: an n-ary co-occurrence fact is never silently expanded to clique edges. `apps/projection/tests/unit/test_nary_preservation.py` (FR-073)
- [ ] T152 [P] [US3] Test: a derived edge carries rule id, derivation path, premise refs and interval semantics. `apps/projection/tests/unit/test_derived_edge_lineage.py` (FR-072)
- [ ] T153 [P] [US3] Test: TDA fixtures — edgeless graph, isolated vertices, mixed scales, duplicate edges — produce declared, stable results; incompatible scales are refused or stratified. `apps/projection/tests/unit/test_tda_declared_inputs.py` (FR-076)
- [ ] T154 [P] [US3] Test: an H3 cell never implies precision finer than the source geometry. `apps/projection/tests/unit/test_spatial_precision.py` (FR-077)
- [ ] T155 [P] [US3] Test: source-health metrics stay separate from world-anomaly candidates. `apps/projection/tests/unit/test_source_health_separation.py` (FR-078)
- [ ] T156 [P] [US3] Test: deleting a search index document loses no evidence it pointed to. `apps/projection/tests/contract/test_search_evidence_retention.py` (FR-075)

### Implementation

- [ ] T157 [US3] Declare the eleven properties per family and wire them into the manifest schema from T032 in `apps/projection/` — graph, search, temporal, analytics, TDA, spatial (FR-070)
- [ ] T158 [US3] Apply the T011 ownership decision — remove or mark every duplicate/inert execution path in `apps/projection/tda/`, `apps/science/scitda/` and `GraphInvariant.to_tda_input`, naming exactly one production owner per operation (ADR-030-07)
- [ ] T159 [P] [US3] Persist TDA feature series with snapshot digest, window, filtration definition, scale units, code fingerprint and evidence lineage in `apps/projection/tda/` — a feature that is computed but never written or consumed is not live (FR-076)
- [ ] T160 [P] [US3] Implement bounded graph traversal with path provenance and truncation metadata in `apps/projection/graph/`, keeping vendor graph clients out of domain logic (FR-074)
- [ ] T161 [P] [US3] Expose index revision, searched fields, filters, staleness and candidate-pool truncation in the search response path under `apps/projection/search/` (FR-075)
- [ ] T162 [P] [US3] Enforce the FR-083 admission checklist in `apps/admission/resolution/` — span reachability, shape, policy, dependency, method version, review threshold (analyze A8)
- [ ] T163 [P] [US3] Add a kill switch and a staleness indicator per projection under `apps/projection/`; a stale projection may satisfy a freshness-requiring obligation only through an explicit profile (FR-079)

**Checkpoint**: SC-006 demonstrable for every projection family. Gate G6 satisfied.

---

# Phase 5: User Story 3 — The platform does not lie about ignorance (P1)

**Goal**: Thirteen epistemic states stay distinct through storage, events, API and UI. Universal
queries degrade honestly when detection power is unknown.

**Independent test**: The epistemic fixture corpus — unreachable source, zero-result from a source
with declared and with undeclared detection power, two sources disagreeing, an unknown predicate —
resolves to four distinct, non-collapsed outcomes.

**Maps to**: SC-003. Requirements: FR-010–FR-017.

### Tests

- [ ] T064 [P] [US3] Build the epistemic fixture corpus in `bench/fixtures/global_upgrade/epistemic/`: positive-only, negative-only, both, unknown, unsupported source, failed source, searched-no-result with known detection power, searched-no-result with unknown detection power. Each states ground truth, expected output, prohibited false inference, applicable measurement and source licence
- [ ] T065 [P] [US3] Test: all 13 states round-trip through storage → events → API → UI without collapse. `apps/control-plane/tests/integration/test_epistemic_roundtrip.py`
- [ ] T066 [P] [US3] Test: zero-result with unknown detection power ⇒ `SEARCHED_NO_RESULT / INFORMATIONAL_ONLY`, never `QUALIFIED_ABSENCE`. Same file
- [ ] T067 [P] [US3] Test: unknown relation predicate survives storage, projection and API with raw label and span intact. `apps/shared/tests/unit/test_open_world_predicates.py`
- [ ] T068 [P] [US3] Test: four-valued support truth table — `TRUE_ONLY` and `FALSE_ONLY` are incomparable; confidence is a separate field. `apps/science/context/tests/test_epistemic_algebra.py`
- [ ] T069 [P] [US3] Test: contradiction survives to the API and is never resolved by recency, document majority or a single high score. `apps/science/context/tests/test_epistemic_algebra.py`

### Implementation

- [ ] T070 [US3] Consolidate the 13 research states into structured dimensions in `apps/science/context/epistemic.py` — a single enum that loses information is not acceptable (FR-010)
- [ ] T071 [US3] Add `detection_power` to `SourceDefinition` in `apps/shared/domain/` — declared or unknown; unknown ⇒ absence claims are informational only (FR-014)
- [ ] T072 [US3] Make `predicate_raw` non-nullable in the relation candidate model in `apps/shared/domain/` — unknown predicate produces a typed unknown candidate, never a silent drop (FR-013)
- [ ] T073 [US3] Enforce universal-quantification degradation in `apps/science/context/completeness.py` and `apps/science/context/coverage.py` — without declared preconditions, degrade to "candidates observed within the stated coverage" with enumerated limitations (FR-014)
- [ ] T074 [US3] Separate the fourteen score components in `apps/science/context/` — relevance, source reliability, claim support, identity match, novelty, independence, centrality, freshness, uncertainty, action utility must stay distinct, with any composite carrying a policy version (FR-016, P5)
- [ ] T075 [US3] Enforce that a bare `[]` is never returned from an API or source adapter — response carries status + coverage + provenance + limitations. `apps/control-plane/api/routes/` per contract 07 R4

**Checkpoint**: SC-003 demonstrable.

---

# Phase 6: User Story 4 — Identity is decided, never scored (P2)

**Goal**: No similarity probability, centrality, graph adjacency, topological feature or model output
commits a merge alone; decisions are append-only and reversible through explicit supersession.

**Independent test**: A labelled pair corpus with transliteration variants, shared addresses, name
changes, missing fields and true negatives. Assert measured false-merge / false-non-match rates and
that a score alone cannot commit a merge.

**Maps to**: SC-009. Requirements: FR-080–FR-084.
**Depends on**: US2 (T060) — identity candidates need spans to be reviewable.

### Tests

- [ ] T076 [P] [US4] Build the labelled pair corpus in `bench/fixtures/global_upgrade/identity/`: transliteration variants, same-name/different-person, company alias and name change, shared address, old/new identifiers, conflicting dates, incomplete fields. Include explicit **ambiguous** pairs. `DON-ER-001` from the source specification
- [ ] T077 [P] [US4] Test: a high-score pair with no admission decision commits **zero** merges. `apps/admission/tests/contract/test_no_auto_merge.py`
- [ ] T078 [P] [US4] Test: A↔B and B↔C match with inconsistent A↔C evidence does **not** imply A = C. `apps/admission/tests/unit/test_cluster_transitivity.py`
- [ ] T079 [P] [US4] Test: a split supersedes the merge without deleting it, and claims stay traceable to the identity interpretation they were written under. `apps/admission/tests/contract/test_resolution_history.py`
- [ ] T080 [P] [US4] Test: corroboration counts lineage roots, not hostnames, and the measure is named on every decision. `apps/admission/tests/contract/test_resolution_history.py` — guards the WP-E behaviour already delivered in 029

### Implementation

- [ ] T081 [US4] Harden the admission gate in `apps/admission/resolution/` so a matcher whose own profile declares itself uncalibrated cannot commit a merge
- [ ] T082 [P] [US4] Make `ResolutionDecision` append-only with supersession in `apps/admission/resolution/` — merge/split never rewrite (FR-082)
- [ ] T083 [P] [US4] Preserve competing identity hypotheses and the decision trail in `apps/admission/resolution/decision_store.py`
- [ ] T084 [US4] Record the baseline matcher measurement in `benchmarks/er-baseline.md`: pair recall, candidate-pair reduction, false-merge rate, false-non-match rate, calibration — for the current matcher at `apps/zero/zero/resolution/fellegi_sunter.py`. **No numbers before this exists**

**Checkpoint**: SC-009 demonstrable. US6 becomes unblocked for Splink benchmark-only work.

---

# Phase 7: User Story 5 — More independent knowledge per unit cost (P2)

**Goal**: A fixed budget yields more unique, independent, verifiable evidence; unproductive repeats
are suppressed; sources that could not be reached are reported.

**Independent test**: Fixed query set and budget, two configurations; compare unique novel evidence,
independent-source groups obtained, duplicate rate and total cost, with a ranking explanation
available for each selected action.

**Maps to**: SC-011, SC-012, SC-013. Requirements: FR-042, FR-043, FR-045, FR-061, FR-067, FR-068.

### Tests

- [ ] T085 [P] [US5] Build the judged retrieval query set in `bench/fixtures/global_upgrade/retrieval/`: exact identifier, lexical, multilingual/transliteration, paraphrased, multi-hop relational, temporal, spatial, hard negative, near duplicate. Ground truth plus prohibited false inference per case. `DON-RET-002`
- [ ] T086 [P] [US5] Test: hard filters run before ranking; an excluded candidate records its exclusion reason. `apps/control-plane/tests/unit/test_action_ranking.py`
- [ ] T087 [P] [US5] Test: high expected gain cannot outweigh a policy, budget, capability or approval violation. `apps/control-plane/tests/unit/test_action_ranking.py`
- [ ] T088 [P] [US5] Test: a syndication cluster yields effective independence that does not scale with copy count. `apps/admission/tests/integration/test_evidence_independence.py`
- [ ] T089 [P] [US5] Test: downstream backlog growth reduces the acquisition dispatch rate. `apps/acquisition/tests/integration/test_backpressure.py` — extends the existing file rather than replacing it
- [ ] T090 [P] [US5] Test: retries distinguish transient failure / unsupported / denied / throttled / parse failure / no-result / valid empty. `apps/shared/tests/unit/test_retry_classification.py`

### Implementation

- [ ] T091 [US5] Implement the 14-component action utility vector with hard filters first in `apps/control-plane/context_engine/engine.py:270` (`ActionProposer.propose`). Retain the raw vector; any composite carries a policy version (FR-042, P5)
- [ ] T092 [P] [US5] Label `probability_of_success` with its semantics — an uncalibrated heuristic is `uncalibrated_score`, never a bare `0.73`. Same file
- [ ] T093 [US5] Build the retrieval benchmark harness in `bench/bench/` — Recall@k, Precision@k, MRR/nDCG, unique novel evidence, independent-source yield, novelty, duplicate rate, p50/p95 latency, cost per useful observation, **stratified by query class**
- [ ] T094 [US5] Measure the current BM25 path at `apps/projection/search/` first. **Do not change retrieval before this number exists**
- [ ] T095 [US5] Implement RRF as a **clean-room** comparison candidate in `apps/shared/scoring/fusion/` — labelled `clean-room-inspired`, **not** donor code, because `ranknexus` and `fuse` were verified as non-existent projects in `donor-matrix.md §1`
- [ ] T096 [US5] Implement duplicate/freshness suppression at candidate generation in `apps/projection/search/` and `apps/acquisition/discovery/`
- [ ] T097 [US5] Write the same-envelope comparison into `benchmarks/retrieval-comparison.md` — identical query set, budget and source universe. **The decision is recorded either way**, including "current path retained"

**Checkpoint**: SC-011/012/013 demonstrable with a recorded decision.

---

# Phase 8: User Story 6 — Third-party capability is integrated, not listed (P2)

**Goal**: An external capability runs behind a contract, preserves provenance, cannot write canonical
state, reports failure honestly, and is benchmarked on our data before promotion.

**Independent test**: Baseline vs integrated capability on the same corpus, labels and compute
envelope; compare measured quality and total cost; verify the rollback switch exists and that
disabling deletes nothing.

**Maps to**: SC-014. Requirements: FR-007, FR-110–FR-115.

**⚠️ Ordering constraint**: `donor-matrix.md §6` marks Docling, GROBID, Splink, Redpanda Connect,
H3, DuckDB Spatial, OpenAleph and Browsertrix **DEFERRED — after contracts hold**, verbatim: "None
should receive data while the gate and identity defects stand." This phase runs **after** US1–US5.

### Tests

- [ ] T098 [P] [US6] Test: a donor integrated behind the contract writes no canonical store, and `substitution_attempted` stays false when a capability is missing. `apps/shared/tests/contract/test_capacity_gap.py` (CE-I13)
- [ ] T099 [P] [US6] Test: a donor adapter cannot write canonical evidence, identity, investigation state or projection stores. `apps/shared/tests/contract/test_donor_write_boundary.py`
- [ ] T100 [P] [US6] Test: disabling an integrated donor resumes the previous path and deletes no evidence, candidate or derived artifact. `apps/shared/tests/integration/test_donor_kill_switch.py`
- [ ] T101 [P] [US6] Test: an integrated capability's output identifies inputs, operator version, method fingerprint and exact spans — or is labelled partial. `apps/shared/tests/contract/test_donor_provenance.py`
- [ ] T102 [P] [US6] Test: empty / timeout / unsupported from a donor are recorded as three distinct statuses. `apps/shared/tests/contract/test_donor_failure_modes.py`
- [ ] T103 [P] [US6] Test: an unverified donor is refused at the registry. `apps/shared/tests/contract/test_donor_failure_modes.py` — FR-114

### Implementation

- [ ] T104 [US6] Implement the operator registry in `apps/shared/` — capability, cost model, resource limits, isolation class, egress, credential scope, licence metadata, kill switch. A missing capability returns `CapacityGap`, never a weaker substitute (CE-I13)
- [ ] T105 [P] [US6] Build the frozen labelled ER corpus consumption for Splink **benchmark-only**, behind the same `ResolutionCandidate` contract, in `apps/admission/resolution/` — no second identity writer (ADR-030-06)
- [ ] T106 [P] [US6] Harden the existing Browsertrix adapter at `apps/acquisition/adapters/browsertrix/collect.py` — archive to immutable object storage, byte/decompression/depth limits, explicit empty-crawl status, cleanup, partial/truncated marking. **Do not build a second crawler.** Record the AGPL-3.0-or-later deployment decision in `donor-matrix.md`
- [ ] T107 [P] [US6] Evaluate a document-structure donor behind the parser operator contract — pinned revision, per-model licence recorded (Docling code is MIT but model licences vary; one model repo returned HTTP 401 in the 029 verification), typed segments with page/coordinates, warnings and partial status. in `apps/interpretation/parsers/` - **benchmark against the current pipeline before promotion**
- [ ] T108 [US6] Produce the supply-chain record in `benchmarks/sbom-donors.md` — code licence, dependency licences, model weights, datasets, training data, bundled binaries, documentation and sample assets **inventoried separately**
- [ ] T109 [US6] Record the accept/reject decision per donor in `donor-matrix.md` with the measured comparison. A rejected donor is a **completed** task when the decision is recorded and no code is merged

**Checkpoint**: SC-014 demonstrable.

---

# Phase 9: User Story 7 — The analyst and the platform agree on current state (P3)

**Goal**: One navigable view of question, known/unknown/blocked states, competing hypotheses,
proposed/deferred/suppressed/blocked actions, findings with evidence chains, timeline, projection
freshness, budget and the reason the investigation continues or stops.

**Independent test**: A scenario where an observation changes the recommended action; the analyst sees
before/after with the cause, and their recorded approval or refusal is visible without altering the
original evidence.

**Maps to**: SC-017. Requirements: FR-048, FR-049, FR-100–FR-103.

### Tests

- [ ] T110 [P] [US7] Test: unknown / no-result / unsupported / unavailable / blocked render as **distinct** states in the API response and console. `apps/control-plane/tests/contract/test_api_state_distinction.py`
- [ ] T111 [P] [US7] Test: no fabricated metric is emitted; an unavailable measurement is `null` with the missing instrumentation named. `apps/control-plane/tests/unit/test_no_fabricated_metrics.py`
- [ ] T112 [P] [US7] Test: analyst approve/reject/defer is stored with actor, time, rationale and the revision it applied to; rejection does not delete the candidate. `apps/control-plane/tests/integration/test_analyst_feedback.py`
- [ ] T113 [P] [US7] Test: concurrent writes with a stale `expected_revision` are rejected for re-evaluation, never last-write-wins. `apps/control-plane/tests/integration/test_concurrency_cas.py`
- [ ] T114 [P] [US7] Test: cross-tenant access returns the same response shape as a genuinely absent object. `apps/control-plane/tests/integration/test_tenancy.py` — extends the existing file

### Implementation

- [ ] T115 [P] [US7] Expose revision, obligation, hypothesis, contradiction and action state endpoints in `apps/control-plane/api/routes/` — every response carries status, warnings, limitations and trace ids; no fabricated number
- [ ] T116 [P] [US7] Expose finding lineage to exact source fragment in `apps/control-plane/api/routes/` — `Finding → claim → derived artifact → observation → span → blob`, with partial rendering when a hop fails
- [ ] T117 [US7] Build the revision navigator and evidence inspector in `apps/webapp/` — before/after values, source events, rule/operator version, supersession, stop reason
- [ ] T118 [US7] Implement `AnalystFeedback` semantics in `apps/feedback/` — support / refute / uncertain / irrelevant / duplicate / identity-merge / identity-split / withdraw / approve-action / reject-action, each immutable with actor, time, target revision and rationale
- [ ] T119 [P] [US7] Add decision-history and audit endpoints in `apps/control-plane/api/routes/` — the rationale for every state change is queryable
- [ ] T120 [P] [US7] Add projection staleness/degradation surfaces in `apps/control-plane/api/routes/` — a stale projection never silently satisfies a freshness-requiring obligation

**Checkpoint**: SC-017 demonstrable.

---

# Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Concerns that span every story.

- [ ] T121 [P] Wire end-to-end tracing across `action → task → capture → observation → operator → invariant revision → context revision → finding` in `apps/shared/observability/` — opaque ids and fingerprints, **never raw sensitive text**
- [ ] T122 [P] Enforce per-tenant budget and policy in `apps/shared/` — remove any default that lets all tenants share one policy or budget id (FR-034)
- [ ] T123 [P] Implement egress and scope-limit enforcement — private/loopback/link-local/metadata blocking, DNS validation before and after redirect, DNS-rebinding handling, archive/file limits, in `apps/shared/isolation.py` and `apps/acquisition/` (FR-092, FR-093)
- [ ] T124 [P] Security tests in `apps/shared/tests/security/`: SSRF, redirect to private IP, DNS rebinding, archive bomb, malicious-HTML prompt injection, path traversal, cross-tenant request, secret redaction
- [ ] T164 [P] Enforce the backend approval gate in `apps/control-plane/api/routes/` — a proposed action marked `approval_required` MUST NOT execute until the decision is recorded, regardless of client state. Test that a client claiming approval without a `DecisionRecord` is refused (FR-095, analyze A5)
- [ ] T165 [P] Assert no acquisition path circumvents auth, CAPTCHA, paywall or other access controls — a negative capability test over `apps/acquisition/adapters/` and `apps/acquisition/registry.py` asserting that no registered adapter holds bypass privileges (FR-094, analyze A5)
- [ ] T166 [P] Enforce tenant scope on every durable read/write/cache key/replay key at the repository layer in `apps/shared/` and `apps/control-plane/api/routes/`, plus a cross-tenant cache-key test proving no key collision across tenants (FR-090, FR-093)
- [ ] T167 [P] Prove no fabricated metric reaches an interface in `apps/control-plane/api/routes/` and `apps/webapp/` — an unavailable measurement serialises as `null` with the missing instrumentation named. Extends T111 (FR-100, FR-101, SC-015, analyze A3)
- [ ] T125 [P] Verify DLQ/quarantine replay preserves idempotency — extends `apps/shared/events/dlq.py`, `dlq_durable.py` and `apps/control-plane/api/routes/quarantine.py` (FR-069)
- [ ] T126 Migration, backfill, dry-run and rollback tooling in `apps/control-plane/db/` — batched, checkpointed, idempotent restart (spec §20.1)
- [ ] T127 [P] Reconcile `deploy/specops/lab/docker-compose.yml` and `.env.example` — ports, endpoints, credentials, readiness checks must agree with what the code actually reads. **[MEASURED]** `neo4j` is declared with no configuration variable; resolve here
- [ ] T128 Run every validation scenario V-1…V-10 from `quickstart.md §7` and record results in `benchmarks/validation-results.md` — each classified PASS / FAIL / BLOCKED / NOT-RUN
- [ ] T129 [P] Update `specs/030-global-platform-upgrade/` documents — set every task status to its evidence-backed value; update `current-state-audit.md` with the final capability matrix
- [ ] T130 Write the final engineering report in `specs/030-global-platform-upgrade/final-report.md` — starting/ending commits, changed modules, migrations, ADRs, donor inventory, transplanted files with notices, test matrix with exact commands and exit statuses, benchmark tables, migration/rollback steps, known gaps with reproduction, and **an explicit statement of which goals are proven end-to-end and which remain unverified**

---

## Dependencies & Execution Order

### Analyze remediation (applied 2026-10-14)

/speckit.analyze reported 3 CRITICAL + 2 HIGH findings on the first generated list. All are fixed:

| Finding | Fix | New tasks |
|---|---|---|
| **A1** CRITICAL — plan.md gates on WP3 (invariant/worldline) with no phase | Phase 2.5 added | T131–T145 |
| **A2** CRITICAL — plan.md gates on WP7 (projections) with no phase | Phase 4.5 added | T146–T163 |
| **A3** **WITHDRAWN — was wrong.** SC-006/SC-007 are covered by `test_invariant_reducer.py` and `test_digest_gated_revision.py`. | none |
| **A4** **CORRECTED.** Bitemporality exists: `EntityFact` in `db/schema.py:2768`, migration `023_derivation_enforcement.py`, read by `dossier_store.py`; `TemporalMode` in `science/context/query_ast.py` with 125 passing contract tests. **U-03 resolved: `recorded_at` does flow past migration into ORM and the query layer.** The real gap is a cross-layer E2E, not the model. | none |
| **A5** HIGH — FR-094/FR-095 unenforced | added to Phase 10 | T164, T165, T166 |
| **A7** MEDIUM — FR-066 science anchoring | real gap, kept | T139 |
| **A8** MEDIUM — FR-083 admission checklist | folded into Phase 4.5 | T162 |
| **A3b** MEDIUM — SC-015 no fake metrics | added to Phase 10 | T167 |

**Task IDs are deliberately non-contiguous.** T131–T167 were appended rather than renumbered so the
citations in the analysis report — T025, T032, T058, T059, T060, T089, T099, T120 — stay valid, and
so references from specs/029 remain resolvable. Insert by phase position, not by ID order.

### Phase Dependencies

- **Phase 1 (Setup/WP0)**: no dependencies — start immediately
- **Phase 2 (Foundational/WP1+WP2)**: depends on Phase 1 — **BLOCKS all user stories**
- **Phase 3–9 (US1–US7)**: depend on Phase 2
- **Phase 10 (Polish)**: depends on the stories being targeted

### User Story Dependencies

| Story | Priority | Depends on | Notes |
|---|---|---|---|
| **US1** Loop works the problem | P1 | Foundational | **MVP.** Runnable with zero donors |
| **US2** Conclusion opens its source | P1 | Foundational | Fixes the span defect that US4 needs |
| **US3** No lying about ignorance | P1 | Foundational | Independent of US1/US2 |
| **US4** Identity by decision | P2 | Foundational + **US2** (T060) | Candidates need spans to be reviewable |
| **US5** More knowledge per cost | P2 | Foundational | Independent |
| **US6** Donor integration | P2 | Foundational + **US1–US5** | `donor-matrix.md §6` defers all donors until contracts hold |
| **US7** Analyst agreement | P3 | Foundational | Best after US1 so the UI has a real loop to show |

### Within Each User Story

Tests first and **watch them fail** → models → services → endpoints → integration.

### Parallel Opportunities

- T002–T005 (baseline runs), T006–T014 (audit) — all `[P]`
- T016–T018, T020–T021, T023–T024, T026–T027 (ADRs) — all `[P]`
- T028–T036 (contract implementations and their tests) — all `[P]`
- Within each story, all `[P]` tests and all `[P]` models run together
- Different stories run in parallel once Phase 2 completes — **except** US4→US2 and US6→US1–US5

---

## Parallel Example: User Story 2

```text
Task: "Test: every accepted claim's lineage resolves to a content address + span matching the stored bytes"
Task: "Test: two producers with different selector_semantics_version are refused, not conflated"
Task: "Test: raw blob digest unchanged after parser upgrade, reprocessing, rollback and donor disable"
Task: "Test: a parser rerun at a new version creates a new derived revision"
Task: "Test: a finding with an unresolvable chain renders as partial/unsupported"

Task: "Add a span field to ResolutionMention in apps/admission/resolution/"
Task: "Enforce immutability of raw objects at the storage layer in apps/shared/storage/"
Task: "Add DerivedArtifact persistence in apps/shared/domain/"
```

Then sequentially: **T058** (the `lane.py:82-86` producer fix) and **T059** (stop discarding the span
in `document_adapter.py`) — everything downstream depends on those two.

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup — baseline + audit
2. Phase 2 Foundational — ADRs + contracts
3. Phase 3 User Story 1 — the loop
4. **STOP and VALIDATE** V-1…V-4 from `quickstart.md`
5. **MVP**: COGNITIVE investigates, records evidence, reaches a stated conclusion, and explains its
   next move — with byte-level provenance and honest ignorance, and with **no donor component present**

### Incremental Delivery

1. Setup + Foundational → foundation real
2. US1 → validate → **MVP**
3. US2 → provenance reaches bytes
4. US3 → ignorance becomes honest
5. US4 → identity becomes a decision
6. US5 → cost becomes measurable
7. US6 → third-party capability proves itself
8. US7 → the analyst sees all of it

Each step is independently shippable and independently testable.

### What is explicitly **not** scheduled, and why

| Not scheduled | Reason |
|---|---|
| LLM routing / evaluation vertical | **[MEASURED]** no provider dependency exists in any workspace member. Scheduled as an operator-evals contract once one does |
| Vector/ANN retrieval arm | **[MEASURED]** no vector dependency exists. Adding one before a baseline violates FR-110. `ADR-030-05` makes it an optional profile |
| ranknexus, fuse, QUANTA, IntelShed, OptLLM, lcc, nax, Stablerank, worker-browser | **Verified non-existent** in `donor-matrix.md §1`. T095 builds RRF clean-room and labels it honestly |
| giotto-tda as a new adoption | Already installed and **AGPL-3.0** — T012 produces a disposition, not an adoption |

---

## Notes

- `[P]` = different files, no dependency on an incomplete task
- `[Story]` maps a task to its user story for traceability
- Verify tests **fail** before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate independently
- **A task is `[x]` only with evidence** — a `file:line` reference or a recorded command with exit
  status. Code having been written is not evidence
- `[!]` requires a concrete blocker, an owner and an executable next action
- Do not update the constitution, ADR or spec status without owner authorisation and evidence (spec §25.1)
- Avoid: vague tasks, same-file conflicts, cross-story dependencies that break independence