---

description: "Task list for feature implementation"
---

# Tasks: Donor Core Subsystems

**Input**: Design documents from `/specs/005-donor-core-subsystems/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Organization**: Tasks grouped by user story for independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story this task belongs to (US1..US6)
- All tasks carry exact file paths.

## Path Conventions

- Monorepo `apps/`: `shared`, `admission`, `interpretation`, `acquisition`, `control-plane`, `webapp`
- python apps use `uv run --project apps/<app> pytest`; webapp uses vitest/tsc.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Baseline + scaffolding for the whole track.

- [x] T001 Verify regression baseline before any change: run `uv run --project apps/shared pytest`, `uv run --project apps/admission pytest`, `uv run --project apps/bench pytest`, and webapp `npm test` + `npx tsc -b`; record counts (expect shared=144, admission=41, bench=20, webapp=43).
- [x] T002 Add event catalog entries `resolution.candidate_created`, `resolution.candidate_decided`, `evidence.manifest_created` (and `resolution.merge_recorded`) in `apps/shared/events/topics.py`.

---

## Phase 2: Foundational (Canonical Knowledge Model Core)

**Purpose**: The `apps/shared/domain` model that ALL stories consume (spec FR-004). BLOCKS US1, US3, US4, US6.

**Donor slice**: FollowTheMoney (MIT) `donors/followthemoney/followthemoney/{model,entity}.py` — stdlib-only subset.

- [x] T003 [P] Create `apps/shared/domain/schema.py`: `SchemaDefinition`, `SchemaRegistry`, `UnknownSchemaError`; `register/resolve/validate_entity` mappings keyed by `schema_name`. Attribution header (repo, license, commit-ish, changes).
- [x] T004 [P] Create `apps/shared/domain/property.py`: `Property` (name, type, value, original_value, confidence) with registry validation. Attribution header.
- [x] T005 [P] Create `apps/shared/domain/entity.py`: `Entity` (entity_id, schema_name, properties, dataset_id, first/last_seen). Attribution header.
- [x] T006 Create `apps/shared/domain/statement.py`: canonical `Statement` (statement_id, entity_id, schema_name, properties, dataset_id, original_value, extraction_version, valid_from/until, first/last_seen, provenance, claimed=True); `build_statement()` emitting `statement.created` via `events.kafka.build_envelope`; inherits existing `StatementProvenanceError` invariant. Attribution header (followthemoney model pattern).
- [x] T007 [P] Unit tests `apps/shared/tests/unit/domain/test_schema.py`, `test_property.py`, `test_entity.py`, `test_statement.py`: round-trip provenance/dataset/temporal; unknown schema raises; missing provenance raises.
- [x] T008 Export canonical model + invariants from `apps/shared/domain/__init__.py` (no duplicated class definitions remaining in that package).

**Checkpoint**: `uv run --project apps/shared pytest` — new domain tests green (shared ≥ 144 + new).

---

## Phase 3: User Story 1 - Unified Knowledge Model in the executable path (Priority: P1) ✱ MVP

**Goal**: parsers/resolution/admission produce and consume Statements through the canonical model.

**Independent Test**: a parsed observation yields a canonical Statement; `statement.created` preserved; no duplicated Statement class remains in admission.

- [x] T009 [US1] Adapt `apps/admission/engine/assertions.py` to consume `shared.domain.Statement` (delete the local `Statement` dataclass; keep event shape). Depends on T006.
- [x] T010 [P] [US1] Wire `apps/interpretation/pipeline.py` to emit entities/properties via the domain model + produce `statement.created` for parsed observations.
- [x] T011 [US1] Integration test `apps/shared/tests/unit/domain/test_statement_consumer.py` (or admission test): observation → Statement round-trip preserves dataset/provenance/temporal; grep-check: `grep -r "class Statement" apps/admission` empty.

**Checkpoint**: shared + admission green; US1 independently testable.

---

## Phase 4: User Story 2 - Resolution with human review & non-destructive merge (Priority: P1)

**Goal**: reviewable Candidates + append-only merge/reverse records behind existing resolver/review stack.

**Independent Test**: indicative pair → Candidate (deterministic pair_key); accept keeps both entities queryable; reject preserved & not re-proposed; reverse appends.

**Donor slice**: OpenOSINT (MIT) `donors/OpenOSINT/openosint/graph/review.py` + `graph/dedup/candidates.py` + `graph/store/resolutions.py`.

- [x] T012 [P] [US2] Create `apps/admission/resolution/candidate.py`: `Candidate` (pair_key deterministic, candidate_a/b, score_vector, collective_score, evidence_links, review_state `open|accepted|rejected|reversed`, decision_revision list), `create_candidate()`, `decide_candidate()`, `reverse_resolution()`, `ResolutionRecord` (non-destructive). Attribution header (OpenOSINT).
- [x] T013 [US2] Adapt `apps/admission/resolution/{resolver.py,collective.py}` to materialize Candidates and emit `resolution.candidate_created` / `resolution.candidate_decided` envelopes (topics from T002). Acceptance = refs-only payloads (I-5).
- [x] T014 [US2] Wire `apps/control-plane/services/review.py` — `ReviewTargetType.CANDIDATE` accepts a pair_key; review decision persists as append-only `ReviewRecord`, compatible with candidate state.
- [x] T015 [P] [US2] Unit tests `apps/admission/tests/test_candidate.py`: deterministic pair key; accept/reject/reverse semantics; original entities retained; rejection not re-proposed at equal evidence.
- [x] T016 [US2] Expose reverse path in `apps/control-plane/api/routes/investigations.py` or a resolution route (read-only list + decision endpoints).

**Checkpoint**: `uv run --project apps/admission pytest` + `apps/control-plane pytest` green.

---

## Phase 5: User Story 6 - Review queue & timeline UI (Priority: P2)

**Goal**: review queue + node status badges in the webapp, driven by vitni ported review model.

**Independent Test**: vitest on `review.ts`; UI renders queue, filters/sorts, tolerates empty/unknown data.

**Donor slice**: vitni (Apache-2.0) `donors/vitni/app/renderer/src/features/review/reviewModel.ts`; PANO reference = `contracts/ux-reference.md` only.

- [x] T017 [P] [US6] Port `apps/webapp/src/lib/donor/review.ts` (pure): types + `buildDerivedReviewAssertions` / `filterReviewAssertions` / `buildNodeReviewStatusMap` / `getAdjacentReviewAssertionId` / `getNextUnreviewedAssertionId`; attribution header (vitni).
- [x] T018 [P] [US6] Vitest `apps/webapp/src/lib/donor/review.test.ts` covering derive (grouping/corroboration/conflict), filter/sort modes, status map, empty-input.
- [x] T019 [US6] Wire review queue into `apps/webapp/src/containers/InvestigationContainer.tsx` (or a ReviewContainer) using `review.ts`; render badges via existing `confidence.ts`/status colors.
- [x] T020 [US6] Surface evidence/timeline grouping in `apps/webapp/src/components/LineageWalker.tsx` (per-subject fact list, date-ordered) + `npx tsc -b` + vitest green.

**Checkpoint**: `cd apps/webapp && npm test && npx tsc -b --pretty false` green.

---

## Phase 6: User Story 3 - Pluggable parsers & evidence manifest (Priority: P2)

**Goal**: hardened parser sandbox + immutable manifest chain `Finding → Evidence → Observation → Raw`.

**Independent Test**: registered adapter parses deterministically; manifest chains to raw sha256; oversized/hostile input quarantined, never parsed.

**Donor slice**: NetForensicAI (MIT) `donors/NetForensicAI/netforensicai/core/evidence.py` (Evidence/manager, sha256 streaming).

- [x] T021 [P] [US3] Create `apps/interpretation/evidence/manifest.py`: `Finding` (reusable), `EvidenceManifest` chain (finding → evidence → observation → raw_sha256), `build_manifest()`, streaming `sha256_of_bytes`; emits `evidence.manifest_created` (refs-only). Attribution header (NetForensicAI).
- [x] T022 [US3] Harden `apps/interpretation/parsers/registry.py`: size/time/depth limits (`ParserLimitError`), deterministic adapter dispatch, unknown-format → quarantine path (reuse quarantine/dlq semantics in `apps/shared/events/dlq.py`).
- [x] T023 [P] [US3] Tests `apps/interpretation/tests/test_evidence_manifest.py` + extend `test_parser_adapter.py`: manifest chain integrity, limit error, quarantine on unknown.
- [x] T024 [US3] Adapt `apps/interpretation/pipeline.py` to attach manifests to parsed observations (integration point for US1 statements).

**Checkpoint**: `uv run --project apps/interpretation pytest` green.

---

## Phase 7: User Story 4 - Connector module registry (Priority: P3)

**Goal**: SpiderFoot-style module lifecycle (register/scan/stop) + bounded pool + shared event channel, normalized via `shared/donor/target.py`.

**Independent Test**: two dummy modules register; scan pushes events on one channel; stop is prompt; fault contained; events normalize to canonical targets.

**Donor slice**: SpiderFoot (MIT, logic) `donors/spiderfoot/spiderfoot/{plugin,event,threadpool}.py`.

- [x] T025 [P] [US4] Create `apps/acquisition/registry.py`: `ConnectorModule` protocol (name, capabilities, run(task, channel), stop()), registry, `connector.registered`/`connector.status_changed` emissions. Attribution header (SpiderFoot).
- [x] T026 [US4] Port bounded thread pool + event normalization helper (`shared/donor/target.py` reuse) into `apps/acquisition/registry.py`(`ConnectorRunner`); fault isolation per module.
- [x] T027 [P] [US4] Tests `apps/acquisition/tests/test_connector_registry.py`: registration, channel events, prompt stop, fault containment, canonical-target normalization.

**Checkpoint**: `uv run --project apps/acquisition pytest` green (existing acquisition suite + new).

---

## Phase 8: User Story 5 - Investigation state & monitoring (Priority: P3)

**Goal**: monitor counters + atomic updates + late-event dead-letter parking in control plane.

**Independent Test**: counters advance atomically; snapshot persists on close; late event after COMPLETED is parked, state unmutated.

**Donor slice**: investigator (MIT) `donors/investigator/src/investigator/state/investigation.py`.

- [x] T028 [P] [US5] Extend `apps/control-plane/domain/investigation.py`: `monitor` counters (`items_examined`, `evidence_ingested`, `candidates_resolved`, `findings_created`), `update_counter()` (atomic Delta), `snapshot()`, terminal-state late-event parking → `governance.quarantined`. Attribution header (investigator state pattern).
- [x] T029 [US5] Adapt `apps/control-plane/workflows/investigation.py` to emit `investigation.*` monitor/state events on transitions + snapshot on COMPLETED.
- [x] T030 [P] [US5] Tests `apps/control-plane/tests/unit/test_monitor.py`: counter updates, snapshot, late-event parking.

**Checkpoint**: `uv run --project apps/control-plane pytest` green.

---

## Phase 9: Polish & Cross-Cutting

- [x] T031 [P] Attribution/license audit: every adapted module carries header (repo/license/commit-ish/changes); grep NO imports of `donors/PANO`, `donors/rengine`, `donors/kipi` in `apps/`. **CSS pull (user-directed):** vendored donor stylesheets into `apps/webapp/src/styles/donors/` with license headers + `INDEX.md` (PANO tokens ported from `ui/styles/*.py`, CC BY-NC-4.0; vitni scoped `.v2-*` files Apache-2.0 imported via `src/styles/layers.css`; spiderfoot/kafSIEM/rengine/netforensicai CSS vendored, global-selector/tailwind-dependent files documented as non-imported). Wired `layers.css` into `main.tsx` before `index.css`. **CSS application (user-directed, follow-up):** donor CSS now actually drives the UI — `.v2-*` palette bridged onto review/lineage classes (`src/styles/bridge/vitni.css` → `.review-*`, `.confidence-badge`, `.node-review-status`); PANO graph/timeline tokens (`--pano-*`) adopted in `index.css` `:root` and consumed by `.graph-canvas`, `#entity-timeline`, `GraphPanel` cytoscape styles; spiderfoot/netforensicai re-scoped under section wrappers `.sf-scope` (SearchPage fused results) and `.nfa-scope` (EntityViewPage evidence/timeline manifests) via `src/styles/scoped/*.css`. `npm test` 67/67 green, `tsc -b` clean.
- [ ] T032 [P] `uvx ruff check` on all touched Python paths; fix clean.
- [ ] T033 Full regression: `uv run --project apps/shared pytest` and `apps/admission`, `apps/bench`, `apps/interpretation`, `apps/acquisition`, `apps/control-plane`; webapp `npm test` + `npx tsc -b --pretty false`.
- [ ] T034 Grep consumer check (FR-008): each new module referenced by a live consumer (pipeline/API/UI) — not dead code; run `quickstart.md` scenarios.
- [ ] T035 Close out `checklists/requirements.md` and mark all tasks `[x]` in review gate; update `tasks.md` final status.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1**: No dependencies.
- **Phase 2**: Depends on T002 (topics). BLOCKS US1, US3, US4, US6.
- **US1**: after Phase 2.
- **US2**: after Phase 2 (independent of US1).
- **US6 (UI)**: after Phase 2 (vitni review model needs knowledge-model shapes conceptually; pure logic can start after T006 shape).
- **US3, US4, US5**: after Phase 2; mutually independent.
- **Phase 9**: after all user stories.

### User Story Dependencies

- US2 ↔ US6: US6 review queue consumes candidate/assertion data shapes from US2; the UI slice (T017-T018, porting pure logic) can precede wiring (T019-T020).
- US1 → US3: parsers emit Statements via the canonical model.
- US2, US4, US5: independent of each other.

### Parallel Opportunities

- T003/T004/T005/T007 ([P]) in parallel.
- US2, US3, US4, US5 phases can run in parallel after Phase 2.
- T017/T018 ([P]) parallel; T025/T027 ([P]) parallel.
- Phase 9 audit tasks ([P]) parallel.

## Parallel Example: Phase 2 Foundational

```bash
# Launch all domain models together:
Task: "Create schema.py registry" (T003)
Task: "Create property.py" (T004)
Task: "Create entity.py" (T005)
Task: "Create statement.py canonical" (T006)
Task: "Domain unit tests" (T007)
```

---

## Implementation Strategy

### MVP First (US1)

1. Phase 1 (baseline + topics) → Phase 2 (domain core + tests) → **checkpoint**.
2. Phase 3 US1 (admission adaptation + consumer test) → **STOP and VALIDATE** (MVP: canonical knowledge model in the executable path).
3. Then US2, US6, US3, US4, US5 incrementally, each validated independently.
4. Phase 9 polish + full regression.

### Incremental Delivery

- Each phase ends at a green checkpoint (commands listed per phase).
- Regression gates never drop below baseline (shared 144 / admission 41 / bench 20 / webapp 43).
- After every phase, ruff + (for webapp) tsc/vitest clean.

### Parallel Team Strategy

Not applicable (single worker); phases executed sequentially; [P]-marked tasks batched.

---

## Notes

- Tests are required by spec FR-003 (each adapted module ships unit tests) — included in every phase.
- Attribution headers per FR-001; license gate per FR-005/FR-012 (no PANO/reNgine/kipi code).
- Keep event payloads refs-only (I-5); all new records emit envelopes (I-12).
- Commit after each phase checkpoint.
