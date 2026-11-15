# Feature 041 — Implementation plan

## Phase 0 — Preserve current capability

- [x] Create an isolated feature branch.
- [x] Inventory the former apps/specops package from the generated platform model.
- [x] Copy the complete 68-file package and tests to spec-ops legacy/apps/specops.
- [x] Keep a temporary import bridge for the still-mounted API adapters.
- [ ] Archive/migrate remaining API, UI, deployment and feature-spec surfaces in
      separately reviewable slices.

## Phase 1 — Shared boundary

- [x] Define tenant-scoped evidence references and immutable entity/relation snapshots.
- [x] Define a purpose-bound bounded query and IntelligenceReadPort.
- [x] Validate evidence tenant, unique entity IDs, relation endpoints and subject ID.
- [ ] Implement a production read adapter over the existing authoritative evidence and
      projection stores.
- [ ] Add caller authentication/authorization, tenant ACL, budgets, audit events,
      freshness policy and query observability to the serving path.
- [ ] Add versioned schemas and event publication only after payload contracts and
      compatibility policy are reviewed.

## Phase 2 — Economics domain

- [x] Define evidenced economic subjects from Intelligence entities.
- [x] Define financial flows bound to tenant, snapshot, payer/payee, amount/currency,
      timestamp and evidence references.
- [x] Add scope-safe aggregation without implicit FX or inferred values.
- [x] Add domain tests for derived subjects, net flows and endpoint validation.
- [ ] Expand domain entities and typed predicates for corporate ownership, debt,
      trade, investment, payment, market and institutional relationships.
- [ ] Wire economic APIs and analyst UI to the production Intelligence read adapter.
- [ ] Separate internal ingestion cost/capacity telemetry into Operations UI.

## Phase 3 — SpecOps&CI domain

- [x] Define explicit assessment types and a time-bounded authorization model.
- [x] Bind authorization to tenant, snapshot, exact entity roster, approver and approval
      reference.
- [x] Reject expired authorizations and targets absent from the snapshot or roster.
- [x] Add tests for allowed scope and refusal paths.
- [ ] Route existing emulation, lab, forensics, counterintel and engagement services
      through prepare_assessment / the Intelligence read port.
- [ ] Migrate API adapters and UI canvases to the new domain package while preserving
      stable endpoint behavior.
- [ ] Ensure execution workers are isolated, cancellable, egress-restricted and
      evidence-producing; preparation context is not execution authorization by itself.

## Phase 4 — Architecture enforcement and acceptance

- [x] Add a static import-boundary test forbidding domain consumers from importing
      acquisition/recon implementation packages.
- [ ] Regenerate docs/platform through uv run python -m platform_model.build.
- [ ] Run uv run python -m platform_model.build --check.
- [ ] Run focused tests, control-plane tests, full Python suite and UI tests.
- [ ] Run the maintained Playwright screenshot workflows and inspect/fix regressions.
- [ ] Run an end-to-end path: Intelligence investigation → snapshot → Economics analysis.
- [ ] Run an end-to-end path: Intelligence investigation → approved snapshot → RoE-bound
      SpecOps&CI assessment → evidence-backed after-action finding.
- [ ] Remove apps/specops/__init__.py compatibility bridge when all consumers migrate.

## Risks and controls

| Risk | Control |
|---|---|
| Consumers recreate recon through imports | Static import-boundary test and code ownership |
| Snapshot leaks data across tenants | Contract validation plus authorization in production adapter |
| Target scope expands silently | Exact snapshot + approved roster + time-bounded authorization |
| Derived analysis loses provenance | Every output retains snapshot and evidence refs |
| Archive breaks old imports | Temporary bridge; migrate adapters before removal |
| Documentation falsely claims production wiring | Generated model and reachability checks; no claims before end-to-end acceptance |
