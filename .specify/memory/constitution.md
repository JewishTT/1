# COGNITIVE Constitution

## Core Principles

### I. Observation-Immutable Evidence Substrate
Every observation is immutable once recorded. Raw objects are stored content-addressable (s3://knowledge/raw/{prefix}/{sha256}) and remain available independently of any downstream projection. Nothing downstream may edit an observation.

### II. Evidence-First
Any knowledge must trace fully: Finding → Analytical/Topological Feature → Graph/Assertion → Evidence → Observation → Raw Object → Source. Every analytical result must be reproducible from source observations/evidence. Originals stay accessible regardless of projections.

### III. Projection-First Knowledge Architecture
Knowledge lives in the durable Event/Evidence Substrate (S3 + Kafka + PostgreSQL). Semantic Graph, Evidence Graph, Candidate Graph, Temporal Graph, Search Index, Analytical Store, and TDA projections are all rebuildable artifacts. Projection failure must never destroy evidence.

### IV. No Single Store / Graph / Score
Different workloads use different storage engines (S3 raw, Kafka events, PostgreSQL state, OpenSearch search, ClickHouse analytics, pluggable graph backend, TDA artifacts). There is no universal graph serving as source of truth, and no single score equates to truth: validity, relevance, novelty, resolution confidence, source quality, evidence support, and structural significance are stored separately.

### V. Plugability by Contract
All acquisition implementations conform to the AcquisitionWorker interface (capabilities() / estimate(task) / acquire(task)). Application code interacts with graphs only through GraphProjection / GraphReader / GraphSnapshot / GraphTraversal. No vendor-specific classes in domain logic. Engines (Rust HTTP, Crawlee, Playwright, connectors) and graph backends (Neo4j/Memgraph/other) are swappable behind contracts.

### VI. Process-Centric
The user creates an Investigation — not a graph. Graphs, search indices, analytical structures, and TDA complexes materialize automatically within the investigation lifecycle and its policy/budget/freshness constraints.

### VII. Security-First
All external input is untrusted. Mandatory: SSRF protection, DNS-rebinding protection, sandboxed parsers, browser isolation, network egress policy, CPU/memory/timeout/size limits, archive-depth and file-count limits, tenant isolation at every level, RBAC, audit logs, secret isolation. Tool constraint (engineering, not legal scope): the engine ships no mechanisms for bypassing authentication, CAPTCHA, paywall, or other access controls — it operates strictly through sources' public interfaces.

## Domain Invariants

1. Observation is immutable.
2. Mention != Candidate != Entity.
3. Assertion != truth.
4. Graph != source of truth.
5. Kafka != object store.
6. TDA != truth oracle (topological features are structural signals, not proof of identity).
7. Admission != Priority.
8. Entity novelty != evidence novelty != structural novelty.
9. Search != Graph traversal != OLAP.
10. Acquisition throughput != intelligence throughput.
11. The fastest request is the request correctly avoided.
12. All downstream projections must be rebuildable from durable evidence/events.

## Technology Baseline

- Frontend: React + TypeScript
- API: FastAPI / Python
- High-throughput components: Rust
- Workflow: Temporal
- Event backbone: Apache Kafka (KRaft), Protobuf, Schema Registry
- Raw storage: S3-compatible object storage (MinIO for dev/self-hosted)
- Operational state: PostgreSQL
- Search: OpenSearch projection
- Analytical storage: ClickHouse projection
- Stateful stream processing: Apache Flink (only for genuine stateful work, not transport)
- Graph serving: replaceable abstraction layer
- TDA: Python (GUDHI, giotto-tda, NumPy, SciPy)
- Runtime: Docker, Kubernetes
- Observability: OpenTelemetry, Prometheus, Grafana
- Secrets: Vault

## Additional Constraints

- **No MVP/mini-architecture**: implement contracts of all major planes (Investigation, Acquisition, Evidence, Interpretation, Admission, Projection, Analysis, Feedback) up front; components may be introduced incrementally but must never break final domain/event contracts.
- **Script type**: PowerShell (ps) for Speckit automation on Windows.
- **Backpressure**: downstream queue growth must reduce acquisition rate, not expand Kafka backlog.
- **Retry budgets**: task / source / investigation / global retry budgets to avoid retry storms.
- **Dead letter / quarantine** for malformed data, repeated parser failures, policy uncertainty, resource abuse, unsupported formats; rejected candidates are never auto-deleted (replay/re-evaluation supported).
- **Idempotency**: every consumer is idempotent using event_id / task_id / observation_id / projection offsets.
- **HTTP-first acquisition**, browser escalation only on insufficiency; separate browser fabric pool; resource classes priced by expected_value / estimated_cost.

## Governance

Constitution supersedes all other practices. Changes to architectural decisions require an ADR (e.g., Kafka vs alternatives, object storage, PostgreSQL role, OpenSearch, ClickHouse, Flink, Temporal, graph abstraction/backend, TDA architecture, event schema, provenance, entity resolution, admission engine, frontier architecture, scheduling, recrawl, multi-region topology).

Compliance is verified on every PR/review. Rejected analysis outputs (admission rejections, TDA signals) are preserved with decision, reasons, score vectors, versions, and timestamps for replay. Source independence (copied/derived sources) is considered in evidence fusion; publication count is not treated as independent-source count.

**Version**: 1.0.0 | **Ratified**: 2026-09-07 | **Last Amended**: 2026-09-07