# Contracts — 025 **v2**

**Feature**: `025-context-reality-approximation-engine`
Normative source: [input.md](input.md) §30, §41–§42, Appendix G, H, O, P, Q. Items marked
**ADDED** are binding details v2 did not spell out.

---

## 1. Reasoning operator contract (§30, Appendix H)

```python
class ReasoningOperator(Protocol):
    id: str
    version: str
    operator_class: str
    input_contract: ContractRef
    output_contract: ContractRef
    determinism: str      # EXACT | FIXED_POINT | FLOAT_QUANTIZED | NON_DETERMINISTIC(reason)
    numeric_mode: str
    complexity: ComplexityModel

    def validate_input(self, input_view) -> ValidationResult: ...
    def run(self, input_view, parameters, seed) -> OperatorResult: ...
    def explain(self, result) -> ExplanationTrace: ...
```

Operator classes: `NORMALIZATION COMPATIBILITY GLUING STATE_ESTIMATION ABDUCTION DEDUCTION
DIALECTICS BAYESIAN_UPDATE ARGUMENTATION TEMPORAL CHANGE_POINT REGIME TDA CAUSAL
GRAPH_ANALYSIS INFORMATION_GAIN SATURATION CALIBRATION ANOMALY SCENARIO INDEPENDENCE`.

### Execution protocol (Appendix H.2) — normative order, v2 is 14 steps

```text
 1 validate operator registration      8 allocate resource budget
 2 validate input contract             9 execute operator
 3 check inference policy (output classes)  10 validate output contract
 4 load declared dependencies         11 generate explanation trace
 5 bind context revision and branch   12 persist result + run record
 6 bind semantic regime + reasoning profile   13 emit event
 7 bind policy and derive seed        14 expose result only after commit
```

Step 10 failure → `QUARANTINED`, no world-model mutation, run `FAILED`, error artifact
persisted, input replayable.

### Seed derivation (§4.1) — mandatory for any stochastic operator

```text
seed = digest128(context_id, branch_id, parent_revision, operator_id, run_ordinal)
```

Part of the parameter fingerprint. **No ambient RNG.** Floats are canonicalised to decimal
strings before hashing; NaN/Inf are forbidden in identity material.

### Cache key (§30.5) — tenant mandatory

```text
(tenant_id, context_id, branch_id, operator_id, operator_version,
 input_digest, parameter_fingerprint, seed, policy_fingerprint)
```

A key without `tenant_id` is rejected at registration. Cache reads fail closed on tenant
mismatch exactly like storage.

### Failure taxonomy (§44, v2)

`SUCCESS PARTIAL UNKNOWN INSUFFICIENT_EVIDENCE INCOMPATIBLE CONFLICTING UNRESOLVED
BUDGET_EXHAUSTED TIMEOUT DEPENDENCY_UNAVAILABLE POLICY_BLOCKED INVALID_INPUT
NOT_IDENTIFIED PARITY_VIOLATION`

Never collapsed to `UNKNOWN`.

---

## 2. API surface (§41, v2)

```http
GET /api/v1/investigations/{investigation_id}/context
GET /api/v1/investigations/{investigation_id}/context/revisions
GET /api/v1/investigations/{investigation_id}/context/revisions/{revision}
GET /api/v1/context/{context_id}/branches

GET /api/v1/context/{context_id}/hypothesis-spaces
GET /api/v1/context/{context_id}/hypotheses
GET /api/v1/context/{context_id}/hypotheses/{hypothesis_id}
GET /api/v1/context/{context_id}/dialectics
GET /api/v1/context/{context_id}/predictions

GET /api/v1/context/{context_id}/contradictions
GET /api/v1/context/{context_id}/contradictions/{contradiction_id}

GET /api/v1/context/{context_id}/state
GET /api/v1/context/{context_id}/regimes
GET /api/v1/context/{context_id}/transitions
GET /api/v1/context/{context_id}/topology

GET  /api/v1/context/{context_id}/frontier
GET  /api/v1/context/{context_id}/obligations
GET  /api/v1/context/{context_id}/actions
POST /api/v1/context/{context_id}/actions/{action_id}/approve
POST /api/v1/context/{context_id}/actions/{action_id}/reject
POST /api/v1/context/{context_id}/analyst/assertions
POST /api/v1/context/{context_id}/analyst/decisions
```

**ADDED** — `ContextDefinition` endpoints on a distinct prefix (ADR-0028 cost note):

```http
GET  /api/v1/context/{context_id}/definition
POST /api/v1/investigations/{investigation_id}/definition
```

**ADDED** — every revision/state endpoint accepts `branch`, default mainline (§41.1). A
non-mainline branch label is mandatory in every response body, so a counterfactual can
never be rendered as a mainline finding (§6.4).

`POST` endpoints create decisions/tasks through existing control-plane boundaries, never
call acquisition runtimes, and never edit evidence.

---

## 3. Query response (§42, v2)

```yaml
QueryResult:
  query_id: QRY-...
  context_id: CXI-...
  branch_id: BRN-...
  revision: 42
  result_items: [...]
  completeness:
    mode: EXACT_ENUMERATION | KNOWN_UNIVERSE_ENUMERATION | OPEN_WORLD_DISCOVERY
    coverage: ...
    saturation: ...
    blind_spots: [...]
    qualified_absences: [...]
  epistemic:
    hypotheses: [...]
    contradictions: [...]
    unknowns: [...]
    n_eff: ...
  provenance: { evidence_lineage, derivation_lineage, research_lineage }
  method_fingerprint: MF-...
```

`completeness.mode` is mandatory and non-nullable for any query compiled from a universal
term. A universal-negative is expressible **only** as a `CoverageQualifiedAbsence` meeting
the profile's coverage and detection-power thresholds; otherwise it is reported as "none
observed under declared coverage" (Appendix P.2).

---

## 4. Ranking contract (§20.3–20.4, v2) — replaces the v1 multiplicative formula

```text
1 hard gates are FILTERS: policy, capability, safety, feasibility==0  → blocked + reason
2 ranking_mode ∈ { LEXICOGRAPHIC, PARETO_THEN_TIEBREAK, WEIGHTED_ADDITIVE_NORMALIZED }
3 no cross-tier numeric comparison; tiers interleaved by profile-declared rule
4 exploration quota reserves a declared fraction, recorded as exploration_picks
5 cost floor ε > 0 where cost divides; unknown cost is UNKNOWN, never 0
6 every factor/normalisation echoed in the decision trace
```

**ADDED** — a ranking implementation that receives two candidates of different
`gain.tier` **must not** compare their numeric values. The property test in Appendix M.2
fails the build otherwise. Likewise `dominated()` (§46.1) is never evaluated across score
kinds.

---

## 5. Determinism and replay (§4, §36)

| Class | Identity requirement |
|---|---|
| `EXACT` | byte-identical on any platform |
| `FIXED_POINT` | byte-identical on any platform (declared scale) |
| `FLOAT_QUANTIZED` | quantized-identical across platforms; byte-identical on same build+platform |

Floating-point reductions use canonical order (sorted by stable id). Parallel execution
partitions deterministically and merges in canonical order. Wall-clock influences neither
identity, nor batch boundaries, nor ordering.

Replay uses **recorded** batch boundaries from the log, never wall-clock timers. After
erasure it returns `REPLAY_DEGRADED` with the list of unreadable inputs; digests of erased
inputs remain so all other integrity is still checkable (§36.3).

**ADDED** — `Replayed` is not a revision status. Replay emits a `ReplayReport` and never
creates or mutates a revision (§6.2).

---

## 6. Epistemic algebra (§13)

Five normative operations on `s = (p, n)`:

```text
negate(s)    = (n, p)
accumulate   = (p1 ∨ p2, n1 ∨ n2)   knowledge-join, same proposition
consensus    = (p1 ∧ p2, n1 ∧ n2)   knowledge-meet
and          = (p1 ∧ p2, n1 ∨ n2)   truth-order conjunction
or           = (p1 ∨ p2, n1 ∧ n2)   truth-order disjunction
```

`truth_state(P)` = `accumulate` over polarity contributions of **admitted** evidence for
`P` in the same scope/time qualifier. Independence does **not** change the flags — it changes
score weights. `truth_state(P) = BOTH` implies a `Contradiction` exists in the same
revision. Wave 1 requires full truth tables plus the lattice laws (idempotence,
commutativity, associativity, absorption, De Morgan under `negate`).

---

## 7. Method fingerprint (Appendix Q)

```yaml
MethodFingerprint:
  fingerprint_id: MF-...
  code_revision: string
  package_versions: {}          # concrete versions only — no ranges
  operator_versions: {}
  model_versions: {}
  semantic_regime_version: string
  policy_version: string
  reasoning_profile_version: string
  runtime_version: string
  numeric_environment: {platform, libm/BLAS build, float mode}
  build_metadata: {}
```

Floating dependencies (`latest`, `^1.2`, `>=1`) are invalid. Enforced from the first
operator registration, not retrofitted.

---

## 8. Governance (§49)

```text
Reasoning → ResearchAction → Approval/Policy → Task/Capability → Controlled execution → Observation
```

**ADDED** — §49.3 inference policy gate. The query compiler and the abduction/dialectics
generators check `InferencePolicy` **before** generating a hypothesis in a sensitive class;
blocked cases return `POLICY_BLOCKED`. Sensitive classes: attribution of control to a
natural person, linking pseudonymous identities, inferring protected attributes,
behavioural profiling of individuals. Permitted sensitive hypotheses are always labelled as
hypotheses with evidence and false-positive caveats.

---

## 9. Audit obligations (Appendix L, v2 — eight questions)

All eight must be answerable from durable state; a missing lineage edge is a test failure.

1. Why is this entity in my result? → claim → resolution → mentions → observations → captures → sources
2. Why is this relation in my result? → claim material → candidate → signals → mentions → observations → evidence
3. Why does the engine believe H? → revision → support/refutation (grouped, `n_eff`) → assumptions → model → space incl. `H_OTHER` mass → fingerprint
4. Why did the engine request source S? → action → test → target hypotheses → differential predictions → gain model (tier) → ranking mode/profile → capability → source
5. Why did the investigation stop? → closure → terminal obligations → saturation → coverage → marginal gain → qualified absences → budget → blind spots → policy
6. What changed when new evidence arrived? → event → batch → changeset → invalidated dependencies → revision → changed hypotheses/contradictions/frontier
7. Why was this candidate dropped? → pruned candidate → comparison set → dominance dimensions → operator version
8. Who overrode what? → analyst decision → target → justification → model-derived state beside it

---

## 10. Machine-checked coverage (Appendix Y, v2)

`T025-153` is a CI gate: every `FR-025-001…088` must appear in Appendix Y with ≥1 task and
≥1 test reference, or the build fails. This file, `data-model.md` and `tasks.md` are the three
maintained sides of that matrix.