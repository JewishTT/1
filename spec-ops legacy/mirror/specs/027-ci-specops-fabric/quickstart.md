# Quickstart & Validation: CI/SpecOps Department Fabric

**Feature**: `027-ci-specops-fabric` | **Date**: 2026-10-10

Runnable validation scenarios proving the feature works end-to-end. Contract shapes: [`contracts/specops-api.md`](./contracts/specops-api.md). Entities: [`data-model.md`](./data-model.md).

## Prerequisites
- Lab fixtures up: `docker compose -f deploy/specops/lab/docker-compose.yml up -d` (caldera core, PhishSlayer lab, target fixture).
- Control plane running (`apps/control-plane`, FastAPI on :8000) with the new `specops_*` routers mounted.
- Webapp dev server (`apps/webapp`, Vite on :5173).

## Scenario 1 — Department shell (US1)
1. Open the workspace, switch to the SpecOps module, open the CI/SpecOps department.
2. **Expect**: one canvas, a tab per panel (Operations · Emulation · Phishing · Forensics · Detection · Counterintel · Social), and a persistent scope note.
3. Switch tabs; return. **Expect**: each panel renders its subject; prior selection preserved.
4. Stop a donor service (e.g. PhishSlayer). Open its panel. **Expect**: named absence with the source name — no blank pane, no zero.

## Scenario 2 — Kill-chain emulation (US2, mandatory)
1. `GET /api/v1/specops/emulation/plans` → pick a micro plan (ael/adversary_emulation_library).
2. `GET .../plans/{id}` → confirm abilities + expected telemetry listed.
3. `POST .../emulation/operations` **without** `roe_id` → **Expect** `409 RoEError`, nothing launched.
4. Record RoE: `POST /api/v1/specops/roe` → then launch with `roe_id` → **Expect** `state: running`.
5. Poll `GET .../operations/{id}` → **Expect** abilities move `planned → executed` live; beacons/pivots populate.
6. Freeze/inspect → **Expect** per-ability technique, target, expected telemetry.

## Scenario 3 — Phishing / SAT under RoE gate (US3, mandatory)
1. `POST /api/v1/specops/phishing/campaigns` with an approved roster.
2. `POST .../launch` without RoE → **Expect** `409 RoEError`, nothing sent.
3. Add an out-of-roster target, launch with RoE → **Expect** `422 RosterError`, out-of-roster rejected before send.
4. Launch in-roster with RoE → **Expect** `state: sending → complete`, engagement metrics present.
5. Inspect any recipient submission → **Expect** `captured_credentials_count: 0` (never stored).

## Scenario 4 — Counterintelligence board (US4)
1. `GET /api/v1/specops/counterintel/subjects/{id}` for a subject with known evidence.
2. **Expect**: each invariant shows `evidence_refs` and `supported: true`; the relation graph renders.
3. A subject whose invariant has no evidence → **Expect** `supported: false`, rendered as unsupported.

## Scenario 5 — Social-reaction projection (US5)
1. `POST /api/v1/specops/social/projections` with a population + narrative + horizon.
2. **Expect**: reach/polarization trajectories over the horizon; `phase_transition_risk` with `threshold_crossed` when applicable; artifacts inspectable.
3. Tiny/sparse population → **Expect** `confidence: "low"`, not a confident curve.

## Scenario 6 — APT forensics (US6)
1. Complete an emulation run (Scenario 2), then `GET /api/v1/specops/forensics/operations/{id}`.
2. **Expect**: expected vs actual per ability; unmatched items listed in `gaps`; ATT&CK coverage heatmap data present.

## Automated gates
- `pytest apps/control-plane/tests/.../test_specops_*.py` — routers, RoE gate (0 unauthorized sends), roster rejection, named-absence, unknown-status → `Unknown`.
- `pnpm -C apps/webapp test` — panel rendering, named-absence, scope label, tab state preservation (mirrors existing `ops` tests).
- Guarding test per vendored donor with attribution header (constitution rev.2).
