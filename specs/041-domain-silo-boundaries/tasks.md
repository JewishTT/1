# Feature 041 — Task ledger

This ledger distinguishes implemented foundation work from outstanding production
integration. Checkboxes describe repository state at this change; no unchecked item is
implied complete by the existence of a package or interface.

## Archived SpecOps foundation
- [x] T001 Inventory all paths under the former apps/specops component.
- [x] T002 Preserve all 68 source and test files under spec-ops legacy/apps/specops.
- [x] T003 Replace the active package body with a temporary import bridge.
- [ ] T004 Migrate mounted API routers and tests to the new domain package.
- [ ] T005 Migrate React canvases, related UI tests and deploy wiring.
- [ ] T006 Retire compatibility bridge after runtime import graph is clear.

## Intelligence contract
- [x] T010 Define evidence reference, entity, relation, snapshot, query and read-port types.
- [x] T011 Enforce tenant/evidence consistency and bounded query depth.
- [ ] T012 Implement production-backed read adapter against authoritative platform stores.
- [ ] T013 Add API authentication, purpose authorization, tenant ACL, budget and audit.
- [ ] T014 Add versioned transport schemas and compatibility tests.

## Economics
- [x] T020 Model economic subjects as projections of Intelligence entities.
- [x] T021 Model evidence-backed financial flows with explicit currency and timestamp.
- [x] T022 Aggregate by entity/currency while enforcing tenant and snapshot scope.
- [ ] T023 Add corporate ownership, market, debt, investment, trade and payment domain models.
- [ ] T024 Wire Economics APIs and UI to the production Intelligence adapter.
- [ ] T025 Separate external Economic Intelligence from platform pipeline economics.

## SpecOps&CI
- [x] T030 Model explicit assessment kinds and engagement authorization.
- [x] T031 Bind the allowed roster to a tenant-scoped Intelligence snapshot.
- [x] T032 Refuse unknown, duplicate, cross-snapshot and out-of-roster targets.
- [ ] T033 Route existing SpecOps service preparation through Intelligence.
- [ ] T034 Bind all existing execution entrypoints to authorization and snapshot references.
- [ ] T035 Migrate counterintelligence, lab, forensics and engagement APIs/UI.

## Enforcement and verification
- [x] T040 Add tests for Intelligence snapshot invariants.
- [x] T041 Add tests for Economics flow aggregation.
- [x] T042 Add tests for SpecOps&CI authorization scope.
- [x] T043 Add AST import-boundary tests prohibiting recon/acquisition imports in consumers.
- [ ] T044 Run tests in CI and fix all failures.
- [ ] T045 Regenerate/check the machine-generated platform model.
- [ ] T046 Execute full-stack, screenshot and cross-silo acceptance paths.
