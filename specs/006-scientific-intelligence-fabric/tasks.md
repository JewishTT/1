# Tasks: Scientific Intelligence Fabric

**Input**: Design documents from `/specs/006-scientific-intelligence-fabric/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Test tasks are included because the feature specification explicitly demands
verifiable scientific rigor (calibration, null models, robustness, reproduction) and the
repos baseline suites are verified via pytest/vitest. Tests are written FIRST and fail
before implementation (Execution Principle below).

**Organization**: Tasks are grouped by user story so each story can be implemented and
tested independently. Task IDs continue the platform's global task track (T080–T143)
per the user's Phase 7 plan.

> **Numbering note**: `specs/001-global-osint-platform/tasks.md` independently uses
> T080–T087 for earlier tracks; this file is the `006` feature's own registry and continues
> the user's Phase 7 numbering (T080–T143). IDs are scoped per feature directory; the
> `[USn]` labels below map to this spec's user stories.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US7)
- Include exact file paths in descriptions

## Path Conventions

- Python: `apps/science/...` (workspace member added in T080)
- Events: `apps/shared/events/topics.py`
- API: `apps/control-plane/api/...`
- Webapp: `apps/webapp/src/...`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [ ] T080 Add `apps/science` to `[tool.uv.workspace] members` in `pyproject.toml` and create `apps/science/pyproject.toml` (name `cognitive-science`, deps `cognitive-shared`, `numpy>=1.26`, `scipy>=1.13`; dev `pytest`, `pytest-asyncio`, `ruff`; pytest markers `contract|integration|unit`; uv source `cognitive-shared = { workspace = true }`)
- [ ] T081 [P] Create package layout `apps/science/{claims,hypotheses,causal,temporal,structure,robustness,experiments,review,api,../_events.py,../errors.py,../store.py}/__init__.py`
- [ ] T082 [P] Register `science.*` topics in `apps/shared/events/topics.py` `EVENT_CATALOG` (full list in research §9; refs-only payloads)
- [ ] T083 [P] Add `apps/science` to ruff lint paths; add a `.ruff.toml` or per-app `[tool.ruff]` in `apps/science/pyproject.toml` matching root (`line-length=100`, select `["E","F","I","B","UP"]`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure MUST be complete before any user story can be implemented.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T084 Implement core value types `CredenceDistribution`, claim/hypothesis status enums, and `Knowledge artifacts` in `apps/science/claims/model.py` (fields per data-model §1–§7)
- [ ] T085 Implement error primitives in `apps/science/errors.py` (`ProvenanceRequiredError`, `UnknownModelError`, `DecisionRequiredError`, `ScopeBoundaryError`)
- [ ] T086 Implement the shared scope guard `ensure_scoped(outcome_attribute)` in `apps/science/causal/scope.py` (hard-excluded person-level classes; emits audit event; policy ref `contracts/scope-boundary.md`)
- [ ] T087 Implement evidence-chain validation in `apps/science/claims/provenance.py` (EvidenceLink → Observation → Raw(sha256) resolution, FR-001)
- [ ] T088 Implement an in-memory, event-replayable state store in `apps/science/store.py` (upsert by deterministic id; rebuild from `science.*` envelopes, Constitution I-12)
- [ ] T089 [P] Implement `envelope()` emitter helper wrapping `events.kafka.build_envelope` in `apps/science/_events.py` (topic_for + EVENT_CATALOG lookup, refs-only payloads)
- [ ] T090 [P] Implement run-context builder (seed, pipeline_version, dependency_freeze) in `apps/science/experiments/context.py`

**Checkpoint**: Foundation ready — user story implementation can now begin in parallel.

---

## Phase 3: User Story 1 - Probabilistic Claims & Calibration (Priority: P1) 🎯 MVP

**Goal**: Register reproducible, fully-provenanced, calibrated probabilistic claims; no fabricated probabilities.

**Independent Test**: `register_claim` with full provenance succeeds and emits an envelope; empty provenance raises; unknown method raises; calibration harness labels a synthetic overconfident model `OVERCONFIDENT`.

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T091 [P] [US1] Contract test for claim registration + calibration per `contracts/interface-contracts.md` §1–2 in `apps/science/tests/contract/test_claim_contract.py`
- [ ] T092 [P] [US1] Unit test: overconfident synthetic model yields `OVERCONFIDENT` verdict in `apps/science/tests/unit/test_calibration.py`

### Implementation for User Story 1

- [ ] T093 [US1] Implement `register_claim()` (provenance gate + `ensure_scoped` gate + `UnknownModelError`) in `apps/science/claims/registry.py`
- [ ] T094 [US1] Implement calibration harness (decile buckets, Brier, ECE m=10, verdict) in `apps/science/claims/calibration.py`
- [ ] T095 [US1] Implement claim status transitions (append-only events, Supersedes semantics in store) in `apps/science/claims/status.py`
- [ ] T096 [US1] Implement claim query/list by project in `apps/science/claims/query.py`
- [ ] T097 [US1] Add routes `POST/GET /api/science/claims`, `POST /api/science/calibration`, `GET /api/science/calibration/{model_id}` in `apps/control-plane/api/routes/science_claims.py` (422 scope_refused semantics)
- [ ] T098 [US1] Mount the science router in `apps/control-plane/api/main.py` (and add `science_claims` route file to app package)

**Checkpoint**: US1 fully functional and testable independently — MVP slice delivers claims + calibration + provenance.

---

## Phase 4: User Story 2 - Hypotheses & Information Gain (Priority: P1)

**Goal**: Competing hypotheses with lifecycle, direction-tagged evidence, information-gain planning, coverage.

**Independent Test**: Two competing hypotheses stay alive; evidence attaches with direction and updates credence via claims layer; planner ranks by expected KL gain over alive hypotheses only; discard without decision rejected; coverage computed.

### Tests for User Story 2 ⚠️

- [ ] T099 [P] [US2] Contract test for hypothesis lifecycle + planner per `contracts/interface-contracts.md` §3–4 in `apps/science/tests/contract/test_hypothesis_contract.py`
- [ ] T100 [P] [US2] Unit test: two competing hypotheses, gain planner excludes dead hypotheses in `apps/science/tests/unit/test_gain.py`

### Implementation for User Story 2

- [ ] T101 [US2] Implement `Hypothesis` model + lifecycle (status transitions) in `apps/science/hypotheses/model.py`
- [ ] T102 [US2] Implement `attach_evidence()` (direction `supports|refutes|discriminates`, weight via claims layer) in `apps/science/hypotheses/evidence.py`
- [ ] T103 [US2] Implement `discard_hypothesis()` (requires DecisionRecord; keeps links) in `apps/science/hypotheses/decide.py`
- [ ] T104 [US2] Implement `plan_collection()` (expected KL information gain over alive hypotheses) in `apps/science/hypotheses/gain.py`
- [ ] T105 [US2] Implement per-project coverage in `apps/science/hypotheses/coverage.py`
- [ ] T106 [US2] Add routes `POST/GET /api/science/hypotheses`, `POST .../evidence`, `POST .../discard`, `POST /api/science/hypotheses/plan`, `GET .../coverage` in `apps/control-plane/api/routes/science_hypotheses.py`

**Checkpoint**: US1 AND US2 both work independently.

---

## Phase 5: User Story 3 - Causal Inference & Scope Boundary (Priority: P2)

**Goal**: Declared-model causal classification and machine-enforced person-level scope refusal.

**Independent Test**: Without a model → `CORRELATIONAL` with confounders list; with a declared model → `CAUSAL` carrying confounders+assumptions; any person-level sensitive outcome → `ScopeBoundaryError` + audit, no computation.

### Tests for User Story 3 ⚠️

- [ ] T107 [P] [US3] Contract test for causal classify + scope refusal per `contracts/interface-contracts.md` §5 and `contracts/scope-boundary.md` in `apps/science/tests/contract/test_causal_contract.py`
- [ ] T108 [P] [US3] Unit test: scope guard refuses person-sensitive outcomes before any math; audit emitted in `apps/science/tests/unit/test_scope.py`

### Implementation for User Story 3

- [ ] T109 [US3] Implement `CausalModel` + scope validation in `apps/science/causal/model.py` (forbidden classes rejected at creation)
- [ ] T110 [US3] Implement `classify()` (CORRELATIONAL default; CAUSAL only with declared model) in `apps/science/causal/infer.py`
- [ ] T111 [US3] Wire `ensure_scoped` as the first guard in `register_claim`, `classify`, and `analyze` entry points (single shared guard)
- [ ] T112 [US3] Add routes `POST /api/science/causal/classify`, `POST/GET /api/science/causal/models` in `apps/control-plane/api/routes/science_causal.py`

**Checkpoint**: US1–US3 independently functional.

---

## Phase 6: User Story 4 - Temporal Dynamics & Change Detection (Priority: P2)

**Goal**: UTC-normalized time series, change-point detection, versioned (Supersedes) reprojection.

**Independent Test**: UTC-normalized series preserves originals; injected discontinuity detected with confidence + segment summaries; reprojection produces a new version linked `SUPERSEDES`, original stays queryable.

### Tests for User Story 4 ⚠️

- [ ] T113 [P] [US4] Contract test for temporal series + change detection per `contracts/interface-contracts.md` §6 in `apps/science/tests/contract/test_temporal_contract.py`
- [ ] T114 [P] [US4] Unit test: injected regime change detected with pre/post segments in `apps/science/tests/unit/test_changedetect.py`

### Implementation for User Story 4

- [ ] T115 [US4] Implement `build_series()` (UTC normalization + original preservation) in `apps/science/temporal/timeseries.py`
- [ ] T116 [US4] Implement `detect_change_points()` (windowed mean-shift/CUSUM, config thresholds) in `apps/science/temporal/changedetect.py`
- [ ] T117 [US4] Implement versioned reprojection with `SUPERSEDES` link in `apps/science/temporal/scenario.py`
- [ ] T118 [US4] Add routes `POST /api/science/temporal/series`, `POST .../change-points`, `GET .../series/{id}` in `apps/control-plane/api/routes/science_temporal.py`

**Checkpoint**: US1–US4 independently functional.

---

## Phase 7: User Story 5 - Structure / Spectral / Higher-Order (Priority: P3)

**Goal**: Bounded structural analysis with normalized scores and permutation-null significance; DEFERRED (never truncated) over budget.

**Independent Test**: Spectral/centrality outputs normalized to documented range; motif counts come with permutation-null significance; budget-exceeding graph returns `DEFERRED` with budget+sample plan.

### Tests for User Story 5 ⚠️

- [ ] T119 [P] [US5] Contract test for structure analyze + DEFERRED per `contracts/interface-contracts.md` §7 in `apps/science/tests/contract/test_structure_contract.py`
- [ ] T120 [P] [US5] Unit test: motif counts carry permutation-null significance; over-budget returns DEFERRED in `apps/science/tests/unit/test_structure.py`

### Implementation for User Story 5

- [ ] T121 [US5] Implement size-aware bounded graph primitives in `apps/science/structure/graph.py` (no accidental O(N²); budget checks)
- [ ] T122 [US5] Implement normalized spectral/centrality analysis in `apps/science/structure/spectral.py`
- [ ] T123 [US5] Implement motif/higher-order counts + degree-preserving permutation null in `apps/science/structure/motif.py`
- [ ] T124 [US5] Add route `POST /api/science/structure/analyze` + `GET .../results/{id}` in `apps/control-plane/api/routes/science_structure.py`
- [ ] T125 [P] [US5] Add scale benchmark `bench/science/bench_structural.py` (sub-quadratic gate, SC-006; optional harness)

**Checkpoint**: US1–US5 independently functional.

---

## Phase 8: User Story 6 - Robustness & Reproducible Experiments (Priority: P3)

**Goal**: Perturbation-driven robustness, null/permutation baselines, seeded reproducible experiment registry.

**Independent Test**: Perturbation over missing/flip/subsample families reports flip rates per family; null distribution + observed statistic + comparison stored; identical seeds+versions reproduce within tolerance and log a reproduction event.

### Tests for User Story 6 ⚠️

- [ ] T126 [P] [US6] Contract test for robustness + experiment registry per `contracts/interface-contracts.md` §8–9 in `apps/science/tests/contract/test_robustness_contract.py`
- [ ] T127 [P] [US6] Unit test: perturbation grid produces per-family flip rates; reproduction within tolerance in `apps/science/tests/unit/test_reproduction.py`

### Implementation for User Story 6

- [ ] T128 [US6] Implement perturbation grid (missing-fraction / label-flip / biased-subsample) in `apps/science/robustness/perturb.py`
- [ ] T129 [US6] Implement flip-rate + sensitivity + noise-region report in `apps/science/robustness/report.py`
- [ ] T130 [US6] Implement experiment registry (inputs, outputs, seed, versions, freeze, tolerance) in `apps/science/experiments/registry.py`
- [ ] T131 [US6] Implement `reproduce()` (pinned seeds+versions, tolerance compare, event) in `apps/science/experiments/reproduction.py`
- [ ] T132 [US6] Add routes `POST /api/science/robustness`, `GET .../robustness/{id}`, `POST/GET /api/science/experiments`, `POST .../reproduce` in `apps/control-plane/api/routes/science_robustness.py`

**Checkpoint**: US1–US6 independently functional.

---

## Phase 9: User Story 7 - Scientific Review UI (Priority: P3)

**Goal**: Evidence-ladder rendering, machine-checked top-rung gating, review comments/status transitions, coverage views.

**Independent Test**: Full-provenance claims render on the ladder; claims missing calibration/robustness render `REVIEW_PENDING`, un-ratable top rung; comments and status transitions persist and render.

### Tests for User Story 7 ⚠️

- [x] T133 [P] [US7] Contract test for ladder gating per `contracts/interface-contracts.md` §10 in `apps/science/tests/contract/test_review_contract.py`
- [x] T134 [P] [US7] Unit test: ladder top rung requires calibration+null+robustness+reproduction gates in `apps/science/tests/unit/test_ladder.py`

### Implementation for User Story 7

- [x] T135 [US7] Implement `ladder_position()` machine-gating in `apps/science/review/ladder.py`
- [x] T136 [US7] Implement review events (comment / status change) in `apps/science/review/events.py`
- [x] T137 [US7] Add routes `POST/GET /api/science/review/{claim_id}` in `apps/control-plane/api/routes/science_review.py`
- [x] T138 [US7] Add science API client methods + types in `apps/webapp/src/lib/api.ts` and `apps/webapp/src/lib/science/`
- [x] T139 [US7] Build `SciencePage.tsx` (evidence ladder, REVIEW_PENDING badges, calibration/robustness context) in `apps/webapp/src/pages/SciencePage.tsx`
- [x] T140 [US7] Build `HypothesesPage.tsx` (register, evidence attach, gain plan, coverage) in `apps/webapp/src/pages/HypothesesPage.tsx`
- [x] T141 [US7] Build containers `ScienceContainer.tsx` / `HypothesisContainer.tsx` / `ExperimentContainer.tsx` + wire routes in `apps/webapp/src/App.tsx` and `Layout.tsx`

**Checkpoint**: All user stories independently functional.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories.

- [x] T142 [P] Add webapp tests (`SciencePage.test.tsx`, `HypothesesPage.test.tsx`, container tests) in `apps/webapp/src/`
- [ ] T143 Run `quickstart.md` validation end-to-end: `uv run --project apps/science pytest`, `uvx ruff check apps/science`, `npm test -- --run`, `npx tsc -b`; confirm hard-boundary test (422 scope_refused + audit) and regression gates (shared ≥144, admission ≥41, projection ≥20, webapp ≥43) all green; update `docs/` references to feature 006 if any

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately (T080–T083 parallel per [P]).
- **Foundational (Phase 2)**: Depends on Setup completion — **BLOCKS all user stories** (T084–T090).
- **User Stories (Phase 3–9)**: All depend on Foundational; stories proceed in priority order (P1 → P2 → P3) or in parallel once foundation is ready.
- **Polish (Phase 10)**: Depends on all desired user stories being complete.

### User Story Dependencies

- **US1 (P1)**: Standalone after Foundational. **US2 (P1)**: depends on US1 (credence via claims layer). **US3 (P2)** and **US4 (P2)**: depend on US1 (evidence/claims), independent of each other. **US5 (P3), US6 (P3), US7 (P3)**: depend on US1 (claims/evidence) and US2 (hypotheses, for UI); can run in parallel after US1–US2.

### Within Each User Story

- Tests written FIRST and FAIL before implementation (T091/T092, T099/T100, T107/T108, T113/T114, T119/T120, T126/T127, T133/T134).
- Models before services; services before endpoints; core implementation before integration.
- Story complete before moving to next priority.

### Parallel Opportunities

- Setup: T081, T082, T083 parallel. Foundational: T089, T090 parallel (after T084–T088 gates landed).
- Within stories: each contract test [P] runs parallel with its unit test [P]; endpoints follow the story's service layer.
- After US1 completes, US3/US4 can start alongside US2 if staffed.

---

## Parallel Example: User Story 1

```bash
# Launch contract + unit tests for US1 together (fail first, TDD):
Task: "Contract test for claim + calibration in apps/science/tests/contract/test_claim_contract.py"
Task: "Unit test overconfident → OVERCONFIDENT in apps/science/tests/unit/test_calibration.py"

# After tests pass implementation gates, models/services in sequence:
Task: "register_claim() in apps/science/claims/registry.py"
Task: "calibration harness in apps/science/claims/calibration.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 Setup (T080–T083)
2. Phase 2 Foundational (T084–T090 — CRITICAL)
3. Phase 3 US1 (T091–T098)
4. **STOP and VALIDATE**: claims + calibration + provenance independently — this is the MVP.
5. Deploy/demo if ready.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. US1 (claims/calibration) → test independently → MVP.
3. US2 (hypotheses/gain) → test independently.
4. US3/US4 → causal+scope, temporal.
5. US5/US6 → structure, robustness, experiments.
6. US7 → scientific review UI.

### Parallel Team Strategy

With multiple developers:

1. Foundation together (T080–T090).
2. After US1: Developer A → US3 (causal), Developer B → US4 (temporal), Developer C → US2 (hypotheses). US5–US7 distribute after US2 lands.
3. Every story completes and integrates independently; boundary guard (T086/T111) is shared so no story can bypass it.

---

## Notes

- [P] tasks = different files, no dependencies.
- [Story] label maps task to specific user story for traceability.
- Each user story independently completable and testable.
- Verify tests fail before implementing (TDD convention enforced by repo gate).
- Commit after each task or logical group.
- Stop at any checkpoint to validate story independently.
- Constitution gates: `ensure_scoped` (FR-007) is foundational (T086) and wired into every entry point (T111) — No-MVP rule keeps it structural, not post-hoc.
- Attribution headers mandatory on all first-party modules noting donor best-practice basis (Apache-2.0/MIT), per tracks 002–005 policy.