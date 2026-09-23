# Tasks: Temporal Entity Materialization

**Input**: Design documents from `specs/014-temporal-materialization/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

## Phase 1: Setup

- [x] T001 [P] Add shared temporal materialization domain contracts and frozen dataclasses in `apps/shared/domain/temporal_materialization.py`.
- [x] T002 [P] Add canonical hashing, window/revision/publication fingerprints, and empty/dormant handling in `apps/shared/domain/temporal_materialization.py`.
- [x] T003 [P] Add unit-test scaffolding for deterministic windows, source cuts, revisions, and idempotent replay in `apps/shared/tests/unit/domain/test_temporal_materialization.py`.

## Phase 2: Foundational

- [x] T004 [P] Implement pure materialization engine over accepted entity stream records in `apps/shared/domain/temporal_materialization.py`.
- [x] T005 [P] Implement temporal window projection and aligned feature records with explicit unavailable values in `apps/shared/domain/temporal_materialization.py`.
- [x] T006 [P] Implement source-cut sealing, late-event dependency revision, and staged publication candidates in `apps/shared/domain/temporal_materialization.py`.
- [x] T007 [P] Add contracts and tests for tenant isolation, source provenance, and structural-only feature output in `apps/shared/tests/unit/domain/test_temporal_materialization.py`.
- [x] T008 [P] Add PostgreSQL repository and migration for runs, source cuts, window revisions, publications, and audit records in `apps/control-plane/db/`.
- [x] T009 [P] Add ClickHouse append-only feature-series storage with explicit projection generation in `apps/projection/temporal_materialization/`.
- [x] T010 [P] Add idempotent event consumer and Temporal rebuild workflow bindings in `apps/projection/temporal_materialization/`.
- [x] T011 [P] Add operational health, quarantine, retry/backpressure, and reconciliation services in `apps/projection/temporal_materialization/`.
- [x] T012 [P] Add FastAPI current/history/features/health/audit/rebuild routes in `apps/control-plane/api/routes/`.
- [ ] T013 [P] Add frontend timeline, point-in-time, source-cut, revision, and provenance view in `apps/webapp/src/`.
- [x] T014 [P] Add integration tests for publication atomicity, failure recovery, replay equality, and tenant isolation in `apps/shared/tests/contract/` and `apps/control-plane/tests/`.
- [x] T015 Run `uv run pytest` for the affected shared/domain/control-plane/projection suites.

## Phase 3: User Story 1 Р Р†Р вЂљРІР‚Сњ Timeline and point-in-time views (P1)

- [x] T016 [US1] Implement timeline/current/point-in-time materialization queries backed by the publication head.
- [x] T017 [US1] Implement explicit dormant windows, source-cut visibility, and last-valid-publication fallback.
- [x] T018 [US1] Add user-story tests for complete timelines, gaps, point-in-time consistency, and deterministic rebuilds.

## Phase 4: User Story 2 Р Р†Р вЂљРІР‚Сњ Late evidence and safe revisions (P1)

- [ ] T019 [US2] Implement late-event revision dependency tracking and immutable window revision publication.
- [ ] T020 [US2] Implement exact duplicate no-op, contradiction quarantine, interrupted rebuild resume, and audit decisions.
- [ ] T021 [US2] Add user-story tests for late events, duplicate delivery, contradictions, and resume equality.

## Phase 5: User Story 3 Р Р†Р вЂљРІР‚Сњ Aligned feature series (P2)

- [x] T022 [US3] Implement lifecycle/activity/relationship feature records aligned one-to-one with temporal windows.
- [x] T023 [US3] Implement unavailable-vs-zero semantics, structural-only labels, and source-cut provenance.
- [x] T024 [US3] Add user-story tests for feature alignment, insufficient data, and traceable structural values.

## Phase 6: User Story 4 Р Р†Р вЂљРІР‚Сњ Operations and audit (P2)

- [x] T025 [US4] Implement health/current/rebuilding/degraded/quarantined status projections.
- [x] T026 [US4] Implement tenant-safe audit access, bounded retries, backpressure, and run reconciliation controls.
- [x] T027 [US4] Add operator tests for visible health, audited changes, tenant isolation, and load protection.

## Phase 7: Polish and validation

- [ ] T028 Run the feature quickstart validation in `specs/014-temporal-materialization/quickstart.md`.
- [ ] T029 Run full affected Python tests and frontend typecheck/tests.
- [ ] T030 Verify no raw evidence mutation, no timeless temporal relations, no unbounded retry/backlog behavior, and mark tasks complete only after validation.