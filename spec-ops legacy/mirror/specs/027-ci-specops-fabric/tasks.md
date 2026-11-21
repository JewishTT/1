# Tasks: CI/SpecOps Department Fabric

**Input**: Design documents from `/specs/027-ci-specops-fabric/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Included. The COGNITIVE Constitution mandates a guarding test per vendored donor (attribution header) and the plan/quickstart define automated gates (RoE gate, named-absence, unknown-status), so test tasks are required here, not optional.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

Web app: frontend `apps/webapp/src/`, backend `apps/control-plane/`, donors `apps/specops/`, lab `deploy/specops/lab/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Create CI/SpecOps directory structure: `apps/webapp/src/ci/`, `apps/webapp/src/ci/panels/`, `apps/specops/vendor/`, `apps/specops/roe/`, `apps/control-plane/api/routes/` (specops routers go here), `deploy/specops/lab/`
- [X] T002 Create lab compose skeleton in `deploy/specops/lab/docker-compose.yml` with three services: caldera core, PhishSlayer lab, and an isolated target fixture (no external egress)
- [X] T003 [P] Add CI/SpecOps sections and breadcrumb titles to `apps/webapp/src/shell/nav.ts` under the existing `specops` module (Emulation, Phishing, Forensics, Counterintel, Social destinations)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story — RoE gate, status/absence vocabulary, API client, canvas host.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Implement the rules-of-engagement gate in `apps/specops/roe/gate.py`: `RoEError`, `RosterError`, `launch_campaign()` that refuses to send without a confirmed sign-off, `validate_target_roster()` accepting only a supervisor-approved list, and `capture_passwords=False` hardcoded (PIDSF pattern, research D4)
- [X] T005 Implement the RoE router `apps/control-plane/api/routes/specops_roe.py` exposing `POST /api/v1/specops/roe` (record sign-off) per `contracts/specops-api.md`, and mount it in `apps/control-plane/api/main.py`
- [X] T006 [P] Define the CI row vocabulary + named-absence type in `apps/webapp/src/ci/types.ts` (`Unavailable`, panel server-state shape with `served[]`/`missing[]`/`scope`), mirroring `src/ops/types.ts`
- [X] T007 [P] Implement status mapping in `apps/webapp/src/ci/model.ts` reusing `src/ui/status.ts` `WorkStatus`; any unrecognized donor status string maps to `Unknown` (FR-011)
- [X] T008 [P] Add the specops API client functions in `apps/webapp/src/lib/api.ts` (plans, operations, campaigns, roe, counterintel, social, forensics) matching `contracts/specops-api.md`, with named-absence `missing[]` surfaced to callers
- [X] T009 Build the canvas host `apps/webapp/src/ci/CICanvas.tsx`: one canvas with a tab per panel (Operations, Emulation, Phishing, Forensics, Detection, Counterintel, Social), a persistent scope note, and per-tab state preservation — mirrors `src/ops/OpsCanvas.tsx`
- [X] T010 [P] Add `apps/webapp/src/ci/ci.css` for the canvas shell and panel layout on the existing design tokens (elegant, coherent visual system, SC-008)
- [X] T011 Mount the CI view in the workspace switcher and route it in `apps/webapp/src/App.tsx` (process-centric: a view within the investigation workspace, research D1)

**Checkpoint**: Foundation ready — RoE gate + router live, vocabulary/API client/canvas host in place; user story panels can now be built in parallel.

---

## Phase 3: User Story 1 - Unified CI/SpecOps fabric shell (Priority: P1) 🎯 MVP

**Goal**: One canvas presenting all operational panels as tabs, each scope-labelled, absorbing the existing operations surface; named-absence when a source is down.

**Independent Test**: Open the department, switch all tabs, confirm each renders its subject + scope note; stop a donor and confirm its panel shows a named absence (quickstart Scenario 1).

### Tests for User Story 1 ⚠️

- [ ] T012 [P] [US1] Vitest for `CICanvas` tab switching + state preservation in `apps/webapp/src/ci/CICanvas.test.tsx`
- [ ] T013 [P] [US1] Vitest for named-absence rendering (source down → source-named absence, not zero) in `apps/webapp/src/ci/panels/panels.named-absence.test.tsx`

### Implementation for User Story 1

- [ ] T014 [P] [US1] Implement the Operations panel `apps/webapp/src/ci/panels/OperationsPanel.tsx` re-exporting/absorbing the existing `src/ops/OperationsWorkspace` surface (scope-labelled tenant-wide)
- [ ] T015 [US1] Add `useCiState` TanStack Query hooks in `apps/webapp/src/ci/useCiState.ts` with per-panel query keys and `missing[]` arrays (mirrors `src/ops/useOpsState.ts`)
- [ ] T016 [US1] Register all seven panels in `CICanvas.tsx` with lazy mounts so each renders its subject within one interaction (SC-001)

**Checkpoint**: US1 delivers the MVP shell — every panel reachable, scope-labelled, named-absence honest.

---

## Phase 4: User Story 2 - Kill-chain adversary emulation (Priority: P1) 🎯 MANDATORY

**Goal**: Select an ATT&CK plan, confirm an authorized lab target under RoE, launch, and watch planned-vs-executed abilities live; freeze/inspect after.

**Independent Test**: Launch a micro plan against a lab fixture and observe abilities move planned→executed live; launch without RoE is refused (quickstart Scenario 2).

### Tests for User Story 2 ⚠️

- [X] T017 [P] [US2] pytest for `specops_emulation.py`: list/get plans, launch blocked without confirmed RoE (409 RoEError), live ability state in `apps/control-plane/tests/unit/test_specops_emulation.py`
- [X] T018 [P] [US2] Guarding test for vendored caldera + ael/adversary_emulation_library with attribution header in `apps/specops/tests/test_vendor_emulation.py`

### Implementation for User Story 2

- [X] T019 [P] [US2] Vendor caldera (Apache-2.0) into `apps/specops/vendor/caldera/` with attribution header (research D3)
- [X] T020 [P] [US2] Load ael + adversary_emulation_library plan YAML (Apache-2.0) as plan data parsed into the scenario DSL in `apps/specops/vendor/`
- [X] T021 [US2] Implement the emulation router `apps/control-plane/api/routes/specops_emulation.py`: `GET /plans`, `GET /plans/{id}`, `POST /operations` (RoE-gated), `GET /operations/{id}` per contract; mount in `main.py`
- [X] T022 [P] [US2] Add emulation derivations in `apps/webapp/src/ci/model.ts` (plans→rows, operation→per-ability planned/executed with WorkStatus mapping)
- [X] T023 [US2] Build the Emulation panel `apps/webapp/src/ci/panels/EmulationPanel.tsx`: plan list, RoE confirm, launch, live ability matrix (cytoscape ability graph), freeze/inspect
- [ ] T024 [US2] Wire emulation TanStack Query hooks (poll operation state) in `apps/webapp/src/ci/useCiState.ts`

**Checkpoint**: US2 is the mandatory kill-chain pillar — emulation runs end-to-end against a lab fixture, RoE-gated.


---

## Phase 5: User Story 3 - Phishing / SAT under RoE gate (Priority: P1) 🎯 MANDATORY

**Goal**: Prepare an authorized campaign against a supervisor-approved roster; send is blocked until RoE sign-off; credentials never captured; engagement metrics mapped to ATT&CK.

**Independent Test**: Launch without sign-off (blocked), out-of-roster target (rejected), then authorized run (metrics, 0 credentials stored) — quickstart Scenario 3.

### Tests for User Story 3 ⚠️

- [X] T025 [P] [US3] pytest for `specops_phishing.py`: launch blocked without RoE (409), out-of-roster rejected (422), 0 credentials persisted, metrics present in `apps/control-plane/tests/unit/test_specops_phishing.py`
- [X] T026 [P] [US3] pytest proving `capture_credentials` is never written for any submission path in `apps/specops/tests/test_phishing_no_capture.py`

### Implementation for User Story 3

- [X] T027 [P] [US3] Run PhishSlayer (GPLv3) as an isolated lab service via `deploy/specops/lab/docker-compose.yml`; add a control-plane proxy in `apps/control-plane/api/routes/specops_phishing.py` (research D2 shape 2, D4)
- [X] T028 [US3] Implement the phishing router `apps/control-plane/api/routes/specops_phishing.py`: `POST /campaigns`, `POST /campaigns/{id}/launch` (RoE-gated + roster-validated server-side), `GET /campaigns/{id}` per contract; mount in `main.py`
- [X] T029 [US3] Enforce the RoE gate + roster validation inside the launch path using `apps/specops/roe/gate.py` so the UI cannot bypass it (FR-005/FR-006)
- [X] T030 [P] [US3] Add phishing derivations in `apps/webapp/src/ci/model.ts` (campaign→engagement metrics, ATT&CK mapping, `captured_credentials_count` always 0)
- [X] T031 [US3] Build the Phishing panel `apps/webapp/src/ci/panels/PhishingPanel.tsx`: roster editor, RoE confirm, launch (blocked state shown), engagement metrics
- [ ] T032 [US3] Wire phishing TanStack Query hooks in `apps/webapp/src/ci/useCiState.ts`

**Checkpoint**: US3 is the mandatory phishing/SAT pillar — safe (RoE-gated, no capture), operational end-to-end.


---

## Phase 6: User Story 4 - Counterintelligence subject board (Priority: P2)

**Goal**: Open a subject and see its tracked invariants (belief-state, narrative-position, bias-profile, coordination-signature, phase-state), each with evidence; unsupported invariants rendered as unsupported.

**Independent Test**: Open a subject with known evidence; each invariant shows evidence refs; an invariant without evidence renders as unsupported (quickstart Scenario 4).

### Tests for User Story 4 ⚠️

- [ ] T033 [P] [US4] pytest for `specops_counterintel.py`: invariants carry evidence refs; empty evidence ⇒ `supported: false`; tenant isolation in `apps/control-plane/tests/unit/test_specops_counterintel.py`

### Implementation for User Story 4

- [X] T034 [P] [US4] Wire cognitive operators (CognitiveAttack, DIMA-OntoToolkit, io-coordinated-replies, IO-detecting) to emit subject-invariant claims to `/api/science/*` (research D5)
- [X] T035 [US4] Implement the counterintel router `apps/control-plane/api/routes/specops_counterintel.py`: `GET /subjects/{id}` returning invariants + relations with evidence refs per contract; mount in `main.py`
- [X] T036 [P] [US4] Add subject/invariant derivations in `apps/webapp/src/ci/model.ts` (invariant→row with supported flag + evidence links)
- [X] T037 [US4] Build the Counterintel panel `apps/webapp/src/ci/panels/CounterintelPanel.tsx`: subject selector, invariant readout with evidence, relation graph (cytoscape), unsupported marking
- [ ] T038 [US4] Wire counterintel TanStack Query hooks in `apps/webapp/src/ci/useCiState.ts`

**Checkpoint**: US4 delivers the counterintelligence half — subject invariants, evidence-backed, honest about support.

---

## Phase 7: User Story 5 - Social-reaction simulation (Priority: P2)

**Goal**: Inject a narrative/shock into a modeled population and project reach, polarization and phase-transition risk over a horizon; artifacts inspectable; low population ⇒ low confidence.

**Independent Test**: Run a projection and view trajectories + phase-transition indicator; tiny population yields low confidence (quickstart Scenario 5).

### Tests for User Story 5 ⚠️

- [ ] T039 [P] [US5] pytest for `specops_social.py`: trajectories over horizon, phase-transition risk surfaced, low population ⇒ low confidence in `apps/control-plane/tests/unit/test_specops_social.py`

### Implementation for User Story 5

- [X] T040 [P] [US5] Integrate social-simulation operators (YuLan-OneSim/posim/silisocs/DualMind/social-oscillation/cognitive_phase_transitions) as science operators returning projection claims (research D5)
- [X] T041 [US5] Implement the social router `apps/control-plane/api/routes/specops_social.py`: `POST /projections` per contract (trajectories, phase_transition_risk, confidence, artifacts_ref); mount in `main.py`
- [X] T042 [P] [US5] Add projection derivations in `apps/webapp/src/ci/model.ts` (trajectory series + phase-transition indicator + confidence)
- [X] T043 [US5] Build the Social panel `apps/webapp/src/ci/panels/SocialPanel.tsx`: population + narrative input, horizon, trajectory chart (echarts), phase-transition risk indicator, inspectable run artifacts
- [ ] T044 [US5] Wire social TanStack Query hooks in `apps/webapp/src/ci/useCiState.ts`

**Checkpoint**: US5 delivers social-reaction modeling — requested capability, honest about confidence.


---

## Phase 8: User Story 6 - APT forensics: expected vs actual telemetry (Priority: P2)

**Goal**: For a completed emulation run, compare expected telemetry against recorded observations; unmatched expectations listed as detection gaps; ATT&CK coverage heatmap.

**Independent Test**: Open a completed run with known telemetry; expected-vs-actual renders; unmatched items appear as gaps (quickstart Scenario 6).

### Tests for User Story 6 ⚠️

- [ ] T045 [P] [US6] pytest for `specops_forensics.py`: expected-vs-actual per ability, unmatched ⇒ gap, coverage map in `apps/control-plane/tests/unit/test_specops_forensics.py`

### Implementation for User Story 6

- [X] T046 [US6] Implement the forensics router `apps/control-plane/api/routes/specops_forensics.py`: `GET /operations/{id}` (comparison + gaps + coverage) per contract; expected telemetry from the emulation plan, actual from recorded observations; mount in `main.py`
- [X] T047 [P] [US6] Add forensics derivations in `apps/webapp/src/ci/model.ts` (comparison rows, gap list, coverage)
- [X] T048 [US6] Build the Forensics panel `apps/webapp/src/ci/panels/ForensicsPanel.tsx`: expected-vs-actual table, gap list, ATT&CK coverage heatmap (echarts)
- [ ] T049 [US6] Wire forensics TanStack Query hooks in `apps/webapp/src/ci/useCiState.ts`

**Checkpoint**: US6 makes emulation pay off — detection gaps and coverage are explicit.

---

## Phase 9: User Story 7 - Detection coverage & evidence-to-detection (Priority: P3)

**Goal**: Trace a finding through evidence → behavior → technique → required telemetry → candidate rules; record validation.

**Independent Test**: Trace one finding end-to-end; each hop renders with its source (quickstart Scenario 6, detection view).

### Implementation for User Story 7

- [ ] T050 [US7] Implement the detection router `apps/control-plane/api/routes/specops_detection.py`: `GET /findings/{id}/detection-chain` + `POST /candidates/{id}/validate` per the evidence-to-detection pattern (adversarygraph reference); mount in `main.py`
- [X] T051 [US7] Build the Detection panel `apps/webapp/src/ci/panels/DetectionPanel.tsx`: finding→evidence→behavior→technique→telemetry→candidate-rules chain, validation result
- [ ] T052 [US7] Wire detection TanStack Query hooks in `apps/webapp/src/ci/useCiState.ts`

**Checkpoint**: US7 closes the defense loop — findings trace to detection candidates.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T053 [P] Run the full quickstart.md validation (Scenarios 1–6) end-to-end against the lab compose
- [ ] T054 [P] Verify SC-004/SC-005: every figure traceable to evidence or marked named-absence/unsupported; 0 untraceable numbers
- [ ] T055 [P] Verify SC-006: unknown donor status → `Unknown` in 100% of cases (no new status value)
- [ ] T056 Visual/aesthetic pass across all panels for a coherent, elegant system (SC-008)
- [ ] T057 [P] Attribution headers + guarding tests present for every vendored donor (constitution rev.2)
- [ ] T058 Documentation: update `docs/architecture/donors/` cross-refs and note deferred hardening (isolation/licensing) as a follow-up


---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories (RoE gate + router, vocabulary, API client, canvas host, workspace mount).
- **User Stories (Phase 3–9)**: All depend on Foundational completion.
  - US1 (P1) and US2 (P1) and US3 (P1) first — US2/US3 are the mandatory pillars.
  - US4/US5/US6 (P2) next; US7 (P3) last.
- **Polish (Phase 10)**: Depends on the desired user stories being complete.

### User Story Dependencies

- **US1 (P1)**: after Foundational; no dependency on other stories. Delivers the MVP shell.
- **US2 (P1, mandatory)**: after Foundational (needs RoE gate T004/T005); independent otherwise.
- **US3 (P1, mandatory)**: after Foundational (needs RoE gate T004/T005); independent otherwise.
- **US4 (P2)**: after Foundational; depends on cognitive operators emitting claims (T034) but not on US2/US3.
- **US5 (P2)**: after Foundational; depends on social operators (T040); independent of US2–US4.
- **US6 (P2)**: after US2 output exists (needs a completed emulation run to compare); otherwise independent.
- **US7 (P3)**: after Foundational; independent.

### Within Each User Story

- Tests written and FAIL before implementation (constitution guarding tests).
- Models/derivations before routers; routers before panels; hooks before panel wiring.
- Story complete before moving to the next priority.

### Parallel Opportunities

- All Setup tasks marked [P] run in parallel.
- All Foundational tasks marked [P] run in parallel (T006, T007, T008, T010).
- After Foundational: US1, US2, US3 can start in parallel (different files); US4/US5 independent of US2/US3.
- Within a story, tests and vendor/derivation tasks marked [P] run in parallel.

---

## Parallel Example: User Story 2 (kill-chain)

```bash
# Vendor + guarding test in parallel:
Task: "Vendor caldera into apps/specops/vendor/caldera/ (T019)"
Task: "Load ael + adversary_emulation_library plan YAML (T020)"
Task: "pytest specops_emulation + vendor guarding test (T017, T018)"
# Then router → derivations → panel → hooks (sequential core).
```

---

## Implementation Strategy

### MVP First (mandatory pillars)

1. Phase 1 Setup.
2. Phase 2 Foundational (CRITICAL — blocks all).
3. Phase 3 US1 (shell) → validate independently.
4. Phase 4 US2 (kill-chain) + Phase 5 US3 (phishing) — the two mandatory pillars.
5. **STOP and VALIDATE**: run quickstart Scenarios 1–3; confirm RoE gate, named-absence, live emulation, 0 credential capture.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. US1 → MVP shell. US2 → kill-chain. US3 → phishing/SAT (mandatory set complete).
3. US4 → counterintel. US5 → social-reaction. US6 → forensics.
4. US7 → detection coverage.
5. Polish: quickstart validation, evidence/absence/unknown-status gates, aesthetic pass.

### Deferred (explicit owner decision, tracked as follow-up)

Full process isolation, network-egress/sandbox hardening, and license reconciliation — after the department is working (FR-003/SC-007). The RoE gate + lab-only targeting ship in the mandatory pillars so the capability is safe to run.

---

## Notes

- [P] tasks = different files, no dependencies.
- [Story] label maps task to a user story for traceability.
- Each user story is independently completable and testable.
- Verify tests fail before implementing.
- Commit after each task or logical group.
- Direct wholesale donor integration this phase; isolation/licensing/hardening deferred (owner decision).
- Unknown donor status → `Unknown`; unserved field → named absence with source name (never zero/default).

