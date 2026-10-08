# ADR-0037 — Ranking policy: no multiplicative utility

**Status**: Accepted (Wave 0, ADR-025-10)
**Feature**: `025-context-reality-approximation-engine`
**Baseline**: v2 §20.3–20.5, §46.1, Appendix I.6, N.10

## Context

v1 specified

```text
utility = IG × feasibility × quality × discrimination / cost
```

This is the shape every ranking heuristic converges to, and it is wrong in four independent
ways:

1. **Zero annihilation.** Any zero factor zeroes the result. "Feasibility 0" is not "worth
   nothing" — it means *not runnable*, which is a filter, not a weight.
2. **Unit mixing.** IG is bits, quality is a 0–1 score, cost is seconds. Their product is
   dimensionless only in the sense that nobody can say what it means.
3. **Division by zero.** Cost can legitimately be zero (a local index lookup). The formula is
   then undefined, and the temptation is to substitute a small constant, which silently
   dominates the ranking.
4. **Cross-kind comparison.** A `HEURISTIC_SCORE` of 0.7 and a `MODEL_POSTERIOR` of 0.7 are
   different quantities. Multiplying them together invites a comparison that is meaningless.

Left alone, this formula is also how a relevant-looking number ends up ranking an action that
cannot run.

## Decision

**1. The multiplicative formula is removed.** Not deprecated — removed.

**2. Hard gates are filters.** Policy status, capability availability, safety policy and
feasibility `= 0` remove an action from the ready set. It appears in the frontier as blocked,
with the reason. It never receives a score.

**3. Declared ranking mode** in `ReasoningProfile` (`RPF-`, versioned, fingerprinted,
referenced by every revision):

```text
LEXICOGRAPHIC               ordered criteria with tolerance bands
PARETO_THEN_TIEBREAK        keep the non-dominated set, then a declared tie-break
WEIGHTED_ADDITIVE_NORMALIZED  only over criteria normalized to a declared common scale,
                              weight vector in the profile, no universal defaults
```

No default weights. A profile that has not declared them cannot rank, and says so.

**4. No cross-tier numeric comparison.** `IG_PROBABILISTIC` values compare only with other
`IG_PROBABILISTIC` values; surrogate tiers likewise. Tiers are combined by a profile-declared
interleaving rule. Raw numbers from different tiers are never compared.

**5. Exploration quota.** The profile reserves a declared fraction of selections for
exploration — unexplored capability classes, under-covered source families — recorded as
`exploration_picks`. Greedy exploitation alone is how an investigation converges on one source
family and reports high confidence from one publisher.

**6. Cost floor.** Where cost appears as a divisor, a declared floor `ε > 0` applies. Zero or
unknown cost is reported as `UNKNOWN` cost, never as zero cost.

**7. Every factor, normalisation and transformation is declared in the profile and echoed in
the decision trace.** The analyst must be able to reconstruct the ordering, not observe it.

**8. Dominance never crosses score kinds** (ADR-0032/0033 principle applied to pruning). The
discarded candidate and the dominance reason remain auditable.

**9. Expected and realised gain are stored with the same tier label.** Realised gain is
computed after `PredictionOutcome` (ADR-0030/0032) as change in entropy or separation within
the *same* space. Comparing realised gain against expected gain of different tiers is
prohibited.

**10. Priority components are always exposed.** The tuple `urgency, information_gain (tier),
discrimination, expected_quality, novelty, cost, latency, redundancy_penalty, policy_penalty`
is the output; a final ordering is a profile-derived convenience, never the only artifact.

## Consequences

**Positive**

- A non-runnable action cannot be ranked highly, because it never enters the ranking.
- Rankings are reconstructible and profile-attributed.
- Heuristic and probabilistic candidates coexist without a false comparison.

**Costs, accepted**

- `LEXICOGRAPHIC` is brittle to criterion ordering and will need profile tuning.
- The profile becomes a real artefact that must be maintained and versioned.

**Not changed**

- The frontier priority tuple.
- Action governance: a selected action is still a proposal until approved.

## Verification

- [ ] Property test: **no ranking function compares raw values across score kinds.**
- [ ] Feasibility 0 → blocked with reason, never ranked.
- [ ] Zero-cost action handled via `ε` floor; unknown cost reported as `UNKNOWN`.
- [ ] Undeclared weight vector → ranking refuses and reports the missing declaration.
- [ ] N.10: heuristic-scored and probabilistic candidates ordered by interleave, not by value.
- [ ] Exploration quota produces the declared fraction of exploration picks and marks them.
- [ ] Realised gain is computed within the same space and tier as expected gain.
- [ ] Every ordering is reproducible from the profile version recorded in the decision trace.