# ADR-0038 — Branches and the analyst in the loop

**Status**: Accepted (Wave 0, ADR-025-11)
**Feature**: `025-context-reality-approximation-engine`
**Baseline**: v2 §6.4, §16A, §38, §49.1, Appendix L.8, N.9, N.11

## Context

Two related hazards, one cause: **derived state being mistaken for authoritative state.**

A counterfactual branch concludes something the mainline never observed. Nothing stops that
conclusion from surfacing next to a real finding in a UI table, because the data model has
only one stream of revisions.

An analyst disagrees with the model and overrides a hypothesis status. If the override
replaces the model value, the audit trail loses the fact that the model disagreed. If it is
refused, the analyst cannot correct anything, which pushes them to work outside the platform
where nothing is recorded.

Both are the same error: a state transition that is not labelled with its authority.

## Decision

**1. `ContextBranch` is part of the revision key.**

```yaml
ContextBranch:
  branch_id: BRN-...
  context_id: CXI-...
  branch_kind: MAINLINE | SCENARIO | COUNTERFACTUAL | WHAT_IF
  forked_from: {branch_id, revision}
  intervention_set: [...]
  assumptions_overlay: [...]
  status: ACTIVE | ARCHIVED
```

Revisions are monotonic per `(context_id, branch_id)`. A fork's first revision has a parent in
the source branch (ADR-0030 invariant 2).

**2. A non-mainline branch never writes into mainline.** Not revisions, not evidence, not truth
states, not admission decisions. Branch contents are derived views over mainline evidence plus
the declared overlay.

**3. Branch label is mandatory in every response body and every UI surface.** A counterfactual
result can never be rendered as an observed or inferred finding on the mainline.

**4. Merging a branch into mainline is not an operation.** There is no API, no job, no admin
path. A scenario may only be **cited** as a hypothesis premise with
`provenance = BRANCH_DERIVED`. This is the enforcement mechanism: if merging does not exist,
branch contamination cannot occur through it.

**5. Analyst inputs are observations or decisions — never edits.**

```yaml
AnalystAssertion:  assertion_id: ANL-...  principal, statement, basis, admission
AnalystDecision:   decision_id: DEC-...  kind, target_ref, justification (required), principal
```

Assertion kind `ACCEPT_HYPOTHESIS | REJECT_HYPOTHESIS | PIN_ASSUMPTION | DISMISS_OBLIGATION |
APPROVE_ACTION | REJECT_ACTION | SET_PRIORITY | OVERRIDE_STATUS`.

**6. An override never replaces model state.** It is stored as a decision and displayed as
`OVERRIDDEN_BY_ANALYST` **beside** the model-derived value. Both remain visible. The model
value is not rewritten, and downstream explanations flag the override.

**7. `justification` is required, not optional.** An override without a reason is rejected at
the API boundary. This is what makes the audit question "who overrode what, and why"
answerable (Appendix L.8).

**8. Analyst assertions are subject to independence accounting.** An analyst repeating a
source is not independent of it (ADR-0036). The analyst is an evidence source, not a
shortcut around evidence accounting.

**9. Pinned assumptions are inputs to re-evaluation**, flagged `PINNED` in every downstream
explanation.

**10. Mainline-isolation is enforced by the read path, not by convention.** Queries scoped to a
branch cannot see or be seen by another branch without an explicit branch-scoped read.

## Consequences

**Positive**

- Counterfactuals are answerable without contaminating findings.
- Analyst corrections are possible and fully audited.
- "The model thought X, the analyst thought Y, here is both" becomes a first-class state.

**Costs, accepted**

- Branch isolation must be enforced in every query path; a leak is a correctness bug, not a
  cosmetic one.
- Analysts must write justifications. Friction accepted: an unexplained override is
  indistinguishable from tampering.

**Not changed**

- Mainline revision semantics.
- Action governance (ADR-0037): approval remains an analyst decision routed through the
  existing capability boundary.

## Verification

- [ ] Property test: **branch writes never appear in mainline queries.**
- [ ] Counterfactual conclusion is visible only on its branch (N.11).
- [ ] Every API response for a non-mainline read carries the branch label.
- [ ] There is no merge endpoint, job or admin path — asserted by an API surface test.
- [ ] Analyst override: model value unchanged, decision stored with justification, both shown
      (N.9).
- [ ] Override without justification is rejected with `422`.
- [ ] Analyst assertion repeating a source does not raise `n_eff`.
- [ ] Pinned assumption appears as `PINNED` in every downstream explanation trace.