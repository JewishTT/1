# Tasks: Full Donor Coverage

**Input**: Design documents from `/specs/004-donor-coverage-complete/`

**Prerequisites**: plan.md (required), spec.md (required for user stories)

**Tests**: Explicit test tasks included per feature requirement (FR-003).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P] [Story] Description`

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: No new packages — the `apps/shared/donor` package and `apps/webapp/src/lib/donor` already exist from track 003. This phase only extends re-exports.

- [x] **T001** [P] [All] Extend `apps/shared/donor/__init__.py`: re-export temp「temporal + target」adders, refresh attribution header (7 allowed donors). Add stub-free — only after modules exist (final edit in T013).

## Phase 2: US1 — Temporal conflict detection (investigator, MIT)

**Purpose**: Detects contradictory date evidence from stored data, surfaced via graph export summary + bench.

- [x] **T002** [P] [US1] Implement `apps/shared/donor/temporal.py` — adapt `investigator/graph/temporal_consistency.py` + date primitives from `investigator/graph/dedup.py`; stdlib only; renamed public API; attribution header (investigator, MIT, what-changed).
- [x] **T003** [P] [US1] Unit tests `apps/shared/tests/unit/donor/test_temporal.py` — spread conflict, ordering conflict, year-only no-op, `dates_compatible` windows, `to_iso_date` (RFC-2822/GDELT/ISO).
- [x] **T004** [US1] Integrate into `apps/admission/resolution/collective.py`: `CorrelationService.export_graph(..., conflict_days=30)` adds `conflicts` to summary via `donor.temporal.scan` over edge `observed_dates`/`event_followed_by`. Extend `apps/admission/tests/test_collective_export.py`.

## Phase 3: US2 — Target normalization (SpiderFoot, MIT logic)

- [x] **T005** [P] [US2] Implement `apps/shared/donor/target.py` — adapt `spiderfoot/target.py`, rewrite netaddr→stdlib `ipaddress`/`ip_network`, strip logging; attribution header.
- [x] **T006** [P] [US2] Unit tests `apps/shared/tests/unit/donor/test_target.py` — domain/email/IPv4/IPv6/URL classification + normalization, invalid input rejection, alias registry.

## Phase 4: US3 — Link kind styling (kafSIEM, Apache-2.0)

- [x] **T007** [P] [US3] Implement `apps/webapp/src/lib/donor/links.ts` + `links.test.ts` — pure link-kind → label/color/class mappings (adapted from `src/lib/severity.ts` + `src/lib/incident-links.ts`), safe defaults, no Tailwind.
- [x] **T008** [US3] Integrate into `apps/webapp/src/components/GraphPanel.tsx` — edge label/color from link kind; extend webapp test.

## Phase 5: US4 — Confidence + relationship typing (vitni, Apache-2.0)

- [x] **T009** [P] [US4] Implement `apps/webapp/src/lib/donor/confidence.ts` + `confidence.test.ts`, `apps/webapp/src/lib/donor/relationshipTypes.ts` + `relationshipTypes.test.ts` — drop react-icons, theme-agnostic colors, lookup with default.
- [x] **T010** [US4] Integrate into `apps/webapp/src/components/LineageWalker.tsx` (confidence badges) and `GraphPanel.tsx` (relationship labels); extend webapp tests.

## Phase 6: Bench + finalization

- [x] **T011** [US1+US2] Extend `bench/bench/harness.py` `bench_donor`: temporal `scan` latency + correctness metric; target classification/normalization latency + correctness; update `bench/tests/test_harness.py`.
- [x] **T012** [P] [All] Final `apps/shared/donor/__init__.py` re-export of `temporal` + `target`; attribution header updated.
- [x] **T013** [All] Validation gate: ruff on all touched Python; shared/admission/bench suites; webapp vitest + tsc; grep-verify consumers; mark all tasks `[x]`; review gate passed.