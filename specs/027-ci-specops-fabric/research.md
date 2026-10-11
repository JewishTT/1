# Phase 0 Research: CI/SpecOps Department Fabric

**Feature**: `027-ci-specops-fabric` | **Date**: 2026-10-10

Resolves every unknown in the plan's Technical Context and fixes the integration decisions for direct, maximal donor reuse. All decisions favor **running the donor's real code first**, deferring isolation/licensing/hardening (FR-003, SC-007).

## D1 — Where does the department live in the UI?

- **Decision**: A new workspace view `src/ci/` mounted by a `CICanvas.tsx` host (mirrors `src/ops/OpsCanvas.tsx` exactly), reached through the workspace switcher under the existing `specops` module tab. Reuses the shell, tenant, TanStack Query client and status vocabulary.
- **Rationale**: ui-upgrade §1 + constitution §VI make the Investigation the unit of work and surfaces views within it; `OpsCanvas` is the proven pattern for "one canvas, N internal panels, scope-labelled." Duplicating chrome would drift the two shells apart again.
- **Alternatives rejected**: (a) separate peer route `/ci/*` — puts a tenant-wide operator surface outside the investigation, the exact mistake `ops/index.ts` warns about; (b) three separate views — three tabs on one subject where one canvas with panels says "one fabric" (§48).

## D2 — How is each donor integrated "directly and wholly"?

- **Decision**: Two integration shapes, chosen per donor, both run real donor code:
  1. **Vendored module/service** (MIT/BSD/Apache-2.0): donor code vendored under `apps/specops/vendor/<donor>/` with an attribution header, wrapped by a thin FastAPI router under `apps/control-plane/api/routes/specops_*.py` mounted at `/api/v1/specops/*`. Frontend panels call these via TanStack Query hooks (pattern: `useOpsState.ts`).
  2. **Isolated lab service** (GPL/AGPL/personal-use): donor runs as its own container (docker-compose under `deploy/specops/lab/`), reached through a control-plane proxy route that forwards to the donor's own API. Process boundary preserves core purity; still the donor's real functionality.
- **Rationale**: Constitution "Donor reuse is the default, not an exception" + rev.2 integration policy (license chooses the *mechanism*, not whether). Caldera/ael/adversary_emulation_library → shape 1 or plan-data; PhishSlayer/fiercephish/Labyrinth → shape 2.
- **Alternatives rejected**: "concept only / pattern inspiration" — explicitly forbidden by the owner for this phase.

## D3 — Kill-chain emulation (US2, mandatory) — concrete integration

- **Decision**: Integrate **caldera** (Apache-2.0, P1) as the emulation core service; load **ael** + **adversary_emulation_library** (Apache-2.0 YAML) as plan data parsed into a scenario DSL; **sticks** for procedural-sufficiency metric + Caldera lab fixture. The Emulation panel drives caldera's REST API through a `specops_emulation.py` router: list plans → confirm target (RoE) → launch → poll operation abilities (planned vs executed) → freeze/inspect.
- **Rationale**: Caldera already exposes C2 + planners + agents + ability graph + operation matrix (Magma UI pattern) — exactly the US2 acceptance scenarios. Reimplementing an ATT&CK orchestrator would re-walk a path already paid for.
- **Alternatives rejected**: custom lightweight orchestrator — violates FR-003 and loses field-tested planner/agent behavior.


## D4 — Phishing / SAT (US3, mandatory) — concrete integration + RoE gate

- **Decision**: Integrate **PhishSlayer** (GPLv3, P1) as an isolated lab service for CMDB+MCP+LLM hyper-personalized simulation; adopt **PIDSF**'s RoE gate *pattern in code* (not its whole service): `launch_campaign()` raises `RoEError` and never sends without a recorded sign-off; `capture_passwords=False` hardcoded; `validate_target_roster()` accepts only a supervisor-approved list. The Phishing panel and its `specops_phishing.py` router enforce the gate server-side, so the UI cannot bypass it.
- **Rationale**: PIDSF's "safety in code, not UI" is the exact property SC-003 requires (0 unauthorized sends, 0 credentials stored). SPEAR (LIME-adversarial) plugs into the detection-side red-team of our detectors.
- **Alternatives rejected**: UI-only warning — FR-005/SC-003 require the send to be *blocked*, not warned.

## D5 — Counterintelligence board (US4) + social-reaction (US5) + forensics (US6)

- **Decision**: These are P2 and depend on science/interpretation operators, so their panels are built against the existing evidence substrate and wired to operators as they land:
  - **Counterintel**: subject invariants (belief-state, narrative-position, bias-profile, coordination-signature, phase-state) render from science operators (CognitiveAttack, DIMA-OntoToolkit, io-coordinated-replies, IO-detecting) returning **claims**, each carrying evidence refs. Unsupported invariant → rendered as unsupported (FR-008).
  - **Social-reaction**: YuLan-OneSim/posim/silisocs/DualMind/social-oscillation/cognitive_phase_transitions run as science operators; the panel projects trajectories + a phase-transition risk indicator (r_c analog). Population too small → low-confidence (edge case).
  - **Forensics**: expected telemetry comes from the emulation plan (ael/ael-lib), actual from recorded observations; unmatched → Detection Gap (FR-010). Reuses `evidence/lineage` pattern.
- **Rationale**: These are science-heavy; building the panel shell now (D1) and wiring operators incrementally keeps the shell honest while the operators calibrate. No fake numbers (FR-012).
- **Alternatives rejected**: blocking the whole department on P2 science maturity — the shell + US2/US3 deliver value independently.

## D6 — Security / RoE / lab isolation for this phase

- **Decision**: For the "make it work first" phase, emulation + phishing run against **isolated lab fixtures only** (docker-compose lab under `deploy/specops/lab/`). The RoE gate (D4) blocks any send without sign-off. Full network-egress policy, sandboxing and license reconciliation are **deferred** to a later hardening phase by explicit owner decision, but the RoE gate and lab-only targeting ship now because they are what make the capability safe to run at all (FR-014, FR-005).
- **Rationale**: FR-003/SC-007 defer isolation/licensing; but US3's RoE gate is a hard acceptance scenario and is cheap to ship (PIDSF pattern). Shipping phishing without the gate would be unsafe; shipping it *with* the gate is the agreed first slice.
- **Alternatives rejected**: shipping phishing with only a UI warning (unsafe); full egress/sandbox hardening now (explicitly deferred).

## Best practices applied

- **Frontend**: React 18 + TS + Vite + TanStack Query (per-surface query keys, §68) + zustand (UI selection only) + cytoscape (operation graph) + echarts (reaction trajectories). Named-absence `missing[]` arrays on every hook (mirrors `useOpsState.ts`).
- **Backend**: FastAPI routers under `/api/v1/specops/*`; science operators return claims to `/api/science/*`. Composition root tolerant of partial startup (mirrors `main.py` lifespan).
- **Status vocabulary**: reuse `src/ui/status.ts` `WorkStatus`; unknown donor spelling → `Unknown` (FR-011).
- **Testing**: pytest for routers/operators; vitest + Testing Library for panels (mirrors existing `*.test.tsx`). Guarding test per vendored donor with attribution header.
