# Event Contract: Temporal Materialization

**Feature**: `014-temporal-materialization`  
**Event schema baseline**: `cognitive/event-envelope/v2`  
**Status**: Design artifact; Protobuf and topic registrations are not implemented

## Scope

Use the existing Kafka backbone and event catalog. No new broker, retry bus, universal event store, or orchestration backbone is introduced.

## Topic mapping

| Logical stream | Event type | Existing topic resolution | Role |
| --- | --- | --- | --- |
| Accepted entity stream | `entity.stream.appended` | `topic_for("entity.stream.appended")` / `entity-stream` | Incremental materialization trigger. |
| Published history | `entity.temporal_history.published` | Projection topic via `topic_for` | Initial publication or rebuild promotion. |
| Revised history | `entity.temporal_history.revised` | Projection topic via `topic_for` | One or more effective window revisions changed at a newer source cut. |
| Rejected/quarantined work | Existing governed quarantine event family | Existing governance/quarantine topic resolution | Durable disposition notification; database quarantine remains authority. |

Do not hard-code topic names in domain code. Producers/consumers use the existing catalog resolver.

## Envelope requirements

The materialization path uses the existing envelope fields:

- `event_id` as delivery idempotency identity;
- `event_type` and `schema_version` for dispatch/evolution;
- `tenant_id` as mandatory routing/isolation;
- `investigation_id`, `correlation_id`, and `causation_id` for process-centric lineage;
- `entity_id` for entity history scope;
- `observation_id`, source, work, region, producer, and production time for trace/retry behavior.

A new materialization-specific payload Protobuf is preferred for published/revised history events. The domain canonicalizer must not hash generated Protobuf wire bytes.

## Input contract: `entity.stream.appended` v2

The materialization-ready payload contains:

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `tenant_id` | string | yes | Must match envelope and accepted source row. |
| `entity_id` | string | yes | Must match the stable dynamic history scope. |
| `source_namespace` | string | yes | Producer/source namespace. |
| `source_record_id` | string | yes | Stable source identity. |
| `stream_sequence` | uint64 | yes | Positive entity-stream sequence. |
| `event_occurrence_at` | timestamp | yes | Timezone-aware occurrence time. |
| `record_hash` | bytes/string | yes | Canonical accepted source content hash. |
| `wire_hash` | bytes/string | no | Forensic raw transport hash. |
| `schema_name` / `schema_version` | string | yes | Governed source interpretation. |
| `observation_id` | string | no | Evidence/observation reference. |
| `evidence_refs` | repeated typed reference | yes | References only; no payload/blob. |
| `entity_class` / `materialization_eligible` | enum/bool | yes | Dynamic-continuant decision input from existing authority. |
| `source_payload` | bytes/typed object | yes | Accepted semantic content, size-bounded and policy-versioned. |

The accepted PostgreSQL source row is the materialization input authority. The Kafka event is a trigger and lineage reference; the consumer verifies/reloads the accepted row before changing a candidate.

## Input idempotency and disposition

1. Same `event_id` already durably handled: no-op.
2. Same source identity/content already accepted: exact duplicate; no new accepted event or revision.
3. Same source identity with different verified content: quarantine `contradictory_source_record`.
4. Different event ID with identical source/content: exact source duplicate, while delivery evidence is retained.
5. Missing tenant/entity/source identity, invalid timestamp/hash/schema, or non-dynamic source: validate/quarantine before candidate mutation.

## Consumer context

The corrected Kafka consumer must pass the handler:

- envelope/event ID and type/version;
- tenant/entity/investigation;
- topic/partition/offset and delivery attempt;
- received time;
- acknowledged-by-consumer boolean.

Transport position is forensic metadata. It is not a substitute for `SourceCut`.

## Offset and quarantine protocol

1. Parse and validate the envelope/payload.
2. Persist accepted/duplicate/quarantined disposition and resulting run/outbox state durably.
3. Commit the Kafka offset only after that transaction succeeds.
4. Publish quarantine through a producer/outbox, never by calling `produce` on a Kafka consumer.
5. On temporary infrastructure failure, do not commit; retry within the delivery/run budget.
6. On deterministic validation failure, commit only after durable quarantine succeeds.

A crash before offset commit may redeliver; event/source identity and database constraints make that safe.

## Output contract: `entity.temporal_history.published`

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `tenant_id` / `entity_id` | string | yes | Stable scope and key. |
| `publication_id` | string | yes | Immutable verified history publication. |
| `history_revision` | uint64 | yes | Monotonic entity-local publication revision. |
| `source_cut_id` | string | yes | Exact accepted source prefix. |
| `source_cut_fingerprint` | string | yes | Canonical cut hash. |
| `policy_version` / `policy_fingerprint` | string | yes | Governed computation. |
| `schema_versions` | map | yes | Window/feature/publication versions. |
| `history_fingerprint` | string | yes | Full deterministic history fingerprint. |
| `window_count` | uint64 | yes | Expected and verified count. |
| `changed_window_count` | uint64 | yes | Reused revisions are not counted as changed. |
| `feature_record_count` | uint64 | yes | Aligned feature count. |
| `completeness` | enum | yes | `complete` or `incomplete`; only complete candidates are published in the initial contract. |
| `occurred_at` | timestamp | yes | Operational event time, excluded from semantic fingerprint. |
| `run_id` | string | yes | Operational trace. |
| `investigation_ids` | repeated string | no | Process-centric lineage only. |
| `region` | string | yes | Tenant home-region routing. |

## Output contract: `entity.temporal_history.revised`

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| Shared publication fields | as above | yes | Same source cut, policy, schema, and history-fingerprint contract. |
| `reason` | enum | yes | `late_event`, `coverage_advance`, `policy_change`, `rebuild`, or `recovery`. |
| `changed_windows` | repeated window change | yes | Only effective revisions created/reused because of this publication. |
| `reused_window_count` | uint64 | yes | Count of unchanged carried-forward windows. |
| `dependency_root_window_keys` | repeated string | yes | Late-data roots, when applicable. |
| `reconciliation_result_id` | string | yes | Must identify a passed immutable result. |
| `last_valid_publication_id` | string | yes | Prior valid publication retained. |

Each `changed_window` contains window bounds, old/new revision IDs, window fingerprint, reason, and provenance manifest reference. It contains no raw evidence.

## Keying and ordering

- Kafka key is a canonical encoding of `(tenant_id, entity_id)`, not entity ID alone.
- Records for one entity are partition-ordered by Kafka for a single partition key.
- Event-time ordering is derived from source fields, never Kafka arrival order.
- One entity's incremental runs serialize through optimistic head updates; independent entities process concurrently.
- A multi-partition/global source cut may include multiple transport positions, but semantic queries use the durable entity-scoped `SourceCut`.
- Consumers must not assume global event-type ordering.

## Publication/outbox ordering

1. Candidate rows and ClickHouse feature rows are written under the run/build identity.
2. Reconciliation passes and is persisted.
3. PostgreSQL promotion, publication row, head/effectivity update, audit, and outbox commit atomically.
4. The outbox relay publishes `published` or `revised` with deterministic event ID.
5. A relay retry may duplicate the event; consumers deduplicate by event ID/publication ID/history fingerprint.

Temporal workflow completion does not publish an event directly; it records the same durable promotion/outbox state.

## Quarantine event

The existing governed quarantine event must include or reference:

- tenant and entity when safely known;
- source/event identity and transport position;
- quarantine record ID/reason code;
- raw digest and immutable payload reference;
- run/attempt context;
- processing time and resolution status.

Raw payload bytes/secret material are not placed in the event body unless a separately governed encrypted transport explicitly requires it; the database/S3 reference remains authoritative.

## Schema evolution

- Add new fields rather than reusing removed field numbers or semantics.
- Never reuse Protobuf field numbers or enum numeric values.
- Preserve unknown fields for transport tolerance, but reject unknown incompatible semantic major versions.
- New enum values must be handled safely by older consumers as `unsupported`/deferred rather than misread.
- Changes to source/window/history fingerprint inputs require a new schema/policy version and do not alter retained records.
- Publication events use a materialization-specific payload schema rather than an unversioned JSON blob.

## Security and isolation

- Reject missing/mismatched envelope tenant before domain work.
- Key, partition, repository, audit, and error paths are tenant-scoped.
- Do not place raw tenant IDs as public API identifiers or global metric labels.
- Size-limit decoded messages, source payloads, evidence references, and repeated fields.
- Malformed Protobuf, contradictory source identity, and policy uncertainty go to durable quarantine; they are not dropped.
- Access-policy decisions for privileged event/admin operations are audited.

## Compatibility with existing consumers

- Existing consumers continue to ignore new optional envelope/payload fields.
- Adding a new projection event type does not alter the `entity.stream.appended` source-event contract.
- The materialization consumer does not mutate or republish the source event as a new truth record.
- Downstream projections may consume published/revised events, but they must still rebuild from the immutable source substrate if their event is lost.
