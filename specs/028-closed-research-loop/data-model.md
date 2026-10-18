# Data Model: Closed Research Loop with Versioned Evidence Contracts

**Feature**: 028-closed-research-loop
**Status**: Proposed — each entity below is marked with its current fate
(`KEEP` = exists and stays, `CHANGE` = exists and is altered, `NEW` = does not exist)

---

## 1. Identity vocabulary

Four distinct notions. Conflating any two of them is the defect this section exists
to prevent.

| Notion | Answers | Form | Current |
|---|---|---|---|
| **Content digest** | "Are these the same bytes?" | `sha256` hex over the raw bytes | KEEP |
| **Identity id** | "Is this the same *occurrence*?" | `OBS-` + digest over documented canonical material | CHANGE — four derivations collapse to one |
| **Logical id** | "Is this the same *thing*?" | `CAP-`, `RL-`, entity identity | KEEP |
| **Revision** | "Did the accumulated state change?" | minted only when a digest moves | CHANGE — currently minted unconditionally |

### 1.1 Observation identity (CHANGE)

Canonical material, sorted-key JSON, no separators, UTF-8, then truncated SHA-256:

```
identity_schema = "observation-identity/v2"
tenant_id
capture_id
locator
record_digest
```

The clock is deliberately excluded: two fetches returning identical bytes are one
payload and two publications, not one observation.

**Change**: v2 adds the `capture_locator` discriminator explicitly and is the *only*
derivation site. The two shadowing derivations are deleted:

- `services/interpretation_bridge.py:592` — derived from `tenant|digest` only, which
  collapses two distinct records carrying identical bytes into one observation.
- `zero/observation_gate.py:110` — a random UUID, which makes replay non-idempotent.

Compatibility: `observation-identity/v1` remains readable. A reader accepts either
version; a writer emits only v2. The refusal code `observation_identity_schema_unknown`
is raised for anything else.

### 1.2 Event identity (CHANGE)

```
event_id = "evt-" + sha256(canonical({
    event_type, event_version, tenant_id,
    observation_id | entity_id | record_hash,     # exactly one, per event type
    producer, producer_version, payload_digest,
}))[:32]
```

**Change**: `build_envelope` currently defaults `event_id` to `uuid4`
(`events/kafka.py:50`) and a contract test at `tests/contract/test_event_envelope.py:77`
pins that behaviour. The default becomes derived; the test is inverted to assert that
two builds of the same envelope yield the *same* id. An explicit `event_id=` argument
remains honoured for producers that legitimately mint one, and is then required to
justify itself: `IdempotentConsumer` records both the derived and supplied values.

---

## 2. The evidence chain (CHANGE)

```
Finding
  └─ derivation_id ──▶ Derivation
                         ├─ operator_result_id ──▶ OperatorResult
                         │                            ├─ method_fingerprint
                         │                            ├─ operator_id @ version
                         │                            ├─ inputs: [observation_id…]
                         │                            ├─ inputs: [content_digest…]
                         │                            └─ status: succeeded|partial|
                         │                                          unsupported|blocked|
                         │                                          failed|quarantined
                         ├─ claim_id ──▶ Assertion
                         │                 ├─ subject_ref / predicate / object_ref
                         │                 ├─ polarity: supports | refutes
                         │                 ├─ dependency_group_id
                         │                 └─ competing_with: [claim_id…]
                         └─ evidence_ref ──▶ EvidenceReference
                                              ├─ observation_id
                                              ├─ locator: Locator  (typed, §3)
                                              ├─ byte_start / byte_end
                                              ├─ page / box / frame / time_interval
                                              └─ excerpt_digest
```

**Change**: `ResolutionMention` currently has no span field at all
(`shared/semantic/resolution.py:244-277`); the span is consumed by `mint_mention_id`
and dropped at `services/document_adapter.py:271-300`. The locator becomes a
first-class carried value.

### 2.1 OperatorResult (NEW — one envelope for every analytical step)

Replaces the ad-hoc return shapes of parsers, extractors, matchers, rankers, graph
analytics, topological analysis, spatial indexing, online detectors and model calls.

| Field | Type | Purpose |
|---|---|---|
| `operator_id` | str | stable identity |
| `operator_version` | semver | code version |
| `upstream` | `UpstreamRef?` | repo / release / commit / image digest |
| `licence` | `LicenceRef?` | code licence, separate from data and model licences |
| `input_observation_ids` | list[str] | what was read |
| `input_content_digests` | list[str] | what the bytes actually were |
| `parent_derivation_ids` | list[str] | lineage |
| `output_kind` | str | typed output |
| `output_schema_version` | str | |
| `evidence_refs` | list[EvidenceReference] | exact spans |
| `observed_at` | timestamp? | **when the fact occurred in the world** |
| `published_at` | timestamp? | **when the source says it was published** |
| `processed_at` | timestamp | **when this platform computed it** |
| `valid_from` / `valid_until` | timestamp? | half-open `[from, until)` |
| `recorded_at` / `known_at` | timestamp | **when the platform learned it** |
| `method_fingerprint` | str | digest over the method's parameters |
| `deterministic` | bool | declared, not assumed |
| `seed` / `config_digest` | any / str? | required when `deterministic` is false |
| `nondeterminism_source` | str? | model sampling, thread order, clock |
| `calibration_id` | str? | when the output is a probability |
| `uncertainty` | `UncertaintyVector` | **a vector, never a scalar** |
| `missingness` | `MissingnessState` | not-random / not-applicable / unknown |
| `warnings` | list[str] | |
| `status` | `OperatorStatus` | succeeded / partial / unsupported / blocked / failed / quarantined |
| `cost` | `CostRecord?` | compute, network, storage, tokens, wall time |
| `replay_key` | str | same key ⇒ same result for a deterministic operator |
| `idempotency_key` | str | same key ⇒ no second logical effect |
| `tenant_id` | str | refused when empty |
| `scope_ref` | str? | investigation or question the result belongs to |

**Rule enforced by test**: `status == succeeded` with an empty `output` for a
non-nullable `output_kind` is a contract violation. This is the "absence must not
masquerade as an empty success" gate.

---

## 3. Locator (NEW — the typed span)

The single most consequential change to provenance. `Segment.offset` currently means
byte offset in one parser, segment index in another, and zero in a third — all summed
into one field at `extractors/lane.py:82-86`.

```python
class LocatorKind(StrEnum):
    BYTE_RANGE   = "byte_range"     # exact, resolvable against stored bytes
    PAGE_BOX     = "page_box"       # page index + bounding box
    FRAME_TIME   = "frame_time"     # frame index + time interval
    ROW_COLUMN   = "row_column"     # table row/column
    SEGMENT_INDEX= "segment_index"  # a parsed block, NOT a position in bytes
    CHARACTER    = "character"      # codepoint offset
    TIME_INTERVAL= "time_interval"
    UNKNOWN      = "unknown"        # preserved, never coerced
```

A `Locator` carries its kind and only the fields its kind defines. `UNKNOWN` is a
first-class value: an unlocated reference is recorded as unlocated, not assigned a
plausible byte offset.

**Rule**: two locators of different kinds are never compared for equality, and a
consumer that requires `BYTE_RANGE` refuses anything else rather than coercing.

---

## 4. Research state (CHANGE + NEW)

### 4.1 Question Definition (NEW)

Implements the decision already recorded in `docs/adr/0028`. Today the definition
concept exists only in specification — a code search for it returns nothing.

```
definition_id      CXD-<digest32>   own identity space, disjoint from CXI-
investigation_kind
objective
semantic_regime    versioned name + parameters
temporal_scope     { mode: current|as_of|interval, from?, to? }
policy_ref         policy identity + version
created_at
```

Identity material excludes mutable state, so re-describing the same analytical
assignment yields the same definition id and the platform can tell that two
investigations were set up the same way.

### 4.2 Investigation Context (CHANGE)

```
context_id         CXI-<digest32>   unchanged
definition_id      CXD-…            NEW field
revision           int              unchanged
parent_revision    int?             NEW — the supersession edge
revision_cause     RevisionCause    NEW — see §4.3
```

### 4.3 RevisionCause (NEW)

A revision that cannot explain itself is not auditable.

```
input_event_ids        list[str]   events consumed since the parent
rule_version           str         which rule set decided this revision
operator_versions      dict        operator_id → version used
parameters             dict        every parameter that affected the outcome
derived_changes        list[str]   what actually changed
unresolved_warnings    list[str]
```

### 4.4 Decision (CHANGE — becomes durable)

Currently a process-local list at `context_engine/engine.py:350` with no store method.

```
decision_id        DEC-<digest32>
context_id         CXI-…
revision           int              the revision this decision produced
grounds            list[str]        why
inputs             dict             what was known at decision time
alternatives       list[str]        what else was considered
actor              { kind: model|rule|analyst, id }
outcome            { kind: proposed|approved|rejected|executed|deferred|blocked }
decided_at         timestamp
```

Content-addressed over everything except `decided_at`, so the same decision reasoned
twice from the same state is the same decision.

### 4.5 ResearchObligation (KEEP)

Already content-addressed and status-bearing. Changes:

- `satisfied_by` must reference evidence, not just an outcome count.
- Add `blocking_capability` — the named capability that prevents progress, so a
  blocked obligation is distinguishable from a merely slow one.
- Add `no_gain_attempts` with the condition fingerprint that would unblock a repeat.

### 4.6 AbsenceStatement (NEW)

Five distinct states, never collapsed:

| State | Requires |
|---|---|
| `not_investigated` | nothing — the honest default |
| `searched_no_result` | a search that ran, plus its coverage |
| `source_unavailable` | a named failure of a named source |
| `query_unsupported` | a named capability that cannot express this question |
| `qualified_absence` | a named detecting capability, known coverage, and the budget spent |

Converting any of these into `negative support` requires an explicit decision record.
The epistemic layer already models the distinction; the schema does not currently
carry it through to a finding.

---

## 5. Storage and ordering (CHANGE)

Current reality: bytes are stored, then an observation row is written, then an event
is published — with no atomicity between the three, and the capture record constructed
in memory and discarded (`acquisition/artifact_sink.py:182-204`).

Target ordering, stated honestly rather than implied:

```
1. store raw bytes            → returns ref + dedup result
2. write capture record       → durable; the capture_id every event cites resolves
3. write observation          → references the capture ref from step 1
4. write membership / stream  → same transaction as step 3
5. publish event              → derived from the committed row, not the input
```

The guarantee claimed is: **step 5 may fail without losing evidence** (the row is
durable and a re-publish is idempotent because the event id is derived).
The guarantee **not** claimed is: steps 3 and 5 are atomic. They are not, and saying
otherwise would be the fabrication the constitution forbids.

Each of the four failure windows gets a named repair path:

| Window | State left behind | Repair |
|---|---|---|
| after 1, before 2 | orphan bytes | content-addressed garbage collection; harmless |
| after 2, before 3 | capture with no observation | capture is re-drivable from its locator |
| after 3, before 4 | observation with no membership | invariant fold skips it; re-drive appends membership idempotently |
| after 4, before 5 | complete, unpublished | periodic republish of rows whose event is absent |

---

## 6. Time (CHANGE)

Nine semantic fields, never interchanged:

| Field | Meaning | Not |
|---|---|---|
| `fetched_at` | when the bytes were obtained | when they happened |
| `captured_at` | when this platform recorded the capture | when it happened |
| `observed_at` | when the described event occurred in the world | when we learned it |
| `published_at` | when the source declares it was published | when we fetched it |
| `valid_from` / `valid_until` | half-open validity of the described fact | when we learned it |
| `recorded_at` / `known_at` | when the platform learned it | when it happened |
| `processed_at` | when this operator computed a result | any of the above |
| `ingested_at` | storage-layer arrival | any of the above |

**Change**: `CURRENT` is currently a byte-identical duplicate of the unsuffixed route.
It becomes a distinct query with its own contract, and `INTERVAL` is exposed on the
same surface as `CURRENT` and `AS_OF`, all three answering on the same underlying
materialisation.

---

## 7. Open world (CHANGE)

```python
class PredicateRef:
    namespace: str          # "" for unnamespaced — preserved, not rejected
    local_name: str
    version: str
    recognised: bool        # false ⇒ routed, not discarded
    policy_ref: str | None  # set only when a policy explicitly forbids it
```

A `PredicateRef` with `recognised=False` and `policy_ref=None` is an unknown
predicate in an open world: it routes to a generic bucket, is stored, is readable, and
is flagged. Setting `policy_ref` requires a recorded, versioned policy decision.
Default behaviour for an unrecognised predicate is therefore **retention**.

---

## 8. Projections (CHANGE)

Every projection carries this record, and the record is data rather than prose:

```python
class ProjectionContract:
    projection_id: str
    purpose: str
    input_event_types: list[str]
    checkpoint_ref: str | None          # durable offset, or None if whole-rebuild only
    schema_version: str
    operator_fingerprint: str
    incremental_path: bool
    rebuild_path: bool
    staleness_signal: str | None
    cost_per_rebuild: CostRecord | None
```

A projection claiming `rebuild_path` and failing the rebuild-digest test fails the
test suite. A projection claiming neither is marked experimental and is excluded from
the production readiness report.

---

## 9. Entity-level changes to the admission path

```python
class ResolutionDecision:            # already exists; becomes the only merge path
    decision_id: str
    candidate_pair: tuple[str, str]
    feature_breakdown: dict[str, float]     # per comparison level, not one number
    model_fingerprint: str
    calibration_id: str | None              # None ⇒ cannot auto-merge
    decision: accept | reject | defer | reverse
    actor: { kind: rule | analyst | model, id }
    decided_at: timestamp
    supersedes: str | None
```

**Change**: an automatic merge requires a non-null `calibration_id`. A profile whose
own version string declares itself uncalibrated can only produce `defer`. This is a
hard gate, enforced by test, not a default that can be overridden by configuration.

---

## 10. Migration summary

| # | Migration | Contents | Reversible |
|---|---|---|---|
| M1 | decision records | `research_decisions` table + indexes | yes (drop) |
| M2 | question definitions | `question_definitions` table; `investigation_contexts.definition_id` | forward-only column; table drop for rollback |
| M3 | revision cause | `context_revisions.cause` JSON column, default `{}` | yes |
| M4 | obligation blocking | two nullable columns | yes |
| M5 | locator | `mentions.locator` JSON column; existing `offset` retained and read as `SEGMENT_INDEX` | yes (dual-read) |
| M6 | capture persistence | `captures` table | yes |
| M7 | predicate openness | no schema change; policy decision record only | n/a |

Each migration ships with a dry-run, a checkpoint, and a rollback statement. No
migration drops or rewrites a raw observation.