# Implementation Plan: Temporal Entity Materialization

**Branch**: `014-temporal-materialization` | **Date**: 2026-09-24 | **Spec**: [spec.md](./spec.md)

**Input**: Completed feature specification from `specs/014-temporal-materialization/spec.md`

## Summary

Implement temporal materialization as a deterministic, rebuildable projection over accepted entity-stream records and immutable evidence references. The feature will:

- assign every accepted dynamic-entity event to one governed half-open event-time window;
- materialize lifecycle, activity, relationship/topology, evidence-reference, and eligible structural-feature summaries for every covered window;
- preserve prior valid point-in-time views through immutable source cuts, window revisions, and publication records;
- revise only dependency-affected windows for late evidence while exact duplicates and repeated requests remain no-ops;
- quarantine contradictions and policy-uncertain input without changing accepted history;
- stage, reconcile, and atomically promote rebuild candidates while serving the last valid publication on failure;
- expose tenant-safe current, historical, feature-series, health, audit, quarantine, and rebuild interfaces;
- use Kafka for continuous incremental triggers, Temporal for long-running rebuilds, PostgreSQL for exact publication authority, ClickHouse for rebuildable feature-series scans, and the existing React timeline for analyst access.

The feature consumes features 011 and 012 as deterministic compute/domain dependencies. It does not make their partial persistence paths authoritative and does not create a new source of truth, orchestration backbone, or universal knowledge store.

## Scope

### In scope

- Dynamic-entity eligibility and accepted-source validation.
- Entity-scoped source cuts and point-in-time selectors.
- Governed window coverage, lifecycle/activity, relationship/topology, evidence references, and aligned feature records.
- Immutable window revisions, publication effectivity, deterministic fingerprints, late-data dependency tracking, and current-head promotion.
- Durable materialization runs, safe points, reconciliation, audit, quarantine, health, backpressure, and bounded retries.
- PostgreSQL repositories, ClickHouse feature storage, Kafka contracts/consumers, Temporal rebuild workflow, FastAPI routes, existing React timeline integration, telemetry, migrations, and rollout controls.

### Out of scope

- Identity resolution, admission decisions, evidence interpretation, truth adjudication, recrawl/scheduling policy, and source acquisition.
- Independent histories for static objects or evidence leaves.
- Generative/LLM decisions, structural signals as identity/truth, raw evidence mutation, and evidence deletion.
- A new orchestration backbone, universal graph/store, acquisition scheduling redesign, or wholesale UI redesign.
- In-place semantic changes to feature 011's legacy `entity_series` table.

## Existing dependencies and prerequisites

| Dependency | Existing state | Planning disposition |
| --- | --- | --- |
| Feature 012 `GraphInvariant` | Deterministic half-open windows, lifecycle states, dormant gaps, topology/evidence boundaries, and canonical hash exist. | Reuse and wrap; add coverage end, source identity, per-window provenance, serialization, and persistence. |
| Feature 011 temporal metrics/TDA | Pure metric, diagram, feature, and structural-only kernels exist; ClickHouse/TDA wiring remains partial. | Reuse behind a versioned provider; do not treat legacy series persistence as publication authority. |
| `EntityStreamRow`/`StreamRecord` | Tenant/entity/hash/sequence/validity contract exists; no production PostgreSQL store and no explicit source-record identity. | Add source identity/lineage, a production store, disposition, and durable accepted stream before materialization. |
| Kafka | `entity.stream.appended` exists; current generic consumer has async, offset-commit, and quarantine correctness gaps. | Harden as a prerequisite before adding the materialization consumer. |
| PostgreSQL | Operational store baseline exists; Alembic is scaffolded without revisions. | Establish a safe baseline and additive migration chain before feature tables. |
| ClickHouse | Compose/dependency and an in-memory series seam exist; no real adapter or migration ledger. | Add a real adapter, migration mechanism, append revision table, and current projection. |
| Temporal | Service/client/workflow examples exist; no first-party worker/activity runtime. | Add a real worker and materialization workflow for rebuilds only. |
| Auth/RBAC/audit/quarantine | Basic primitives exist but several routes are global or unscoped. | Build new tenant-bound repositories/routes; do not copy unsafe global stores. |
| Observability/deployment | OTel/Prometheus helpers and Compose exist, but application telemetry, alerts, and application deployment manifests are incomplete. | Add first-party startup, metrics, dashboard/alerts, worker/API deployment, and migration jobs. |

## Technical Context

**Language/Version**: Python 3.11+ (domain, services, workflows, API); TypeScript 5.5+ / React 18 (existing webapp)

**Primary Dependencies**: FastAPI, Pydantic 2, SQLAlchemy 2/asyncpg, Alembic, Temporalio, confluent-kafka, Protobuf 5, ClickHouse Connect, Redis where required for bounded coordination, existing NumPy/SciPy/GUDHI/giotto-tda kernels, React Query, Vitest

**Storage**: S3-compatible immutable evidence/artifacts; PostgreSQL exact publication/revision/run/audit/quarantine state; ClickHouse rebuildable feature series; Kafka event backbone; existing graph/search projections for current summaries

**Testing**: pytest 8, pytest-asyncio, FastAPI/TestClient, testcontainers/live infrastructure tests, Ruff, Vitest/Testing Library, TypeScript compiler, dedicated load/chaos validation

**Target Platform**: Docker development stack; Linux containers on Kubernetes; regional control plane and ClickHouse deployments; browser client through the existing React application

**Project Type**: Full-stack projection/control-plane service with shared domain contracts, asynchronous workers, analytical storage, API, and web client

**Performance Goals**: 95% current-view requests under 2 seconds; 95% point-in-time requests under 3 seconds; status visible within 60 seconds; 99% interrupted rebuilds converge within 15 minutes after capacity recovery

**Constraints**: Immutable observations/evidence; exact same input/policy/schema produces identical values and fingerprints; no LLM in core decisions; seven-day governed default; half-open windows; bounded memory/duration/input size; task/source/investigation/global retry budgets; tenant isolation and least privilege; no incomplete view presented as current; prior valid revisions retained under governance

**Scale/Scope**: 100,000 entity histories and 10,000,000 source events in the representative investigation; at least 1,000 exact duplicate deliveries in the idempotency test; 10 million events must remain replayable without evidence loss

## Constitution Check

*Gate evaluated before Phase 0 research and re-evaluated after design.*

| Principle / constraint | Plan evidence | Pre-research gate | Post-design gate |
| --- | --- | --- | --- |
| I. Observation-immutable evidence substrate | Materialization reads accepted events and typed evidence references; no source/evidence mutation path exists. | PASS | PASS |
| II. Evidence-first | Every window, feature, publication, and run carries a provenance manifest and source references. | PASS | PASS |
| III. Projection-first architecture | The feature is explicitly rebuildable from `entity_stream` and evidence references; PostgreSQL/ClickHouse records are projection data. | PASS | PASS |
| IV. No single store/graph/score | S3, Kafka, PostgreSQL, ClickHouse, graph/search, and Temporal each retain distinct responsibilities. | PASS | PASS |
| V. Plugability by contract | Source, revision, feature, publication, audit, clock, and event publisher are protocol boundaries; no ClickHouse/Temporal/vendor types enter pure domain logic. | PASS | PASS |
| VI. Process-centric | Materialization is keyed by tenant/entity while investigation IDs govern policy, lineage, budget, and access. | PASS | PASS |
| VII. Security-first | Tenant-bound repositories/API, RLS, RBAC, bounded inputs/retries, durable quarantine, and cross-tenant negative tests are release gates. | PASS | PASS |
| Backpressure/retry/quarantine | Incremental admission and rebuilds have independent bounded work lanes, durable lag, retry budgets, and non-purging quarantine. | PASS | PASS |
| Idempotency | Source identity/content hash, run idempotency keys, unique revision/publication constraints, and event IDs are explicit. | PASS | PASS |
| Major-plane completeness | The work extends the existing Investigation, Evidence, Admission, Projection, Analysis, Feedback, and operational contracts without adding an incompatible final-domain surface. | PASS | PASS |
| ADR governance | Source-cut, revision, publication, ClickHouse, Temporal, and rollout decisions require an accepted ADR before implementation begins. | PASS WITH PREREQUISITE | PASS WITH PHASE 0 GATE |

**Gate result**: No constitutional violation or unjustified complexity exception. Implementation is blocked until the Phase 0 ADR and platform-prerequisite gates pass.

## Architecture

```text
admission / identity authority
  -> immutable accepted entity_stream + evidence references
  -> entity.stream.appended Kafka trigger
  -> keyed idempotent incremental consumer
       -> deterministic shared-domain materializer
       -> staged window revisions + aligned feature candidates
       -> PostgreSQL reconciliation + publication head
       -> ClickHouse append revision history/current projection
       -> transactional outbox -> projection notifications

operator rebuild request
  -> tenant/RBAC-authorized API
  -> durable MaterializationRun
  -> Temporal rebuild workflow
       -> bounded idempotent activities
       -> PostgreSQL safe points
       -> same deterministic materializer/publication protocol
```

### Publication boundary

1. Seal a deterministic source cut and coverage end.
2. Replay and build candidate windows/features under a run identity.
3. Compare expected versus actual coverage and every canonical fingerprint.
4. Write a completion/reconciliation manifest.
5. Advance the PostgreSQL publication/effectivity head in one transaction.
6. Publish output events from the outbox after commit.
7. Keep the previous valid publication available on any later failure.

No cross-system distributed transaction is assumed. PostgreSQL is the publication authority; ClickHouse rows must be complete and verified before the pointer advances.

## Project Structure

### Documentation (this feature)

```text
specs/014-temporal-materialization/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── service-contracts.md
│   ├── api.md
│   ├── events.md
│   └── operations.md
└── tasks.md                         # Phase 2 command; not created by /speckit.plan
```

### Source Code (planned, not implemented by this command)

```text
apps/
├── shared/
│   ├── domain/temporal_materialization.py
│   ├── events/event_envelope.proto
│   ├── events/topics.py
│   ├── events/kafka.py
│   ├── events/dlq.py
│   └── observability/__init__.py
├── projection/
│   └── temporal_materialization/
│       ├── engine.py
│       ├── dependencies.py
│       ├── features.py
│       ├── reconciliation.py
│       ├── consumer.py
│       └── ports.py
├── control-plane/
│   ├── db/schema.py
│   ├── db/migrations/versions/
│   ├── db/clickhouse/migrations/
│   ├── services/temporal_materialization.py
│   ├── services/temporal_feature_store.py
│   ├── workflows/temporal_materialization.py
│   ├── workflows/worker.py
│   └── api/routes/temporal_materialization.py
├── webapp/src/
│   ├── lib/api.ts
│   ├── lib/timelineTypes.ts
│   ├── components/TimelineView.tsx
│   ├── components/TimelineSlider.tsx
│   ├── pages/EntityViewPage.tsx
│   └── pages/OpsDashboardPage.tsx
└── deploy/
    ├── docker-compose.yml
    ├── prometheus/rules/temporal-materialization.yml
    ├── grafana/temporal-materialization-dashboard.json
    └── k8s/
```

**Structure Decision**: Preserve the existing shared/projection/control-plane/web boundaries. Pure contracts stay in `apps/shared`, computation and ports stay in `apps/projection`, transactional adapters and public interfaces stay in `apps/control-plane`, and the existing React application receives server-authoritative timeline data.

## Implementation Phases

### Phase 0 — Governance and platform prerequisites

**Depends on**: Completed specification, constitution, and this approved plan.

**Work**

1. Allocate and approve an ADR covering source-cut semantics, stable source identity, revision/fingerprint rules, publication protocol, ClickHouse engine/key semantics, Temporal role, retention, and regional rollout.
2. Inventory production PostgreSQL and ClickHouse schemas; establish a reviewed Alembic baseline and a checksummed, resumable ClickHouse migration mechanism.
3. Implement a production `EntityStreamStore` bound to `entity_stream`; add producer-scoped `source_record_id`, acceptance/transport lineage, and investigation membership without altering existing event semantics.
4. Harden the Kafka consumer: await async handlers, validate event idempotency before durable handling, preserve transport position, quarantine parse/domain failures, and commit offsets only after durable disposition.
5. Establish a runnable Temporal worker/activity test environment, configuration for namespace/task queue, and deterministic Continue-As-New coverage.
6. Initialize OTel/Prometheus in API and worker processes and replace static materialization-related health values with durable state.
7. Capture a clean baseline for affected test suites and document pre-existing failures separately.

**Exit gates**

- Accepted ADR and migration ownership.
- Accepted source can be persisted and replayed from `entity_stream` with stable identity and tenant/entity validation.
- No offset can advance before accepted/duplicate/quarantined disposition is durable.
- Migration and worker test environments run from empty and interrupted states.
- No evidence/source hash changes during prerequisite tests.

**Rollback**: Feature migrations are not applied; prerequisite changes remain backward-compatible and independently deployable.

### Phase 1 — Pure domain contracts and deterministic engine

**Depends on**: Phase 0 source identity and policy decisions.

**Work**

1. Add shared frozen domain contracts for `SourceCut`, `MaterializationPolicy`, `ProvenanceManifest`, `WindowRevision`, `TemporalFeatureRecord`, `HistoryPublication`, `TemporalHistory`, `MaterializationRun`, and `QuarantineRecord`.
2. Define the versioned canonical fingerprint contract for source content, window revisions, and publication histories.
3. Wrap feature 012's `from_entity_stream`/window/lifecycle/topology model rather than creating a second lifecycle implementation.
4. Add governed `coverage_end` expansion and explicit trailing dormant windows.
5. Add dynamic-entity eligibility checks and refs-only evidence validation.
6. Define dependency declarations for lifecycle carry-forward and cumulative/TDA feature inputs; compute the affected closure from a late source record.
7. Define deterministic pure operations for source-cut sealing, candidate building, fingerprint comparison, reconciliation, and point-in-time selection.
8. Define versioned feature-provider ports with explicit `available`/`reason`, measured zero, and `structural_only` semantics.

**Exit gates**

- Same accepted source set, policy, schema, and coverage end yields identical windows, ordering, feature values, and fingerprints under shuffled input and replay.
- Exact boundary, multi-window dormant, trailing dormant, late, duplicate, contradictory, missing-tenant/entity, non-dynamic, and insufficient-data fixtures pass.
- No pure-domain import of Kafka, PostgreSQL, ClickHouse, Temporal, FastAPI, or vendor-generated types.
- No `NEEDS CLARIFICATION` remains.

**Rollback**: Pure additive contracts can remain unused; no persisted or user-visible state exists.

### Phase 2 — PostgreSQL/ClickHouse persistence and migrations

**Depends on**: Phase 1 canonical entities and fingerprints.

**Work**

1. Add additive PostgreSQL migrations for source-cut manifests, materialization runs/safe points, immutable window revisions, publication/effectivity records, history heads, outbox, access decisions, and durable quarantine decisions.
2. Add tenant-scoped composite keys, foreign keys, uniqueness/exclusion constraints, append-only protections, and PostgreSQL RLS for every history/run/revision/quarantine/audit path.
3. Implement repositories for candidate staging, exact duplicate suppression, effectivity interval closure/opening, optimistic head advancement, run checkpoints, and transactional outbox writes.
4. Add forward-only ClickHouse migrations for append-only feature revisions and a separately documented disposable current projection.
5. Implement a real ClickHouse feature adapter with bounded batches, stable insert tokens, explicit duplicate suppression, canonical current-row selection, and tenant-scoped queries.
6. Leave legacy `entity_series` unchanged; backfill feature 014 only from immutable source events and evidence references.
7. Add migration tests from empty, upgraded, repeated, and interrupted states.

**Exit gates**

- Prior revisions remain queryable after promotion and rollback.
- Concurrent candidates cannot overwrite a newer head.
- PostgreSQL and ClickHouse tests prove one-to-one window/feature alignment and exact duplicate suppression.
- RLS/API predicates return indistinguishable not-found behavior across tenants.
- Migrations are additive, resumable, and compatible with the old application.

**Rollback**: Disable the feature; leave additive tables and data intact. Do not destructively downgrade audit or revision history.

### Phase 3 — Incremental materialization, late data, and publication

**Depends on**: Phase 2 durable repositories and outbox.

**Work**

1. Implement the keyed incremental service over `entity.stream.appended`, using the accepted PostgreSQL record as input authority.
2. Seal the entity source cut, expand governed coverage, build candidate windows/features, and record the dependency scope.
3. Compare candidate fingerprints with effective revisions; stage only changed windows and carry unchanged revisions forward.
4. Implement reconciliation for expected coverage, missing/extra/divergent windows, revision uniqueness, feature alignment, and history fingerprint.
5. Promote candidate publication and head atomically with audit/outbox records; publish only after commit.
6. Make exact duplicate deliveries and repeated requests no-ops; quarantine contradictory identity reuse without candidate mutation.
7. Preserve the last valid head and expose rebuilding/delayed/degraded state while a new candidate is incomplete.
8. Add bounded entity/run processing with tenant fairness, durable source lag, and independent rebuild/replay scheduling lanes.

**Exit gates**

- Acceptance scenarios AS-001 through AS-008 pass against real PostgreSQL plus the memory/real ClickHouse test seam.
- A late event revises every and only dependency-affected window.
- 1,000 duplicate deliveries create zero accepted events, phantom windows, or revisions.
- Contradictory and malformed records are durably quarantined with actionable reasons.
- A failed downstream feature write cannot advance or partially publish the history head.

**Rollback**: Pause the consumer for affected tenant/home region; continue serving the last valid publication and resume from durable run/checkpoint state.

### Phase 4 — Aligned feature-series publication

**Depends on**: Phase 2 feature store and Phase 3 publication protocol.

**Work**

1. Adapt feature 011 metric/TDA kernels behind a versioned provider contract and full input/output manifest.
2. Publish lifecycle/activity/relationship records and eligible structural features one-to-one with every covered window.
3. Emit explicit unavailable reasons for insufficient, dormant-only, missing dependency, unsupported provider, or bounded-memory cases; never coerce them to zero.
4. Propagate source-record hashes, source cut, policy/schema/provider versions, window revision, and history/window fingerprints.
5. Enforce `structural_only=true` and prohibit identity/truth/source-independence fields in structural outputs.
6. Build historical scans from append feature revisions and a clearly marked current projection; never use CH background merge state as publication proof.

**Exit gates**

- Acceptance scenarios AS-009 through AS-011 pass.
- 100% of feature records align to one and only one covered window/revision.
- Replaying identical provider inputs under pinned versions reproduces every feature value and fingerprint.
- GUDHI/provider absence produces an explicit unavailable state, not fabricated zeros.

**Rollback**: Disable feature publication while preserving the last verified history publication; historical window views remain available and report series availability honestly.

### Phase 5 — Temporal rebuild, resume, and reconciliation

**Depends on**: Phases 1–4.

**Work**

1. Add a deterministic `TemporalMaterializationWorkflow` with stable workflow ID derived from tenant, entity, source cut, policy/schema, and request idempotency key.
2. Add typed bounded activities for source paging, candidate generation, candidate persistence, reconciliation, publication, and safe-point writes.
3. Resume from PostgreSQL safe points and make every activity idempotent by run/window/fingerprint operation key.
4. Use Continue-As-New for large histories, explicit cancellation, and bounded retries; classify domain failures as non-retryable quarantine/rejection.
5. Enforce run admission limits and return explicit backpressure rather than creating an unbounded workflow backlog.
6. Verify interrupted and uninterrupted builds produce the same publication fingerprint.

**Exit gates**

- Acceptance scenario AS-008 passes under crashes at each activity boundary.
- At least 99% of injected interrupted builds resume without manual cleanup and converge within 15 minutes.
- Concurrent rebuilds cannot silently merge; the deterministic valid head wins and stale candidates are retained with reason.
- Missing, extra, or divergent windows prevent promotion.

**Rollback**: Cancel or pause rebuild workflows; active publication remains unchanged and resumable.

### Phase 6 — API, RBAC, audit, health, and existing UI

**Depends on**: Stable publication and rebuild contracts from Phases 3–5.

**Work**

1. Add the FastAPI endpoints and strict response/error models in `contracts/api.md`.
2. Bind tenant/actor from authentication; enforce read, rebuild, quarantine-review, audit, and policy capabilities.
3. Add current/history, point-in-time, window, feature, run, health, audit, and quarantine query/replay operations.
4. Persist audit and access-policy decisions; make foreign resources indistinguishable from absent resources.
5. Replace browser-generated timeline state with server-authoritative windows, revisions, source cuts, completeness, and provenance while reusing existing components.
6. Add tenant-safe investigation/operator status and explicit last-valid versus current-status display.
7. Emit aggregate metrics without raw tenant labels and add alert rules/dashboard panels for lag, failures, fingerprints, reconciliation, quarantine, backpressure, and query latency.

**Exit gates**

- Acceptance scenarios AS-012 through AS-015 pass, including deliberate tenant-ID collisions and role-negative tests.
- No static/global store or unauthenticated status path is used.
- Health/audit changes appear within 60 seconds.
- The 90% analyst usability study can complete the source-cut/completeness task under three minutes.

**Rollback**: Route reads to the legacy view, retain the last valid new publication, and disable rebuild admission without dropping audit/quarantine data.

### Phase 7 — Full validation and staged rollout

**Depends on**: All prior phases.

**Work**

1. Run the complete validation matrix and repository quality gates from [quickstart.md](./quickstart.md).
2. Run deterministic replay, 1,000-delivery, late-event, contradiction, boundary, dormancy, and point-in-time suites.
3. Run real PostgreSQL, Kafka, ClickHouse, Temporal, and API integration tests.
4. Run tenant/RBAC, failure injection, backpressure, retry exhaustion, worker termination, and downstream outage tests.
5. Run the 100,000-history/10,000,000-event representative workload and query-latency measurements.
6. Execute shadow, backfill, canary, and regional cohort rollout with observed gates.
7. Run rollback, migration interruption, and prior-revision availability drills.

**Exit gates**

- All FR-001 through FR-030 and AS-001 through AS-015 have passing evidence.
- SC-001 through SC-012 meet their numeric thresholds.
- No evidence/source mutation, cross-tenant disclosure, unexplained fingerprint mismatch, or incomplete-as-current publication occurs.
- Monitoring and on-call procedures are active before broad enablement.

**Rollback**: Move the affected tenant/home region from `new` to `legacy` or `shadow`, stop new publication, retain the last valid head, and retain candidates/audit for replay.

## Contracts

Detailed interface artifacts are generated in Phase 1 design:

| Contract | Purpose |
| --- | --- |
| [contracts/service-contracts.md](./contracts/service-contracts.md) | Pure domain operations and injectable source/store/feature/audit/publisher ports. |
| [contracts/api.md](./contracts/api.md) | FastAPI endpoints, selectors, response/error schemas, pagination, RBAC, and idempotency. |
| [contracts/events.md](./contracts/events.md) | Input/output Kafka and Protobuf compatibility, keys, idempotency, quarantine, and ordering. |
| [contracts/operations.md](./contracts/operations.md) | State machines, health, reconciliation, retry/backpressure, audit, retention, and rollout controls. |

## Dependency Order and Parallelism

```text
ADR/source prerequisites
  -> pure domain contracts
  -> PostgreSQL/ClickHouse schema
       -> incremental engine + late-data publication
          -> aligned feature publication
             -> Temporal rebuild workflow
                -> API/UI/operations
                   -> full-scale validation and rollout
```

- Phases 1 contract slices and contract-test fixtures can proceed in parallel after Phase 0 decisions.
- PostgreSQL and ClickHouse adapters can be implemented in parallel after canonical entity/fingerprint tests are pinned.
- API schema fixtures and React component fixtures can proceed against mocked contracts while persistence work continues.
- No phase may promote a publication before reconciliation and tenant/security tests are active.

## Validation Strategy

### Requirement traceability

| Requirements / scenarios | Validation layer | Required evidence |
| --- | --- | --- |
| FR-001–FR-012; AS-001–AS-004, AS-009–AS-011 | Shared domain, PostgreSQL/API, ClickHouse feature contract | Complete timeline, explicit dormancy, exact source-cut query, deterministic fingerprint, one-to-one features, structural-only provenance. |
| FR-013–FR-019; AS-003, AS-005–AS-008, AS-011 | Incremental/rebuild integration | Late-event dependency revisions, exact duplicate no-op, contradictory quarantine, interrupted resume, immutable prior revisions. |
| FR-020–FR-024; AS-005, AS-008, AS-015 | Reconciliation/workflow/load/failure | Rebuild equivalence, promotion block on differences, bounded tasks/resources, sustained backpressure, bounded retries. |
| FR-025–FR-030; AS-012–AS-015 | API/RLS/RBAC/audit/health/operations | Tenant-ID collision isolation, role-negative cases, full audit, status age under 60 seconds, last-valid publication on failure. |
| SC-001–SC-004 | Determinism/property/integration tests | Exact cut selection, 100% replay equality, 100% affected-only revisions, 1,000 deliveries with zero changes. |
| SC-005–SC-007 | Performance/chaos tests | p95 current/PIT latency, 100k/10m run, 99% resume convergence within 15 minutes. |
| SC-008–SC-011 | Quarantine/provenance/security tests | 100% actionable quarantine, explicit unavailable values, structural-only labeling, complete audit. |
| SC-012 | Moderated analyst study | At least 90% success under three minutes without assistance. |

### Planned validation layers

1. **Pure unit/property tests**: canonicalization, hash stability, window boundaries, lifecycle, dormancy, availability, dependencies, source identity dispositions, reconciliation.
2. **Contract tests**: pure engine against memory stores; Pydantic/API examples; Protobuf backward compatibility; ClickHouse and PostgreSQL adapter conformance.
3. **Integration tests**: real PostgreSQL/Kafka/ClickHouse/Temporal, transactional outbox, candidate promotion, rebuild resume, tenant RLS.
4. **Failure/security tests**: worker crash, database/CH outage, poison input, retry exhaustion, backpressure, concurrent rebuild, role and cross-tenant negatives.
5. **Performance tests**: representative 100k/10m dataset, burst/backlog recovery, current/PIT query percentiles, status latency, resume duration.
6. **Usability tests**: analyst identification of active/dormant periods, known evidence, source cut/revision, and completeness.

### Quality gates

After implementation, run the commands documented in [quickstart.md](./quickstart.md), including Ruff check/format-check, affected pytest suites, real infrastructure integration tests, Vitest, TypeScript build, Prettier check, and non-mutating repository diff checks. Existing unrelated baseline failures must be fixed or explicitly approved; feature success cannot rely on a “no new failures” waiver.

## Rollout and Rollback

### Rollout stages

1. **Governance/preflight**: accepted ADR, schema inventory, source hashes/counts captured, no application behavior changed.
2. **Expand**: additive PostgreSQL/ClickHouse migrations applied; old application remains compatible; read path still legacy.
3. **Shadow**: allowlisted tenant/home-region cohorts build and reconcile candidates; no user-visible publication.
4. **Backfill**: bounded 1-tenant, 5-tenant/5%, 25%, 50%, then 100% regional cohorts; retain previous heads and audit every batch.
5. **Canary read**: internal/test tenants use the new API/UI while ordinary users remain legacy; compare aggregate results without cross-tenant exposure.
6. **Regional enablement**: 1%/internal, 5%, 25%, 50%, 100% per home region with at least one full seven-day policy window of soak time before the next region.
7. **Default/retire writes**: make new histories default only after all gates; retain legacy read/rebuild support for the approved rollback window.

### Activation modes

- `legacy`: no new candidates or reads.
- `shadow`: candidates/reconciliation only; legacy reads remain authoritative.
- `canary`: allowlisted tenants/regions may read new publications.
- `new`: eligible cohorts use the materialization publication; last-valid fallback remains available.

Configuration must be tenant/home-region scoped, versioned, and audited; no global bypass is permitted.

### Automatic stop/rollback triggers

- Any evidence/source count or hash change.
- Any cross-tenant value, count, status, timing, error, or existence disclosure.
- Any unexplained missing/extra/divergent window or fingerprint mismatch.
- Any incomplete/delayed candidate presented as current.
- Source/status age over 60 seconds beyond the approved grace interval.
- Current-view p95 over 2 seconds or point-in-time p95 over 3 seconds for 15 minutes.
- Sustained unbounded backlog, retry amplification, or publication failure.
- Resume convergence below 99% or inability to preserve the last valid publication.

### Rollback behavior

- Stop new publication/rebuild admission for the affected tenant/home region.
- Route reads to legacy or the last valid new publication and identify it as such.
- Retain candidate/revision/audit/quarantine data for diagnosis; do not delete or destructively downgrade it.
- Resume/replay from the durable source cut and run safe point after correction.
- Require a fresh reconciliation and explicit operator action before re-enabling `new`.

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Existing 011 ClickHouse path is incomplete | Use kernels only; require real adapter, migration, and live integration tests before publication. |
| Source identity is absent in current streams | Phase 0 adds an explicit producer-scoped identity and compatibility migration; materialization fails closed without it. |
| Kafka consumer can lose or skip work | Repair async/offset/quarantine behavior and test crash/duplicate delivery before adding consumers. |
| Full history snapshots scale poorly | Store one immutable revision per changed window plus cut-range effectivity/publication manifests, not a full copy per event. |
| ClickHouse and PostgreSQL cannot transact together | Stage, reconcile, verify, then atomically publish a PostgreSQL pointer; never use CH merge state as authority. |
| Lifecycle late data affects later windows | Use explicit dependency closure and fingerprint comparison, not arrival-time updates. |
| Structural zero is mistaken for measured zero | Separate availability/reason and enforce structural-only provenance. |
| Existing global routes leak tenant data | New repositories/routes use tenant-bound keys, RLS, authenticated context, and negative tests. |
| Rollout exceeds operational capacity | Tenant/home-region cohorts, bounded backpressure, independent rebuild lane, and stop thresholds. |

## Complexity Tracking

No constitution violations or exceptions are required. The project remains a single monorepo with the existing shared/projection/control-plane/web separation; the new materialization package is a feature module, not a new project or architecture exception.

## Plan Completion Gate

Planning is complete when the human plan review approves this document and the generated [research](./research.md), [data model](./data-model.md), [contracts](./contracts/), and [quickstart](./quickstart.md) artifacts. `/speckit.tasks` may then create `tasks.md`; this `/speckit.plan` execution must not implement application code.
