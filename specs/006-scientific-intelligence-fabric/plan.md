# Implementation Plan: Scientific Intelligence Fabric

**Branch**: `006-scientific-intelligence-fabric` | **Date**: 2026-09-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/006-scientific-intelligence-fabric/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command; its definition describes the execution workflow.

## Summary

Add a first-party **scientific analysis layer** to COGNITIVE that turns raw evidence into
*honest, calibrated, reproducible* claims rather than verdicts. The layer comprises a new
`apps/science` package plus a scientific review UI in the webapp, built on the platform's
existing immutable event substrate (`apps/shared/events`), knowledge model
(`apps/shared/domain`), admission artifacts (`calibration.py`, `temporal.py`,
`evidence/independence.py`), and projection graph/TDA (`apps/projection`). It delivers,
in priority order:

1. **Probabilistic claims with calibration & provenance** (US1) — `ScientificClaim` with a
   declared probability source, an epistemic status, a trace `Claim → EvidenceLink →
   Observation → Raw`, and a calibration harness (observed-vs-expected buckets, Brier, ECE)
   that labels models `OVERCONFIDENT`/`CALIBRATED`. No fabricated probabilities, ever.
2. **Hypothesis management with information gain** (US2) — competing hypotheses with a
   lifecycle, direction-tagged evidence links, discard decisions, expected-information-gain
   collection planning, per-project coverage.
3. **Causal inference with explicit confounder control** (US3) — declared causal models,
   `CORRELATIONAL` vs `CAUSAL` classification, named confounders/assumptions, and a **hard
   scope boundary**: person-level sensitive outcome requests are refused with an audit event.
4. **Temporal dynamics & change detection** (US4) — time-variable claims, change points,
   credence trajectories, versioned reprojection (Supersedes, never mutation).
5. **Network/spectral/higher-order analysis** (US5) — bounded structural analysis with
   normalized scores and permutation-null significance, always structural (never
   person-verdicts).
6. **Robustness, null models, reproducible experiments** (US6) — perturbation studies,
   null/permutation baselines, seeded reproducible experiment registry.
7. **Scientific review UI (evidence ladder)** (US7) — tiered confidence rendering,
   calibration/robustness context, review comments and status transitions, top-rung gated
   on recorded checks.

## Technical Context

**Language/Version**: Python ≥3.11 (uv workspace), TypeScript/React webapp (`apps/webapp`).
Python code must be stdlib + already-wired deps; new statistical dependencies are scoped
and justified (below).

**Primary Dependencies**: New: `apps/science` declares `numpy>=1.26`, `scipy>=1.13`
(already used by `admission`/`projection`) — reused, not duplicated. Optional (only where
the benchmark demands compiled kernels): kept behind the shared graph abstraction; no
vendor classes in domain logic (Constitution V). Webapp: no new runtime deps (React 18 +
existing Vite/vitest/tsc toolchain).

**Storage**: Reuses hermetic in-memory stores pattern from `control-plane/db/schema.py`;
raw objects content-addressed (`storage/s3.py`, sha256). New scientific artifacts
(scientific claims, hypotheses, calibration reports, experiment runs, review events) are
persisted as state rows + emitted as immutable envelopes on Kafka topics registered in
`events/topics.py` (`EVENT_CATALOG`).

**Testing**: `uv run --project apps/science pytest` added; existing suites remain green
(shared ≥144, admission ≥41, projection ≥20, webapp ≥43). Webapp: `npx tsc -b` +
`npm test`. Ruff: `uvx ruff check apps/science apps/webapp`. New markers:
`contract|integration|unit` (root pytest already configures these markers).

**Target Platform**: Linux container deploy; dev on Windows (pwsh). Python ≥3.11 (the
repo baseline), NumPy/SciPy numeric kernels.

**Project Type**: Multi-application Python monorepo; adds the `apps/science` member to the
uv workspace; scientific UI lives in the existing React webapp.

**Performance Goals**: No accidental O(N²) on projection graphs; spectral/motif routines
bounded and benchmarked (SC-006); idempotent re-runs; deterministic seed-respected
reproduction (SC-007).

**Constraints**:
- Hard boundary invariant (FR-007/SC-005): scope rejection at the analysis/API layer with
  an audit event — enforced in code, not by post-hoc review.
- No fabricated probabilities (FR-002): every numeric confidence must be derivable via a
  declared method; else status `UNCERTAIN` with enumerated missing evidence.
- Immutability: claims/hypotheses/experiments/reviews are immutable events; superseding,
  retraction, and discard are recorded links, never deletion (FR-014/FR-015; Constitution
  I/III/12).
- Evidence-first transparency: every claim traces to raw observations (Constitution II).
- Null/robustness honesty: reported significance always carries null parameters and
  permutation counts (FR-010); no bare "significant" labels.
- License gate: `apps/science` is first-party code; donor libraries consulted only for
  best practices (Apache-2.0/MIT compatible), never copied (matches prior tracks' policy).
- Webapp UI mirrors the PANO-licensed pattern policy: patterns only, no copied assets.

**Scale/Scope**: 7 user stories; first-party modules across `apps/science` (claims,
hypotheses, causal, temporal, structure, robustness, experiments, review) + API routes +
webapp science pages + tests. Benchmark harness optional for scale gates.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Invariant | Status | How this plan honors it |
|-----------|--------|-------------------------|
| I-1 Observation immutable | OK | All scientific inputs reference immutable observations/raw; claims never edit them. |
| I-2 Mention != Candidate != Entity | OK | Scientific claims are about structures/processes; person-level outcomes are refused (FR-007); claims never upgrade mentions to entity-verdicts. |
| I-3 Assertion != truth | OK | Claims carry status + model id + distribution; `CONFIRMED` is a scaffolded epistemic state, not truth. |
| I-5 No blobs on Kafka | OK | New events carry refs/manifest chains and JSON payloads; raw stays in S3. |
| I-6 TDA != truth oracle | OK | Structural/spectral outputs are described with null significance, never identity-proofs (US5). |
| I-12 Projections rebuildable | OK | Calibration reports, experiments, claims re-derivable from emitted envelopes + seeds/versions. |
| II Evidence-first | OK | Claim → EvidenceLink → Observation → Raw chain is a first-class field (FR-001). |
| IV No single score | OK | Calibration, robustness, null significance, causal status stored as separate, independently inspectable artifacts. |
| V Plugability by contract | OK | Causal/structure engines are swappable behind declared contracts; spectral kernels behind the shared graph abstraction; no vendor classes in domain logic. |
| VII Security-first | OK | All input untrusted; scope-boundary rejection is an audit event; numeric kernels bounded. |

## Project Structure

### Documentation (this feature)

```text
specs/006-scientific-intelligence-fabric/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
apps/science/                            # NEW first-party package (uv workspace member)
├── claims/
│   ├── model.py                        # ScientificClaim, CredenceDistribution, status enum
│   ├── registry.py                     # claim registration + provenance chain (FR-001/002)
│   └── calibration.py                  # observed-vs-expected, Brier, ECE, verdict (FR-003)
├── hypotheses/
│   ├── model.py                        # Hypothesis lifecycle + EvidenceLink direction
│   ├── evidence.py                     # attach evidence, update credences (via claims)
│   ├── gain.py                         # expected information gain planner (FR-005)
│   └── coverage.py                     # per-project coverage
├── causal/
│   ├── model.py                        # CausalModel (dir graph, confounders, assumptions)
│   ├── infer.py                        # CORRELATIONAL vs CAUSAL classification (FR-006)
│   └── scope.py                        # hard boundary enforcement + audit events (FR-007)
├── temporal/
│   ├── timeseries.py                   # temporal validity, UTC normalization
│   ├── changedetect.py                 # change-point detection
│   └── scenario.py                     # credence trajectories, versioned reprojection
├── structure/
│   ├── spectral.py                     # bounded spectral/centrality, normalized scores
│   ├── motif.py                        # motif/higher-order counts + null significance (FR-009/010)
│   └── graph.py                        # size-aware bounded graph primitives (no O(N²))
├── robustness/
│   ├── perturb.py                      # missing/flipped/subsampled analyses (FR-011)
│   └── report.py                       # flip rates + sensitivity summary
├── experiments/
│   ├── registry.py                     # reproducible run registry (FR-012)
│   └── reproduction.py                 # seed/version pinned re-run + tolerance check
├── review/
│   ├── ladder.py                       # evidence ladder tiers + gating (FR-013)
│   └── events.py                       # review comments + status transitions
├── api/routes/science.py               # FastAPI routes (registered in control-plane)
└── __init__.py

apps/shared/events/topics.py            # ADAPT (small): register science.* topics in EVENT_CATALOG
apps/shared/contracts/                  # REUSE: envelope, manifest chain, scope policy refs
apps/control-plane/api/main.py          # ADAPT (small): include science router
apps/webapp/
├── src/lib/api.ts                      # ADAPT: science API client methods
├── src/lib/science/                    # NEW: claim/hypothesis/ladder types + selectors
├── src/pages/SciencePage.tsx           # NEW: claims + evidence ladder
├── src/pages/HypothesesPage.tsx        # NEW: hypothesis register + coverage + gain planner
└── src/containers/                     # NEW/ADAPT: ScienceContainer, HypothesisContainer, ExperimentContainer
```

**Structure Decision**: A single new workspace member `apps/science` holds the analytical
domain (claims, hypotheses, causal, temporal, structure, robustness, experiments, review),
keeping the platform's per-app cohesion intact. All persistence and eventing flows through
existing `apps/shared` contracts; `apps/control-plane` only mounts the router; the webapp
gains science pages reusing existing Vite/React conventions. No new project is needed and
no Constitution violation is introduced.

## Complexity Tracking

> No Constitution violations — the Complexity Tracking table is intentionally empty.

## Phase 0: Outline & Research

Resolved in `research.md` (NPC: none unresolved):
1. **Numerical/Bayesian stack**: NumPy/SciPy reuse vs new deps — decision, rationale, alternatives.
2. **Calibration practice**: ECE/Brier protocols and honest overconfidence labeling.
3. **Information-gain planning**: expected information gain across competing hypotheses; budget semantics.
4. **Causal inference scope**: declared causal models, confounder control, and scope-boundary enforcement patterns.
5. **Change-point detection**: robust algorithms for credence trajectories (SciPy-based).
6. **Spectral/higher-order analysis**: bounded spectral centrality + motif significance with permutation nulls.
7. **Null models / robustness**: permutation protocols, perturbation designs, flip-rate reporting.
8. **Reproducibility**: seed/version pinning for the experiment registry.
9. **Event mapping**: which `science.*` topics/contracts to register in `EVENT_CATALOG`.
10. **UI gating**: evidence-ladder tiers and top-rung gating rules for the webapp.

## Phase 1: Design & Contracts

**Prerequisites**: `research.md` above.

1. **Entity model** → `data-model.md` (ScientificClaim, CredenceDistribution, Hypothesis,
   EvidenceLink, CalibrationReport, CausalModel, ChangePoint, StructureAnalysisResult,
   NullModelResult, RobustnessReport, ExperimentRun, ReviewEvent).
2. **Interface contracts** → `contracts/`:
   - `contracts/science-api.md` (REST surface for claims/hypotheses/calibration/causal/
     temporal/structure/robustness/experiments/review).
   - `contracts/science-events.md` (Kafka event envelope for `science.*` topics).
   - `contracts/scope-boundary.md` (person-level sensitive outcome rejection policy + audit).
3. **Validation guide** → `quickstart.md` (synthetic corpora scenarios proving US1–US7
   end-to-end: claim registration+calibration, hypothesis+gain planning, causal
   CORRELATIONAL→CAUSAL, change detection, spectral+null, robustness flip, reproduction,
   ladder gating).
4. **Re-check Constitution Check** post-design (table above remains green).

**Done when**: design artifacts generated; extension hooks dispatched or skipped; completion
reported with branch, plan path, and generated artifacts.