# Wave 0 — Architecture Freeze: index

**Feature**: `025-context-reality-approximation-engine` · **Closed**: 2026-10-04
**Gate**: baseline v2 §55 — *no unresolved contradiction between 024 and 025 terminology **and
lifecycles*; ADR 01–12 accepted; §47.4 targets ratified.*

| ADR-025 | Record | File | Status |
|---|---|---|---|
| `ADR-025-01` | Context Engine placement + context/definition identity | [0028](0028-context-definition-identity-and-placement.md) | Accepted |
| `ADR-025-02` | Epistemic algebra — Belnap support, truth vs score | [0029](0029-epistemic-algebra-belnap.md) | Accepted |
| `ADR-025-03` | Revision, determinism and replay contract | [0030](0030-revision-determinism-replay.md) | Accepted |
| `ADR-025-04` | Locality boundary — pair and triple coherence | [0031](0031-locality-pair-triple-coherence.md) | Accepted |
| `ADR-025-05` | Hypothesis lifecycle and hypothesis space | [0032](0032-hypothesis-lifecycle-and-space.md) | Accepted |
| `ADR-025-06` | Reasoning operator contract | [0033](0033-reasoning-operator-contract.md) | Accepted |
| `ADR-025-07` | Global-search completeness semantics | [0034](0034-global-search-completeness.md) | Accepted |
| `ADR-025-08` | Temporal algebra — 13 Allen relations | [0035](0035-temporal-algebra-allen.md) | Accepted |
| `ADR-025-09` | Evidence independence and coverage-qualified absence | [0036](0036-evidence-independence-and-absence.md) | Accepted |
| `ADR-025-10` | Ranking policy — no multiplicative utility | [0037](0037-ranking-policy-no-multiplicative-utility.md) | Accepted |
| `ADR-025-11` | Branches and analyst-in-the-loop | [0038](0038-branches-and-analyst-in-the-loop.md) | Accepted |
| `ADR-025-12` | Retention, erasure and permissible inference | [0039](0039-retention-erasure-and-inference-policy.md) | Accepted |

**All 12 accepted. `T025-154` discharged. Wave 0 is closed.**

## 024 conflicts found and resolved

Per the v2 conflict rule — *024 wins on already-approved semantics; amend 025*:

| # | Conflict | Resolution |
|---|---|---|
| 1 | Context identity namespace | ADR-0028: `CXI-` = InvestigationContext, `CXD-` = ContextDefinition. 024 untouched except one additive `definition_ref`. |
| 2 | Placement `cp_domain/context_engine/` | ADR-0028: canonical path is `apps/control-plane/context_engine/`. §1.2 superseded by verified topology. |
| 3 | Obligation lifecycle vs frontier readiness vs action state overlapped | ADR-0030/0038 + §21.1: three orthogonal fields. 024 names win where they collide; to be reconciled verbatim in Phase L. |
| 4 | `REPLAYED` was a revision status | ADR-0030: not a status. Replay is a run mode emitting `ReplayReport`. |
| 5 | `STRENGTHENED`/`WEAKENED` were hypothesis states | ADR-0032: derived `trend`. |
| 6 | Prefix `OBS-` meant both Obstruction and Observation | v2 fixed: `OBST-` for obstruction. No decision needed. |

## Still open (not blocking Wave 0)

- **§47.4 targets ratified into deployment config** — a config act, not an ADR.
- **`.specify/memory/constitution.md` is still an unmodified template** (research R8). The real
  doctrine is `AGENTS.md` plus the invariants in `spec.md`. Needs an owner decision on whether
  the constitution is generated from `AGENTS.md`.

## What Wave 0 does *not* deliver

It delivers decisions, not capability. Nothing in the platform runs differently because these
twelve documents exist. The critical path to a working slice is unchanged and still starts at
Phase A → B → **2S Slice-0**.