# Data Model: Temporal Entity Materialization

**Feature**: `014-temporal-materialization`  
**Date**: 2026-09-24  
**Status**: Design artifact; no schema migration or application code implemented

## Model boundary

This model stores approved references and deterministic derived values. It does not copy raw evidence, own identity/admission decisions, or replace feature 012's dynamic-invariant/static-object boundary. Feature 012 remains the lifecycle/topology calculator; this model versions, aligns, persists, and queries its output.

## Relationship overview

```text
SourceRecordIdentity 1 -> * SourceCut membership
MaterializationPolicy 1 -> * MaterializationRun
SourceCut 1 -> * MaterializationRun
MaterializationRun 1 -> * staged WindowRevision
WindowRevision 1 -> * TemporalFeatureRecord
WindowRevision 1 -> 1 ProvenanceManifest
HistoryPublication 1 -> * effective WindowRevision
HistoryPublication 1 -> 1 TemporalHistory
TemporalHistory 1 -> 0..1 active HistoryPublication head
MaterializationRun 1 -> * ReconciliationResult
MaterializationRun 1 -> * QuarantineRecord
QuarantineRecord 1 -> * QuarantineDecision
Materialization action 1 -> * AuditEvent
```

## Invariants

1. Every persisted record is scoped by one non-empty `tenant_id`; every history additionally has one stable `entity_id`.
2. Accepted source records and evidence are immutable. Materialization never updates or deletes them.
3. Each occurrence time belongs to exactly one half-open `[window_start, window_end)` interval.
4. A source identity has one content fingerprint. A conflicting fingerprint is quarantined.
5. Exact replay cannot create a new accepted source record, window revision, publication, or run revision count.
6. Window revisions and provenance manifests are immutable. Only operational publication pointers/effectivity may change.
7. An unchanged window fingerprint reuses the prior revision; a changed fingerprint creates a new monotonic revision.
8. A candidate becomes the active history only after complete reconciliation and an atomic head advancement.
9. Every covered window has explicit lifecycle, completeness, and provenance, whether active or dormant.
10. A feature record references exactly one window revision. Required feature keys have one record per covered window, with an explicit value or unavailable state.
11. Structural values always have `structural_only=true` and cannot carry identity, truth, or source-independence decisions.
12. A prior valid publication remains queryable until governed retention permits removal.
13. Cross-tenant reads, writes, revisions, status, counts, errors, rebuilds, quarantine, and audit access are prohibited and indistinguishable from absence at the API boundary.
14. Operational timestamps, run IDs, retry counts, and physical database IDs never enter deterministic semantic fingerprints.

## `SourceRecordIdentity`

Stable identity and accepted representation of one upstream entity-stream record.

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `tenant_id` | string | yes | Stable tenant; mixed-tenant source batches fail closed. |
| `entity_id` | string | yes | Stable dynamic entity for the materialization scope. |
| `source_namespace` | string | yes | Producer/source namespace; prevents cross-source identity reuse. |
| `source_record_id` | string | yes | Stable producer-scoped source-record identity. |
| `stream_sequence` | integer | yes | Positive, monotonic entity-stream sequence. |
| `event_occurrence_at` | RFC 3339 datetime | yes | Timezone-aware and normalized to UTC. |
| `accepted_at` | RFC 3339 datetime | yes | Durable source acceptance time; not event time. |
| `record_hash` | SHA-256 string | yes | Verified canonical content hash of the accepted source record. |
| `wire_hash` | SHA-256 string | no | Forensic transport/raw-payload hash; never used as semantic identity. |
| `observation_id` | string/null | no | Immutable evidence/observation reference. |
| `evidence_refs` | ordered reference list | yes | Approved typed references only; never embedded content. |
| `schema_version` | string | yes | Version used to interpret the source record. |
| `event_id` | string | yes | Kafka/envelope idempotency identity. |
| `transport_position` | topic/partition/offset/null | no | Forensic position; not the semantic source cut. |

**Identity constraints**

- Unique: `(tenant_id, entity_id, source_namespace, source_record_id)`.
- Unique within an entity stream: `(tenant_id, entity_id, stream_sequence)`.
- Same identity and same `record_hash`: exact duplicate/no-op.
- Same identity and different `record_hash`: `contradictory_source_record` quarantine.
- Missing tenant/entity/source identity or invalid hash: quarantine before candidate mutation.

## `SourceCut`

Immutable manifest of the accepted source knowledge and governed coverage used to build one history candidate.

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `source_cut_id` | content ID | yes | Deterministic fingerprint of the canonical manifest. |
| `tenant_id` | string | yes | Stable tenant. |
| `entity_id` | string | yes | Stable dynamic entity. |
| `cut_ordinal` | integer | yes | Monotonic entity-local publication ordinal used for effectivity. |
| `first_stream_sequence` | integer/null | yes | First accepted sequence represented; null only for an empty initial cut. |
| `last_stream_sequence` | integer | yes | Highest accepted sequence represented. |
| `stream_head` | SHA-256 string | yes | Hash over canonical ordered source hashes through the cut. |
| `head_source_record_id` | string | yes | Source identity at the stream head. |
| `coverage_start` | RFC 3339 datetime | yes | Inclusive start of covered windows. |
| `coverage_end` | RFC 3339 datetime | yes | Exclusive end; persisted so trailing dormancy is deterministic. |
| `source_schema_version` | string | yes | Accepted stream interpretation version. |
| `accepted_record_count` | integer | yes | Non-negative. |
| `event_ids` | ordered string list | yes | Envelope identities represented by the cut. |
| `transport_positions` | ordered reference list | no | Topic/partition/offset evidence, not cut identity. |
| `sealed_at` | RFC 3339 datetime | yes | Operational metadata excluded from fingerprint. |

**Validation**

- All member records have the same tenant/entity/schema.
- The cut is sealed only after every represented record is durably accepted, classified duplicate, or explicitly excluded by policy.
- `coverage_end > coverage_start`.
- The same source records, coverage, and schema produce the same `source_cut_id` regardless of replay time.
- Empty histories are valid only when policy explicitly requests an empty coverage cut; no fabricated genesis identity is created.

## `MaterializationPolicy`

Immutable, governed input to deterministic computation.

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `policy_id` | string | yes | Stable logical policy name. |
| `policy_version` | string | yes | Monotonic governed version. |
| `policy_fingerprint` | SHA-256 string | yes | Hash of all effective settings. |
| `window_duration` | duration | yes | Default `P7D`; must be positive. |
| `window_epoch_anchor` | RFC 3339 datetime | yes | UTC alignment anchor. |
| `lifecycle_parameters` | canonical object | yes | Reuse feature 012 rules/version; no hidden defaults. |
| `minimum_sample_rules` | canonical object | yes | Per-feature sufficiency thresholds. |
| `dependency_rules` | canonical object | yes | Lifecycle/cumulative/feature dependency declarations. |
| `feature_provider_versions` | ordered map | yes | Pinned deterministic provider and algorithm versions. |
| `resource_limits` | canonical object | yes | Maximum input, memory, duration, rows, and concurrency. |
| `retention_policy_version` | string | yes | Governs revisions, audit, and quarantine. |
| `schema_versions` | canonical map | yes | Window, feature, publication, and event schemas. |

Changing any semantic setting requires a new policy version/fingerprint and new window revisions; retained evidence is never reinterpreted in place.

## `ProvenanceManifest`

Trace contract attached to each candidate/window revision and publication.

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `tenant_id` / `entity_id` | string | yes | Stable history scope. |
| `source_cut_id` | string | yes | Exact accepted source prefix. |
| `source_record_range` | start/end sequences | yes | Inclusive accepted range represented by the window. |
| `source_record_ids` | ordered string list | yes | Producer-scoped source identities. |
| `source_record_hashes` | ordered string list | yes | Verified canonical content hashes. |
| `evidence_refs` | ordered typed references | yes | References only; missing/inaccessible evidence is explicit unavailable. |
| `policy_id` / `policy_version` / `policy_fingerprint` | string | yes | Governed computation policy. |
| `schema_version` | string | yes | Materialized record schema. |
| `algorithm_versions` | canonical map | yes | Lifecycle/metric/TDA/reconciliation implementations. |
| `run_id` | string | yes | Operational origin; excluded from semantic value hash. |
| `window_revision_id` | string/null | no | Present for a window manifest. |
| `window_fingerprint` | string/null | no | Present for a window manifest. |
| `history_fingerprint` | string/null | no | Present for a publication/history manifest. |
| `publication_id` | string/null | no | Present after promotion. |

## `WindowRevision`

Immutable version of one covered temporal window.

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `window_revision_id` | content ID | yes | Deterministic window fingerprint identity. |
| `tenant_id` / `entity_id` | string | yes | Stable history scope. |
| `window_start` / `window_end` | RFC 3339 datetime | yes | UTC, aligned, `end > start`, half-open `[start,end)`. |
| `window_key` | string | yes | Deterministic logical identity for the interval. |
| `revision_number` | integer | yes | Positive, monotonic for the window. |
| `parent_window_revision_id` | string/null | yes | Prior effective revision when changed. |
| `window_fingerprint` | SHA-256 string | yes | Full digest of semantic content and provenance inputs. |
| `lifecycle_state` | enum | yes | `nascent`, `growing`, `stable`, `decaying`, `dormant`. |
| `activity` | canonical object | yes | Count/rate/burstiness plus per-value availability and reason. |
| `relationship_summary` | canonical object | yes | Window-specific typed summary; identity resolution excluded. |
| `evidence_references` | ordered typed references | yes | Approved refs/digests only. |
| `completeness` | enum | yes | `complete` or `incomplete`. |
| `completeness_reason` | string/null | yes | Required when incomplete/degraded. |
| `provenance` | `ProvenanceManifest` | yes | Exact source and policy trace. |
| `created_by_run_id` | string | yes | Operational creation record. |
| `created_at` | RFC 3339 datetime | yes | Excluded from semantic fingerprint. |

**Validation**

- Dormant windows have zero admitted event count and no fabricated relationship/feature measurement.
- Incomplete windows expose the latest valid content and reason; they are never presented as current complete state.
- Identical `window_fingerprint` reuses the existing revision, including across runs and rebuilds.
- Static objects, malformed tenant/entity input, and mixed histories cannot produce a revision.

## `TemporalFeatureRecord`

One deterministic feature value or explicit unavailable state aligned to one window revision.

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `feature_record_id` | content ID | yes | Deterministic from feature/window/provenance identity. |
| `tenant_id` / `entity_id` | string | yes | Same scope as window revision. |
| `window_revision_id` | string | yes | Exactly one immutable window revision. |
| `feature_name` | string | yes | Versioned governed feature key. |
| `feature_kind` | enum | yes | `lifecycle`, `activity`, `relationship`, or `structural`. |
| `value_type` | enum | yes | `number`, `integer`, `boolean`, `categorical`, `vector`, or `none`. |
| `value` | canonical value/null | yes | Null only with `available=false`. |
| `availability` | enum | yes | `available` or `unavailable`. |
| `unavailable_reason` | string/null | yes | Required when unavailable. |
| `structural_only` | boolean | yes | True for every topology/persistence-derived value. |
| `minimum_samples` | integer | yes | Policy-declared requirement. |
| `sample_count` | integer | yes | Actual sample count. |
| `input_fingerprint` | SHA-256 string | yes | Exact normalized feature input. |
| `provider_id` / `provider_version` | string | yes | Pinned deterministic provider. |
| `provenance` | `ProvenanceManifest` | yes | Includes cut, policy, schema, source records, and fingerprints. |

**Availability rules**

- A measured numeric `0` has `availability=available` and `value=0`.
- Missing/insufficient/provider-unavailable data has `availability=unavailable`, `value=null`, and a non-empty reason.
- Dormancy is represented explicitly in the window; it is not a fabricated feature measurement.
- Structural records cannot expose identity resolution, truth, or source-independence fields.

## `HistoryPublication`

Immutable manifest for one verified set of effective window revisions at a source cut.

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `publication_id` | content ID | yes | Deterministic history fingerprint identity. |
| `tenant_id` / `entity_id` | string | yes | Stable history scope. |
| `source_cut_id` | string | yes | Exact source manifest. |
| `cut_ordinal` | integer | yes | Entity-local effectivity ordinal. |
| `policy_fingerprint` | SHA-256 string | yes | Governed policy. |
| `schema_versions` | canonical map | yes | All participating record schemas. |
| `history_fingerprint` | SHA-256 string | yes | Ordered effective window revision identities plus cut/completeness. |
| `completeness` | enum | yes | `complete` or `incomplete`. |
| `completeness_reason` | string/null | yes | Required when incomplete. |
| `reconciliation_result_id` | string | yes | Must be successful before promotion. |
| `created_by_run_id` | string | yes | Operational origin. |
| `created_at` / `promoted_at` | RFC 3339 datetime | yes | Excluded from semantic fingerprint. |
| `superseded_at` | RFC 3339 datetime/null | no | Operational; prior publication remains queryable. |

## Window effectivity and active head

To avoid copying every unchanged window on every event, changed windows are stored once and mapped to cut ranges.

### `WindowEffectivity`

| Field | Type | Rules |
| --- | --- | --- |
| `tenant_id` / `entity_id` | string | Tenant-scoped history/window key. |
| `window_key` | string | Logical window identity. |
| `from_cut_ordinal` | integer | Inclusive first publication cut. |
| `to_cut_ordinal` | integer/null | Exclusive next effective cut; null means current. |
| `window_revision_id` | string | Immutable effective content. |
| `publication_id` | string | Publication that installed the interval. |

**Rules**

- At most one effectivity interval can cover a given window and cut ordinal.
- A promotion closes the prior interval and opens the new interval in the same PostgreSQL transaction.
- Old intervals are retained and never updated to change content.
- Point-in-time history is reconstructed by selecting each window interval effective at the requested publication cut.

### `TemporalHistoryHead`

| Field | Type | Rules |
| --- | --- | --- |
| `tenant_id` / `entity_id` | string | One mutable current-head row per history. |
| `active_publication_id` | string/null | Last successfully promoted publication. |
| `active_cut_ordinal` | integer | Optimistic concurrency token. |
| `latest_source_cut_id` | string | Newest sealed source cut observed, even if not promoted. |
| `status` | enum | `current`, `delayed`, `rebuilding`, `degraded`, `quarantined`, `incomplete`. |
| `status_reason` | string/null | Actionable reason. |
| `latest_accepted_at` | RFC 3339 datetime/null | Freshness calculation. |
| `active_run_id` | string/null | Current incremental/rebuild activity. |
| `heartbeat_at` | RFC 3339 datetime | Worker liveness. |
| `updated_at` | RFC 3339 datetime | Operational metadata. |

The active publication remains readable when `latest_source_cut_id` is newer but delayed, rebuilding, degraded, quarantined, or incomplete.

## `MaterializationRun`

Auditable incremental or rebuild execution.

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `run_id` | UUID/string | yes | Operational execution identity. |
| `idempotency_key` | string | yes | Unique per tenant/operation scope. |
| `mode` | enum | yes | `incremental` or `rebuild`. |
| `trigger` | enum | yes | `source_event`, `coverage_advance`, `operator`, `policy_change`, or `recovery`. |
| `tenant_id` / `entity_id` | string | yes | Stable history scope. |
| `investigation_id` | string/null | yes | Lineage/policy/access scope, not storage identity. |
| `requested_by` | actor/principal | yes | Authenticated initiator. |
| `source_cut_id` | string | yes | Fixed input cut. |
| `policy_fingerprint` | string | yes | Fixed policy. |
| `schema_versions` | map | yes | Fixed schemas. |
| `status` | enum | yes | See state machine below. |
| `safe_point` | canonical object/null | yes | Durable source/window/checkpoint position. |
| `attempt_counts` | budget map | yes | Task/source/entity/investigation/global counters. |
| `expected_summary` | canonical object/null | yes | Expected windows/counts/fingerprint inputs. |
| `actual_summary` | canonical object/null | yes | Actual candidate summary. |
| `status_reason` | string/null | yes | Required for delayed/degraded/failed/quarantined states. |
| `started_at` / `heartbeat_at` / `finished_at` | datetime/null | yes | Operational only. |

## `ReconciliationResult`

Immutable result proving a candidate is safe to promote.

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `reconciliation_result_id` | string | yes | Run/build-scoped identity. |
| `run_id` | string | yes | Owning run. |
| `source_cut_id` | string | yes | Expected source manifest. |
| `expected_window_count` | integer | yes | Non-negative. |
| `actual_window_count` | integer | yes | Must equal expected for complete promotion. |
| `missing_windows` | window-key list | yes | Must be empty for promotion. |
| `extra_windows` | window-key list | yes | Must be empty for promotion. |
| `divergent_windows` | comparison list | yes | Must be empty for promotion. |
| `expected_history_fingerprint` | SHA-256 string | yes | Deterministic candidate. |
| `actual_history_fingerprint` | SHA-256 string | yes | Must match. |
| `feature_alignment_errors` | reference list | yes | Must be empty. |
| `clickhouse_checksum` | string/null | yes | Required when feature publication is enabled. |
| `outcome` | enum | yes | `passed`, `failed`, or `incomplete`. |
| `completed_at` | datetime | yes | Operational. |

Only `outcome=passed` permits publication promotion.

## `QuarantineRecord` and `QuarantineDecision`

Durable retained representation of rejected, ambiguous, policy-uncertain, contradictory, malformed, or exhausted work.

### `QuarantineRecord`

| Field | Type | Rules |
| --- | --- | --- |
| `quarantine_id` | content ID | Stable fingerprint of source identity/context/reason. |
| `tenant_id` / `entity_id` | string/null | Tenant required; entity may be unknown for malformed input. |
| `run_id` | string/null | Processing context. |
| `source_record_id` | string/null | Original producer identity when available. |
| `source_record_hash` / `wire_hash` | string/null | Original representation integrity. |
| `source_payload_ref` | S3 reference/null | Approved immutable retained reference. |
| `source_position` | reference/null | Event/transport provenance. |
| `reason_code` | enum | Actionable governed reason. |
| `reason_detail` | string | Sanitized detail; no secrets/raw content. |
| `first_quarantined_at` / `last_seen_at` | datetime | Retention/audit. |
| `attempt_count` | integer | Bounded by retry policy. |
| `status` | enum | `open`, `under_review`, `replay_requested`, `resolved`, `rejected`. |
| `resolution_run_id` | string/null | Later replay/re-evaluation. |

### `QuarantineDecision`

Append-only decisions: `observed`, `released`, `rejected`, `superseded`, or `resolved`. A replay never deletes or rewrites the original record.

**Reason codes**

`missing_tenant`, `mixed_tenant`, `mixed_entity`, `missing_source_record_id`, `ambiguous_timestamp`, `unknown_stream_kind`, `non_dynamic_entity`, `contradictory_source_record`, `unsupported_schema_version`, `unknown_materialization_policy`, `resource_limit_exceeded`, `provenance_incomplete`, `fingerprint_mismatch`, `retry_budget_exhausted`.

## `TemporalHistory` query model

A read-only aggregate assembled for a selector.

| Field | Type | Rules |
| --- | --- | --- |
| `tenant_id` / `entity_id` | string | Authenticated tenant scope and stable entity. |
| `selector` | canonical selector | `latest`, event-time + source cut/revision, source cut, or revision. |
| `publication_id` | string | Exact published version. |
| `source_cut` | `SourceCut` | Never null. |
| `history_revision` | integer | Monotonic publication ordinal/revision. |
| `status` | enum | Current/delayed/rebuilding/degraded/quarantined/incomplete as of request time. |
| `is_latest_valid` | boolean | True only for the last valid publication. |
| `completeness` | enum | `complete` or `incomplete`. |
| `windows` | ordered `WindowRevision` list | Chronological, no gaps, no overlaps. |
| `features` | ordered feature records | Aligned to window revisions. |
| `provenance` | publication manifest | Exact source/policy/schema/fingerprints. |
| `verification_fingerprint` | SHA-256 string | History fingerprint. |

**Point-in-time selection**

1. `latest`: load the active head and its immutable publication.
2. `source_cut_id`: load the publication for that exact sealed cut.
3. `revision`: load the requested immutable publication within the tenant/entity history.
4. Event-time point: first resolve the allowed source cut/revision, then select the single window where `start <= at < end`.
5. Select every window effectivity interval effective at the publication cut and verify the ordered set matches the publication fingerprint.
6. Attach feature rows by exact window revision IDs; unavailable state remains explicit.
7. Never fall forward to a newer source cut when a requested historical cut/revision is unavailable.

## Fingerprint definitions

| Fingerprint | Canonical input | Excludes |
| --- | --- | --- |
| Source content | Schema version, tenant/entity, source identity, normalized occurrence time, semantic payload, evidence refs | Arrival time, transport position, retry count. |
| Feature | Feature/provider versions, normalized input, sample/policy rules, value or unavailable reason | Random IDs, wall clock, provider installation details. |
| Window | Logical window, contributing source identities/hashes, lifecycle/activity/relationship/evidence/completeness content, aligned feature identities, policy/schema versions | Run/publication time, activity count, database IDs, CH part/merge state. |
| History | Source cut, policy/schema versions, completeness, ordered effective window revision identities | Number of unchanged events, worker count, Temporal run ID. |

Canonicalization uses versioned canonical JSON, sorted mapping keys, stable ordered lists, UTC RFC 3339 timestamps, explicit absent/null handling, normalized Unicode/numeric values, and full SHA-256 digests.

## State transitions

### `MaterializationRun`

```text
queued -> running -> staged -> reconciling -> promoting -> completed
   |         |          |           |             |
   +---------+----------+-----------+-------------+-> cancelled/failed
                                                    |
                                                    +-> quarantined (blocked input)
```

- `failed`/`quarantined` never advances the active head.
- Resuming a failed run creates/continues the same idempotent operation and safe point.
- A stale concurrent candidate transitions to `failed` with `stale_head` or restarts from the newer cut; it never silently merges.

### `TemporalHistoryHead`

```text
current <-> delayed
current/delayed -> rebuilding -> current
current/delayed/rebuilding -> degraded -> current
any state -> quarantined -> current/degraded
any state -> incomplete -> current/degraded
```

The underlying active publication does not disappear when status changes to `delayed`, `rebuilding`, `degraded`, `quarantined`, or `incomplete`.

### `TemporalFeatureRecord` availability

```text
available(value, including measured zero)
unavailable(reason)
```

The state never changes without a new window revision and aligned feature record.

### Quarantine decision

```text
open -> under_review -> replay_requested -> resolved
                         |                |
                         +-> rejected <---+
```

Decisions are append-only; status is a projection of the decision history.

## Physical mapping and scale

- PostgreSQL owns `SourceCut`, `MaterializationRun`, `ReconciliationResult`, `WindowRevision`, `ProvenanceManifest`, `HistoryPublication`, `WindowEffectivity`, `TemporalHistoryHead`, quarantine/audit/outbox, and the exact query path.
- ClickHouse owns append-oriented `TemporalFeatureRecord` revisions and a disposable current projection.
- S3 owns raw evidence and approved derived spill/manifest objects only.
- Kafka/Temporal run IDs are references, not business revision identity.
- Use a small fixed number of shared/partitioned tables, not one table per entity or window.
- Partition high-volume ClickHouse data by governed time windows and order by tenant/entity/window/feature/revision.
- Use cut-range effectivity so an unchanged window is not duplicated for every source event.
- Use tenant-leading indexes/RLS and bounded JSON/reference payloads; large non-query payloads may use content-addressed S3 references.

## Retention

- Evidence and accepted source records follow existing evidence-retention policy.
- Published window revisions, feature revisions, source cuts, audit, and required replay history remain available for the governed audit/dispute/reproducibility horizon.
- Operational run logs may compact only when all referenced publication, audit, quarantine, and safe-point records remain recoverable.
- ClickHouse bulk data may expire earlier only when it is rebuildable and an unavailable/expired response is explicit; no current-view fallback may masquerade as a historical answer.
- Derived failure never deletes evidence or the last valid publication.
