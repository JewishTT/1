# Service Contracts: Temporal Materialization

**Feature**: `014-temporal-materialization`  
**Contract version**: `temporal-materialization/v1`  
**Status**: Design artifact; interfaces are not implemented

## Purpose

Define the vendor-neutral boundaries used by the deterministic materialization engine, persistence adapters, incremental consumer, Temporal rebuild workflow, API, and ClickHouse feature projection.

## Contract rules

1. Pure domain operations accept and return shared frozen contracts only. They cannot import Kafka, PostgreSQL, ClickHouse, Temporal, FastAPI, SQLAlchemy rows, generated Protobuf classes, or web types.
2. Every operation is tenant- and entity-scoped. A missing tenant is a validation error; a foreign tenant/entity is not resolved through a global lookup.
3. Every externally triggered operation has an idempotency identity. Replaying it with the same accepted input produces the same business state and fingerprints.
4. Operational execution metadata may be returned but is excluded from source/window/publication semantic fingerprints.
5. All evidence and source payloads are references/digests. Raw content never crosses this boundary.
6. Errors are typed and stable. Callers must not infer state from message text.

## Pure domain operations

| Operation | Input | Output | Required behavior |
| --- | --- | --- | --- |
| `seal_source_cut` | Tenant, entity, accepted source prefix, governed coverage end, schema | Immutable `SourceCut` | Verify stable identity/hash, sort canonically, seal exact stream head and coverage. |
| `validate_source_record` | Candidate `StreamRecord` and entity policy | Accepted disposition or typed rejection | Reject mixed tenant/entity, invalid timestamp/hash, static/non-dynamic source, missing identity, or schema uncertainty. |
| `classify_source_reuse` | Source identity, existing content fingerprint, incoming fingerprint | `accepted`, `exact_duplicate`, or `contradictory` | Never infer source identity from payload equality alone. |
| `build_candidate` | `SourceCut`, `MaterializationPolicy`, accepted records, feature-provider results | Ordered candidate windows/features and dependencies | Cover every window through `coverage_end`; use half-open UTC windows; mark gaps dormant; expose unavailable values explicitly. |
| `compute_affected_closure` | Late source record and published dependency graph | Ordered affected window keys | Include the record's window, later lifecycle carry-forward, and declared cumulative/feature dependencies. |
| `compare_candidate` | Candidate and currently effective history | Added/changed/unchanged window sets | Compare canonical fingerprints; never compare arrival timestamps to decide semantic equality. |
| `reconcile_candidate` | Candidate, source cut, policy, expected coverage | `ReconciliationResult` | Detect every missing, extra, divergent, misaligned, or mismatched-fingerprint window/block publication. |
| `compute_point_in_time_view` | Tenant/entity plus `latest`, source cut, revision, or event-time selector | `TemporalHistory` | Resolve only published data and never fall forward to a newer source cut. |
| `compute_health` | Durable head, runs, source age, reconciliation state | `MaterializationHealth` | Distinguish last-valid publication from current processing health. |

## Canonicalization contract

The versioned canonicalizer must:

- use sorted object keys and explicit list ordering;
- represent timestamps as UTC RFC 3339 values;
- distinguish an absent field from an explicit null where semantics differ;
- define Unicode, decimal/float, negative zero, NaN, and infinity handling;
- hash the full SHA-256 digest;
- use `none` as the first hash member to domain-separate source, feature, window, and history fingerprints;
- exclude run IDs, wall-clock timestamps, retries, database IDs, Kafka positions, Temporal IDs, and ClickHouse merge state.

## Feature provider contract

A `FeatureProvider` receives a pinned, normalized window input and returns versioned feature records or typed unavailable reasons.

**Input**

- tenant/entity and exact window revision candidate identity;
- source cut and contributing source record refs/hashes;
- normalized activity/relationship input;
- policy fingerprint and minimum samples;
- provider ID/version and resource limits.

**Output**

- zero or more named feature values;
- each value has `available=true` and a typed value, or `available=false`, null value, and actionable reason;
- `structural_only=true` for topology/persistence-derived features;
- normalized input fingerprint, provider/version, and complete provenance;
- no identity, truth, source-independence, or raw-evidence fields.

**Failure classes**

- `insufficient_data`: deterministic unavailable result, not a system failure.
- `unsupported_feature`: deterministic unavailable result for the pinned provider/version.
- `resource_limit_exceeded`: candidate fails or uses governed bounded fallback; never fabricates a value.
- `provider_infrastructure_error`: transient run failure within retry budget.
- `deterministic_provider_error`: candidate fails and is quarantined/degraded; no repeated infinite retry.

## Source port

The source adapter must provide:

- durable accepted records through a requested source cut;
- transport/provenance references without making transport position semantic;
- exact duplicate and contradictory identity lookup;
- stable paging ordered by `(stream_sequence, source_record_id, record_hash)`;
- bounded page size/bytes;
- tenant/entity-scoped existence behavior.

A source read may not skip an unclassified record inside a sealed cut.

## Revision and publication store ports

The store must provide these logical operations:

| Operation | Atomicity requirement |
| --- | --- |
| `begin_or_get_run` | Idempotent by tenant/mode/idempotency key/source cut/policy. |
| `stage_window_revision` | Insert immutable revision or return the existing identical fingerprint. |
| `stage_feature_revision` | Require an existing window revision and exact one-to-one feature identity. |
| `record_safe_point` | Monotonic per run; never move backward. |
| `record_reconciliation` | Insert immutable result; promotion requires `passed`. |
| `promote_candidate` | In one PostgreSQL transaction: close superseded effectivity, open new intervals, insert publication, advance head, append audit/outbox. |
| `load_effective_history` | Exact point-in-time query scoped to tenant/entity/publication cut. |
| `load_features` | Exact window revision IDs with explicit feature unavailability. |

Promotion uses optimistic concurrency against `active_cut_ordinal`; a stale candidate cannot overwrite a newer head.

## Run/checkpoint port

- Business safe points are persisted outside Temporal history.
- A safe point contains source sequence/page, covered window, staged revision cursor, and last committed candidate chunk.
- Safe-point writes are monotonic and idempotent.
- Interrupted processing resumes from the last committed safe point.
- Retry counters are persisted and partitioned by task, source, entity/investigation, tenant, and global budget.

## Feature-series store port

- Append all verified feature revisions; do not mutate them.
- Deduplicate exact replay using stable build/revision identity and insert token where available.
- Query historical features by exact window revision IDs.
- Build a clearly marked current projection separately if useful.
- Publication is promoted in PostgreSQL only after feature-store verification succeeds.
- ClickHouse failure leaves the last valid publication available and creates recoverable projection lag.

## Audit port

Append an audit decision for:

- run request/admission/rejection;
- publication, revision, promotion, and supersession;
- reconciliation pass/failure;
- quarantine/rejection/replay/resolution;
- privileged access and denied access-policy decision;
- policy/config change affecting materialization.

Audit entries are tenant-scoped, append-only, and include actor/principal, action, reason, time, entity, revision/publication/run, source cut, and policy/schema versions.

## Outbox/event publisher port

- Output events are written to a transactional outbox in the same PostgreSQL transaction as promotion.
- An idempotent relay may publish duplicates, so consumers use event IDs and business fingerprints.
- Publishing occurs only after commit.
- Publication success is tracked independently; event delivery failure does not roll back a valid head.

## Incremental service contract

`materialize_incremental(context, source_trigger, idempotency_key)` must:

1. validate the trigger and resolve its accepted source record;
2. create or retrieve the idempotent run;
3. seal the newest entity source cut/coverage;
4. build the deterministic candidate;
5. calculate the dependency closure and compare fingerprints;
6. stage changed windows/features and reconcile the full candidate;
7. promote only after all checks pass;
8. preserve the last valid publication on any failure;
9. record audit/outbox/health state;
10. classify malformed/contradictory/policy-uncertain input as durable quarantine rather than transient retry.

A repeated request with the same identity is a no-op and does not advance revision/publication numbers.

## Rebuild service contract

`rebuild(context, source_cut_selector, policy_selector, idempotency_key)` must:

- use a stable, explicit source cut rather than live tailing data;
- accept bounded entity/window/time/record batches;
- stage under a run/build identity;
- persist resumable safe points;
- reconcile the complete candidate before promotion;
- compare two independent rebuild fingerprints for deterministic validation;
- never publish candidates from stale head state;
- retain failed/cancelled candidate diagnostics.

Temporal workflow code calls these deterministic activities. Business logic does not live in workflow replay code.

## Error model

| Error type | Retry class | Caller behavior |
| --- | --- | --- |
| `validation_error` | Non-retryable | Reject request/record; quarantine where source-triggered. |
| `tenant_mismatch` | Non-retryable | Fail closed with non-disclosing response. |
| `entity_mismatch` | Non-retryable | Fail closed. |
| `source_identity_conflict` | Non-retryable | Quarantine contradictory representation. |
| `unsupported_schema/policy` | Non-retryable | Quarantine or reject with version information. |
| `stale_candidate` | Re-plan | Restart from current head/newer cut; do not overwrite. |
| `temporary_store_error` | Bounded transient retry | Preserve run/safe point. |
| `downstream_timeout` | Bounded transient retry | Preserve last valid publication. |
| `retry_budget_exhausted` | Terminal/quarantine | Record actionable quarantine/degraded state. |
| `reconciliation_failed` | Terminal for candidate | Do not promote; expose run reason. |
| `retention_expired` | Terminal read error | Return explicit unavailable; never substitute current data. |

## Version compatibility

- Domain records carry explicit schema and policy versions.
- Additive optional fields are allowed only under a new schema version or documented compatibility rule.
- Field removal, semantic changes, and hash-input changes require a new contract/version.
- Readers reject unknown semantic major versions rather than guessing.
- Historical revisions remain readable with their original versions after the latest reader is deployed.
