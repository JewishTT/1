# ADR-0036 — Evidence independence and coverage-qualified absence

**Status**: Accepted (Wave 0, ADR-025-09)
**Feature**: `025-context-reality-approximation-engine`
**Baseline**: v2 §13A, §14A, §23.2, Appendix K.3, N.3, N.8

## Context

Two of the oldest failure modes in open-source intelligence are both counting errors.

**Volume.** The same press release copied by 500 sites is one observation. Counting it as 500
inflates confidence by the square of the syndication radius, and no amount of downstream
reasoning recovers from it. The existing platform already captures content identity and
derivation lineage, so the raw material to detect this exists — it was simply never consumed
by any aggregation rule.

**Absence.** "Searched and found nothing" is the second. It is evidence only if the search
could have found it. Coverage and detection power are the difference between a negative
finding and an absence of evidence, and v1 had no way to express the difference, so every
absence became a negative.

Together these make every number in the system untrustworthy in a specific, silent way.

## Decision

**1. One independence model governs every aggregation.** `EvidenceDependencyGroup` (EDG) is
derived deterministically from evidence lineage plus declared rules, persisted and versioned.
Dependence bases: `SAME_UNDERLYING_OBSERVATION`, `SYNDICATION_LINEAGE`,
`SAME_TRANSFORMATION_CHAIN`, `SAME_EXTRACTION_METHOD`, `SAME_PUBLISHER / SOURCE_FAMILY`,
`SAME_UPSTREAM_MODEL`. Correlation model: `DECLARED_DISCOUNT | MAX_ONLY | PROFILE_SPECIFIC`.

**2. Every combining rule consumes groups, never items.** Within a group the contribution is
`max` or a declared discount. Across groups, contributions combine under the rule's
independence assumption — which is itself a declared entry in the assumption ledger.

**3. `n_eff` is reported next to the raw count, everywhere either appears.** Not instead of
it. The raw count is informative; the effective count is what the arithmetic used.

**4. Unknown lineage is conservative.** A rule that cannot determine dependence treats the
items as one group and records `INDEPENDENCE_UNKNOWN`. Assuming independence when it is
unknown is the exact error this ADR exists to prevent.

**5. `truth_state` flags are unaffected.** Dependency groups change score *weights*, never
`positive_support`/`negative_support`. Those are existence claims (ADR-0029). One admissible
item sets the flag; five hundred copies do not set it five hundred times, and do not clear it.

**6. Absence is an object with an admissibility decision.**

```yaml
CoverageQualifiedAbsence:
  absence_id: CQA-...
  query, source_set, window
  coverage: value | interval | UNKNOWN
  detection_power: value | interval | UNKNOWN   # P(detect | present)
  errors_accounted: bool
  result: NOT_FOUND_UNDER_COVERAGE
  admissibility: NEGATIVE_EVIDENCE | INFORMATIONAL_ONLY
```

`NEGATIVE_EVIDENCE` only when the profile's thresholds on coverage **and** detection power
are met **and** the absence bears on a falsifiable prediction. Otherwise
`INFORMATIONAL_ONLY`: stored, shown, feeding saturation and coverage, contributing `NEITHER`.

**7. Unknown detection power ⇒ `INFORMATIONAL_ONLY`, always.** No threshold, no profile, no
exception. This is the safe direction and the whole point.

**8. "Not searched" is not an object of this type at all** and never contributes. Absence of
search is not a kind of absence.

**9. Universal negatives route through CQA** (ADR-0034). "None exist" is expressible only as a
CQA meeting the thresholds.

**10. Independence assumptions are ledger entries.** Every rule's independence assumption is an
`Assumption`, so "this conclusion depends on assuming these sources are independent" is
answerable without reading logs.

## Consequences

**Positive**

- Syndication stops inflating confidence, mechanically rather than by discipline.
- Negative findings become defensible: the system can say why an absence counts.
- Saturation's `distinct_sources` becomes honest (`n_eff`).

**Costs, accepted**

- Every aggregation rule must be rewritten to consume groups. There is no shortcut, and a rule
  left on raw items is a defect.
- `n_eff` is frequently much lower than the raw count, which will make some results look weak
  that previously looked strong. They were weak.

**Not changed**

- Content identity and derivation lineage — consumed, not modified.
- Evidence is never deleted; groups are an overlay.

## Verification

- [ ] Syndicated set: three captures → one content identity, one dependency group, `n_eff`
      below the raw count, posterior not inflated (N.3).
- [ ] Property test: adding a duplicate of an existing evidence item raises neither `n_eff` nor
      any posterior.
- [ ] Unknown lineage → single group + `INDEPENDENCE_UNKNOWN` recorded.
- [ ] Covered search with declared detection power → `NEGATIVE_EVIDENCE`, contributes negative
      support.
- [ ] Unknown detection power → `INFORMATIONAL_ONLY`, contributes `NEITHER` (N.8).
- [ ] "Not searched" produces no CQA and contributes nothing.
- [ ] Every update rule that combines evidence declares its independence assumption in the
      ledger.
- [ ] `truth_state` flags unchanged by group size (unit test with 1 vs 5 identical items).