# ADR-0032 — Hypothesis lifecycle and hypothesis space

**Status**: Accepted (Wave 0, ADR-025-05)
**Feature**: `025-context-reality-approximation-engine`
**Baseline**: v2 §15, §17.7, §18, Appendix F.2, N.7

## Context

v1 had three defects that made the lifecycle ambiguous in practice.

1. `STRENGTHENED` and `WEAKENED` appeared as lifecycle *states* next to `ACTIVE`. A hypothesis
   that was already active and then gained evidence became a different state, so "what is the
   state of H?" had two defensible answers and the answer changed over time for reasons that
   were not transitions.
2. There was no transition table. Implementations wrote their own, and they disagreed.
3. Posteriors and information gain were computed over "the hypotheses" without saying which
   hypotheses. A posterior over the set you happened to think of sums to 1 by construction and
   is therefore meaningless — the missing explanations have been silently deleted rather than
   weighed.

The third is the most dangerous, because the resulting numbers look correct.

## Decision

**1. Status is a state, trend is derived.**

```text
status ∈ { PROPOSED, ACTIVE, CONTESTED, UNRESOLVED, CONFIRMED, DISCARDED, SUPERSEDED }
trend ∈ { STRENGTHENED, WEAKENED, STABLE, NEW }     # derived vs previous revision
```

`trend` is computed, never written directly. A caller cannot assert that a hypothesis
strengthened.

**2. Normative transition table.**

```text
PROPOSED   → ACTIVE | DISCARDED
ACTIVE     → CONTESTED | UNRESOLVED | CONFIRMED | DISCARDED | SUPERSEDED
CONTESTED  → ACTIVE | UNRESOLVED | CONFIRMED | DISCARDED | SUPERSEDED
UNRESOLVED → ACTIVE | CONTESTED | DISCARDED | SUPERSEDED
CONFIRMED  → CONTESTED | SUPERSEDED
DISCARDED  → ACTIVE (new evidence / profile change, as a new revision) | SUPERSEDED
SUPERSEDED → terminal
```

Forbidden: `PROPOSED → CONFIRMED`; any transition without a recorded `DecisionTrace`;
`SUPERSEDED → *`.

`CONFIRMED` is revisable by contrary evidence — confirmation is not immunity. The profile
declares the threshold (independent groups, calibration, refutation attempts survived). It
never means metaphysical truth.

**3. Status lives on the revision.** A transition creates a new hypothesis revision. Previous
evaluations stay readable forever; historical hypothesis assessments are a query, not a
reconstruction (ADR-0030).

**4. Every hypothesis lives in a `HypothesisSpace`.** The space declares the question the
hypotheses are competing answers to, `exclusivity_groups`, `compatible_pairs`, and
`exhaustive`.

**5. Non-exhaustive spaces carry residual mass.** If `exhaustive != true`, the space MUST
contain a `RESIDUAL` hypothesis (`H_OTHER`) with declared prior mass. Posterior and entropy
computations include it. Listed hypotheses therefore sum to less than one, which is the
honest answer.

**6. `H_OTHER` mass is only reduced explicitly.** By evidence, or by admitting a concrete new
hypothesis into the space, which draws mass under a declared rule. It is never silently
renormalised away — that is how a space quietly becomes exhaustive without anyone deciding
so.

**7. Probabilities are computed within an exclusivity group.** Compatible, non-exclusive
hypotheses are not normalised against each other: both may be true, so normalising them would
be a category error.

**8. Material difference is a reproducible test.** Two hypotheses are materially different
iff their structural signatures differ by at least `τ` on at least one declared facet
(mechanism, actor configuration, temporal explanation, causal direction, source
interpretation, state transition) **and** they have non-empty differential predictions or
differ in at least one critical assumption. The metric, `τ`, and the comparison result are
persisted. Failing hypotheses are `COUNTERHYPOTHESIS_DUPLICATE`, not a second insight.

## Consequences

**Positive**

- "What is the state of H?" has exactly one answer, and history is preserved.
- Posterior mass accounts for explanations nobody thought of.
- Top-k returns structurally distinct explanations rather than paraphrases.

**Costs, accepted**

- Non-exhaustive spaces make every posterior visibly incomplete. Researchers will find this
  annoying; it is the point.
- The material-difference metric is profile-dependent, so "diverse" is a declared judgement
  rather than an absolute — and the judgement is recorded.

**Not changed**

- Hypothesis identity keeps its two levels: `logical_id` is the hypothesis, `revision` is one
  assessment.

## Verification

- [ ] Every transition in the table is exercised; every forbidden transition raises.
- [ ] `trend` cannot be written directly (API/schema rejection).
- [ ] Non-exhaustive space: listed posteriors sum to < 1; `H_OTHER` mass present (N.7).
- [ ] Adding mass to a listed hypothesis draws the declared amount from `H_OTHER`; mass is
      conserved across the update.
- [ ] Admitting a new hypothesis reduces `H_OTHER` under the declared rule.
- [ ] Information gain reports whether it addresses `H_OTHER`.
- [ ] Near-duplicate hypotheses are rejected with a persisted metric and threshold.
- [ ] `CONFIRMED` → `CONTESTED` is reachable on contrary evidence.