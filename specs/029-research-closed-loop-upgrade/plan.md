# Implementation Plan: COGNITIVE Master Platform Upgrade

**Feature**: 029-research-closed-loop-upgrade
**Spec**: [spec.md](./spec.md) · **Audit**: [audit/current-state-audit.md](./audit/current-state-audit.md)
**Donors**: [donors/donor-matrix.md](./donors/donor-matrix.md)
**Status**: WP-0 and WP-A delivered and measured. WP-B onward open.
**Date**: 2026-10-13

---

## 1. The finding that determines the whole plan

The audit (`audit/current-state-audit.md`) produced one result that outranks everything
else in the input document's donor list:

**The platform already contains almost every capability it needs — and they are not
connected to each other.**

An obligation ledger exists. A satisfaction evaluator exists. A decision recorder exists.
A revision manager exists. A five-fold absence algebra exists. An independence model
exists. An append-only life stream exists. An incremental invariant reducer exists.
Together they are individually unit-tested and collectively inert.

`CognitiveLoop.tick` has exactly one production call site. It passes no saturation
evidence. `_reevaluate` fabricates a basis with `marginal_gain=1.0` — above every
threshold the loop ships with — so `is_saturated` is a constant `False`, so the
satisfaction evaluator never returns satisfied, so **no obligation can ever reach a
terminal state**. The platform's central claim, that it investigates to a conclusion,
had no reachable code path.

Everything else follows from this. The plan is therefore not "add a context engine" or
"integrate donors". It is:

1. **Connect what exists** and remove what duplicates it.
2. **Make the dead paths either live or absent.**
3. **Prove the result end to end.**
4. **Add capability only where the audit shows a genuine gap.**

New capability is added last, because every audit of the substrate found the same three
violations already present in the platform's own code: observations published without
stored bytes, four disagreeing identity schemes, and spans discarded before reaching a
finding. Adding producers multiplies exactly what is already broken.

---

## 2. Target architecture

### 2.1 The loop

```
              ┌───────────────────────────────────────────────┐
              │ Question Definition  (CXD-, immutable)        │
              │  objective · scope · policy · temporal frame  │
              └──────────────────┬────────────────────────────┘
                                 │ one definition, many investigations
              ┌──────────────────▼────────────────────────────┐
              │ Investigation Context (CXI-, revisable)        │
              │  revision N ──supersedes──▶ revision N+1       │
              │  obligations · hypotheses · evidence           │
              │  conflicts · unknown · decisions               │
              └──────────────────┬────────────────────────────┘
                                 │
  ┌──────────────────────────────┼──────────────────────────────┐
  │                              │                              │
┌─▼───────────────┐     ┌────────▼─────────┐        ┌───────────▼─────────┐
│ ObligationGen.  │────▶│ ActionProposer   │───────▶│ Acquisition         │
│ gaps → obligat. │     │ explainable,     │        │ adapters → workers  │
└─────────────────┘     │ multi-objective  │        └───────────┬─────────┘
                      │ hard constraints  │                    │ ONE gate
┌─────────────────┐    └────────┬─────────┘         ┌───────────▼─────────┐
│ SatisfactionEval.│◀───────────┘                     │ Observation Gate    │
│ independence ·   │      ▲                            │  bytes FIRST        │
│ conflicts · gaps │      │                            │  then observation   │
└────────┬────────┘      │                            │  then publish       │
         │               │                            │  derived identity   │
         │     ┌─────────┴──────────┐                 └───────────┬─────────┘
         │     │ DecisionRecorder   │                             │
         │     │ durable (M1)       │                  ┌──────────▼─────────┐
         │     └────────────────────┘                  │ append-only stream │
         │                                             │ (immutable)        │
         │    ┌──────────────┐                          └──────────┬─────────┘
         └───▶│ InvariantRed.│◀── digest-gated, incremental ──────┘
              │ new revision  │       revision only when digest moves
              │ ONLY on move  │
              └──────┬───────┘
                     │
   ┌─────────────────┼─────────────────┬──────────────────┐
   │                 │                 │                  │
┌──▼────────┐  ┌─────▼──────┐  ┌───────▼───────┐  ┌───────▼────────┐
│ graph     │  │ search     │  │ temporal /    │  │ TDA / spatial / │
│           │  │            │  │ OLAP          │  │ analytics       │
└──┬────────┘  └─────┬──────┘  └───────┬───────┘  └───────┬────────┘
   └─────────────────┼─────────────────┼──────────────────┘
              ┌──────▼─────────────────▼──────┐
              │ Findings + epistemic state   │
              │ + traceable derivations      │
              └──────┬────────────────────────┘
                     │ analyst review
                     └──▶ ObligationGenerator  ↺
```

### 2.2 Authority model

| Layer | Authority | Rebuildable | Notes |
|---|---|---|---|
| Raw object store | **Authoritative** | n/a | Bytes first, content-addressed |
| Append-only life stream | **Authoritative** | n/a | Immutable; the only thing an invariant is a fold over |
| Relational operational store | **Authoritative** | n/a | Observations, obligations, decisions, revisions, tenancy |
| Investigation context | **Authoritative** | Folded from stream + decisions | Versioned, superseding, never rewritten |
| Graph / search / temporal / OLAP / TDA / spatial | Derived | **Yes, fully** | Each with fingerprint, checkpoint, rebuild path |

Enforced by test: a derived layer may be deleted and rebuilt and the digest must match.
A non-derived layer may not be deleted.

### 2.3 Context kernel — five responsibilities, not a god object

They already exist and a module test already asserts they stay separate. The plan keeps
the structure and fixes what is missing:

| Responsibility | File | State today | Gap |
|---|---|---|---|
| `ObligationGenerator` | `engine.py:100` | pure, rule-versioned | none |
| `SatisfactionEvaluator` | `engine.py:185` | pure | reachable only via the tick |
| `ActionProposer` | `engine.py:264` | pure | ranking components not exposed (FR-012/013) |
| `DecisionRecorder` | `engine.py:345` | **in-memory list** | **not durable — WP-B** |
| `RevisionManager` | `engine.py:407` | durable | revision cause not recorded — WP-B2 |

---

## 3. Work packages

Ordered by dependency. Each ends with a runnable test and a recorded command.

### WP-0 — Trustworthy baseline — **DELIVERED**

`testpaths` + `norecursedirs` set; stray `bench/__init__.py` deleted; `bench` on the path.
`pytest -q` now collects 4336 tests with **0 collection errors** and runs in one command.
22 failures triaged by cause.

### WP-A — Make the loop closable — **DELIVERED**

The saturation basis resolves supplied → fabric pass → what the outcomes actually
reported. Unknown stays unknown (`coverage_known` / `marginal_gain_known`), because
collapsing "not measured" into `0.0` reads as *measured and zero* and closes an
obligation on an absence. Stop reason reaches the caller on every terminal path.

15 new tests. Baseline 22/4273 → 22/4288. Zero new failures.

### WP-B — Durable decision record

1. `research_decisions` table + migration M1.
2. `ContextStore` decision methods; `DecisionRecorder` off the in-memory list.
3. Content-address `decision_id` over grounds/inputs/alternatives/actor/outcome so the
   same decision reasoned twice is the same decision.
4. Contract test on a real database: record → restart → retrieve → compare. (SC-005)

### WP-B2 — Definitions, revision cause, explicit ranking

1. `question_definitions` table + `investigation_contexts.definition_id` (FR-006/007).
2. `RevisionCause` — input events, rule version, operator versions, parameters,
   predecessor, derived changes, unresolved warnings (FR-008/009).
3. Obligation blocking capability + no-gain suppression with a condition fingerprint
   (FR-011).
4. Expose action-ranking components; store raw features, calibrated probability and
   policy decision separately (FR-012/013).

### WP-C — One gate, one identity

1. Refuse to publish an observation whose bytes were not stored. Closes the
   `sources/connector.py:161` hole, where the event carries no `raw_ref` and no store
   write happens.
2. Route the remaining bypassing producers (`worker_acquisition.py:442`,
   `pow_run.py:187`) through the gate.
3. Collapse four identity derivations into one; v2 schema with v1 dual-read.
4. Replace the random default event id; invert the contract test that pins it.
5. Count dropped runtime artefacts instead of `continue`.
6. Persist the capture record that is currently constructed and discarded.
7. Name the repair path for each of the four failure windows (FR-029/030).
8. Also fix `postgres_store.py:572`, which calls a `from_dict` that does not exist.

### WP-D — Accumulated state, digest-gated revision

Wire `InvariantReducer` into the live path; retire unconditional revision minting.
Make `CURRENT` a distinct query; expose `INTERVAL` beside `AS_OF`. Fixtures for
current/as-of/interval divergence, late-arriving evidence, and restart digest equality.

### WP-E — Admission without uncalibrated auto-merge

Refuse auto-merge when `calibration_id` is null. Replace hostname corroboration with
dependency groups at the live call site. Give the zero-layer matcher accept/reject/defer
instead of a zero default threshold.

### WP-F — Spans that survive to the finding

Typed `Locator` with `UNKNOWN` preserved. Split the overloaded positional field; dual-read
legacy rows. Carry the locator through the resolution layer. Provenance completeness gate
on findings.

### WP-G — Operator envelope

One versioned envelope for every analytical step (FR-025…FR-030). Explicit status so an
absence cannot masquerade as an empty success. Uncertainty as a vector. Replay and
idempotency keys. Tenant and policy identity.

### WP-H — Projections that are real

`ProjectionContract` as enforced data. Rebuild-to-identical-digest per projection.
Refuse unimplemented retrieval modes. Decide each inert plane — wire a consumer or mark
experimental with a kill switch. Do not leave both.

### WP-I — Open world and absence algebra

Unknown predicates survive the full path, flagged. Discarding requires a recorded
versioned policy decision. Five absence states carried through to a finding.

### WP-J — Retrieval, LLM and security

Separate candidate generation, scoring, policy ranking and action selection, each with
its own metrics. Offline/mock providers and hermetic tests. Per-operator limits, kill
switches, retry budgets, backpressure, supply-chain record.

### WP-K — Evidence of work

Benchmarks, donor re-verification, document reconciliation, final report.

---

## 4. What this plan deliberately does not do

| Not doing | Why |
|---|---|
| Adding a datastore, broker, graph engine or model provider | No measured failure attributable to the existing choice |
| Integrating a parsing donor before WP-F | Spans are currently lost downstream; a better parser feeding a lossy pipeline buys nothing |
| Integrating a resolution donor before WP-E | An uncalibrated threshold is the defect; a better model does not fix it |
| Adding a fusion library before retrieval stages are separated | Fusion is meaningless while generation, scoring and policy ranking are conflated |
| Adding a spatial index | There is no geometry anywhere in the substrate. An index over nothing is not a capability |
| Adding a graph neural network | No time-split benchmark exists to admit one, and no baseline to beat |
| Rewriting the topological plane | The problem is wiring and persistence, not the mathematics |
| Deleting dead pipelines outright | Removing them before replacements are live would lose the only integration coverage they have. They are marked and fenced first |

**Donor integration is scheduled, not abandoned.** Constitution requires an explicit
owner decision where a donor conflicts with a platform boundary; that decision is
recorded in `donors/donor-matrix.md` §6 and re-asserted per donor at integration time.

---

## 5. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Fixing the closure path changes behaviour other tests depend on | High | High | WP-0 triage first; every change lands with its own test; the floor is recorded before the first change |
| Collapsing four identity schemes breaks stored references | Medium | High | Content-addressed derivation keeps old ids derivable; a v1 reader is retained for one release |
| Durable decisions add write amplification on the tick path | Medium | Medium | Decisions are small and infrequent; measure before optimising |
| Digest-gated revision suppresses revisions a consumer expects | Medium | Medium | The supersession chain is preserved; consumers read heads, not counts |
| The end-to-end test cannot run because a service is absent | Medium | High | SC-002 requires naming the blocker precisely; an unrunnable test is recorded as unrunnable, never as passing |

---

## 6. Verification strategy

Four tiers, each recorded with command and exit code:

1. **Unit** — pure contracts, determinism, refusal codes.
2. **Contract** — every implementation against the store seam, against a real database
   where the claim is about durability.
3. **Integration** — composition through the actual service objects, not fakes,
   wherever the claim is about wiring.
4. **End-to-end** — one observation traversing the whole loop on the real stack profile,
   or a named blocker.

A claim is labelled only by the tier that actually ran.