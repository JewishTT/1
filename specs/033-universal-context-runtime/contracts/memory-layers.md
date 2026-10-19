# Contract 07 — Memory Layers

**Feature**: `033-universal-context-runtime`
**Governs**: what the platform remembers, for how long, under whose control.
**Enforces**: FR-052…FR-054; blueprint §25.

---

## Why this contract exists

A single "memory" is how a research platform becomes a system that cannot explain, correct or forget.
The blueprint requires nine layers, each with its own scope, retention, permissions, correction,
expiry and replay rules, and it forbids applying "remember forever" to all objects (§25).

The layers are not storage tiers. They are **different kinds of remembering**, and conflating them is
how a preference becomes evidence and a working summary becomes a finding.

---

## The layers

| # | Layer | Contents | Scope | Lifetime | Write authority |
|---|---|---|---|---|---|
| 1 | Conversation state | turns, pointers, visible commitments | one conversation | session + configured window | conversation service |
| 2 | Working set | the context for one step | one operation | rebuilt per operation | memory compiler |
| 3 | Task/process | actions, outputs, retries, open obligations, plans | one context | until context closes | kernel |
| 4 | Case/project | claims, decisions, ontology and scope versions, findings | one case | case policy | case authority |
| 5 | Entity/worldline | accepted claims and events, identity decisions | one entity | entity policy + legal hold | invariant reducer |
| 6 | Procedural | validated recipes, capability docs, evaluated prompts | capability | versioned | governance |
| 7 | Semantic/episodic | retrieval indexes | tenant | rebuildable | projection fabric |
| 8 | Preference | user settings | user | user-controlled | user |
| 9 | Institutional | approved methods, standards, decisions, lessons | organisation | dated validity | governance |

---

## Shape

```text
MemoryRecord
├── memory_id                 REQUIRED
├── layer                     REQUIRED   one of the nine
├── scope                     REQUIRED   conversation | operation | context | case |
│                                        entity | capability | tenant | user | organisation
├── content_ref               REQUIRED
├── source_refs[]             REQUIRED   what it was derived from
├── omitted[]                 REQUIRED   for any summary or compaction
├── retention
│   ├── policy_id             REQUIRED
│   ├── expires_at            REQUIRED   or `null` with a reason
│   └── legal_hold            OPTIONAL
├── permissions
│   ├── read_by[]             REQUIRED
│   └── write_by[]            REQUIRED
├── correction
│   ├── correctable_by[]      REQUIRED
│   └── correction_history[]  REQUIRED
└── replay
    └── replayable            REQUIRED   can the record be re-derived from sources?
```

---

## Normative rules

### R1 — Layer rules are not interchangeable

A retention, permission or correction rule from one layer never applies to another. A blanket policy
is a failure of this contract, not a simplification.

### R2 — Preference is not evidence

Layer 8 never appears in an evidence query, a claim, a finding or an assembly's `included[]` as
support. It may appear as an explicit preference annotation, never as a source.

### R3 — Summary remembers what it omitted

A compaction or summary in any layer carries `omitted[]` and `source_refs[]`. A summary that cannot
say what it dropped is not a memory; it is an assertion.

### R4 — Expiry is an action with a record

Expiring a record records the lineage impact: what derived artifacts referenced it, and what their
status becomes. Silent deletion is forbidden.

### R5 — Correction is a new record

A corrected memory appends a correction and keeps the prior version. "Fixing" a record in place
destroys the ability to explain a past answer.

### R6 — Replayability is declared

A record is either replayable from its sources or explicitly not. A non-replayable record is a
limitation, and it says so.

### R7 — Legal hold beats retention

A record under legal hold does not expire. The hold is recorded with its authority and its scope.

### R8 — Institutional memory has an owner and a validity period

An approved method or standard is not eternal. It has an owner, a date and a review condition.

---

## Prohibitions

- One retention policy for all layers.
- Preference data used as evidence.
- Silent deletion on expiry.
- In-place correction of a record that supported a reported finding.
- A summary without `omitted[]`.
- Institutional memory with no owner.

---

## Tests

| Test | Asserts |
|---|---|
| `tests/contract/test_memory_layers.py::test_scope_isolation` | R1 |
| `tests/security/test_preference_never_evidence.py` | R2 |
| `tests/golden/test_summary_records_omissions.py` | R3 |
| `tests/integration/test_expiry_records_lineage_impact.py` | R4 |
| `tests/integration/test_correction_appends.py` | R5 |
