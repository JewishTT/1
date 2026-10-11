# Implementation Plan: CI/SpecOps Department Fabric

**Branch**: `027-ci-specops-fabric` | **Date**: 2026-10-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/027-ci-specops-fabric/spec.md`

## Summary

Build the Counterintelligence & Special Operations department as **one unified fabric** in the webapp: a `CICanvas` host (mirroring `OpsCanvas`) exposing internal panels — Operations, Kill-chain Emulation, Phishing/SAT, APT Forensics, Detection Coverage, Counterintelligence, Social-Reaction. Donor capabilities are integrated **directly and wholly** (vendored modules/services + isolated lab services), made working first; isolation, licensing and forensic hardening are deferred. Kill-chain emulation (caldera + ael/adversary_emulation_library) and phishing/SAT (PhishSlayer + PIDSF RoE-gate pattern) are the mandatory P1 pillars, gated by a rules-of-engagement sign-off enforced server-side. The approach reuses the platform's evidence substrate, closed status vocabulary, named-absence convention and the existing `src/ops/` panel pattern.

## Technical Context

**Language/Version**: TypeScript 5.5 (frontend), Python 3.11 (control-plane/donor services), Rust unchanged

**Primary Dependencies**: React 18 + Vite + TanStack Query + zustand + cytoscape + echarts (webapp); FastAPI (control-plane routers); integrated donors — caldera, ael, adversary_emulation_library, sticks, PhishSlayer, PIDSF (RoE pattern), SPEAR (P2), cognitive/social-sim operators (P2)

**Storage**: PostgreSQL (campaign/operation/RoE state), existing S3 evidence substrate + Kafka event stream; donor lab services keep their own stores behind a process boundary

**Testing**: pytest (routers, RoE gate, named-absence, unknown-status); vitest + Testing Library (panels); guarding test per vendored donor with attribution header

**Target Platform**: Linux server (control-plane + lab containers via docker-compose), browser SPA

**Project Type**: Web application (frontend panel set + backend routers + isolated donor lab services)

**Performance Goals**: live emulation ability state visible within one poll interval; panels render subject within one interaction (SC-001)

**Constraints**: lab-only targets; RoE gate blocks sends (0 unauthorized, SC-003); no credentials stored; named-absence for unserved fields (no fake zeros); unknown status → `Unknown`

**Scale/Scope**: ~7 panels, ~6 control-plane routers, ~4 vendored/isolated donors in wave 1 (caldera, ael/adversary_emulation_library, PhishSlayer, sticks)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **§I Observation-Immutable / §II Evidence-First**: emulation/simulation results recorded as observations and asserted as claims with evidence refs; nothing downstream edits an observation. → **PASS** (FR-007/FR-016).
- **§III Projection-First / Domain Invariant 12**: panels are rebuildable projections; donor failure never destroys evidence. → **PASS** (FR-016).
- **§IV No Single Store/Score**: no single donor score equates to truth; invariants carry separate confidence + evidence. → **PASS**.
- **§V Plugability by Contract**: donors reached behind FastAPI routers / proxy contracts; no vendor classes in domain logic. → **PASS**.
- **§VI Process-Centric**: department is a view within the investigation workspace, not a peer product. → **PASS** (FR-015, research D1).
- **§VII Security-First**: lab-only targets; RoE gate; no credential capture; engine ships no access-control bypass. Full egress/sandbox hardening deferred by owner decision but RoE + lab-only ship now. → **PASS with noted deferral** (FR-014, research D6).
- **Donor reuse is the default**: direct wholesale integration; donor defects repaired on transfer. → **PASS** (FR-003).
- **No MVP/mini-architecture**: contracts of the planes are respected; components introduced incrementally without breaking domain/event contracts. → **PASS**.

**Gate result: PASS.** No unjustified violations. The one deferral (full isolation/licensing hardening) is an explicit owner decision recorded in Assumptions and is bounded by the RoE gate + lab-only targeting that do ship.


## Project Structure

### Documentation (this feature)

```text
specs/027-ci-specops-fabric/
├── plan.md              # This file
├── research.md          # Phase 0 output (D1–D6)
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── specops-api.md   # Phase 1 output (/api/v1/specops/*)
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (repository root)

```text
apps/webapp/src/
├── ci/
│   ├── CICanvas.tsx           # host: one canvas, internal panel tabs (mirrors ops/OpsCanvas)
│   ├── ci.css
│   ├── types.ts               # panel row vocabulary + Unavailable named-absence type
│   ├── model.ts               # pure derivations: plans→rows, ops→abilities, campaign→metrics
│   ├── useCiState.ts          # TanStack Query hooks per panel (named-absence missing[])
│   ├── panels/
│   │   ├── EmulationPanel.tsx     # kill-chain: plans, launch, live abilities (cytoscape)
│   │   ├── PhishingPanel.tsx      # SAT: roster, RoE gate, metrics
│   │   ├── ForensicsPanel.tsx     # expected vs actual, gaps, coverage heatmap (echarts)
│   │   ├── CounterintelPanel.tsx  # subject invariants + relation graph
│   │   ├── SocialPanel.tsx        # reaction trajectories + phase-transition risk
│   │   └── OperationsPanel.tsx    # re-export/absorb existing ops surface
│   └── *.test.tsx
├── shell/nav.ts                # add CI/SpecOps sections + titles
└── App.tsx                     # mount CI view in workspace switcher

apps/control-plane/api/routes/
├── specops_emulation.py     # /api/v1/specops/emulation/*
├── specops_phishing.py      # /api/v1/specops/phishing/*  (RoE gate server-side)
├── specops_counterintel.py  # /api/v1/specops/counterintel/*
├── specops_social.py        # /api/v1/specops/social/*
├── specops_forensics.py     # /api/v1/specops/forensics/*
└── specops_roe.py           # /api/v1/specops/roe  (sign-off)
apps/control-plane/api/main.py  # mount the six routers

apps/specops/
├── vendor/
│   ├── caldera/                 # Apache-2.0, attribution header
│   ├── ael/                     # Apache-2.0 plan YAML
│   ├── adversary_emulation_library/
│   └── sticks/                  # sufficiency metric + lab fixture
└── roe/
    └── gate.py                  # RoEError / RosterError / capture_passwords=False (PIDSF pattern)

deploy/specops/lab/
└── docker-compose.yml           # caldera core, PhishSlayer lab, target fixture (isolated)

apps/control-plane/tests/
└── test_specops_*.py            # routers, RoE gate, named-absence, unknown-status
```

**Structure Decision**: Web application layout (frontend `apps/webapp/src/ci/` + backend `apps/control-plane/api/routes/specops_*.py` + vendored/isolated donors under `apps/specops/` and `deploy/specops/lab/`). Mirrors the proven `src/ops/` module and the `main.py` router-mount pattern; no new top-level app, no new shell.

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Deferred full isolation/licensing hardening (owner-directed) | "Make it work first" — direct wholesale donor integration this phase | Bounded by RoE gate + lab-only targets that DO ship; phishing is unsafe without the gate, so the gate is in wave 1, only broader egress/sandbox/license reconciliation is deferred |
