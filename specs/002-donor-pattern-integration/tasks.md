---

description: "Task list for Donor Pattern Integration implementation"

---

# Tasks: Donor Pattern Integration

**Input**: Design documents from `/specs/002-donor-pattern-integration/`

**Prerequisites**: plan.md (spec + constitution check), spec.md (user stories), research.md, data-model.md, contracts/

**Organization**: Tasks are grouped by user story (US1 = Statement-level knowledge model, US2 = Correlation without destruction, US3 = Investigation/evidence workspace, US4 = Connector ecosystem & recon orchestration, US5 = Evidence reasoning & stream provenance) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1/US2/US3/US4/US5)
- Include exact file paths in descriptions

## Path Conventions

Monorepo per plan.md: `apps/shared`, `apps/control-plane`, `apps/acquisition`, `apps/interpretation`, `apps/admission`, `apps/projection`, `apps/feedback`, `apps/webapp`, `apps/deploy`, `bench/`. Python apps use `uv` (pytest); Rust uses cargo; frontend uses pnpm + Vitest.

---

## Phase 1: Setup (Shared Contracts)

**Purpose**: Donor-pattern contracts + domain enforcement primitives ALL stories depend on

- [x] T001 Create statement/correlation/review/connector/parser/ontology-pack contract stubs in `apps/shared/contracts/` mirroring `specs/002-donor-pattern-integration/contracts/*.md`
- [x] T002 [P] Add `enforce_statement_provenance` + `enforce_correlation_no_merge` + `enforce_review_append_only` primitives in `apps/shared/domain/__init__.py` (I-1/I-2/I-12)
- [x] T003 [P] Add OntologyPack registry stub in `apps/shared/events/ontology_pack.py` (versioned, never overwritten; refs not blobs, I-5)
- [x] T004 [P] Add claim verdict / corroboration signal types in `apps/shared/scoring/claim.py` (separate typed signals, I-7)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Durable types that BLOCK user stories

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T005 Create Statement table model in `apps/control-plane/db/schema.py` (statement_id, dataset_id, first_seen/last_seen, original_value, extraction_version, valid_from/valid_until, provenance, tenant_id) + migration
- [x] T006 Create CorrelationEdge table model in `apps/control-plane/db/schema.py` (candidate_a/b, kind, raw_pair_score, reasons, collective_score, state, tenant_id) + migration
- [x] T007 Create ReviewDecision table model in `apps/control-plane/db/schema.py` (target_type/target_id, decision ACCEPT/REJECT/UNCERTAIN, analyst, reasoning, reviewed_at, provenance) + migration
- [x] T008 Create Connector / ReconPlan table models in `apps/control-plane/db/schema.py` + migration
- [x] T009 Create OntologyPack table model in `apps/control-plane/db/schema.py` + migration
- [x] T010 Create Claim/Storyline table models in `apps/control-plane/db/schema.py` + migration

---

## Phase 3: User Story 1 - Statement-level knowledge model (Priority: P1)

**Goal**: Every assertion carries full statement provenance; reprints collapse to one independent chain.

### Tests for User Story 1 (write first, fail before implementation)



- [x] T011 [P] [US1] Contract test for Statement provenance in `apps/shared/tests/contract/test_statement.py` — every assertion has dataset_id + extraction_version + original_value (FR-001)
- [x] T012 [P] [US1] Unit test for reprint collapse in `apps/admission/tests/test_independence.py` — N copies + 1 original → independent_sources=1, publication_count=N+1 (FR-002)

### Implementation for User Story 1

- [x] T013 [P] [US1] Implement Statement provenance emission in `apps/interpretation/pipeline.py` (statement_id/dataset_id/first_seen/last_seen/original_value/extraction_version)
- [x] T014 [P] [US1] Implement dataset-lineage reprint collapse in `apps/admission/evidence/independence.py` (chain_id, member_observation_ids, independent_sources vs publication_count)
- [x] T015 [US1] Wire Statement rows into the admission evidence path in `apps/admission/engine/assertions.py` (assertion → statement link)

---

## Phase 4: User Story 2 - Correlation Without Destruction (Priority: P1)

**Goal**: possible_match edges exist without auto-merge; analyst review is replayable provenance.

### Tests for User Story 2 (write first)

- [x] T016 [P] [US2] Contract test for correlation-no-merge in `apps/shared/tests/contract/test_correlation.py` — edges never collapse candidates into entities (FR-004)
- [x] T017 [P] [US2] Contract test for review append-only in `apps/shared/tests/contract/test_review.py` — review rows immutable, replayable (FR-006)

### Implementation for User Story 2

- [x] T018 [P] [US2] Implement CorrelationEdge graph over candidates in `apps/admission/resolution/collective.py` (possible_match edges with raw_pair_score/reasons; no auto-merge)
 
- [x] T019 [P] [US2] Implement ReviewDecision persistence + event emission in `apps/control-plane/services/review.py` (ACCEPT/REJECT/UNCERTAIN; append-only provenance)
- [x] T020 [US2] Expose correlation + review endpoints in `apps/control-plane/api/routes/entities.py`
---

## Phase 5: User Story 3 - Investigation & Evidence Workspace (Priority: P2)

**Goal**: Analyst drives investigations with evidence grading, timeline, and review in a merged graph/timeline/map workbench.

### Tests for User Story 3 (write first)

- [x] T021 [P] [US3] Unit test for evidence grading + timeline in `apps/control-plane/tests/integration/test_lineage_api.py` (evidence objects carry grading + provenance)

### Implementation for User Story 3

- [x] T022 [P] [US3] Add evidence + review panels to `apps/webapp/src/pages/InvestigationPage.tsx` (targets/evidence/timeline/sources/decisions)
- [x] T023 [P] [US3] Add merged graph/timeline/map entity inspector to `apps/webapp/src/pages/EntityViewPage.tsx` (PANO-style; timeline from assertion temporal fields)
- [x] T024 [US3] Add review controls to `apps/webapp/src/components/LineageWalker.tsx` (ACCEPT/REJECT/UNCERTAIN → review API)

---

## Phase 6: User Story 4 - Connector Ecosystem & Recon Orchestration (Priority: P2)

**Goal**: New sources register as connectors behind AcquisitionWorker; recon plans orchestrate acquisition tasks.

### Tests for User Story 4 (write first)

- [x] T025 [P] [US4] Contract test for AcquisitionWorker compliance in `apps/acquisition/tests/integration/test_worker.py` (capabilities/estimate/acquire + standard observation)

### Implementation for User Story 4

- [x] T026 [P] [US4] Implement connector registry + recon plan endpoints in `apps/control-plane/services/source_registry.py` (register, ACTIVE gate, plan_id, task_ids)
- [x] T027 [P] [US4] Add `ParserAdapter.can_parse/parse` to `apps/interpretation/parsers/registry.py` (HTML/JSON/CSV/PDF/Email/Archive)
- [x] T028 [US4] Wire recon-plan scheduling through existing frontier/dispatcher in `apps/control-plane/services/dispatcher.py` (ReconPlan → Kafka → collectors → observations)

---

## Phase 7: User Story 5 - Evidence Reasoning & Stream Provenance (Priority: P3)

**Goal**: Corroboration vs copying verdicts and storylines over consolidated evidence; Kafka-native provenance intact.

### Tests for User Story 5 (write first)

- [x] T029 [P] [US5] Contract test for claim verdict in `apps/admission/tests/test_claims.py` (SUPPORTED/CONTRADICTED/UNCERTAIN from independent chains)
- [x] T030 [P] [US5] Unit test for stream replay idempotency in `apps/shared/tests/integration/test_idempotency.py` (provenance survives replay, no duplicate rows)

### Implementation for User Story 5

- [x] T031 [P] [US5] Implement corroboration-vs-copy + claim verdict + storyline in `apps/admission/evidence/independence.py` and `apps/admission/engine/temporal.py`
- [x] T032 [P] [US5] Wire OntologyPack consumption in `apps/interpretation/extractors/registry.py` (admissible types/relations from ACTIVE pack)
- [x] T033 [US5] Ensure all new events use EventEnvelope + idempotent consumers (statement/review/correlation/ontology) in `apps/shared/events/*`

---

## Phase 8: Polish & Cross-Cutting

- [x] T034 [P] Documentation: full donor mapping in `docs/architecture/donor-analysis.md` (exists; link from this feature)
- [x] T035 [P] Bench harness: add statement/correlation/claim micro-benchmarks in `bench/bench/harness.py` (provenance/reprint/claim latencies)
- [x] T036 Run full validation per quickstart + bench/run --scenario smoke-val, plus per-story tests; verify SC-001…SC-010

---

## Dependencies & Execution Order

- **Setup/Foundational (Phases 1–2)** block US1–US5.
- **US1 (P0)** → **US2 (P0)** → **US3 (P2)** → **US4 (P2)** → **US5 (P3)** (priority order).
- Tests first for each story; models → services → endpoints; core before integration.

## Notes

- [P] tasks = different files, no dependencies.
- Story label maps to feature 002 user story; model/type names follow data-model.md.
- Architecture contracts (EventEnvelope, AcquisitionWorker, Graph* abstraction, UtilityScorer) must NEVER break — Constitution No-MVP rule.
- Donor adoption is patterns-only (FR-014); no vendor code/deps in deliverables.

## Implementation status (T001–T036)

- **Done (36)**: shared domain primitives (T002), OntologyPack registry (T003), claim/corroboration signals (T004); Postgres tables Statement/CorrelationEdge/ReviewDecision/Connector/ReconPlan/OntologyPack/Claim (T005–T010); contract stubs in `apps/shared/contracts/` (T001); statement provenance in `engine/assertions.py` (T013, lives with assertion lifecycle rather than `pipeline.py`); reprint collapse + dataset boundary + claim assessment in `evidence/independence.py` (T014/T031); CorrelationEdge + `correlate()` in `resolution/collective.py` (T018); ReviewService + API endpoints (T019/T020); ParserAdapter (T027); Connector registry + ReconPlan service + `/connectors` API (T026); **recon-plan dispatch through the frontier/dispatcher loop with `recon.plan_started`/`recon.plan_completed` lineage (T028, `dispatcher.run_recon_plan` + tests)**, ontology gating in extractors (T032); **producer-side EventEnvelope emission for `statement.created`/`review.recorded`/`correlation.edge_created` via idempotent producers (T033, assertions.py/review.py/collective.py + tests)**; webapp review controls + correlations/map panels (T022–T024); docs (T034); **donor statement/correlation/claim micro-benchmarks (T035, `bench/bench/harness.py` `bench_donor`)**; full validation (T036). Tests: shared 77, admission 37, interpretation 20, projection 24, feedback 8, control-plane 77, acquisition-python 11, bench 18, cargo 31, webapp 26 — all green; `bench/run.py --scenario smoke-val --dry-run` PASS; webapp fixes: review buttons on edge-less lineage chains (LineageWalker) + dropped dead `handleRefreshMetrics` (InvestigationContainer).