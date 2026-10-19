# Data Model — Feature 033

**Feature**: `033-universal-context-runtime` | **Date**: 2026-10-19

The v2.0 runtime adds a **context layer** above the evidence and claim layer that Feature 032 owns.
This document defines that layer. It does not redefine evidence, claims, conflicts or projections —
those are referenced, not duplicated.

---

## 1. Layer map

```text
┌──────────────────────────────────────────────────────────────┐
│ Policy / decision model        authority, purpose, thresholds │  ← §15.2(5), §29
├──────────────────────────────────────────────────────────────┤
│ Context / process model        frame, revision, obligations,  │  ← §16, §18, §26
│                                actions, completion            │
├──────────────────────────────────────────────────────────────┤
│ Model / simulation space       assumptions, models, scenarios │  ← §17.2, §19.12
├──────────────────────────────────────────────────────────────┤
│ World / knowledge model        elements, relations, claims,   │  ← §16.3, §16.4
│                                entities, events               │
├──────────────────────────────────────────────────────────────┤
│ Evidence model                 raw artifacts, captures,       │  ← Feature 032
│                                observations, spans             │
└──────────────────────────────────────────────────────────────┘
```

**Invariant L1**: a hypothesis in the process model cannot be written into the knowledge model.
**Invariant L2**: a simulation artifact in the model space cannot be written into the evidence model.
**Invariant L3**: an authorisation in the policy model does not establish the truth of what it permitted.

---

## 2. `ContextFrame`

A versioned snapshot of *what is being understood*, referencing live data rather than copying it.

```text
ContextFrame
├── id, revision, parent_revision
├── tenant_id
├── purpose { goal, success_criteria[], deliverable_contract }
├── scope   { inclusions[], exclusions[], granularity, scope_revision }
├── perspective { observer_role, jurisdiction, ontology_view }
├── time    { mode, valid_interval, knowledge_cutoff, timezone }
├── epistemics { open_world, confidence_policy, unknowns_are_explicit }
├── assumptions[] · questions[] · hypotheses[] · obligations[]
├── resources { cost_budget, time_budget, compute_budget }
├── access    { policy_snapshot, data_classification }
├── provenance { created_by, created_at, source_request_digest }
└── state_digest
```

**Invariant F1**: `granularity` does not replace a typed scope model; a frame may carry several granularities for different questions.
**Invariant F2**: a revision is created only on a meaningful delta; a re-render is not a revision.
**Invariant F3**: a revision or branch always carries its parent; nothing is rewritten in place.

Full contract: [`contracts/context-frame.md`](./contracts/context-frame.md).

---

## 3. `ContextElement`

The open-typed envelope for any content.

```text
ContextElement
├── element_id
├── kind_uri                    open namespace, not a closed enum
├── schema_ref + schema_version
├── payload_ref | inline_small_payload
├── raw_form_ref?               the exact observed form, where meaningful
├── semantic_refs[]             zero or many mappings to concepts
├── relations[]                 typed, directed, optionally n-ary
├── time_scope                  valid time + knowledge time where meaningful
├── space_scope?                geometry/region/topology with CRS
├── epistemic_status
├── provenance_refs[]
├── abstraction_level_ref
├── perspective_refs[]
├── assumptions_refs[]
├── sensitivity/classification
├── lineage / supersedes
└── validation_status
```

**Invariant E1**: an invalid payload goes to quarantine with its decoding errors; it is not dropped.
**Invariant E2**: an unknown `kind_uri` is preserved as opaque and can be investigated after a schema is registered.
**Invariant E3**: a missing dimension is `unknown` or `not_applicable` — never a plausible default.

Full contract: [`contracts/context-element.md`](./contracts/context-element.md).

---

## 4. Relations and event frames

```text
RelationAssertion
├── relation_id
├── predicate_uri               open
├── participants[] { role, participant_ref }   ≥ 2, ordered by role
├── time_scope
├── evidence_spans[]
├── epistemic_status
├── ontology_pack_ref
└── lineage

EventFrame
├── event_id
├── event_type_uri              open
├── participants[] { role, participant_ref }
├── time_scope { occurred_at | interval, precision, timezone }
├── place_ref?
├── evidence_spans[]
└── epistemic_status
```

**Invariant R1**: a role-bearing relation is reified, not flattened into a triple.
**Invariant R2**: projection to graph edges is a view, not the storage.
**Invariant R3**: every participant has a role label; `participant_1` is not a role.

---

## 5. Dimensions (all fifteen)

| Dimension | Values | What must never be lost |
|---|---|---|
| Content | text, code, table, signal, image, video, document, event, graph, model | original form and exact locator |
| Semantics | concept, type, predicate, role, unit, schema, ontology, free term | original term and mapping version |
| Abstraction | atom, feature, fact, object, event, process, system, model, theory, goal | transition and aggregation rule |
| Time | event, valid, source, capture, knowledge, processing | precision, timezone, unknown |
| Space | coordinates, address, region, topology, virtual | CRS, error, resolution |
| Causality | association, mechanism, hypothesis, intervention, counterfactual | assumptions and confounders |
| Epistemics | observation, claim, inference, hypothesis, refutation, contradiction, absence | justification type and independence |
| Modality | asserted, possible, necessary, permitted, forbidden, scenario | fact vs possibility vs norm |
| Perspective | source, user, organisation, jurisdiction, model, observer | who asserts, in what sense, with what rights |
| Social structure | actor, role, group, authority, obligation, contract, conflict of interest | role validity and basis |
| Computational model | language, type system, program, state, dependency, trace | runtime/model/config and reproducibility |
| Normative model | rule, constraint, permission, prohibition, standard, clause | version and applicability |
| Uncertainty | interval, probabilistic, epistemic, aleatoric, model, conflict | the distinct sources are not merged into one confidence |
| Provenance | direct source, derivation chain, lineage root, operator run | independence and repeatability |
| Goal/value | question, criterion, utility, risk, action cost | whose preferences and which constraints |

**Invariant D1**: `unknown` and `not_applicable` are distinct everywhere.
**Invariant D2**: two uncertainty sources are never averaged into one number.

---

## 6. Abstraction

```text
AbstractionManifest
├── inputs { ids[], digests[], included_scope }
├── rule_or_model { ref, version, parameters_digest }
├── omitted { fields[], fragments[], exception_counts_by_class }
├── support { supporting_cases[], contradicting_cases[] }
├── applicability { range, conditions }
├── staleness { becomes_stale_when[] }
├── drill_down { route, resolvable }
└── output { digest, artifact_ref }
```

**Invariant A1**: every upward step has a manifest.
**Invariant A2**: `drill_down.resolvable` must be true for a manifest to be accepted in a report.
**Invariant A3**: a summary or embedding is never the only surviving representation.

Full contract: [`contracts/abstraction-manifest.md`](./contracts/abstraction-manifest.md).

---

## 7. Capability and permission

```text
CapabilityManifest
├── id, version
├── input_schema, output_schema
├── accepts[], emits[]
├── preconditions[]
├── constraints { deterministic, network_access, max_payload, languages }
├── quality { eval_suite, minimum_gate }
├── execution { runtime, timeout, retry_policy }
├── governance { owner, license_ref, model_data_manifest, enabled_by_default }
├── observability { metrics[] }
└── permission_class ∈ {READ, DERIVE, PROPOSE, DECIDE, WRITE_EXTERNAL, ADMIN}

OperatorRequest
├── typed input refs
├── context snapshot + revision
├── effective policy
├── budget + deadline
├── idempotency key
└── requested output contract

OperatorResult
├── status, typed outputs, provenance
├── input and output digests
├── operator/runtime/model versions
├── warnings, coverage, resource costs
├── emitted candidates
└── continuation/checkpoint ref
```

**Invariant C1**: one plugin, one permission class — never a bundle "because it needs one of them".
**Invariant C2**: `WRITE_EXTERNAL` is off by default and requires grant, confirmation and idempotency.
**Invariant C3**: an operator call carries no ambient write privilege.

Full contract: [`contracts/capability-manifest.md`](./contracts/capability-manifest.md).

---

## 8. Context assembly

```text
ContextAssemblyManifest
├── question + output_schema
├── included[] { ref, kind, reason_included }
├── excluded[] { ref, reason ∈ {irrelevant, duplicate, inaccessible, over_budget, stale} }
├── revisions { context, ontology, policy, time_cut }
├── summary_links[] { summary_ref, source_refs[] }
├── abstraction_manifests[]
├── budget { tokens, bytes, rows } + pruning_decisions[]
├── must_not_omit { unresolved_conflicts[], unknowns[] }
├── privacy_filters[] + redactions[]
├── assembly_digest
└── renderer_version
```

**Invariant M1**: every included and excluded item has a reason.
**Invariant M2**: an unresolved conflict is included or its exclusion is surfaced on the answer.
**Invariant M3**: an answer cites the assembly digest.

Full contract: [`contracts/context-assembly-manifest.md`](./contracts/context-assembly-manifest.md).

---

## 9. Memory layers

| Layer | Scope | Retention | Must never do |
|---|---|---|---|
| Conversation state | one conversation | session + configured window | outlive its conversation silently |
| Working set | one step | rebuilt per operation | hide the full-context reference |
| Task/process | one context | until the context closes | be treated as findings |
| Case/project | one case | case retention policy | cross cases without access |
| Entity/worldline | the entity | entity retention + legal hold | be edited by hand |
| Procedural | the capability | versioned, reviewed | be silently rewritten by an agent |
| Semantic/episodic index | the tenant | rebuildable | become canonical truth |
| Preference | the user | user-controlled | appear as evidence |
| Institutional | the organisation | owned, dated | persist past its validity unmarked |

**Invariant M4**: each layer has its own scope, retention, permission, correction and expiry.
**Invariant M5**: no blanket "remember forever".
**Invariant M6**: a summary remembers what it omitted and links to the sources.

Full contract: [`contracts/memory-layers.md`](./contracts/memory-layers.md).

---

## 10. Completion

```text
CompletionReport
├── context_id + final_revision
├── completion_status + reason_code
├── criteria_satisfied[] / criteria_not_satisfied[]
├── obligations_satisfied[] / residual_obligations[]
├── executed_scope / unexecuted_scope / excluded_scope
├── sources_attempted / sources_unavailable / unsupported_capabilities
├── evidence_coverage_and_known_selection_bias
├── conflicts_open / hypotheses_unresolved
├── budgets_consumed / reason_for_stopping
├── reproducibility_manifest / policy_version
└── reopen_conditions[] / next_best_actions[]
```

**Invariant N1**: every terminal state emits one.
**Invariant N2**: `COMPLETE_WITH_LIMITATIONS` is valid.
**Invariant N3**: open questions are never hidden to present a clean answer.

Full contract: [`contracts/completion-report.md`](./contracts/completion-report.md).

---

## 11. What is deliberately open

| Open by design | Closed for the platform |
|---|---|
| `kind_uri` namespaces | context lifecycle states |
| entity types and relation predicates | obligation states |
| schema versions per domain pack | conflict statuses |
| context kinds beyond the sixteen starters | capability lifecycle statuses |
| reasoning-mode providers | permission classes |
| optional backends | completion statuses |

The rule from the contract layer applies: closed for our workflow states, open for the world.
