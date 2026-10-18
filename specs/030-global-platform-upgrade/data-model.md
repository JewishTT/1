# Phase 1 Data Model: COGNITIVE Global Platform Upgrade

**Feature**: `030-global-platform-upgrade`
**Input**: [`spec.md`](./spec.md) · [`plan.md`](./plan.md) · [`research.md`](./research.md)

This document states the **semantic** model. It does not prescribe table names, column types or ORM
classes — the repository already has a schema (`apps/control-plane/db/schema.py`) and Alembic
migrations through `015_worldline_reconstruction`, and the specification forbids creating
duplicate types without proven cause.

**Existence markers**: `[E]` = **[MEASURED]** — this record or its equivalent exists in the tree today.
`[N]` = **[NEW]** — must be created by this feature. `[E+V]` = exists but requires verification and
extension.

---

## 0. Identity rules — apply to every record below

**[DECIDED, `research.md §2`]**

1. **Logical identity, content digest, event identity and revision sequence are separate fields.**
   Overloading one id for content identity, logical identity, event identity and sequence is a
   defect. Each record below gets a stable logical id; each revision gets a content digest; each
   delivery gets an event id.
2. **Content-derived ids must be stable** for equivalent canonical content under declared identity
   semantics. Wall-clock time, request arrival order and mutable worker diagnostics are **not**
   hashed into deterministic content identity unless semantically part of the object.
3. **Every identifier generation algorithm is versioned.** A future scheme must support
   lookup/alias resolution and preserve stored lineage.
4. **Tenant scope is part of every durable key.** Cross-tenant reference is a refusal, not a lookup.

---

## 1. Evidence layer

### 1.1 SourceDefinition **[N]**

| Field | Type | Notes |
|---|---|---|
| `source_id` | id | |
| `access_classification` | open enum | policy tier |
| `capability_profile` | capability set | operations, query shapes, temporal + geographic coverage, output formats |
| `rate_policy` | policy ref | |
| `retry_policy` | policy ref | per FR-068 |
| `budget_policy` | policy ref | |
| `reliability_prior` | scalar **with named semantics** | never a truth value (P5) |
| **`detection_power`** | declared / unknown | **The gate for qualified absence.** Absent → absence claims are informational only (FR-014) |
| `legal_restrictions` | set | |
| `cost_model` | cost vector | §2.14 — vector, not scalar |

**Validation**: `detection_power = unknown` ⇒ any zero-result MUST serialise as
`SEARCHED_NO_RESULT / INFORMATIONAL_ONLY`. This is enforced at the contract layer, not by callers.

### 1.2 Capture **[E+V]**

Acquisition task, locator, `fetched_at` / `captured_at`, HTTP/browser/source metadata, response
digest, archived payload reference, source policy result, adapter + config version.

**Verification required (U-07)**: the S3-compatible endpoint variable was not found in the
`.env.example` window. WP0 resolves.

### 1.3 Observation **[E+V]** — immutable

Observation id, tenant, capture/source refs, raw object digest, observation kind,
acquisition timestamps, discovered time fields, immutable metadata.

**Invariants**:
- An observation is never mutated after commit (P1).
- Redelivery of the same observation MUST NOT increment revisions, evidence independence, coverage
  or cost-benefit learning (FR-065).
- Re-fetch of changed source content creates a **new** observation or an explicit source revision.

### 1.4 DerivedArtifact **[N]** — append-only

Artifact id, source observation ids, operator manifest, **input digest set**, output digest,
method/parameter/model fingerprints, deterministic flag, replay mode.

**Invariants**: a new parse result creates a **new** derived revision. It never overwrites the prior
one (FR-003). Rerunning a parser at a new version is the canonical supersession case.

### 1.5 Segment **[E — DEFECTIVE]** → **[E+V, WP5]**

Original-relative byte/page/time/geometry span + content reference.

> **[MEASURED] Known defect.** `Segment.offset` means byte offset in one parser, segment index in
> another, and is always `0` in a third — and all three are summed into one field at
> `extractors/lane.py:82-86`. Downstream, `document_adapter.py:271-300` consumes the span to mint
> `mention_id` and discards it.

**Required change [DECIDED]**: replace the single positional field with a **typed span union**
(§1.5.1). Conflating is forbidden by FR-006.

#### 1.5.1 `EvidenceSpanRef` **[N]** — the one span type

```text
EvidenceSpanRef
├── observation_ref        (required — always)
├── blob_digest            (required — always)
├── selector               (exactly one, required)
│   ├── char_span           { start, end, encoding }
│   ├── page_box            { page, box: [x0,y0,x1,y1], coordinate_system }
│   ├── table_cell          { table_ref, row, column, header_path[] }
│   ├── json_path           { pointer }
│   ├── time_range          { start, end, track?, frame? }
│   ├── geometry            { feature_ref, geometry_ref }
│   ├── warc_record         { record_offset, warc_digest }
│   └── source_locator      { uri, fragment }
├── source_locator          (always — how to re-fetch)
└── selector_semantics_version   (required — which producer wrote it)
```

**Rules**:
- Coordinates MUST carry a coordinate system and a reference to the original representation (FR-004).
- Two spans with different `selector_semantics_version` MUST NOT be compared or summed without
  explicit conversion. When conversion is impossible, the system **refuses** (FR-006).
- A selector is never a bare integer.

### 1.6 Mention **[E+V]**

Text, span (now `EvidenceSpanRef`), normalization candidates, language/script/transliteration
metadata, extraction-method id.

**Invariant**: normalization never rewrites the raw span; original form and script are retained.

### 1.7 EvidenceDependencyGroup **[E+V]**

Relationship between copied / syndicated / jointly sourced evidence; independence estimate;
**method lineage**.

**Invariant [MEASURED from 029 WP-E]**: corroboration counts **lineage roots**, not hostnames, and
the measure used is named on every decision. The 22-failure baseline is not affected by this.

---

## 2. Identity and admission layer

### 2.1 EntityReference / Candidate **[E+V]**

Unresolved reference, fields, observations, matching features, uncertainty, **competing identity
hypotheses**.

**Invariant**: mention ≠ candidate ≠ entity (P3).

### 2.2 ResolutionCandidate **[E+V]**

Pair/cluster, blocking trace, comparison vector, model fingerprint, calibrated score **with named
semantics**, decision state, provenance.

**Invariant**: a donor matcher (e.g. Splink) produces **candidates only** — `research.md §2.6`.

### 2.3 ResolutionDecision **[E+V]** — append-only

Decision type (`admit` / `defer` / `reject` / `quarantine` / `merge` / `split` / `reopen`),
authority/actor, rule/model + version, rationale, supporting **and** refuting evidence, superseded
decision ref.

**Invariant [DECIDED `§2.3`]**: merge and split **supersede, never rewrite**. A claim records the
identity interpretation it was written under and stays traceable to it (FR-082).

### 2.4 Cluster transitivity **[N]**

> A↔B and B↔C matching MUST NOT imply A=C where feature evidence is inconsistent (FR-084).

---

## 3. Canonical claim layer

### 3.1 RelationCandidate **[E+V]**

```text
RelationCandidate
├── subject_ref / participants[]     (ordered; arity explicit)
├── predicate_raw                    (ALWAYS — verbatim, never discarded)
├── predicate_normalized             (nullable — unknown is a valid state)
├── mapping_status                   known | mapped | unknown_predicate |
│                                   conflicting_mapping | invalid_shape | unsupported
├── direction                        directed | undirected | n-ary | unknown
├── polarity / qualifier / modality
├── valid_interval                   (nullable; unknown ≠ current time)
├── evidence_span                    (EvidenceSpanRef)
├── extraction_method + version
├── confidence + uncertainty
├── extraction_status                ← separate from admission_status
└── admission_status                 ← separate from extraction_status
```

**Invariant [P4]**: `predicate_raw` is non-nullable and survives storage, projection and UI. An
unknown predicate produces a **typed** unknown relation candidate — never a silent drop.

### 3.2 Claim / Assertion **[E+V]**

Semantic proposition + support structure. **Entering the claim store does not confer truth** (P6).

```text
Claim
├── claim_id, revision, version
├── predicate (open, normalized), participants[], qualifiers, polarity
├── valid_interval
├── recorded_at / known_at                    ← bitemporal
├── source_time_refs[]                        (typed, §4)
├── support_positive[]  /  support_negative[] ← INDEPENDENT dimensions (FR-011)
├── epistemic_state                           (four-valued; see §3.4)
├── confidence + confidence_semantics         ← separate value, not the epistemic state
├── dependency_group_ref
├── premise_refs[] / derivation_refs[]
├── scope_ref, admission_status
└── supersedes / withdrawn_by                 ← append-only
```

**Invariant**: claims from separate sources are **not** merged into one truth-bearing row.
Aggregated proposition state is *derived* from statements, never stored as the truth.

### 3.3 DerivedRelation **[E+V]**

Inference conclusion + `premise_refs[]` + `rule_id` + `rule_version` + `parameters_fingerprint` +
`valid_interval` + `created_from_revision` + `confidence_semantics` + `warnings[]`.

**Invariant**: transitive closure only over predicates whose regime declares transitivity
(FR-072). A derived edge is invalid if any premise is withdrawn or temporally incompatible, unless
the derivation records the conditional form explicitly.

### 3.4 Epistemic state — four-valued support **[E+V]**

`NEITHER` / `TRUE_ONLY` / `FALSE_ONLY` / `BOTH`.

**Rules**:
- `TRUE_ONLY` and `FALSE_ONLY` are **incomparable**. A single linear scale that orders them is a
  defect (FR-011).
- `BOTH` is a distinct state, not "low confidence".
- Confidence is a **separate field**, never the state itself (P5).

### 3.5 The thirteen research states **[N — consolidation record]**

Stored as **structured dimensions where a single enum would lose information** (CE-001 §7.5), with
these values distinguishable end-to-end through storage → events → API → UI (FR-010):

| Value | Meaning |
|---|---|
| `UNKNOWN_NOT_INVESTIGATED` | no obligation/query existed |
| `NO_OBSERVATIONS` | in scope, nothing recorded |
| `SOURCE_UNAVAILABLE` | no valid execution — transport/source |
| `QUERY_UNSUPPORTED` | not representable by this operator/source |
| `SEARCHED_NO_RESULT` | executed, zero matches, detection power unknown |
| `QUALIFIED_ABSENCE` | valid only under recorded coverage + detection power |
| `POSITIVE_SUPPORT` | |
| `NEGATIVE_SUPPORT` | |
| `BOTH` | contradiction |
| `INCONCLUSIVE` | |
| `BLOCKED` / `PARTIAL` | constraint / incompleteness |
| `HYPOTHESIS_REFUTED` | declared prediction contradicted under declared profile |
| `SATURATED_WITH_SCOPE` | marginal gain below threshold **under stated scope** |

**Invariants**:
- `SEARCHED_NO_RESULT` ⇒ informational only when detection power is unknown (FR-014).
- `NO_RESULT` is not `ABSENT`; `FAILED` is not a successful empty observation; a parser that cannot
  process a format is `UNSUPPORTED`, not a zero-content document.
- Saturation is **never** inferred from empty results, task count, exhausted retries or model
  confidence (`research.md §2.11`).

---

## 4. Temporal model

### 4.1 Eight typed clocks **[E+V]**

| Field | Meaning | Nullable |
|---|---|---|
| `source_published_at` | publication time **as claimed by the source** | yes |
| `source_valid_from` / `source_valid_until` | period the fact is claimed to hold | yes |
| `source_observed_at` | when the phenomenon is claimed to have happened | yes |
| `captured_at` / `fetched_at` | when **this platform** retrieved it | no |
| `recorded_at` / `known_at` | when this platform committed it to state | no |
| `processed_at` | when a given operator run processed it | no |
| `projected_at` | when a projection consumed it | yes |

**Invariants**: unknown source time stays unknown; never defaulted to now (FR-021). Each field has a
declared timezone and null semantics.

> **[UNVERIFIED U-03]** Whether `recorded_at` flows past migration into the ORM and query layer is
> still `[ ]` in the 029 ledger. WP0 verifies; SC-008 depends on it.

### 4.2 Three query dimensions **[N]** — never aliased

| Query | Answers | Never means |
|---|---|---|
| `CURRENT` | best current reconstruction under current evidence + profile | — |
| `AS_OF(t)` | what the platform **held** at known-time `t` | what is *true in the world* at valid-time `t` |
| `INTERVAL(a,b)` | claim/relation validity over a valid-time interval | — |

**Invariant [FR-023]**: late-arriving evidence changes `CURRENT` and `INTERVAL` reconstruction of the
past, and **must not alter** `AS_OF` at an earlier known-time.

### 4.3 Interval relations **[E+V]**

A declared subset of Allen relations with explicit disjunctive/unknown representation for imprecise
endpoints. `PRECEDES`/`OVERLAPS`/`CO_OCCURS` are **not** causality; `CAUSES` requires an
independent identification method with assumptions, confounders and a non-identifiability state
(FR-024).

---

## 5. Invariant layer

### 5.1 GraphInvariantRevision **[E]**

Stable entity id ref, **stream head**, revision, predecessor/`supersedes`, lifecycle/time slices,
relational signatures, integrity digest, method/schema version, source event hashes.

**Invariants (P1, P9)**:
- Not a full ontology. Not raw content. Not identity. Not proof of truth.
- Contains no raw content (spec §2.3).
- Identity merge/split is **not** the invariant's responsibility (P3).

### 5.2 InvariantReducer **[E — property must not regress]**

> **[MEASURED]** The reducer advances its revision counter **once per `reduce()` call**, not once per
> event. Folding a three-event stream in one batch lands at revision 1; folding incrementally reaches
> revision 3. Because the revision is inside the invariant identity, **the two produce different
> digests over identical evidence**.
>
> The mitigation is `restore(stream, history=)`, which rebuilds at the recorded position.
> `test_a_cold_fold_is_not_equivalent_to_a_restore` pins the behaviour deliberately.

**Required invariants**:
- Fold the **accumulated** life stream, not the current batch (FR-064).
- Deterministic canonical ordering; deduplicate by stable event/record identity.
- Mint a revision **only when the canonical digest changes** (FR-032).
- Persist `supersedes`/head + all source event hashes; restore the head across restart.
- Distinguish event correction/retraction from redelivery.
- Tenant/entity scoped. **Never** makes identity decisions.

---

## 6. Research process layer — the kernel

### 6.1 ContextDefinition **[E — verify]** (`CXD-…`)

**Immutable analytical contract.** Objective, query-intent/AST ref, semantic regime, reasoning
profile, coverage profile, temporal scope + known-time semantics, source universe, policy refs,
action/analysis budgets, stop conditions, creation actor/time, optional `supersedes`.

**Invariants [FR-030, FR-031]**:
- **Separate id namespace** from `CXI-…`. Never share a prefix.
- Changing objective/scope/profile leaves a trace: a running investigation continues against a
  pinned revision or transitions with an explicit rebase decision.
- Historical revisions are **never** silently reinterpreted.
- A text objective does not substitute for compiled/AST fields; both are stored, plus
  parser/compiler version.

### 6.2 InvestigationContext **[E]** (`CXI-…`) — mutable by revision

Root aggregate: tenant, `definition_ref`, lifecycle status, current revision head, actor,
timestamps, budget state, closure/saturation state, optional parent/branch refs.

### 6.3 ContextRevision **[E+V]**

```text
ContextRevision
├── context_id, revision_number (monotonic, per-context), revision_id (content-derived)
├── parent_revision_id / supersedes
├── input_fingerprint           (prior revision + event ids + pinned heads
│                                + rule versions + parameters)
├── changeset + durable refs to full change records
├── obligation / hypothesis / contradiction / unknown state heads
├── projection / invariant / worldline heads observed
├── rule_bundle_fingerprint, operator_fingerprints
├── status, warnings, degradation_reason
├── replay_manifest
└── integrity_digest
```

**Invants**:
- Revision sequence is **per-context** and is never conflated with entity invariant revision.
- No-op input MAY skip a semantic revision, but its delivery record stays observable when
  idempotency requires it (FR-032).
- Revision + its `DecisionRecord` are **atomic** — `PostgresContextGraphStore.apply(tenant_id,
  transaction) → DecisionRecord` **[MEASURED]** already satisfies this at the storage layer
  (`research.md §2.1`).

### 6.4 Lifecycle state machines **[E+V]**

```text
InvestigationContext:
  CREATED → ACTIVE ↔ PAUSED
     │         │        │
     └─────────┴────────┴──→ SUSPENDED
  ACTIVE → SATURATED   (qualified; reopens on new evidence or profile change)
  ACTIVE → BLOCKED     (resumable; NOT closed)
  ACTIVE → CLOSED      (explicit analyst/policy closure)

ResearchObligation:
  OPEN → PROPOSED → IN_PROGRESS → EVALUATING
                                ├→ SATISFIED             (criteria + evidence refs + evaluator version)
                                ├→ PARTIALLY_SATISFIED   (creates residual gap / child obligation)
                                ├→ UNSATISFIED           (evidence did not meet criteria — NOT "false")
                                └→ BLOCKED               (missing capability / policy / approval / budget)
  any → DEFERRED | SUPERSEDED | WITHDRAWN              (history preserved, cause recorded)

Hypothesis:
  PROPOSED → ACTIVE → SUPPORTED      (under declared evidence)
                     → REFUTED       (under declared test/policy)
                     → INCONCLUSIVE
  ACTIVE | SUPPORTED → DISPUTED      (conflicting evidence)
  any nonterminal → SUPERSEDED | WITHDRAWN
```

**Invariants**:
- `BLOCKED` ≠ `CLOSED`; `SATURATED` is scoped, never universal.
- Status is relative to scope/time/definition/evidence revision and is queryable `as_of`.
- An obligation is never **deleted** when superseded or withdrawn (FR-038).

### 6.5 ResearchObligation **[E+V]**

```text
obligation_id, context/question/scope refs
trigger        { kind, event_id, rule_id, rule_version, reason, evidence_refs }
question / intent
parent_refs    { gaps[], hypotheses[], contradictions[], claims[] }
required_outcome { kind, hypothesis_refs[], acceptance_predicates[] }   ← separate from ranking signal
capabilities_required[], eligible_sources[] + why each qualifies
unknown_dependencies[], policy_requirements
priority_components  (nullable = not yet estimated — NOT fabricated 0.0)
expected_gain, cost_range, success_estimate, uncertainty
status + every transition with reason
attempt_history[] { action_ref, result, marginal_gain, cost, suppression_rule }
stop_rule, satisfaction_rule, scope_boundaries
rules_fingerprint
```

**Invariants [FR-039, FR-040]**:
- A gap never disappears because a function returned `[]` or a task ended.
- **Task completion ≠ obligation satisfaction.** Task count is never a satisfaction criterion.
- Unknown numeric components stay `null` — not `0.0` (§7 of the source spec).

### 6.6 ResearchAction / ActionAttempt **[E+V]**

Action: canonical fingerprint, parent obligations, capability descriptor, payload, preconditions,
source selection, estimate, policy/approval state, **ranking feature vector**, constraints, expected
outcomes, idempotency/replay identifiers. Immutable once scheduled except by supersession.

Attempt: task id, worker/operator/source versions, start/complete + times, actual costs, observation
refs, result status, failure class, retries, **measured marginal gain (or explicitly unknown)**,
affected obligations, redacted diagnostics. Multiple attempts never collapse into one action status.

### 6.7 Action utility vector **[E+V]**

Fourteen components, **each inspectable**: `expected_information_gain`,
`hypothesis_discrimination`, `relevance`, `source_quality`, `evidence_independence_gain`, `novelty`,
`temporal_freshness`, `probability_of_success` (+ stated semantics), `estimated_cost`, `latency`,
`repeat_penalty`, `source_failure_rate`, `resource_risk`, `policy_penalty`.

**Invariants [P5, P11, FR-043]**:
- The raw vector is retained; a composite carries its policy version and weights.
- **Hard constraints are evaluated before ranking** and cannot be outweighed (§7.5: hard filters,
  then drop/suppress redundant, then compute the vector, then rank).
- An adaptive layer may reorder; the deterministic core still decides, and the applied policy
  version is stored with its inputs (§2.8).

### 6.8 ActionMemory **[E]**

Keyed by canonical action fingerprint + scope + temporal range + parameters + operator version.
Records actual cost and measured marginal gain.

**Invariant [FR-045]**: a repeated no-gain action is suppressed until a **declared** condition
changes (new evidence, source content changed, stale interval elapsed, source became available,
parser/model version changed, parameters changed, analyst override, hypothesis test now requires
it) or an explicit override with a reason is recorded. Failure and no-result are **different**
memory states.

### 6.9 Gap / Unknown / Contradiction **[E+V]**

- **Gap** — derived deficiency vs question/scope/profile; type, affected scope, parent refs,
  required evidence/capability, expected action, confidence in the detection of the gap itself.
- **Unknown** — **durable state, not the absence of a row**. Target, what is unknown, reason kind,
  attempts and searches performed, coverage/detection conditions, missing capability, blockers,
  opened-from event, resolution criteria.
- **Contradiction** — opposing claims, source refs, dimension, temporal/scope mismatch, dependency
  groups, compatibility state, resolution criteria, lifecycle, prior decisions.

**Invariant [P6]**: contradictions persist. Resolution needs more evidence or an explicit reasoned
decision — never recency, document majority, or a single high score.

### 6.10 DecisionRecord **[E+V]**

Decision type, actor/system principal, context/definition/revision, target ref, prior state,
resulting state, trigger event, rule/operator + version, parameters, evidence refs, **alternatives
considered**, rationale, hard constraints applied, override/review refs, digest.

### 6.11 Finding **[E+V]**

```text
finding_id, revision, context/question/obligation refs
finding_type      direct_observation | inferred_relation | hypothesis_evaluation |
                  temporal_shift | topological_structure | qualified_absence | anomaly
content
status            candidate | grounded | partial | disputed | withdrawn | superseded
support_refs[], counter_evidence_refs[], dependency_groups[]
scope, valid_interval, temporal_mode
derivation_refs[], operator_fingerprints[], projection_heads[]
uncertainty, warnings, alternative_explanations
coverage_mode, limitations
review_state, supersedes
```

**Invariant [FR-048]**: a Finding is an analyst-facing projection **with lineage** — never a
replacement for evidence or claims. A generated summary never replaces the underlying evidence.

---

## 7. Projection layer

### 7.1 ProjectionManifest **[N]** — required for every projection

```text
projection_id, projection_kind, tenant_id
source_event_offsets / snapshot
input_snapshot_digest
builder           { id, version, container_digest }
parameters, parameters_fingerprint
output_digest
status            succeeded | partial | failed | stale | quarantined
rebuildable       ← true ONLY if a durable source + checkpoint + algorithm route exists AND is tested
staleness         { status, lag_events }
created_at
```

**Invariant [FR-071]**: a `projection_id` that is created but never used is a defect. A `rebuild()`
that silently restarts from offset zero while presenting itself as incremental is a defect — either
fixed or explicitly documented as the chosen cost model.

### 7.2 Family-specific requirements

| Family | Invariant |
|---|---|
| **Graph** | Asserted vs derived edges distinguishable; every derived edge carries rule + path + premises + interval + invalidation. N-ary preserved — a pairwise view is opt-in with an explicit derivation and a semantic-loss warning (FR-073). Traversal returns truncation metadata (FR-074). |
| **Search** | Response carries index revision, searched fields, applied filters, staleness, candidate-pool truncation. A hit is a candidate pointer. Deleting an index doc MUST NOT lose evidence (FR-075). |
| **Temporal** | Budget exhaustion is a **partial-result envelope**, not an exception and not a silent tail drop. |
| **TDA** | Snapshot digest, node set **including isolated nodes**, edge direction/arity treatment, filtration scale + units, metric, complex constructor, window, code+dependency fingerprint. Refuse or stratify incomparable scales. Never mutates identity or truth (FR-076). |
| **Spatial** | Original geometry + CRS + precision/accuracy + validity/known time + footprint retained. A cell MUST NOT imply precision finer than the source (FR-077). |
| **Analytics** | Estimator + version, sample scope, sample size, CI/uncertainty, missingness. **Source-health is maintained separately from real-world anomaly candidates** (FR-078). |

### 7.3 Projection ownership **[UNVERIFIED U-01, U-02]**

Three TDA trees exist (`apps/projection/tda/`, `apps/science/scitda/`,
`GraphInvariant.to_tda_input`) and **both** `gudhi` and `giotto-tda` are installed. Which is the
production path — and the AGPL-3.0 disposition of giotto-tda — is a WP0 output feeding
`ADR-030-07` and `ADR-030-09`. **This document does not guess it.**

---

## 8. Operator layer

### 8.1 `OperatorResult` **[N]** — see [`contracts/operator-result.md`](./contracts/operator-result.md)

Carries operator id/version, input observation ids + digests, output kind + schema version,
output digest, artifact refs, evidence refs, method/parameters/model fingerprints, deterministic
flag, **replay key + replay mode**, status, uncertainty, warnings, missingness, error code,
start/complete times, **cost vector**, tenant, investigation, policy fingerprint.

**Invariants**:
- An empty output MUST NOT be overloaded to mean success / no-hits / unsupported / blocked / error.
  Those are distinct `status` values (FR-047).
- Source times are attached with **explicit type labels**; never squashed into one datetime.
- Two replay modes: `deterministic` (recompute, digest must match) and `result-replay` (preserve
  the exact result, state that recomputation is not possible) — `research.md §2.10`.

### 8.2 Operator registry **[E+V]**

Capability, cost estimate, constraints, version, isolation class, licence metadata.

**Invariant [P13]**: a registry selection MUST return an explicit `CapabilityGap`. Silently
substituting a weaker capability for a missing one is forbidden (CE-I13).

### 8.3 Capacity gap **[N]** — the missing-capability record

`capability_required, capability_available, substitution_attempted=false, status=unsupported|approximate, gap_reason, owner, next_action`

**Invariant**: an operator that cannot do X says so. It does not do Y and report success.

---

## 9. What this feature creates vs extends

| Record | Status | Work |
|---|---|---|
| `SourceDefinition.detection_power` | **[N]** | gate for qualified absence |
| `EvidenceSpanRef` typed union | **[N]** | replaces the conflated positional field |
| `Segment` span semantics | **[E]** → **[E+V]** | WP5 producer fix |
| `DerivedArtifact` | **[N]** | provenance for every derived output |
| `ResolutionDecision` supersession | **[E+V]** | merge/split never rewrite |
| `InvariantRevision` history | **[E+V]** | durable `supersedes` chain |
| `ContextDefinition` / `InvestigationContext` id separation | **[E — verify]** | WP0 |
| `ContextRevision` fields | **[E+V]** | WP2 |
| `ResearchObligation` trigger completeness | **[E+V]** | WP2/WP8 |
| Action utility component vector | **[E+V]** | WP9 |
| 13-state epistemic model | **[N]** | WP8 |
| `ProjectionManifest` | **[N]** | WP7 |
| `OperatorResult` + replay modes | **[N]** | WP6 |
| `CapacityGap` | **[N]** | WP6 |
| `donors/registry.yaml` | **[N — file absent]** | WP0/WP1 |
| Constitution (filled) | **[N — template only]** | WP1 `T0100` |

---

## 10. Validation rules index

| Rule | Enforced by |
|---|---|
| Raw object immutable | byte-digest comparison, SC-005 |
| Span selectors never conflated | `EvidenceSpanRef.selector_semantics_version`, FR-006 |
| Unknown predicate survives | `RelationCandidate.predicate_raw` non-null, FR-013 |
| No scalar truth | FR-016 component-vector retention |
| `TRUE_ONLY` ≁ `FALSE_ONLY` | four-valued state test, §3.4 |
| Absence needs detection power | `SourceDefinition.detection_power`, FR-014 |
| Eight clocks stay separate | §4.1 |
| `AS_OF` ≠ valid-time reality | §4.2 |
| Revision on digest change only | `InvariantReducer`, FR-032/FR-064 |
| Cold fold ≁ restore | `test_a_cold_fold_is_not_equivalent_to_a_restore` **[MEASURED]** |
| Obligation ≠ task | FR-040 |
| Hard constraints before ranking | FR-043 |
| Identity never by score | FR-081 |
| Tenant-scoped durable keys | §0.4, FR-090 |
| Donor never writes canonical stores | FR-111 |
| No fabricated metrics | FR-100, SC-015 |
| Blocked ≠ pass | SC-016 |