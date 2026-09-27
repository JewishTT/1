# Event Contract: Relation & Evidence Graph Fabric

**Feature**: [016-relation-evidence-graph-fabric](../spec.md) | **Date**: 2026-09-26

Six new event types on the **existing** envelope. This feature introduces **no new
envelope shape**: every event is built with `build_envelope` from
`apps/shared/events/kafka.py` and routed with `topic_for` from
`apps/shared/events/topics.py`, exactly as the existing fabric events are. The envelope
itself is unchanged — `apps/shared/events/event_envelope.proto`
(`cognitive.events.v1.EventEnvelope`) is not modified by this feature.

**Refs only** (constitution I-5 / III): no payload carries document text, segment bodies,
WARC records, resolved frames-as-blobs or any other evidence content. Payloads carry
identifiers, versions and structured metadata; bytes stay in the content-addressed object
store and are reached by reference.

---

## Envelope

`EventEnvelope` field by field, for the events in this contract:

| Contract field | Envelope field (`event_envelope.proto`) | Source | Value for this feature |
| --- | --- | --- | --- |
| `event_id` | `event_id` (1) | `build_envelope(event_id=...)` | Deterministic: `"evt-" + digest128(canonical({"event_type", "event_version", "payload"}))`. Never a random uuid, never a clock reading — a producer retry must produce the same id, so re-delivery is a no-op (I-11). |
| `event_type` | `event_type` (2) | `build_envelope(event_type=...)` | One of the six types below. Also the key into `EVENT_CATALOG`; an unregistered type raises `UnknownEventTypeError` from `topic_for`. |
| `event_version` | `event_version` (3) | `build_envelope(event_version=...)` | Per-type payload version, semver-shaped. `"0.1.0"` for all six at introduction. Governs compatibility — see *Compatibility rules*. |
| `producer` | `producer` (7) | `build_envelope(producer=...)` | `projection.relation-claim`, `projection.evidence-context` or `admission.context-validator`. |
| `producer_version` | `producer_version` (8) | `build_envelope(producer_version=...)` | `0.1.0` for all three producers at introduction. |
| `payload` | `payload` (12) | `build_envelope(payload=json.dumps(...).encode("utf-8"))` | UTF-8 JSON bytes, one object per event type, registered against the Schema Registry as `PayloadRegistration(event_type, event_version, descriptor)`. |
| `entity_id` | `entity_id` (11) | `build_envelope(entity_id=...)` | The graph entity the claim is about (see per-event rules). `""` for a context whose `entity_anchor` is empty. |
| `key` | **not an envelope field** | `IdempotentProducer.produce(topic, envelope, key=...)` | The **Kafka record key**, which selects the partition. Defaults to `event_id` when omitted — for these events it is always passed explicitly. Partitioning semantics are in *Ordering and partitioning*. |
| `observed_at` | `produced_at` (9) for the emission instant; the domain instant stays in the payload | `build_envelope` stamps `produced_at = now_rfc3339()` | There is no `observed_at` envelope field. Emission time is `produced_at`; a claim's or frame's own `observed_at` is carried in the payload. `produced_at` is **excluded from the `event_id` digest** so a retry is byte-identical apart from that field. |
| `tenant_id` | `tenant_id` (13) | `build_envelope(tenant_id=...)` | The claim's / frame's `tenant_id`. MUST be set on every envelope; a consumer rejects an envelope whose `tenant_id` is empty. |
| `trace_id` | `correlation_id` (5) | `build_envelope(correlation_id=...)` | Root-intent correlation id shared by every event of one validation/extraction chain. `causation_id` (6) carries the immediate causing `event_id` (e.g. the `relation.claim.created` that a revision supersedes). |
| — | `investigation_id` (4) | `build_envelope(investigation_id=...)` | The claim's / frame's `investigation_id`. Set on every event in this contract: the fabric is process-centric and every claim is scoped to an investigation (constitution VI). |
| — | `observation_id` (10) | `build_envelope(observation_id=...)` | The frame's primary `observation_id` for `context.registered`; the claim's first `observation_ref` for claim events; `""` when a claim has no observations. |
| — | `source_id` (14) | `build_envelope(source_id=...)` | The frame's `source_id` for `context.registered`; `""` otherwise. |
| — | `work_id` (15), `region_id` (16) | `build_envelope(...)` | `""` unless a producer has them; not part of this contract. |

Worked envelope — `relation.claim.created` for the claim used throughout this contract
(`payload` is a `bytes` field, shown as its decoded JSON string):

```json
{
  "event_id": "evt-1f0c73ab5d2e48619a4cb7e0d3f5a8216",
  "event_type": "relation.claim.created",
  "event_version": "0.1.0",
  "investigation_id": "INV-77",
  "correlation_id": "0af7651916cd43dd8448eb211c80319c",
  "causation_id": "evt-6b31f0a97c2d4e58b0f1a6d3c8e50712",
  "producer": "projection.relation-claim",
  "producer_version": "0.1.0",
  "produced_at": "2026-09-24T08:12:07Z",
  "observation_id": "OBS-CC-7f31c0",
  "entity_id": "ENT-1042",
  "tenant_id": "t-acme",
  "source_id": "",
  "work_id": "",
  "region_id": "",
  "payload": "{\"relation_id\":\"RC-4c1f9ab27d5e8036b14ac95f2e7d3068\",\"logical_relation_id\":\"RL-8b2d5f0a71c34e96a4d80b53f2c7e119\", … }"
}
```

Produced with:

```python
producer.produce(
    topic_for("relation.claim.created"),
    build_envelope(
        event_type="relation.claim.created",
        event_version="0.1.0",
        producer="projection.relation-claim",
        producer_version="0.1.0",
        payload=json.dumps(claim_payload, sort_keys=True).encode("utf-8"),
        event_id=event_id,
        investigation_id=claim.investigation_id,
        correlation_id=trace_id,
        causation_id=causation_event_id,
        observation_id=next(iter(claim.observation_refs), ""),
        entity_id=claim.subject_ref,
        tenant_id=claim.tenant_id,
    ),
    key=claim.logical_relation_id,
)
```

**Producers**

| Producer | `producer_version` | Emits | Plane |
| --- | --- | --- | --- |
| `projection.relation-claim` | `0.1.0` | `relation.claim.created`, `.revised`, `.superseded`, `.contradicted` | Projection — materialises claims and their revision ledger into PostgreSQL and the graph backends |
| `projection.evidence-context` | `0.1.0` | `context.registered` | Projection — materialises the frame registry |
| `admission.context-validator` | `0.1.0` | `context.validation.recorded` | Admission — emits the graded verdict, never the verdict itself as a decision |

Producer names are dotted lowercase, matching the existing convention
(`acquisition.worker-http`, `observation-gate`, `shared.domain`).

---

## Topic catalogue

`topic_for(event_type)` returns the topic group from `EVENT_CATALOG` in
`apps/shared/events/topics.py`. The six entries below are **additions** to that catalogue;
no existing entry is renamed, re-pointed or removed, and no new envelope or topic-per-event
convention is introduced. A group of several event types is intentional: it puts one
relation's whole lifecycle on one topic, and the record key then does the per-relation
partitioning.

| Event type | `topic_for` → topic | Catalogue group | Status |
| --- | --- | --- | --- |
| `relation.claim.created` | `relation` | claim lifecycle | new entry, new group |
| `relation.claim.revised` | `relation` | claim lifecycle | new entry, same group |
| `relation.claim.superseded` | `relation` | claim lifecycle | new entry, same group |
| `relation.claim.contradicted` | `relation` | claim lifecycle | new entry, same group |
| `context.registered` | `evidence` | evidence substrate | new entry, existing group |
| `context.validation.recorded` | `admission` | admission verdicts | new entry, existing group |

`relation` joins the derived set in `TOPICS` automatically (`TOPICS = sorted(set(
EVENT_CATALOG.values()) | {TOPIC_DLQ, TOPIC_QUARANTINE})`). The dead-letter and quarantine
lanes are unchanged: a consumer that cannot process a record routes it to
`TOPIC_QUARANTINE` (`events.quarantine`) keyed by `event_id`, keeping the raw bytes for
replay (constitution quarantine + replay requirement).

**Two keys, deliberately distinct.** data-model.md §11 records one *aggregate* key per
event — the claim id a consumer folds on. The **record key** written to Kafka is the
*partition key*, given per event below. They differ for the claim events on purpose: the
aggregate key must identify the specific revision, while the partition key must keep all
revisions of one relation in order. `data-model.md` §11's key for
`relation.claim.revised` (`logical_relation_id`) is the one case where the two coincide.

---

## Event catalogue

Every payload below is UTF-8 JSON decoded from `EventEnvelope.payload`. Field names are
those of [data-model.md](../data-model.md); the two derived fields
(`independent_source_count`, `publication_count`) are included on `relation.claim.created`
because a consumer must not recompute them incorrectly, and they are always **separate
values, never a combined score** (constitution IV, FR-034).

### relation.claim.created

Materialises one content-distinct claim revision. Emitted for **every** distinct
`relation_id`, including revisions — this is the rebuild unit of the relation store, and a
rebuild replays these and nothing else to reproduce the store.

| Property | Value |
| --- | --- |
| Topic | `relation` |
| Record key (partition) | `logical_relation_id` |
| Aggregate key (dedupe) | `relation_id` |
| `entity_id` | `subject_ref` for `directed`/`temporal`; the lexicographically smallest participant ref for `undirected`/`nary`; `""` only if the claim has no participants, which cannot occur |
| `event_version` | `0.1.0` |
| Producer | `projection.relation-claim` `0.1.0` |

```json
{
  "relation_id": "RC-4c1f9ab27d5e8036b14ac95f2e7d3068",
  "logical_relation_id": "RL-8b2d5f0a71c34e96a4d80b53f2c7e119",
  "revision_number": 1,
  "relation_type": "works_for",
  "arity_mode": "directed",
  "subject_ref": "ENT-1042",
  "object_ref": "ENT-2087",
  "role_bindings": [],
  "valid_from": "2017-01-01T00:00:00+00:00",
  "valid_to": null,
  "observed_at": "2026-09-24T08:12:03+00:00",
  "published_at": "2026-09-24T09:40:00+00:00",
  "known_from": "2026-09-24T08:12:03+00:00",
  "known_until": null,
  "assertion_refs": ["ASR-77c1e04b"],
  "observation_refs": ["OBS-CC-7f31c0", "OBS-CC-b2048e", "OBS-WB-4a90de"],
  "context_ref": "CX-6e0a41c8b93d27f5a4c68e0b1d7f9235",
  "source_independence_groups": [
    ["OBS-CC-7f31c0", "OBS-CC-b2048e"],
    ["OBS-WB-4a90de"]
  ],
  "extraction_version": "rel-extract-2.4.0",
  "normalization_version": "norm-1.9.2",
  "ontology_version": "ontology-v3",
  "schema_version": "3",
  "status": "active",
  "confidence": 0.81,
  "evidence_grade": "strong",
  "tenant_id": "t-acme",
  "investigation_id": "INV-77",
  "created_by": "interp-rel-extract-2.4.0",
  "supersedes": "",
  "contradicts": [],
  "created_at": "2026-09-24T08:12:07+00:00",
  "content_hash": "0b91c7d4e6a2f83045b19d7c8e2a6f53",
  "independent_source_count": 2,
  "publication_count": 3
}
```

**Create-only, content-immutable.** A `relation.claim.created` is an assertion that this
`relation_id` exists with exactly this content. Re-emitting the same `relation_id` with the
same `content_hash` is a no-op. Re-emitting the same `relation_id` with a **different**
`content_hash` is an identity violation: the consumer must reject it to the quarantine lane
with reason `relation_id_content_mismatch`, never update the stored row (FR-005, FR-011).
A changed claim is a new `relation_id` and a new event.

**Consumer / projection**: `RelationClaimProjector` (group `relation-claim`) upserts the
`relation_claim` row and appends the `relation_claim_revision` row; `GraphProjectionWriter`
writes `GraphEdge(edge_id=relation_id, edge_type=relation_type, source=subject_ref,
target=object_ref, properties=claim.to_dict())` and `MERGE`s on the relation id, so a
re-write is idempotent (FR-035, FR-036, FR-038). `RebuildableRelationStore` folds the same
events to reconstruct the store; the relation checksum after a full replay equals the
checksum of the live store (FR-040).

**Satisfies**: FR-001, FR-003, FR-005, FR-007, FR-035, FR-036, FR-049.

### relation.claim.revised

Records the lineage transition when a new revision of an existing relation is produced. It
carries **no claim content** — the content arrives as a second
`relation.claim.created` for the new `relation_id` on the same partition.

| Property | Value |
| --- | --- |
| Topic | `relation` |
| Record key (partition) | `logical_relation_id` (identical to the aggregate key here) |
| Aggregate key (dedupe) | `logical_relation_id` + `revision_number` |
| `entity_id` | as for the claim the revision belongs to |
| `event_version` | `0.1.0` |
| Producer | `projection.relation-claim` `0.1.0` |

```json
{
  "logical_relation_id": "RL-8b2d5f0a71c34e96a4d80b53f2c7e119",
  "relation_id": "RC-91d7c0e45a2b6f38c07e15b9da3f2846",
  "revision_number": 2,
  "supersedes": "RC-4c1f9ab27d5e8036b14ac95f2e7d3068",
  "revision_window": {
    "previous_valid_from": "2017-01-01T00:00:00+00:00",
    "previous_valid_to": null,
    "valid_from": "2017-01-01T00:00:00+00:00",
    "valid_to": "2022-12-31T00:00:00+00:00"
  },
  "changed_fields": ["valid_to", "context_ref", "observation_refs"],
  "schema_version": "3",
  "ontology_version": "ontology-v3",
  "tenant_id": "t-acme",
  "investigation_id": "INV-77"
}
```

`changed_fields` is a hint for the diff view, derived from the two claims' field sets; a
consumer MUST NOT rely on it to reconstruct the change — it re-reads the two claim objects
from the two `relation.claim.created` events. `causation_id` points at the
`relation.claim.created` of the **previous** revision, so the chain is walkable in both
directions from the envelope alone.

**Consumer / projection**: `RelationRevisionLedgerProjector` appends the
`relation_claim_revision` row and flips the prior revision's `status` to `superseded`. The
claim rows of both revisions are preserved (FR-006). The graph projection re-points its
current edge to the new `relation_id` and keeps the old edge, so a graph snapshot taken
before the revision remains reproducible.

**Satisfies**: FR-003, FR-006, FR-029, FR-049.

### relation.claim.superseded

Emitted when a claim loses currency to a newer revision. A status transition, never a
delete: the payload carries no content, because the content is unchanged.

| Property | Value |
| --- | --- |
| Topic | `relation` |
| Record key (partition) | `logical_relation_id` |
| Aggregate key (dedupe) | `relation_id` |
| `entity_id` | the superseded claim's `subject_ref` / smallest participant |
| `event_version` | `0.1.0` |
| Producer | `projection.relation-claim` `0.1.0` |

```json
{
  "relation_id": "RC-4c1f9ab27d5e8036b14ac95f2e7d3068",
  "logical_relation_id": "RL-8b2d5f0a71c34e96a4d80b53f2c7e119",
  "revision_number": 1,
  "superseded_by": "RC-91d7c0e45a2b6f38c07e15b9da3f2846",
  "previous_status": "active",
  "status": "superseded",
  "known_until": "2026-09-24T16:05:41+00:00",
  "tenant_id": "t-acme",
  "investigation_id": "INV-77"
}
```

A `superseded` claim stays fully readable and keeps its content, evidence, context and
grade. There is no tombstone, no delete event and no expiry (FR-006, constitution I-3).

**Consumer / projection**: `RelationRevisionLedgerProjector` sets
`status = "superseded"` and `known_until` on the claim row, appends to
`relation_claim_revision`, and marks the graph projection's edge as no longer current. A
rebuild replays `created` + `revised` + `superseded` and reaches the same state.

**Satisfies**: FR-006, FR-049.

### relation.claim.contradicted

Records that a claim is contradicted by other claims. This feature persists the links and
reports overlapping conflicting intervals; it does **not** rank which claim wins
(contradiction reasoning is out of scope per spec.md *Out of Scope*).

| Property | Value |
| --- | --- |
| Topic | `relation` |
| Record key (partition) | `logical_relation_id` |
| Aggregate key (dedupe) | `relation_id` |
| `entity_id` | the contradicted claim's `subject_ref` / smallest participant |
| `event_version` | `0.1.0` |
| Producer | `projection.relation-claim` `0.1.0` |

```json
{
  "relation_id": "RC-4c1f9ab27d5e8036b14ac95f2e7d3068",
  "logical_relation_id": "RL-8b2d5f0a71c34e96a4d80b53f2c7e119",
  "contradicts": [
    "RC-c07d3e914b8f26a50d3c9e7b1f48206a",
    "RC-2f6c8b1d47a0e935c218b74da60f5e83"
  ],
  "conflict_kind": "overlapping_interval",
  "overlap_window": {
    "from": "2019-04-01T00:00:00+00:00",
    "to": "2022-12-31T00:00:00+00:00"
  },
  "previous_status": "superseded",
  "status": "contradicted",
  "tenant_id": "t-acme",
  "investigation_id": "INV-77"
}
```

`conflict_kind` is `overlapping_interval` when the claims' validity windows overlap with
conflicting `object_ref` values, or `mutual_exclusion` when the schema declares the relation
mutually exclusive over its participants. Disjoint windows are **not** a contradiction and
produce no such event; they produce a `temporal_non_overlap` note on the validation record
instead (FR-024). Both sides are preserved with their statuses intact; the contradicted
claim is not deleted (FR-006).

**Consumer / projection**: `ContradictionEdgeProjector` sets `status = "contradicted"`,
writes the `contradicts` edges into the graph projection as a derived view, and records the
overlap window on the revision ledger. The graph is a projection, so the contradiction edge
can be rebuilt and dropped without touching the claims (constitution IV).

**Satisfies**: FR-006, FR-022, FR-024, FR-049.

### context.registered

Registers one immutable, content-addressed `EvidenceContext` frame. A claim is only
writable once its frame is registered, so this event always precedes the
`relation.claim.created` that cites the frame (FR-007, FR-016, I-12).

| Property | Value |
| --- | --- |
| Topic | `evidence` |
| Record key (partition) | `context_id` |
| Aggregate key (dedupe) | `context_id` |
| `entity_id` | `entity_anchor`, or `""` when the frame anchors no entity |
| `event_version` | `0.1.0` |
| Producer | `projection.evidence-context` `0.1.0` |

```json
{
  "context_id": "CX-2f6c8b1d47a0e935c218b74da60f5e83",
  "tenant_id": "t-acme",
  "investigation_id": "INV-77",
  "entity_anchor": "ENT-1042",
  "observation_id": "OBS-REG-3c77a0",
  "source_id": "SRC-uk-registry",
  "document_id": "DOC-9b22e0d1",
  "segment_id": "SEG-9b22e0d1-p1-s04",
  "subject_candidate_ids": ["CAN-9d2f10"],
  "object_candidate_ids": ["CAN-5b71ae", "CAN-77a1c4"],
  "observed_at": "2026-09-24T15:58:11+00:00",
  "published_at": "2026-09-24T16:02:00+00:00",
  "valid_from": "2017-01-01T00:00:00+00:00",
  "valid_to": "2022-12-31T00:00:00+00:00",
  "source_family": "registry",
  "independence_group": "ig-reg-3c77a0",
  "language": "en",
  "location_context": "GB-LND",
  "extraction_version": "rel-extract-2.4.0",
  "normalization_version": "norm-1.9.2",
  "ontology_version": "ontology-v3",
  "completeness": "partial",
  "trust_state": "attested",
  "policy_snapshot_ref": "pol-2026-09-20T00:00Z",
  "parent_context_id": "CX-6e0a41c8b93d27f5a4c68e0b1d7f9235",
  "frame_fingerprint": "2f6c8b1d47a0e935c218b74da60f5e83",
  "created_at": "2026-09-24T15:58:12+00:00"
}
```

The frame content is immutable (FR-015): re-registering the same `context_id` with an
identical fingerprint is a no-op, and a `context_id` re-registration with a different
`frame_fingerprint` is an identity violation routed to quarantine with reason
`context_id_fingerprint_mismatch` — never an update. A frame whose `parent_context_id` is
missing or cyclic is **registered anyway**: a frame is evidence, not a verdict, and
`context_parent_missing` / `context_parent_cycle` are validator verdicts over a storable
frame (US3 AS-3). The frame carries no `raw_text`, no segment body and no inline
document — `document_id` and `segment_id` are references (constitution I-5).

**Consumer / projection**: `ContextRegistryProjector` (group `evidence-context`) upserts the
`evidence_context` row, enforcing the unique index on `(tenant_id, frame_fingerprint)`;
`EvidenceGraphBuilder` materialises the `observation`/`capture`/`source` hops for the
lineage traversal. The read path `GET /api/v1/contexts/{context_id}` is served from this
projection and never from Kafka directly (Kafka is not a query store, constitution I-5).

**Satisfies**: FR-013, FR-014, FR-015, FR-016, FR-017, FR-018, FR-030, FR-049.

### context.validation.recorded

Records the graded outcome of one validation run. Emitted for **every** verdict, including
`valid` and including every non-`valid` one — a rejected or underdetermined claim is
preserved with its decision, reasons, components, versions and timestamps, and is
replayable (FR-050).

| Property | Value |
| --- | --- |
| Topic | `admission` |
| Record key (partition) | `relation_id` |
| Aggregate key (dedupe) | `relation_id` + `context_id` + `evaluated_versions` |
| `entity_id` | as for the validated claim |
| `event_version` | `0.1.0` |
| Producer | `admission.context-validator` `0.1.0` |

```json
{
  "claim_id": "RC-7d10b8e2c4f6a1903b5e8d7c2a6f4e13",
  "relation_id": "RC-7d10b8e2c4f6a1903b5e8d7c2a6f4e13",
  "context_id": "CX-0a3f6d19c7b24e85f61a0c93b8d47e2",
  "verdict": "invalid",
  "layers": {
    "structural": "passed",
    "semantic": "passed",
    "temporal": "failed",
    "provenance": "passed",
    "identity": "passed",
    "cross_source": "passed",
    "graph_constraints": "passed"
  },
  "reasons": [
    {
      "code": "temporal_interval_inverted",
      "layer": "temporal",
      "detail": "valid_from 2025-01-01T00:00:00+00:00 is after valid_to 2020-12-31T00:00:00+00:00",
      "evidence": ["RC-7d10b8e2c4f6a1903b5e8d7c2a6f4e13"]
    }
  ],
  "evidence_grade": "moderate",
  "grade_components": {
    "independent_source_count": 1,
    "publication_count": 2,
    "completeness": "partial",
    "trust_state": "attested",
    "confidence": 0.62
  },
  "evaluated_versions": {
    "extraction_version": "rel-extract-2.4.0",
    "normalization_version": "norm-1.9.2",
    "ontology_version": "ontology-v3",
    "schema_version": "3"
  },
  "tenant_id": "t-acme",
  "investigation_id": "INV-77"
}
```

Contract rules on this payload:

1. `layers` carries **all seven** keys, always, whatever the verdict — a record with a
   missing layer key is invalid and is routed to quarantine (FR-019).
2. `reasons` is **non-empty whenever `verdict != "valid"`**. A record with an empty
   `reasons` and a non-`valid` verdict is invalid and is routed to quarantine with reason
   `validation_reasons_missing`. `reasons` may be non-empty for a `valid` verdict — a
   `temporal_non_overlap` note is the normal case (FR-020, FR-024).
3. **No boolean.** There is no `valid`/`passed`/`ok` field. `verdict` is one of `valid`,
   `invalid`, `underdetermined`, `incomplete`, `conflicting`, `stale`, resolved by the fixed
   precedence `invalid > conflicting > stale > incomplete > underdetermined > valid`
   (FR-021).
4. `grade_components` holds the five components **separately** and the payload contains no
   combined grade number (constitution IV, FR-025). `evidence_grade` is the enumerated label.
5. `claim_id` and `evidence_grade` are carried in addition to the seven fields listed in
   data-model.md §11, so a replayed record reconstructs the identical `ValidationResult`
   shape that `POST /api/v1/relations/{relation_id}/validate` returns. This is an additive
   change to that table and is permissible under the compatibility rules below.
6. `evaluated_versions` is the compatibility guard: it records the extractor,
   normalisation, ontology and schema versions the run actually evaluated against, so a
   later reader can tell a `stale` verdict from a current one (FR-029).

**Consumer / projection**: `ValidationRecordProjector` (group `admission`) materialises the
record for replay and for the read path; `AdmissibilityProjector` reads the verdict to gate
admission — but a non-`valid` verdict gates a *claim*, and never deletes a context, an
observation or a claim. The durable record is the event; the projection caches it for reads
(see *Compatibility rules* for parking).

**Satisfies**: FR-019, FR-020, FR-021, FR-022, FR-025, FR-029, FR-050.

**Coverage matrix**

| Event | Requirements |
| --- | --- |
| `relation.claim.created` | FR-001, FR-003, FR-005, FR-007, FR-035, FR-036, FR-049 |
| `relation.claim.revised` | FR-003, FR-006, FR-029, FR-049 |
| `relation.claim.superseded` | FR-006, FR-049 |
| `relation.claim.contradicted` | FR-006, FR-022, FR-024, FR-049 |
| `context.registered` | FR-013, FR-014, FR-015, FR-016, FR-017, FR-018, FR-030, FR-049 |
| `context.validation.recorded` | FR-019, FR-020, FR-021, FR-022, FR-025, FR-029, FR-050 |

---

## Idempotency

**Primary dedupe: `event_id`.** `event_id` is the consumer idempotency key for every event in
this contract, exactly as for the existing fabric. It is `evt-` + `digest128` over the
canonical `(event_type, event_version, payload)` and is therefore deterministic: a producer
retry, a re-delivery by Kafka, or a replay from the log produces the identical id and is a
no-op. A consumer that sees an `event_id` it has already applied MUST skip the event
entirely — not re-append a ledger row, not re-emit a derived graph edge (constitution I-11).

**Secondary dedupe keys**, in addition to `event_id`:

| Consumer class | Secondary dedupe key | Why |
| --- | --- | --- |
| Claim consumers (`relation.claim.*`) | `relation_id` **and** `content_hash` | `content_hash` is a content address: a claim's content is immutable, so the pair must be stable for the life of the record. Seeing `relation_id` with a different `content_hash` is an identity violation → quarantine, never update (FR-005, FR-011). |
| Context consumers (`context.registered`) | `context_id` | `context_id` is a content address over the frame, so a re-registration with the same id is the same frame; the unique index on `(tenant_id, frame_fingerprint)` is the store-level expression of the same rule (FR-014). |
| Validation-record consumers (`context.validation.recorded`) | `(relation_id, context_id, evaluated_versions)` | The same claim, under the same frame, against the same version triple, must have one verdict. A re-validation whose `evaluated_versions` are unchanged is a no-op — and if it somehow produces different content, the **older record stands**; a materially different evaluation must carry a changed version triple, which is a new key and a new record. |

**Convergence.** Replaying the whole durable log must converge to a byte-identical store
state: same claim rows, same revision ledger, same frame registry, same evidence hops, and
therefore the same relation checksum from `InMemoryRelationStore.checksum()` — claims
sorted by `relation_id`, then `digest128` over the joined `content_hash` list
(FR-040, SC-011). This is a hard requirement of the contract, not a property of a particular
consumer: a consumer whose fold is order-sensitive or whose dedupe is not content-addressed
violates this contract even if every individual apply looks correct.

**Nothing is dropped.** A record a consumer cannot apply is routed to
`TOPIC_QUARANTINE` (`events.quarantine`) keyed by `event_id` with the raw bytes retained for
replay — including a record whose version the consumer cannot interpret (see
*Compatibility rules*). A rejected, unapplicable or uninterpretable record is never silently
discarded (constitution quarantine/replay requirement).

**Tenant isolation.** A consumer MUST reject any envelope whose `tenant_id` does not match
its own scope. The rejection is itself recorded, never applied.

---

## Ordering and partitioning

| Stream | Record key | Partitioning consequence |
| --- | --- | --- |
| `relation.claim.created` / `.revised` / `.superseded` / `.contradicted` | `logical_relation_id` | All revisions of one relation land on **one** partition, so the revision chain arrives in order and the ledger append is contention-free. |
| `context.registered` | `context_id` | A frame's own re-registrations stay ordered; parent/child frames are independent (a child may register before its parent — the resolver tolerates it and the validator reports `context_parent_missing`). |
| `context.validation.recorded` | `relation_id` | All verdicts about one claim stay ordered relative to each other. |

**Claim ordering rules.**

1. All four claim event types share the `relation` topic and the `logical_relation_id`
   key, so a relation's whole lifecycle is one ordered sequence. A consumer MAY assume
   `relation.claim.created` for revision *n* precedes `relation.claim.revised` for revision
   *n+1*.
2. **Within a relation, do not rely on arrival order; order by `revision_number`.** A
   producer retry or a redelivery can interleave, so a consumer MUST sort or buffer by
   `revision_number` from the payload and apply the ledger by that number, not by
   `produced_at` and not by offset. `produced_at` is wall-clock and is deliberately excluded
   from `event_id`, so it cannot be used as a sequence.
3. `relation.claim.revised` for revision *n+1* requires the `relation.claim.created` for
   revision *n+1* to be applied first (the `revised` event carries no content). A consumer
   that sees `revised` before the matching `created` must **park** the record, not discard
   it, and re-apply it when the `created` arrives; parking is the quarantine lane plus a
   re-drive from the log.
4. `relation.claim.revised`, `relation.claim.superseded` and
   `relation.claim.contradicted` carry only transitions. A consumer that never receives a
   `created` for a `relation_id` referenced by such a transition has an incomplete fold
   and must report it — not synthesise the claim.

**Global ordering is not guaranteed.** Cross-relation ordering is explicitly not provided
and nothing may depend on it: no query may assume "the newest event overall", no consumer
may derive a global sequence number from these topics, and no projection may use wall-clock
`produced_at` to decide which state is current. State is current by `revision_number` and
`status`, both carried in the payload. Cross-relation and cross-tenant reads are served from
the PostgreSQL projection, which is the query surface — Kafka is not an ordering or query
mechanism (constitution I-5, projection-first III).

---

## Compatibility rules

**Semantic versioning of `event_version`, per event type.** Each of the six types versions
independently.

| Change | Classification | Requirement |
| --- | --- | --- |
| Adding an optional field (a nullable field, a new key in a `grade_components`-style map, a new `NOTED` reason code) | **minor** | Bump `event_version` (`0.1.0` → `0.2.0`). Consumers on the older minor must ignore unknown fields and still converge to the same store state. A new reason code is additive: a consumer that does not recognise a reason code stores it verbatim and does not change the verdict it already computed. |
| Removing a field, renaming a field, changing a type (e.g. `publication_count` int → string), narrowing an enum (`RelationStatus` dropping a value), or changing the meaning of an existing field | **major** | New `event_version` (`0.1.0` → `1.0.0`) and a dual-publish window: both versions are produced for the overlap, and consumers register both via `SchemaRegistryClient`. A payload of an unknown major version is never parsed best-effort. |
| Changing a partition key or a producer name | **major** | It changes ordering guarantees and consumer group routing; it requires a new `event_version` and a migration note in `operations.md`. |

**The `evaluated_versions` guard.** A consumer that cannot interpret the recorded
`ontology_version`, `extraction_version`, `normalization_version` or `schema_version` in a
`context.validation.recorded` payload — because it predates that version, or because the
version is absent from its own ontology pack registry — **parks the record**: it writes it to
the quarantine lane with reason `evaluated_version_unknown`, keyed by `event_id`, retaining
the raw bytes, and makes no change to any projection state. It must **not** drop the record,
must **not** fall back to a default ontology version, and must **not** re-evaluate the claim
under the version it does know. A parked record becomes applicable when a consumer able to
interpret it replays the log. The same rule governs a `relation.claim.created` whose
`ontology_version` is unknown to the consumer: the claim is stored as-is with a `stale`
marker, never interpreted (FR-029, I-4).

**Payload content rules.** Every payload carries **refs and versions only**: `relation_id`,
`logical_relation_id`, `context_id`, `observation_refs`, `source_id`, `document_id`,
`segment_id`, `policy_snapshot_ref`, `ontology_version`, `schema_version`, counts, enums
and structured reasons. No payload carries raw bytes, document text, a segment body, a
mention span's source text, a resolved frame duplicated inline, or any blob — the object
store is the only place content lives, and Kafka is not the object store (constitution I-5,
III). A frame is referenced by `context_ref`/`context_id`, never copied into a claim payload
(FR-018). The one deliberate duplication is `frame_fingerprint` on
`context.registered`, which is 32 hex characters of derived address, not content.

**Registration.** Each `(event_type, event_version)` is registered as a
`PayloadRegistration` against the Schema Registry before it is produced; production of an
unregistered version is refused, and a consumer of an unregistered version parks rather
than parses.
