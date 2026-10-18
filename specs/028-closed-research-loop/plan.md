# Implementation Plan: Closed Research Loop with Versioned Evidence Contracts

**Feature**: 028-closed-research-loop
**Spec**: [spec.md](./spec.md)
**Status**: Planned — awaiting implementation
**Date**: 2026-10-13

---

## 1. Why this plan exists in this shape

The specification asks for a loop that closes, evidence that traces, and determinism
that survives restart. The audit (`audit/current-state-audit.md`) shows the platform
already contains almost all the pieces — an obligation ledger, a satisfaction
evaluator, a decision recorder, a revision manager, an append-only life stream, an
incremental invariant reducer, a five-fold absence algebra, an independence model.

**They are not connected.** The pieces are individually unit-tested and collectively
inert. The single production call into the research loop passes no saturation
evidence, which makes the saturation verdict permanently "not saturated", which makes
the satisfaction evaluator permanently unsatisfied, which means no obligation can ever
reach a terminal state.

So the plan is not "add a context engine". It is **connect what exists, remove what
duplicates it, make the dead paths either live or absent, and prove the result
end-to-end.** New capability is added only where the audit shows a genuine gap.

That ordering matters. Adding donors (Docling, Splink, RRF libraries, GNN, H3,
DuckDB Spatial, vector retrieval) before the contracts are sound would multiply
uncounted producer paths across a substrate whose central invariant is already
violated by three of its own producers.

---

## 2. Architecture

### 2.1 The loop as implemented

```
                    ┌──────────────────────────────────────────┐
                    │ Question Definition  (CXD-, immutable)   │
                    │  objective · scope · policy · time frame │
                    └───────────────┬──────────────────────────┘
                                    │ one definition, many investigations
                    ┌───────────────▼──────────────────────────┐
                    │ Investigation Context (CXI-, revisable)   │
                    │  revision N ──supersedes──▶ revision N+1  │
                    │  obligations · hypotheses · evidence      │
                    │  conflicts · unknown · decisions          │
                    └───────────────┬──────────────────────────┘
                                    │
   ┌────────────────────────────────┼────────────────────────────────┐
   │                                │                                │
┌──▼──────────────┐        ┌────────▼─────────┐        ┌─────────▼──────────┐
│ ObligationGen.  │───────▶│ ActionProposer   │───────▶│ Acquisition        │
│ gaps→obligations│        │ explainable      │        │ adapters → workers │
└─────────────────┘        │ multi-objective  │        └─────────┬──────────┘
                           │ hard constraints  │                  │
                           └────────┬─────────┘                  │ ONE gate
                                    │                    ┌─────────▼──────────┐
                                    │                    │ Observation Gate   │
                           ┌────────▼─────────┐         │  raw bytes FIRST   │
                           │ SatisfactionEval.│         │  then observation   │
                           │ independence ·   │         │  then publish      │
                           │ conflicts · gaps │         │  deterministic id   │
                           └────────┬─────────┘         └─────────┬──────────┘
                                    │                             │
                                    │                    ┌────────▼──────────┐
                                    │                    │ append-only life  │
                                    │                    │ stream (immutable) │
                                    │                    └────────┬──────────┘
                                    │                             │
                           ┌────────▼─────────────────────────────▼──────────┐
                           │ InvariantReducer — digest-gated, incremental   │
                           │ new revision ONLY when the digest moves       │
                           └────────┬──────────────────────────────────────┘
                                    │
             ┌──────────────────────┼──────────────────────┐
             │                      │                      │
      ┌──────▼──────┐       ┌───────▼───────┐      ┌───────▼────────┐
      │ graph       │       │ search        │      │ temporal/TDA/  │
      │ projection  │       │ projection    │      │ spatial/OLAP   │
      └──────┬──────┘       └───────┬───────┘      └───────┬────────┘
             └──────────────────────┼──────────────────────┘
                           ┌───────▼────────┐
                           │ Findings +     │
                           │ epistemic state│
                           └───────┬────────┘
                                   │
                           ┌───────▼────────┐
                           │ analyst review │
                           └───────┬────────┘
                                   │ feedback
                                   └──────▶ back to ObligationGenerator
```

### 2.2 Authority model

| Layer | Authority | Rebuildable | Notes |
|---|---|---|---|
| Raw object store (S3/MinIO) | **Authoritative** | n/a | Bytes first, content-addressed |
| Append-only life stream | **Authoritative** | n/a | Immutable; the only thing an invariant is a fold over |
| Relational operational store | **Authoritative** | n/a | Observations, obligations, decisions, revisions, tenancy |
| Investigation context | **Authoritative** | Folded from stream + decisions | Versioned, superseding, never rewritten |
| Knowledge graph / search / temporal / analytical / topological / spatial | Derived | **Yes, fully** | Each with fingerprint, checkpoint, rebuild path |

The rule enforced by tests: **a derived layer may be deleted and rebuilt, and the
rebuilt digest must match. A non-derived layer may not be deleted.**

### 2.3 Component boundaries in the context kernel

The five responsibilities the specification requires already exist as
`ObligationGenerator`, `SatisfactionEvaluator`, `ActionProposer`, `DecisionRecorder`
and `RevisionManager`. A module-level test already asserts they stay separate. The
plan keeps that structure and fixes what is missing:

- `DecisionRecorder` becomes durable (new store method + migration).
- `ContextEngine` gains the ability to be constructed per investigation rather than
  once per process.
- `ContextDefinition` is introduced as a real object with its own identity space,
  matching the decision already recorded for it.
- `CognitiveLoop.tick()` receives its saturation input from the fabric's own
  completeness assessment rather than from a default.

---

## 3. The critical defects this plan attacks, in priority order

Each is a verified finding, not an inference. File and line references are in
`audit/current-state-audit.md`.

| # | Defect | Consequence | Work package |
|---|---|---|---|
| D1 | The loop's saturation input is never supplied on the live path | No obligation can ever be satisfied. The loop cannot close. | WP-A |
| D2 | `DecisionRecorder` holds decisions in a process-local list | "Why did we do this?" is unrecoverable after restart | WP-B |
| D3 | Three producers publish observations without the gate; four identity schemes exist; one is a random UUID | Evidence with no bytes behind it; identity collision or divergence | WP-C |
| D4 | The default event identifier is a random value, pinned as such by a test | Redelivery creates a new logical event; idempotency is opt-in luck | WP-C |
| D5 | The incremental reducer that implements digest-gated revision has no caller; the live path mints a revision per sweep unconditionally | Revision inflation; no replay determinism | WP-D |
| D6 | The one writer that could make observation+membership atomic is dead code, and splits its own transaction anyway | Invariant can vanish while the entity looks present | WP-C |
| D7 | The live ingestion path drops every runtime artefact without counting | Silent zero-yield acquisition | WP-C |
| D8 | Automatic identity merge against a profile whose own version reads `UNCALIBRATED-v1` | False merges presented as resolved identity | WP-E |
| D9 | The independence model exists and is unused; the live path counts hostnames | Copied evidence scored as independent confirmation | WP-E |
| D10 | Spans are hashed into identifiers and discarded; one field means both a byte offset and a segment index | Conclusions cannot be opened at source | WP-F |
| D11 | `CURRENT` route is a byte-identical duplicate; `INTERVAL` is not exposed | Time semantics untested against reality | WP-D |
| D12 | No spatial projection exists; retrieval advertises a semantic mode nothing reads | Interfaces promise capabilities the platform lacks | WP-G |
| D13 | Topological analysis has no production caller and persists nothing | A plane that costs maintenance and returns nothing | WP-G |
| D14 | The whole feedback plane has no production caller | The loop has no closing signal from analyst review | WP-H |
| D15 | Root `pytest` collects vendored trees (831 errors); `bench` fails collection | No trustworthy single-command baseline | WP-0 |

---

## 4. Work packages

Ordered by dependency, not by ambition. Each package ends with a runnable test and a
recorded command.

### WP-0 — Trustworthy baseline (blocking, everything depends on it)

1. Set `testpaths` in the root pytest configuration so vendored `donors/` and `tmp/`
   are not collected.
2. Fix the `bench` collection error (package shadowing: `bench/__init__.py` vs
   `bench/bench/`).
3. Triage the 22 existing failures into "caused by this feature", "pre-existing and
   in scope", "pre-existing and out of scope", each with a reason.
4. Record the command and raw output as the regression floor.

**Exit**: one command runs the platform suite; the failure count is known and
attributed.

### WP-A — Make the loop closable (the P1 defect)

1. Supply the loop's saturation input from the fabric's completeness assessment on
   the live path, instead of a default that can never saturate.
2. Propagate the science-plane saturation verdict into a saturation state the engine
   can read, rather than reading it as a bare string after the tick.
3. Make the loop's stop reason reach the caller. Today the termination report is
   computed and discarded on the saturation path.
4. Carry the analyst's feedback into the tick, instead of an empty default.
5. Suppress a repeated action that produced no gain until a stated condition changes.

**Exit**: an integration test drives one obligation from open to satisfied via a real
observation, and the termination report names the reason.

### WP-B — Durable decision record

1. Add a decision table and store methods; move `DecisionRecorder` off its in-memory
   list.
2. Add the migration.
3. Contract test against a real database: record, restart, retrieve, compare.

**Exit**: SC-005 passes against a real database.

### WP-C — One gate, one identity, atomic enough to be honest

1. Route the three bypassing producers through the gate; make a producer unable to
   publish an observation it did not store.
2. Collapse the four identity derivations into one. The zero-layer gate's random
   identifier goes away.
3. Replace the random default event identifier with a content-derived one, and update
   the contract test that currently pins the random behaviour.
4. Make the artefact-dropping path count what it drops.
5. Persist the capture record that is currently constructed and discarded.
6. Define the storage-ordering guarantee honestly: bytes first, observation second,
   publication third, with the repair path for each of the three failure windows
   stated rather than implied.

**Exit**: every production observation resolves to stored bytes; redelivering an
event yields one logical observation; no producer can mint an unstored observation.

### WP-D — Accumulated state, digest-gated revision

1. Wire the incremental reducer into the live materialization path and retire the
   unconditional revision minting.
2. Make the as-of and interval queries genuinely distinct and expose interval.
3. Add the closing fixture test: current vs as-of vs interval on data where they
   differ, plus a late-arriving record that must not rewrite the past.
4. Restart-digest test.

**Exit**: SC-003, SC-004, SC-006 pass.

### WP-E — Admission without uncalibrated auto-merge

1. Refuse automatic merge when the profile's calibration state is undeclared or empty;
   route those cases to review.
2. Replace the hostname-count corroboration with the dependency-group model that
   already exists, at the live call site.
3. Give the zero-layer matcher the accept/reject/defer vocabulary it lacks and stop
   defaulting its threshold to zero.

**Exit**: no merge occurs without a declared calibration identity; copied evidence
does not raise the independence count.

### WP-F — Spans that survive to the finding

1. Separate the positional field into distinct, typed locators (byte range, page,
   box, segment index, row) so two producers cannot conflate them.
2. Carry the span forward through the resolution layer instead of hashing it away.
3. Provenance completeness gate: a finding either resolves its chain or is marked
   unsupported.

**Exit**: SC-001 and SC-014 pass; the document-intelligence fixture opens an exact
span.

### WP-G — Projections that are real

1. Every projection declares purpose, inputs, checkpoint, fingerprint, incremental
   path, rebuild path and staleness signal — as enforced data, not as prose.
2. Rebuild-to-identical-digest test for each projection that claims one.
3. Refuse honestly: a requested mode with no implementation returns a named refusal.
4. Decide each currently-inert plane: wire topological analysis into a consumer, or
   mark it experimental with a kill switch. Do not leave both.

**Exit**: SC-008 passes; no interface advertises an unimplemented capability.

### WP-H — Close the loop from analyst review

1. Wire the feedback plane to the tick; record review actions as history.
2. Surface unknown, uncovered, blocked and conflicting knowledge, not only findings.

**Exit**: analyst review changes the next proposed action, in a test.

### WP-I — Open world

1. Unknown predicates survive the full path, flagged.
2. Discarding one requires an explicit versioned policy decision that is recorded.

**Exit**: SC-007 passes.

### WP-J — Evidence of work

1. Audit document with the declared/implemented/tested/wired/proven table.
2. Donor matrix with verified verdicts.
3. Decision records for every gate changed.
4. Benchmark suite and recorded raw measurements.
5. Reconciliation of the stale documents named in the audit.

---

## 5. What this plan deliberately does not do

| Not doing | Why |
|---|---|
| Adding a graph database, message broker, datastore or model provider | No measured failure attributable to the existing choice |
| Integrating a parsing donor before the provenance fix | Spans are currently lost downstream; a better parser feeding a lossy pipeline buys nothing |
| Integrating a resolution donor before the calibration gate | An uncalibrated threshold is the defect; a better model does not fix it |
| Adding a retrieval fusion library before the retrieval stages are separated | Fusion is meaningless while candidate generation, scoring and policy ranking are conflated |
| Adding a spatial index before there is spatial data | There is no geometry anywhere in the substrate; an index over nothing is not a capability |
| Adding a graph neural network | No time-split benchmark exists to admit one, and no baseline to beat |
| Rewriting the topological plane | The audit says the problem is wiring and persistence, not the mathematics |
| Deleting the dead pipelines outright | Removing them before the replacements are live would lose the only integration coverage they have; they are marked and fenced instead |

---

## 6. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Fixing the loop's closure path changes existing behaviour other tests depend on | High | High | WP-0 triage first; every behaviour change lands with its own test; the floor is recorded before the first change |
| Collapsing four identity schemes breaks stored references | Medium | High | Content-addressed derivation means old ids remain derivable; a compatibility reader is kept for one release |
| Making decisions durable adds write amplification on the tick path | Medium | Medium | Decisions are small and infrequent; measure before optimising |
| Digest-gated revision suppresses revisions some consumer expects | Medium | Medium | The supersession chain is preserved; consumers read heads, not counts |
| The end-to-end test cannot run because a service is absent | Medium | High | SC-002 requires naming the blocker precisely; an unrunnable test is recorded as unrunnable, never as passing |

---

## 7. Verification strategy

Four tiers, all recorded with commands and exit codes:

1. **Unit** — pure contracts, determinism, refusal codes.
2. **Contract** — every implementation against the store seam, against a real database
   where the claim is about durability.
3. **Integration** — composition through the actual service objects, not fakes,
   wherever the claim is about wiring.
4. **End-to-end** — one observation traversing the whole loop on the real stack
   profile, or a named blocker.

A claim is only ever labelled by the tier that actually ran.

---

## 8. Deliverables in this feature directory

```
specs/028-closed-research-loop/
├── spec.md                      what and why
├── plan.md                      this file
├── data-model.md                the contracts, typed
├── tasks.md                     the ordered work, with status vocabulary
├── research.md                  audit method and donor verification method
├── quickstart.md                how to run each tier
├── audit/
│   └── current-state-audit.md   WP0 evidence, the declared/implemented table
├── donors/
│   └── donor-matrix.md          every candidate, with a verdict
├── decisions/                   ADRs for every gate changed
├── contracts/                   schema and event evolution rules
└── benchmarks/                  scenarios, fixtures, recorded measurements
```