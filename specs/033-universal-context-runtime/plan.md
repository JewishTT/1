# Implementation Plan: COGNITIVE Universal Context Runtime — v2.0

**Branch**: `033-universal-context-runtime` | **Date**: 2026-10-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/033-universal-context-runtime/spec.md`, whose Appendix A is the owner's v2.0 blueprint reproduced verbatim.

## Summary

The v2.0 blueprint extends the programme from "an evidence-processing platform" to "a **context
runtime**". That extension is not a second product: §33 states that it attaches to
`specs/030-global-platform-upgrade` as a coherent extension and must not become a competing spec.

The technical approach is therefore an **additive layer over Feature 032's seam**, in five moves:

1. **A formal, open context model.** `ContextFrame`, `ContextElement`, typed scopes, open
   `kind_uri` and role-bearing relations. Nothing about a new domain may require a core enum change.
2. **A capability registry that replaces tool names.** Every operator declares what it accepts,
   emits, costs and is permitted to do; the planner selects by capability and policy, never by a
   hard-coded name or an LLM score.
3. **Abstraction as accountable operators.** Every upward step emits an `AbstractionManifest` with
   its omissions, and every summary keeps a drill-down to the bytes.
4. **A context kernel that compiles, evaluates and stops honestly.** Frame compilation with visible
   ambiguity, obligation evaluation, context assembly manifests, and a `CompletionReport` at every
   terminal state.
5. **A conformance regime that can say `NOT_RUN`.** Eighteen suites, a fifteen-fixture golden corpus,
   twenty ADRs and a Definition of Done, with the lifecycle statuses from §32 as the only admissible
   vocabulary.

The runtime reuses the evidence seam, spans, identity decisions, conflict records and projections
that Feature 032 builds. It does not replace them, and it must not create a parallel copy of any of
them.

## Technical Context

**Language/Version**: Python 3.11 for the runtime, contracts and operators; TypeScript/React for the
analyst workbenches; SQL and YAML for domain packs and capability manifests. No new language is
introduced.

**Primary Dependencies**: the existing platform stack — `apps/control-plane/context_engine`,
`apps/shared/contracts`, `apps/shared/events`, `apps/projection`, `apps/admission`, the typed
routers under `apps/control-plane/api`, and the webapp. New dependencies are limited to what a
capability manifest declares, and each must pass the donor gate.

**Storage**: no new canonical store. Context definitions, revisions, branches, obligations, action
plans and completion reports belong to PostgreSQL through the context kernel; elements reference
payloads in the object store; indexes are projections. A graph or vector store is an optional serving
profile pending the §30.2 benchmark and an ADR.

**Testing**: `pytest` for the runtime and contracts; the eighteen conformance suites of §32.1 as
named, runnable suites; the fifteen-fixture golden corpus of §32.2; contract tests for every
capability manifest; and the API/event compatibility suite. A suite that cannot run is reported
`NOT_RUN`, never omitted.

**Target Platform**: the existing deployment; Linux containers; the Windows workstation only for
development and tooling.

**Project Type**: runtime extension inside an existing multi-service platform.

**Performance Goals**: **not set here.** The §33 Phase A and H measurement programme sets them. The
v2.0 document is explicit that capability naming is not completion and that benchmark figures
without corpus, configuration and versions are not evidence.

**Constraints**: open `kind_uri` and schema registry; no core enum for domain kinds; every operator
invocation carries no ambient write privilege; `WRITE_EXTERNAL` off by default; untrusted content is
data, never instructions; no model may grant itself privileges; optional backends never become truth
stores; provider fallback cannot silently change jurisdiction or semantics.

**Scale/Scope**: 36 specification sections, 18 functional catalogues, 22 abstraction operators,
20 workbenches, 18 conformance suites, 15 golden fixtures, 20 ADRs. The scalar figures are
catalogues to be dispositioned, not capabilities to be claimed.

## Constitution Check

*GATE: must pass before Phase A; re-checked at the end of every phase.*

The constitution is `.specify/memory/constitution.md`. Feature 032's WP1 ratifies it as an
engineering constitution; this feature inherits that ratification rather than performing its own.

| Gate | Source | How this plan satisfies it | Failure mode prevented |
|---|---|---|---|
| **G1 — Open world, closed workflow** | Constitution; §16.3, §18.2, FR-001 | `kind_uri` and schema registry are open; only platform workflow states are enumerated | A closed ontology disguised as extensibility |
| **G2 — Five models stay distinct** | §15.2, FR-002 | hypothesis, simulation, evidence and policy are separate stores with separate write paths | A simulation becoming a fact |
| **G3 — Every transformation is accountable** | §17.3, FR-013 | `AbstractionManifest` on every upward step; drill-down mandatory | Silent data destruction by summary |
| **G4 — Capability, not tool name** | §20, FR-030 | `CapabilityManifest` registry; policy before quality before provider | An agent swarm with ambient permissions |
| **G5 — Permission classes** | §20.3, FR-034 | six classes, least privilege, `WRITE_EXTERNAL` off by default | A `DERIVE` operator writing canonical state |
| **G6 — Assembly is inspectable** | §22.2, FR-042 | `ContextAssemblyManifest` on every model and solver invocation | Unexplainable answers |
| **G7 — Unknown is classified** | §26.1, FR-055 | fourteen states, distinct across storage/API/UI | "No result" read as "does not exist" |
| **G8 — Confidence is not authorization** | §29.3, FR-073 | policy code and adversarial tests separate the two | A high-confidence match authorising collection |
| **G9 — Proven lifecycle** | §32, FR-077 | ten statuses with `BLOCKED`/`NOT_RUN`/`UNKNOWN` first-class | "Production-ready" by import |
| **G10 — No second authority** | §33, FR-080 | attaches to 030/032; reuses their stores and contracts | A parallel kernel or memory system |

**Result**: PASS on all gates. No exception requested. The twenty §34 ADRs are the vehicle for any
future exception; an exception without an ADR is not permitted.

## Relationship to Features 030 and 032

| Topic | Owner | This feature's role |
|---|---|---|
| Evidence seam, spans, identity decisions, conflict records, projections | **032** | consumes them; may not duplicate them |
| Context Engine kernel, obligations, closed loop | **030** | extends with frame/element/abstraction/assembly contracts and the completion report |
| Context model (`ContextFrame`, `ContextElement`, dimensions, abstraction ladder) | **033** | new |
| Capability registry and permission classes | **033** | new, and reused by 032's WP6 |
| Functional catalogue, workbenches, retrieval layers, reasoning modes | **033** | new |
| Multimodal contract, memory layers | **033** | new |
| API/event surface, model gateway | **033** | new resources and envelopes, reconciled against existing routers |
| Conformance suites, golden corpus, ADRs, Definition of Done | **033** | new regime governing both features |

Where 032 and 033 both constrain an object, the stricter rule governs and the difference is recorded
rather than reconciled by editing either spec.

## Project Structure

### Documentation (this feature)

```text
specs/033-universal-context-runtime/
├── spec.md                    # specification + Appendix A (verbatim v2.0 blueprint)
├── plan.md                    # this file
├── tasks.md                   # Phases A–H mapped to US1–US12
├── data-model.md              # context, abstraction, capability, assembly, memory, completion
├── quickstart.md              # how to verify the runtime's claims
├── checklists/
│   └── requirements.md
├── contracts/
│   ├── README.md
│   ├── context-frame.md
│   ├── context-element.md
│   ├── abstraction-manifest.md
│   ├── capability-manifest.md
│   ├── context-assembly-manifest.md
│   ├── completion-report.md
│   ├── memory-layers.md
│   ├── api-and-events.md
│   └── model-gateway.md
├── adr/
│   └── README.md              # the twenty mandatory ADRs and their status
├── conformance/
│   └── suites.md              # the eighteen suites and their current status
└── corpus/
    └── golden-corpus.md       # the fifteen fixtures and their expected states
```

### Source Code (repository root)

```text
apps/
├── control-plane/
│   ├── context_engine/        # frame compiler, obligation evaluator, revision manager, stopping
│   └── api/routes/            # contexts, conflicts, resolutions, evidence, ontologies,
│                              # capabilities, queries, analyses, runs, reports, audit
├── shared/
│   ├── contracts/             # ContextFrame, ContextElement, AbstractionManifest,
│   │                          # CapabilityManifest, ContextAssemblyManifest, CompletionReport
│   ├── semantic/              # ontology registry integration, open-world preservation
│   └── tools/                 # capability registry and permission enforcement
├── projection/                # serving projections: search, graph, timeline, spatial, TDA
├── science/                   # statistical, causal and simulation operators
└── webapp/                    # the twenty workbenches
```

**Structure Decision**: the runtime lives in `apps/control-plane/context_engine` and
`apps/shared/contracts`; it does not become a new top-level service. The blueprint's §18.1 says
exactly this — refine and integrate the existing engine, do not create a competing one.

## Phases A–H and their gates

| Phase | Delivers | Gate to leave the phase |
|---|---|---|
| **A — Measure and freeze baseline** | commit, tree, migrations, config, envelope; per-capability maturity matrix; canonical owner per critical entity; donor inventory; cardinality measurements; golden corpus; baseline quality/cost report | every figure has a command and a date; nothing is estimated where it can be measured |
| **B — Trustworthy evidence substrate** | one sink and gate across all profiles; canonical envelope, outbox and idempotency; typed spans end to end; SSRF/redirect/DNS/body-size/archive isolation; durable frontier and real budget enforcement; source policy and access modes in the capability registry | Feature 032's WP4/WP5 gates pass here, not in parallel |
| **C — Canonical semantics** | entity references and resolution decisions; claim and event schemas with support; four-valued epistemics and open-world preservation; typed time/space/scope/perspective; bitemporal queries and reducers; conflict records, dependency roots and abstain; ontology lifecycle | `NEITHER`/`TRUE_ONLY`/`FALSE_ONLY`/`BOTH` round-trip; no `now()` substitution |
| **D — Universal Context Kernel** | frame/definition/revision/branch contracts; obligation lifecycle and evaluator; capability planner, assembly manifest and action budget; stop/completion report and residual ledger; durable execution, checkpoints, restart; first E2E case with no optional donor | two persisted iterations change the next action for a recorded reason |
| **E — Analysis and abstraction operators** | lexical retrieval, exact span search, graph/time/space query interfaces; deterministic rule and constraint validation; abstraction manifests and reversible drill-down; statistical and causal operator contracts; multimodal extraction contracts; output schemas, reports and explanation paths | every summary can drill back; every causal claim states identification |
| **F — UI/SDK and collaboration** | workbench, context explorer, evidence browser; conflict desk, ontology studio, timeline, report builder; capability and source registries; API/SDK with durable run/status/trace; audit, redaction, retention, multi-tenant validation | every surface shows staleness, unknown and conflict; no surface has its own truth |
| **G — Measured donor promotion and scale profiles** | Semantica as non-authoritative operators; `kafSIEM` patterns without its store; AEGiS identity pinned and classified; optional vector and graph backends benchmarked; each tool through the full lifecycle to `APPROVED_FOR_SCOPE` with a rollback route | the donor gate of Feature 032 §8.7 holds for every promotion |
| **H — Operational hardening** | load, concurrency, recovery, restore and long-run tests; source/capability/operator health; cost and SLOs from measured distributions; policy-change replay controls and access review; migration, runbook, rollback, incident response and security review; release gate requiring live E2E evidence | the §35 Definition of Done is demonstrated item by item |

## Risks and their mitigations

| Risk | Why it is live here | Mitigation |
|---|---|---|
| The catalogue of §19 is mistaken for a capability list | it is 18 sections of plausible features | FR-022 requires an ID, owner, contract, determinism, cost, tests and production status per row; `NOT_RUN` is admissible |
| "Universal" becomes an excuse for an unbounded agent swarm | the word invites it | FR-030/FR-034: capability registry plus permission classes; one plugin, one permission class |
| Abstraction quietly destroys evidence | summaries are cheap and seductive | FR-013: a manifest with omissions and a drill-down is mandatory, and the drill-down is tested |
| Context assembly prunes the decisive contradiction | budget pressure is constant | FR-042: conflicts are preserved or the exclusion is recorded and surfaced |
| The API grows a second set of routers | the resource list is long | FR-059: reconcile against existing routers; no second set without a migration plan |
| Optional backends become canonical | a benchmark is tedious | FR-075/FR-076: optional profiles never become truth stores; benchmark includes deletion propagation and recovery |
| `NOT_RUN` disappears from the release report | it is the least flattering entry | FR-077 and SC-014 make it a blocking value at the release gate |

## Complexity Tracking

No constitution violation is requested. The apparent additions — a capability registry, nine
memory layers, twenty workbenches, eighteen suites — are the mechanisms that make the runtime's
universality *checkable*. Each one replaces an implicit assumption with a named, testable contract.
