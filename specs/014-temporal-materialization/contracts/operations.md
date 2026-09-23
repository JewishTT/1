# Operations Contract: Temporal Materialization

**Feature**: `014-temporal-materialization`  
**Status**: Design artifact; telemetry, deployment, and runbooks are not implemented

## Operating objective

Keep materialization current, complete, deterministic, tenant-isolated, and rebuildable without turning the projection into a source of truth. A downstream failure must leave the last valid published view available and observable.

## Status model

### History health

| Status | Meaning | Publication behavior |
| --- | --- | --- |
| `current` | Latest sealed source cut is promoted, complete, and within freshness target. | Latest valid publication is current. |
| `delayed` | Valid publication exists, but source processing/freshness exceeds target. | Serve last valid publication with delay. |
| `rebuilding` | An authorized rebuild is staged/reconciling. | Serve last valid publication. |
| `degraded` | Repeated infrastructure failure, heartbeat loss, fingerprint/reconciliation issue, or dependency outage. | Serve last valid publication unless correctness is uncertain; never mark complete. |
| `quarantined` | One or more blocking records require review. | Non-blocking publication may remain valid; blocking cut cannot become current. |
| `incomplete` | Expected coverage/feature/provenance is incomplete. | Never present as complete/current. |

### Run status

`queued -> running -> staged -> reconciling -> promoting -> completed`

Terminal alternatives are `cancelled`, `failed`, and `quarantined`. Resume does not reset the business safe point or create an unrelated run.

### Completeness

Publication completeness is independent from health:

- `complete`: all expected windows/features/provenance reconcile and the publication fingerprint matches.
- `incomplete`: explicit missing/extra/divergent/dependency state; not eligible for normal promotion.

## Service-level targets

| Signal | Target |
| --- | --- |
| Materialization health transition visibility | <= 60 seconds after delay, failure, quarantine, or completed reconciliation. |
| Current-view latency | 95% <= 2 seconds after corresponding view is available. |
| Point-in-time latency | 95% <= 3 seconds after corresponding view is available. |
| Interrupted rebuild resume | >= 99% without manual cleanup; converge within 15 minutes after capacity restoration. |
| Source/event immutability | 0 mutations or losses in all tests/rollouts. |
| Cross-tenant disclosure | 0. |
| Structural identity/truth assertions | 0. |
| Exact duplicate deliveries | 1,000 deliveries cause 0 new accepted events, phantom windows, or revisions. |

## Bounded work defaults

These are safe starting defaults and must be measured in the 100k/10m workload. Policy may tighten them; raising them requires load evidence and governance.

| Limit | Default |
| --- | --- |
| Incremental source batch | 5,000 records or 16 MiB, whichever occurs first. |
| Window candidate batch | 500 windows or 64 MiB, whichever occurs first. |
| Feature batch | 10,000 feature records or 32 MiB, whichever occurs first. |
| Activity timeout | 10 minutes. |
| Per-worker concurrent activities | 4, with tenant-fair scheduling. |
| Rebuild request records/windows | Cannot exceed policy and capacity; rejected with `429` rather than queued without bound. |
| In-memory work | Explicit per-activity memory budget and input-size checks; no unbounded entity accumulation. |
| Source/Kafka acknowledgement | No offset commit before durable accepted/duplicate/quarantine disposition. |

A large entity is processed in deterministic chunks and continue-as-new workflow pages; it is not loaded wholly into memory.

## Backpressure

### Pressure signals

- Kafka record count/bytes and oldest source age.
- PostgreSQL/ClickHouse write latency, pool saturation, errors, and queue age.
- Active candidate rows/parts/bytes.
- Retry-budget consumption and oldest retrying task.
- Temporal rebuild backlog and oldest queued run.
- Per-tenant fair-share lag and hot-key skew.

### Default control bands

| Band | Trigger | Response |
| --- | --- | --- |
| Normal | Source age < 30 seconds; durable stores healthy; bounded queue | Process normally. |
| Throttled | Source age >= 30 seconds, downstream p95 >= 1 second, or retry utilization >= 50% | Reduce concurrency, disable nonessential rebuild admission, prioritize new source preservation. |
| Paused | Source age >= 60 seconds, durable control store unavailable, memory/size limit risk, or retry utilization >= 80% | Pause affected incremental partition processing before unsafe acknowledgement; keep last valid view. |
| Recovery hysteresis | Source age <= 15 seconds and downstream p95 < 250 ms for 2 minutes | Increase concurrency gradually to normal. |

These controls reduce materialization throughput before expanding Kafka backlog. They do not drop late events and do not stop evidence acquisition solely to hide projection lag; acquisition's existing backpressure may also be signaled through its configured boundary.

## Retry budgets

Default bounded attempts for a single logical operation:

| Scope | Default maximum | Exhaustion behavior |
| --- | --- | --- |
| Task/activity | 3 | Fail run activity; workflow may checkpoint/replan. |
| Source record/delivery | 5 | Durable quarantine after transient retries if disposition cannot complete. |
| Entity/investigation | 10 | Degrade and quarantine blocking work; preserve run/safe point. |
| Tenant | governed per investigation/window | Pause new run admission; keep last valid view. |
| Global | governed fleet budget | Shed nonessential rebuild/replay work; never retry deterministic poison input indefinitely. |

Retries use exponential backoff with jitter. Deterministic validation, contradiction, unsupported schema/policy, and fingerprint mismatch errors are not transiently retried.

## Reconciliation contract

A candidate is promotable only when:

1. Source cut and coverage manifest are sealed and verifiable.
2. Expected covered windows equal actual windows exactly.
3. There are no missing, extra, or divergent window keys.
4. Every window is unique, non-overlapping, chronological, and valid half-open.
5. Every changed window fingerprint is new or reuses an identical prior revision.
6. Every unchanged effective window is carried forward unchanged.
7. Required feature keys align one-to-one with windows and distinguish unavailable from measured zero.
8. Structural records are labeled structural-only and contain no identity/truth assertion.
9. The canonical history fingerprint equals the independently computed expected fingerprint.
10. ClickHouse feature rows/checksums, when enabled, are complete before PostgreSQL promotion.
11. Audit/outbox records and publication manifest can commit atomically with the head/effectivity update.

Any failed check blocks promotion and records an immutable failed reconciliation result.

## Concurrency and optimistic publication

- Incremental work is keyed by `(tenant_id, entity_id)`.
- Two operators may create separate idempotent rebuild requests, but only one candidate can promote against a given `active_cut_ordinal`.
- A stale candidate is retained with `stale_head` reason and replanned; it is never merged silently.
- Exact duplicate source records never advance the source cut or history head.
- A valid late record may advance the entity cut and only the dependency-affected window revisions.
- Concurrent candidates for the same exact input may converge to the same publication fingerprint and reuse revisions.

## Health and freshness

Health is computed from durable PostgreSQL state plus dependency/worker telemetry. Worker memory alone is not authoritative.

Required health fields:

- tenant/entity or tenant aggregate scope;
- active publication and latest sealed source cut;
- status/reason;
- latest source acceptance time and age;
- active run/safe point/heartbeat;
- completeness and whether the active view is latest valid;
- expected/actual coverage at the last reconciliation;
- current dependent-store degradation.

Operators can distinguish a delayed newest cut from the last valid published view.

## Audit contract

Audit the following actions with actor/principal, tenant, entity, action, reason, timestamp, run, publication/window revision, source cut, policy/schema versions, request ID, and safe detail:

- materialization run requested/admitted/rejected;
- source accepted, duplicate, rejected, or quarantined;
- candidate staged and safe point committed;
- reconciliation passed/failed;
- window revision created/reused;
- publication promoted/superseded;
- rebuild started/resumed/cancelled/failed/completed;
- quarantine reviewed/replayed/rejected/resolved;
- policy/activation change;
- allowed and denied privileged access.

Audit rows are append-only. Audit access itself is audited. Secrets, raw evidence, and foreign-tenant identifiers are excluded.

## Quarantine operations

- Retain source identity/hash, immutable payload reference, reason, attempt count, first/last processing time, and append-only decisions.
- Reviewers see sanitized metadata; raw payload access is a separate governed action.
- Replay uses a new run/decision and never deletes or edits the original quarantine record.
- Contradictory source identity cannot be released merely by administrative retry; it requires a source correction/policy decision that creates a new accepted representation or remains rejected.
- Retention expiry returns `410 retention_expired`; it never falls back to current data for a historical answer.

## Metrics

Proposed metric names, without raw tenant labels:

```text
cognitive_temporal_materialization_runs_total
cognitive_temporal_materialization_source_lag_seconds
cognitive_temporal_materialization_status_age_seconds
cognitive_temporal_materialization_active_runs
cognitive_temporal_materialization_revisions_total
cognitive_temporal_materialization_duplicates_suppressed_total
cognitive_temporal_materialization_quarantined_total
cognitive_temporal_materialization_reconciliation_failures_total
cognitive_temporal_materialization_fingerprint_mismatches_total
cognitive_temporal_materialization_publication_failures_total
cognitive_temporal_materialization_backpressure_ratio
cognitive_temporal_materialization_resume_duration_seconds
cognitive_temporal_materialization_request_duration_seconds
```

Labels may include bounded dimensions such as mode, reason code, region, run mode, and status. Tenant-facing detail is queried through the tenant-scoped API, not global Prometheus labels.

## Alerts and automatic stops

| Alert | Default condition | Response |
| --- | --- | --- |
| Status stale | Materialization status transition not visible for 60 seconds | Page/on-call; inspect head/run/store. |
| Reconciliation mismatch | Any unexplained missing/extra/divergent window | Stop promotion for affected history/region. |
| Fingerprint mismatch | Any mismatch between independently computed candidate/history fingerprint | Stop promotion and quarantine evidence. |
| Cross-tenant access attempt | Any confirmed or suspicious unauthorized tenant scope | Security stop and audit escalation. |
| Query SLO breach | Current p95 > 2s or PIT p95 > 3s for 15 minutes | Throttle rebuilds/scale reads; inspect plans/indexes. |
| Resume SLO breach | Resume convergence < 99% or > 15 minutes | Pause broad backfill; inspect safe points/activity failures. |
| Retry/backlog | Budget > 80%, sustained growth, or hot-key starvation | Enter throttled/paused band; shed nonessential work. |
| Publication failure | Promotion/outbox failure or invalid head transition | Preserve last valid head; disable new mode. |
| Evidence integrity | Any source/evidence count/hash change | Immediate stop and investigation. |

## Tenant and regional isolation

- Enforce tenant scope in event keys, repositories, SQL predicates/RLS, ClickHouse query filters, Temporal workflow IDs/search attributes, audit, health, logs, and API errors.
- Keep work in the tenant's home region; cross-region migration is a governed re-projection, not ad hoc failover.
- Do not reveal foreign entity existence through status, count, latency, quarantine, or audit behavior.
- Roll out by tenant/home-region allowlist rather than a global switch.

## Deployment and migration sequence

1. **Preflight**: approve ADR; inventory PostgreSQL/CH schemas; capture source/evidence counts and hashes.
2. **Expand**: establish Alembic baseline/migration runner; add additive source-lineage/materialization tables and ClickHouse tables; old app remains compatible.
3. **Worker shadow**: deploy workers in shadow mode; no user-visible reads.
4. **Data validation**: compare two replays, inject duplicates/late/conflicts/failures, verify old source hashes unchanged.
5. **Backfill**: bounded cohorts 1 tenant, 5 tenants/5%, 25%, 50%, 100% per region.
6. **Canary read**: allowlisted internal/test tenants use API/UI; legacy remains fallback.
7. **Regional enablement**: 1%, 5%, 25%, 50%, 100% with at least one seven-day window soak.
8. **Default**: switch eligible new histories after all success/rollback gates; retain legacy support for the approved rollback window.

## Rollback contract

Rollback is application-level, not destructive:

1. Enter affected tenant/home region in `legacy` or `shadow` mode.
2. Stop new promotion and nonessential rebuild/replay admission.
3. Continue serving the last valid publication or legacy view with explicit status/freshness.
4. Retain candidate, revision, quarantine, audit, source-cut, and checkpoint data.
5. Correct the cause, resume/rebuild from the recorded cut, reconcile, and explicitly re-enable.
6. Never use a destructive database downgrade to remove audit/revision history.

## Validation and release evidence

Before broad enablement, retain:

- pure/property and contract test reports;
- real PostgreSQL/Kafka/ClickHouse/Temporal integration results;
- migration repeat/interruption/old-app compatibility results;
- tenant/RBAC and cross-tenant negative results;
- 1,000-duplicate and late-event reconciliation evidence;
- worker/database/CH failure and recovery timings;
- 100k-history/10m-event load report and query percentiles;
- dashboard/alert firing evidence;
- analyst usability study;
- canary rollout metrics and rollback-drill record.

No broad rollout proceeds while any constitution gate, source/evidence integrity check, tenant isolation check, or reconciliation invariant fails.
