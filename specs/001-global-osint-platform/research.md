# Research: Global OSINT Intelligence Platform

**Phase 0 output** — resolves all unknowns in Technical Context. Decision / Rationale / Alternatives format per `/speckit.plan`.

## R-1: Tech baseline confirmation

- **Decision**: Adopt the recorded Technology Baseline from the Constitution verbatim: FastAPI/Python API, Rust acquisition workers, React/TypeScript frontend, Temporal (workflow), Kafka KRaft + Protobuf + Schema Registry (events), MinIO (raw dev storage), PostgreSQL (operational state), OpenSearch (search), ClickHouse (analytics), replaceable graph backend (Neo4j default dev), Python+GUDHI+giotto-tda (TDA), OpenTelemetry/Prometheus/Grafana (observability), Vault (secrets), Docker/Kubernetes runtime.
- **Rationale**: The master document already fixed the baseline; constitution ratifies it; benchmark harness (FR-034) will validate, not re-litigate, the stack.
- **Alternatives considered**: None — stack is specified externally. Open questions (pricing numbers, graph backend) are the only post-baseline decisions (see R-2, R-3).

## R-2: Graph backend selection strategy

- **Decision**: Keep graph abstraction (GraphProjector/GraphReader/GraphTraversal/GraphSnapshot/GraphExporter) as the only application-facing surface; default dev backend = Neo4j 5 (community, single instance); production path = benchmark-driven selection (Neo4j / Memgraph / custom analytical representation) with no domain-logic rewrites.
- **Rationale**: Constitution C-5 requires vendor-neutral domain logic; Spec FR-018 explicitly forbids vendor imports in application logic. Benchmark harness from FR-034 picks backend under a given workload; swapping must be a configuration + adapter concern.
- **Alternatives considered**: Neo4j-only (rejected: violates No-Single-Graph and plugability), custom graph in Postgres (rejected: OLAP-style workloads distort the operational store), networkx in-memory (rejected: not distributed, projection-throughput target unmet).

## R-3: Scheduling / utility scoring model

- **Decision**: Utility = (ExpectedInformationGain × Relevance × Novelty × FreshnessValue × DiscoveryPotential × SourceQuality) / (NetworkCost + ComputeCost + DuplicateRisk). Heuristic scorer v1 behind a `UtilityScorer` interface; contract allows swapping to a learned model (feature store + ML service) without scheduler changes. Per-source/host adaptive state via EWMA latency/error-rate/payload, success/retry/change rates, discovery yield, cooldown, last-request.
- **Rationale**: Spec FR-027 + §14/§15. Scheduler job is optimizing Useful Information Yield / Resource Cost, not req/sec; scorer replaceability is a hard contract. Adaptive state drives concurrency/delay/priority/retry/recrawl/worker-class decisions.
- **Alternatives considered**: Fixed-priority queue (rejected: no utility optimization), reactive/learned-only v1 (rejected: needs cold-start data; heuristic wins first), requests/sec maximization (rejected: explicitly anti-goal).

## R-4: Frontier implementation

- **Decision**: Frontier as operational state in PostgreSQL (authoritative, hierarchical GLOBAL→TENANT→INVESTIGATION→SOURCE→HOST/DOMAIN→TASK) + Redis for hot lease/cooldown/locking; event writes to Kafka for observation/lineage, not for the frontier queue itself.
- **Rationale**: Spec FR-003 + §11/§13: Kafka is not a frontier database; frontier needs priority/schedule/lease/retry/cooldown/dedup/host-state/quotas/recrawl/cancellation. Postgres gives transactional authority; Redis gives fast lease expiry for hot path.
- **Alternatives considered**: Kafka-backed frontier (rejected: not a database, no cooldown/quota semantics), pure-Redis frontier (rejected: durability of authority), external queue product (rejected: adds a database, violates No-Single-Database principle).

## R-5: Stream processing role (Flink)

- **Decision**: Flink used only for genuine stateful workloads: temporal windows/aggregates, stream joins, change/pattern detection, real-time counters, online signals (e.g., correlation of admission decisions with acquisition strategy, cross-source independence detection). Event transport stays on Kafka; projection counters that need only idempotent aggregates default to consumer-side computation first.
- **Rationale**: Spec FR-021 + §44: Flink is not the transport for every event. Start flink-free consumers for simple projections; introduce Flink jobs where window/state semantics justify it.
- **Alternatives considered**: Flink-everywhere (rejected: transport misuse), no streaming (rejected: real-time counters/pattern detection unmet), Kafka Streams (acceptable alternative, kept as candidate for selector jobs; decision deferred to tasks where state semantics are concrete).

## R-6: Multi-language boundary (Rust vs Python)

- **Decision**: Rust owns acquisition hot path (HTTP worker, dispatcher/scheduler, canonicalization, dedup at request/URL/hash layers) and content hashing. Python owns API, interpretation, admission, projection orchestration, TDA, feedback. Boundary = AcquisitionWorker contract plus Kafka event schemas; both sides share contracts/ events proto.
- **Rationale**: Spec baseline: Rust for high-throughput components; Python for FastAPI + TDA + ML-heavy interpretation; plugability (FR-005) means workers are swappable binaries.
- **Alternatives considered**: Python-only workers (rejected: throughput/cost targets), Rust-everything (rejected: TDA/interpretation velocity), Go (not in baseline).

## R-7: Event schema and idempotency

- **Decision**: EventEnvelope protobuf (event_id, event_type, event_version, investigation_id, correlation_id, causation_id, producer, producer_version, produced_at, observation_id, entity_id, payload) registered in Schema Registry; per-event-type payloads versioned. Consumers idempotent on (event_id / task_id / observation_id / projection offsets); no exactly-once guarantees assumed anywhere; dead-letter and quarantine topics for malformed/failed events.
- **Rationale**: Spec FR-023/FR-024 + §47/§48. Lineage is first-class (correlation/causation). Best-effort delivery + idempotency is the documented reliability model.
- **Alternatives considered**: JSON over Kafka (rejected: evolution/validation), assume exactly-once (rejected: explicitly disallowed), only dedupe-store (rejected: still needs envelope + lineage).

## R-8: TDA pipeline geometry

- **Decision**: TDA runs per investigation context over an adaptive subgraph: edges carry confidence/weight/support/independence/temporal/semantic metrics; single-parameter filtration Gλ = { e | score(e) >= λ } with score from those metrics; Ripser/GUDHI persistence on H0/H1/H2 under a configurable dimension+memory budget; outputs TopologicalFeatures as structural signals into admission/feedback — never trusted entities. Multiparameter TDA decoupled as a separate extension module (same feature contract, different algorithm path).
- **Rationale**: Spec FR-025/FR-026 + §49-§55. Budgeted computation prevents uncontrolled complex construction; separation of single- vs multiparameter keeps the contract stable.
- **Alternatives considered**: TDA on the whole global graph (rejected: unbounded, meaningless), TDA-first pipeline before admission (rejected: violates TDA !- truth oracle), no TDA v1 (rejected: core feature scope).

## R-9: Cost model and SLA numbers

- **Decision**: Execution-class pricing is a first-class scheduler input with per-class cost per unit (HTTP req, API call, document parse, browser session, OCR/page, vision inference, TDA persistence). Initial SMOKE numbers from benchmark harness; budgets per investigation enforced against measured cost; SWA=pricing stored in Vault/config, not hard-coded in domain logic. Search/graph/analytics SLA targets: p50<100ms / p95<500ms search, graph traversal p95<200ms; validated against bench/.
- **Rationale**: Spec FR-027/FR-034 + §19/§71; quantitative targets kept out of spec per SC-010 assumption and pinned in plan instead.
- **Alternatives considered**: fixed cheap/expensive flags (rejected: violates expected_value/estimated_cost), no SLA targets until GA (rejected: bench harness needs targets to measure against).

## R-10: Multi-tenant and isolation

- **Decision**: Tenancy enforced at every layer keyed by tenant_id: data tables (row-level), Kafka topics (per-tenant partitions/ACLs), OpenSearch per-tenant index aliases, graph per-tenant name-spaces, S3 prefixes + policies, budgets, policies, and query authorization (tenant-scoped resolver). Isolation verified by contract tests; single shared deployment in dev.
- **Rationale**: Spec FR-029/FR-030 + §64. No cross-tenant leakage is a success criterion (SC-007).
- **Alternatives considered**: per-tenant entire stacks (rejected: cost/ops burden), soft isolation via tenant_id only (rejected: SC-007 demands hard isolation guarantees).

## R-11: Backpressure & stopping policy

- **Decision**: Global control loop: subscriber consumer-lag and queue-depth metrics (OpenSearch indexing lag, ClickHouse ingestion lag, admission queue, parser queue) feed the scheduler rate limiter; backpressure lowers acquisition rate before Kafka backlog grows. Per-branch marginal-information-gain stopping policy: when yield drops, priority decays → SLEEP → STOP; discovery expansion gates on feedback from accepted knowledge.
- **Rationale**: Spec FR-028/FR-027 + §58/§68/§69. Prevents uncontrolled frontier explosion and retry storms.
- **Alternatives considered**: unbounded queue growth (rejected: explicitly disallowed), static rate limits (rejected: no adaptation).

## R-12: External donor mapping (what to borrow from existing OSINT systems)

- **Decision**: Borrow a single specific idea/subsystem from each of ten donor projects, rewritten for our event-driven architecture, and unify them under our existing data model and contracts. Full matrix in [`docs/architecture/donor-analysis.md`](../../docs/architecture/donor-analysis.md). Tier 1 (source-level): FollowTheMoney → statement provenance + dataset boundary + schema + temporal semantics; OpenOSINT → correlation graph + non-destructive resolution + human review; Kipi → investigation/evidence workflow. Tier 2 (patterns): PANO (UX ideology only, CC BY-NC), SpiderFoot (connector ecosystem), investigator (corroboration/triangulation), reNgine (recon task patterns), kafSIEM (Kafka-native provenance), Vitni (review/timeline), NetForensicAI (unified parser interface).
- **Rationale**: Templates the ready spec/contracts/data-model (R-1..R-11, FR-013/FR-015/FR-024, I-1..I-12, ADR-0011/0013) — the platform already models statement provenance, correlation-before-merge, DEFER-favored admission, and rebuildable projections; donors are reference implementations of those concepts, not foundations to vendor-lock on. Avoids the anti-goal of a ten-codebase Frankenstein and respects license constraints.
- **Alternatives considered**: import any donor stack wholesale (rejected: violates C-4/C-5 no-vendor-crossing + No-MVP and dilutes our unified model), rebuild without study (rejected: loses validated patterns for provenance/resolution/connector isolation), copy UI assets (rejected: PANO CC BY-NC).