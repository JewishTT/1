---

description: "Task list for Global OSINT Intelligence Platform implementation"
---

# Tasks: Global OSINT Intelligence Platform

**Input**: Design documents from `/specs/001-global-osint-platform/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Organization**: Tasks are grouped by user story (US1 = Run an Investigation End-to-End, US2 = Evidence-Backed Expert Search & Analysis, US3 = Operate, Govern, Scale) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1/US2/US3)
- Include exact file paths in descriptions

## Path Conventions

Monorepo per `plan.md` Project Structure: `apps/control-plane`, `apps/acquisition`, `apps/interpretation`, `apps/admission`, `apps/projection`, `apps/feedback`, `apps/shared`, `apps/webapp`, `apps/deploy`, `bench/`. Python apps use `uv` (pytest), Rust uses cargo, frontend uses pnpm + Vitest.

Tests are included because the Constitution (SC-005) requires invariant enforcement via tests/factories and the benchmark harness (FR-034) is part of deliverable scope.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Monorepo initialization and dev topology

- [x] T001 Create monorepo structure per plan.md (`apps/{control-plane,acquisition,interpretation,admission,projection,feedback,shared,webapp,deploy,bench}`) with root `.gitignore`, `README.md`, `.env.example`
- [x] T002 Initialize Python workspace for control-plane/interpretation/admission/projection/feedback/shared with `uv` (`pyproject.toml`, deps: fastapi, pydantic v2, sqlalchemy[asyncio], asyncpg, confluent-kafka, redis, aioboto3, opensearch-py, clickhouse-connect, gudhi, giotto-tda, numpy, scipy, opencensus, pytest, pytest-asyncio, testcontainers)
- [x] T003 Initialize Rust workspace `apps/acquisition` (crates: `worker-http`, `dispatcher`, `frontier`, `discovery`, `content-router`; deps: tokio, reqwest, hyper, sha2) with `cargo fmt`/`clippy` config
- [x] T004 Initialize frontend `apps/webapp` (Vite + React 18 + TypeScript, Router, TanStack Query, Zustand, Cytoscape.js, ECharts)
- [x] T005 [P] Author dev topology `apps/deploy/docker-compose.yml` (MinIO, Kafka KRaft x1, Schema Registry, PostgreSQL 16, Redis, OpenSearch, ClickHouse, Neo4j 5, Temporal) with healthchecks and fixture bucket seeding
- [x] T006 Configure lint/format: `ruff` (Python), `prettier` (TS), `cargo fmt/clippy` (Rust); add pre-commit config
- [x] T007 Implement env/config bootstrap `apps/shared/config/settings.py` (pydantic-settings, reads `.env`, per-app overrides)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Contracts + durable substrate that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T008 Create EventEnvelope protobuf + full topic catalog in `apps/shared/events/event_envelope.proto` (envelope per `contracts/event-envelope.proto`; topics per spec FR-023)
- [x] T009 [P] Implement Schema Registry client + versioned payload registry in `apps/shared/events/registry.py` (register/fetch by event_type+event_version)
- [x] T010 [P] Implement idempotent Kafka producer/consumer base in `apps/shared/events/kafka.py` (dedup on event_id/task_id/observation_id, offsets bookkeeping)
- [x] T011 Implement Storage contract in `apps/shared/storage/s3.py` (content-addressed `s3://knowledge/raw/{tenant}/{ym}/{sha256}` per `contracts/storage.md`, dedup-on-hash, immutability guard)
- [x] T012 Create Postgres operational schema + Alembic migrations in `apps/control-plane/db/migrations` (investigation, source, policy, budget, frontier_item, acquisition_task, observation, mention, candidate, entity, entity_version, assertion, evidence_link, admission_decision, projection, topological_feature, finding, model_version, host_state)
- [x] T013 [P] Implement RBAC + tenant-scoped auth middleware `apps/control-plane/api/auth.py` (tenant_id resolution, scoped queries — isolation foundation, FR-029/FR-032)
- [x] T014 Implement domain base + invariant enforcement in `apps/shared/domain/__init__.py` (ConstraintViolation on I-1 observation immutable, I-2 Mention/Candidate/Entity separation, I-5 no blobs on Kafka, I-12 projections rebuildable — enforced at model layer)
- [x] T015 Implement observability bootstrap `apps/shared/observability/__init__.py` (OpenTelemetry tracing, Prometheus counters/histograms, structured logging)
- [x] T016 Bootstrap Temporal client + worker connection `apps/shared/workflow/client.py` (namespaces, task queues, retry policy config)
- [x] T017 Contract + invariant tests: `apps/shared/tests/contract/test_event_envelope.py`, `test_storage.py`, `test_domain_invariants.py` (write FIRST, must FAIL before implementations land)

**Checkpoint**: Foundation ready — events, storage, schema, auth, invariants, observability all contract-tested; user stories can start.

---

## Phase 3: User Story 1 - Run an Investigation End-to-End (Priority: P1) 🎯 Core Loop

**Goal**: Closed intelligence loop per §84: Investigation → seeds → discovery → frontier → acquisition → immutable Observation → Kafka → parse/mentions/candidates/assertions → resolution → admission → projections → snapshot → TDA → TopologicalFeature → Finding → feedback → new acquisition, with traceability at every hop.

**Independent Test**: `bench/run --scenario smoke-val` (per quickstart.md) runs steps 1–8 against a clean compose stack on fixtures with zero manual DB pokes; every finding links to a raw object in MinIO.

### Tests for User Story 1 (Constitution SC-005: invariant tests)

> Write these FIRST, ensure they FAIL before implementation.

- [x] T018 [P] [US1] E2E smoke harness scaffold `bench/run.py` (provision compose, poll observations, assert chain) + `bench/fixtures/` (served pages, sitemap, rss, mirrored page graph)
- [x] T019 [P] [US1] Invariant test: observation immutability in `apps/control-plane/tests/integration/test_observation_immutability.py`
- [x] T020 [P] [US1] Invariant test: idempotent replay of `observation.created` causes no duplicates in `apps/shared/tests/integration/test_idempotency.py`

### Implementation for User Story 1

**Control plane**

- [x] T021 [P] [US1] Investigation domain + state machine in `apps/control-plane/domain/investigation.py` (DRAFT→PLANNING→RUNNING→PAUSED→COMPLETED→ARCHIVED, budget/scope validation)
- [x] T022 [P] [US1] Policy & Budget models + policy engine (pre-dispatch validation, retention) in `apps/control-plane/domain/policy.py` and `apps/control-plane/services/policy_service.py`
- [x] T023 [P] [US1] Source registry + SourceProfile in `apps/control-plane/services/source_registry.py` (capabilities, quality profile, yield/cost/freshness)
- [x] T024 [US1] Investigation + sources + policy API routes in `apps/control-plane/api/routes/investigations.py` (create/update/pause/resume/archive; emits `investigation.created/.updated`)

**Discovery → Frontier → Acquisition**

- [x] T025 [US1] Discovery engine in `apps/acquisition/discovery/` (Rust: sitemap/sitemap-index/RSS/Atom/HTML links; each discovery event carries method/source_id/parent_observation/timestamp/confidence)
- [x] T026 [US1] Frontier in `apps/acquisition/frontier/` (Rust + Postgres authoritative, Redis lease/cooldown, hierarchical keys per spec §12) — Rust crate contract + `apps/control-plane/services/frontier.py` authoritative impl
- [x] T027 [P] [US1] UtilityScorer heuristic + AdaptiveState impl in `apps/shared/scoring/scorer.py` (implements `contracts/utility-scorer.md`; EWMA adaptive per source/host)
- [x] T028 [US1] HTTP worker (Rust) implementing AcquisitionWorker contract in `apps/acquisition/worker-http` (capabilities/estimate/acquire, callbacks to Storage + Kafka)
- [x] T029 [US1] Dispatcher/scheduler loop in `apps/acquisition/dispatcher` (Rust: scores frontier, respects budgets/cooldowns/retry, backpressure reads downstream lags) — Rust core contract + Python orchestration
- [x] T030 [US1] Content router + dedup in `apps/acquisition/content-router` (MIME detect, size validation, hashing, request/canonical-url/exact-hash dedup, conditional acquisition etag/last-modified) — shared `content_router.py`
- [x] T031 [US1] Observation gate (store raw → `observation.created/.unchanged/.duplicate` events; observation immutable enforce) — shared `observation_gate.py`

**Interpretation**

- [x] T032 [P] [US1] Observation→segments parser scaffold `apps/interpretation/parsers/` (HTML/JSON/XML/PDF/plain dispatch — heavy parsers isolated) — `parsers/registry.py`; 4 tests
- [x] T033 [P] [US1] Mention extractor registry + baseline NER `apps/interpretation/ner/extractors.py` (extractor_version provenance; emits surface_form+offsets AND normalized_form+transliteration_variants+script+language+normalization_version per FR-011; deterministic extractors follow T081) — `extractors/registry.py` (email/url/ipv4/domain/CVE/sha256/md5/hash/token/crypto); 3 tests
- [x] T081 [P] [US1] Normalization + deterministic/gazetteer stage `apps/interpretation/ner/normalize.py` (language/script detection → Unicode → transliteration variants → OCR-normalization → gazetteer/deterministic extractors for URL/email/IP/CIDR/hash/date/doc-number/domain/crypto-address → NER; original surface_form never replaced) — `normalization/canonical.py`; 3 tests
- [x] T034 [US1] Candidate aggregation + candidate graph `apps/interpretation/candidates.py` (aggregate mentions; candidate.created events; noisy Candidate Graph kept separate) — `aggregation/candidates.py` composite confidence + aliases; 1+ tests

**Admission / Resolution / Evidence**

- [x] T082 [P] [US1] Multi-strategy blocking `apps/admission/resolution/blocking.py` (keys: name prefix, phonetic, transliteration, email/domain, id-fragments, date/year, location, org, same-doc, co-occurrence, shared handle; union candidate pairs; complexity benchmark — no O(N²)) — implements `contracts/resolution-admission.md`; 4 tests
- [x] T035 [P] [US1] Pairwise resolver + pipeline glue `apps/admission/resolution/resolver.py` (per-type signal scoring → raw_pair_score + reasons; consumes T082 pairs; entity versions) — 2 tests
- [x] T083 [US1] Collective/graph-aware resolution `apps/admission/resolution/collective.py` (candidate-resolution graph → relational propagation → re-score → cluster/resolve; iterate until convergence; output = raw_pair_score + collective_score + reasons — no opaque graph magic) — 2 tests
- [x] T084 [P] [US1] Temporal consistency + retraction `apps/admission/engine/temporal.py` (relation-specific temporal policy single/multi/interval/append-only/supersedable/contradictory; assertion state machine ASSERTED→SUPERSEDED|RETRACTED|CONTRADICTED|EXPIRED; supersedes/replacement links — original never deleted; FR-016) — 3 tests
- [x] T087 [P] [US1] Source Independence Engine `apps/admission/evidence/independence.py` (citation/derivation graph: cites/copies/references/rewrites; independent_evidence_chains; independence score → evidence fusion; FR-015) — 3 tests
- [x] T037 [US1] Assertion extractor + EvidenceLink builder `apps/admission/engine/assertions.py` (evidence_refs, valid/observed time; publication_count separate from independent_support and independent_evidence_chains — FR-015, per T087) — 2 tests
- [x] T036 [P] [US1] Admission engine core `apps/admission/engine/admission.py` (score_vector separate fields, ACCEPT_NEW/ACCEPT_EXISTING/DEFER/REJECT/QUARANTINE, evidence refs, model/policy versions; rejected kept replayable; FR-013/014) — 5 tests
- [x] T086 [US1] Risk-sensitive calibrated admission `apps/admission/engine/calibration.py` (epistemic policy: categorical hard-reject rules FIRST — invalid identifier→REJECT, explicit strong contradiction→QUARANTINE/REJECT per policy, insufficient evidence→DEFER default, strong corroboration→ACCEPT; CalibrationProfile lookup by entity_type/language/script; per-type thresholds; UNCALIBRATED bootstrap v1 → later CALIBRATED per T085; consumes T081–T084, T087) — MediaProfile + profiles in `engine/calibration.py`

**Projections**

- [x] T038 [US1] Graph abstraction impl + Neo4j adapter in `apps/projection/graph/` (implements `contracts/graph.md`, no vendor imports in application code) — `graph/abstraction.py` (I-11 idempotent, I-12 provenance, node-type immutable) + `graph/neo4j.py` (only vendor import site); 4 tests
- [x] T039 [P] [US1] Search projector → OpenSearch indices (observations/documents/mentions/candidates/entities/assertions/findings) `apps/projection/search/projector.py` — 6 kinds + findings; index abstraction `search/index.py`; rebuild idempotent; 4 tests
- [x] T040 [P] [US1] Analytics projector → ClickHouse (observation metrics, per-source aggregates, cost accounting) `apps/projection/analytics/projector.py` + `store.py`; idempotent inserts, rebuild from log; 2 tests
- [x] T041 [US1] GraphSnapshot + rebuild(projection_id) from Kafka offsets (I-12) in `apps/projection/graph/snapshot.py` — RebuildableGraphStore logs replay events, snapshot head + checksum, rebuild reproduces; 1 test

**TDA**

- [x] T042 [US1] TDA pipeline in `apps/projection/tda/pipeline.py` (adaptive subgraph → weighted filtration Gλ → GUDHI persistence H0/H1/H2, configurable dimension/memory budget, single-vs-multiparameter separated) — `AdaptiveSubgraph` (budget-guarded), `GudhiProvider`, `TDAPipeline`; single-param Vietoris–Rips; multiparameter → NotImplementedError; 3 tests
- [x] T043 [US1] TopologicalFeature materialization + `tda.completed` events in `apps/projection/tda/features.py` (birth/death/persistence, supporting nodes/edges, algorithm_version; feeds admission/feedback as structural signals ONLY — identity claims come exclusively from resolution (I-6), never from TDA) — `structural_only` invariant enforced; 2 tests

**Feedback + Web**

- [x] T044 [US1] Feedback engine `apps/feedback/engine.py` (new entities/relations/discoveries/topological signals → priority/recrawl/discovery/budget; `feedback.generated`) — 4 tests
- [x] T045 [US1] Stopping policy `apps/feedback/stopping.py` (marginal information gain decay → SLEEP/STOP; frontier explosion guard) — 4 tests
- [x] T046 [P] [US1] Investigation pipeline UI page `apps/webapp/src/pages/InvestigationPage.tsx` (objective, acquisition qps/queue/freshness, interpretation counters, admission verdicts, knowledge counts, analysis panel) — 3 vitest tests + wired route `App.tsx`
- [x] T047 [US1] Lineage walker component `apps/webapp/src/components/LineageWalker.tsx` (Finding → feature → graph/assertion → evidence → observation → raw source, per FR-032) — 2 vitest tests; tsc build clean + prettier formatted
- [x] T077 [P] [US1] Request coalescing + canonical fan-out in `apps/acquisition/dispatcher/coalesce.rs` (coalesce identical acquisition intents across investigations → one acquisition → one observation → fan-out; depends on T029, T030 — FR-008) — implemented as shared `coalesce.py`
- [x] T078 [US1] Temporal investigation/recrawl workflows in `apps/control-plane/workflows/investigation.py` (long-running lifecycle, scheduled recrawls, multi-step acquisition, pause/resume, human approval, workflow recovery — uses T016; FR-022) — `InvestigationLifecycle` pure state machine + `InvestigationWorkflow`/`RecrawlWorkflow` (pause/resume/approve/reject/schedule_recrawl/complete signals, checkpoint recovery); 12 tests

**Checkpoint**: `bench/run --scenario smoke-val` green — US1 core loop is fully functional and independently testable: the closed loop runs on fixtures with validated lineage.

---

## Phase 4: User Story 2 - Evidence-Backed Expert Search & Analysis (Priority: P2)

**Goal**: Query planner fusing OpenSearch/graph/ClickHouse/TDA behind one surface; entity view and finding view with evidence links; graph canvas as one panel.

**Independent Test**: Index fixture corpus → hybrid query with temporal/source/investigation filters returns fused results whose evidence chain resolves to immutable observations; entity view shows versions + timeline + structural signals.

### Tests for User Story 2

- [x] T048 [P] [US2] Integration test: hybrid query fusion returns evidence-linked results in `apps/control-plane/tests/integration/test_query_planner.py` — 5 tests (fusion, evidence→immutable obs (I-1), source/investigation filters, ranked bounded scores)
- [x] T049 [P] [US2] Integration test: entity + finding lineage drill-down in `apps/control-plane/tests/integration/test_lineage_api.py` — 4 tests (versions/aliases/signals, evidence anchors, finding→obs→sources, full FR-032 chain)

### Implementation for User Story 2

- [x] T050 [P] [US2] Query planner `apps/control-plane/services/query_planner.py` (query understanding → route to OpenSearch/graph/ClickHouse/TDA metadata → result fusion → evidence links; user never sees backend choice) — `QueryPlanner`+`BackendClient` protocol+`MemoryBackend`; `FusedResult` carries uniform evidence → immutable obs
- [x] T051 [P] [US2] Search plane endpoints `apps/control-plane/api/routes/search.py` (lexical/semantic/hybrid + metadata/temporal/source/investigation filters) — GET/POST, hermetic fixture corpus
- [x] T052 [P] [US2] Entity overview API `apps/control-plane/api/routes/entities.py` (current state, historical versions, aliases, relationships, supporting assertions, evidence, timeline, structural signals) — backed by `services/catalog.py::Catalog`
- [x] T053 [P] [US2] Finding overview API `apps/control-plane/api/routes/findings.py` (why detected, structural/semantic evidence, supporting graph region, assertions, observations, raw source) — + `GET /findings/{id}/lineage` (FR-032 chain)
- [x] T054 [P] [US2] Webapp search page `apps/webapp/src/pages/SearchPage.tsx` (hybrid query + filters + result fusion display) — 3 vitest tests; evidence links render uniform association, fused obs count
- [x] T055 [P] [US2] Webapp entity view page `apps/webapp/src/pages/EntityViewPage.tsx` — 3 vitest tests (identity/aliases/timeline/signals + I-1 evidence integrity)
- [x] T056 [P] [US2] Webapp finding view page `apps/webapp/src/pages/FindingViewPage.tsx` — 3 vitest tests (reason, region, obs+sources, FR-032 lineage walk)
- [x] T057 [US2] Graph canvas panel (Cytoscape) embedding in search/entity views `apps/webapp/src/components/GraphPanel.tsx` (panel, not main interface) — lazy cytoscape; 3 vitest tests; wired into SearchPage/EntityViewPage/FindingViewPage

**Checkpoint**: US1 + US2 work independently — search/entity/finding UX delivers provable (evidence-linked) answers.

---

## Phase 5: User Story 3 - Operate, Govern, and Scale (Priority: P3)

**Goal**: Multi-tenant isolation, RBAC + audit, backpressure/retry budgets, dead-letter/quarantine, operational dashboard, worker failure isolation, multi-region acquisition topology.

**Independent Test**: Two tenants run parallel investigations with no cross-tenant leakage in data/events/search/graph/storage/budgets; forced projection failure preserves evidence; malformed data lands in quarantine preserved; downstream overload throttles acquisition instead of growing backlog.

### Tests for User Story 3

- [x] T058 [P] [US3] Integration test: cross-tenant isolation matrix in `apps/control-plane/tests/integration/test_tenancy.py`
- [x] T059 [P] [US3] Integration test: backpressure throttling + retry budgets in `apps/acquisition/tests/integration/test_backpressure.py`
- [x] T060 [P] [US3] Integration test: dead-letter/quarantine preservation + replay in `apps/control-plane/tests/integration/test_quarantine.py`

### Implementation for User Story 3

- [x] T061 [P] [US3] Tenant isolation hardening (per-tenant Kafka ACLs/partitions, OpenSearch index aliases, S3 prefixes, graph namespaces, budget/policy scoping) across `apps/shared/` + deploy config
- [x] T062 [P] [US3] Audit log service `apps/control-plane/services/audit.py` (decision/projection/access audit events + Postgres copy, FR-029)
- [x] T063 [US3] Backpressure control loop `apps/acquisition/dispatcher/backpressure.rs` (queue-depth/lag → rate limiter; no unbounded Kafka backlog)
- [x] T064 [P] [US3] Retry budget enforcement (task/source/investigation/global) in dispatcher + worker callbacks
- [x] T065 [P] [US3] Dead-letter/quarantine handlers `apps/shared/events/dlq.py` + control-plane replay/re-evaluation API (rejected candidates preserved)
- [x] T066 [P] [US3] Worker pool failure isolation (HTTP/browser/document/OCR/vision/TDA pools independent; one failing pool doesn't stop others)
- [x] T067 [US3] Browser fabric escalation path `apps/acquisition/worker-browser/` (Playwright pool, escalation-only route, isolated pool)
- [x] T068 [P] [US3] Operational dashboard page `apps/webapp/src/pages/OpsDashboardPage.tsx` + metrics API `apps/control-plane/api/routes/metrics.py` (throughput, useful observations, discovery yield, duplicate ratio, browser utilization, lags, queues, storage growth, cost)
- [x] T069 [P] [US3] Multi-region topology design docs + regional frontier partition config in `apps/deploy/k8s/` and `docs/architecture/multi-region.md`
- [x] T079 [US3] Flink stateful jobs in `apps/projection/streams/` (temporal windows, stream joins, change/pattern detection, real-time counters, online signals — genuine stateful work only, never transport per FR-021; depends on T038–T040)

**Checkpoint**: US1 + US2 + US3 work independently — governance, isolation, backpressure, DLQ, ops dashboard all pass their tests.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: ADRs, benchmark harness, security hardening, dashboards, docs.

- [x] T070 [P] Write ADR set in `docs/adr/` (per FR-033/Constitution Governance): 0001 Kafka vs alternatives, 0002 object storage, 0003 PostgreSQL role, 0004 OpenSearch, 0005 ClickHouse, 0006 Flink role, 0007 Temporal, 0008 graph abstraction, 0009 graph backend selection, 0010 TDA architecture, 0011 event schema, 0012 provenance, 0013 entity resolution, 0014 admission engine, 0015 frontier architecture, 0016 scheduling, 0017 recrawl strategy, 0018 multi-region topology
- [x] T071 [P] Benchmark harness `bench/` (acquisition req/s + useful obs/s + new urls/s; knowledge docs/hour, accepted assertions/hour, resolution latency; search p50/p95/p99; graph projection throughput/traversal/snapshot; TDA nodes/edges/dims/memory/runtime/feature stability; cost per million observations/assertions/discoveries) with reproducible run + report
- [x] T085 [P] [US2] Knowledge-quality harness `bench/knowledge/` (gold corpus → pair/cluster P/R/F1, false merge/split, Brier/ECE calibration, per-type/language/script breakdown, contradiction handling, source-independence accuracy; measures bootstrap v1 `CalibrationProfile`, builds calibration curves, picks operating points under asymmetric false-merge/false-split cost, emits new immutable CALIBRATED profile — CI knowledge-quality gate per SC-011/SC-012; depends on T082–T084, T087)
- [x] T072 [P] Security hardening pass (SSRF/DNS-rebinding guards, sandboxed parsers, browser isolation, egress policy, CPU/mem/timeout/size/archive-depth/file-count limits enforcement) reviewed against FR-029
- [x] T073 [P] Grafana dashboards + KPI panels (useful_knowledge per total resource cost, freshness-lag, queue-age, projection-lag) `apps/deploy/grafana/`
- [ ] T074 Performance optimization across hot paths (Rust acquisitions, projection batching)
- [x] T075 Final validation: full `quickstart.md` scenario + all stories' independent tests green on clean compose stack
- [x] T076 Project docs (`docs/README.md`, architecture overview, contribution guide)

## Phase 7: Global Collection Fabric (Architecture Review Extension, T088–T136)

**Source**: `specs/001-global-collection-fabric/` (architecture review + phased plan, research.md R-01..R-15). IDs continue the repo series from T087. Grouping per research.md R-15.

### Setup (scaffolding)

- [x] T126 [P] Create `apps/acquisition/{contracts,adapters,observation-gate}` directory skeletons (with README + module stubs) in `1/apps/acquisition/`
- [x] T127 [P] Register new top-level app groups in workspace manifests: add `apps/bulk-ingestion`, `apps/projection/streams`, `apps/projection/lakehouse` to `1/pyproject.toml` `[tool.uv.workspace]` members; add matching crate crates where Rust-based
- [x] T128 Register the T088–T136 task block in the platform backlog `1/specs/001-global-osint-platform/tasks.md` (Phase A–E grouping from research.md R-15)

### Foundational Contracts (blocks all stories)

- [x] T088 [P] Async `AcquisitionWorker` trait (capabilities(), estimate(), acquire()) + worker outcome/audit structure in `1/apps/acquisition/contracts/`
- [x] T089 [P] `CollectionAdapter` trait (resolve policy requirements, capability surface, lifecycle: init/start/suspend/stop) in `1/apps/acquisition/contracts/`
- [x] T090 [P] Capability registry + selection (R-03: capability-intersection match; CapabilityGap; fallback baseline `http`) in `1/apps/acquisition/adapters/` and Rust `contracts/`
- [x] T103 [P] EventEnvelope v2: mandatory `tenant_id` + routing fields `source_id`/`work_id`/`region_id` on every envelope (proto + generated bindings + `build_envelope`) in `1/apps/shared/events/`
- [x] T104 [P] Event catalog: register acquisition lifecycle + feedback three-way split event types in `1/apps/shared/events/topics.py`
- [x] T129 [P] Implement Observation Manifest schema + validation (json model from contracts/observation-manifest.md) in `1/apps/acquisition/contracts/manifest.rs`
- [x] T137 [P] Contract test for async `AcquisitionWorker` trait in `1/apps/acquisition/tests/contract/test_worker.rs`
- [x] T138 [P] Contract test for `CollectionAdapter` trait in `1/apps/acquisition/tests/contract/test_adapter.rs`
- [x] T139 [P] Contract test for `EventEnvelope` v2 proto fields in `1/apps/shared/tests/contract/test_event_envelope.py`

### US1 — Closed-Loop Acquisition (Core)

- [x] T091 [US1] Move AcquisitionWorker to async; worker-http implements `capabilities()` (RFC-9110 ETag/Last-Modified) in `contracts/capabilities.md`, `estimate()`, `acquire()` in `1/apps/acquisition/worker-http/`
- [x] T110 [US1] Implement worker capability-aware scheduling (choose execution class by match + cost) in `1/apps/acquisition/dispatcher/`
- [x] T132 [US1] Implement intelligence scheduler stage (utility/novelty/freshness/expected-gain/cost) in `1/apps/acquisition/dispatcher/` (reuses `apps/shared/scoring/scorer.py` UtilityScore)
- [x] T133 [US1] Implement resource scheduler stage (region, worker-class availability, browser capacity, host concurrency, queue depth, source limits) in `1/apps/acquisition/dispatcher/`
- [x] T130 [US1] Implement Observation Gate: single content-addressed write path (sha256 → S3/MinIO) with mandatory `raw_ref` on every outcome in `1/apps/acquisition/observation-gate/`
- [x] T131 [US1] Emit observation lifecycle events (`created`/`changed`/`unchanged`/`duplicate`) from the gate into Redpanda in `1/apps/acquisition/observation-gate/`
- [x] T111 [US1] Extend adaptive state to source level (`SourceState`: yield/change_rate/freshness/cost/error_rate/independence_yield) in `1/apps/shared/scoring/scorer.py`
- [x] T112 [US1] Extend adaptive state to worker-class level (`WorkerClassState`: throughput/latency/saturation/failure_rate/queue_age) in `1/apps/shared/scoring/scorer.py`
- [x] T114 [P] [US1] Add collection metrics (collector throughput, frontier enqueue/dequeue rate, scheduler decision latency) in `1/apps/shared/scoring/metrics.py` and `1/bench/`
- [x] T116 [US1] Implement source-independence feedback branch (yield/cost/freshness → next utility) in `1/apps/feedback/`
- [x] T117 [US1] Implement entity-resolution → acquisition-hypothesis feedback (aliases/identifiers → new retrieval keys → FrontierItems) in `1/apps/feedback/`
- [x] T118 [US1] Implement finding → new-work feedback (FindingCandidate → UtilityScorer → Frontier) in `1/apps/feedback/`

### US2 — Expert Search & Analysis

- [x] T102 [US2] Add Common Crawl index access (existing `commoncrawl` dependency; badges/pagination) in `1/apps/shared/network/commoncrawl.py`
- [x] T095 [US2] Implement capability-annotated engine facade (badge: `capability.match-by-badges`) in `1/apps/control-plane/badges/`
- [x] T109 [US2] Implement cross-semantic search retriever (fuzzy badge + capability-aware, fuzzy over badge names/aliases) in `1/apps/interpretation/search/`
- [x] T094 [US2] Implement Entity/ID mismatch adapter (badge matching, entity-link dedupe, modify urgency) in `1/apps/control-plane/modifier/`
- [x] T093 [US2] Implement WARC retrieval (fetch WARC, scan CDX) in `1/apps/acquisition/adapters/warc/`
- [x] T092 [US2] Implement Common Crawl discovery reservoir (WPEX/WAT/WET index → frontier) in `1/apps/acquisition/adapters/commoncrawl/`
- [x] T105 [US2] Add crawler headless browser cluster + visibility overlay (SS/Collusion cluster ↔ coverage overlay) in `1/apps/acquisition/worker-browser/`
- [x] T106 [US2] Add crawler archival mode (WARC/ARClint; visibility overlay) in `1/apps/acquisition/worker-http/`
- [x] T107 [US2] Add crawler JS rendering (headless, leftover DOM; visibility overlay) in `1/apps/acquisition/worker-browser/`
- [x] T098 [US2] Add Browsertrix engine adapter (browser worker pool) in `1/apps/acquisition/adapters/browsertrix/`
- [x] T096 [US2] Add Heritrix engine adapter (archival WARC-first collection) in `1/apps/acquisition/adapters/heritrix/`
- [x] T099 [US2] Add StormCrawler engine adapter (distributed streaming crawl engine) in `1/apps/acquisition/adapters/stormcrawler/`
- [x] T100 [US2] Add Nutch engine adapter (bulk crawl backend) in `1/apps/acquisition/adapters/nutch/`

### US3 — Operate, Govern, Scale

- [x] T113 [US3] Implement region-level backpressure in `1/apps/acquisition/dispatcher/`
- [x] T119 [US3] Implement multi-region frontier partitioning with globally unique `observation_id`/`event_id`/`entity_id` in `1/apps/acquisition/frontier/`
- [x] T120 [US3] Implement collector replay/reprocessing (resume from durable state after crash) in `1/apps/acquisition/observation-gate/`
- [x] T121 [US3] Implement historical archive replay (Common Crawl bulk → batch discovery → Frontier) in `1/apps/bulk-ingestion/historical/`
- [x] T122 [US3] Write bulk/live convergence tests (common URL in archive + live) in `1/apps/acquisition/tests/integration/test_bulk_live_convergence.py`
- [x] T123 [US3] Add 1M-observation acquisition benchmark in `1/bench/`
- [x] T124 [P] [US3] Add 10M-observation acquisition benchmark in `1/bench/`
- [x] T125 [US3] Add failure/replay chaos tests (kill worker mid-acquisition; replay projection) in `1/bench/`
- [x] T101 [US3] Implement re-observation dedup + three-way split on Etag (`304`/`hash`-only changes/no-change) in `1/apps/acquisition/frontier/`
- [x] T108 [US3] Implement bulk historical backfill package (Common Crawl + Wayback CDX, linio via archive) in `1/apps/bulk-ingestion/`
- [x] T127b [US3] Implement collector replay/reprocessing (resume from durable state after crash) in `1/apps/acquisition/observation-gate/` (alias of T120; listed here for full coverage)

### Polish (Final)

- [x] T115 [P] Add cost-per-useful-observation KPI (`useful_findings / (network+compute+storage+worker cost)`) to `1/bench/` and `1/apps/shared/scoring/metrics.py`
- [x] T134 [P] Run full quickstart.md validation (scenarios A/B/C) and record results in `1/docs/`
- [x] T135 [P] Update architecture docs (data-plane, topic taxonomy, feedback loops, phased deployment) in `1/docs/`
- [x] T136 [P] Add dev compose profiles (`core`/`streaming`/`collectors`/`analytics`) in `1/apps/deploy/docker-compose.yml`
- [x] T140 [P] Expose the Collection Fabric zero-layer as backend endpoints under `1/apps/control-plane/api/routes/fabric.py` (badge/engine selection T095, re-observation+etag T101, modifier T094, cross-semantic search T109, frontier T119, worker pools, region backpressure T113, throttle, bulk backfill plan/cdx/replay T108/T121) with controller-side hermetic tests in `1/apps/control-plane/tests/unit/test_fabric_endpoints.py`

**Execution order**: Setup (T126/T127/T128) → Foundational (T088/T089/T090/T103/T104/T129 + T137/T138/T139) → US1 closed loop → US2 → US3 → Polish. Details in `specs/001-global-collection-fabric/plan.md`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational completion
  - US1 (Phase 3) → US2 (Phase 4) → US3 (Phase 5) sequential by priority, or parallel if staffed
- **Polish (Phase 6)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1)**: After Foundational — no dependencies on other stories
- **US2 (P2)**: After Foundational — needs US1 projections/search indices to query but is independently testable after its tests index fixtures; integrates with US1 endpoints
- **US3 (P3)**: After Foundational — needs US1 dispatcher/frontier + US2 dashboards integration, independently testable at the isolation/budget level

### Within Each User Story

- Tests written FIRST and FAIL before implementation
- Models before services; services before endpoints; core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- All tasks marked [P] run in parallel (different files)
- Within US1: control-plane tasks (T021–T024) ∥ discovery/frontier/scoring (T025–T027) ∥ workers (T028–T031); interpretation ∥ admission; projections ∥ TDA; feedback + web independent after projection tasks
- US2 frontend pages (T054–T056) ∥ APIs (T050–T053)
- US3 isolation/audit/DLQ/multi-region all [P] across `apps/`

---

## Parallel Example: User Story 1

```bash
# Launch tests for US1 together (invariant suites):
Task: "E2E smoke scaffolding bench/run.py + fixtures"
Task: "Observation immutability test"
Task: "Idempotent replay test"

# Launch models for US1 together:
Task: "Investigation domain model"
Task: "Policy & Budget models"
Task: "Source registry"
```

---

## Implementation Strategy

### Full Platform (Constitution No-MVP — all planes in final contracts)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Implement ALL user stories to their final contract level (US1 + US2 + US3) before any production consumption — no MVP slice, no contract-breaking shortcuts per Constitution (§81/§82)
4. **Validate continuously**: run `bench/run --scenario smoke-val` + per-story independent tests as each phase lands, but ship the complete platform (events, AcquisitionWorker, Graph*, UtilityScorer contracts fixed from the start)
5. Final gate: full quickstart.md chain + all universal invariants (I-1…I-12) green on a clean compose stack

### Incremental Delivery

1. Setup + Foundational → durable substrate ready
2. US1 → validate → US2 → validate → US3 → validate (continuous delivery of the full platform)
3. US2 → validate → search/analysis UX
4. US3 → validate → governance/ops/scaling
5. Polish: ADRs, bench harness, security hardening

### Parallel Team Strategy

1. Team completes Setup + Foundational together
2. Once Foundational done:
   - Dev A: US1 control-plane + acquisition (closed loop)
   - Dev B: US1 interpretation/admission/projection/TDA
   - Dev C: US2 query/UI
   - Dev D: US3 ops/isolation
3. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to user story for traceability; Setup/Foundational/Polish phases carry no label
- Each user story independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Architecture contracts (events, AcquisitionWorker, Graph* abstraction, UtilityScorer) must NEVER break — Constitution No-MVP rule (§81/§82)

