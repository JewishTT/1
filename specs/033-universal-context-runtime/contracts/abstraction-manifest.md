# Contract 03 — `AbstractionManifest`

**Feature**: `033-universal-context-runtime`
**Governs**: accountability for every step from detail to abstraction.
**Enforces**: FR-010…FR-014; blueprint §17.2, §17.3.

---

## Why this contract exists

Every upward step loses information. That is not a defect — it is what abstraction *is*. The defect
is losing information **silently**, so that a summary is later treated as if it had been the whole
record.

The blueprint's rule is exact: *"Любой переход от детального уровня к абстрактному теряет
информацию."* The manifest is the record of what was lost, what was kept, what contradicts it, and
how to get back.

---

## Shape

```text
AbstractionManifest
├── operation                 REQUIRED   the §17.2 operator that ran
├── operation_version         REQUIRED
├── inputs
│   ├── input_ids[]           REQUIRED
│   ├── input_digests[]       REQUIRED
│   └── included_scope        REQUIRED   what was in scope for this step
├── rule_or_model
│   ├── ref                   REQUIRED   rule id, model id or operator id
│   ├── version               REQUIRED
│   └── parameters_digest     OPTIONAL
├── omitted
│   ├── fields[]              REQUIRED   may be empty; the field is not
│   ├── fragments[]           REQUIRED   may be empty
│   ├── exception_counts      REQUIRED   by class
│   └── excluded_scope        REQUIRED
├── support
│   ├── supporting_cases[]    REQUIRED
│   └── contradicting_cases[] REQUIRED   may be empty; presence is mandatory
├── applicability
│   ├── range                 REQUIRED
│   └── conditions[]          REQUIRED
├── staleness
│   └── becomes_stale_when[]  REQUIRED
├── drill_down
│   ├── route                 REQUIRED
│   └── resolvable            REQUIRED   must be true to be accepted in a report
└── output
    ├── digest                REQUIRED
    └── artifact_ref          REQUIRED
```

---

## The twenty-two operators (§17.2)

Each has a mandatory record beyond the common manifest:

| Operator | Extra mandatory record |
|---|---|
| `DECOMPOSE` | decomposition criterion, coverage, excluded parts |
| `AGGREGATE` | aggregation window, denominator, weighting, omitted records |
| `ABSTRACT` | commonality rule, counterexamples, abstraction loss |
| `INSTANTIATE` | assumptions, unverified instantiated slots |
| `GENERALIZE` | population/scope, exceptions, validation set |
| `SPECIALIZE` | constraint, ontology revision |
| `PROJECT` | projection schema, omitted dimensions, freshness |
| `LIFT_RELATION` | mapping path, preservation conditions |
| `COMPOSE` | interface compatibility, inter-model assumptions |
| `DECOMPOSE_CAUSALLY` | causal graph version, identification limits |
| `ANALOGIZE` | source/target mapping, matched invariants, mismatch set |
| `CONCRETIZE` | operational definition, measurement assumptions |
| `TEMPORALIZE` | clock semantics, event ordering policy |
| `SPATIALIZE` | CRS, precision, projection assumptions |
| `MODEL` | variables, equations/rules, assumptions, validation evidence |
| `SIMULATE` | random seeds, versioned parameters, reproducibility mode |
| `COUNTERFACTUAL` | intervention variable, identification assumptions, affected outputs |
| `COMPARE` | alignment map, incomparable fields |
| `RECONCILE` | mapping table, losses, conflicts, approval |
| `EXPLAIN` | premises, rules/operators, evidence links, uncertainty |
| `REFUTE` | falsification criteria, searched scope, disconfirming evidence |
| `BOUND` | assumptions, missingness model, validity conditions |

---

## Normative rules

### R1 — A manifest is mandatory

An operator that produces an abstraction without a manifest has not produced an acceptable artifact.
This applies to summaries, embeddings, models, analogies and every other upward step — not only to
"analysis".

### R2 — Omission is recorded, not implied

`fields`, `fragments`, `exception_counts` and `excluded_scope` are explicit. "Some details were
summarised" is not a record.

### R3 — Contradictions are carried

`contradicting_cases[]` is present even when empty. A summary that omits its counterexamples is
misleading by construction.

### R4 — Drill-down must resolve

`drill_down.resolvable: true` is required for the manifest to be accepted in a report. If the route
cannot be executed, the abstraction is a dead end and is reported as such.

### R5 — Staleness has conditions

An abstraction becomes stale when its inputs change, its ontology changes or its model version
changes. Those conditions are named, so a consumer can check them.

### R6 — Outcomes are four

Every abstraction operator returns `success`, `partial`, `unsupported/blocked` or `no_change`. There
is no fifth "probably fine".

### R7 — Inputs are never rewritten

An abstraction creates a new derived artifact and leaves the input untouched. A summary that mutates
its source is not an abstraction; it is a rewrite.

### R8 — Summaries are not the only surviving form

`output.artifact_ref` exists alongside the source artifacts. Replacing a source with its summary is a
contract violation.

---

## Prohibitions

- A summary with no manifest.
- A manifest whose `drill_down.resolvable` is false and which is nonetheless cited in a report.
- An abstraction that rewrites its inputs.
- A model-space artifact entering the observed-claim store.
- A "confidence" replacing the assumption and omission record.

---

## Tests

| Test | Asserts |
|---|---|
| `tests/contract/test_abstraction_manifest.py::test_manifest_required` | R1 |
| `tests/golden/test_summary_drill_down.py` | R4, R8 |
| `tests/golden/test_abstraction_counterexamples.py` | R3 |
| `tests/golden/test_simulation_not_observation.py` | R7, prohibition 4 |
| `tests/contract/test_abstraction_manifest.py::test_four_outcomes` | R6 |
