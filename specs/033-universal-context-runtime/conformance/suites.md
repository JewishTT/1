# Conformance Suites — Feature 033

**Feature**: `033-universal-context-runtime`
**Requirement**: FR-078, FR-080, SC-014 — the eighteen suites of §32.1 must exist and pass before the
runtime is called complete.

---

## Why a status table, not a claim

§32 states the rule plainly: a capability is not `production-ready` because its code imports or its
unit tests pass. The lifecycle is
`DISCOVERED → LICENSE_REVIEWED → CONTRACTED → UNIT_TESTED → CONTRACT_TESTED → BENCHMARKED → WIRED → E2E_PROVEN → OBSERVED_IN_OPERATION → APPROVED_FOR_SCOPE`,
and `BLOCKED`, `NOT_RUN` and `UNKNOWN` are first-class statuses.

The table below is the truthful current state. **Every suite is `NOT_RUN`**, because Phase A has not
executed. That is not an omission; it is the state, and it blocks the release gate until each row has
a real result.

---

## Status vocabulary

| Status | Meaning |
|---|---|
| `PASS` | ran, asserted, and passed; evidence recorded |
| `FAIL` | ran and failed; defect linked |
| `BLOCKED` | could not run; dependency named |
| `NOT_RUN` | deliberately not executed yet; reason recorded |
| `UNKNOWN` | ran with an inconclusive result |

A suite is never `PASS` because it was written. It is `PASS` when it ran and its evidence exists.

---

## The eighteen suites

| # | Suite | What it proves | Status | Evidence |
|---|---|---|---|---|
| 1 | Context revision | identical inputs do not create meaningless revisions; material policy/evidence/ontology change does | `NOT_RUN` | — |
| 2 | Open-world round trip | unknown type or predicate survives storage, events, API, export and UI | `NOT_RUN` | — |
| 3 | Evidence grounding | a finding opens the exact span and raw artifact after restart and rebuild | `NOT_RUN` | — |
| 4 | Temporal correctness | `AS_OF` returns what was known then; late evidence alters the current reconstruction without rewriting past knowledge | `NOT_RUN` | — |
| 5 | Epistemic correctness | `NEITHER`/`TRUE_ONLY`/`FALSE_ONLY`/`BOTH` survive every surface; no observation is not negative evidence | `NOT_RUN` | — |
| 6 | Identity safety | similarity and `A≈B`, `B≈C` never commit a merge; conflicting attributes require adjudication | `NOT_RUN` | — |
| 7 | Conflict correctness | unit/scope/time mismatch is not a factual conflict; independent evidence is separated from syndicated copies | `NOT_RUN` | — |
| 8 | Abstraction accounting | every summary or model drills back to evidence and declares omitted scope and caveats | `NOT_RUN` | — |
| 9 | Tool permission | capability denied when purpose, scope, tenant or egress requirements fail; a model cannot override the gate | `NOT_RUN` | — |
| 10 | Replay and idempotency | redelivery or retry inflates nothing; cold rebuild matches the canonical digest | `NOT_RUN` | — |
| 11 | Budget correctness | tasks cannot exceed per-tenant, per-context, per-source, per-host or token budgets through a default-allow gap | `NOT_RUN` | — |
| 12 | Completion correctness | exhausted queue or retries never equals done; residual unknowns and skipped scope appear | `NOT_RUN` | — |
| 13 | Projection recovery | delete/rebuild from the canonical cut yields the correct digest and freshness manifest | `NOT_RUN` | — |
| 14 | Security corpus | SSRF, redirect, DNS rebinding, decompression bombs, oversized body, prompt injection, secret leakage, cross-tenant queries | `NOT_RUN` | — |
| 15 | Model/provider drift | changes are benchmarked; prior outputs keep old fingerprints and stay inspectable | `NOT_RUN` | — |
| 16 | Multimodal alignment | OCR, ASR, frames and structured extracts link back to accurate location or time, with tolerance tests | `NOT_RUN` | — |
| 17 | Branch semantics | analytical branches do not silently mutate canonical facts; merge conflicts are explicit | `NOT_RUN` | — |
| 18 | Adversarial epistemic suite | false corroboration, deceptive timestamps, misleading entity names, circular citation, selective evidence | `NOT_RUN` | — |

---

## How a suite is recorded

Each suite appends a row to its own record under `conformance/suite-<nn>.md`:

```text
Suite:        <name>
Run at:       <timestamp>
Commit:       <git sha + dirty state>
Command:      <exact command>
Exit status:  <code>
Result:       PASS | FAIL | BLOCKED | NOT_RUN | UNKNOWN
Corpus:       <fixture ids and versions>
Assertions:   <n passed / n failed / n skipped>
Evidence:     <artifact path or CI job id>
Notes:        <defects, accepted alternatives, known limitations>
```

A row with no command or no exit status is not a result. §11.2 of the v1.0 blueprint and SC-013 of
this feature both require that a benchmark print its inputs, configuration, versions, exit status,
runtime, resources and source count — and that an unavailable measure be `null` with a named reason.

---

## Release gate

The release gate (T084) requires:

- every suite has a status;
- every `FAIL` has a linked defect and a disposition;
- every `BLOCKED` has an owner and a next action;
- every `NOT_RUN` is explicitly accepted by the owner as a known limitation, with the consequence
  named;
- no capability is `APPROVED_FOR_SCOPE` without `E2E_PROVEN`.

A release with `NOT_RUN` suites is permissible **only** as a declared limitation. A release with
untracked `NOT_RUN` suites is not.
