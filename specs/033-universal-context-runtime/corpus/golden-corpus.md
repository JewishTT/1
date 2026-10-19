# Golden Corpus — Feature 033

**Feature**: `033-universal-context-runtime`
**Requirement**: FR-079, SC-015 — the fifteen fixtures of §32.2, each with expected accepted,
rejected, unresolved and unknown states, expected citations and spans, and explicitly allowed
alternative interpretations.

---

## Why a corpus and not a test file

A single test asserts one behaviour. A corpus is a **contract with the future**: it fixes the cases
that must keep behaving as the platform evolves, and it records the alternative interpretations that
a reasonable reviewer might accept. When a fixture changes, the change is a decision, not a
side-effect of a refactor.

Each fixture below is defined by its **purpose**, its **expected states** and its **allowed
alternatives**. Data files live beside this document under `corpus/fixtures/`.

---

## The fifteen fixtures

### F01 — Multilingual aliases with a false-positive near-match

**Purpose**: prove that an alias-rich identity is not collapsed with a similar-but-different person.
**Contains**: one entity with names in three scripts and two transliterations; a second entity that
shares a transliteration and a co-location but not an identity.
**Expected**: two entities; the near-match is a candidate, not a merge; the blocking trace names
which alias and which attribute matched.
**Unresolved**: the transliteration ambiguity is recorded, not resolved by preference.
**Allowed alternatives**: a reviewer may accept a merge only with an explicit adjudication and a
recorded rationale.

### F02 — Contradictory values with non-overlapping validity

**Purpose**: prove that temporal non-overlap is not a conflict.
**Contains**: two claims about one property with disjoint valid intervals.
**Expected**: `NOT_A_CONFLICT` with reason `temporal_non_overlap`; both claims retained.
**Unresolved**: none.
**Allowed alternatives**: none — this is the canonical negative case.

### F03 — Two sources with one upstream origin

**Purpose**: prove that syndicated republishing is not independent corroboration.
**Contains**: three URLs carrying the same wire copy, plus one genuinely independent source.
**Expected**: one lineage root for the three; independence count of two, not four; voting over roots.
**Unresolved**: the wire copy's original author may remain unknown; that is recorded.
**Allowed alternatives**: a reviewer may identify a fourth origin if the evidence supports it.

### F04 — Late evidence about an earlier event

**Purpose**: prove `AS_OF` correctness.
**Contains**: a knowledge state without the 2020 fact; a 2026 capture asserting it with valid time 2020.
**Expected**: `AS_OF(2025)` unchanged; `CURRENT` includes it; `INTERVAL(2020)` returns it; the
capture's own `known_at` is 2026.
**Unresolved**: the 2020 fact's source authority may be weak; that is a separate judgement.
**Allowed alternatives**: none for the temporal result.

### F05 — Empty, unavailable and unsupported sources

**Purpose**: prove the three states are distinct.
**Contains**: a source that returns nothing, a source that refuses access, a query shape no operator
can express.
**Expected**: `SEARCHED_NO_RESULT`, `SOURCE_UNAVAILABLE`, `QUERY_UNSUPPORTED` — three distinct
durable outcomes with three distinct codes.
**Unresolved**: none.
**Allowed alternatives**: none.

### F06 — A recurring unknown ontology term

**Purpose**: prove open-world preservation and ontology-gap detection.
**Contains**: the same unknown predicate in four sources, with different surface forms.
**Expected**: four preserved records with `mapping_status=unknown_predicate`; one grouped gap with
four contexts; no automatic activation of a mapping.
**Unresolved**: the correct mapping is unresolved until governance decides.
**Allowed alternatives**: a reviewer may propose a mapping; the proposal is not an activation.

### F07 — Nested JSON, table and WARC span preservation

**Purpose**: prove typed spans survive non-trivial structures.
**Contains**: a nested JSON record, a table with a two-level header, and a WARC record containing both.
**Expected**: JSON pointer, table cell with header path, and WARC offset plus record digest each
resolve to exact bytes.
**Unresolved**: none.
**Allowed alternatives**: an equivalent header path representation is acceptable if it resolves to
the same cell.

### F08 — Document, image and audio with exact locators

**Purpose**: prove multimodal grounding.
**Contains**: a paginated document, a scanned table, an audio interview.
**Expected**: page box, OCR cell box, and transcript time range, each within the declared tolerance.
**Unresolved**: the audio's speaker attribution may be uncertain; that is recorded per segment.
**Allowed alternatives**: a coarser time range is acceptable only if the declared tolerance allows it.

### F09 — Merge followed by an evidence-driven split

**Purpose**: prove correction does not rewrite history.
**Contains**: a committed merge; later evidence that the two are distinct.
**Expected**: a split decision with `previous_decision_ref`; prior claims unchanged; projections
regenerated with a new digest; the earlier interpretation remains retrievable.
**Unresolved**: the identity of the previously merged entity may remain ambiguous.
**Allowed alternatives**: none for the immutability of the prior claims.

### F10 — A simulation result that must not become an observation

**Purpose**: prove the five-model separation.
**Contains**: a scenario trajectory derived from cited parameters.
**Expected**: stored as a model-space artifact, labelled simulated, not queryable as an observed claim;
its inputs are cited.
**Unresolved**: the scenario's plausibility is not a finding.
**Allowed alternatives**: none — this is the category boundary.

### F11 — Policy-denied acquisition with a durable outcome

**Purpose**: prove denial is a result, not an exception.
**Contains**: a source whose access mode forbids the request.
**Expected**: `policy-denied` outcome, durable, with the policy rule named and the request visible in
the completion report.
**Unresolved**: whether the source would have answered is unknown and stays unknown.
**Allowed alternatives**: none.

### F12 — Partial run, restart, replay under changed policy

**Purpose**: prove recovery and re-authorisation.
**Contains**: a run interrupted mid-flight, restarted, then replayed under a stricter policy.
**Expected**: resume is idempotent; the replay is re-authorised; the original policy is preserved as
provenance but does not authorise the replay.
**Unresolved**: none.
**Allowed alternatives**: a replay may be refused if the new policy forbids it; that refusal is a
valid expected result.

### F13 — Two context branches reaching different plausible conclusions

**Purpose**: prove branch semantics.
**Contains**: one frame, two branches differing in scope assumption.
**Expected**: both branches retained; no canonical fact mutated by either; merging is refused where
the conclusions conflict.
**Unresolved**: which conclusion is correct may remain unresolved.
**Allowed alternatives**: both conclusions are allowed, each with its assumption visible.

### F14 — Causal question with a non-identifiable effect

**Purpose**: prove causal honesty.
**Contains**: a question whose treatment effect cannot be identified from the available data.
**Expected**: the operator returns non-identifiability with the missing assumption named; no point
estimate is fabricated.
**Unresolved**: the effect is unknown.
**Allowed alternatives**: a bound may be returned if the assumptions for it are stated.

### F15 — Budget exhausted before scope is complete

**Purpose**: prove the stop semantics.
**Contains**: a context whose budget runs out with obligations still open.
**Expected**: `BLOCKED_PARTIAL` with the budget named; residual obligations and unexecuted scope in
the report; no closure.
**Unresolved**: the unexamined scope.
**Allowed alternatives**: none.

---

## Fixture record format

```yaml
id: F01
title: multilingual aliases with a false-positive near-match
purpose: identity safety
inputs:
  - path: fixtures/F01/aliases.json
  - path: fixtures/F01/documents/
expected:
  accepted: []
  rejected: []
  unresolved: [transliteration_ambiguity]
  unknown: [resolved_identity_of_near_match]
citations:
  - span_kind: char_span
    must_resolve: true
allowed_alternatives:
  - merge_with_explicit_adjudication
status: NOT_RUN
```

---

## Current state

All fifteen fixtures are defined and **none has run**. Phase A creates the data; Phases C–F make the
assertions meaningful; Phase H runs them as part of the release gate.

A corpus that is defined but never run is a plan, not a proof. That distinction is the point of this
document.
