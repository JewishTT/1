# Data Model — Feature 032

**Feature**: `032-global-upgrade-execution` | **Date**: 2026-10-19

This is the entity model the programme must converge on, expressed as **contracts and invariants**
rather than tables. Physical schema is a WP2/WP4 deliverable; what is fixed here is what each object
means, which store owns it, and which invariants may never be violated.

A table name in this document is a *pointer to the canonical owner*, not a proposed migration.

---

## 1. Ownership map

| Entity | Canonical owner | Store | Explicitly not owned by |
|---|---|---|---|
| Raw artifact bytes | ArtifactSink | S3/MinIO, content-addressed | any executor, any projection |
| Capture | Observation Gate | PostgreSQL | interpretation, projection |
| Observation + locator | Observation Gate | PostgreSQL | interpretation, projection |
| Canonical event | outbox → broker | PostgreSQL outbox, broker as transport | projections, consumers |
| Derived artifact (parse, extract, normalize) | interpretation | PostgreSQL metadata + object store payload | the raw artifact it derives from |
| Evidence span | the producing operator, validated by the contract layer | PostgreSQL | display layer, projections |
| Entity reference | identity resolution | PostgreSQL | admission, projections |
| Resolution candidate | identity resolution | PostgreSQL | admission |
| Resolution decision | admission | PostgreSQL, append-only | resolvers, projections, UI |
| Entity invariant / worldline revision | invariant reducer | PostgreSQL | identity resolution, projections |
| Claim | claim ingestion (admission path) | PostgreSQL, append-only | projections, conflict engine |
| Support (positive/negative) | claim ingestion | PostgreSQL | resolvers |
| Conflict record | conflict engine | PostgreSQL | resolvers (which only propose) |
| Resolution proposal | conflict resolver / identity resolver | PostgreSQL | admission |
| Ontology pack revision | ontology registry | PostgreSQL | operators (which reference it) |
| Context definition | context kernel | PostgreSQL, immutable | operators |
| Investigation context / revision | context kernel | PostgreSQL | acquisition |
| Research obligation | obligation evaluator | PostgreSQL | acquisition planner |
| Acquisition task | frontier | PostgreSQL | executors |
| Projection | projection fabric | its serving store | canonical stream, any other projection |
| Projection manifest | projection fabric | PostgreSQL | the projection itself |
| Donor registry entry | governance | repository file `donors/registry.yaml` | runtime |
| Capability manifest | capability registry | PostgreSQL + repo definitions | operators |
| Stop report / completion report | stopping engine | PostgreSQL | the caller |
| Audit event | governance | append-only table | everything else |

**Invariant O1**: every field has exactly one owner. A second writer is a defect with a WP reference,
not a tolerated reality.

---

## 2. Core relationships

```text
AcquisitionTask ──1:N──> Attempt ──1:1──> Publication
                                           │
                                           ├──> Capture (1) ──1:N──> Observation
                                           │                              │
                                           │                              └──> Locator
                                           └──> CanonicalEvent (outbox)

Observation ──1:N──> DerivedArtifact ──1:N──> Candidate ──1:1──> EvidenceSpanRef
                                                    │
                                                    v
                                              (mention | entity_ref |
                                               relation_candidate | claim_candidate)

Claim ──N:M──> Support (positive | negative)
Claim ──N:M──> ConflictRecord
ConflictRecord ──1:N──> ResolutionProposal ──1:N──> ResolutionDecision

EntityReference ──N:M──> ResolutionCandidate ──0:N──> ResolutionDecision
EntityInvariant ──1:N──> Revision ──1:N──> WorldlineSlice

OntologyPackRevision ──referenced by──> OperatorRun
ContextDefinition ──1:N──> ContextRevision ──0:N──> ContextBranch
ContextRevision ──1:N──> ResearchObligation ──1:N──> AcquisitionTask
ResearchObligation ──1:1──> CompletionReport (per terminal state)
```

**Invariant R1**: a `ResolutionDecision` always cites at least one `ResolutionProposal`.
**Invariant R2**: a `ConflictRecord` always has at least two non-empty sides.
**Invariant R3**: an `Observation` always has a `Capture`, a typed `Locator` and a resolvable `raw_ref`.
**Invariant R4**: a `Claim` is immutable after admission; correction is a new claim with `supersedes`.
**Invariant R5**: every `Projection` has exactly one `ProjectionManifest`.

---

## 3. Identity, digest, event and revision — four different things

The most expensive confusion in an evidence system is treating these as one field.

| Concept | Derived from | Changes when | Stable across |
|---|---|---|---|
| **Logical identity** (`entity_id`, `claim_id`) | admission decision | never; it is assigned | rebuilds, replays, restores |
| **Content digest** (`blob_digest`, `output_digest`) | canonical content bytes | the content changes | renames, timestamps, worker state |
| **Event identity** (`event_id`) | the producing transaction | never for one event | consumer restarts |
| **Revision sequence** (`revision`) | the ordered canonical stream | a canonical change appends | process restarts |

**Invariant I1**: `entity_id` is never computed from a similarity score or a single attribute.
**Invariant I2**: a digest never includes wall-clock time, arrival order or mutable diagnostics.
**Invariant I3**: a redelivery reuses the event's idempotency key and produces no new revision.
**Invariant I4**: a revision number is monotonic per object and never reused.

---

## 4. Temporal model

Every temporal value is one of the named clocks, and `unknown` is a value — never `now()`.

```text
TemporalScope
├── source_published_at      when the source says it published
├── source_valid_from        start of the period the claim speaks about
├── source_valid_until       end of that period
├── source_observed_at       when the source says the event occurred
├── captured_at / fetched_at when the platform received the bytes
├── recorded_at / known_at   when the data entered canonical knowledge
├── processed_at             when this operator run touched it
└── projected_at             when the projection caught up
```

**Invariant T1**: `known_at` is never backdated to `source_valid_from`.
**Invariant T2**: `AS_OF(t)` for `t` before a capture is unaffected by that capture.
**Invariant T3**: no causal conclusion follows from temporal precedence alone.
**Invariant T4**: a lifecycle event is rendered only when a source-backed claim exists for it.

---

## 5. Epistemic model

```text
SupportSet
├── support_positive[]   claim refs + spans + independence group
└── support_negative[]   claim refs + spans + independence group

EpistemicState = NEITHER | TRUE_ONLY | FALSE_ONLY | BOTH
```

**Invariant E1**: `support_negative` is populated only by evidence that bears against the claim;
silence contributes nothing.
**Invariant E2**: `BOTH` is a state, not a threshold.
**Invariant E3**: the four states survive storage, events, API, export and UI unchanged.
**Invariant E4**: a numeric confidence, if present, never replaces the four-valued state.

---

## 6. Conflict and resolution

```text
ConflictRecord
├── kind ∈ {value,type,relation,temporal,logical,identity,provenance,scope}
├── status ∈ {OPEN,INVESTIGATING,PROVISIONALLY_RESOLVED,ADJUDICATED,REOPENED,NOT_A_CONFLICT}
├── sides[] ≥ 2
├── dependency_groups[]
├── dimension_vectors { temporal, provenance, semantic, identity, source_quality }
└── transitions[] (status, reason, actor, at)
```

**Invariant C1**: no conflict is created before the comparability pre-check runs and its result is stored.
**Invariant C2**: resolution never removes a side.
**Invariant C3**: `NOT_A_CONFLICT` records what was established.
**Invariant C4**: abstention keeps `BOTH` and opens a discriminating-evidence obligation.

---

## 7. Research state

```text
ContextDefinition (immutable, versioned)
  objective · intent_ast · scope · time_mode · source_universe ·
  ontology_profile · output_requirements · budgets · access_policy ·
  freshness · quality · stop_conditions

InvestigationContext (durable, revisioned)
  active_revision · hypotheses · obligations · unknowns · contradictions ·
  attempted_actions · findings · cost · coverage · blockers · stop_condition

ResearchObligation
  trigger · parent(gap|hypothesis|conflict) · required_outcome ·
  acceptance_predicates[] · coverage_assumptions · capability_requirements[] ·
  unknown_dependencies[] · priority_vector · cost_estimate · attempts[] ·
  marginal_gain · stop_rules

AcquisitionTask
  (see contracts/acquisition-task.md)

CompletionReport
  context_id · final_revision · status · reason_code ·
  criteria_satisfied[] / criteria_not_satisfied[] ·
  obligations_satisfied[] / residual_obligations[] ·
  executed_scope / unexecuted_scope / excluded_scope ·
  sources_attempted / sources_unavailable / unsupported_capabilities ·
  coverage_and_selection_bias · conflicts_open · hypotheses_unresolved ·
  budgets_consumed · reason_for_stopping · reproducibility_manifest ·
  policy_version · reopen_conditions[] · next_best_actions[]
```

**Invariant S1**: an obligation closes only on evaluated acceptance predicates with evidence.
**Invariant S2**: every terminal state emits a `CompletionReport`.
**Invariant S3**: `queue_empty` is not a stop condition.
**Invariant S4**: a `ContextDefinition` revision is never mutated; a change is a new revision or branch.

---

## 8. Projection

```text
ProjectionManifest
  projection_id · tenant_scope · kind · source_cut · input_digests[] · offsets ·
  builder_version · operator_versions[] · built_at · duration ·
  output_digest · output_location · staleness{lag,within_slo,reason} ·
  status · last_successful_build · rebuild_route · kill_switch · owner
```

**Invariant P1**: a projection never writes into the canonical stream.
**Invariant P2**: rebuild from the declared cut reproduces `output_digest`.
**Invariant P3**: a stale projection cannot satisfy an obligation without a recorded acceptance.
**Invariant P4**: every production projection has exactly one builder.

---

## 9. Donor and capability

```text
DonorRegistryEntry      (see contracts/donor-registry.md)
CapabilityManifest
  id · version · input_schema · output_schema · accepts[] · emits[] ·
  preconditions[] · constraints{deterministic,network,payload,limitations} ·
  quality{eval_suite,minimum_gate} · execution{runtime,timeout,retry_policy} ·
  governance{owner,license_ref,assets_ref,enabled_by_default} ·
  observability{metrics[]} · permission_class
```

**Invariant D1**: a capability with `permission_class: DERIVE` cannot hold a canonical write handle.
**Invariant D2**: a donor at `WIRED` without `E2E_PROVEN` is not `LIVE_PROVEN`.
**Invariant D3**: disabling a donor preserves all raw and derived evidence.

---

## 10. What this model deliberately does not fix

- **Physical table layout.** WP2/WP4 decide it against the existing schema; the blueprint forbids a
  parallel canonical store, so every new table names its existing owner or replaces one.
- **A closed enumeration of entity types, predicates or context kinds.** Those are open-world by
  construction; only the platform's own workflow states are closed.
- **A confidence scale.** Numeric confidence may exist for ranking; it is not part of the epistemic
  model, which is four-valued and evidence-based.
- **A graph or vector schema.** Those are projections and their schema follows the benchmark in WP9
  and the ADR in WP1.
