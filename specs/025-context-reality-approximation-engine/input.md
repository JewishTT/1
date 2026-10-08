<!--
  VERBATIM INPUT — Specification 025 **v2** (Design Baseline v2) as supplied by the owner
  on 2026-10-04. Supersedes the v1 text previously stored here.

  Authoritative for every object schema, algorithm, state machine, data contract,
  requirement ID (FR-025-001..088), task ID (T025-001..154), acceptance gate (A..Q),
  wave gate and the v1->v2 change log.

  Do NOT edit, tidy or summarise. Where a later owner decision diverges from this text,
  the decision is recorded in decisions.md / docs/adr and this file stays untouched.

  Known deliberate divergences (recorded, not applied here):
    - ADR-0028 splits the CXI- namespace: CXI- = InvestigationContext, CXD- =
      ContextDefinition. Sections 5.1 and Appendix G.1 below still say CXI- for
      ContextDefinition. Preserved as written.
    - Control-plane placement is apps/control-plane/context_engine/, not the
      cp_domain/ path required by section 1.2. Superseded by ADR-0028.

  Sections 0-61, appendices A-Z follow.
-->
# COGNITIVE — Specification 025
## Context & Dialectical Reality Approximation Engine

Feature ID: `025-context-reality-approximation-engine`
Status: Design Baseline v2 / Implementation-Ready Draft
Supersedes: `025-context-reality-approximation-engine.md` (v1)
Depends on: `024-context-driven-continuous-intelligence`
Primary architectural position: the Context Engine is a domain capability over the existing COGNITIVE world substrate. It is not a new application, not a new event backbone, and not an LLM-centric "understanding layer".

> **Conflict rule with 024.** Where this document and 024 define the same lifecycle or object, **024 wins** for already-approved semantics. Any divergence found during Wave 0 is resolved by amending 025, not by redefining 024 (see §58.1).
>
> **Single source of normativity.** §54 (acceptance gates), Appendix T (requirement catalogue) and Appendix U (wave gates) are normative. §60 (Definition of Done) is a derived summary. Appendix Y maps every requirement to tasks, tests and gates. A v1→v2 change log is in Appendix Z.

---

## 0. Executive definition

### 0.1 What this feature actually builds

The feature builds a Context & Reality Approximation Engine (CRAE) that maintains a versioned approximation of a scoped, changing system from incomplete observations.

The engine must be able to answer four different questions without confusing them:

1. What was observed?
2. What interpretations are compatible with what was observed?
3. Which explanations currently provide the best account of the observations?
4. What should be investigated next to distinguish the remaining explanations?

The engine operates as a closed epistemic loop:

```text
OBSERVE
  ↓
CONTEXTUALIZE
  ↓
CONSTRAIN
  ↓
ESTIMATE STATE
  ↓
GENERATE HYPOTHESES
  ↓
COMPARE / CONTRADICT / EXPLAIN
  ↓
DEDUCE TESTABLE CONSEQUENCES
  ↓
SELECT DISCRIMINATING EVIDENCE
  ↓
RESEARCH / ACQUIRE
  ↓
OBSERVE NEW DATA
  ↓
REVISE CONTEXT
  ↺
```

The output is never just a scalar "confidence" or a single narrative. The output is a Context Revision containing:

```text
scope
state
observations
constraints
known structure
unknown structure
hypotheses (inside an explicit hypothesis space)
supporting evidence
refuting evidence
coverage-qualified absences
contradictions
assumptions
predictions and their outcomes
regime/dynamics findings
causal findings
topological findings
open obligations
saturation
provenance
method/version fingerprints
```

### 0.2 Core epistemic rule

> **Do not destroy observability when semantic certainty is unavailable.**

This rule is binding across every layer.

```text
unknown relation type
    ≠ discard relation signal

unresolved identity
    ≠ discard mention

contradictory sources
    ≠ overwrite one source

unknown hidden state
    ≠ state = false

no evidence observed
    ≠ evidence = negative

not searched
    ≠ not found

searched with unknown detection power
    ≠ negative finding

TDA anomaly
    ≠ causal explanation

high posterior
    ≠ truth

LLM suggestion
    ≠ admission
```

### 0.3 Architectural consequence

The system has five epistemic levels:

```text
L0  OBSERVATION
L1  INTERPRETATION
L2  ADMITTED WORLD MODEL
L3  HYPOTHESIS / EXPLANATION SPACE
L4  RESEARCH / DECISION FRONTIER
```

No API, persistence model or UI component may collapse these levels into a single generic "result".

---

## 1. Relationship to the existing COGNITIVE architecture

The repository already defines an event-driven, evidence-first investigation loop and a durable context/obligation layer. The canonical path is investigation → discovery → frontier → acquisition → immutable observation → interpretation → resolution → admission → projections → science → feedback.

This feature extends that loop rather than replacing it.

### 1.1 Existing substrate that is reused

```text
Investigation
InvestigationContext
ContextRevision
ResearchObligation
ResearchAction
ContextFrontier
Capture
Observation
Mention
RelationSignal
RelationCandidate
RelationClaim
Entity
WorldlineSnapshot
GraphProjection
Evidence lineage
Derivation lineage
Research lineage
SemanticRegime
Scientific evaluation
EventEnvelope
```

PostgreSQL is the authoritative operational/context graph store and Neo4j is a rebuildable serving projection; 025 respects that decision and introduces no other graph authority.

### 1.2 No new `apps/context-engine`

Forbidden:

```text
apps/context-engine/
```

Required placement:

```text
apps/shared/domain/context/
apps/control-plane/cp_domain/context_engine/
apps/science/context/
apps/projection/context/
apps/webapp/src/context/
```

The separation is functional:

```text
shared      = pure domain + deterministic contracts
control     = durable state + orchestration boundary
science     = algorithms / reasoning operators
projection  = serving read models
webapp      = operator presentation
```

---

## 2. Design principles

- **P01 — Observation precedes commitment.** Nothing below the observation layer may rewrite the observation.
- **P02 — Identity is not context inference.** Contextual compatibility may produce candidate identity evidence, but entity identity remains owned by resolution/admission.
- **P03 — Unknown is first-class.** Unknown, unresolved, incomplete and unobserved are distinct states.
- **P04 — Contradictions are durable.** Both sides of a contradiction remain readable.
- **P05 — Hypotheses compete.** The engine preserves multiple live explanations whenever the evidence does not justify collapsing them.
- **P06 — Every inference has a method.** A derived probability, score, classification, transition or explanation names the model/operator/version that produced it.
- **P07 — Deterministic core.** The constitutional core works with adaptive/neural components disabled.
- **P08 — Adaptive layer is subordinate.** LLMs or learned models may propose; the deterministic substrate decides what enters the authoritative epistemic state.
- **P09 — Rebuildability.** Every derived result is reproducible from immutable inputs plus declared method/version/policy/seed parameters.
- **P10 — Locality before global explosion.** All pair generation, hypothesis generation and graph traversal is bounded by named scopes, windows and budgets.
- **P11 — Semantics do not gate structure.** An unknown or unmapped predicate must not cause structural evidence to disappear.
- **P12 — No hidden second truth model.** The engine consumes and updates the existing world substrate rather than creating a parallel "context database" with its own entity truth.
- **P13 — Hypothesis spaces are explicit.** Any probability or information-gain computation names the hypothesis space it is relative to, including whether that space is exhaustive and what mass is reserved for "none of the above" (§15.3).
- **P14 — Evidence is counted by independence, not by volume.** Every aggregation rule consumes evidence dependency groups, not raw item counts (§14A).
- **P15 — Absence is only evidence under coverage.** A negative finding exists only as a coverage-qualified absence with declared detection power (§13A).
- **P16 — The analyst is a first-class actor.** Human assertions and decisions enter through the same observation/decision/admission boundaries as everything else, with provenance (§16A).
- **P17 — Different kinds of numbers are never compared.** Probabilities, heuristic scores and surrogates are not ranked against each other without an explicit, declared policy (§20.3).

---

## 3. Terminology

### 3.1 Context
A Context is a scoped analytical universe in which observations, entities, events, relations, states and hypotheses are evaluated under a defined purpose, temporal range, semantic regime and policy. Context is not merely a document window.

### 3.2 Local context cell
A ContextCell is a local section of information: a source, document, event window, entity neighbourhood, market slice, geographic region, institutional scope or other bounded observational domain.

### 3.3 Context overlap
An Overlap is a pair (or, for triple checks, a triple) of context cells sharing enough scope to permit compatibility comparison.

### 3.4 Restriction
A RestrictionMap projects information from a larger context onto a smaller overlap scope.

### 3.5 Gluing
Gluing asks whether compatible local sections can be combined into a larger coherent section without hiding conflicts. Pairwise compatibility is necessary but not sufficient; coherence on triple overlaps is also checked (§10.2).

The implementation is sheaf-inspired. It must not claim that the platform has implemented a formal sheaf library or mathematical topos unless such a dependency is actually introduced. The terms "section", "restriction" and "obstruction" are used in an operational sense defined in this document.

### 3.6 Hidden state
A HiddenState is a state variable that is not directly observed but can be estimated from observations through an explicit observation model.

### 3.7 Hypothesis
A Hypothesis is a versioned candidate explanation/model that may be supported, contradicted, incomplete or unresolved. It always lives inside a HypothesisSpace.

### 3.8 Explanation
An Explanation is a structured mapping from observations to a hypothesis, including mechanisms, assumptions, evidence, gaps and predictions.

### 3.9 Obstruction
An Obstruction is a recorded reason why local context sections cannot currently be glued into a coherent larger state. It is not merely an error; it is actionable research information.

### 3.10 Regime
A Regime is a bounded interval or region in state-space where a declared structural/dynamical descriptor remains approximately stable.

### 3.11 Transition
A TransitionWindow is a bounded period in which evidence indicates that a system is changing between regimes.

### 3.12 Discriminating test
A DiscriminatingTest is an evidence request selected because different live hypotheses make meaningfully different predictions about its outcome.

### 3.13 Proposition
A Proposition is a normalized, canonically identified statement (subject, predicate, object, scope, temporal qualifier) to which evidence can attach polarity. Truth state (§13) is a property of a proposition within a context revision.

### 3.14 Branch
A Branch is an isolated line of context revisions forked from a given revision, used for scenarios and counterfactuals. Branches never write into the mainline (§6.4).

### 3.15 Evidence dependency group
A set of evidence items that are not independent of each other (same underlying observation, syndication chain, transformation chain, extraction method, etc.). See §14A.

---
## 4. Formal state of the engine

The minimum state of a context branch at revision `r` is:

```text
S_r = (O_r, C_r, I_r, W_r, H_r, K_r, D_r, G_r, R_r, F_r, P_r, M_r)
```

where:

```text
O = observations (including analyst inputs, coverage-qualified absences)
C = constraints
I = interpretations
W = admitted world state references
H = hypothesis spaces and hypotheses
K = contradictions / knowledge conflict state
D = dynamics / regime state
G = information gaps / obstructions
R = research frontier
F = supporting fingerprints/provenance
P = policies and parameters (including seeds)
M = method/operator versions
```

A transition is:

```text
S_(r+1) = T(S_r, ChangeBatch, rule_set, parameter_set)
```

The deterministic core MUST satisfy the **determinism contract** (v2):

```text
same(S_r, ordered ChangeBatch, rule_set, parameter_set, seeds)
    => identical(S_(r+1))
```

where "identical" is defined by §4.1.

### 4.1 Determinism classes (v2)

Byte-identity across heterogeneous platforms is not achievable for floating-point-backed artifacts, so identity is defined per artifact class:

| Class | Applies to | Requirement |
|---|---|---|
| `EXACT` | ids, graphs, sets, categorical/structural artifacts, integer/decimal arithmetic | byte-identical on any platform |
| `FIXED_POINT` | quantities with declared scale (money, counts, ratios with fixed scale) | byte-identical on any platform |
| `FLOAT_QUANTIZED` | floating-point results | identity material is the value quantized to a declared number of significant digits; byte-identical on the same build+platform, **quantized-identical** across platforms |

Rules:

- Every operator declares its `numeric_mode` ∈ {EXACT, FIXED_POINT, FLOAT_QUANTIZED}.
- Floating-point reductions MUST use a canonical order (sorted by stable id); parallel execution partitions deterministically and merges in canonical order.
- Stochastic operators (MCMC, subsampling, randomized TDA approximations, tie-breaking) MUST use a seed derived as
  `seed = digest128(context_id, branch_id, parent_revision, operator_id, run_ordinal)`
  and the seed is part of the parameter fingerprint. No ambient RNG.
- Wall-clock timestamps MUST NOT influence deterministic content identity, batch boundaries or ordering.
- Replay compares artifacts at their declared class; a mismatch in a `FLOAT_QUANTIZED` artifact beyond quantization is a defect.

### 4.2 Canonical event order and batches (v2)

- Each context branch has exactly **one sequencer**; it assigns a gapless `context_event_seq` to incoming events. Ties between simultaneous arrivals are broken by `(source_event_id)` lexicographic order and the resulting order is persisted in the event log manifest.
- Events are partitioned by context partition key so that per-context total order is preserved across Redpanda partitions.
- Revisions are produced per **ChangeBatch**: a contiguous run of sequenced events. Batch boundaries are closed by count or logical window (e.g. `max_events`, `max_logical_span`) and are **recorded** in the log; replay uses the recorded boundaries, never wall-clock timers.
- A tick on a batch yields at most one new revision (no revision-per-event explosion).## 5. Core domain model

### 5.1 `ContextDefinition`

Immutable definition of the scope and objective of a context.

| Field | Type | Required | Identity input | Meaning |
|---|---|---|---|---|
| `context_id` | `CXI-*` | yes | generated | Durable identity |
| `tenant_id` | UUID | yes | yes | Tenant scope |
| `investigation_id` | UUID | yes | yes | Parent investigation |
| `name` | string | yes | yes | Human label |
| `objective` | structured text | yes | yes | Analytical objective |
| `scope` | object | yes | yes | Entity/event/source/geographic scope |
| `temporal_scope` | object | yes | yes | Time interval/window semantics |
| `semantic_regime_ref` | ID | yes | yes | Semantic interpretation regime |
| `analysis_profile_ref` | ID | yes | yes | Operator policy profile |
| `reasoning_profile_ref` | `RPF-*` | yes | yes | Ranking/scoring/gain policy (§20.4) |
| `policy_ref` | ID | yes | yes | Collection/reasoning policy |
| `inference_policy_ref` | ID | yes | yes | Permissible-inference policy (§49.3) |
| `retention_policy_ref` | `RET-*` | yes | no | Retention/erasure policy (§39.3) |
| `created_by` | principal | yes | no | Audit field |
| `created_at` | timestamp | yes | no | Audit timestamp |

Identity rule:

```text
context_id = CXI-{digest128(canonical(identity_material))}
```

`identity_material` excludes: revision, obligation statuses, hypothesis scores, runtime timestamps, cache state, projection offsets, retention policy.

---

## 6. Context revision model

### 6.1 `ContextRevision`

A context revision is an immutable state snapshot. To avoid storing full state per revision, a revision is a **manifest of content-addressed artifacts** (§39.4); unchanged artifacts are shared structurally with the parent revision.

```yaml
ContextRevision:
  context_id: CXI-...
  branch_id: BRN-...          # mainline branch is the default branch of the context
  revision: 42
  parent_revision: 41
  state_hash: REV-...         # digest over the manifest (artifact digests, per class §4.1)
  manifest_ref: artifact digest
  batch_ref: change batch id + recorded boundaries
  input_event_refs: []
  decision_refs: []
  obligation_refs: []
  hypothesis_refs: []
  contradiction_refs: []
  worldline_snapshot_ref: WLS-...
  method_fingerprint: MF-...
  policy_fingerprint: PF-...
  created_at: timestamp       # audit only; not identity
```

Invariants:

1. `revision` is monotonically increasing per `(context_id, branch_id)`.
2. `parent_revision` is exactly the prior committed revision except for genesis (and for the first revision of a fork, whose parent is in the source branch — §6.4).
3. A revision cannot be edited after commit.
4. A later revision supersedes state; it does not mutate history.
5. Every revision has a complete causal/provenance explanation.
6. A revision is visible only after its transaction commits.
7. Commit uses **optimistic concurrency** on `(context_id, branch_id, parent_revision)`; a conflicting writer fails and re-proposes. The sequencer (§4.2) makes this the exceptional path.

### 6.2 Revision status

```text
PROPOSED
VALIDATING
COMMITTED
SUPERSEDED
REJECTED
```

Only `COMMITTED` revisions participate in ordinary serving queries.

`REPLAYED` is **not** a revision status (v2). Replay is a run mode: it produces a `ReplayReport` comparing artifact digests of the replayed state with the committed state; it never creates or alters a revision.

### 6.3 Late and out-of-order data
See §24.4. A late event never edits a past revision; it produces a new revision on the same branch that supersedes the affected state.

### 6.4 Branches, scenarios and counterfactuals (v2)

```yaml
ContextBranch:
  branch_id: BRN-...
  context_id: CXI-...
  branch_kind: MAINLINE | SCENARIO | COUNTERFACTUAL | WHAT_IF
  forked_from: {branch_id, revision}
  intervention_set: [...]       # for COUNTERFACTUAL / WHAT_IF
  assumptions_overlay: [...]
  status: ACTIVE | ARCHIVED
```

Rules:

- A non-mainline branch **never** writes into mainline revisions, evidence, truth states or admission decisions.
- Branch outputs are labelled by branch in every API and UI surface; a counterfactual result can never be rendered as an observed or inferred finding on the mainline.
- Branch identity is part of the revision key; branch contents are derived views over mainline evidence plus the declared overlay.
- Merging a branch result into the mainline is not an operation. A scenario may only be *cited* as a hypothesis premise with `provenance = BRANCH_DERIVED`.

---

## 7. Context cells and locality fabric

### 7.1 `ContextCell`

```yaml
ContextCell:
  cell_id: CXC-...
  context_id: CXI-...
  cell_kind: SOURCE | DOCUMENT | EVENT_WINDOW | ENTITY_EGO | GEO | ORGANIZATION | MARKET | CUSTOM
  scope_descriptor: {...}
  temporal_slice: {...}
  observation_refs: [...]
  entity_refs: [...]
  relation_refs: [...]
  state_refs: [...]
  semantic_regime_ref: SR-...
  completeness: {...}
  trust_state: VERIFIED | UNVERIFIED | CONTESTED | UNKNOWN
  produced_by: operator-id
  method_fingerprint: MF-...
```

Cell design rule: a cell must be independently inspectable. A caller must be able to answer:

```text
why is this datum in this cell?
what scope produced the cell?
what observations support it?
what time interval does it represent?
what semantic regime was used?
```

### 7.2 Cell scope algebra

Scopes are explicit objects: `EntityScope`, `EventScope`, `SourceScope`, `TemporalScope`, `GeospatialScope`, `OrganizationalScope`, `SemanticScope`, `NetworkScope`, `CustomScope`.

Scope intersection returns exactly one of:

```text
EMPTY
PARTIAL
EXACT
UNKNOWN
```

No scope intersection may be inferred from string equality alone.

---

## 8. Restriction and overlap model

### 8.1 `RestrictionMap`

```yaml
RestrictionMap:
  restriction_id: RST-...
  from_cell: CXC-...
  to_scope: {...}
  projected_observations: [...]
  projected_entities: [...]
  projected_relations: [...]
  projected_states: [...]
  loss_profile:
    entities_removed: int
    relations_removed: int
    temporal_precision_loss: enum
    semantic_precision_loss: enum
  method_fingerprint: MF-...
```

Restrictions must be monotonic with respect to observability: a restriction may reduce scope, may reduce precision, and must NOT fabricate information.

### 8.2 `ContextOverlap`

```yaml
ContextOverlap:
  overlap_id: OVL-...
  context_id: CXI-...
  cells: [CXC-..., CXC-...]        # 2 cells (pair) or 3 cells (triple, §10.2)
  overlap_scope: {...}
  overlapping_observations: [...]
  overlapping_entities: [...]
  overlapping_relations: [...]
  overlapping_time: {...}
  compatibility_status: UNRESOLVED | COMPATIBLE | INCOMPATIBLE | PARTIAL
```

(`UNKNOWN` is replaced by `UNRESOLVED` so that overlap status and assessment verdict share one vocabulary — §9.1.)

### 8.3 Boundedness

The engine MUST NOT compare all cells with all cells. Required blocking keys:

```text
same investigation
same temporal bucket
scope intersection != EMPTY
shared entity/participant
shared source lineage
same geospatial tile (when applicable)
semantic profile compatibility
```

Bucket overflow, triple-budget exhaustion and any other truncation are recorded (Appendix I.1, §45.2), never silent.

---

## 9. Compatibility engine

### 9.1 `CompatibilityAssessment`

```yaml
CompatibilityAssessment:
  assessment_id: CMP-...
  overlap_id: OVL-...
  dimensions:
    identity: {...}
    temporal: {...}
    spatial: {...}
    semantic: {...}
    structural: {...}
    numeric: {...}
    provenance: {...}
    causal: {...}
  verdict: COMPATIBLE | PARTIAL | INCOMPATIBLE | UNRESOLVED
  blocking_dimensions: [...]
  supporting_evidence: [...]
  contradicting_evidence: [...]
  missing_evidence: [...]
  operator: compatibility.operator.v1
  method_fingerprint: MF-...
```

Per-dimension verdicts are typed: `SUPPORTED | CONTRADICTED | UNKNOWN | NOT_APPLICABLE` (Appendix I.2). The vector is authoritative; the single `verdict` is a profile-derived summary.

### 9.2 Dimension semantics

- **Identity compatibility.** Uses durable resolution outputs where available. Context is not allowed to invent identity.
- **Temporal compatibility.** Evaluates explicit time relations from the full interval algebra (§24.2). The six platform time axes remain distinct; no axis may be substituted for another, and every temporal verdict names the axis it was computed on.
- **Semantic compatibility.** Evaluates mappings under an explicit semantic regime, preserving `UNKNOWN` where no mapping exists.
- **Structural compatibility.** Compares graph/hypergraph patterns under declared tolerance.
- **Numeric compatibility.** Uses declared units, precision, intervals and tolerance. Missing numeric data is not zero.

---

## 10. Gluing engine

### 10.1 `GluingResult`

```yaml
GluingResult:
  gluing_id: GLU-...
  context_id: CXI-...
  input_cells: [...]
  merged_scope: {...}
  merged_state_refs: [...]
  conflicts: [...]
  obstructions: [...]
  triples_checked: int
  triples_unchecked: int          # truncated by budget; reason recorded
  completeness: {...}
  verdict: GLUED | PARTIALLY_GLUED | BLOCKED
  method_fingerprint: MF-...
```

### 10.2 Gluing rule (v2: includes triple coherence)

For cells `C1 ... Cn`:

```text
1. construct overlaps (pairs) under bounded blocking
2. restrict each cell to overlaps
3. compare restrictions pairwise / blockwise
4. identify compatible observations
5. identify contradictions
6. TRIPLE COHERENCE: for every triangle (Ci, Cj, Ck) of the overlap graph
   (all three pairwise overlaps non-empty), restrict to the triple overlap
   and check that the three pairwise-compatible restrictions agree there
   (a cocycle-style consistency check)
7. preserve both compatible and contradictory contributions
8. construct merged candidate section
9. emit obstructions for unresolved joins and for triple inconsistencies
```

Rationale: pairwise compatibility does not imply global coherence. A triple of locally compatible pairs can still be jointly inconsistent (e.g. A≈B on time, B≈C on time, A≉C on time via different chains). These are the genuine "gluing obstructions".

Bounds: triples are enumerated only from triangles in the existing overlap graph, in stable id order, up to `max_triples` per gluing run. Unchecked triples are counted in `triples_unchecked` with a truncation reason. Higher-order (k>3) coherence is out of scope; if not implemented, documentation and UI must not claim global coherence — only "pair- and triple-coherent under budget".

Critical rule: `BLOCKED` does not mean `FALSE`. It means current evidence is insufficient to produce a coherent merged section.

### 10.3 Obstruction taxonomy

```text
TEMPORAL_OBSTRUCTION
SEMANTIC_OBSTRUCTION
IDENTITY_OBSTRUCTION
STRUCTURAL_OBSTRUCTION
NUMERIC_OBSTRUCTION
PROVENANCE_OBSTRUCTION
SCOPE_OBSTRUCTION
MISSING_COVERAGE
SOURCE_CONFLICT
MODEL_CONFLICT
TRIPLE_INCONSISTENCY
BUCKET_OVERFLOW
```

Obstruction identifiers use the prefix `OBST-` (v2; `OBS-` is reserved for Observation). Each obstruction MAY become a `ResearchObligation`.

---

## 11. State-space model

### 11.1 `StateVariable`

```yaml
StateVariable:
  variable_id: VAR-...
  context_id: CXI-...
  name: string
  value_type: scalar | categorical | vector | distribution | graph_feature | set
  unit: optional
  domain: optional
  observable: true | false | partial
  temporal_resolution: {...}
  source_mapping: {...}
  numeric_mode: EXACT | FIXED_POINT | FLOAT_QUANTIZED
```

Examples: `exchange_reserves`, `supplier_concentration`, `network_density`, `media_attention`, `capital_flow_rate`, `organizational_headcount`, `entity_activity_rate`, `claim_support_ratio`.

### 11.2 `StateEstimate`

```yaml
StateEstimate:
  estimate_id: STE-...
  variable_id: VAR-...
  time_interval: {...}
  estimate:
    point: optional
    interval: optional
    distribution: optional
    feasible_set: optional
  epistemic_status: OBSERVED | ESTIMATED | LATENT | UNKNOWN | INCONSISTENT
  evidence_refs: [...]
  model_ref: MOD-...
  method_fingerprint: MF-...
```

A latent state MUST NEVER be serialized as if it were observed. `INCONSISTENT` means the constraints admit an empty feasible set; the minimal conflict set is stored as residual (§12.3).

---

## 12. Observation model and hidden state

### 12.1 System model

```text
x_(t+1) = f(x_t, u_t, ε_t)
y_t     = g(x_t, ν_t)
```

where `x` = latent/system state, `u` = declared input/intervention/exogenous variable, `ε` = process uncertainty, `y` = observation, `ν` = observation noise/uncertainty. The implementation does not assume linearity.

### 12.2 `ObservationModel`

```yaml
ObservationModel:
  model_id: MOD-...
  state_variables: [...]
  observed_variables: [...]
  transition_operator: optional
  emission_operator: required
  assumptions: [...]
  parameter_set: {...}
  parameter_fingerprint: PF-...
```

### 12.3 State estimator contract

```python
estimate_state(
    prior_state,
    observations,
    model,
    constraints,
    parameters,
) -> StateEstimateBatch
```

Required outputs: posterior / feasible set, residuals, unexplained observations, sensitivity, missing evidence, method fingerprint. A successful estimator that cannot explain an observation must emit the residual rather than dropping it.

### 12.4 Baseline estimator: interval constraint propagation (v2)

The deterministic baseline (T025-045) is **interval/constraint propagation**, deliberately not a Kalman-style filter:

- Each state variable carries an interval (or finite set) domain; unobserved variables start unbounded = `UNKNOWN`.
- Observations narrow domains by intersection with their (unit-aware, tolerance-aware) intervals.
- Declared constraints (sums, bounds, monotonicity, conservation) propagate to a fixed point in canonical constraint order.
- An empty domain produces `INCONSISTENT` with a minimal conflicting constraint/observation set as the residual; nothing is dropped.
- Unbounded domains after propagation stay `UNKNOWN`; they are never defaulted to zero.
- The output is a *feasible set*; probabilistic estimators (Tier 2) refine within it and must declare their model.

This yields honest "unknown" and residual behaviour without claiming a dynamical model.

---
## 13. Epistemic algebra

### 13.1 Four-valued support state (Belnap–Dunn)

Truth state is a pair of independent support flags attached to a **Proposition** (§3.13) within a context revision and branch:

```yaml
TruthState:
  positive_support: bool
  negative_support: bool
```

| (positive, negative) | State |
|---|---|
| (false, false) | `NEITHER` |
| (true, false) | `TRUE_ONLY` |
| (false, true) | `FALSE_ONLY` |
| (true, true) | `BOTH` |

Two orders (corrected diagrams):

Knowledge (information) order — more evidence is higher:

```text
           BOTH
          /    \
   TRUE_ONLY  FALSE_ONLY
          \    /
          NEITHER
```

Truth order — more true is higher:

```text
         TRUE_ONLY
          /    \
     NEITHER   BOTH
          \    /
         FALSE_ONLY
```

### 13.2 Operations (normative)

Let `s = (p, n)`.

| Operation | Definition | Use |
|---|---|---|
| `negate(s)` | `(n, p)` | polarity inversion of a proposition |
| `accumulate(s1, s2)` | `(p1 ∨ p2, n1 ∨ n2)` | knowledge-join: combining admitted evidence about the **same** proposition |
| `consensus(s1, s2)` | `(p1 ∧ p2, n1 ∧ n2)` | knowledge-meet: what two bodies of evidence agree on |
| `and(s1, s2)` | `(p1 ∧ p2, n1 ∨ n2)` | truth-order conjunction (for compound propositions) |
| `or(s1, s2)` | `(p1 ∨ p2, n1 ∧ n2)` | truth-order disjunction |

Rules:

- `truth_state(P)` = `accumulate` over the polarity contributions of **admitted** evidence items for `P`, restricted to evidence in the same scope/time qualifier. Unadmitted proposals contribute nothing.
- A contribution requires an *admissible* evidence item (passed admission, not a coverage-qualified absence below threshold — §13A). Independence (§14A) does **not** change `positive_support`/`negative_support` (these are existence flags); it changes *weights* in scores.
- `truth_state` and `score` are independent fields. `truth_state` never converts to a probability.
- A compound hypothesis statement's truth state is composed by `and`/`or`/`negate` over its component propositions.
- The unit tests required by Wave 1 are the full truth tables of the five operations plus the lattice laws (idempotence, commutativity, associativity, absorption, De Morgan under `negate`).

### 13.3 Relation to `Contradiction`

- `truth_state(P) = BOTH` ⇒ there MUST exist (or be created in the same revision) a `Contradiction` object whose two sides are the positive and negative support sets of `P`.
- A `Contradiction` may exist without `BOTH` (e.g. numeric or structural contradictions between different propositions). Its `subject_ref` identifies the proposition(s) involved.
- Resolving a contradiction (EXPLAINED/RESOLVED) never deletes support flags: it records an explanation (e.g. different time qualifiers, different referents) and may, via re-scoping, create *distinct* propositions. The prior revision still shows `BOTH`.

### 13.4 Confidence is a separate, targeted quantity

```text
truth_state = BOTH
score = { kind: MODEL_POSTERIOR, value: 0.88, target: "P(proposition X | evidence, model M, space HSP-…)" }
```

is legal and means: strong evidence exists on both sides; the declared model, within the declared hypothesis space, assigns 0.88 to X. Every score MUST carry `target` (the estimand), `model_ref`, and `hypothesis_space_ref` where applicable. The UI shows truth state, score kind, target and calibration status together.---
## 13A. Coverage-qualified absence (v2)

"Searched and found nothing" is evidence only under declared coverage.

```yaml
CoverageQualifiedAbsence:
  absence_id: CQA-...
  context_id: CXI-...
  query: structured                  # what was looked for
  source_set: [...]                  # where it was looked for
  window: {...}                      # time window covered
  coverage: value | interval | UNKNOWN
  detection_power: value | interval | UNKNOWN   # P(detect | present), per source class
  errors_accounted: bool             # pagination complete, source errors accounted
  result: NOT_FOUND_UNDER_COVERAGE
  admissibility: NEGATIVE_EVIDENCE | INFORMATIONAL_ONLY
  research_action_ref: ACT-...
  method_fingerprint: MF-...
```

Rules:

- `admissibility = NEGATIVE_EVIDENCE` only if the active profile's thresholds on coverage and detection power are met **and** the absence is relevant to a falsifiable prediction. Only then may it contribute `negative_support` to the relevant proposition.
- Otherwise it is `INFORMATIONAL_ONLY`: it is stored, shown, and feeds saturation/coverage, but contributes `NEITHER`.
- Unknown detection power ⇒ `INFORMATIONAL_ONLY`, always.
- A non-search ("not searched") is not an object of this type and never contributes.
- Universal-negative query results (`none`) use this object (Appendix P).

---
## 14. Confidence and probability

### 14.1 Prohibition
No probability may be invented merely because a UI or API expects a number.

### 14.2 Every probability needs

```text
model_id
model_version
target (estimand)
hypothesis_space_ref (if over hypotheses)
input evidence refs and dependency groups used
calibration status
prior specification (if applicable)
update rule
parameter fingerprint (including seed)
calibration cohort/version
```

### 14.3 Probability categories (single vocabulary, v2)

```text
MODEL_POSTERIOR
HEURISTIC_SCORE
EMPIRICAL_FREQUENCY
CALIBRATED_SCORE
INTERVAL_ONLY
UNKNOWN
```

`Hypothesis.score.kind` uses exactly this set (plus `NONE` meaning no score). A `HEURISTIC_SCORE` is never serialized as a probability and never compared with a probability (§20.3).

### 14.4 Calibration cohorts (v2)

Calibration needs ground truth. The source of ground truth is `PredictionOutcome` (§19.3): predictions with resolved outcomes (CONFIRMED / FALSIFIED) form a cohort keyed by `(model_ref, score kind, domain/profile, time range)`. A `CALIBRATED_SCORE` may be emitted only for a model whose cohort meets the profile's minimum size and whose calibration error is within the profile's tolerance. Cohort definition and version are persisted and referenced from the score.

---

## 14A. Evidence dependency and independence model (v2)

Source count is not source independence, and correlated evidence double-counts. A single model governs every aggregation (posterior updates, support ratios, saturation, contradiction independence).

### 14A.1 `EvidenceDependencyGroup`

```yaml
EvidenceDependencyGroup:
  group_id: EDG-...
  members: [EVID-...]
  dependence_basis:
    - SAME_UNDERLYING_OBSERVATION
    - SYNDICATION_LINEAGE
    - SAME_TRANSFORMATION_CHAIN
    - SAME_EXTRACTION_METHOD
    - SAME_PUBLISHER / SOURCE_FAMILY
    - SAME_UPSTREAM_MODEL
  correlation_model: DECLARED_DISCOUNT | MAX_ONLY | PROFILE_SPECIFIC
  assessed_by: operator-id
```

Groups are derived deterministically from evidence lineage (§37) plus declared rules; assignments are persisted and versioned.

### 14A.2 Use in updates

- Every update rule that combines evidence MUST consume groups, not items: within a group the contribution is `max` or a declared discount; across groups, contributions combine under the rule's independence assumption (which is itself a declared assumption in the Assumption ledger).
- `effective_independent_sources (n_eff)` is computed from the groups and reported next to the raw count wherever either is shown.
- A rule that cannot determine dependence (lineage unknown) treats the items as one group and records `INDEPENDENCE_UNKNOWN`.
- `truth_state` flags are unaffected (existence of support); scores, saturation `distinct_sources`, and contradiction independence use groups.

---

## 15. Hypothesis object

### 15.1 `Hypothesis`

```yaml
Hypothesis:
  hypothesis_id: HYP-...
  logical_id: LHYP-...
  revision: int
  context_id: CXI-...
  branch_id: BRN-...
  space_ref: HSP-...
  statement: structured semantic object
  hypothesis_kind: EXPLANATORY | CAUSAL | TEMPORAL | STRUCTURAL | IDENTITY | STATE | STRATEGIC | CLASSIFICATION | RESIDUAL
  scope: {...}
  assumptions: [...]
  premises: [...]
  supporting_evidence: [...]
  refuting_evidence: [...]
  missing_evidence: [...]
  truth_state: TruthState
  status: PROPOSED | ACTIVE | CONTESTED | UNRESOLVED | CONFIRMED | DISCARDED | SUPERSEDED
  trend: STRENGTHENED | WEAKENED | STABLE | NEW      # derived vs previous revision
  score:
    kind: MODEL_POSTERIOR | HEURISTIC_SCORE | EMPIRICAL_FREQUENCY | CALIBRATED_SCORE | INTERVAL_ONLY | UNKNOWN | NONE
    value: optional
    target: optional
    model_ref: optional
  predictions: [...]
  discriminating_tests: [...]
  parent_hypotheses: [...]
  competing_with: [...]
  derived_from: [...]
  method_fingerprint: MF-...
```

Change from v1: `STRENGTHENED`/`WEAKENED` are no longer lifecycle states; they are a derived `trend` comparing consecutive revisions. This removes the ambiguity between "state" and "direction of change".

### 15.2 Hypothesis identity

```text
logical_id = stable canonical hypothesis material (statement, kind, scope)
revision   = a concrete assessment under a context revision
```

Changing evidence or score must not mutate the previous evaluation.

### 15.3 `HypothesisSpace` (v2)

Posteriors and information gain are only meaningful relative to a declared space.

```yaml
HypothesisSpace:
  space_id: HSP-...
  context_id: CXI-...
  question: structured                 # what the hypotheses are alternative answers to
  members: [LHYP-...]
  exclusivity_groups:                  # sets of mutually exclusive members
    - [LHYP-a, LHYP-b, LHYP-c]
  compatible_pairs: [[LHYP-a, LHYP-d]] # members that may be jointly true
  exhaustive: true | false | UNKNOWN
  residual:
    hypothesis_id: HYP-...             # explicit H_OTHER ("none of the listed")
    prior_mass: declared by profile
    posterior_mass: optional
```

Rules:

- If `exhaustive != true`, the space MUST contain a `RESIDUAL` hypothesis (`H_OTHER`) with declared prior mass. Posterior and entropy computations include it.
- Probabilities are computed within an exclusivity group; compatible (non-exclusive) hypotheses are not normalized against each other.
- Information gain (§20.2) is computed on the space the test addresses, including `H_OTHER`. A test that only splits listed hypotheses while `H_OTHER` holds substantial mass is reported as such.
- `H_OTHER` mass can only be reduced by evidence or by admission of a concrete new hypothesis into the space (which draws mass from `H_OTHER` under a declared rule); it is never silently renormalized away.

### 15.4 Lifecycle (normative transition table)

```text
PROPOSED   → ACTIVE | DISCARDED
ACTIVE     → CONTESTED | UNRESOLVED | CONFIRMED | DISCARDED | SUPERSEDED
CONTESTED  → ACTIVE | UNRESOLVED | CONFIRMED | DISCARDED | SUPERSEDED
UNRESOLVED → ACTIVE | CONTESTED | DISCARDED | SUPERSEDED
CONFIRMED  → CONTESTED | SUPERSEDED              # confirmation is revisable by contrary evidence
DISCARDED  → ACTIVE (only on new evidence/profile change, as a new revision) | SUPERSEDED
SUPERSEDED → (terminal)
```

Forbidden: `PROPOSED → CONFIRMED`; any transition without a recorded DecisionTrace; `SUPERSEDED → *`. Status is a property of a hypothesis *revision*; "transitions" create new revisions, they do not edit old ones.

`CONFIRMED` is a profile-specific epistemic state. It never means metaphysical truth. The profile declares the admission threshold (evidence independence, calibration, refutation attempts survived) required to use it.

---

## 16. Assumption ledger

### 16.1 `Assumption`

```yaml
Assumption:
  assumption_id: ASM-...
  hypothesis_id: HYP-...
  statement: structured
  importance: LOW | MEDIUM | HIGH | CRITICAL
  status: OPEN | SUPPORTED | REFUTED | UNTESTABLE | PINNED
  evidence_refs: [...]
  sensitivity: {...}
  introduced_by: operator | rule | model | analyst
  method_fingerprint: MF-...
```

### 16.2 Assumption discipline

Every causal, strategic, hidden-state or counterfactual hypothesis must expose assumptions. Independence assumptions of update rules (§14A) are assumptions in this ledger. The UI must make it possible to say "this conclusion depends on assumption A3" without requiring the analyst to inspect logs. `PINNED` marks an analyst-fixed assumption (§16A).

---

## 16A. Analyst in the loop (v2)

The analyst is a first-class source of inputs and decisions.

```yaml
AnalystAssertion:           # enters as an observation of kind ANALYST_INPUT
  assertion_id: ANL-...
  principal: ...
  statement: structured
  basis: free text + evidence refs
  admission: via the standard interpretation/admission path
```

```yaml
AnalystDecision:            # recorded as a DecisionTrace with a principal
  decision_id: DEC-...
  kind: ACCEPT_HYPOTHESIS | REJECT_HYPOTHESIS | PIN_ASSUMPTION | DISMISS_OBLIGATION | APPROVE_ACTION | REJECT_ACTION | SET_PRIORITY | OVERRIDE_STATUS
  target_ref: ...
  justification: required
  principal: ...
```

Rules:

- Analyst inputs never edit evidence or observations. They are new observations or decisions.
- An analyst override of a hypothesis status is stored as a decision and displayed as `OVERRIDDEN_BY_ANALYST` beside the model-derived status; both remain visible.
- Pinned assumptions are inputs to re-evaluation, flagged in all downstream explanations.
- Analyst assertions are subject to the same independence accounting (an analyst repeating a source is not independent of it).

---

## 17. Abductive engine

### 17.1 Purpose
Abduction asks: given observations E and candidate explanations H, which explanations best account for E under the active model and assumptions? It does not mean "invent the most interesting story".

### 17.2 Inputs
observations, relations, state estimates, constraints, known rules, semantic profile, prior hypotheses, candidate operator set, resource budget, hypothesis space.

### 17.3 Outputs
candidate hypotheses, explanations, support/refutation links, missing evidence, predictions, discriminating tests, complexity cost.

### 17.4 Abduction operator contract

```python
abduce(
    context: ContextRevision,
    evidence: EvidenceView,
    constraints: ConstraintSet,
    operators: OperatorSet,
    budget: ComputeBudget,
    seed: Seed,
) -> AbductiveResult
```

`AbductiveResult` contains: hypotheses, rejected_candidates, truncation_reason, search_cost, operator_versions, provenance.

### 17.5 Candidate-generation strategy
Bounded generators. Minimum families: `RULE_ABDUCTION`, `STRUCTURAL_TEMPLATE`, `TEMPORAL_TEMPLATE`, `CAUSE_TEMPLATE`, `STATE_TRANSITION_TEMPLATE`, `GRAPH_PATTERN`, `ANOMALY_EXPLANATION`, `CONSTRAINT_REPAIR`.

### 17.6 Minimal explanation preference

```text
score(H) = evidential_fit(H)
           - complexity_penalty(H)
           - unsupported_assumption_penalty(H)
           - contradiction_penalty(H)
```

Complexity is a ranking criterion, not "Occam says true". The formula is versioned and configurable in the ReasoningProfile (§20.4). Evidential fit consumes dependency groups (§14A). This is a `HEURISTIC_SCORE` unless embedded in a declared probabilistic model.

### 17.7 Diversity preservation and material difference (v2)

Top-k selection MUST NOT return k near-duplicates. Two hypotheses are **materially different** iff all of:

1. their structural signatures differ by at least `τ` on at least one declared facet: `mechanism`, `actor_configuration`, `temporal_explanation`, `causal_direction`, `source_interpretation`, `state_transition` (distance metric and `τ` are profile parameters);
2. and they have non-empty differential predictions (some prediction on which they disagree), **or** differ in at least one critical assumption.

Hypotheses failing (1)∧(2) are treated as duplicates (`COUNTERHYPOTHESIS_DUPLICATE` in dialectics). The metric, threshold, and the comparison result are persisted so the decision is reproducible.

---

## 18. Dialectical reasoning engine

### 18.1 Purpose
Expose the strongest competing interpretations rather than prematurely converging.

### 18.2 Cycle

```text
THESIS
  ↓
COUNTER-HYPOTHESIS GENERATION
  ↓
COMMON PREMISE EXTRACTION
  ↓
DIFFERENCE ANALYSIS
  ↓
TESTABLE CONSEQUENCES
  ↓
DISCRIMINATING EVIDENCE
  ↓
REVISION
```

### 18.3 `DialecticalPair`

```yaml
DialecticalPair:
  pair_id: DLP-...
  context_id: CXI-...
  thesis: HYP-...
  antithesis: HYP-...
  shared_premises: [...]
  disputed_premises: [...]
  differential_predictions: [...]
  discriminating_tests: [...]
  parity_audit: {...}
  resolution_state: OPEN | SHIFTED | RESOLVED | INCONCLUSIVE
```

### 18.4 Counter-hypothesis generation

For every active hypothesis meeting the profile threshold, the engine must attempt to generate at least one materially different competitor (§17.7) unless a profile explicitly disables the rule. Failure outcomes:

```text
NO_VALID_COUNTERHYPOTHESIS
COUNTERHYPOTHESIS_DUPLICATE
INSUFFICIENT_EVIDENCE
BUDGET_EXHAUSTED
```

`NO_VALID_COUNTERHYPOTHESIS` is a result, not a silent skip.

### 18.5 Steelman parity (v2)

The antithesis MUST be evaluated under the same conditions as the thesis: the same evidence view, the same generation budget, the same scoring pathway, the same dependency-group accounting. `parity_audit` records budget spent per side, evidence views, scorer versions, and any asymmetry; a pair with material asymmetry is flagged `PARITY_VIOLATION` and its resolution cannot be `RESOLVED`.

### 18.6 Revision rules
Evidence may cause: support increase/decrease, status change, assumption change, prediction change, regime change, new hypothesis generation, old hypothesis supersession. The engine never mutates historical hypothesis evaluations.

---

## 19. Deductive consequence engine

### 19.1 Purpose
Given hypothesis `H`, derive consequences that should be observable if H is true under assumptions A.

### 19.2 Contract

```python
deduce_predictions(hypothesis, assumptions, rules) -> PredictionSet
```

```yaml
Prediction:
  prediction_id: PRD-...
  hypothesis_id: HYP-...
  statement: structured
  expected_observation: structured
  time_window: optional
  scope: optional
  discriminative_power: optional
  falsifiability: HIGH | MEDIUM | LOW | NONE
  derivation_trace: [...]
  status: PENDING | CONFIRMED | FALSIFIED | INDETERMINATE | EXPIRED | UNOBSERVABLE
```

`status` is a property of the prediction *as assessed at a revision* (append-only assessments).

### 19.3 `PredictionOutcome` (v2)

```yaml
PredictionOutcome:
  outcome_id: PRO-...
  prediction_id: PRD-...
  status: CONFIRMED | FALSIFIED | INDETERMINATE | EXPIRED | UNOBSERVABLE
  outcome_observation_refs: [...]
  coverage_absence_refs: [CQA-...]      # when the outcome is a qualified absence
  evaluated_at_revision: int
  effect_on_hypothesis: {support_delta, refutation_added, ...}
```

- `EXPIRED`: the time window closed without sufficient coverage to decide (not a falsification).
- `UNOBSERVABLE`: no registered capability can observe it (feeds `BLOCKED_CAPABILITY`).
- Outcomes feed hypothesis re-evaluation, realized information gain (§20.5) and calibration cohorts (§14.4).

### 19.4 Falsifiability rule
A hypothesis with no observable consequence may remain a descriptive label, but must not be treated as a testable explanatory model.

---

## 20. Discriminating evidence and information gain

### 20.1 `DiscriminatingTest`

```yaml
DiscriminatingTest:
  test_id: DGT-...
  context_id: CXI-...
  target_hypotheses: [...]
  space_ref: HSP-...
  question: structured
  expected_outcomes: [...]
  outcome_likelihoods: {...}
  gain:
    tier: IG_PROBABILISTIC | SURROGATE_SEPARATION | SURROGATE_CONTRADICTION_REDUCTION | SURROGATE_COVERAGE | UNKNOWN
    value: float | interval | UNKNOWN
    includes_residual_hypothesis: bool
  acquisition_cost: structured
  feasibility: {...}
  required_capabilities: [...]
  safety_policy: {...}
```

### 20.2 Information gain

Where a probabilistic model is valid (calibrated or declared model, exclusive group within an explicit `HypothesisSpace`):

```text
IG(T) = H(Hypotheses ∪ {H_other}) - E_o[H(Hypotheses ∪ {H_other} | outcome=o)]
```

Otherwise the engine uses a declared surrogate (hypothesis-separation score, expected contradiction reduction, coverage gain) and the `gain.tier` states which. Surrogates are never labelled information-theoretic.

### 20.3 Action ranking (v2: no hidden multiplicative formula)

The v1 multiplicative utility (`IG × feasibility × quality × discrimination / cost`) is **removed**: any zero factor annihilates it, cost can be zero, and it mixes incomparable units. Replacement rules:

1. **Hard gates are filters, not factors.** Policy status, capability availability, safety policy and feasibility `= 0` remove an action from the ready set (it appears as blocked with reason).
2. **Declared ranking mode** in the ReasoningProfile:
   - `LEXICOGRAPHIC` — ordered criteria with tolerance bands (e.g. discrimination, then gain tier-value, then expected quality, then cost);
   - `PARETO_THEN_TIEBREAK` — keep the non-dominated set (dominance as in §46.1), then a declared tie-break;
   - `WEIGHTED_ADDITIVE_NORMALIZED` — only over criteria normalized to a common declared scale, with the weight vector in the profile (no universal default weights).
3. **No cross-tier numeric comparison.** `IG_PROBABILISTIC` values are compared only with other `IG_PROBABILISTIC` values; surrogate tiers likewise. Tiers are combined by a profile-declared interleaving rule, never by comparing raw numbers.
4. **Exploration quota.** The profile reserves a declared fraction of selections for exploration (unexplored capability classes, under-covered source families), recorded as such.
5. **Cost floor.** Where cost appears as a divisor, a declared floor `ε > 0` applies; zero or unknown cost is reported as `UNKNOWN` cost, not zero.
6. Every factor, normalization and transformation is declared in the ReasoningProfile and echoed in the decision trace.

### 20.4 `ReasoningProfile` (v2)

```yaml
ReasoningProfile:
  profile_id: RPF-...
  version: string
  complexity_penalty: {function, parameters}
  unsupported_assumption_penalty: {...}
  contradiction_penalty: {...}
  material_difference: {facets, distance, tau}
  dominance_dimensions: [...]
  confirmation_threshold: {independent_groups_min, calibration_required, refutation_attempts_min}
  counterhypothesis_rule: {enabled, activation_threshold}
  residual_prior_mass: ...
  ranking_mode: LEXICOGRAPHIC | PARETO_THEN_TIEBREAK | WEIGHTED_ADDITIVE_NORMALIZED
  ranking_parameters: {...}
  tier_interleave: {...}
  exploration_quota: ...
  absence_thresholds: {min_coverage, min_detection_power}
  independence_rules: {...}
  saturation_criteria: {...}
  numeric_modes: {...}
  scientific_sufficiency: {phase_transition_signals_required, ...}
```

The profile is versioned, fingerprinted (`PF-…`), and referenced by every revision. Changing a profile is a `changed_policies` change set (Appendix J).

### 20.5 Expected vs realized gain
Expected gain is stored at proposal time; realized gain is computed after outcomes (change in entropy/separation within the same space, or surrogate equivalent) and stored with the same tier label. Both are exposed (FR-025-043/044).---
## 21. Context frontier

The context frontier is not a URL queue. It is the set of unresolved epistemic demands connected to executable acquisition/research capabilities.

```text
ContextFrontierItem
    = ResearchObligation
    + readiness
    + missing evidence
    + discriminating value
    + available capabilities
    + budget
    + policy
    + action memory
```

### 21.1 State vocabularies (v2: one normative separation)

The v1 text had two overlapping lists (frontier readiness and obligation lifecycle). They are now orthogonal fields, to be reconciled verbatim with 024 in Wave 0 (024 wins on names):

```text
Obligation.lifecycle  : OPEN | SATISFIED | UNSATISFIABLE | ABANDONED | SUPERSEDED
Obligation.readiness  : BLOCKED_SCOPE | BLOCKED_POLICY | BLOCKED_CAPABILITY | READY      (only while OPEN)
Action.state          : PROPOSED | AWAITING_APPROVAL | APPROVED | REJECTED | RUNNING | OBSERVING | EVALUATING | COMPLETED | FAILED | CANCELLED
Saturation.verdict    : UNSATURATED | SATURATED | BLOCKED | UNKNOWN        (descriptive; never itself closes anything)
```

### 21.2 Frontier priority tuple

```text
priority = {
  urgency, information_gain (with tier), discrimination, expected_quality,
  novelty, cost, latency, redundancy_penalty, policy_penalty
}
```

Components are exposed, never an opaque scalar. A final ordering is produced under the ranking mode of §20.3.

---

## 22. Saturation and termination

### 22.1 Saturation is not "we searched a lot"
Saturation incorporates: distinct sources (as `n_eff`, §14A), source-family diversity, coverage, marginal gain, contradiction status, remaining unexplored capability classes, budget, time horizon, known blind spots.

### 22.2 `SaturationState`

```yaml
SaturationState:
  saturation_id: SAT-...
  obligation_id: OBL-...
  coverage: value | interval | UNKNOWN
  distinct_sources: int
  effective_independent_sources: value
  source_families: int
  marginal_gain: value | interval | UNKNOWN
  unexplored_capability_classes: [...]
  contradiction_count: int
  unresolved_obstruction_count: int
  qualified_absences: [CQA-...]
  budget_remaining: {...}
  verdict: UNSATURATED | SATURATED | BLOCKED | UNKNOWN
  reason_codes: [...]
```

### 22.3 Closure rule
An obligation may be marked `SATISFIED` only when its declared satisfaction criteria evaluate true. A source being exhausted is not satisfaction. Low marginal gain is not satisfaction. The closure report states why the obligation terminated. A temporary source failure never moves an obligation to `SATISFIED`.

---

## 23. Contradiction engine

### 23.1 `Contradiction`

```yaml
Contradiction:
  contradiction_id: CTR-...
  context_id: CXI-...
  subject_ref: optional
  statement_a_ref: ...
  statement_b_ref: ...
  contradiction_kind: LOGICAL | TEMPORAL | NUMERIC | IDENTITY | STRUCTURAL | SEMANTIC | SOURCE | CAUSAL | MODEL
  severity: LOW | MEDIUM | HIGH | CRITICAL
  independence_assessment: {groups_a, groups_b, n_eff_a, n_eff_b, basis}
  supporting_evidence_a: [...]
  supporting_evidence_b: [...]
  resolution_state: DETECTED | OPEN | EXPLAINED | RESOLVED | PERSISTENT
  explanation_ref: optional
  generated_obligations: [...]
```

(`UNKNOWN` is removed from `resolution_state`; unknown independence lives in `independence_assessment`.)

### 23.2 Independence
Uses the shared model of §14A: the same press release copied by 500 sites is one dependency group, not 500 observations.

### 23.3 Lifecycle (normative)

```text
DETECTED   → OPEN
OPEN       → EXPLAINED | PERSISTENT
EXPLAINED  → RESOLVED | OPEN (explanation invalidated by new evidence)
PERSISTENT → EXPLAINED | RESOLVED (new evidence) | PERSISTENT (renewed, no change)
RESOLVED   → OPEN (reopen on new contradicting evidence; recorded as new revision)
```

A contradiction can remain `PERSISTENT` indefinitely if evidence genuinely supports both sides.

---

## 24. Temporal reasoning

### 24.1 Fixed time axes
The existing six axes remain authoritative: `fetched_at`, `observed_at`, `published_at`, `valid_from`, `valid_to`, `known_from`. The engine may add derived temporal relations but must not create a seventh authoritative axis. Every temporal relation names the axis (or axis pair) it was computed on.

### 24.2 Interval relation algebra (v2: full Allen)

The 13 basic relations:

```text
BEFORE      AFTER
MEETS       MET_BY
OVERLAPS    OVERLAPPED_BY
STARTS      STARTED_BY
DURING      CONTAINS
FINISHES    FINISHED_BY
EQUAL
```

A temporal relation value is a **non-empty subset of the 13** (a disjunctive relation). The full set is `UNKNOWN`; a singleton is a definite relation. Operations (all deterministic, table-driven): `converse`, `intersection` (constraint tightening), `composition` (Allen's composition table; used for path-consistency over bounded temporal networks). Empty intersection ⇒ `INCOMPATIBLE` on the temporal dimension.

When interval endpoints are themselves uncertain (precision, §24.5), the relation is the set of basic relations consistent with *all* admissible endpoint values. Point events are degenerate intervals.

### 24.3 Temporal evidence
Every temporal relation can be: `OBSERVED`, `DECLARED`, `DERIVED`, `INFERRED`, `UNKNOWN`.

### 24.4 Out-of-order data
Late events must not mutate past revisions. Instead:

```text
late event
  ↓
recompute affected dependency subgraph
  ↓
new revision
  ↓
record supersession
```

### 24.5 Temporal precision
`EXACT`, `DAY`, `WEEK`, `MONTH`, `YEAR`, `INTERVAL`, `ORDER_ONLY`, `UNKNOWN`.

---

## 25. Dynamics and regime detection

### 25.1 `Regime`

```yaml
Regime:
  regime_id: REG-...
  context_id: CXI-...
  start: timestamp
  end: timestamp | open
  descriptor_features: [...]
  stability_measures: [...]
  confidence: optional
  model_ref: MOD-...
```

### 25.2 `TransitionWindow`

```yaml
TransitionWindow:
  transition_id: TRN-...
  context_id: CXI-...
  from_regime: REG-...
  to_regime: REG-... | UNKNOWN
  interval: {...}
  change_points: [...]
  order_parameters: [...]
  structural_delta: {...}
  candidate_causes: [...]
  evidence_refs: [...]
```

### 25.3 Change-point discipline
A change point is evidence of a statistical/structural distribution change under a method. It is not automatically intent, cause, actor responsibility or a phase transition. Separate claim levels:

```text
CHANGE_POINT_DETECTED
REGIME_CHANGE_SUPPORTED
REGIME_SHIFT_CANDIDATE
CAUSAL_EXPLANATION
```

(v2: `PHASE_TRANSITION_CANDIDATE` is renamed `REGIME_SHIFT_CANDIDATE`. The physics term "phase transition" implies order parameters and criticality that the available signals rarely establish. A profile MAY enable the label `PHASE_TRANSITION_CANDIDATE` only when its scientific profile declares the required evidence.)

### 25.4 Regime-shift candidate
A candidate requires multiple signals where possible: order parameter shift, structural change, persistence change, variance/entropy change, connectivity change, state transition evidence. No single metric is sufficient unless the active scientific profile explicitly declares it sufficient.

---

## 26. TDA layer

### 26.1 Role
TDA is a structural diagnostic instrument: connected components, persistent features, structural holes, topological persistence changes, multi-scale structural anomalies.

### 26.2 Input contract

```text
WorldlineSnapshot → GraphSnapshot / multiplex layer → windowed adjacency / simplicial representation → TDA operator
```

### 26.3 Output

```yaml
TopologicalFeature:
  feature_id: TDA-...
  snapshot_ref: WLS-...
  window: {...}
  feature_kind: H0 | H1 | H2 | CUSTOM
  persistence_summary: {...}
  statistics: {...}
  numeric_mode: FLOAT_QUANTIZED
  seed: optional
  method_fingerprint: MF-...
```

### 26.4 Strict boundary
TDA MUST NOT directly emit entity identity, intent, truth, causality or attribution. It may generate an `AnomalyObservation` or `ResearchObligation`.

---

## 27. Causal reasoning

### 27.1 `CausalModel`

```yaml
CausalModel:
  model_id: CAU-...
  variables: [...]
  edges: [...]
  observed_variables: [...]
  latent_variables: [...]
  confounders: [...]
  interventions: [...]
  assumptions: [...]
  identification_strategy: ...
  estimation_strategy: ...
  refutation_tests: [...]
```

### 27.2 Mandatory stages
`IDENTIFICATION`, `ESTIMATION`, `REFUTATION`. No single "causal confidence" field may conceal which stage failed.

### 27.3 Identification failure
The correct result is `NOT_IDENTIFIED`, not `causal_effect = 0`.

### 27.4 Refutation
Support at least conceptually: placebo test, unobserved-confounder sensitivity, alternative specification, temporal falsification, negative-control style test (when applicable). Exact methods are versioned operator/plugin concerns.

---

## 28. Strategic / system analysis

### 28.1 `StrategicSystem`

```yaml
StrategicSystem:
  system_id: SYS-...
  context_id: CXI-...
  actors: [...]
  resources: [...]
  constraints: [...]
  dependencies: [...]
  objectives: [...]
  actions: [...]
  response_channels: [...]
  state_variables: [...]
  coupling_links: [...]
```

### 28.2 Actor representation
Actors are model objects tied to existing resolved entities where appropriate; strategic hypotheses MUST distinguish observed action, attributed action, inferred objective, hypothesized capability.

### 28.3 Strategic hypothesis
actor configuration, objective hypothesis, constraint set, available moves, observed moves, expected response, counter-response. Strategic interpretation is labelled hypothesis unless directly evidenced.

### 28.4 Counterfactuals
Valid only under an explicit model and only on a COUNTERFACTUAL/WHAT_IF branch (§6.4). Required fields: baseline state, intervention, assumptions, transition model, estimated outcome, uncertainty, violated assumptions.

---

## 29. Semantic architecture

### 29.1 Open-world principle
The world model remains open. An observed relation may have a known, mapped, unknown, or ambiguous relation type.

### 29.2 Closed-operation principle
Specific operators MAY define a closed vocabulary for their own task (e.g. a supply-chain concentration operator requiring `SUPPLIER_OF`, `CUSTOMER_OF`, `OWNED_BY`, `CONTROLLED_BY`) while the global world model still contains unknown or domain-specific relations.

### 29.3 Semantic incompleteness
Semantic uncertainty must not reduce structural observability. `LINK(signal)` with participants `[document A, document B]` and `relation_type = UNKNOWN` remains valid information.---
## 30. Reasoning Operator framework

### 30.1 Contract

```python
class ReasoningOperator(Protocol):
    id: str
    version: str
    operator_class: str
    input_contract: ContractRef
    output_contract: ContractRef
    determinism: str            # EXACT | FIXED_POINT | FLOAT_QUANTIZED | NON_DETERMINISTIC(reason)
    numeric_mode: str
    complexity: ComplexityModel

    def validate_input(self, input_view) -> ValidationResult: ...
    def run(self, input_view, parameters, seed) -> OperatorResult: ...
    def explain(self, result) -> ExplanationTrace: ...
```

### 30.2 Operator metadata

```yaml
Operator:
  id, version, class, input_contract, output_contract, parameter_schema,
  dependency_fingerprint, determinism_mode, numeric_mode, complexity_class, memory_class,
  supports_incremental, supports_replay, provenance_contract, license,
  isolation_requirements, safety_policy, cache_policy
```

### 30.3 Operator classes

```text
NORMALIZATION  COMPATIBILITY  GLUING  STATE_ESTIMATION  ABDUCTION  DEDUCTION
DIALECTICS  BAYESIAN_UPDATE  ARGUMENTATION  TEMPORAL  CHANGE_POINT  REGIME
TDA  CAUSAL  GRAPH_ANALYSIS  INFORMATION_GAIN  SATURATION  CALIBRATION
ANOMALY  SCENARIO  INDEPENDENCE
```

(`INDEPENDENCE` added in v2 for §14A.)

### 30.4 Donor integration

```text
Donor implementation → Adapter → ReasoningOperator contract → Operator Registry → Planner selection → Sandboxed runtime
```

Donors are implementation sources, not domain authorities.

### 30.5 Caching (v2)
Memoized operator results are keyed by `(tenant_id, context_id, branch_id, operator_id, operator_version, input_digest, parameter_fingerprint, seed, policy_fingerprint)`. A cache key without `tenant_id` is forbidden; cache reads follow the same tenant fail-closed rule as storage (§40).

---

## 31. Execution tiers

- **Tier 0 — deterministic cheap path:** rules, normalization, indexes, blocking, temporal relations, structural signatures, exact graph queries, basic contradictions, interval constraint propagation.
- **Tier 1 — symbolic:** Prolog/Datalog-style rules, constraint solving, graph pattern reasoning, abduction over finite rule sets, argumentation.
- **Tier 2 — statistical/scientific:** Bayesian models, change points, TDA, causal estimation, calibration, null-model evaluation.
- **Tier 3 — adaptive/neural:** LLM interpretation, semantic candidate generation, hypothesis proposal, natural-language query compilation.

Tier 3 must never be required for correctness of the deterministic core.

---

## 32. Query compiler

### 32.1 User request model
A natural-language query compiles into: `QueryIntent`, `Scope`, `TargetPredicate`, `Constraints`, `RequiredEvidence`, `Aggregation`, `TemporalScope`, `SemanticRegime`, `StoppingPolicy`, `OutputProjection`.

### 32.2 Example

Input: `Найди всех крипто-китов с совокупным состоянием от $1M.`

```yaml
QueryIntent:
  objective: IDENTIFY_COHORT
  target:
    subject_class: wallet_control_cluster
    property: aggregate_asset_value
  constraints:
    aggregate_asset_value: {op: ">=", value: 1000000, currency: USD}
  temporal_scope: {mode: CURRENT | AS_OF | INTERVAL}
  identity_requirement: {mode: CONTROL_CLUSTER, allow_unresolved: true}
  evidence_requirement: {balance_sources_min: 1, attribution_sources_min: 0}
  saturation: {enabled: true}
```

The compiler must preserve unresolved cases rather than silently dropping them.

### 32.3 Execution pipeline

```text
parse → normalize → bind semantic profile → check inference policy (§49.3) → construct context
→ generate obligations → generate frontier → select capabilities → acquire → observe
→ interpret → resolve → aggregate → validate → rank
→ return result + uncertainty + coverage + blind spots
```

---

## 33. Global-search semantics

The phrase "find all" has to become machine-readable.

### 33.1 Universal search claim
The platform MUST NOT claim literal global completeness unless the source universe and coverage model make that defensible. It returns:

```text
observed_set, candidate_set, resolved_set, unresolved_set, excluded_set,
coverage_estimate, source_universe, saturation_state, known_blind_spots,
qualified_absences
```

### 33.2 Three completeness modes

```text
EXACT_ENUMERATION          universe explicitly enumerable and completely scanned
KNOWN_UNIVERSE_ENUMERATION all registered sources in the current catalogue exhausted under declared policy
OPEN_WORLD_DISCOVERY       available sources searched; universe completeness cannot be established
```

The UI must display which mode applies.

---

## 34. Research planning from hypotheses

Each open hypothesis may generate: missing evidence, prediction checks, discriminating tests, counter-hypothesis search, source expansion, temporal backfill, entity-resolution task, semantic mapping task, coverage extension (to upgrade an `INFORMATIONAL_ONLY` absence).

### 34.1 Obligation generation rule

```python
generate_obligations(
    context_revision, hypotheses, contradictions, obstructions,
    saturation, capability_catalogue,
) -> list[ResearchObligation]
```

Every generated obligation records: trigger_event, trigger_rule, reason, parent hypothesis/contradiction/obstruction, required evidence, candidate capabilities, priority components.

---

## 35. Incremental engine

### 35.1 ChangeSet

```yaml
ChangeSet:
  batch_ref: ...
  event_refs: [...]
  added_observations: [...]
  removed_refs: []             # removed from derived input views only
  changed_entities: [...]
  changed_relations: [...]
  changed_temporal_windows: [...]
  changed_semantics: [...]
  changed_policies: [...]
  analyst_decisions: [...]
```

Raw observations are never removed from the world.

### 35.2 Dependency graph
Every derived artifact records its dependencies (observations, relations, models, policies, seeds). A changed input invalidates only reachable dependents.

### 35.3 Invalidation classes
`LOCAL_RECOMPUTE`, `WINDOW_RECOMPUTE`, `CELL_RECOMPUTE`, `HYPOTHESIS_REEVALUATION`, `FULL_CONTEXT_REPLAY`. Policy determines the minimum safe recomputation scope.

---

## 36. Deterministic replay

### 36.1 Required replay identity

```text
input event ids
ordered canonical event sequence with recorded batch boundaries
rule-set versions
operator versions
parameter fingerprint (incl. seeds, numeric modes)
semantic regime version
policy fingerprint
```

### 36.2 Replay requirement

```text
run(E, R, M, P, seeds) → state S ; record event log L
replay(L, R, M, P) → S'  ;  replay(L, R, M, P) → S''
Required: S = S' = S'' at every declared artifact boundary, per determinism class (§4.1)
```

### 36.3 Replay after erasure
If payloads were erased under retention policy (§39.3), replay reports `REPLAY_DEGRADED` with the list of unreadable inputs; digests of erased inputs remain, so integrity of everything else is still checkable.

---

## 37. Provenance model

Three lineage dimensions are mandatory and independently queryable.

```text
EVIDENCE:   Claim → Assertion → Mention → Segment → Observation → Capture → Source → Raw bytes
DERIVATION: Claim → Material → Candidate → Hypothesis → RelationSignal → Mention → Observation
RESEARCH:   Context → Obligation → Action → Task → Result → ContextRevision
```

Evidence lineage also feeds the dependency-group derivation of §14A.

---

## 38. Decision trace

```yaml
DecisionTrace:
  decision_id: DEC-...
  input_refs: [...]
  prior_state_ref: ...
  rule_id: ...
  rule_version: ...
  operator_id: ...
  operator_version: ...
  parameters_fingerprint: ...
  policy_fingerprint: ...
  seed: optional
  principal: optional          # for analyst decisions
  output_refs: [...]
  omitted_candidates: [...]
  truncation_reason: optional
```

The analyst must be able to ask "Почему движок решил сделать именно это?" and receive a structured answer, not a log dump.

---

## 39. Storage model

PostgreSQL remains authoritative for durable context/research state.

Minimum tables/entities:

```text
investigation_context, context_branch, context_revision, revision_manifest, artifact_store,
context_cell, context_overlap, restriction_map, compatibility_assessment, gluing_result,
state_variable, state_estimate, observation_model,
hypothesis_space, hypothesis, hypothesis_revision, assumption, dialectical_pair,
prediction, prediction_outcome, discriminating_test,
contradiction, obstruction, evidence_dependency_group, coverage_absence,
regime, transition_window, topological_feature, causal_model, causal_evaluation,
saturation_state, research_obligation, research_action, action_memory,
analyst_assertion, context_decision, reasoning_run, replay_report,
reasoning_profile, retention_policy, inference_policy,
operator_registry_snapshot, method_fingerprint
```

### 39.1 Append-only rule
Historical analytical records are append-only. State queries use the latest committed revision of a branch; historical queries use explicit revision identifiers.

### 39.2 JSONB rule
JSONB may be used for extensible operator-specific payloads. Fields participating in identity, joins, indexes, security constraints, temporal queries or tenant isolation must be first-class columns or indexed generated fields.

### 39.3 Retention, legal hold and erasure (v2)

Append-only is a *logical* property. Legal and privacy obligations require a physical-erasure path that does not break integrity:

```yaml
RetentionPolicy:
  policy_id: RET-...
  data_classes: {...}
  retention_periods: {...}
  legal_hold: bool/scope
  erasure_method: CRYPTO_SHRED | TOMBSTONE
```

- Payloads of sensitive classes are stored encrypted under per-subject / per-class keys; erasure deletes the key (**crypto-shredding**) and leaves a tombstone: id, digest, class, erasure decision ref, timestamp.
- Revisions, manifests and digests remain; derived artifacts that depended on erased inputs are marked `INPUT_ERASED` and flagged for recomputation on a new revision (never in-place mutation).
- Legal hold blocks erasure and expiry for the held scope; holds are themselves auditable decisions.
- Retention applies identically to branches and caches.

### 39.4 Content-addressed artifacts and revision manifests (v2)
Derived artifacts (cells, overlaps, assessments, hypotheses revisions, etc.) are stored content-addressed by their canonical digest. A `ContextRevision` stores a manifest of artifact digests; unchanged artifacts are shared with the parent revision. Garbage collection only removes artifacts unreachable from any non-expired revision and not under hold.

---

## 40. Index design requirements

Mandatory logical access patterns:

```text
(context_id, branch_id, revision)
(context_id, status)
(context_id, obligation_lifecycle, readiness)
(context_id, hypothesis_status)
(context_id, space_id)
(context_id, contradiction_state)
(context_id, temporal_start, temporal_end)
(context_id, entity_ref)
(context_id, source_ref)
(context_id, dependency_group)
(context_id, method_fingerprint)
(context_id, state_hash)
```

Every tenant-scoped table has tenant-aware indexes. Cross-tenant reads must fail closed (including cache reads — §30.5).

---

## 41. API contracts

### 41.1 Context state
```http
GET /api/v1/investigations/{investigation_id}/context
GET /api/v1/investigations/{investigation_id}/context/revisions
GET /api/v1/investigations/{investigation_id}/context/revisions/{revision}
GET /api/v1/context/{context_id}/branches
```
All revision/state endpoints accept `branch` (default: mainline).

### 41.2 Hypotheses
```http
GET /api/v1/context/{context_id}/hypothesis-spaces
GET /api/v1/context/{context_id}/hypotheses
GET /api/v1/context/{context_id}/hypotheses/{hypothesis_id}
GET /api/v1/context/{context_id}/dialectics
GET /api/v1/context/{context_id}/predictions
```

### 41.3 Contradictions
```http
GET /api/v1/context/{context_id}/contradictions
GET /api/v1/context/{context_id}/contradictions/{contradiction_id}
```

### 41.4 Dynamics
```http
GET /api/v1/context/{context_id}/state
GET /api/v1/context/{context_id}/regimes
GET /api/v1/context/{context_id}/transitions
GET /api/v1/context/{context_id}/topology
```

### 41.5 Frontier and analyst decisions
```http
GET  /api/v1/context/{context_id}/frontier
GET  /api/v1/context/{context_id}/obligations
GET  /api/v1/context/{context_id}/actions
POST /api/v1/context/{context_id}/actions/{action_id}/approve
POST /api/v1/context/{context_id}/actions/{action_id}/reject
POST /api/v1/context/{context_id}/analyst/assertions
POST /api/v1/context/{context_id}/analyst/decisions
```

`POST` endpoints create decisions/tasks through existing control-plane boundaries; they do not directly call acquisition runtimes and never edit evidence.

---

## 42. Query response contract

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
  provenance:
    evidence_lineage: ...
    derivation_lineage: ...
    research_lineage: ...
  method_fingerprint: MF-...
```

The API must never return a confident-looking flat array without its epistemic context for queries where incompleteness is materially relevant.

---

## 43. Event model

```text
CONTEXT_CREATED
CONTEXT_BRANCH_CREATED
CONTEXT_REVISION_PROPOSED
CONTEXT_REVISION_COMMITTED
CONTEXT_CELL_CREATED
CONTEXT_OVERLAP_ASSESSED
GLUING_COMPLETED
STATE_ESTIMATE_CREATED
HYPOTHESIS_SPACE_UPDATED
HYPOTHESIS_CREATED
HYPOTHESIS_REEVALUATED
DIALECTIC_UPDATED
PREDICTION_CREATED
PREDICTION_OUTCOME_RECORDED
CONTRADICTION_DETECTED
OBSTRUCTION_CREATED
COVERAGE_ABSENCE_RECORDED
REGIME_DETECTED
TRANSITION_DETECTED
TDA_FEATURE_CREATED
CAUSAL_EVALUATION_COMPLETED
DISCRIMINATING_TEST_CREATED
RESEARCH_OBLIGATION_CREATED
RESEARCH_ACTION_PROPOSED
RESEARCH_ACTION_APPROVED
RESEARCH_ACTION_REJECTED
ANALYST_ASSERTION_RECORDED
ANALYST_DECISION_RECORDED
SATURATION_UPDATED
CONTEXT_REOPENED
REPLAY_COMPLETED
```

Each event uses the existing event envelope contract and typed payload time convention.

---

## 44. Failure and uncertainty taxonomy

Every operator result distinguishes:

```text
SUCCESS  PARTIAL  UNKNOWN  INSUFFICIENT_EVIDENCE  INCOMPATIBLE  CONFLICTING
UNRESOLVED  BUDGET_EXHAUSTED  TIMEOUT  DEPENDENCY_UNAVAILABLE  POLICY_BLOCKED
INVALID_INPUT  NOT_IDENTIFIED  PARITY_VIOLATION
```

The engine must not convert all failures to `UNKNOWN`.

---

## 45. Resource model

### 45.1 Resource budget

```yaml
ComputeBudget:
  max_wall_time_ms, max_cpu_ms, max_memory_mb, max_candidates, max_hypotheses,
  max_graph_nodes, max_graph_edges, max_triples, max_bucket_size,
  max_source_actions, max_parallelism, max_reasoning_depth
```

### 45.2 Budget exhaustion
The engine returns partial results plus: what was processed, what was not, which frontier was truncated, which hypotheses were pruned, why pruning was allowed. Silent truncation is forbidden.

---

## 46. Complexity controls

Mandatory: hard blocking before expensive pair scoring, bounded neighbourhoods, beam limits, hypothesis dominance pruning, memoized operator results (tenant-keyed), incremental recomputation, lazy model loading, query result streaming, source-level fanout limits.

### 46.1 Dominance rule
A candidate may be pruned only if another candidate is no worse on all declared dimensions, strictly better on at least one, and the profile declares those dimensions sufficient. The discarded candidate and the dominance reason remain auditable. Dominance is never evaluated across score kinds (§20.3).

---

## 47. 20 GB developer profile

The target development environment includes a 20 GB RAM ultrabook. The engine therefore requires a CPU-first profile.

### 47.1 Mandatory profile behaviour

```text
LLM disabled by default
models loaded lazily
memory-mapped large assets
streaming ingestion
bounded in-memory graph views
PostgreSQL (local/embedded or container) even in the lightweight profile
optional Neo4j only for serving/projection tests
symbolic operators preferred over neural equivalents
```

SQLite is **not** used for persistence tests (v2): append-only guards, row-level security, generated columns and JSONB indexing behave differently and would hide defects until late. SQLite may be used only for pure unit tests that touch no persistence semantics.

### 47.2 Memory classes

```text
TINY  < 64 MB     SMALL 64–256 MB    MEDIUM 256 MB–1 GB    LARGE 1–4 GB    XL > 4 GB
```

Every operator declares a memory class. Peak process memory for dev-lite must stay within the target in §47.4.

### 47.3 LLM policy
Natural-language query parsing may use a local quantized model, but the same query must have a deterministic parser path for supported structured grammar. The LLM must not own entity identity, claim admission, contradiction resolution or truth state.

### 47.4 Initial quantitative targets (v2)

These are **proposed defaults to be ratified in Wave 0** and stored in the deployment/profile config; they exist so that "bounded" and "no silent truncation" are testable.

| Metric | dev-lite target | dev-full target |
|---|---|---|
| p95 tick latency, batch ≤ 100 observations, ≤ 500 cells | ≤ 2 s | ≤ 2 s |
| p95 tick latency, batch ≤ 1 000 observations | ≤ 15 s | ≤ 10 s |
| `max_bucket_size` (cells per blocking key) | 500 | 2 000 |
| `max_triples` per gluing run | 20 000 | 200 000 |
| Peak resident memory for the reasoning process | ≤ 8 GB | ≤ 16 GB |
| Replay of 10 000-event log | ≤ 5 min | ≤ 5 min |
| Golden corpus size (cases) | ≥ 30 by Wave 3 | ≥ 100 at acceptance |

Missing a target is a recorded finding (benchmark Appendix M), not a silent change to the target.---
## 48. Adaptive layer

### 48.1 Deterministic mode
Adaptive models OFF, neural proposals OFF; same inputs → same outputs. This is the constitutional acceptance mode.

### 48.2 Adaptive mode
Adaptive models may suggest semantic mappings, suggest candidate hypotheses, rank source opportunities, propose missing variables, compile free-form questions. Every suggestion enters as a `PROPOSAL` and passes the same admission/validation boundaries as any other interpretation.

### 48.3 Neural provenance
Every neural proposal retains: model id, model version, prompt/template fingerprint, input references, generation parameters (including seed/temperature), timestamp, output digest. Because LLM output is not reproducible, replay uses the **recorded proposal** (by digest), never regeneration.

---

## 49. Security, safety and permissible inference

This engine is an intelligence reasoning substrate, not an unconstrained external-action engine.

### 49.1 Separation

```text
Reasoning → ResearchAction → Approval / Policy → Existing Task/Capability boundary → Controlled execution → Observation
```

### 49.2 External operations
The Context Engine cannot directly send arbitrary messages, modify third-party accounts, perform destructive actions, bypass access controls, execute arbitrary payloads, or run unbounded internet automation. It can propose research actions routed through the platform governance boundary.

### 49.3 Inference policy (v2)
Outbound controls are not enough: *what the engine may conclude* also needs policy. `InferencePolicy` declares:

```yaml
InferencePolicy:
  sensitive_inference_classes:
    - ATTRIBUTION_OF_CONTROL_TO_NATURAL_PERSON
    - LINKING_PSEUDONYMOUS_IDENTITIES
    - INFERRING_PROTECTED_ATTRIBUTES
    - BEHAVIOURAL_PROFILING_OF_INDIVIDUALS
  purpose_limitation: allowed objectives per context
  required_controls: [APPROVAL, MINIMUM_EVIDENCE_THRESHOLD, REVIEW_LABEL, RESTRICTED_VISIBILITY]
  disclosure: how such results are labelled and who may see them
```

- The query compiler (§32.3) and the abduction/dialectics generators check the policy before generating hypotheses in a sensitive class; blocked cases return `POLICY_BLOCKED`.
- Permitted sensitive hypotheses are always labelled as hypotheses with their evidence and false-positive caveats; they cannot be rendered as findings.
- Appendix C (wallet-cluster attribution) is subject to this policy.

---

## 50. UI — Context Workspace

The UI is an inspection surface for the reasoning state, not the state machine itself.

### 50.1 Main sections
`OVERVIEW`, `WORLD`, `CONTEXT`, `HYPOTHESES`, `CONTRADICTIONS`, `DYNAMICS`, `EVIDENCE`, `FRONTIER`, `PROVENANCE`, `EXPERIMENTS`, `BRANCHES`.

### 50.2 Context header
Must show: context identity, branch and revision, scope, time range, semantic regime, current state, coverage, saturation, open obligations, contradictions, last revision reason, completeness mode.

### 50.3 Hypothesis matrix
Rows: hypotheses (including `H_OTHER` and its mass). Columns: truth state, score (kind + target + calibration), support, refutation, `n_eff`, assumptions, predictions and their outcomes, contradictions, information gaps, expected discrimination.

### 50.4 Context map
Visualizes local cells, overlaps, triple inconsistencies and obstructions.

### 50.5 Dynamics view
Overlay: state variables, worldline events, regimes, change points, transitions, TDA features. No chart may imply causality solely by visual ordering.

---

## 51. Explainability UI

For every hypothesis: WHY ALIVE? WHAT SUPPORTS IT? WHAT CONTRADICTS IT? WHAT ASSUMPTIONS DOES IT NEED? WHAT WOULD FALSIFY IT? WHAT OTHER HYPOTHESES COMPETE (and how much mass remains unassigned)? WHAT SHOULD WE CHECK NEXT?

For every research action: WHY THIS ACTION? WHICH HYPOTHESES DOES IT DISTINGUISH? EXPECTED GAIN (with tier)? COST? SOURCE QUALITY? POLICY STATUS? WAS IT AN EXPLORATION PICK?

Analyst overrides are shown beside model-derived status, never instead of it.

---

## 52. Scientific benchmark suite

- **52.1 Determinism:** repeated runs on identical fixtures produce equal hashes (per class, §4.1) for context revision, hypothesis revision, compatibility assessment, gluing result, state estimate, contradiction, frontier ranking; cross-platform run for `EXACT`/`FIXED_POINT`/quantized artifacts.
- **52.2 Abduction:** single explanation, multiple explanations, weak evidence, contradictory evidence, minimal-explanation tie, near-duplicate hypotheses, missing evidence, non-exhaustive space (`H_OTHER` carries mass).
- **52.3 Dialectical:** strong thesis / weak counter, strong thesis / strong counter, false thesis, unresolvable competition, parity violation.
- **52.4 Temporal:** late event, out-of-order event, interval uncertainty (disjunctive Allen relations), publication ≠ observation, validity interval, regime transition.
- **52.5 Causal:** identifiable effect, non-identifiable effect, known confounder, unobserved-confounder sensitivity, refutation failure.
- **52.6 Locality (v2):** pairwise-compatible but triple-inconsistent cells; bucket overflow; unchecked-triple reporting.
- **52.7 Evidence independence (v2):** syndicated copies, translated copies, shared extraction method; `n_eff` below raw count; posterior does not inflate.
- **52.8 Absence (v2):** covered search → admissible negative; unknown detection power → informational only; not searched → no contribution.

---

## 53. Golden corpus

Each case stores:

```yaml
case_id: ...
input_events: [...]           # with recorded batch boundaries and seeds
context_definition: {...}
expected_cells: [...]
expected_compatibility: [...]
expected_obstructions: [...]
expected_hypothesis_space: {...}
expected_hypotheses: [...]
expected_truth_states: [...]
expected_dependency_groups: [...]
expected_contradictions: [...]
expected_predictions: [...]
expected_prediction_outcomes: [...]
expected_absences: [...]
expected_frontier: [...]
expected_saturation: {...}
expected_query_result_shape: {...}
```

The corpus tests intermediate outputs, not only the final answer. **Corpus construction starts in Wave 1** (see §55) and grows with every phase; it is not a final-phase activity.

---

## 54. Acceptance criteria

- **A — Context.** Survives restart; revisions append-only; revision replay deterministic; scope and semantic regime explicit; single sequencer + optimistic concurrency hold under concurrent writers.
- **B — Locality.** Cells independently inspectable; overlap generation bounded; restriction never fabricates evidence; triple coherence checked and truncation reported; obstructions persisted.
- **C — Hypothesis.** Competing hypotheses coexist inside explicit spaces; `H_OTHER` present when non-exhaustive; history immutable; support/refutation queryable; missing evidence explicit; lifecycle transitions follow §15.4.
- **D — Abduction.** Returns hypotheses plus explanations; truncation explicit; complexity declared; near-duplicates controlled by the material-difference test.
- **E — Dialectics.** Active hypotheses produce counter-hypotheses; differential predictions explicit; steelman parity audited; inconclusive competition stays inconclusive.
- **F — Dynamics.** Regimes and change points distinct; regime-shift candidates not automatically causal; late data causes new revisions.
- **G — TDA.** Uses durable worldline snapshots; structural features only; never changes identity or truth state.
- **H — Causal.** Identification/estimation/refutation separate; assumptions persisted; non-identifiability represented honestly.
- **I — Research loop.** Contradictions create/update obligations; information gaps become actions; actions route through governance; closure reports explain why investigation stopped; prediction outcomes feed hypotheses and calibration.
- **J — Completeness.** Every global-search result declares completeness mode, coverage, saturation, blind spots, unknown/unresolved population, qualified absences.
- **K — Provenance.** Every derived result traceable through all applicable lineage dimensions.
- **L — Determinism.** With adaptive layer disabled: same inputs + versions + parameters + seeds = same outputs per §4.1.
- **M — Resource limits.** A run cannot exceed declared memory, CPU, wall time, candidate count, hypothesis count, parallelism without an explicit budget-exhaustion state; §47.4 targets measured.
- **N — Epistemic algebra (v2).** Truth-state operations satisfy the lattice laws; `BOTH` always has a Contradiction; scores always carry target and kind; no cross-kind ranking.
- **O — Independence and absence (v2).** Aggregations consume dependency groups; absences are admissible only with declared coverage and detection power.
- **P — Branches and analyst (v2).** Branch output never reaches mainline; analyst decisions are traced and visible beside model-derived state.
- **Q — Retention and inference policy (v2).** Erasure via crypto-shredding preserves integrity and yields `REPLAY_DEGRADED`; sensitive-inference classes are gated by policy; caches are tenant-keyed.

---
## 55. Implementation decomposition (v2: vertical slice first)

v1 ran waterfall A→N with benchmarks and UI last, which postpones the largest risks. v2 inserts an early end-to-end slice and starts the golden corpus in Wave 1.

### Wave 0 — Contract freeze
Freeze vocabulary and boundaries. Deliverables (ADRs):

```text
ADR-025-01 Context Engine placement
ADR-025-02 Epistemic algebra (Belnap operations, truth vs score)
ADR-025-03 Revision/replay contract (determinism classes, sequencer, batches, manifests)
ADR-025-04 Sheaf-inspired locality boundary (pair + triple coherence, honest terminology)
ADR-025-05 Hypothesis lifecycle and hypothesis space (H_OTHER, trend vs status)
ADR-025-06 Reasoning operator contract (numeric modes, seeds, cache keys)
ADR-025-07 Global search completeness semantics
ADR-025-08 Temporal algebra (13 Allen relations, disjunctive sets)
ADR-025-09 Evidence independence and coverage-qualified absence
ADR-025-10 Ranking policy and ReasoningProfile (no multiplicative utility)
ADR-025-11 Branches, scenarios, analyst-in-the-loop
ADR-025-12 Retention, erasure and permissible-inference policy
```

Exit: no unresolved contradiction between 024 and 025 terminology and lifecycles; §47.4 targets ratified.

### Wave 1 — Domain kernel + corpus seed
Core domain objects, canonicalization, truth algebra; **first 10 golden-corpus cases** (conflicting sources, syndication, missing source, late event, non-exhaustive space).

### Wave 2 — Durable substrate
Migrations, append-only guards, content-addressed artifact store, sequencer, optimistic concurrency.

### Wave 2S — Vertical slice (Slice-0)
Thin end-to-end path through real components, with minimal operators:

```text
two conflicting sources
 → propositions with BOTH truth state
 → Contradiction (with dependency groups)
 → HypothesisSpace with two hypotheses + H_OTHER
 → prediction + DiscriminatingTest (surrogate gain, labelled)
 → ResearchObligation → ResearchAction (proposed, approved by analyst)
 → existing task boundary → new observation
 → PredictionOutcome → new ContextRevision (hypotheses re-evaluated)
 → replay reproduces every intermediate artifact
```

Exit: Slice-0 passes in dev-lite and dev-full; its fixtures become corpus cases.

### Waves 3–12
Locality, Dynamics, Abduction, Dialectics, Frontier, Scientific integration, Query compiler, UI, Hardening, Acceptance (see Appendix U). Each wave adds its corpus cases before exit.

---

## 56. Implementation tasks

### Phase A — Shared domain kernel
- [ ] `T025-001` ContextCell model.
- [ ] `T025-002` ContextOverlap model (pair/triple).
- [ ] `T025-003` RestrictionMap model.
- [ ] `T025-004` CompatibilityAssessment model.
- [ ] `T025-005` GluingResult model.
- [ ] `T025-006` StateVariable model.
- [ ] `T025-007` StateEstimate model.
- [ ] `T025-008` Hypothesis + logical/revision ids + status/trend.
- [ ] `T025-009` Assumption model.
- [ ] `T025-010` DialecticalPair model.
- [ ] `T025-011` Prediction model.
- [ ] `T025-012` DiscriminatingTest model.
- [ ] `T025-013` Contradiction model.
- [ ] `T025-014` Obstruction model.
- [ ] `T025-015` Regime model.
- [ ] `T025-016` TransitionWindow model.
- [ ] `T025-017` Completeness/saturation models.
- [ ] `T025-018` Compute-budget model.
- [ ] `T025-019` Deterministic canonicalization utilities.
- [ ] `T025-020` Shared TruthState algebra (all five operations).

### Phase B — Persistence
- [ ] `T025-021` Context cell storage migrations.
- [ ] `T025-022` Overlap/compatibility migrations.
- [ ] `T025-023` Gluing/obstruction migrations.
- [ ] `T025-024` State estimate migrations.
- [ ] `T025-025` Hypotheses and revisions migrations.
- [ ] `T025-026` Assumptions/predictions/tests migrations.
- [ ] `T025-027` Contradiction migrations.
- [ ] `T025-028` Regime/transition migrations.
- [ ] `T025-029` Reasoning-run migrations.
- [ ] `T025-030` Tenant-scoped indexes.
- [ ] `T025-031` Revision uniqueness guards `(context, branch, revision)`.
- [ ] `T025-032` Append-only write guards.
- [ ] `T025-033` Foreign-key integrity checks.

### Phase C — Compatibility/locality
- [ ] `T025-034` Bounded cell blocking (bucket overflow reporting).
- [ ] `T025-035` Scope intersection.
- [ ] `T025-036` Restriction projection.
- [ ] `T025-037` Pairwise compatibility operators.
- [ ] `T025-038` Multi-cell compatibility aggregation.
- [ ] `T025-039` Obstruction generation.
- [ ] `T025-040` Gluing candidate construction.
- [ ] `T025-041` Partial-gluing state.
- [ ] `T025-042` Obligations from persistent obstructions.

### Phase D — State/dynamics
- [ ] `T025-043` State-variable registry.
- [ ] `T025-044` Observation-model contract.
- [ ] `T025-045` Deterministic baseline estimator (see T025-148).
- [ ] `T025-046` Residual tracking.
- [ ] `T025-047` Temporal interval algebra (see T025-140).
- [ ] `T025-048` Window materialization.
- [ ] `T025-049` Change-point operator interface.
- [ ] `T025-050` Regime descriptor.
- [ ] `T025-051` Regime-shift candidate.
- [ ] `T025-052` Worldline snapshot integration.

### Phase E — Abduction
- [ ] `T025-053` Hypothesis canonicalization.
- [ ] `T025-054` Bounded abductive search with auditable pruning.
- [ ] `T025-055` Explanation materialization.
- [ ] `T025-056` Support/refutation ledger.
- [ ] `T025-057` Complexity scoring.
- [ ] `T025-058` Assumption penalties.
- [ ] `T025-059` Diversity-preserving top-k.
- [ ] `T025-060` Prediction generation.
- [ ] `T025-061` Discriminating-test generation.

### Phase F — Dialectics
- [ ] `T025-062` Dialectical pairing.
- [ ] `T025-063` Counter-hypothesis generators.
- [ ] `T025-064` Shared-premise extraction.
- [ ] `T025-065` Differential-prediction calculation.
- [ ] `T025-066` Dialectical revision events.

### Phase G — Contradictions/epistemic state
- [ ] `T025-067` Paraconsistent truth-state integration.
- [ ] `T025-068` Contradiction detection (BOTH ⇒ Contradiction).
- [ ] `T025-069` Contradiction independence assessment (via dependency groups).
- [ ] `T025-070` Persistent contradiction lifecycle.
- [ ] `T025-071` Contradiction → obligation generation.

### Phase H — Information gain/frontier
- [ ] `T025-072` Information-gain operator contract (tiers).
- [ ] `T025-073` Hypothesis discrimination matrix.
- [ ] `T025-074` Action utility decomposition (no multiplicative form).
- [ ] `T025-075` Frontier ranking (profile modes).
- [ ] `T025-076` Action memory.
- [ ] `T025-077` Saturation state.
- [ ] `T025-078` Termination report.
- [ ] `T025-079` Reopen-on-contradiction.

### Phase I — Science integration
- [ ] `T025-080` Evaluation anchored to worldline snapshots.
- [ ] `T025-081` TDA feature series.
- [ ] `T025-082` Change-point analysis.
- [ ] `T025-083` Calibration results (cohorts from PredictionOutcome).
- [ ] `T025-084` Causal identification/estimation/refutation.
- [ ] `T025-085` Null-model outputs.
- [ ] `T025-086` Method/dependency fingerprints.

### Phase J — Operator registry
- [ ] `T025-087` Registry contract.
- [ ] `T025-088` Operator compatibility validation.
- [ ] `T025-089` Resource metadata.
- [ ] `T025-090` Operator provenance.
- [ ] `T025-091` Donor adapters.
- [ ] `T025-092` Deterministic selection profile.
- [ ] `T025-093` Adaptive selection profile.

### Phase K — Query compiler
- [ ] `T025-094` Query intent AST.
- [ ] `T025-095` Deterministic structured grammar.
- [ ] `T025-096` Optional LLM parser adapter (recorded-proposal replay).
- [ ] `T025-097` Semantic binding.
- [ ] `T025-098` Constraint → planner compilation.
- [ ] `T025-099` Completeness-mode compilation.
- [ ] `T025-100` Aggregation requirements.

### Phase L — Read models/API
- [ ] `T025-101` Context state endpoint.
- [ ] `T025-102` Revision endpoint (branch-aware).
- [ ] `T025-103` Hypothesis endpoint (spaces, predictions).
- [ ] `T025-104` Contradiction endpoint.
- [ ] `T025-105` Dynamics endpoint.
- [ ] `T025-106` Frontier endpoint.
- [ ] `T025-107` Provenance endpoint.
- [ ] `T025-108` Completeness endpoint/data shape.

### Phase M — UI
- [ ] `T025-109` Workspace shell.
- [ ] `T025-110` Hypothesis matrix (with H_OTHER, n_eff).
- [ ] `T025-111` Contradiction inspector.
- [ ] `T025-112` Context-cell map (triple inconsistencies).
- [ ] `T025-113` Dynamics/regime view.
- [ ] `T025-114` Evidence ladder.
- [ ] `T025-115` Frontier panel.
- [ ] `T025-116` Provenance/reasoning trace.
- [ ] `T025-117` Completeness/saturation indicator.

### Phase N — Benchmarks (each corpus is started in its own phase, finished here)
- [ ] `T025-118` Determinism corpus.
- [ ] `T025-119` Locality corpus.
- [ ] `T025-120` Abduction corpus.
- [ ] `T025-121` Dialectical corpus.
- [ ] `T025-122` Temporal corpus.
- [ ] `T025-123` Dynamics corpus.
- [ ] `T025-124` TDA corpus.
- [ ] `T025-125` Causal corpus.
- [ ] `T025-126` Information-gain corpus.
- [ ] `T025-127` Global-query corpus.
- [ ] `T025-128` Replay benchmark.
- [ ] `T025-129` Resource-budget benchmark.

### Phase O — v2 additions
- [ ] `T025-130` EvidenceDependencyGroup model and deterministic derivation from lineage.
- [ ] `T025-131` Independence operator (class `INDEPENDENCE`).
- [ ] `T025-132` `n_eff` and group-based consumption in update rules and saturation.
- [ ] `T025-133` HypothesisSpace model, exclusivity groups, `H_OTHER` mass handling.
- [ ] `T025-134` PredictionOutcome model/ingestion; realized information gain.
- [ ] `T025-135` CoverageQualifiedAbsence model and admissibility rule.
- [ ] `T025-136` Numeric modes, quantization utilities, seed derivation.
- [ ] `T025-137` Single sequencer, recorded batch boundaries, optimistic concurrency.
- [ ] `T025-138` Content-addressed artifact store and revision manifests.
- [ ] `T025-139` ReasoningProfile model; ranking modes; tier interleave; exploration quota.
- [ ] `T025-140` 13-relation Allen algebra with disjunctive sets, converse/intersection/composition, bounded path consistency.
- [ ] `T025-141` Triple-coherence check with `max_triples` and unchecked reporting.
- [ ] `T025-142` Branch model and mainline-isolation guard.
- [ ] `T025-143` Material-difference metric and steelman parity audit.
- [ ] `T025-144` AnalystAssertion/AnalystDecision objects and endpoints.
- [ ] `T025-145` Retention policy, crypto-shredding, legal hold, `REPLAY_DEGRADED`.
- [ ] `T025-146` Inference-policy gate (compiler + generators).
- [ ] `T025-147` Tenant-keyed operator cache.
- [ ] `T025-148` Interval constraint propagation estimator.
- [ ] `T025-149` Truth-lattice property-test suite (laws + truth tables).
- [ ] `T025-150` Quantitative-target benchmark harness (§47.4).
- [ ] `T025-151` Honesty-metric denominators (App. K).
- [ ] `T025-152` Slice-0 end-to-end scenario.
- [ ] `T025-153` CI check: every FR maps to ≥1 task and ≥1 test (App. Y).
- [ ] `T025-154` ADR-025-08 … ADR-025-12.

---

## 57. Exact implementation order (v2)

```text
Wave 0  Contract freeze (ADR 01–12, ratify targets)
  ↓
A Domain kernel (+ T130, T133, T135, T136, T149, corpus seed)
  ↓
B Persistence (+ T137, T138)
  ↓
2S  VERTICAL SLICE (T152)
  ↓
C Locality (+ T141)
  ↓
D Temporal/state (+ T140, T148)
  ↓
E Abduction (+ T143)
  ↓
G Epistemic/contradictions (+ T131, T132)
  ↓
F Dialectics
  ↓
H Frontier (+ T134, T139)
  ↓
I Science
  ↓
J Operators (+ T147)
  ↓
K Query compiler (+ T146)
  ↓
L API (+ T142, T144)
  ↓
M UI
  ↓
N Benchmarks hardening (+ T145, T150, T151, T153)
```

`G` precedes `F` because dialectical competition depends on durable contradiction/support semantics. Benchmarks are *not* last: each phase adds its corpus cases before its wave exit.

---

## 58. Required integration with existing specifications

- **58.1 — 024 Context-driven continuous intelligence.** 025 consumes and extends `InvestigationContext`, `ContextRevision`, `ResearchObligation`, `ResearchAction`, `ContextFrontier`, `SaturationState`, `ResearchLineage`, and must not redefine their approved semantics. The state vocabularies of §21.1 and Appendix F are to be reconciled name-for-name with 024 in Wave 0; on conflict, 024 prevails.
- **58.2 — 006 Scientific intelligence.** 025 consumes calibrated claims, hypotheses, causal inference, temporal analysis, network/TDA analysis, robustness, experiments, and provides the contextual integration state in which those results are interpreted.
- **58.3 — 012 Dynamic entity invariant.** Treated as a temporal/worldline input, not a context-local substitute for entity identity.
- **58.4 — 015 Worldline reconstruction.** State/dynamics analysis binds to durable worldline snapshots.
- **58.5 — 016 / 019 / 021 Relation fabric.** 025 consumes relation signals/candidates/claims and their lineage; it does not move relation extraction into the context engine.
- **58.6 — 017 Semantic fabric.** Semantic profiles/regimes are interpretive constraints; semantic lookup is not truth.
- **58.7 — 018 World substrate.** 025 reads and writes through the existing world substrate contract; it must not construct an independent world graph.

---

## 59. Non-goals that must remain permanently explicit

The following are architectural failures even if the code "works":

```text
LLM → final truth
TDA → causality
centrality → importance truth
source count → independence
search count → completeness
high score → admission
co-occurrence → generic relationship
semantic mapping failure → deletion
contradiction → overwrite
unknown → false
not searched → negative finding
searched with unknown detection power → negative finding
heuristic score → probability
posterior over a non-exhaustive space without residual mass
cross-kind comparison of scores
scenario/counterfactual output → mainline finding
analyst override → silent replacement of model state
pairwise compatibility → claimed global coherence
```

---

## 60. Definition of done (derived summary)

This section is a human-readable summary. The **normative** conditions are §54 (all gates A–Q green), Appendix T (every FR green) and Appendix U (every wave gate passed), with Appendix Y proving coverage. 025 is complete when simultaneously:

1. A durable context can be created and revised without mutation of history; concurrent writers are safe.
2. The context decomposes into bounded local cells compared through explicit overlaps/restrictions, with pair and triple coherence checked under budget.
3. Compatible local sections can be partially glued; obstructions persist and generate obligations.
4. State variables and hidden states are explicit; the baseline estimator yields feasible sets and residuals.
5. Hypotheses are first-class, versioned, and live in explicit hypothesis spaces with residual mass where non-exhaustive.
6. Abduction generates competing explanations; dialectics generates materially different, parity-audited counter-hypotheses and discriminating predictions.
7. Contradictions persist without collapsing the model; `BOTH` is representable and always tied to a Contradiction.
8. Evidence is aggregated by independence groups; absences count only under declared coverage.
9. Predictions have outcomes that feed hypotheses, realized gain and calibration.
10. Dynamics detect regime changes without silently calling them causes; TDA is consumed as structural evidence only.
11. Causal analysis exposes identification, estimation and refutation separately.
12. Research actions are selected by a declared, non-multiplicative, tier-respecting ranking policy.
13. Global search reports completeness honestly.
14. Every result is reconstructible through applicable lineage; every calculation exposes method/version/seed/fingerprint.
15. The deterministic core runs without neural models; adaptive models are optional and subordinate.
16. Replay reproduces intermediate state per determinism class.
17. Resource limits and quantitative targets are explicit and enforced.
18. Branches never leak into the mainline; analyst decisions are traced.
19. Retention/erasure and permissible-inference policies are enforced; caches are tenant-keyed.
20. The system remains one coherent extension of the existing COGNITIVE world substrate.

---

## 61. Canonical mental model

```text
                   ┌─────────────────────────┐
                   │        REAL WORLD       │
                   └────────────┬────────────┘
                                │ imperfect observation
                                ▼
                   ┌─────────────────────────┐
                   │    WORLD SUBSTRATE      │
                   │ observations / evidence │
                   │ entities / relations    │
                   │ worldlines / events     │
                   └────────────┬────────────┘
                                │ local contextualization
                                ▼
                   ┌─────────────────────────┐
                   │     CONTEXT FABRIC      │
                   │ cells / overlaps /      │
                   │ restrictions / gluing   │
                   └────────────┬────────────┘
                                │ state reconstruction
                                ▼
                   ┌─────────────────────────┐
                   │   DYNAMICAL MODEL       │
                   │ states / regimes /      │
                   │ transitions / topology  │
                   └────────────┬────────────┘
                                │ hypothesis space
                                ▼
              ┌─────────────────────────────────────┐
              │       EPISTEMIC / REASONING         │
              │ abduction / deduction / dialectics  │
              │ probability / argumentation         │
              │ contradiction / causal inference    │
              └──────────────────┬──────────────────┘
                                 │ discriminating evidence
                                 ▼
              ┌─────────────────────────────────────┐
              │        RESEARCH FRONTIER            │
              │ obligations / actions / budget      │
              │ capability routing / saturation     │
              └──────────────────┬──────────────────┘
                                 │ acquisition
                                 ▼
                         NEW OBSERVATIONS
                                 │
                                 └──────────↺
```---
## Appendix A — Minimum object dependency graph

```text
ContextDefinition
      └── ContextBranch
             └── ContextRevision (manifest of content-addressed artifacts)
                    ├── ContextCell
                    │      └── ContextOverlap (pair/triple)
                    │              ├── RestrictionMap
                    │              └── CompatibilityAssessment
                    │                        └── GluingResult
                    │                               └── Obstruction
                    ├── StateVariable
                    │      └── StateEstimate
                    │             └── Regime
                    │                    └── TransitionWindow
                    ├── EvidenceDependencyGroup
                    ├── CoverageQualifiedAbsence
                    ├── HypothesisSpace
                    │      └── Hypothesis
                    │             ├── Assumption
                    │             ├── Explanation
                    │             ├── Prediction
                    │             │      └── PredictionOutcome
                    │             ├── DiscriminatingTest
                    │             └── DialecticalPair
                    ├── Contradiction
                    ├── AnalystAssertion / AnalystDecision
                    ├── TDA features
                    ├── Causal evaluations
                    └── ResearchObligation
                           └── ResearchAction
                                  └── Task
                                         └── Result
                                                └── ContextRevision
```

## Appendix B — Minimum per-object provenance

Every derived object has: `object_id`, `context_id`, `branch_id`, source/input refs, `created_by_operator`, `operator_version`, `parameters_fingerprint` (including seed), `policy_fingerprint`, `semantic_regime_ref`, `input_revision`, `output_revision`.

Where applicable also: `worldline_snapshot_ref`, `model_ref`, `calibration_ref`, `experiment_ref`, `research_obligation_ref`, `dependency_group_refs`, `reasoning_profile_ref`.

## Appendix C — Canonical example: complex global query

User:

```text
Найди всех субъектов, которые контролируют криптоактивы на сумму не менее $1M,
объедини связанные кошельки, покажи, что это один контрольный кластер,
а затем объясни, какие кластеры действительно являются независимыми субъектами.
```

Decomposition (at least):

```text
 1. define target class
 2. check inference policy (attribution to natural persons is a sensitive class, §49.3)
 3. define asset valuation semantics
 4. define time as-of
 5. enumerate supported chains/sources
 6. discover candidate addresses
 7. construct wallet-level observations
 8. produce behavioural/structural signals
 9. cluster control hypotheses inside an explicit HypothesisSpace (incl. H_OTHER)
10. preserve unresolved clusters
11. aggregate valuations (FIXED_POINT decimals; unknown balances stay UNKNOWN)
12. estimate cross-chain linkage
13. evaluate attribution evidence with dependency groups
14. detect contradictory attribution evidence
15. test alternative cluster explanations (parity-audited counter-hypotheses)
16. record coverage-qualified absences ("no further links found" with coverage/detection power)
17. estimate completeness/saturation
18. emit results with uncertainty and lineage
```

It must not reduce to "SQL query → list of whales": the hard problem is the epistemic path from addresses to a defensible control hypothesis.

## Appendix D — Canonical example: "what is happening around X?"

A broad query compiles into: scope, actors, resources, constraints, relationships, events, temporal sequence, state variables, narratives, hypotheses (in a space), counter-hypotheses, regime changes, causal candidates, contradictions, missing observations, research frontier. The answer distinguishes `OBSERVED`, `INFERRED`, `HYPOTHESIZED`, `UNRESOLVED`, `CONTESTED` and shows the chain from any conclusion to evidence.

## Appendix E — Engineering rule of thumb

Before accepting any implementation proposal ask:

```text
1. What is directly observed?
2. What is derived?
3. What could contradict it?
4. What evidence would distinguish the alternatives?
5. Can the result be replayed and explained?
6. How many of the supporting items are actually independent?
7. What probability mass is not accounted for by the listed hypotheses?
```

If the answer to any is "the model just knows", the implementation does not satisfy 025.

---

## Appendix F — Explicit state machines (normative)

### F.1 ContextRevision

| From | Allowed to |
|---|---|
| PROPOSED | VALIDATING |
| VALIDATING | COMMITTED, REJECTED |
| COMMITTED | SUPERSEDED |
| REJECTED, SUPERSEDED | (terminal) |

Forbidden: `REJECTED → COMMITTED`, `SUPERSEDED → COMMITTED`, `COMMITTED → PROPOSED`. A retry creates a new revision proposal. Replay is not a status (§6.2).

### F.2 Hypothesis
Table in §15.4. `trend` (STRENGTHENED/WEAKENED/STABLE/NEW) is derived and not part of the state machine.

### F.3 Contradiction
Table in §23.3.

### F.4 ResearchObligation (aligned with §21.1)

| From (lifecycle) | Allowed to |
|---|---|
| OPEN (readiness: BLOCKED_* ⇄ READY) | SATISFIED, UNSATISFIABLE, ABANDONED, SUPERSEDED |
| UNSATISFIABLE | ABANDONED, OPEN (if capability/scope changes → new revision) |
| SATISFIED, ABANDONED, SUPERSEDED | (terminal; reopen = new obligation referencing the old one, or `CONTEXT_REOPENED`) |

Action machine:

```text
PROPOSED → AWAITING_APPROVAL | APPROVED (when policy needs no approval)
AWAITING_APPROVAL → APPROVED | REJECTED
APPROVED → RUNNING → OBSERVING → EVALUATING → COMPLETED | FAILED
PROPOSED | AWAITING_APPROVAL | APPROVED → CANCELLED
```

A temporary source failure moves an action to `FAILED`, never an obligation to `SATISFIED`.

### F.5 Prediction

```text
PENDING → CONFIRMED | FALSIFIED | INDETERMINATE | EXPIRED | UNOBSERVABLE
INDETERMINATE → CONFIRMED | FALSIFIED | EXPIRED
UNOBSERVABLE → PENDING (when a capability appears)
```

---

## Appendix G — Exact data contracts

### G.1 Canonical identifier grammar

All identifiers: `PREFIX-{32 lowercase hex}`.

```text
CXI  context            CXC  cell               OVL  overlap
RST  restriction        CMP  compatibility      GLU  gluing
VAR  state variable     STE  state estimate     HYP  hypothesis revision
LHYP logical hypothesis HSP  hypothesis space   ASM  assumption
EXP  explanation        PRD  prediction         PRO  prediction outcome
CTR  contradiction      OBST obstruction        OBS  observation (substrate)
DGT  discriminating test DLP dialectical pair   REG  regime
TRN  transition         TDA  topological feat.  CAU  causal model
SAT  saturation         OBL  obligation         ACT  action
DEC  decision           RUN  reasoning run      MF   method fingerprint
PF   parameter/policy fingerprint               REV  revision state hash
BRN  branch             EDG  dependency group   CQA  coverage-qualified absence
ANL  analyst assertion  RPF  reasoning profile  RET  retention policy
MOD  model              QRY  query              SR   semantic regime
WLS  worldline snapshot EVID evidence item      GAP  evidence gap
ENT  entity (substrate) REL  relation (substrate)
```

Fix from v1: `OBS-` was used for both Obstruction and Observation; Obstruction is now `OBST-`. Prefixes used elsewhere in the text but missing in v1 (`PRD`, `MOD`, `QRY`, `SR`, `WLS`, `EVID`, `GAP`, `ENT`, `REL`) are now declared; `ENT`, `REL`, `OBS`, `WLS`, `SR`, `EVID` are owned by the existing substrate and listed for reference. Prefix length is not a semantic commitment; canonical material and version determine identity.

### G.2 Canonicalization algorithm

```python
def canonical_material(value, numeric_policy):
    normalized = normalize_strings(value)
    normalized = normalize_unicode(normalized, form="NFC")
    normalized = normalize_timestamps(normalized)          # UTC, declared precision
    normalized = normalize_numbers(normalized, numeric_policy)
        # EXACT: integers as-is; FIXED_POINT: decimal strings at declared scale;
        # FLOAT_QUANTIZED: round to declared significant digits, then decimal string;
        # NaN/Inf are forbidden in identity material
    normalized = sort_object_keys(normalized)
    normalized = sort_sets(normalized)
    normalized = remove_identity_excluded_fields(normalized)
    return json_encode(normalized, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
```

Forbidden in identity material: wall-clock creation time, worker/host/process id, random UUID, memory address, hash-map iteration order, cache state, query execution order where semantically irrelevant, unquantized floats.

### G.3 `ContextCell` JSON example

```json
{
  "cell_id": "CXC-8e3d...",
  "context_id": "CXI-21d9...",
  "cell_kind": "ENTITY_EGO",
  "scope_descriptor": {
    "entity_refs": ["ENT-a1..."],
    "hop_limit": 2,
    "relation_classes": ["OWNERSHIP", "CONTROL", "EMPLOYMENT"]
  },
  "temporal_slice": {"start": "2026-01-01T00:00:00Z", "end": "2026-10-01T00:00:00Z", "precision": "DAY"},
  "observation_refs": ["OBS-..."],
  "entity_refs": ["ENT-a1..."],
  "relation_refs": ["REL-..."],
  "completeness": {"status": "PARTIAL", "missing_dimensions": ["private_transactions"]},
  "trust_state": "VERIFIED"
}
```

### G.4 `Hypothesis` JSON example

```json
{
  "hypothesis_id": "HYP-...",
  "logical_id": "LHYP-...",
  "space_ref": "HSP-...",
  "context_id": "CXI-...",
  "branch_id": "BRN-...",
  "statement": {"type": "CONTROL_CLUSTER", "subject": "CLUSTER-c1",
                "predicate": "CONTROLLED_BY_SAME_ACTOR", "object": "ACTOR-a1"},
  "assumptions": ["ASM-..."],
  "premises": ["OBS-...", "REL-..."],
  "supporting_evidence": ["EVID-..."],
  "refuting_evidence": ["EVID-..."],
  "missing_evidence": ["GAP-..."],
  "truth_state": {"positive_support": true, "negative_support": false},
  "status": "ACTIVE",
  "trend": "STRENGTHENED",
  "score": {"kind": "MODEL_POSTERIOR", "value": 0.41,
            "target": "P(H | evidence, model MOD-..., space HSP-...)", "model_ref": "MOD-..."},
  "predictions": ["PRD-..."],
  "discriminating_tests": ["DGT-..."]
}
```

---

## Appendix H — Exact operator execution protocol

Every operator invocation is a transactionally recorded `ReasoningRun`.

```yaml
ReasoningRun:
  run_id: RUN-...
  context_id: CXI-...
  branch_id: BRN-...
  input_revision: 42
  operator_id: operator.abduction
  operator_version: 1.3.0
  parameter_fingerprint: PF-...
  seed: ...
  policy_fingerprint: PF-...
  reasoning_profile_ref: RPF-...
  semantic_regime_ref: SR-...
  dependency_fingerprint: MF-...
  resource_budget: {...}
  input_refs: [...]
  output_refs: [...]
  mode: LIVE | REPLAY
  status: STARTED | COMPLETED | PARTIAL | FAILED
  failure_code: optional
  truncation: optional
  created_at: timestamp
  duration_ms: integer
```

Execution sequence:

```text
 1. validate operator registration
 2. validate input contract
 3. check inference policy for the operator's output classes
 4. load declared dependencies
 5. bind context revision and branch
 6. bind semantic regime and reasoning profile
 7. bind policy and derive seed
 8. allocate resource budget
 9. execute operator
10. validate output contract
11. generate explanation trace
12. persist result + run record
13. emit event
14. expose result only after commit
```

Failure semantics: if step 10 fails, the operator result is `QUARANTINED`, no world-model mutation occurs, run status is `FAILED`, an error artifact is persisted, and the input remains replayable.

---

## Appendix I — Detailed algorithms

### I.1 Bounded overlap discovery

```python
for cell in cells:
    for key in blocking_keys(cell, B):
        index[key].append(cell.id)

for key, members in sorted(index.items()):
    members = sort_by_cell_id(deterministic_unique(members))
    if len(members) > B.max_bucket_size:
        record_obstruction("BUCKET_OVERFLOW", key, len(members))   # + obligation: broader blocking
        continue
    for left, right in bounded_pairs(members):
        overlap = compute_scope_intersection(left, right)
        if overlap != EMPTY:
            emit_overlap(left, right, overlap)
```

Properties: no global all-pairs, stable ordering, bounded buckets, observable overflow.

### I.2 Compatibility aggregation
Each dimension yields `SUPPORTED | CONTRADICTED | UNKNOWN | NOT_APPLICABLE`. The evaluator returns compatible, contradicted and unknown dimensions plus weight/model metadata. The vector is authoritative; a single verdict may be profile-derived.

### I.3 Gluing with triple coherence

```python
def glue(cells, compat, profile, budget):
    compatible = collect_compatible_sections(cells, compat)
    conflicts  = collect_conflicts(cells, compat)
    unknowns   = collect_unknown_joins(cells, compat)

    triples, unchecked = enumerate_triangles(overlap_graph(cells), budget.max_triples)  # stable order
    for (ci, cj, ck) in triples:
        if not coherent_on_triple_overlap(ci, cj, ck, compat):
            conflicts.append(triple_conflict(ci, cj, ck))

    merged = merge_nonconflicting_structure(compatible)
    obstructions = make_obstructions(conflicts, unknowns)

    if conflicts and not profile.allows_partial_gluing:
        verdict = "BLOCKED"
    elif conflicts or unknowns or unchecked:
        verdict = "PARTIALLY_GLUED"
    else:
        verdict = "GLUED"
    return GluingResult(verdict, merged, conflicts, obstructions,
                        triples_checked=len(triples), triples_unchecked=unchecked)
```

`GLUED` may never be returned while `triples_unchecked > 0`.

### I.4 Abductive search (bounded best-first)

```python
OPEN = priority_queue(); CLOSED = set(); RESULTS = diverse_set(material_difference)
space = open_hypothesis_space(question, exhaustive=profile.assume_exhaustive)

while OPEN and budget.available():
    partial = OPEN.pop_best()
    if complete(partial):
        if valid_explanation(partial):
            RESULTS.add(partial)          # rejected as duplicate if not materially different
        continue
    for candidate in expand(partial):
        sig = canonical_signature(candidate)
        if sig in CLOSED: continue
        if dominated(candidate, OPEN, RESULTS):          # same score kind only
            record_pruned(candidate, "DOMINATED", comparison_set, dimensions, operator_version)
            continue
        CLOSED.add(sig); OPEN.push(candidate)

ensure_residual_hypothesis(space)          # H_OTHER when not exhaustive
```

Every prune records candidate signature, comparison set, dominance dimensions and operator version. Ties break by canonical signature order (deterministic).

### I.5 Dialectical pair generation

```python
for thesis in active_hypotheses:
    competitors = generate_counter_hypotheses(thesis, same_budget_as=thesis)
    competitors = [c for c in competitors if materially_different(thesis, c)]
    if not competitors:
        record_result(thesis, reason_code)       # NO_VALID_COUNTERHYPOTHESIS etc.
        continue
    for anti in competitors:
        pair = build_dialectical_pair(thesis, anti)
        pair.differential_predictions = compare_predictions(thesis, anti)
        pair.tests = generate_discriminating_tests(pair)
        pair.parity_audit = audit_parity(thesis, anti)
        persist(pair)
```

### I.6 Research action selection

```python
ready, blocked = split_by_hard_gates(frontier.actions())      # policy, capability, safety, feasibility
for a in ready:
    a.gain = estimate_gain(a)                # carries tier
    a.cost = estimate_cost(a)                # UNKNOWN allowed; never silently 0
    a.quality = estimate_source_quality(a)
    a.discrimination = estimate_hypothesis_discrimination(a)

ranked = rank(ready, profile.ranking_mode, profile.tier_interleave)   # no cross-tier numeric comparison
picked = apply_exploration_quota(ranked, profile.exploration_quota)
return picked[:budget.max_actions], blocked_with_reasons(blocked)
```

### I.7 Context tick (batch-based)

```python
def context_tick(context, branch, batch):
    prior = load_current_revision(context, branch)

    changes = classify_change(batch, prior)               # includes analyst decisions, policy/profile changes
    invalidated = dependency_graph.affected(changes)

    cells = recompute_cells(invalidated.cells)
    overlaps = recompute_overlaps(invalidated.overlaps)
    compat = recompute_compatibility(invalidated.compatibility)
    gluing = recompute_gluing(invalidated.gluing)         # pair + triple

    groups = recompute_dependency_groups(changes)
    absences = assess_absences(changes, groups)
    truth = recompute_truth_states(changes, groups, absences)
    contradictions = detect_contradictions(changes, compat, truth, groups)   # BOTH => Contradiction

    states = recompute_states(invalidated.states)
    dynamics = recompute_dynamics(invalidated.dynamics)

    outcomes = evaluate_predictions(prior.predictions, changes, absences)
    spaces, hypotheses = reevaluate_hypotheses(prior, changes, contradictions, states, dynamics, outcomes, groups)
    dialectics = update_dialectics(hypotheses, contradictions)
    predictions = recompute_predictions(hypotheses)
    tests = recompute_discriminating_tests(spaces, predictions)

    obligations = generate_obligations(context, hypotheses, contradictions, gluing.obstructions, absences)
    frontier = rank_frontier(obligations, tests)
    saturation = evaluate_saturation(context, obligations, frontier, groups)

    return commit_revision(prior, ...all of the above..., optimistic_check=prior.revision)
```

Production implementations may optimize stages but must preserve the observable dependency semantics.

---

## Appendix J — Dependency invalidation matrix

| Change | Cells | Overlaps | State | Dynamics | Groups | Hypotheses | Dialectics | Frontier |
|---|---|---|---|---|---|---|---|---|
| New observation | affected | affected | affected | affected | affected | affected | affected | affected |
| New relation claim | affected | affected | possible | affected | affected | affected | affected | affected |
| Contradiction | no | possible | possible | possible | possible | affected | affected | affected |
| Semantic mapping | affected | affected | affected | possible | possible | affected | affected | affected |
| Time correction | affected | affected | affected | affected | possible | affected | affected | affected |
| Dependency-group reassignment | no | no | no | no | affected | affected | affected | affected |
| New qualified absence | no | no | possible | no | no | affected | possible | affected |
| Prediction outcome | no | no | no | no | no | affected | affected | affected |
| Analyst decision | no | no | no | no | no | affected | affected | affected |
| Policy / reasoning-profile change | policy-defined | policy-defined | policy-defined | policy-defined | policy-defined | affected | affected | affected |
| Operator version change | affected outputs only | affected outputs only | affected outputs only | affected outputs only | affected outputs only | affected | affected | affected |
| Input erasure (retention) | affected | affected | affected | affected | affected | affected | affected | affected |
| UI state change | no | no | no | no | no | no | no | no |

The invalidation planner chooses the minimal safe superset.

---

## Appendix K — Observability specification

### K.1 Operator metrics
`reasoning_runs_total`, `reasoning_runs_failed_total`, `reasoning_runs_partial_total`, `reasoning_duration_ms`, `reasoning_cpu_ms`, `reasoning_memory_peak_mb`, `reasoning_candidates_generated`, `reasoning_candidates_pruned`, `reasoning_hypotheses_generated`, `reasoning_hypotheses_pruned`, `reasoning_output_count`, `gluing_triples_unchecked`, `bucket_overflow_total`.

### K.2 Epistemic metrics
`open_hypotheses`, `contested_hypotheses`, `contradictions_open`, `obstructions_open`, `unknown_state_variables`, `unresolved_identities`, `unsupported_assumptions`, `missing_evidence_items`, `residual_mass` (per hypothesis space), `informational_only_absences`.

### K.3 Research metrics
`obligations_open`, `obligations_satisfied`, `obligations_abandoned`, `actions_proposed`, `actions_approved`, `actions_rejected`, `actions_blocked`, `expected_information_gain` and `realized_information_gain` (both labelled by tier), `marginal_gain`, `source_diversity` (as `n_eff`), `coverage`, `exploration_picks`.

### K.4 Honesty metrics — denominators (v2)

| Metric | Definition |
|---|---|
| `unknown_rate` | state variables with status `UNKNOWN` ÷ state variables in the context scope |
| `contradiction_rate` | propositions with an open/persistent Contradiction ÷ propositions with any admitted support |
| `unresolved_rate` | unresolved identity mentions ÷ mentions in scope |
| `coverage_rate` | covered items ÷ items in the declared source universe (`UNKNOWN` when no universe is declared) |
| `calibration_error` | expected calibration error over the `CALIBRATED_SCORE`/`MODEL_POSTERIOR` cohort of the period (undefined, reported as `UNKNOWN`, when the cohort is below minimum size) |
| `budget_exhaustion_rate` | runs ending `BUDGET_EXHAUSTED` ÷ total runs, per operator and window |
| `residual_mass` | posterior mass on `H_OTHER` per space |

These are not vanity metrics. High unknown/contradiction rates may be scientifically correct.

---

## Appendix L — Audit queries the system must answer

- **L.1 "Why is this entity in my result?"** result item → claim → resolution decision → mentions → observations → captures → sources.
- **L.2 "Why is this relation in my result?"** relation claim → claim material → candidate → relation signals → mentions → observations → evidence.
- **L.3 "Why does the engine believe hypothesis H?"** hypothesis → current revision → support/refutation evidence (grouped by dependency group, `n_eff`) → assumptions → model → space (incl. `H_OTHER` mass) → method fingerprint.
- **L.4 "Why did the engine request source S?"** research action → discriminating test → target hypotheses → differential predictions → information gain model (tier) → ranking mode/profile → capability requirement → source/runtime.
- **L.5 "Why did the investigation stop?"** context closure → terminal obligations → saturation state → coverage → marginal gain → qualified absences → budget → unresolved blind spots → stopping policy.
- **L.6 "What changed when new evidence arrived?"** event → batch → changeset → invalidated dependencies → new context revision → changed hypotheses → changed contradictions → changed frontier.
- **L.7 "Why was this candidate dropped?"** pruned candidate → comparison set → dominance dimensions → operator version.
- **L.8 "Who overrode what?"** analyst decision → target → justification → model-derived state beside it.

---

## Appendix M — Test contract by implementation layer

### M.1 Unit tests
canonicalization (incl. numeric modes), id derivation, scope intersection, Allen algebra (converse, intersection, composition tables), truth-state operations (full truth tables), hypothesis ranking, dominance rule, information-gain calculations (per tier), saturation calculations, `n_eff`, absence admissibility, resource budget accounting, seed derivation.

### M.2 Property tests
canonicalization is idempotent; sort permutation does not change identity; restriction cannot fabricate evidence; replay is fixed-point; old revision remains readable; contradiction preserves both sides; unknown never becomes false automatically; truth lattice laws hold; Allen composition is consistent with converse; adding a duplicate of an existing evidence item never raises `n_eff` or a posterior; no ranking function compares across score kinds; branch writes never appear in mainline queries.

### M.3 Integration tests
observation → context cell; cell → overlap → compatibility; compatibility → gluing → obstruction; triangle of pairwise-compatible cells → `TRIPLE_INCONSISTENCY`; obstruction → obligation; hypothesis → prediction → discriminating test; test → action → task → observation → prediction outcome → hypothesis revision; worldline snapshot → dynamics → hypothesis revision; concurrent writers → exactly one commit wins; erasure → `INPUT_ERASED` + `REPLAY_DEGRADED`.

### M.4 End-to-end tests
single observation; conflicting observations; missing evidence; late observation; regime change; false-positive hypothesis; strong alternative hypothesis; global-search open-world query; budget exhaustion; operator unavailable; adaptive layer disabled; non-exhaustive hypothesis space; analyst override; scenario branch isolation; sensitive-inference blocked by policy; Slice-0.

---

## Appendix N — Test cases with expected epistemic behaviour

**N.1 Missing source.** H requires variable V; no registered source observes V. Expected: H remains ACTIVE/UNCERTAIN; V = UNKNOWN; obligation `BLOCKED_CAPABILITY`; no false negative.

**N.2 Conflicting sources.** Source A: X; Source B: not-X. Expected: `truth_state(X) = BOTH`; Contradiction OPEN with independence assessment; alternatives retained; obligation may be created.

**N.3 Same source syndicated.** Source A article; B exact copy; C translated copy. Expected: three captures; one or more content identities; explicit syndication lineage; one dependency group (or two if translation is independent extraction by declared rule); `n_eff` below raw count; posterior not inflated.

**N.4 TDA anomaly.** Persistent H1 feature disappears sharply. Expected: derived structural result; possible transition obligation; NO causal claim.

**N.5 Attractive hypothesis with no discriminating evidence.** Hypothesis may remain ACTIVE; confidence does not become 1.0; frontier explains that no discriminating evidence is available.

**N.6 Triple inconsistency.** A≈B and B≈C and A≈C pairwise on time, but jointly inconsistent on the triple overlap. Expected: pairwise verdicts COMPATIBLE; gluing `PARTIALLY_GLUED` with `TRIPLE_INCONSISTENCY` obstruction; never `GLUED`.

**N.7 Non-exhaustive space.** Two listed hypotheses explain the data; space declared non-exhaustive. Expected: `H_OTHER` carries declared mass; posteriors of listed hypotheses sum to < 1; IG reports whether it addresses `H_OTHER`.

**N.8 Search with unknown detection power.** Source searched, nothing found, detection power unknown. Expected: `CoverageQualifiedAbsence` stored as `INFORMATIONAL_ONLY`; no negative support; saturation reflects it as coverage only.

**N.9 Analyst override.** Analyst marks H as DISCARDED against model state ACTIVE. Expected: decision stored with justification; UI shows both; model state unchanged; downstream explanation flags the override.

**N.10 Unrelated numbers.** A heuristic-scored candidate and a probabilistic candidate in the same frontier. Expected: ranked by declared interleave, never by comparing raw values.

**N.11 Counterfactual isolation.** A counterfactual branch concludes "if X had not happened, Y would have stopped". Expected: result visible only on the branch; mainline contains no corresponding finding.

---

## Appendix O — Query compiler grammar

```ebnf
query          = verb, target, constraints?, temporal?, scope?, output? ;
verb           = "find" | "show" | "compare" | "explain" | "trace" | "detect" ;
target         = noun_phrase | relation_phrase | event_phrase ;
constraints    = { constraint } ;
constraint     = field, operator, value ;
temporal       = "as_of", timestamp | "between", timestamp, timestamp ;
scope          = "within", scope_term ;
output         = "return", field_list ;
operator       = "=" | ">" | ">=" | "<" | "<=" | "contains" | "in" ;
```

Natural-language adapters compile into the same AST as the deterministic parser.

### O.1 AST

```yaml
QueryAST:
  verb: FIND
  target: {concept: CRYPTO_CONTROL_CLUSTER}
  filters:
    - {field: aggregate_asset_value, operator: GTE, value: 1000000, unit: USD}
  temporal: {mode: AS_OF, timestamp: 2026-10-04T00:00:00Z}
  scope: {universe: REGISTERED_CHAIN_SOURCES}
  output:
    include: [cluster, valuation, supporting_evidence, coverage, contradictions, qualified_absences]
```

---

## Appendix P — Completeness protocol

Every query that semantically implies universality (`all`, `every`, `global`, `none`) must be checked for completeness mode.

### P.1 Compiler output

```yaml
CompletenessRequirement:
  requested_mode: UNIVERSAL
  feasible_mode: OPEN_WORLD_DISCOVERY
  universe_definition: REGISTERED_CHAIN_SOURCES
  required_conditions:
    source_catalogue_exhausted: true/false
    temporal_scope_defined: true/false
    identity_resolution_complete: true/false
    pagination_complete: true/false
    source_errors_zero_or_accounted: true/false
```

### P.2 Response rules
If universal conditions are not met, the engine phrases the result internally as "observed candidates under declared coverage". The UI may render the user's wording but exposes a completeness banner/state. A universal-negative ("none exist") is only expressible as a `CoverageQualifiedAbsence` that meets the profile's coverage and detection-power thresholds; otherwise it is reported as "none observed under declared coverage".

---

## Appendix Q — Method fingerprint

```yaml
MethodFingerprint:
  fingerprint_id: MF-...
  code_revision: string
  package_versions: {...}
  operator_versions: {...}
  model_versions: {...}
  semantic_regime_version: string
  policy_version: string
  reasoning_profile_version: string
  runtime_version: string
  numeric_environment: {platform, libm/BLAS build, float mode}
  build_metadata: {...}
```

A result is reproducible only when its fingerprint resolves to concrete versions. Floating dependencies (`latest`, `^1.2`, `>=1`) are insufficient.

---

## Appendix R — Deployment profiles

- **R.1 `dev-lite`** — single process where possible; local PostgreSQL (embedded or container) — **not SQLite** for persistence tests; CPU-only; adaptive layer OFF; small fixture corpus. Purpose: fast local iteration.
- **R.2 `dev-full`** — PostgreSQL, Redpanda, object store, Temporal, optional Neo4j projection, science services. Purpose: canonical integration validation.
- **R.3 `single-node-research`** — all authoritative state local, bounded worker pool, optional local model, resource budget enforced. Purpose: multi-day investigation on one machine.
- **R.4 `scale-out`** — stateless reasoning workers, partitioned context scheduling (one sequencer per context), shared durable authority, rebuildable projections, separate heavy science workers. Purpose: large-scale collection/reasoning.

---

## Appendix S — File-level implementation map

Indicative; exact paths follow repository conventions; no new application boundary.

```text
apps/shared/domain/context/
    __init__.py ids.py canonical.py numeric.py truth.py scope.py temporal.py allen.py
    cells.py overlap.py hypothesis.py hypothesis_space.py evidence.py absence.py
    contradiction.py dynamics.py frontier.py profile.py branch.py budget.py

apps/control-plane/cp_domain/context_engine/
    __init__.py context.py revisions.py sequencer.py decisions.py obligations.py
    frontier.py lifecycle.py replay.py retention.py inference_policy.py analyst.py

apps/science/context/
    operators/
        base.py compatibility.py gluing.py state.py abduction.py dialectics.py
        independence.py information_gain.py dynamics.py tda.py causal.py
    models/ calibration/ experiments/

apps/projection/context/
    readers.py materializers.py serializers.py metrics.py

apps/webapp/src/context/
    api/ state/ views/ components/ hooks/

bench/context/
    corpus/ deterministic/ locality/ independence/ absence/ abduction/
    dialectics/ dynamics/ global_search/ slice0/
```

Before creating a file, inspect adjacent code and reuse compatible primitives.

---

## Appendix T — Requirement catalogue

**Context and revision**
- `FR-025-001` ContextDefinition is immutable.
- `FR-025-002` Context identity excludes revision state.
- `FR-025-003` ContextRevision is append-only.
- `FR-025-004` ContextRevision is transactionally committed before visible.
- `FR-025-005` Historical revisions remain queryable.
- `FR-025-006` Context reconstruction is replayable.

**Locality**
- `FR-025-007` ContextCell is independently inspectable.
- `FR-025-008` Scope intersection is typed.
- `FR-025-009` Overlap generation is blocked and bounded.
- `FR-025-010` Restriction cannot fabricate information.
- `FR-025-011` Compatibility produces a dimensional verdict vector.
- `FR-025-012` Gluing preserves conflicts.
- `FR-025-013` Obstructions are durable.
- `FR-025-014` Obstructions can generate obligations.

**State/dynamics**
- `FR-025-015` StateVariable has explicit observability status.
- `FR-025-016` Hidden state is not serialized as observed fact.
- `FR-025-017` State estimation records residuals.
- `FR-025-018` Six authoritative time axes remain unchanged.
- `FR-025-019` Late events create new revisions.
- `FR-025-020` Regime is separate from change point.
- `FR-025-021` Transition is separate from causality.
- `FR-025-022` TDA output remains structural.

**Hypotheses**
- `FR-025-023` Hypotheses are first-class durable objects.
- `FR-025-024` Hypothesis identity has logical/revision levels.
- `FR-025-025` Support/refutation are separate vectors.
- `FR-025-026` Assumptions are explicit.
- `FR-025-027` Predictions are explicit.
- `FR-025-028` Discriminating tests are explicit.
- `FR-025-029` Competing hypotheses coexist.
- `FR-025-030` Historical hypothesis assessments remain queryable.

**Abduction/dialectics**
- `FR-025-031` Abduction is bounded.
- `FR-025-032` Candidate pruning is auditable.
- `FR-025-033` Complexity penalties are declared.
- `FR-025-034` Hypothesis diversity is preserved.
- `FR-025-035` Active hypotheses can produce counter-hypotheses.
- `FR-025-036` Differential predictions are persisted.
- `FR-025-037` Dialectical resolution can remain inconclusive.

**Contradictions**
- `FR-025-038` Contradictions are durable.
- `FR-025-039` Source independence is assessed explicitly.
- `FR-025-040` Contradictions do not delete either side.
- `FR-025-041` Contradictions can create obligations.

**Frontier**
- `FR-025-042` Research actions remain proposals until governance permits execution.
- `FR-025-043` Expected information gain is recorded.
- `FR-025-044` Realized information gain is recorded.
- `FR-025-045` Action utility is decomposable.
- `FR-025-046` Action repetition is controlled by ActionMemory.
- `FR-025-047` Saturation is multidimensional.
- `FR-025-048` Closure requires explicit criteria.
- `FR-025-049` Re-opening on contradiction is supported.

**Query/global search**
- `FR-025-050` Natural-language queries compile to a common AST.
- `FR-025-051` Deterministic grammar exists for supported queries.
- `FR-025-052` Optional LLM compilation is subordinate.
- `FR-025-053` Universal terms trigger completeness analysis.
- `FR-025-054` Open-world results expose coverage and blind spots.

**Execution**
- `FR-025-055` Every operator has a registered contract.
- `FR-025-056` Every operator has a method fingerprint.
- `FR-025-057` Every operator declares complexity/resource requirements.
- `FR-025-058` Every operator exposes an explanation trace.
- `FR-025-059` Every operator supports deterministic replay or explicitly declares why not.
- `FR-025-060` Adaptive operators are optional.

**Integrity**
- `FR-025-061` No LLM owns admission.
- `FR-025-062` No TDA result owns truth.
- `FR-025-063` No source count is treated as source independence.
- `FR-025-064` No unknown value is silently coerced to zero/false.
- `FR-025-065` No derived object is visible before durable commit.
- `FR-025-066` Every major derived result has reverse provenance.
- `FR-025-067` Resource exhaustion is explicit.
- `FR-025-068` Replay is fixed-point deterministic (per determinism class).

**Added in v2**
- `FR-025-069` Hypotheses live in an explicit HypothesisSpace; non-exhaustive spaces carry `H_OTHER` mass.
- `FR-025-070` All aggregation consumes evidence dependency groups; `n_eff` is reported.
- `FR-025-071` Negative findings exist only as coverage-qualified absences with declared detection power.
- `FR-025-072` Predictions have statuses and persisted outcomes that feed hypotheses, gain and calibration.
- `FR-025-073` Ranking is declared in the ReasoningProfile, non-multiplicative, tier-respecting, with exploration quota.
- `FR-025-074` Gluing checks triple coherence under budget and reports unchecked triples.
- `FR-025-075` Counter-hypotheses satisfy a reproducible material-difference test and steelman parity.
- `FR-025-076` Branches are isolated from the mainline.
- `FR-025-077` Analyst assertions/decisions are first-class, traced and visible beside model state.
- `FR-025-078` Numeric modes, quantization and derived seeds govern determinism.
- `FR-025-079` One sequencer per context; batch boundaries are recorded; replay uses them.
- `FR-025-080` Revisions are manifests of content-addressed artifacts with optimistic concurrency.
- `FR-025-081` Retention/erasure via crypto-shredding preserves integrity and yields explicit `REPLAY_DEGRADED`.
- `FR-025-082` Sensitive inference classes are gated by InferencePolicy.
- `FR-025-083` Operator caches are tenant-keyed and fail closed.
- `FR-025-084` Quantitative targets (§47.4) are ratified, measured and reported.
- `FR-025-085` Honesty-metric denominators are defined and implemented.
- `FR-025-086` Baseline estimator is interval constraint propagation with explicit residuals.
- `FR-025-087` Temporal relations use the full 13-relation disjunctive algebra.
- `FR-025-088` Truth-state operations satisfy the Belnap lattice laws; `BOTH` implies a Contradiction.

---

## Appendix U — Wave exit gates

- **Wave 0 — Architecture freeze.** All terms defined; all state machines fixed and reconciled with 024; identity and lineage boundaries fixed; ADR 01–12 accepted; §47.4 targets ratified; no 024 contradiction.
- **Wave 1 — Domain kernel.** All core objects exist; canonicalization (incl. numeric modes) passes property tests; truth algebra passes truth tables and lattice laws; ≥10 golden-corpus cases.
- **Wave 2 — Durable substrate.** Restart preserves state; append-only enforcement; historical lookup; sequencer + optimistic concurrency; artifact store and manifests.
- **Wave 2S — Vertical slice.** Slice-0 green in dev-lite and dev-full with replay of every intermediate artifact.
- **Wave 3 — Locality.** Bounded overlaps; conflicts survive gluing; obstructions queryable; triple coherence works and `GLUED` never returned with unchecked triples.
- **Wave 4 — Dynamics.** Worldline binding; late-event re-evaluation; regime and transition distinct; full Allen algebra; ICP estimator with residuals.
- **Wave 5 — Abduction.** Multiple explanations coexist; pruning explainable; predictions generated; `H_OTHER` handled; material-difference test reproducible.
- **Wave 6 — Dialectics.** Counter-hypothesis generation; differential tests; inconclusive cases remain open; parity audit.
- **Wave 7 — Frontier.** obligation → action → task route; action ranking explainable and tier-respecting; prediction outcomes feed hypotheses; saturation/closure durable.
- **Wave 8 — Scientific integration.** TDA bound to snapshot; causal evaluation staged; calibration durable from outcome cohorts.
- **Wave 9 — Query compiler.** Structured path works; NL adapter yields equivalent AST for golden cases; completeness mode explicit; inference policy enforced.
- **Wave 10 — UI.** Context state, hypothesis matrix (with `H_OTHER`, `n_eff`), analyst controls, branches inspectable; provenance clickable end-to-end.
- **Wave 11 — Hardening.** Resource budgets enforced; replay fixed-point; no silent truncation; no cross-tenant leakage (storage and cache); erasure drill passes; §47.4 targets measured.
- **Wave 12 — Acceptance.** Every gate in §54 and every FR in Appendix T green; Appendix Y complete.

---

## Appendix V — Anti-pattern catalogue

- **V.1 "Context = prompt."** Rejected: ephemeral, non-replayable.
- **V.2 "Context = graph neighbourhood."** Rejected: temporal, semantic and epistemic state missing.
- **V.3 "Context = vector embedding."** Rejected: no provenance, contradiction or truth state.
- **V.4 "Reasoning = LLM chain of thought."** Rejected as authoritative substrate.
- **V.5 "Abduction = choose highest score."** Rejected: hides alternatives and uncertainty.
- **V.6 "Contradiction = pick the better source."** Rejected; source weighting is a model, the contradiction remains.
- **V.7 "Global search = crawl everything available."** Rejected: effort does not establish completeness.
- **V.8 "Phase transition = sudden increase."** Rejected: regime-level change needs a declared method.
- **V.9 "Information gain = another relevance score."** Rejected unless labelled as a surrogate.
- **V.10 "Projection is truth."** Rejected: projections are rebuildable serving artifacts.
- **V.11 "N sources = N confirmations."** Rejected: dependency groups.
- **V.12 "Nothing found = doesn't exist."** Rejected: coverage-qualified absence only.
- **V.13 "Posteriors over the hypotheses I thought of."** Rejected: residual mass.
- **V.14 "Utility = product of factors."** Rejected: annihilation, unit mixing, division by zero.
- **V.15 "Pairwise OK = globally OK."** Rejected: triple coherence, honest claims.
- **V.16 "SQLite is close enough to PostgreSQL."** Rejected for persistence tests.

---

## Appendix W — Product-level result semantics

A user-facing answer generated from this engine is structurally capable of saying:

```text
ANSWER
  ├── observed facts
  ├── strongest current explanation (with score kind, target, calibration)
  ├── competing explanations (and unassigned "none of the above" mass)
  ├── contradictions
  ├── assumptions
  ├── unresolved gaps
  ├── coverage / completeness / qualified absences
  ├── independent-source count (n_eff) vs raw count
  ├── confidence/calibration
  ├── predicted consequences and outcomes so far
  ├── analyst overrides (if any)
  └── next best discriminating observations
```

The user need not know what a `ContextCell`, `RestrictionMap` or `ReasoningRun` is, but can drill into each one.

---

## Appendix X — Final architectural statement

The Context & Dialectical Reality Approximation Engine is not an "AI brain" attached to COGNITIVE. It is the mechanism that turns the existing evidence-first substrate into an active epistemic system:

```text
observations
    → context
    → structure
    → state
    → hypotheses (in explicit spaces)
    → competing explanations
    → predictions
    → discriminating observations
    → research actions
    → new observations
    → revised world approximation
```

Its deepest architectural commitment:

> **The system does not have to know the world in advance. It must be able to represent what it does not know, construct plausible explanations, expose why they compete, determine what evidence would discriminate them, acquire that evidence through governed capabilities, and revise its model without destroying its history.**

That is the implementation target for specification 025.

---

## Appendix Y — Traceability matrix (FR → tasks → tests → gate)

| FR | Tasks | Primary tests | Gate |
|---|---|---|---|
| 001 | T019, T032 | M.1 canonicalization; M.3 | A |
| 002 | T019 | M.1 id derivation | A |
| 003 | T031, T032 | M.2 old revision readable | A |
| 004 | T031, T137 | M.3 concurrent writers | A |
| 005 | T102 | M.3 historical lookup | A |
| 006 | T128, T136 | Replay benchmark | A, L |
| 007 | T001, T112 | M.3 observation→cell | B |
| 008 | T035 | M.1 scope intersection | B |
| 009 | T034, T129 | Locality corpus; I.1 overflow | B |
| 010 | T003, T036 | M.2 restriction | B |
| 011 | T004, T037, T038 | M.1; Locality corpus | B |
| 012 | T005, T040, T041 | M.2 contradiction preserves both sides | B |
| 013 | T014, T023, T039 | M.3 gluing→obstruction | B |
| 014 | T042 | M.3 obstruction→obligation | B, I |
| 015 | T006, T043 | M.1 | F |
| 016 | T007, T044 | M.2 unknown never false | F |
| 017 | T046, T045, T148 | Dynamics corpus | F |
| 018 | T047, T140 | Temporal corpus | F |
| 019 | T052, T122 | Temporal corpus (late event) | F |
| 020 | T049, T050 | Dynamics corpus | F |
| 021 | T051 | Dynamics corpus | F |
| 022 | T081, T124 | TDA corpus; N.4 | G |
| 023 | T008, T025 | M.3 | C |
| 024 | T008, T053 | M.1 id derivation | C |
| 025 | T056 | Abduction corpus | C |
| 026 | T009, T058 | Abduction corpus | C |
| 027 | T011, T060 | M.3 hypothesis→prediction | C |
| 028 | T012, T061 | M.3 prediction→test | C |
| 029 | T054, T059 | Abduction corpus | C, D |
| 030 | T025, T032 | M.2 | C |
| 031 | T054 | Resource-budget benchmark | D |
| 032 | T054, T059 | Abduction corpus; L.7 | D |
| 033 | T057, T139 | M.1 ranking | D |
| 034 | T059, T143 | Abduction corpus (near-duplicates) | D |
| 035 | T063 | Dialectical corpus | E |
| 036 | T065 | Dialectical corpus | E |
| 037 | T062, T066 | Dialectical corpus (unresolvable) | E |
| 038 | T013, T027, T068 | M.3; N.2 | C |
| 039 | T069, T130–T132 | N.3; independence corpus | O |
| 040 | T070 | M.2 | N |
| 041 | T071 | M.3 | I |
| 042 | T074, T075, T115 | E2E obligation→action | I |
| 043 | T072, T073 | IG corpus | I |
| 044 | T134 | IG corpus | I |
| 045 | T074, T139 | M.1 ranking; N.10 | I |
| 046 | T076 | Frontier tests | I |
| 047 | T017, T077, T132 | M.1 saturation | J |
| 048 | T078 | E2E closure | I |
| 049 | T079 | E2E reopen | I |
| 050 | T094, T096 | Global-query corpus | K |
| 051 | T095 | Global-query corpus | K |
| 052 | T096 | Adaptive-off E2E | L |
| 053 | T099 | Global-query corpus | J |
| 054 | T108, T117 | Global-query corpus | J |
| 055 | T087 | Registry tests | — |
| 056 | T086, T090 | Fingerprint tests | K |
| 057 | T089 | Registry tests | — |
| 058 | T090 | Explanation-trace tests | K |
| 059 | T092, T128 | Replay benchmark | L |
| 060 | T093, T096 | Adaptive-off E2E | L |
| 061 | T096, T146 | Adaptive-off E2E | L |
| 062 | T081 | TDA corpus | G |
| 063 | T130–T132 | N.3 | O |
| 064 | T020, T067 | M.2 unknown never false | F, N |
| 065 | T031, T137 | M.3 | A |
| 066 | T107 | Lineage audit L.1–L.8 | K |
| 067 | T018, T129 | Resource-budget benchmark | M |
| 068 | T128, T136 | Replay benchmark | L |
| 069 | T133 | N.7 | C |
| 070 | T130–T132 | N.3; M.2 duplicate never raises n_eff | O |
| 071 | T135 | N.8; absence corpus | O |
| 072 | T134, T083 | IG corpus; calibration tests | I |
| 073 | T139 | N.10; M.2 no cross-kind ranking | I |
| 074 | T141 | N.6; Locality corpus | B |
| 075 | T143, T063 | Dialectical corpus | E |
| 076 | T142 | N.11; M.2 branch isolation | P |
| 077 | T144 | N.9 | P |
| 078 | T136, T019 | Determinism benchmark (cross-platform) | L |
| 079 | T137 | M.3 concurrent writers; replay with recorded batches | A |
| 080 | T138, T137 | M.3 | A |
| 081 | T145 | Erasure drill; M.3 | Q |
| 082 | T146 | Sensitive-inference E2E | Q |
| 083 | T147 | Cross-tenant cache test | Q |
| 084 | T150 | §47.4 harness | M |
| 085 | T151 | Metric tests | M |
| 086 | T148 | Dynamics corpus | F |
| 087 | T140 | M.1 Allen tables; M.2 | F |
| 088 | T020, T149, T068 | M.1 truth tables; M.2 lattice laws | N |

CI check `T025-153` fails if any `FR-025-*` lacks a task and a test reference.

---

## Appendix Z — Change log v1 → v2

**Defects fixed**
- `OBS-` prefix collision (Obstruction vs Observation) → `OBST-`; missing prefixes declared (G.1).
- Lifecycle inconsistencies resolved: `REPLAYED` removed from revision status; `STRENGTHENED/WEAKENED` became derived `trend`; `RESOLVED`/`UNRESOLVED` reconciled; contradiction `UNKNOWN` removed; hypothesis transition table added; frontier readiness vs obligation lifecycle vs action state separated (§21.1, App. F); 024 declared authoritative.
- Overlap `compatibility_status` and assessment `verdict` share one vocabulary (`UNRESOLVED` instead of `UNKNOWN`).
- Score kinds unified with §14.3.
- Belnap algebra completed: corrected lattice diagrams, five operations, proposition-level attachment, link to Contradiction, separation from score with explicit `target` (§13).
- Allen algebra completed to 13 relations with disjunctive sets and composition (§24.2).
- Single normative definition of done (§54 + App. T + App. U), with traceability matrix (App. Y); phases/waves/task numbering reconciled and critical path updated.

**Conceptual additions**
- `HypothesisSpace` and `H_OTHER` (§15.3); general evidence dependency model (§14A); coverage-qualified absence (§13A); `PredictionOutcome` and calibration cohorts (§19.3, §14.4); non-multiplicative ranking, tiered gain, exploration, `ReasoningProfile` (§20.3–20.4); triple coherence (§10.2); material-difference and steelman parity (§17.7, §18.5); branches/scenarios (§6.4); analyst in the loop (§16A); `PHASE_TRANSITION_CANDIDATE` → `REGIME_SHIFT_CANDIDATE` (§25).

**Engineering additions**
- Determinism classes, numeric modes, derived seeds, canonical event order, single sequencer, recorded batches (§4); manifests, content-addressed artifacts, optimistic concurrency (§6, §39.4); retention/crypto-shredding/legal hold (§39.3); permissible-inference policy (§49.3); tenant-keyed caches (§30.5); PostgreSQL in dev-lite (§47.1, R.1); quantitative targets (§47.4); metric denominators (K.4); interval-constraint-propagation baseline estimator (§12.4); vertical slice and early corpus (§55–57).