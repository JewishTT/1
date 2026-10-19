# Contract 05 — `ConflictRecord`

**Feature**: `032-global-upgrade-execution`
**Governs**: how a detected incompatibility between claims is represented, tracked and closed.
**Enforces**: FR-029, FR-030, FR-031, FR-032; blueprint §6.

---

## Why this contract exists

The blueprint is emphatic that a conflict is not a low score and not a display problem (§6.1): *"Он
не равен `low_confidence` и не всегда означает, что один source ошибается."*

A `ConflictRecord` is therefore a durable object with its own lifecycle, its own evidence on both
sides, and an explicit account of why it opened and why it closed. It is created only after
comparability has been established, and it is never deleted — a resolved conflict is a resolved
conflict, not an absent one.

---

## Shape

```text
ConflictRecord
├── identity
│   ├── conflict_id                REQUIRED
│   ├── tenant_id                  REQUIRED
│   ├── context_id                 OPTIONAL   present when the conflict is investigation-scoped
│   └── entity_or_candidate_refs[] REQUIRED   at least two parties
├── classification
│   ├── conflict_kind              REQUIRED   value | type | relation | temporal |
│   │                                          logical | identity | provenance | scope
│   ├── severity                   REQUIRED   impact on the investigation's decisions
│   └── status                     REQUIRED   see the lifecycle below
├── sides
│   ├── claim_refs_supporting_each_side[]  REQUIRED   at least two non-empty sides
│   ├── evidence_dependency_groups[]       REQUIRED   which claims share an upstream root
│   └── dimension_vectors                  REQUIRED   temporal / provenance / semantic /
│                                                     identity / source_quality, each separate
├── semantics
│   ├── ontology_pack_ref          REQUIRED
│   ├── compatibility_rule_id      REQUIRED   the rule that makes these incompatible
│   ├── compatibility_rule_version REQUIRED
│   ├── valid_time_overlap         REQUIRED   including "none" as a positive value
│   ├── known_time                 REQUIRED   when the platform came to know both sides
│   └── scope_ref                  REQUIRED
├── detection
│   ├── detection_operator         REQUIRED
│   ├── detection_version          REQUIRED
│   └── detection_parameters_digest REQUIRED
├── resolution trail
│   ├── resolution_criteria        REQUIRED   what would settle this
│   ├── proposal_refs[]            OPTIONAL
│   ├── decision_refs[]            OPTIONAL
│   ├── opened_from_revision       REQUIRED
│   └── current_revision           REQUIRED
└── lineage
    ├── supersedes                 OPTIONAL
    └── refers_to[]                OPTIONAL
```

---

## Status lifecycle

```text
OPEN ──> INVESTIGATING ──> PROVISIONALLY_RESOLVED ──> ADJUDICATED
  │            │                     │                    │
  │            │                     └──────> REOPENED <──┘
  │            └──> NOT_A_CONFLICT
  └──> NOT_A_CONFLICT
```

Every transition is stored with its reason, its actor and its timestamp. A `NOT_A_CONFLICT`
transition must state **what was established** — temporal non-overlap, different scope, different
units, non-exclusive predicates, duplicate or syndicated evidence, or another named finding. "It
turned out not to be one" is not a reason.

---

## Normative rules

### R1 — Comparability precedes the conflict

A record may only be created after the §6.2 pre-check has run and its result is stored: participants
and identity revision, predicate mapping and ontology version, units/currency/period/jurisdiction,
valid-time intersection, timestamp precision, source and capture/publication/event times, dependency
root, and predicate exclusivity.

### R2 — Sides are non-empty and independent

At least two sides, each with at least one claim. Where two sides trace to one lineage root, the
record states that they are not independent corroboration — it does not count them as two.

### R3 — The dimension vectors stay separate

Temporal, provenance, semantic, identity and source-quality dimensions are never collapsed into one
number. Their separateness is what lets a resolver say *"the same claim, from two dependent sources,
under a different unit"* rather than *"conflict, 0.61"*.

### R4 — Resolution never deletes a side

A `PROVISIONALLY_RESOLVED` or `ADJUDICATED` conflict keeps both sides queryable. The winning value is
a view decision, not a storage decision (§6.5).

### R5 — Abstention is a valid terminal state

When evidence cannot honestly settle the conflict, the resolver abstains, the conflict keeps `BOTH`,
and a discriminating-evidence obligation opens. The conflict status records the abstention and its
reason.

### R6 — Four-valued support is mandatory

Each claim carries independent `support_positive[]` and `support_negative[]`. The derived state is
`NEITHER`, `TRUE_ONLY`, `FALSE_ONLY` or `BOTH`. `BOTH` is a real state; it is not a confidence
threshold and it is not "unresolved therefore false".

### R7 — Silence is not negative support

A source that did not mention a fact contributes nothing to `support_negative[]`. Only evidence that
actually bears against the claim does.

### R8 — Reopening is first-class

A resolved conflict can reopen on new evidence, an ontology change or an analyst decision. Reopening
creates a new revision; it does not overwrite the resolution.

---

## Prohibitions

- Creating a conflict before comparability is checked.
- Representing a conflict as `confidence < threshold`.
- Deleting the losing side.
- Counting syndicated copies as independent votes.
- Ordering by `captured_at` and calling it "most recent truth".
- Closing a conflict without a stated reason, including a `NOT_A_CONFLICT` closure.

---

## Tests

| Test | Asserts |
|---|---|
| `tests/golden/conflict_corpus/test_value_conflict.py` | R1, R2 |
| `tests/golden/conflict_corpus/test_temporal_transition_not_conflict.py` | R1, status `NOT_A_CONFLICT` |
| `tests/golden/conflict_corpus/test_syndicated_duplicates.py` | R2, R8 |
| `tests/golden/conflict_corpus/test_both_preserved.py` | R4, R6 |
| `tests/contract/test_conflict_record.py::test_every_status_transition_has_reason` | lifecycle |
