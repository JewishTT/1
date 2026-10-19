# Contract 02 — `ContextElement` and Relations

**Feature**: `033-universal-context-runtime`
**Governs**: how any content — known or unknown — is represented, related and preserved.
**Enforces**: FR-006, FR-007, FR-008; blueprint §16.3, §16.4.

---

## Why this contract exists

This is the contract that makes "universal" operational. If a new kind of content requires a new
column, a new enum or a new table before it can be stored, the platform is closed. If unknown content
is discarded because it was not understood, the platform is lossy. Either way, the word "universal"
is false.

The element envelope separates the **open** part — `kind_uri` and payload schema — from the
**stable** part — provenance, scope, epistemics, lineage. The stable part is what lets the platform
link, retrieve, abstract and audit content it does not yet understand.

---

## Shape

```text
ContextElement
├── element_id              REQUIRED
├── kind_uri                REQUIRED   open namespace, e.g. domain://<pack>/<kind>
├── schema_ref              REQUIRED   schema identifier
├── schema_version          REQUIRED
├── payload_ref             CONDITIONAL  large payload, object-store reference
├── inline_small_payload    CONDITIONAL  only under the configured size limit
├── raw_form_ref            OPTIONAL   the exact observed form
├── semantic_refs[]         OPTIONAL   mappings to concepts, each with a mapping revision
├── relations[]             OPTIONAL   typed, directed, optionally n-ary
├── time_scope              CONDITIONAL  required where the kind is time-bearing
├── space_scope             OPTIONAL   geometry/region/topology with CRS
├── epistemic_status        REQUIRED   observation | claim | inference | hypothesis |
│                                      model | simulation | policy | unknown
├── provenance_refs[]       REQUIRED   at least one
├── abstraction_level_ref   REQUIRED
├── perspective_refs[]      OPTIONAL
├── assumptions_refs[]      OPTIONAL
├── sensitivity             REQUIRED   classification label
├── lineage                 OPTIONAL   derived_from, generated_by
├── supersedes              OPTIONAL
└── validation_status       REQUIRED   valid | quarantined | opaque
```

Exactly one of `payload_ref` and `inline_small_payload` is present.

---

## Normative rules

### R1 — The open part is open

`kind_uri` is a URI in an open namespace. A new domain pack registers new kinds without changing a
core enum or a core table. The sixteen starter profiles of §18.2 are the beginning of a registry,
not a closed list.

### R2 — The stable part is mandatory

Provenance, epistemic status, abstraction level, sensitivity and validation status are required for
every element, including an opaque one. An element without provenance cannot be linked, and an
element without an epistemic status cannot be distinguished from a fact.

### R3 — Invalid payloads are quarantined, not dropped

A payload that fails its schema goes to quarantine with its decoding errors and remains retrievable.
`validation_status: quarantined` is a durable state, not a transient log line.

### R4 — Unknown types are preserved as opaque

An unregistered `kind_uri` is stored with `validation_status: opaque`, its bytes intact, and can be
investigated after a parser or schema is registered. It is never dropped for being unrecognised.

### R5 — Relations are typed and role-bearing

Binary relations are a special case. An n-ary or role-bearing relation is a `RelationAssertion`; an
event with participants is an `EventFrame`. Flattening a contract with signer, date, organisation,
authority, place and condition into `(person, signed, document)` destroys exactly the information the
investigation needs.

### R6 — Projection is a view

Relations may be projected into graph edges for traversal. The projection is not the storage, and a
missing edge in the projection is not a missing relation.

### R7 — Epistemic status is not a label of convenience

`epistemic_status` records what kind of object this is. A hypothesis recorded as an observation is a
category error that no downstream confidence score repairs.

### R8 — Rootless elements are rejected

An element must attach to at least one provenance reference: an observation, a derivation, a
user-supplied input with an actor, or a model run. An element that came from nowhere cannot be
audited.

### R9 — Supersession, not overwrite

A changed element creates a new element with `supersedes`. The old element remains, because a
historical answer was given against it.

---

## Prohibitions

- A closed enum for content kinds.
- Dropping an unregistered kind or a malformed payload.
- A relation without roles.
- An element with no provenance.
- An in-place edit of an element that previously supported a reported finding.
- Treating a graph edge as the canonical relation.

---

## Tests

| Test | Asserts |
|---|---|
| `tests/contract/test_context_element.py::test_opaque_kind_round_trip` | R1, R4 |
| `tests/contract/test_context_element.py::test_quarantine_preserves_payload` | R3 |
| `tests/golden/test_nary_relation_preserved.py` | R5, R6 |
| `tests/contract/test_context_element.py::test_rootless_rejected` | R8 |
| `tests/golden/test_unknown_predicate_round_trip.py` | R1 |
