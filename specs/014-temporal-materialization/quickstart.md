# Quickstart Validation: Temporal Materialization

**Feature**: `014-temporal-materialization`  
**Status**: Post-implementation validation/run guide; commands and test files describe the required implementation surface and are not created by `/speckit.plan`

## Purpose

Validate the feature end to end without implementing it in this planning phase. The scenarios prove deterministic histories, exact source-cut reads, late-data revisions, duplicate idempotency, contradiction quarantine, rebuild recovery, aligned features, tenant isolation, audit/health, and scale.

Contract references:

- Domain entities and state transitions: [data-model.md](./data-model.md)
- Pure/service boundaries: [contracts/service-contracts.md](./contracts/service-contracts.md)
- HTTP behavior: [contracts/api.md](./contracts/api.md)
- Event behavior: [contracts/events.md](./contracts/events.md)
- Operational gates: [contracts/operations.md](./contracts/operations.md)
- Overall phases and rollout: [plan.md](./plan.md)

## Prerequisites

- Windows PowerShell 7+, Git, Python 3.11+, `uv`, Node.js 20+, `pnpm`, and Docker Desktop.
- A clean checkout or isolated feature branch.
- Accepted feature ADR and completed migration prerequisites.
- Local non-production credentials only; do not place real secrets in shell history or files.
- Enough disk for the representative 100,000-history/10,000,000-event dataset.
- Test identities for two tenants, viewer/analyst/admin roles, and a deliberate shared entity ID collision.

Run all commands from the repository root unless a step says otherwise.

## 1. Install and start the development substrate

```powershell
uv sync --frozen
docker compose -f apps/deploy/docker-compose.yml --profile core --profile analytics up -d
```

Expected outcome:

- PostgreSQL, Kafka/schema registry, Temporal, MinIO, ClickHouse, Neo4j, and OpenSearch report healthy.
- No live external source or model service is required.
- Network-dependent tests remain disabled unless explicitly opted into.

## 2. Apply additive migrations

After Phase 0 makes Alembic/ClickHouse migration tooling operational:

```powershell
Push-Location apps/control-plane
uv run alembic upgrade head
uv run python -m db.clickhouse.migrate up
Pop-Location
```

Run the migration sequence a second time.

Expected outcome:

- PostgreSQL and ClickHouse reach the same migration version/checksum.
- A repeated run is a no-op.
- Existing `entity_stream`, evidence, graph, and `entity_series` source data is unchanged.
- No feature 014 publication/head is created by migration alone.

## 3. Run deterministic unit and contract validation

```powershell
uv run --project apps/shared pytest apps/shared/tests/unit/domain/test_temporal_materialization.py apps/shared/tests/contract/test_materialization_ports.py -q
uv run --project apps/projection pytest apps/projection/tests/unit/test_temporal_materialization.py apps/projection/tests/unit/test_temporal_features.py -q
uv run --project apps/control-plane pytest apps/control-plane/tests/unit/test_temporal_materialization_service.py apps/control-plane/tests/unit/test_temporal_feature_store.py -q
```

Expected outcome:

- Half-open boundary, dormant/trailing coverage, source identity, late dependency, fingerprint, availability, and reconciliation tests pass.
- Shuffled input and repeated candidate builds produce identical window/history fingerprints.
- A measured zero remains distinct from an unavailable value.
- No pure-domain test imports a vendor/storage/runtime type.

## 4. Run real infrastructure integration validation

With the development substrate healthy:

```powershell
uv run --project apps/shared pytest apps/shared/tests/integration/test_materialization_kafka.py -q
uv run --project apps/control-plane pytest apps/control-plane/tests/integration/test_temporal_materialization.py apps/control-plane/tests/integration/test_temporal_materialization_api.py -q
uv run --project apps/projection pytest apps/projection/tests/integration/test_temporal_feature_store.py -q
```

Expected outcome:

- Real PostgreSQL/ClickHouse/Temporal/Kafka paths complete.
- Promotion is atomic at the PostgreSQL publication pointer.
- Prior revisions remain queryable after promotion.
- Exact duplicate inserts converge without extra accepted/revision rows.
- Offset commits occur only after durable disposition.

## 5. Run the end-to-end fixture scenario

The implementation must provide a deterministic live scenario in the existing benchmark harness:

```powershell
uv run python -m bench.run --scenario temporal-materialization --live
```

The scenario must build a known source history with:

- at least three active windows;
- a multi-window dormant gap;
- a trailing covered dormant window;
- one insufficient-data structural feature;
- a point at an exact window boundary;
- a later source record for an earlier event-time window;
- one exact duplicate and one contradictory source identity;
- one interrupted and one uninterrupted rebuild;
- two tenants using the same entity identifier.

Expected terminal line:

```text
RESULT: PASS
```

The harness must also emit machine-readable evidence for:

- initial and historical source-cut IDs/fingerprints;
- affected window revisions after the late event;
- duplicate/revision counters;
- quarantine reason/decision;
- resumed versus uninterrupted history fingerprints;
- cross-tenant response equivalence;
- current/PIT query durations and materialization status age.

## 6. Validate current and point-in-time reads

Start the API in `shadow` or `canary` mode using local test credentials, then query the current history:

```powershell
$headers = @{ Authorization = "Bearer $env:COGNITIVE_TEST_TOKEN" }
$current = Invoke-RestMethod -Headers $headers -Uri "http://localhost:8000/api/v1/entities/entity-shared/temporal-history/current"
```

Select the exact source cut returned by `$current.source_cut.source_cut_id`:

```powershell
$cutId = [uri]::EscapeDataString($current.source_cut.source_cut_id)
$historical = Invoke-RestMethod -Headers $headers -Uri "http://localhost:8000/api/v1/entities/entity-shared/temporal-history?source_cut_id=$cutId"
```

Select one exact event-time point in that cut:

```powershell
$at = [uri]::EscapeDataString("2026-01-08T00:00:00Z")
$point = Invoke-RestMethod -Headers $headers -Uri "http://localhost:8000/api/v1/entities/entity-shared/temporal-history/at?at=$at&source_cut_id=$cutId"
```

Expected outcome:

- Current, historical, and point responses identify their exact source cut, publication, revision, completeness, and fingerprints.
- Every covered window appears once in chronological order.
- Dormant windows have zero events and no fabricated relationship/feature values.
- The boundary timestamp belongs only to the interval where `start <= at < end`.
- The historical response contains no record admitted after its cut.

## 7. Validate aligned feature series

```powershell
$features = Invoke-RestMethod -Headers $headers -Uri "http://localhost:8000/api/v1/entities/entity-shared/temporal-features?source_cut_id=$cutId"
```

Expected outcome:

- Every required feature key has one record for every covered window.
- `available=false` records have null value and a reason.
- Measured numeric zero has `available=true`.
- Structural records have `structural_only=true` and complete source/cut/policy/provider/window provenance.
- No structural record asserts identity, truth, or source independence.

## 8. Validate late data, exact duplicates, and contradiction quarantine

The live harness injects the required events. Confirm through the API/operator view:

1. The late event is assigned to its original event-time window.
2. Its dependency closure receives new window revisions.
3. Unaffected windows retain the same revision IDs/fingerprints.
4. The prior source cut and publication remain unchanged.
5. The duplicate causes no accepted event, window, publication, or revision-count increase.
6. The contradictory identity is retained in quarantine with `contradictory_source_record`.
7. Replaying the quarantine record does not overwrite accepted history.

Expected outcome: every source/event window, revision, fingerprint, and audit decision is explainable from the contracts and manifests.

## 9. Validate rebuild interruption and reconciliation

Run the rebuild scenario with failure injection after each durable stage:

```powershell
uv run python -m bench.run --scenario temporal-materialization-recovery --live
```

Expected outcome:

- Resumed and uninterrupted builds produce the same history fingerprint.
- At least 99% of injected interrupted runs converge within 15 minutes after capacity restoration.
- Missing, extra, or divergent window fixtures never advance the head.
- A stale concurrent candidate cannot overwrite a newer valid publication.
- The prior valid publication remains readable throughout failure/recovery.
- Audit contains request, safe point, reconciliation, promotion/failure, and completion decisions.

## 10. Validate tenant isolation and RBAC

Use two authenticated tenant contexts with the same `entity_id`, plus viewer/analyst/admin principals.

Expected outcome:

- A foreign history/run/window/quarantine/audit lookup returns the same `404` shape as a nonexistent resource.
- No value, count, status, age, timing, error, revision, or existence signal differs because the resource belongs to another tenant.
- Viewer cannot request rebuild, review/replay quarantine, or read audit.
- Analyst can read and request a bounded rebuild.
- Admin can read audit and perform governed policy actions.
- Denied and allowed privileged actions are audited.
- Cross-tenant isolation tests pass at API, PostgreSQL RLS, ClickHouse, event, audit, and health layers.

## 11. Validate operational failure behavior

Run the bounded failure/backpressure scenario:

```powershell
uv run python -m bench.run --scenario temporal-materialization-resilience --live
```

Inject:

- PostgreSQL promotion failure;
- ClickHouse outage;
- Kafka redelivery;
- worker termination at each activity boundary;
- Temporal outage/restart;
- poison/malformed records;
- repeated failing input;
- downstream demand above capacity.

Expected outcome:

- Last valid publication remains available.
- Incomplete work is never presented as current.
- Retries stay within task/source/entity/investigation/global budgets.
- Poison inputs are quarantined, not retried indefinitely.
- Backlog is bounded and recovers with hysteresis.
- Health/dashboard state becomes visible within 60 seconds.
- No source/evidence record is changed or deleted.

## 12. Validate representative scale and latency

The implementation must expose a repeatable benchmark scenario equivalent to:

```powershell
uv run python -m bench.run --scenario temporal-materialization-scale --live --histories 100000 --events 10000000 --json
```

Record machine shape, dataset fingerprint, worker counts, policy/schema versions, and ClickHouse topology with the result.

Required thresholds:

- 100% of eligible histories/windows materialized or explicitly incomplete.
- 0 evidence loss and 0 cross-tenant disclosure.
- 95% current-view requests <= 2 seconds.
- 95% point-in-time requests <= 3 seconds.
- Status visibility <= 60 seconds.
- Interrupted-run convergence >= 99% within 15 minutes after capacity restoration.
- Backlog remains bounded during a 2x highest-observed 15-minute input burst and drains after the burst.

## 13. Validate the existing web client

```powershell
Push-Location apps/webapp
pnpm test
pnpm exec tsc -b
pnpm build
pnpm exec prettier --check src
pnpm lint
Pop-Location
```

Expected outcome:

- Existing timeline components consume server-authoritative windows, source cuts, revisions, provenance, and completeness.
- Moving between latest and selected history never fetches or displays later knowledge for an older cut.
- Rebuilding/delayed/degraded status is visibly distinct from the last valid publication.
- Foreign/unauthorized resources render the same not-found state.
- No browser-generated fallback fabricates missing timestamps, dormancy, or feature zeros.

## 14. Run non-mutating quality gates

```powershell
uv run ruff check apps/shared apps/control-plane apps/projection
uv run ruff format --check apps/shared apps/control-plane apps/projection
git diff --check
```

After affected suites are green, run the repository's complete documented Python, Rust, and web gates. Any unrelated baseline failure must be fixed or explicitly approved before release; it cannot be hidden behind a “no new failures” rule.

## 15. Conduct the analyst usability check

Use at least the required moderated cohort and a fixture containing active/dormant periods, a late correction, and an incomplete rebuild.

Ask each analyst to:

1. identify when the entity was active;
2. select a historical point;
3. identify what evidence was known at that point;
4. locate the source cut/revision;
5. determine whether the current view is complete.

Pass condition:

- At least 90% complete the task without assistance.
- At least 90% finish in under three minutes.
- No participant mistakes a structural signal for identity/truth or a delayed/rebuilding view for complete current state.

## Release evidence checklist

- [ ] AS-001 through AS-015 pass with recorded evidence.
- [ ] FR-001 through FR-030 map to passing tests.
- [ ] SC-001 through SC-012 meet numeric thresholds.
- [ ] Source/evidence hashes and counts are unchanged.
- [ ] Point-in-time and current queries expose exact provenance.
- [ ] Prior revisions remain queryable.
- [ ] Tenant/RBAC negative tests pass at every boundary.
- [ ] Migration repeat/interruption/old-app compatibility passes.
- [ ] Dashboard and alerts fire in a controlled drill.
- [ ] Analyst usability threshold passes.
- [ ] Rollback drill restores the last valid read path without destructive deletion.
- [ ] All Ruff, pytest, Vitest, TypeScript, build, and Prettier gates are clean.
