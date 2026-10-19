# Contract 01 — `ContextFrame`

**Feature**: `033-universal-context-runtime`
**Governs**: the versioned snapshot of what an investigation is trying to understand.
**Enforces**: FR-003, FR-004, FR-005, FR-009; blueprint §16.1.

---

## Why this contract exists

A `ContextFrame` is not a prompt and not a graph. It is the **task-understanding snapshot**: what is
being asked, under which scope, from which perspective, with which time semantics, which
assumptions, which open questions, which resources and which policy.

The blueprint is explicit that it *references* live data rather than copying it (§16.1), and that
its fields are illustrative but its discipline is not: stable typed ids, schema version, canonical
serialisation, validation and a compatibility policy.

The frame is what makes an investigation reproducible. Without it, "the system looked into X" cannot
be re-run, compared or audited.

---

## Shape

```text
ContextFrame
├── id                        REQUIRED   stable
├── revision                  REQUIRED   monotonic per id
├── parent_revision           REQUIRED   null only for the first
├── tenant_id                 REQUIRED
├── purpose
│   ├── goal                  REQUIRED   the question, in the requester's terms
│   ├── success_criteria[]    REQUIRED   machine-evaluable where possible
│   └── deliverable_contract  REQUIRED   what the output must be
├── scope
│   ├── inclusions[]          REQUIRED   typed subject/time/geography refs
│   ├── exclusions[]          OPTIONAL   typed, explicit
│   ├── granularity           OPTIONAL   may vary per question
│   └── scope_revision        REQUIRED
├── perspective
│   ├── observer_role         REQUIRED
│   ├── jurisdiction          REQUIRED   a policy ref, not a string
│   └── ontology_view         REQUIRED   an ontology pack revision
├── time
│   ├── mode                  REQUIRED   current | as_of | interval
│   ├── valid_interval        CONDITIONAL required for interval
│   ├── knowledge_cutoff      CONDITIONAL required for as_of
│   └── timezone              REQUIRED
├── epistemics
│   ├── open_world            REQUIRED   always true in v2
│   ├── confidence_policy     REQUIRED   a policy ref
│   └── unknowns_are_explicit REQUIRED   always true
├── assumptions[]             REQUIRED   may be empty; the field is not
├── questions[]               REQUIRED
├── hypotheses[]              OPTIONAL
├── obligations[]             REQUIRED
├── resources
│   ├── cost_budget           REQUIRED
│   ├── time_budget           REQUIRED
│   └── compute_budget        OPTIONAL
├── access
│   ├── policy_snapshot       REQUIRED
│   └── data_classification   REQUIRED
├── provenance
│   ├── created_by            REQUIRED
│   ├── created_at            REQUIRED
│   └── source_request_digest REQUIRED
└── state_digest              REQUIRED
```

---

## Normative rules

### R1 — Reference, do not copy

The frame points at subjects, scopes, ontology revisions and policy snapshots by id and revision. It
does not embed the objects. An embedded copy becomes a second truth the moment the original changes.

### R2 — Revisions are appended

A change of intent or scope produces a new revision with `parent_revision`. The previous revision
remains readable and is never reinterpreted. A rebase is an explicit new revision, not a silent edit
(§9.1, FR-009).

### R3 — A revision means a meaningful delta

Re-rendering, re-ordering or a transient status change is not a revision. The revision manager
applies the delta classes of §18.1(5): new evidence, ontology change, policy change, user
correction, projection drift, time advance.

### R4 — Granularity is not scope

A single frame may need event-level granularity for one question and system-level for another. The
typed scope model carries both; one `granularity` field does not replace it.

### R5 — Time mode is explicit

`current`, `as_of` and `interval` are different questions. A frame declares one, and a query that
needs another is a different frame or an explicit second query — not an implicit reinterpretation.

### R6 — The digest is deterministic

`state_digest` is computed over canonical serialisation with deterministic key ordering. Two frames
with identical semantic content have identical digests; a cosmetic difference does not change it.

### R7 — The frame carries its budget

Cost, time and compute budgets are set at compile time and enforced downstream. A frame without a
budget is a frame that can run forever.

### R8 — Assumptions are visible

An assumption made during compilation is recorded in the frame. A hidden assumption is a silent
interpretation, which §22.1 forbids.

---

## Prohibitions

- A frame that embeds its subject objects rather than referencing them.
- A revision without a parent.
- A collection of frames edited in place to look like revisions.
- A frame with `open_world: false`.
- A frame whose time mode is implied rather than declared.
- A frame whose assumptions array is absent rather than empty.

---

## Tests

| Test | Asserts |
|---|---|
| `tests/contract/test_context_frame.py::test_digest_deterministic` | R6 |
| `tests/integration/test_context_revision_not_in_place.py` | R2, R3 |
| `tests/contract/test_context_frame.py::test_scope_granularity_multi` | R4 |
| `tests/integration/test_frame_time_mode_explicit.py` | R5 |
