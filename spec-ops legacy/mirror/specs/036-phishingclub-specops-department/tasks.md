# Tasks: Phishing Club SpecOps Department — Full Red-Team

> **Revision 2026-11-02**: this task list records the original lab-isolated
> implementation order. The completed implementation removes the lab-only boundary,
> allowlist, ADR-0040/Amendment 2.1.0 gate and unverified-donor block; see `spec.md`.

**Input**: `specs/036-phishingclub-specops-department/` (spec.md, plan.md, research.md, data-model.md, contracts/)

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/specops-lab-api.md

**Tests**: Included — the spec's SC-001..SC-012 make tests part of the deliverable.

**Organization**: Foundational lab boundary and governance first; then user stories in
priority order. Each story is independently testable through the engine or router.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [ ] T001 Create `apps/specops/lab/` package skeleton with `__init__.py`, `models.py`, `audit.py`, `boundary.py`, `artifacts.py`, `engine.py`, `readiness.py`, `governance.py`
- [ ] T002 [P] Add `apps/specops/tests/test_lab_engine.py` and `apps/specops/tests/test_specops_lab_router.py` skeletons with an isolated engagement-dir fixture
- [ ] T003 [P] Add `apps/webapp/src/lab/` directory and test skeleton

## Phase 2: Foundational (blocking)

**Purpose**: The lab boundary, audit chain and governance gate every story depends on.

- [ ] T004 [P] Implement closed enums + dataclasses in `apps/specops/lab/models.py` (LabStatus, CampaignState, SessionState, ArtifactKind, Campaign, Template, Sender, AitmSession, Artifact, Assessment, ReportFigure, Report, AuditEvent)
- [ ] T005 Implement append-only SHA-256 hash-chained audit log in `apps/specops/lab/audit.py` with `append()` and `verify()`
- [ ] T006 Implement `apps/specops/lab/governance.py`: `ratified()` reads `docs/adr/ADR-0040-lab-only-red-team-exception.md` and constitution amendment `2.1.0`; `blockers()` names each missing artefact
- [ ] T007 Implement `apps/specops/lab/boundary.py`: target allowlist, lab-identity validation, `check_egress()`, `kill_switch()`, `reset()`, `teardown()`, `status()`
- [ ] T008 Implement `apps/specops/lab/artifacts.py`: AES-256-GCM encrypt/decrypt, redacted preview, retention sweep, metadata-only view
- [ ] T009 Implement `apps/specops/lab/readiness.py`: capability matrix, donor registry read, governance state, encryption key source, named blockers
- [ ] T010 Wire `apps/specops/lab/__init__.py` public surface (`LAB`, `BOUNDARY`, `AUDIT`, engine accessors, errors)

**Checkpoint**: `python -c "from specops.lab import LAB"` succeeds; boundary/audit/governance unit tests pass.

---

## Phase 3: User Story 1 — One lab-isolated department surface (P1) 🎯 MVP

**Goal**: One canvas, eight panels, persistent banner, readiness and named absences.

- [ ] T011 [US1] Implement `GET /api/v1/specops/lab` overview in `apps/control-plane/api/routes/specops_lab.py` (lab + readiness + collections + audit)
- [ ] T012 [US1] Mount `specops_lab.router` in `apps/control-plane/api/main.py`
- [ ] T013 [P] [US1] Add lab wire types + `labOverview()` to `apps/webapp/src/lib/api.ts`
- [ ] T014 [P] [US1] Build `apps/webapp/src/lab/LabCanvas.tsx` with eight tabs and the persistent banner
- [ ] T015 [P] [US1] Build `apps/webapp/src/lab/panels/labParts.tsx` (scope header, named absence, refusal/status chips)
- [ ] T016 [US1] Build `apps/webapp/src/lab/panels/LabControlPanel.tsx` (readiness matrix, kill switch, teardown, reset, audit)
- [ ] T017 [US1] Add `/specops/lab` route in `apps/webapp/src/App.tsx`, nav entry + breadcrumb in `apps/webapp/src/shell/nav.ts`
- [ ] T018 [US1] Router test: overview envelope, `scope=lab-only`, donor blocker named, cross-tenant isolation
- [ ] T019 [US1] UI test: banner, panel switch, named absence when overview fails

**Checkpoint**: `/specops/lab` renders all panels; stopping the overview shows a named absence, not zeros.

---

## Phase 4: User Story 2 — Campaign authoring and RoE-gated launch (P1)

**Goal**: Lab-only roster, template/sender validation, RoE gate, funnel from evidence.

- [ ] T020 [US2] Implement template catalog + sender profiles in `apps/specops/lab/engine.py` with lab-identity/asset validation
- [ ] T021 [US2] Implement campaign create/launch/read in `engine.py`; append engagement events on launch; derive funnel
- [ ] T022 [US2] Add `POST/GET /specops/lab/campaigns`, launch, templates and senders endpoints in `specops_lab.py` with `409/422/424` mapping
- [ ] T023 [P] [US2] Add `api.ts` methods and wire types (`labCreateCampaign`, `labLaunchCampaign`, `labCreateTemplate`, `labCreateSender`)
- [ ] T024 [P] [US2] Build `CampaignsPanel.tsx` and `CatalogPanel.tsx`
- [ ] T025 [US2] Engine tests: no RoE → refusal; non-lab roster → refusal; launch → funnel derived; duplicate recipient refused
- [ ] T026 [US2] Router test: 409/422/424 + captured-credentials count 0
- [ ] T027 [US2] UI test: create then launch, refusal reason rendered verbatim

**Checkpoint**: A lab campaign runs end-to-end and every funnel number traces to engagement events.

---

## Phase 5: User Story 3 — AiTM / remote-browser session (P1)

**Goal**: Full-tier session, encrypted artifacts, redaction, retention, access audit, kill switch.

- [ ] T028 [US3] Implement AiTM start/capture/stop in `engine.py`, gated by RoE + allowlist + `governance.ratified()`
- [ ] T029 [US3] Implement retention sweep and artifact metadata access in `engine.py` / `artifacts.py`
- [ ] T030 [US3] Add `/aitm/sessions` + `/capture` + `/stop` endpoints in `specops_lab.py`
- [ ] T031 [P] [US3] Add `api.ts` session/artifact methods and wire types
- [ ] T032 [P] [US3] Build `AitmPanel.tsx` with target/mode form, redacted artifact list, stop and kill-switch actions
- [ ] T033 [US3] Engine tests: non-allowlisted target refused; ciphertext ≠ plaintext; redacted preview; access audit; retention purge keeps count
- [ ] T034 [US3] Router test: no raw secret anywhere in response/report/audit; cross-tenant 404
- [ ] T035 [US3] UI test: capture shows redacted preview only; stop/kill switch states

**Checkpoint**: Full-tier capture works only inside the lab and never emits a raw secret.

---

## Phase 6: User Story 4 — Caldera/AEL operation + assessment link (P1)

**Goal**: Reuse the emulation spine under the same gate; link campaign ↔ operation.

- [ ] T036 [US4] Add lab operation launch (delegating to `specops.emulation`) and assessment link in `engine.py` / `specops_lab.py`
- [ ] T037 [P] [US4] Add `api.ts` operation/assessment methods
- [ ] T038 [P] [US4] Build `OperationsLabPanel.tsx` (planned/executed abilities, technique coverage, link control)
- [ ] T039 [US4] Engine/router tests: operation blocked without RoE/non-lab target; assessment preserves separate evidence
- [ ] T040 [US4] UI test: operation panel names plan/donor and links a campaign

---

## Phase 7: User Story 5 + 6 — Catalog and engagement/training separation (P2)

- [ ] T041 [US5] Template import preview, external asset refusal, sender readiness missing[] in `engine.py`
- [ ] T042 [US5] UI: template stage preview + sender readiness; external URL refusal shown verbatim
- [ ] T043 [US6] Build `EngagementLabPanel.tsx` over `GET /specops/engagement/board`; keep training block separate; pseudonym-only subjects
- [ ] T044 [US6] Engine/router tests: training not summed into funnel; anonymisation preserves counts; stable pseudonyms
- [ ] T045 [US6] UI test: training and phishing are separate blocks; subjects show pseudonyms

---

## Phase 8: User Story 7 + 8 — Reports and lab lifecycle (P2/P3)

- [ ] T046 [US7] Implement report generation/export in `engine.py` with per-figure status/lineage and no raw secrets
- [ ] T047 [US7] Add report endpoints in `specops_lab.py`
- [ ] T048 [P] [US7] Build `ReportsPanel.tsx` with figure table, limitations, provenance, export
- [ ] T049 [US7] Tests: unavailable figure is `null` + named instrumentation; lineage check; export has no secret
- [ ] T050 [US8] Implement kill switch, teardown, reset, preserved-evidence counts in `engine.py` / `specops_lab.py`
- [ ] T051 [US8] Tests: kill switch stops sessions/campaigns; teardown deletes nothing; reset does not clear evidence
- [ ] T052 [US8] UI test: kill switch reaches stopped state; readiness blockers named

---

## Phase 9: Governance, documentation, verification

- [ ] T053 Write `docs/adr/ADR-0040-lab-only-red-team-exception.md` (accepted, lab-only scope, time bound 2026-11-01..2027-11-01, revocation, enforcement)
- [ ] T054 Amend `apps/../.specify/memory/constitution.md` to 2.1.0 with the scoped lab exception; update version/amendment log
- [ ] T055 [P] Add `donors/phishingclub/ATTRIBUTION.md` (AGPL-3.0, source offer, lab-only, no warranty)
- [ ] T056 [P] Add `docs/adr/WAVE-000-index.md` entry for ADR-0040
- [ ] T057 Run targeted pytest, full `apps/specops/tests`, webapp `npm test -- --run src/lab`, `npm run build`, `npm run lint`
- [ ] T058 Regenerate `docs/platform/` with `python -m platform_model.build` and pass `--check`
- [ ] T059 Update `apps/webapp/src/shell/TopNav.test.tsx` / nav tests for the new destination
- [ ] T060 Report pass/fail/blocked per command; do not mark a blocked command as pass

---

## Dependencies

- **Foundational**: T004–T010 block all stories.
- **US1**: T011–T019; T014 depends on T013.
- **US2**: T020–T027; depends on US1's engine/overview scaffolding.
- **US3**: T028–T035; depends on T005, T008, T028.
- **US4**: T036–T040; depends on existing `specops.emulation` and US2's campaign store.
- **US5/US6**: T041–T045; can run after US2.
- **US7/US8**: T046–T052; depends on US2/US3/US4 evidence.
- **Governance**: T053/T054 before T028's runtime enablement is exercised; T055 can run in parallel.
- **Verification**: T057–T060 after all implementation tasks.

## Parallel opportunities

- T002/T003 skeletons, T004 models, T013/T014/T015, T023/T024, T031/T032, T037/T038, T048, T055/T056.
- Tests can be written before their implementation task in each story; keep the red step.

## Implementation strategy

1. Foundational boundary + audit + governance + encryption (T004–T010).
2. US1 overview/router/canvas (MVP).
3. US2 campaign vertical slice (author → RoE → launch → funnel).
4. US3 capture vertical slice (start → capture → redact → audit → stop).
5. US4 operation link, then P2/P3 panels.
6. Governance artefacts before exercising the full tier.
7. Gates: targeted pytest, full specops suite, UI test, build, lint, model drift.
