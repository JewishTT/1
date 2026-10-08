# ADR-0029 — Epistemic algebra: Belnap four-valued support, proposition-scoped, separate from score

**Status**: Accepted (Wave 0, ADR-025-02)
**Feature**: `025-context-reality-approximation-engine`
**Baseline**: v2 §13, Appendix G.4, Appendix T FR-025-088

## Context

v1 specified four-valued truth state but left three things undefined, and each of them was a
place where a plausible implementation quietly drops the fourth value:

1. **What carries it.** Not the hypothesis — a *Proposition* (§3.13). A hypothesis is a
   compound statement over propositions; its truth state is composed from theirs.
2. **How support accumulates.** v1 had no rule, so implementations invented one, usually
   "last writer wins" or "majority". Both destroy information.
3. **How it relates to contradiction and to score.** v1 left `BOTH` a floating value with no
   obligation to produce a `Contradiction`, and let `confidence` sit next to it with no
   declared relationship.

Zero donors in this repository implement anything of the kind (research §3.7). There is no
prior art to defer to, which raises the stakes on getting the algebra right rather than
lowering them.

## Decision

**1. Representation.** `TruthState = (positive_support: bool, negative_support: bool)`, stored
as two independent boolean columns on a Proposition row. Never an enum with four members: an
enum makes `(true,true)` a value someone eventually omits from a `switch`.

**2. Five operations, normative.**

```text
negate(s)    = (n, p)
accumulate   = (p1 ∨ p2, n1 ∨ n2)   knowledge-join, same proposition
consensus    = (p1 ∧ p2, n1 ∧ n2)   knowledge-meet
and          = (p1 ∧ p2, n1 ∨ n2)   truth-order conjunction
or           = (p1 ∨ p2, n1 ∧ n2)   truth-order disjunction
```

`accumulate` is the only operation used to build `truth_state(P)`.

**3. Contributions.** Only *admissible* evidence contributes (passed admission; a
coverage-qualified absence below the profile's thresholds contributes nothing — ADR-0036).
Unadmitted proposals contribute nothing. Contributions are restricted to the same scope and
time qualifier.

**4. Independence does not touch the flags.** Dependency groups (ADR-0036) change *weights*
in scores, never `positive_support`/`negative_support`. Those are existence claims: if one
admissible item supports P, the flag is set, regardless of how many syndications exist
elsewhere. Conflating the two is how a system ends up claiming "nobody supports this" while
holding forty copies of the same press release.

**5. `BOTH` implies a Contradiction.** `truth_state(P) = BOTH` ⇒ a `Contradiction` exists in
the same revision whose two sides are the positive and negative support sets. The converse
does not hold: a numeric or structural contradiction may exist between two *different*
propositions with neither in `BOTH`.

**6. Resolution never deletes support.** `EXPLAINED`/`RESOLVED` records an explanation
(different time qualifier, different referent) and may create *new, distinct* propositions by
re-scoping. The prior revision still shows `BOTH`. A contradiction is not a switch.

**7. Score is a different field with a declared target.** `truth_state` never converts to a
probability. Every score carries `kind` (§14.3), `target` (the estimand), `model_ref`, and
`hypothesis_space_ref` where applicable. `truth_state = BOTH` with `score 0.88` is legal and
means the two facts are about different things.

## Consequences

**Positive**

- Contradiction cannot be lost by a data path, because no single field holds it.
- Score and support can be reasoned about independently — which is the whole point.
- Compounding is explicit: a hypothesis's truth state is derived, never asserted.

**Costs, accepted**

- Every read that needs "is this true?" must now branch four ways. This is a real
  ergonomic cost paid at roughly ten call sites.
- Proposition modelling is additional work that v1 did not ask for.

**Not changed**

- The six time axes. Scope/time qualifiers reference them; they are not modified.
- Entity identity. Proposition identity is content-addressed separately.

## Verification

- [ ] Full truth tables for all five operations, all four inputs — 4⁵ cases for binaries,
      4 for `negate`.
- [ ] Lattice laws: idempotence, commutativity, associativity, absorption, De Morgan under
      `negate`.
- [ ] Property test: **no code path maps `(true,true)` to `true`** — checked across storage,
      API serialisation, projection and UI props.
- [ ] Round trip: `(true,true)` survives save → API → UI → projection unchanged.
- [ ] `BOTH` at rest always has a `Contradiction` in the same revision (invariant test).
- [ ] Syndicated evidence (three copies) still sets the flag once; it does not set it twice
      and does not clear it.