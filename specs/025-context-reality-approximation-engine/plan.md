# Implementation Plan: Context & Dialectical Reality Approximation Engine (025)

**Branch**: `025-context-reality-approximation-engine` | **Date**: 2026-10-04 | **Spec**: [spec.md](spec.md)

**Input**: Specification 025 **v2** — `/specs/025-context-reality-approximation-engine/spec.md` + verbatim `input.md`
**Research**: [research.md](research.md) · **Baseline**: [input.md](input.md) · **Decisions**: [ADR-0028](../../../docs/adr/0028-context-definition-identity-and-placement.md)

---

## Summary

Turn the existing evidence-first substrate into a closed epistemic loop. The engine
maintains a versioned approximation of a scoped, changing system from incomplete
observations, and answers four questions without conflating them: what was observed; which
interpretations are compatible; which explanations best account for it; and what to
investigate next to separate the remainder.

Primary requirement, in the baseline's own terms: a durable context decomposes into bounded
local cells; compatible sections glue and incompatible ones yield persisted obstructions;
hidden state is estimated with residuals; hypotheses compete with visible assumptions;
contradictions persist without collapsing; regime/change-point/causality stay separate
claims; the research frontier is selected for discrimination; "find all" reports its own
completeness honestly; everything is replayable from immutable inputs under a disabled
adaptive layer.

**Technical approach.** Reuse-first. The durable, async Context Engine already exists and
is live-verified; 025 adopts and extends it rather than rebuilding. New work is
concentrated where research found no prior art: four-valued truth and contradiction
lifecycle, causal staging, gluing/obstruction, and the completeness protocol. Structural
compatibility uses a deterministic hand-specified sheaf-style operator; learned stalk
spaces are excluded from the critical path by P08/P09. TDA is consumed, not rebuilt.

**The single most important constraint on this plan**: §56 enumerates 154 tasks against a
substrate where the corresponding foundation is already implemented, async, durable and
tested. The adoption matrix in §"Adoption Matrix" below is therefore a *load-bearing*
deliverable, not documentation. Anything in §56 that already exists is not re-implemented.

---

## Technical Context

**Language/Version**: Python 3.11 (`requires-python = ">=3.11"`); TypeScript/TSX for the operator UI

**Primary Dependencies**: FastAPI · SQLAlchemy 2.x async (`create_async_engine`, `AsyncSession`, `async_sessionmaker`) · asyncpg · ClickHouse client · Redpanda · Temporal · Neo4j (projection only) · pytest 9.1.1 + pytest-asyncio 1.4.0 (`asyncio_mode = "auto"`) · GUDHI (existing TDA path) · React + Vite (webapp)

**Storage**: PostgreSQL is the sole authority for context and research state (ADR-0027). ClickHouse holds temporal-graph projections. Object storage holds raw bytes. Neo4j is a rebuildable serving projection. No new store is introduced by 025.

**Testing**: pytest with `asyncio_mode = "auto"`; deterministic golden corpora per §52–§53; property tests for canonicalisation, restriction and replay invariants (Appendix M.2)

**Target Platform**: Linux server for services; Windows developer laptop supported. CPU-first, 20 GB RAM profile (§47) — no operator may assume GPU availability

**Project Type**: domain capability layered over an existing monorepo of services. Not a new application; `apps/context-engine/` is forbidden.

**Performance Goals**: cell comparison bounded by blocked candidate sets, never quadratic in cell count (§8.2). Select-path operator latency must remain interactive at corpus scale (existing TDA reference: sub-10ms select, ~90ms clustered full pipeline on this hardware). Overlap discovery must report bucket overflow rather than process it (Appendix I.1).

**Constraints**: byte-identical replay at every declared artifact boundary with wall-clock excluded from identity (§4, §36) · every operator declares a memory class and honours `ComputeBudget` (§45, §47.2) · no derived object visible before durable commit (§6.1) · cross-tenant reads fail closed (§40) · adaptive layer optional and disabled by default (§48)

**Scale/Scope**: one feature across five existing application boundaries. Wave 0 contract freeze (12 ADR), then 154 tasks across 16 phases including the 2S vertical slice, then 14 wave gates. Dominant cost is not code volume but discipline: preserving the epistemic distinctions through every serialisation, API and UI path.

---

## Constitution Check

**Gate status: PASS WITH ONE FINDING.**

`.specify/memory/constitution.md` is still an unmodified template — every placeholder
(`[PROJECT_NAME]`, `[PRINCIPLE_1_NAME]`) is intact. The repository therefore has **no
enforceable spec-kit-level constitution**. The real doctrine lives in `AGENTS.md` and in the
owner-approved invariants of the baseline.

*Finding (research R8)*: before any further speckit governance command runs, the owner must
decide whether the constitution is generated from `AGENTS.md`. Running
`/speckit.constitution` over the current template would either write placeholder doctrine
or conflict with `AGENTS.md`. **This plan does not run it.** The gates below are therefore
derived from the two documents that do carry authority.

### Gates applied

| # | Gate | Source | Status |
|---|---|---|---|
| G1 | Observation precedes commitment — nothing below L0 rewrites an observation | P01, INV-1 | Binding |
| G2 | Identity is owned by resolution/admission, not by contextual compatibility | P02 | Binding |
| G3 | Unknown is first-class; unknown ≠ false | P03, INV-1, FR-025-064 | Binding |
| G4 | Contradictions are durable and preserve both sides | P04, FR-025-040 | Binding |
| G5 | Competing hypotheses coexist; no premature convergence | P05, FR-025-029 | Binding |
| G6 | Every inference names method/operator/version | P06, FR-025-056 | Binding |
| G7 | Deterministic core works with adaptive layer disabled | P07, INV-4 | Binding — acceptance mode |
| G8 | Adaptive layer subordinate; proposals never admissions | P08, FR-025-061 | Binding |
| G9 | Every derived result rebuildable from immutable inputs | P09, FR-025-068 | Binding |
| G10 | Locality: bounded pair generation, named scopes and budgets | P10, FR-025-009 | Binding |
| G11 | Semantics do not gate structure — unmapped predicates keep structural evidence | P11 | Binding |
| G12 | No hidden second truth model | P12 | Binding |
| G13 | Layers import strictly downward; all writes through contracts | `AGENTS.md` §2 | Binding |
| G14 | Donors are reused before new code is written, and reuse is reported as reuse | `AGENTS.md` §1 | Binding |
| G15 | A donor defect is treated on transfer, not used as grounds to refuse transfer | `AGENTS.md` §2 | Binding |
| G16 | Architectural contradiction with the platform is escalated to the owner, never self-resolved | `AGENTS.md` §1.1 | Binding — already exercised by ADR-0028 |

**Re-check required after Phase 1 design**, per the template.

---

## Project Structure

### Documentation (this feature)

```text
specs/025-context-reality-approximation-engine/
├── input.md                  # owner Design Baseline — VERBATIM, 102.8 KB, sections 0-61 + Appendices A-X
├── research.md               # donor inventory, literature, risk register R1–R8
├── spec.md                   # /speckit.specify output — APPROVED (ADR-0028)
├── plan.md                   # this file — /speckit.plan output
├── data-model.md             # Phase 1 output — DONE
├── quickstart.md             # Phase 1 output — DONE
├── contracts/contracts.md    # Phase 1 output — DONE
├── checklists/
│   └── requirements.md       # spec quality checklist — passes, 4 noted items
├── decisions.md              # owner decision record: Q1=B, Q2=B
└── tasks.md                  # Phase 2 output — DONE (154 tasks + 12 ADR records)
```

Architecture decision record lives with the other ADRs:
`docs/adr/0028-context-definition-identity-and-placement.md`.

### Source Code (repository root)

Placement follows the baseline §1.2 **except** for the control-plane layer, where ADR-0028
supersedes the required path. No `cp_domain/` package, no re-export shim.

```text
apps/shared/domain/context/          # PURE DOMAIN — no I/O, deterministic contracts
├── ids.py                           # CXD/CXC/OVL/RST/CMP/GLU/VAR/STE/HYP/LHYP/ASM/
│                                    # EXP/CTR/OBS/DGT/REG/TRN/TDA/CAU/SAT/DEC/RUN/MF/PF
├── canonical.py                     # canonical_material(); forbidden-material linter
├── truth.py                         # TruthState four-way algebra (greenfield, no donor)
├── scope.py                         # typed scope intersection EMPTY|PARTIAL|EXACT|UNKNOWN
├── temporal.py                      # six axes + derived interval relations
├── cells.py  overlap.py  hypothesis.py  contradiction.py
├── dynamics.py  frontier.py  budget.py
└── __init__.py

apps/control-plane/context_engine/   # CANONICAL PATH (ADR-0028) — durable state + orchestration
├── engine.py                        # EXISTS, async — extend, do not rewrite
├── loop.py                          # EXISTS, async — extend
├── obligations.py  store.py  postgres_store.py  catalogue_bridge.py
├── definition.py                    # NEW — ContextDefinition (CXD-) persistence
├── revisions.py  decisions.py  frontier.py  lifecycle.py  replay.py
└── api/routes/context_*.py          # 025 endpoints, distinct URL prefix

apps/science/context/                # ALGORITHMS / REASONING OPERATORS
├── operators/
│   ├── base.py                      # ReasoningOperator protocol, complexity/memory class
│   ├── compatibility.py             # sheaf-style deterministic structural kernel
│   ├── gluing.py  state.py  abduction.py  dialectics.py
│   ├── information_gain.py  dynamics.py  tda.py  causal.py
│   └── registry.py                  # operator registry + selection profile
├── models/  calibration/  experiments/

apps/projection/context/             # SERVING READ MODELS — rebuildable
└── readers.py  materializers.py  serializers.py  metrics.py

apps/webapp/src/context/             # OPERATOR PRESENTATION
└── api/  state/  views/  components/  hooks/

bench/context/                       # corpora per §52–§53
└── corpus/  deterministic/  abduction/  dialectics/  dynamics/  global_search/

docs/adr/0028..0039 + WAVE-000-index  # Wave 0 records 1-12 of 12 (ALL ACCEPTED)
```

**Structure Decision.** Five existing application boundaries, each with a distinct
functional role (pure domain / durable orchestration / algorithms / serving read models /
presentation). The separation is functional, not organisational: `shared` holds no I/O and
must stay importable in a deterministic replay with no services running; `control-plane`
is the only writer of durable context state; `science` computes and never writes world
state directly; `projection` is discardable; `webapp` never computes. The one deviation
from baseline §1.2 is the control-plane path, recorded in ADR-0028 with its justification.

---

## Adoption Matrix (mandatory deliverable — research R2)

The baseline's 129-task list is written as if from scratch. It is not. This table is the
reconciliation, and every task in `tasks.md` must be tagged against it.

| Baseline object | Current state | 025 role | Action |
|---|---|---|---|
| `InvestigationContext` | **Exists.** `apps/shared/domain/investigation_context.py`. Async, durable, live-verified | Operational revisioned state | **REUSE.** Add exactly one nullable attribute `definition_ref -> CXD-…` (ADR-0028). Nothing else changes |
| `ContextRevision` | **Exists.** Append-only, parent-linked, `caused_by_event_ids`, replayable, verified | Revision snapshot | **REUSE.** Extend with `state_hash`, `method_fingerprint`, `policy_fingerprint`, `worldline_snapshot_ref` (§6.1) |
| `ResearchObligation` | **Exists.** Stable address, statuses, satisfaction criteria | Unresolved epistemic demand | **REUSE + EXTEND** with readiness state, missing evidence, priority components (§21) |
| `ResearchAction` | **Exists.** Proposals awaiting approval, runtime refs | Discriminating evidence request | **REUSE + EXTEND** with decomposed utility, expected vs realised gain (§20.3) |
| `ContextFrontier` | **Exists.** Queryable, persisted | Ranked frontier | **REUSE + EXTEND** with priority tuple and truncation disclosure |
| `ActionMemoryEntry` | **Exists.** Keyed by obligation | Repeat suppression | **REUSE** |
| Context Engine (async, durable) | **Exists and green.** Contract, in-memory store, PostgreSQL store, `CognitiveLoop`; 104 context tests pass; 0 regressions across `apps` | Orchestration boundary | **REUSE.** Verified live: investigation → context → question → obligations → frontier → replay |
| Observation / Mention / RelationSignal / RelationClaim | Exist (019/021) | L0/L1 substrate | **REUSE.** Forbidden to relocate (§58.6) |
| Entity / identity / worldline | Exist (012/015) | L2 admitted world | **REUSE.** 025 consumes; never re-resolves identity (P02, G2) |
| Graph projection | Exists, rebuildable | Serving read model | **REUSE** |
| Scientific evaluation / semantic regime | Exist (006/017) | Regimes, semantic constraints | **REUSE** as inputs |
| `EventEnvelope` (16 fields) | Exists | Transport | **REUSE.** No new backbone |
| TDA (`apps/projection/tda`, `apps/science/scitda`) | **Exists and benchmarked.** ~180× clustered speedup, `insight.py` with hidden clusters + anomalies | Structural features (§26) | **REUSE + FENCE.** Prove no write path from topological feature → identity/truth. Do **not** rebuild |
| Acquisition (145 sources, Airbyte, BBOT, SearXNG) | Exists | Evidence supply | **REUSE.** 025 wraps the completeness protocol; no new collector |
| `ContextCell`, `ContextOverlap`, `RestrictionMap` | **Do not exist** | Locality | **NEW** (T025-001–003) |
| `CompatibilityAssessment`, `GluingResult`, `Obstruction` | **Do not exist** | Locality | **NEW** (T025-004–005). No donor implements gluing — research §3.1 |
| Four-valued `TruthState` algebra | **Do not exist.** Zero donor hits — research §3.7 | Epistemic core | **NEW.** Highest-discipline item; truth-table gate is a release gate (R3) |
| Contradiction engine + independence assessment | **Do not exist** | Epistemic core | **NEW** (T025-067–070). Donor `estorides` may inform independence heuristics |
| Causal identification/estimation/refutation staging | **Do not exist.** No donor precedent — research §3.8 | Science | **NEW** (T025-084). Three separately persisted stages from day one (R4). Never add a convenience causal score |
| Hypothesis / Assumption / Prediction / DiscriminatingTest / DialecticalPair | **Do not exist** | Epistemic core | **NEW.** Reuse assessed from `BeliefLandscapeFramework` first (research §3.2) |
| `ReasoningOperator` framework + registry | **Does not exist** | Platform | **NEW** (T025-087–092). Wraps donor adapters per §30.4 |
| State variable / estimate / observation model | **Do not exist** | Dynamics | **NEW** (T025-043–046). Donor candidates: `ABa-KiTo` state-space + ISOKANN |
| Regime / transition window | **Do not exist** | Dynamics | **NEW** (T025-049–051). Donor candidate: `cognitive_phase_transitions` |
| Query compiler + completeness protocol | Compiler does not exist; catalogue exists | Query | **NEW** (T025-094–100). This is the Appendix P honesty layer over existing acquisition |
| **v2: Branches** (`ContextBranch`) | Do not exist | Scenarios/counterfactuals, mainline isolation | **NEW** (T025-142). Mainline revision key unchanged |
| **v2: Analyst objects** | Do not exist | First-class analyst input/decision | **NEW** (T025-144) |
| **v2: Retention/erasure** | Does not exist | Crypto-shredding, legal hold, `REPLAY_DEGRADED` | **NEW** (T025-145) |
| **v2: InferencePolicy** | Does not exist | Gate on sensitive inference classes | **NEW** (T025-146) |
| **v2: ReasoningProfile** | Does not exist | Declared ranking/tiers/quotas | **NEW** (T025-139) |
| **v2: Numeric modes + seeds** | Partial (TDA has fp) | Determinism classes | **NEW** (T025-136) |
| **v2: Allen algebra** | Temporal relations exist (014) but not full 13-relation disjunctive algebra | §24.2 | **EXTEND** (T025-140) |

**Task-count implication (v2).** Of 154 tasks, a substantial minority concern objects that
already exist and must be tagged *extend* or *reuse*. `tasks.md` must not present them as
new construction, and the reuse column of every task report must state what was taken from
024 and what from donors (`AGENTS.md` §1.3).

---

## Risk Mitigations (from `research.md` §4)

| Risk | Mitigation in this plan | Where it lands |
|---|---|---|
| **R1** Config-scope-dependent behaviour (the `asyncio_mode` class of bug) | Every new package's tool configuration must be verified **from the repository root**, not only from its own directory. Added as a standing review item, not a one-off | Wave 0 exit check; standing item in every wave gate |
| **R2** Rebuilding live, working code because §56 reads as greenfield | Adoption Matrix above is a required input to `tasks.md`; tasks must be tagged reuse/extend/new | This document; `tasks.md` tagging |
| **R3** Four-valued `BOTH` leaking to boolean in one serialisation path | Truth-table gate promoted from test to **release gate**; property test asserts no path maps `(true,true) → true` across storage, API, projection, UI | Wave 1 exit (Appendix U) |
| **R4** Causal staging collapses into one confidence number | Three stages persisted separately from the first commit; a single convenience causal score is forbidden by §27.2 and may not be added later | Wave 8 exit |
| **R5** Complexity ranking collapses to "take the top score" (anti-pattern V.5) | `rejected_candidates` and `truncation_reason` mandatory; near-duplicate cases mandatory in the abduction corpus; diversity requirement in top-*k* | Wave 5 exit; T025-059 |
| **R6** ~~Wave 0 unsatisfied~~ | **RESOLVED 2026-10-04** — 12/12 ADR accepted (`docs/adr/WAVE-000-index.md`); `T025-154` discharged; §47.4 targets ratified into deployment config | closed |
| **R9 (v2)** Pairwise compatibility mistaken for global coherence | Triple-coherence check with `max_triples`; `GLUED` forbidden while `triples_unchecked > 0`; UI/docs must say "pair- and triple-coherent under budget" | `T025-141`, Wave 3 |
| **R10 (v2)** Multiplicative utility reintroduced | Ranking modes declared in `ReasoningProfile`; hard gates are filters; no cross-tier numeric comparison; property test fails the build | `T025-139`, Wave 7 |
| **R11 (v2)** Float nondeterminism breaks replay | Determinism classes, numeric modes, derived seeds, canonical reduction order, quantized identity | `T025-136`, Wave 1 |
| **R12 (v2)** SQLite used for persistence tests | Forbidden (§47.1, V.16): append-only guards, RLS, generated columns and JSONB indexing differ and hide defects | Wave 2 exit |
| **R7** Unversioned dependencies defeat replay | `MethodFingerprint` must resolve to concrete versions from the moment the first operator registers, not retrofitted | T025-086, T025-090 |
| **R8** Repository constitution is an unmodified template | Flagged for owner decision. This plan does **not** run `/speckit.constitution` | Reported, awaiting owner |

---

## Phasing

Baseline §57 critical path, with Wave 0 enforced as a real gate and the adoption matrix
threaded through every phase.

```text
WAVE 0  Contract freeze - CLOSED (12/12 ADR accepted)     gate: no 024/025 terminology conflict
                                                        ← + §47.4 targets ratified
  A Domain kernel          T025-001…020   truth, scope, temporal, canonicalisation
  B Persistence            T025-021…033   cells/overlap/gluing/state/hypothesis/…/indexes/guards
  C Compatibility+locality T025-034…042   bounded blocking, restriction, gluing, obstruction→obligation
  D State + dynamics       T025-043…052   observation model, residuals, intervals, regime, transition
  E Abduction              T025-053…061   bounded search, explanations, diversity, predictions, tests
  G Epistemic/contradiction T025-067…071  paraconsistency, detection, independence, lifecycle   ← before F
  F Dialectics             T025-062…066   pairing, counter-hypotheses, differential predictions
  H Frontier               T025-072…079   information gain, utility, ranking, saturation, closure
  I Science integration    T025-080…086   worldline anchoring, TDA series, change points, causal, fingerprints
  J Operator registry      T025-087…093   registry, validation, resource metadata, donor adapters, selection
  K Query compiler         T025-094…100  AST, deterministic grammar, LLM adapter, completeness mode
  L Read models / API      T025-101…108  endpoints
  M UI                     T025-109…117  workspace, hypothesis matrix, cells, dynamics, provenance
  N Benchmarks             T025-118…129  corpora, replay fixed-point, resource budget
  O v2 additions           T025-130…154  вплетаются в фазы выше по §57
```

`G` precedes `F` because dialectical competition depends on durable contradiction and
support semantics (§57). Owner-approved ordering retained unchanged.

### Sequencing constraints that survive ordering

1. **Wave 0 is a gate, not a phase.** CLOSED 2026-10-04: 12/12 ADR accepted (R6 resolved). §55's exit criterion is
   *no unresolved contradiction between 024 and 025 terminology*, which is only evaluable
   once those records exist.
2. **Reuse assessment precedes estimation** for `BeliefLandscapeFramework` (before
   T025-053…066) and for the `cognitive_phase_transitions` + `ABa-KiTo` cluster (before
   T025-049…052). `AGENTS.md` §1 makes the search mandatory; skipping it to reach an
   estimate is a process defect, not a shortcut.
3. **TDA integration is early, TDA construction is never.** `apps/projection/tda` and
   `apps/science/scitda` already exist and are benchmarked. Wave 8 / T025-081 consumes and
   fences them.
4. **Each phase ends at its Appendix U gate.** A gate failure blocks the next phase; it is
   not a documentation checkpoint.

---

## Complexity Tracking

| Deviation | Why needed | Simpler alternative rejected because |
|---|---|---|
| **Control-plane path `apps/control-plane/context_engine/`, not baseline §1.2's `cp_domain/context_engine/`** (ADR-0028) | The live, async, durable, tested Context Engine is at this path. Moving it changes every import, test path and deployment reference for zero behavioural gain | Creating `cp_domain/` (moves verified code); re-export shim (two legal import paths for one implementation — the exact ambiguity class that previously caused 12 collection errors) |
| **Split identifier namespace `CXD-` for `ContextDefinition`** (ADR-0028) | Two distinct objects sharing `CXI-` makes every reference, storage key and lineage edge ambiguous at the storage layer | Keeping the baseline's single `CXI-` for both. A shared prefix is not a style choice here — it is a correctness hazard for lineage and cross-referencing |
| **Two context-shaped objects rather than one extended object** (ADR-0028) | Immutable analytical specification and evolving operational state have genuinely different lifecycles; one object would need a discriminator field and every reader would need to know its mode | Extending `InvestigationContext` in place: rewrites a frozen approved 024 contract, which §58.1 forbids |
| **Wave 0 modelled as a hard gate with 12 ADR records** rather than a parallel activity | The baseline's own exit criterion is a terminology-conflict test, which cannot run before the records exist | Starting Phase A immediately: the first thing Phase A does is mint identity prefixes, so an unfrozen vocabulary guarantees rework |
| **Four-valued truth gate promoted to a release gate** | `BOTH` leaking to boolean in one serialisation path is invisible — the system still returns numbers | A normal test. R3 shows the failure mode is silent, and silent failures do not fail ordinary tests |
| **Operator framework introduced before any operator is written** | Baseline §30 requires every operator to carry a contract, fingerprint, resource declaration and explanation trace. Retrofitting that onto existing operators is more expensive than building it in | Per-operator ad-hoc metadata. This is the same class of mistake as retrofitted reproducibility (R7) |

---

## Deliverables of this plan

1. Technical context filled from verified repository reality, not assumption.
2. Constitution check performed, with the R8 finding surfaced rather than papered over.
3. Project structure reflecting the single ADR-0028 deviation, with functional rationale per
   boundary.
4. **Adoption Matrix** reconciling the baseline's greenfield-shaped task list against a
   substrate that already implements the foundation (R2).
5. Risk mitigations R1–R8 mapped to concrete gates and phases.
6. Phasing preserving the baseline's critical path and its `G`-before-`F` ordering.
7. Complexity tracking recording six deviations with their rejected alternatives.

**Status**: `/speckit.tasks` complete (v2: 154 tasks). `tasks.md` (154 tasks, tagged `NEW`/`EXTEND`/`REUSE`; 12 Wave 0 ADR records **accepted**), `data-model.md`, `quickstart.md` and
`contracts/contracts.md` are written and cross-checked: 129/129 task ids present, 14 phases,
68/68 FR ids in `spec.md`, 62/62 baseline sections and 24/24 appendices in `input.md`.

**Next**: `/speckit.implement` — **unblocked**. Phase A (T025-001…020), then B, then **2S Slice-0**.
epistemic algebra, revision/replay contract, sheaf-inspired locality boundary, hypothesis
lifecycle, reasoning operator contract, global-search completeness semantics. Phase A does
not begin before they are accepted.