# ADR-0034 — Global-search completeness semantics

**Status**: Accepted (Wave 0, ADR-025-07)
**Feature**: `025-context-reality-approximation-engine`
**Baseline**: v2 §32, §33, Appendix O, P

## Context

"Find all X" is the most common request and the easiest to answer dishonestly. The
universe of an open-world source set is not enumerable, so a literal completeness claim is
almost never supportable. Yet a flat list plus a confident framing is indistinguishable from a
correct one at a glance.

The platform already returns unresolved identity and coverage data. What was missing is a
contract that forces those facts into the response and forbids the confident framing.

## Decision

**1. Universal intent triggers completeness analysis.** Any query containing a universal term
(`all`, `every`, `global`, `none`, `все`, `каждый`) is compiled into a `CompletenessRequirement`
before execution, never after.

**2. Three modes, no fourth.**

```text
EXACT_ENUMERATION          universe explicitly enumerable and completely scanned
KNOWN_UNIVERSE_ENUMERATION all registered sources in the catalogue exhausted under declared policy
OPEN_WORLD_DISCOVERY       available sources searched; completeness cannot be established
```

There is no "probably complete". A mode is chosen from what is defensible; if none is, the
answer is `OPEN_WORLD_DISCOVERY`.

**3. Results are always partitioned.**

```text
observed_set · candidate_set · resolved_set · unresolved_set · excluded_set
+ coverage_estimate · source_universe · saturation_state · known_blind_spots · qualified_absences
```

`unresolved_set` is a first-class result set, not a footnote. A query that drops unresolved
identity to produce a cleaner answer is defective.

**4. A universal negative is a coverage-qualified absence.** "None exist" is expressible only
as a `CoverageQualifiedAbsence` meeting the profile's coverage and detection-power thresholds
(ADR-0036). Otherwise the answer is "none observed under declared coverage". An unbounded
absence is never a negative finding.

**5. The mode is mandatory and non-nullable** in the response for any universal-intent query.
A missing mode is a contract violation; there is no default, because the natural default is
the dishonest one.

**6. UI must display the mode.** The user's original wording may be rendered, but a
completeness banner is always shown. The UI is not permitted to render an open-world result in
a form that reads as exhaustive.

**7. Deterministic grammar is normative.** Appendix O EBNF covers a formally useful subset.
Any adaptive parser compiles into the same `QueryAST` for the same input and is Tier 3 —
never required for correctness. Replay of an adaptive-compiled query uses the recorded
proposal by digest, never regeneration.

**8. Inference policy is checked before acquisition.** The pipeline order is parse → normalize
→ bind semantic profile → **check inference policy** → construct context → … (ADR-0039).

## Consequences

**Positive**

- The engine can answer "how complete is this?" with a defensible value instead of a shrug.
- Unresolved identities stay visible instead of being merged away for presentation.
- A consumer of the API cannot mistake an open-world result for an exhaustive one.

**Costs, accepted**

- `OPEN_WORLD_DISCOVERY` will be the common mode. Results will look less decisive than a
  fabricated list.
- The compiler must carry completeness intent through to the response; a query path that
  drops it is a bug.

**Not changed**

- Acquisition (145 sources, Airbyte, BBOT) is untouched. This ADR is a wrapper around what
  exists, not a new collector.
- Saturation semantics stay in ADR-0030/0037 territory.

## Verification

- [ ] Universal-intent query → `CompletenessRequirement` present in the compiled AST.
- [ ] Response for universal intent always carries a non-null `completeness.mode`.
- [ ] `unresolved_set` is non-empty and preserved when identity resolution is incomplete.
- [ ] Universal negative without declared detection power → "none observed under declared
      coverage", never an empty-set-as-proof.
- [ ] Deterministic and adaptive parsers produce equivalent `QueryAST` for the golden corpus.
- [ ] Replay of an adaptive-compiled query uses the recorded proposal; no regeneration.
- [ ] UI shows a completeness banner for every open-world result.
- [ ] A sensitive-class query is blocked with `POLICY_BLOCKED` before any acquisition.