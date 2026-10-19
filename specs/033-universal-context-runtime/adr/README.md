# ADR Register — Feature 033

**Feature**: `033-universal-context-runtime`
**Requirement**: FR-081 — the twenty ADRs of §34 must be approved and versioned before the
architecture is treated as final.

---

## Why a register, not twenty files yet

An ADR is a decision with an owner, alternatives, consequences, migration and rollback. Writing
twenty of them up front, before Phase A's measurements exist, produces twenty documents that record
intentions rather than decisions — and the blueprint's own §34 says *"A proposed architecture is not
final until conflicts between ADRs are resolved."*

So this register fixes **what each ADR must decide**, its required inputs, and its blocking
dependency. The ADR is written when its inputs exist. A register entry that is still `OPEN` at the
release gate is a release blocker (SC-016).

---

## Required structure of every ADR

```text
# ADR-033-NN — <title>

Status:        proposed | accepted | superseded | rejected
Date:          <date>
Owner:         <role>
Supersedes:    <ADR ref or none>

## Decision
<the decision, in one paragraph>

## Context
<why this decision is needed, with the measurements or constraints that force it>

## Alternatives
<each with its rejection reason>

## Consequences
<positive, negative, and the cost of reversing>

## Migration plan
<how the system moves from the current state>

## Rollback plan
<how the decision is undone without losing canonical state>

## Conflict check
<which other ADRs this touches, and how the conflict is resolved>
```

---

## The twenty ADRs

| # | ADR | Must decide | Inputs required | Blocking dependency |
|---|---|---|---|---|
| 01 | Canonical authority map and graph separation | which store owns each object; why the entity graph and the context graph are not one graph | WP0 owner map; Phase A cardinality | Phase A (T003, T005) |
| 02 | Context model, revisions and branch semantics | the frame/revision/branch contract; when a revision is meaningful; how a branch merges | `contracts/context-frame.md`; Phase C | Phase C (T030, T031) |
| 03 | ArtifactSink / Observation Gate / outbox seam | the single publication path and its transaction boundary | Feature 032 WP4 results | Feature 032 WP4 |
| 04 | Evidence spans and selector semantics | the typed union, the semantics version, the conversion policy | Feature 032 WP5 results | Feature 032 WP5 |
| 05 | Claim/event schema, epistemic algebra and absence semantics | four-valued support, the absence vocabulary, the closed workflow states | Phase C results | Phase C (T014, T015) |
| 06 | Identity resolution, merge/split and admission | where identity is decided, and what a proposal may never do | Feature 032 WP4; Phase C | Feature 032 WP4 |
| 07 | Bitemporal time model and query semantics | the seven clocks, `CURRENT`/`AS_OF`/`INTERVAL`, precision propagation | Phase C results | Phase C (T016) |
| 08 | Ontology-pack lifecycle and open-world extension | `DRAFT→…→RETIRED`, mapping proposal, re-interpretation | Phase C results | Phase C (T018) |
| 09 | Conflict detection, source dependency and resolution authority | what counts as independent corroboration; who may adjudicate | Feature 032 WP8 results | Feature 032 WP8 |
| 10 | Capability/plugin execution contract and permission classes | the six classes and their enforcement point | `contracts/capability-manifest.md` | Phase E (T054–T057) |
| 11 | Durable workflow engine ownership and agent-loop boundaries | Temporal remains the owner; what an agent loop may and may not do | Phase D results | Phase D (T040) |
| 12 | Retrieval quality, indexes and context packing | BM25 baseline, when a vector index earns adoption, how packing protects conflicts | Phase E retrieval measurements | Phase E (T035) |
| 13 | Abstraction manifests, summaries and loss accounting | what an abstraction must record, and what makes a drill-down mandatory | `contracts/abstraction-manifest.md` | Phase E (T042–T046) |
| 14 | Model/provider versioning, privacy and fallback | exact identity, fallback constraints, the five output classes | `contracts/model-gateway.md` | Phase F/G |
| 15 | Projection manifests, rebuild and freshness guarantees | the manifest fields and the stale-cannot-satisfy rule | Feature 032 WP7 results | Feature 032 WP7 |
| 16 | Data classification, retention, deletion and replay policy | the nine memory layers' retention; deletion propagation | Phase F (T062, T076) | Phase F |
| 17 | Donor licensing and SBOM/model/data assets | per-artifact-class licensing and the promotion gate | Feature 032 WP0 registry | Feature 032 WP0 |
| 18 | Universal API/event schema versioning | versioning policy, compatibility checks, one API set | Phase F (T064–T068) | Phase F |
| 19 | Evaluation corpus, benchmark ownership and release thresholds | who owns the corpus, what a threshold is derived from, when `NOT_RUN` blocks | Phase A corpus; Phase H | Phase H (T080–T084) |
| 20 | Graph/vector/backend choice after workload-specific benchmarking | whether any optional backend is adopted, and under what kill switch | Phase G benchmarks | Phase G (T073) |

---

## Rules

1. **No ADR without its inputs.** An ADR written before its measurement records an intention.
2. **No conflict left unresolved.** Two ADRs that disagree are a blocking defect; §34 says the
   architecture is not final until they are reconciled.
3. **Every ADR has a rollback plan.** A decision that cannot be undone is a decision that will be
   regretted under pressure.
4. **A superseded ADR stays.** It is marked `superseded`, not deleted, so the history of the
   decision remains readable.
5. **The register is checked at the release gate.** Any `OPEN` entry blocks the release (SC-016).

---

## Current state

All twenty entries are `OPEN`. None is `ACCEPTED`, because Phase A's measurements and Phases B–G's
results do not exist yet. This is the truthful state of the register, and it is exactly what the
release gate is designed to catch if it is still true at Phase H.
