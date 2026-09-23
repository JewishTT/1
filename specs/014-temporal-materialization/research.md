# Research: Temporal Entity Materialization

**Feature**: `014-temporal-materialization`  
**Research date**: 2026-09-24  
**Status**: Resolved; no outstanding clarifications

## Inputs and repository findings

- Completed specification: `specs/014-temporal-materialization/spec.md`.
- Constitution: `.specify/memory/constitution.md`.
- Feature 011 plan/spec/tasks and implementation.
- Feature 012 specification/data model and implementation.
- Existing event, entity-stream, storage, workflow, API, observability, test, and deployment conventions.
- Platform documentation for PostgreSQL, ClickHouse, Kafka, Temporal, S3, Protobuf, and event-time processing.

## Resolved design unknowns

| Unknown | Resolution |
| --- | --- |
| What is authoritative? | Accepted `entity_stream` records plus their immutable evidence references remain authoritative. Temporal materialization is a rebuildable projection. |
| What identifies source knowledge? | An entity-scoped immutable `SourceCut` sealed from the accepted stream head, source range, governed coverage end, and source schema. |
| How are point-in-time views selected? | By published source cut, publication revision, or event-time point within a published cut; later records never enter an earlier cut. |
| How are late data and duplicates handled? | Replay an entity candidate from a fixed cut, compare canonical window fingerprints, revise only the dependency closure, quarantine contradictions, and make exact replay a no-op. |
| Which store owns each concern? | PostgreSQL owns exact revisions, publication pointers, runs, effectivity, audit, and quarantine. ClickHouse owns rebuildable aligned feature-series rows. S3 retains immutable evidence and optional spill/manifests. |
| How is publication made safe? | Stage candidates, reconcile expected versus actual windows, verify history/window fingerprints, then atomically advance a PostgreSQL publication pointer. Cross-store publication is pointer-based, not a distributed transaction. |
| What does Temporal orchestrate? | Explicit long-running rebuilds and bounded batch activities only. Kafka remains the continuous incremental trigger and source backbone. |
| How are gaps and trailing dormancy represented? | Coverage is a governed, persisted input to each source cut. Every covered half-open window is explicit; empty covered windows are dormant and feature values are explicitly unavailable when required. |
| How are feature values represented? | Every covered window has aligned feature records. `available=false` plus a reason is distinct from a measured numeric zero; structural values always carry `structural_only=true`. |
| Which dependency surfaces are required? | Shared pure contracts, PostgreSQL repositories, a Kafka consumer, ClickHouse feature adapter, FastAPI endpoints, existing React timeline, Temporal worker, telemetry, and deployment/migration paths. |
| How is rollout controlled? | Additive migrations, shadow mode, tenant/home-region allowlists, backfill cohorts, canary reads, and application-level rollback while retaining prior valid revisions. |

## R-001: Source authority and storage split

**Decision**

- Use accepted `EntityStreamRow`/`StreamRecord` data as the materialization input authority, with observation and evidence references remaining in their existing S3-backed substrate.
- Use PostgreSQL for exact, transactionally consistent history metadata: source-cut manifests, run/safe-point state, immutable window revisions, publication/effectivity records, active heads, audit, and durable quarantine decisions.
- Use ClickHouse only for high-volume, rebuildable temporal feature-series projections.
- Use Kafka to trigger incremental work, Temporal to coordinate explicit rebuilds, and Neo4j/search only for rebuildable current-state projections.

**Rationale**

The constitution requires projection-first architecture and explicitly rejects a universal store. PostgreSQL provides the uniqueness, transaction, concurrency, and point-in-time query primitives needed to make publication exact. ClickHouse is suited to aligned analytical scans but its background merges and limited cross-table transactional guarantees make it unsuitable as the revision or publication authority. S3 remains the immutable evidence substrate and may hold large derived artifacts, not competing business records.

**Alternatives considered**

- ClickHouse as the history authority: rejected because exact revision uniqueness, publication atomicity, and prior-revision retention are stronger concerns than aggregate scan throughput.
- Neo4j as point-in-time authority: rejected because the graph is a current relational projection and does not express source cuts or immutable materialization revisions.
- Temporal history as the data ledger: rejected because workflow history is execution metadata with retention and versioning constraints.
- One JSON document per entity: rejected because it duplicates unchanged windows on every revision and prevents indexed, auditable window queries.

## R-002: Source-record identity and source cuts

**Decision**

Add a required, producer-scoped `source_record_id` to the materialization-ready entity-stream contract. A materialization source record is identified by `(tenant_id, entity_id, source_record_id)` and content-addressed by its verified canonical `record_hash`.

Disposition rules are:

1. Same source identity and same content fingerprint: exact duplicate; create no accepted event, window revision, or revision count change.
2. Same source identity and different content fingerprint: contradictory reuse; quarantine both references to the conflict and do not alter accepted history.
3. Different source identity with identical content: preserve according to source policy; payload equality alone is not identity.
4. Missing tenant, entity, source identity, or an unverifiable hash: quarantine before candidate mutation.

Define an entity-scoped `SourceCut` as an immutable manifest containing:

- tenant and dynamic-entity identity;
- first and last accepted stream sequence;
- `stream_head` over canonical ordered source hashes;
- stable source-record identity for the head;
- governed `coverage_end` used to define covered trailing windows;
- source/event schema version;
- optional topic, partition, and offset as forensic transport metadata;
- deterministic `source_cut_id`.

The semantic cut is the durable accepted stream prefix, not Kafka merge order, a ClickHouse timestamp, Temporal execution identity, or a local wall clock.

**Rationale**

A record hash proves content but cannot detect the same source identity being reused with different content. Late event time cannot be represented by a timestamp cut. Kafka ordering is per partition and consumer offsets describe one projection's progress, not global knowledge. A durable entity-stream prefix is recoverable from the existing authoritative substrate and gives exact bitemporal behavior.

**Alternatives considered**

- Record hash as source identity: rejected because equal content may be delivered by different legitimate records and conflicting content cannot be distinguished.
- Maximum timestamp as the cut: rejected because records can be late or future-dated.
- Kafka offset alone: rejected because partitions, retention, replay, and multiple consumers make it a transport position rather than durable domain knowledge.
- `created_at` alone: rejected because clock skew and concurrent transactions do not define a reproducible source set.

## R-003: Window coverage and lifecycle

**Decision**

- Reuse feature 012's `window_bounds`, `LifecycleState`, `TemporalSlice`, lifecycle derivation, topology blocks, and canonical hashing.
- Use epoch-aligned half-open `[start, end)` windows with a governed default duration of seven days.
- Materialize from the first accepted event window through the source cut's explicit `coverage_end` window.
- Represent every covered empty window as `dormant`; do not interpolate, skip, or emit inferred activity.
- Treat `coverage_end` as a persisted source/policy input so a replay of the same source set, policy, and schema is byte-for-byte stable.
- Assign a valid late or future-dated record to its occurrence-time window. Arrival order never changes window assignment.
- Do not create independent histories for static objects or non-dynamic occurrences.

**Rationale**

Feature 012 already pins half-open boundaries, lifecycle states, honest burstiness unavailability, dormant interior windows, and deterministic hashes. It does not currently define explicit coverage end, trailing dormancy, per-window source manifests, or persisted revisions, so feature 014 wraps rather than forks those rules.

**Alternatives considered**

- Calendar-local windows: rejected because timezone/DST behavior would make policy ambiguous.
- Filled time-series from an analytics library: rejected because it obscures explicit dormancy and unavailable values.
- Extending history indefinitely from local time: rejected because wall-clock time would make rebuild fingerprints differ.
- Treating future occurrence data as an identity decision: rejected; source assignment is deterministic and does not authorize identity claims.

## R-004: Canonical identity and verification fingerprints

**Decision**

Use a versioned canonical JSON fingerprint contract with sorted mapping keys, stable ordered lists, UTC RFC 3339 timestamps, explicit absent-versus-null semantics, fixed numeric normalization, Unicode normalization, and SHA-256. Store the full digest.

Separate identities:

- **Source record identity**: stable producer/source identity.
- **Content fingerprint**: hash of normalized accepted source content.
- **Window revision identity**: hash of logical window, contributing source identities/hashes, canonical materialized content, policy/schema versions, and aligned feature values.
- **Publication fingerprint**: hash of the source cut, policy/schema versions, completeness state, and the ordered effective window revision identities.
- **Wire hash**: retained separately for forensic transport integrity and never used as the semantic fingerprint.

Exclude wall-clock processing time, run/activity IDs, retry counts, database physical IDs, random UUIDs, and ClickHouse merge order from semantic fingerprints. A logical window revision number is assigned monotonically only when its content fingerprint changes; reusing a fingerprint reuses the prior revision.

**Rationale**

Determinism and auditability require a hash contract independent of Protobuf wire encoding, worker count, processing order, and infrastructure identity. Random feature IDs and hashes over only output values cannot prove which source records, policy, and cut produced a view.

**Alternatives considered**

- Hash serialized Protobuf bytes: rejected because Protobuf serialization is not a canonical semantic encoding.
- UUID feature IDs: rejected because replay creates different identities for identical values.
- Include publication time in the fingerprint: rejected because equivalent replays would diverge.
- Replacing all history with a timestamp version: rejected because equal event-time timestamps do not establish deterministic conflict precedence.

## R-005: Late data, dependency closure, and revisions

**Decision**

For every new source cut:

1. Seal the accepted source prefix and coverage end.
2. Replay the entity candidate deterministically from that cut.
3. Build a dependency declaration for each window under the materialization policy.
4. Recompute the late event's window and its declared dependent closure, including later lifecycle windows and cumulative features that depend on earlier windows.
5. Compare candidate window fingerprints to the currently effective revisions.
6. Stage only changed windows; carry forward identical effective revisions.
7. Reconcile the full candidate before promotion.
8. Create a new publication revision and advance the entity head atomically in PostgreSQL.

Prior revisions and prior cut-to-revision effectivity remain queryable. Concurrent rebuilds use optimistic head/cut ordinals; a stale candidate cannot overwrite a newer valid head and must restart from its recorded cut.

**Rationale**

Feature 012 lifecycle transitions depend on the preceding window, and feature 011 cumulative/topological features may depend on earlier series. A late event cannot safely update only its own window. Comparing fingerprints, rather than timestamps, ensures unaffected windows remain unchanged and exact retries create no revision.

**Alternatives considered**

- Append a late event to ingestion time: rejected because it corrupts event-time analysis.
- Update the event-time window in place: rejected because it mutates previously valid history.
- Recompute and replace every historical view on every late event: correct but creates avoidable revisions and publication cost.
- Reject all records after a watermark: rejected because lateness is not invalidity.

## R-006: Publication, reconciliation, and ClickHouse consistency

**Decision**

Use a staged build/publication protocol:

1. Create a `MaterializationRun` and deterministic run idempotency key.
2. Build candidate window revisions and aligned feature rows under the run/build identity.
3. Check source-cut coverage, expected window set, revision uniqueness, per-window fingerprints, history fingerprint, feature/window one-to-one alignment, and CH row counts/checksums.
4. Write an immutable reconciliation result and completion manifest.
5. In one PostgreSQL transaction, close superseded effectivity ranges, insert the new publication manifest, advance the history head, append audit/outbox records, and commit the source trigger's durable state.
6. Publish output events from the transactional outbox only after commit.
7. Keep the last valid publication readable if the candidate fails.

Use an append-oriented ClickHouse `MergeTree` table for all published feature revisions. Exact duplicate inserts are suppressed by the stable build/revision identity and ClickHouse insert token where supported. A separate `ReplacingMergeTree` current view may be maintained as a disposable read optimization, with explicit final/argmax semantics, but it is not audit history or the publication authority.

**Rationale**

ClickHouse merges are eventual and do not provide a global transaction with PostgreSQL. A PostgreSQL publication pointer is the application-level atomic boundary. Reconciliation must compare against deterministic PostgreSQL candidate/source state rather than trusting ClickHouse `FINAL` alone.

**Alternatives considered**

- Rely on `ReplacingMergeTree` background merge for publication: rejected because readers can observe duplicate versions and prior revisions are not guaranteed by the current model.
- Use two-phase commit across PostgreSQL and ClickHouse: rejected as unsupported and unnecessary.
- Promote before CH reconciliation: rejected because the API could expose incomplete feature data.
- Use ClickHouse mutation to update rows in place: rejected because revisions must remain immutable.

## R-007: Temporal orchestration and recovery

**Decision**

- Use a keyed, idempotent Kafka consumer for continuous incremental materialization.
- Use Temporal for API-requested rebuilds, replay, reconciliation, and long resumable batches.
- Store business safe points in PostgreSQL; Temporal stores execution progress only.
- Use typed activities with stable operation keys, bounded inputs/duration/memory, non-retryable domain failures, and Continue-As-New for large histories.
- Never start one Temporal workflow per ordinary source event.
- Keep the previous valid publication active during rebuild and expose run status separately.

**Rationale**

This follows ADR-0007 and the constitution's rejection of a new orchestration backbone. A normal consumer gives lower latency for incremental updates, while Temporal provides durable execution for large or operator-requested rebuilds. PostgreSQL safe points make recovery independent of a particular Temporal history length.

**Alternatives considered**

- Temporal for every event: rejected due to overhead and unnecessary workflow history growth.
- One giant non-resumable batch job: rejected because it cannot meet the 99% interrupted-rebuild criterion safely.
- Kafka offset as the only safe point: rejected because a consumer offset does not prove candidate reconciliation or publication completed.
- Resuming by deleting candidate rows and replaying the entire entity: safe only as a bounded fallback, not the normal recovery path.

## R-008: Interfaces, access, and investigation scope

**Decision**

- Add a versioned FastAPI router under `/api/v1` for history, point-in-time views, feature series, rebuild requests, run status, health, audit, and quarantine review.
- Bind tenant and actor from authenticated `TenantContext`; never accept a body/query `tenant_id` as authority.
- Apply least privilege: viewer/analyst reads, analyst/admin rebuild and governed quarantine replay, admin-only audit and policy access.
- Return the same not-found response for absent and foreign resources to avoid existence disclosure.
- Materialize by `(tenant_id, entity_id)`; investigation IDs are lineage, policy, budget, and access scope because one entity can participate in multiple investigations.
- Reuse the existing `TimelineView`/`TimelineSlider`, but source its data from server contracts rather than browser-only event filtering.
- Persist an access-policy decision for denied or privileged materialization operations.

**Rationale**

The constitution requires tenant isolation and RBAC at every plane, and the specification explicitly includes reads, writes, rebuilds, status, counts, errors, and audit. Existing global catalog/quarantine/SSE routes are not safe templates. Existing React timeline components are reusable presentation only.

**Alternatives considered**

- Put tenant IDs in client-supplied request bodies: rejected because it permits spoofing.
- Key histories by investigation: rejected because the same entity could receive divergent histories and duplicate work.
- Retain browser event filtering as point-in-time authority: rejected because it cannot represent a source cut or immutable revision.
- Build a new UI design system: rejected as outside scope.

## R-009: Backpressure, retry, quarantine, and observability

**Decision**

- Apply backpressure before acknowledging/processing more source work when PostgreSQL or ClickHouse pressure crosses thresholds; retain lag rather than drop late events.
- Bound task, source, investigation/entity, tenant, and global retry budgets with jittered transient retries.
- Classify malformed, ambiguous, tenant-mismatched, non-dynamic, policy-uncertain, and contradictory records as non-retryable quarantine decisions.
- Preserve the original source reference, raw digest, tenant/entity/run, processing time, attempts, reason, and append-only resolution decision; never purge the only representation.
- Expose durable statuses `current`, `delayed`, `rebuilding`, `degraded`, `quarantined`, and `incomplete`, including latest source cut, completeness, age, and reason.
- Emit lag, age, run, revision, duplicate, quarantine, reconciliation, fingerprint, backpressure, and query-latency telemetry. Status changes must be visible within 60 seconds.

**Rationale**

The constitution mandates bounded work, retry budgets, quarantine, backpressure, idempotency, and observability. The specification adds capacity, timing, and load-protection outcomes. Durable state, not in-memory worker counters, must drive operator status.

**Alternatives considered**

- Expand an unbounded queue: rejected by the constitution and the load-protection requirement.
- Retry malformed/contradictory records indefinitely: rejected because they are deterministic failures.
- Delete quarantine payloads after replay: rejected because audit and reproducibility require retention.
- Report static or worker-memory health: rejected because it can present incomplete work as current.

## R-010: Migrations and rollout

**Decision**

Use additive, forward-compatible changes:

1. Repair/baseline Alembic and add a checksummed ClickHouse migration mechanism before feature migrations.
2. Add source identity/lineage fields and new materialization tables without altering or deleting `entity_series`.
3. Run shadow materialization for allowlisted tenant/home-region cohorts without changing user-visible reads.
4. Reconcile fingerprints and inject failures before backfill.
5. Backfill in bounded cohorts, then enable canary reads.
6. Roll out one home region at a time through increasing cohorts.
7. Roll back by disabling new writes/reads and returning to the last valid publication; retain new tables, candidates, audit, and revisions for diagnosis.

**Rationale**

The current repository has no Alembic revision chain, no production ClickHouse adapter/migration ledger, and no complete application deployment. Destructive downgrades or in-place changes would conflict with evidence preservation and reproducibility. Shadow/canary operation is the only safe way to validate 100k histories and 10m events before broad publication.

**Alternatives considered**

- Mutate the existing `entity_series` table in place: rejected because it cannot preserve every window revision and its current ordering key is insufficient.
- Big-bang backfill and global cutover: rejected because reconciliation failure would affect every tenant.
- Destructive database rollback: rejected because audit and prior valid revisions must remain available.
- Global feature flag across regions: rejected because tenant home-region isolation requires scoped activation.

## Reuse boundary for features 011 and 012

| Existing capability | Reuse | Required extension |
| --- | --- | --- |
| `GraphInvariant`, `TemporalSlice`, lifecycle/window helpers | Reuse deterministic domain kernel and two-kind boundary. | Add source cut, coverage end, per-window manifests, dynamic eligibility, serialization, and revision wrappers. |
| `StreamRecord`, `EntityStreamRow`, entity fabric fold | Reuse tenant/entity/hash/validity rules. | Add producer-scoped source identity, durable source-cut metadata, a production PostgreSQL store, and explicit acceptance disposition. |
| Temporal metrics and TDA kernels | Reuse deterministic calculations behind versioned provider contracts. | Add minimum-sample policy, explicit unavailable states, full provenance, and deterministic identity. |
| `SeriesTable` and ClickHouse baseline | Reuse adapter/test-seam pattern. | Add real CH adapter, migration, revision-aware append history, and publication-aware current view. |
| `TimelineView` and time slider | Reuse UI presentation. | Replace browser-synthesized timestamps/state with server history, revisions, source cuts, and completeness. |
| Generic DLQ, audit, retry, and projection models | Reuse concepts where compatible. | Add tenant/entity/run lineage, durable sink, immutable decisions, safe points, and non-purging replay. |
| Temporal client and investigation workflow patterns | Reuse existing service. | Add real worker/activity registration, deterministic workflow ID, typed activities, and deployment. |

## External best-practice references

- Kafka ordering and offsets: <https://kafka.apache.org/43/design/design/>
- Kafka retention and compaction: <https://kafka.apache.org/43/configuration/topic-configs/>
- Flink event time and late data: <https://nightlies.apache.org/flink/flink-docs-stable/docs/concepts/time/>
- Temporal deterministic workflows: <https://docs.temporal.io/workflow-definition>
- Temporal activity retries and idempotency: <https://docs.temporal.io/activity-execution>
- PostgreSQL transaction isolation: <https://www.postgresql.org/docs/current/transaction-iso.html>
- PostgreSQL range types: <https://www.postgresql.org/docs/current/rangetypes.html>
- Protobuf canonical-encoding warning: <https://protobuf.dev/programming-guides/serialization-not-canonical/>
- ClickHouse transactional limitations: <https://clickhouse.com/docs/guides/developer/transactional>
- `ReplacingMergeTree` semantics: <https://clickhouse.com/docs/reference/engines/table-engines/mergetree-family/replacingmergetree>
- Transactional outbox pattern: <https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html>

## Research conclusion

All technical-context unknowns are resolved. The plan can proceed without a clarification gate failure. Implementation remains blocked on the explicitly identified platform prerequisites: durable entity-stream persistence/identity, safe Kafka consumer behavior, operational migrations, a real Temporal worker, tenant-safe access controls, durable quarantine/audit, and first-party observability/deployment paths.
