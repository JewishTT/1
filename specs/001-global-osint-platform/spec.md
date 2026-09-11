# Feature Specification: Global OSINT Intelligence Platform

**Feature Branch**: `001-global-osint-platform`

**Created**: 2026-09-07

**Status**: Draft

**Input**: User description: "Distributed production-grade global OSINT analysis platform — event-driven, evidence-first, process-centric, adaptive intelligence fabric. Not a crawler + graph; Observation is the primary data unit."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run an Investigation End-to-End (Priority: P1)

An analyst creates an `Investigation` with an objective, seeds, scope, source policy, temporal scope, budgets, and freshness requirements. The platform continuously runs the closed loop (Discovery → Acquisition → Observation → Interpretation → Admission → Assertion → Entity → Projections → Search/Graph/Analytics/TDA → Findings → Feedback → re-Acquisition) and surfaces actionable findings with full lineage to raw evidence.

**Why this priority**: This is the primary value proposition — a process-centric platform where the user manages investigations, not graphs. Everything else is in service of this journey.

**Independent Test**: Can be fully tested by creating an investigation over a controlled set of public seeds, letting acquisition run against a test vault (local mirrors/fixtures), observing the full evidence chain, and confirming every finding traces to an immutable raw observation. Delivers a working investigate-with-provenance loop independent of UI polish, multi-tenancy, or global scaling.

**Acceptance Scenarios**:

1. **Given** an empty platform, **When** an analyst creates an investigation with seeds, scope, policy, and budget, **Then** the investigation is in DRAFT→PLANNING→RUNNING and a frontier with prioritized acquisition items is generated.
2. **Given** a running investigation, **When** acquisition completes for a target, **Then** a raw observation is stored immutably (sha256, provenance, timestamps), a Kafka event is emitted, and the object is retrievable by content address.
3. **Given** observed raw material, **When** the interpretation pipeline runs, **Then** mentions → candidates → assertions are produced, and each assertion links to evidence refs and versions of still-immutable observations.
4. **Given** accepted assertions, **When** projections run, **Then** graph/search/analytics projections materialize and are rebuildable from durable evidence/events without data loss on projection failure.
5. **Given** a materialized knowledge projection, **When** TDA and analytics produce features, **Then** findings are created as structural signals (never direct trusted entities) and feedback is sent to the frontier, influencing acquisition priority.
6. **Given** any finding, **When** an analyst drills into it, **Then** the UI walks the full lineage: Finding → Feature → Graph/Assertion → Evidence → Observation → Raw Object → Source.

---

### User Story 2 - Evidence-Backed Expert Search & Analysis (Priority: P2)

An analyst searches across the knowledge base (lexical, semantic, hybrid) and navigates entity/relation graphs, with every result carrying evidence links and provenance. The system fuses results from search, graph, analytics, and TDA metadata behind a single query surface.

**Why this priority**: Search and graph are the everyday investigative surfaces; they depend on the pipeline from P1 but deliver stand-alone value as query planner + evidence links.

**Independent Test**: Can be fully tested by indexing a corpus of prepared observations, running entity resolution and projections, then issuing hybrid queries and verifying result fusion with evidence traversal. Delivers searchable, navigable knowledge with provenance without requiring live acquisition or TDA.

**Acceptance Scenarios**:

1. **Given** indexed observations and resolved entities, **When** an analyst issues a hybrid query with temporal/source/investigation filters, **Then** the query planner fuses results across OpenSearch/graph/ClickHouse/TDA without exposing backend choice to the user.
2. **Given** an entity view, **When** the analyst opens it, **Then** current state, historical versions, aliases, relationships, supporting assertions, evidence, timeline, and structural signals are shown.
3. **Given** an analytical or graph result, **When** the analyst requests proof, **Then** the full evidence chain to immutable raw objects is available and reproducible.

---

### User Story 3 - Operate, Govern, and Scale the Platform (Priority: P3)

Operators monitor the intelligence fabric (throughput, useful observations, discovery yield, duplicate ratios, browser escalation, Kafka lag, projection lag, storage growth, cost), enforce policies and budgets per tenant/investigation, and scale acquisition across regions and worker classes without cross-tenant leakage.

**Why this priority**: Operational control, tenancy isolation, and global scaling are required for production deployment but not for proving the core intelligence loop.

**Independent Test**: Can be fully tested against a single-region deployment with multiple tenants: enforce per-investigation network/compute/storage budgets, isolate tenant data/events/indexes, simulate a failed projection and confirm evidence survives, and exercise dead-letter/quarantine paths. Delivers governance and failure-isolation guarantees with one logical instance.

**Acceptance Scenarios**:

1. **Given** a multi-tenant deployment, **When** two investigations from different tenants run, **Then** no cross-tenant leakage occurs in data, events, search, graph, storage, budgets, policies, or query authorization.
2. **Given** an overloaded downstream, **When** queues grow, **Then** the scheduler applies backpressure by reducing acquisition rate rather than growing Kafka backlog; retry budgets prevent retry storms.
3. **Given** a failed or stale projection, **When** it is rebuilt, **Then** the projection is regenerated from durable evidence/events without altering or losing raw observations.
4. **Given** malformed data or repeated parser failures, **When** the system detects them, **Then** items go to dead-letter/quarantine and are preserved (never auto-deleted), supporting replay/re-evaluation.

---

### Edge Cases

- What happens when a downstream queue depth rises sharply? — Backpressure throttles acquisition rate inside the global control loop.
- How does the system handle observation content that is unchanged since last fetch? — Conditional acquisition (etag/last-modified), observation.changed/unchanged events; no full downstream processing for unchanged resources.
- What happens when the same acquisition intent arises from multiple investigations? — Request coalescing: one canonical acquisition → one observation → fan-out.
- How does the system handle near-duplicate or semantic-duplicate content? — Layered dedup (request → canonical URL → content hash → near → semantic) with ratio KPIs; semantic dedup is a downstream Layer-1 concern.
- How does the system handle unsupported formats, repeated parser failures, or policy-uncertain resources? — Dead-letter/quarantine with preserved evidence and replay support.
- How is the balance maintained if the discovery frontier grows uncontrolled? — Marginal-information-gain stopping policy: priority decays, then SLEEP/STOP per branch.
- What happens on worker pool failure (HTTP/browser/document/OCR/vision/TDA)? — Failure isolation: one pool failing does not stop the others.
- What happens on multi-region partial failure? — Local frontier partitions, caches and scheduler state in each region; global Kafka/control plane stays authoritative.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST support creating Investigations with objective, seeds, scope (entity types, source classes, time range), policy, budgets (network/compute/storage), freshness, and lifecycle state machine (DRAFT→PLANNING→RUNNING→PAUSED→COMPLETED→ARCHIVED).
- **FR-002**: System MUST store every observation immutably with provenance, timestamps, sha256, mime, size, collector/collector-version, policy-version, timing, and a content-addressable raw URI; raw objects MUST remain accessible regardless of downstream projections.
- **FR-003**: System MUST maintain an acquisition frontier supporting priority, schedule, lease, retry, cooldown, dedup, host state, source quotas, investigation quotas, recrawl, and cancellation, organized hierarchically (GLOBAL→TENANT→INVESTIGATION→SOURCE→HOST/DOMAIN→TASK); Kafka MUST NOT be used as the frontier database.
- **FR-004**: System MUST support discovery from multiple methods (sitemap/index, RSS, Atom, public APIs, bulk datasets, catalogs, document references, HTML links, permitted public indexes, archive metadata), each discovery event carrying method, source_id, parent_observation_id, timestamp, and confidence.
- **FR-005**: System MUST acquire resources HTTP-first, escalating to a separate browser fabric only on response insufficiency; HTTP and browser resources MUST NOT share one worker pool; all acquisition implementations MUST conform to an AcquisitionWorker contract (capabilities() / estimate(task) / acquire(task)) with engine plugability.
- **FR-006**: System MUST apply policy (source permission, robots policy, tenant/investigation policy, rate limits, budgets, retention, allowed source classes) before dispatch. Tool constraint: the engine ships no mechanisms for bypassing authentication, CAPTCHA, paywall, or other access controls — it operates strictly through the public interfaces a source exposes.
- **FR-007**: System MUST deduplicate at request, canonical URL, exact content-hash, near-duplicate, and semantic-duplicate levels, and MUST use conditional acquisition (etag/last-modified/content-hash) with resource state to avoid reprocessing unchanged resources.
- **FR-008**: System MUST fuse coalesced acquisition intents across investigations so identical requests map to one canonical acquisition and one observation, then fan out.
- **FR-009**: System MUST route content by MIME/size validation/hashing after acquisition, dispatching heavy parsers (HTML/JSON/XML/PDF/image/archive/other binary) to isolated worker pools.
- **FR-010**: System MUST run interpretation pipelines (parser → segments → mentions → candidates → candidate relations → assertions) with extraction-version provenance on every artifact.
- **FR-011**: System MUST keep Mention (literal surface form with offsets, type hypothesis, confidence, extractor version) distinct from Candidate (typed hypothesis over mentions) distinct from Entity (resolved, versioned identity). Mentions MUST also carry a normalized_form, transliteration_variants, script, language, and normalization_version — the original surface form is never replaced by its normalization.
- **FR-012**: System MUST perform entity resolution as a pipeline: (1) multi-strategy blocking/co-occurrence yielding a bounded union of candidate pairs (never all-pairs O(N²) comparison), (2) pairwise scoring over multiple signals (identifier, name, attribute, temporal, semantic, relational, source, evidence, graph-neighborhood similarity), (3) collective/graph-aware resolution that propagates relational context (e.g., X~X' when Y~Y' and X→director→Y / X'→director→Y') iterating until convergence. Output MUST preserve raw pair score AND collective score AND reasons; per-type thresholds are NOT globally uniform.
- **FR-013**: System MUST run an admission engine supporting ACCEPT_NEW / ACCEPT_EXISTING / DEFER / REJECT / QUARANTINE, persisting score vectors, reasons, evidence refs, model/policy versions, and timestamps. Admission MUST be epistemically conservative (asymmetric error cost: a rejected rare evidence is far more costly than an accepted noisy candidate): categorical rules take priority over score thresholds — invalid identifier → REJECT; explicit strong contradiction → QUARANTINE/REJECT per policy; insufficient evidence → DEFER; strongly corroborated match → ACCEPT. `uncertain` MUST NOT automatically map to REJECT.
- **FR-014**: System MUST preserve all rejected/deferred/quarantined candidates with decision, reasons, scores, validator version, timestamp, and evidence; never auto-delete; support replay/re-evaluation.
- **FR-015**: System MUST model time triples separately (valid_time / observed_time / system_time) and MUST NOT treat publication count as independent-source count in evidence fusion. System MUST include a Source Independence Engine that builds a citation/derivation graph (cites / copies / references / rewrites) and computes independent evidence chains; assertion support is recorded as publication_count AND independent_support.
- **FR-016**: System MUST support entity versioning with a current projection and retained resolution-decision history. Assertions MUST carry a life-cycle state machine (ASSERTED → SUPERSEDED | RETRACTED | CONTRADICTED | EXPIRED) driven by relation-specific temporal policy (single-valued / multi-valued / interval-valued / append-only / supersedable / contradictory); supersession or retraction MUST NOT delete the original assertion — it stays for forensic provenance, and any replacement assertion is linked to it.
- **FR-017**: System MUST materialize multiple rebuildable knowledge projections (SemanticGraph, EvidenceGraph, CandidateGraph, TemporalGraph, InfrastructureGraph, Search Index, Analytical Store, TDA artifacts) from durable evidence/events; projection failure MUST NOT destroy evidence.
- **FR-018**: System MUST expose graph serving through a replaceable abstraction layer (GraphProjector / GraphReader / GraphTraversal / GraphSnapshot / GraphExporter) with no vendor-specific classes in application logic.
- **FR-019**: System MUST provide a search plane over OpenSearch indices (observations, documents, mentions, candidates, entities, assertions, findings) supporting lexical, semantic, hybrid, metadata/temporal/source/investigation filters, and MUST fuse results via a query planner spanning OpenSearch/graph/ClickHouse/TDA metadata behind a single user-facing surface.
- **FR-020**: System MUST use ClickHouse for bulk OLAP (event aggregation, source/pipeline analytics, temporal statistics, cost accounting, investigation metrics) — NOT the graph database.
- **FR-021**: System MUST use Flink for stateful stream processing only (windows, correlation, joins, change/pattern detection, real-time counters, online signals) — NOT as transportation for every event.
- **FR-022**: System MUST use Temporal for long-running investigations, scheduled recrawls, retries, multi-step acquisition, pause/resume, human approval, and workflow recovery.
- **FR-023**: System MUST publish typed events (Protobuf + Schema Registry) per the defined topic catalog (investigation.*, acquisition.*, observation.*, interpretation.*, resolution.*, admission.*, projection.*, tda.*, finding.created, feedback.generated, acquisition.deadletter, acquisition.quarantine) with an EventEnvelope carrying event_id/type/version, correlation_id, causation_id, producer, produced_at, payload.
- **FR-024**: System MUST make every consumer idempotent via event_id / task_id / observation_id / projection offsets; MUST NOT rely on assumed global exactly-once delivery.
- **FR-025**: System MUST run TDA as a bounded pipeline (investigation context → adaptive subgraph → TDA-ready graph with confidence/weight/support/independence/temporal/semantic edge metrics → weighted filtration → simplicial complex → persistent homology → TopologicalFeature); dimension budget configurable; output MUST be structural signals, never trusted entities; architecture MUST separate single-parameter persistence from multiparameter TDA extensibility.
- **FR-026**: System MUST record TopologicalFeatures with id, projection_id, snapshot_id, dimension, birth/death, persistence, supporting nodes/edges, algorithm version, and provenance, and MUST feed them as structural findings into the admission/feedback loop.
- **FR-027**: System MUST run a feedback engine where downstream results (accepted entities/relations, new domains, new documents, topological signals, high information gain) influence acquisition priority, recrawl, discovery expansion, and investigation budgets; utility-based scheduling MUST optimize Useful Information Yield / Resource Cost and support learned-scorer replacement without changing the scheduler contract.
- **FR-028**: System MUST enforce per-task/source/investigation/global retry budgets, backpressure tied to downstream queue depth, and dead-letter/quarantine for malformed data, repeated parser failures, policy uncertainty, resource abuse, and unsupported formats.
- **FR-029**: System MUST enforce security controls for all external input: SSRF and DNS-rebinding protection, sandboxed parsers, browser isolation, network egress policy, CPU/memory/timeout/response-size/archive-depth/file-count limits, secret isolation, audit logs, RBAC, and tenant isolation across data, events, search, graph, storage, budgets, policies, and query authorization.
- **FR-030**: System MUST support multi-region acquisition topology (local workers, frontier partitions, cache, scheduler state per region; global Kafka/control plane/source registry/investigation metadata) and logical/physical separation of CONTROL/ACQUISITION/PROCESSING/ANALYTICS/GPU/STORAGE planes.
- **FR-031**: System MUST expose UI screens for the investigation pipeline, entity view (current/history/aliases/relations/assertions/evidence/timeline/structural signals), finding view (why detected, evidence, graph region, raw source), and an operational dashboard (throughput, useful observations, discovery yield, duplicate ratio, browser utilization, lags, queues, storage growth, cost). Graph canvas is one panel — not the main interface.
- **FR-032**: System MUST provide full lineage/traceability on every finding (Finding → Feature → Graph/Assertion → Evidence → Observation → Raw → Source) and expose it in the UI.
- **FR-033**: System MUST ship an ADR set covering Kafka vs alternatives, object storage, PostgreSQL role, OpenSearch, ClickHouse, Flink, Temporal, graph abstraction/backend selection, TDA architecture, event schema, provenance, entity resolution, admission engine, frontier architecture, scheduling algorithm, recrawl strategy, multi-region topology.
- **FR-034**: System MUST provide a reproducible benchmark harness (acquisition, knowledge, search p50/p95/p99, graph projection/traversal/snapshot, TDA nodes/edges/dimensions/memory/runtime/stability, cost per million observations/assertions/discoveries) — third-party crawler claims are not architectural guarantees.

### Key Entities *(include if feature involves data)*

- **Investigation**: First-class process container with objective, seeds, scope, policy, budget, freshness, status lifecycle (DRAFT→PLANNING→RUNNING→PAUSED→COMPLETED→ARCHIVED). Owner of all downstream derived artifacts.
- **Observation**: Immutable primary data unit — raw fragment of external reality with provenance, timestamps, sha256, mime, size, collector/version, policy version, timing; raw object stored content-addressable in S3. Never edited after write.
- **Source / SourceProfile**: Registry entry with type, capabilities, policy, quality profile, historical yield, change rate, discovery yield, average cost, freshness characteristics.
- **AcquisitionTask / FrontierItem**: Dispatchable work with target (kind/value), canonical key, source/investigation refs, discovery refs, priority, expected novelty/cost, strategy, attempt, constraints, policy version, and frontier state (READY/SCHEDULED/LEASE/RETRY/COOLDOWN/CANCELLED).
- **Mention**: Literal string/fragment found in an observation (surface form + offsets, normalized_form, transliteration_variants, script, language, normalization_version, type hypothesis, confidence, extractor version). Not an Entity.
- **Candidate**: Typed hypothesis aggregated over mentions with attributes and confidence; carries separate resolution state and epistemic status (PROVISIONAL / DEFERRED / QUARANTINED / ACCEPTED / REJECTED); lives in the noisy Candidate Graph; not trusted knowledge.
- **Assertion**: Subject-predicate-object proposition with evidence refs, confidence, valid/observed time, extractor version, provenance, and a life-cycle state (ASSERTED/SUPERSEDED/RETRACTED/CONTRADICTED/EXPIRED). Not absolute truth; originals never deleted.
- **Entity / EntityVersion**: Resolved identity with versions, aliases, attributes, first/last seen, relationships, provenance summary; current projection plus full resolution history.
- **Relation**: Typed edge between entities with confidence, weight, validity window, support count, independent support, provenance.
- **EvidenceLink**: Provenance link from an assertion/candidate to supporting evidence (observation refs + raw objects), including publication_count, independent_evidence_chains, and citation/derivation-graph references from the Source Independence Engine.
- **CalibrationProfile**: Immutable, versioned bootstrap/calibrated decision profile per entity type (+language/script) with auto_accept/defer/reject thresholds, hard-reject rules, resolver/calibration/feature-schema/policy versions, calibration_status (UNCALIBRATED/CALIBRATED), source, provenance, effective_from/to. Never overwritten — new versions are appended for replay.
- **TopologicalFeature**: TDA output (dimension, birth/death, persistence, supporting nodes/edges, algorithm version, provenance) — a structural signal / finding input.
- **Finding**: Interpreted analytical result with cause, structural/semantic evidence, supporting graph region, assertions, observations, raw source lineage.
- **Projection / GraphSnapshot**: Rebuildable materialized views (semantic/evidence/candidate/temporal/infrastructure graphs, search index, analytics, TDA) with snapshot metadata.
- **Policy / Budget**: Govern scope, source rules, rate limits, retention, and network/compute/storage cost ceilings at tenant and investigation levels.
- **ModelVersion / Decision**: Versioned model outputs and admission decisions (ACCEPT_NEW/ACCEPT_EXISTING/DEFER/REJECT/QUARANTINE) with score vectors, reasons, evidence refs, timestamps — preserved for replay.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new investigation built from seeds reaches a state where every produced finding has a complete, UI-navigable lineage to an immutable raw observation (100% of findings traceable — see §62/§84 acceptance chain).
- **SC-002**: Any projection (graph/search/analytics/TDA) can be fully rebuilt from durable evidence/events without data loss; projection failure does not affect evidence availability (Invariant 12).
- **SC-003**: The platform demonstrates the full acceptance chain end-to-end (investigation → seeds → discovery → frontier → acquisition → observation → raw storage → Kafka event → parse → mentions → candidates → assertions → resolution → admission → projections → snapshot → TDA → TopologicalFeature → Finding → feedback → new acquisition tasks) with traceability at every step.
- **SC-004**: Scheduler maximizes Useful Knowledge / Total Resource Cost (network + compute + GPU + storage + latency). Useful-observation yield, accepted-assertions/hour, new-entities/hour, new-relationships/hour, structural-findings/hour, discovery-yield, duplicate/near-duplicate ratios, retry-amplification, browser-escalation-rate, bytes/and compute per useful observation, accepted-knowledge-per-dollar, freshness-lag, queue-age, and projection-lag are all measured and reported.
- **SC-005**: All 12 architectural invariants (Observation immutable … projections rebuildable) are enforced by tests/factories; no invariant is silently violated by a feature addition.
- **SC-006**: The fastest request is correctly avoided: unchanged resources and coalesced intents demonstrably reduce duplicate acquisitions (duplicate_ratio and near_duplicate_ratio tracked as KPIs).
- **SC-007**: Multi-tenant isolation holds — no cross-tenant leakage in data, events, search, graph, storage, budgets, policies, or query authorization during parallel investigations from different tenants.
- **SC-008**: Under downstream overload, the scheduler reduces acquisition rate (backpressure) without unbounded Kafka backlog growth; retry budgets cap retry storms.
- **SC-009**: Rejected/deferred/quarantined candidates remain replayable with full decision context (scores, reasons, versions, evidence, timestamps) — re-evaluation possible after model/policy changes.
- **SC-010**: Search UX hides backend choice: a hybrid query is fused across OpenSearch/graph/ClickHouse/TDA with evidence links on every result, and p50/p95/p99 are benchmarked by the built-in harness.
- **SC-011**: Knowledge-quality gate in CI: pair precision/recall/F1, cluster precision/recall/F1, false-merge and false-split rates, Brier score / calibration (ECE), per-entity-type / per-language / per-script metrics measured on a gold corpus; aggregate quality does NOT regress below a defined floor across resolver/admission model versions.
- **SC-012**: Rarity survival under asymmetric error cost: rare/weakly-corroborated but valid evidence is preserved (DEFER/QUARANTINE, not destructive REJECT); a rejected rare evidence can be recovered and re-evaluated with full context. False negatives are treated as more costly than false positives in the operating-point policy.

## Assumptions

- The platform is deployed self-hosted by its operator; MinIO is the reference S3-compatible object storage for development and self-hosted deployments; production object storage is S3-compatible by contract.
- Single-vendor neutrality: graph backend is chosen by benchmark via the abstraction layer — assumptions on Neo4j are only used in ADR comparison, not hard-wired in domain logic.
- The platform works only with public sources that expose data through their own public interfaces; acquisition never penetrates authenticated/access-controlled surfaces (tool constraint, FR-006).
- Data freshness/retention defaults follow industry practice per source class (configurable per policy); no platform-wide hard-coded retention assumption.
- v1 targets a self-hosted single-region control plane with multi-region acquisition topology designed but physically deployed per operator needs; tenant isolation and RBAC exist from the start (FR-029).
- Performance targets assume typical public-web workloads; exact SLA numbers (response p50/p95/p99, throughput) are to be pinned during the planning phase against the benchmark harness, not assumed here.
- Best-effort event delivery semantics: consumers are designed idempotent; exactly-once is not assumed anywhere (FR-024).
- TDA in v1 implements single-parameter persistent homology with H0/H1/H2 under a configurable budget; multiparameter extension is architecturally decoupled but not in the v1 acceptance chain (FR-025).
- The interpretation pipeline's entity-resolution thresholds are tuned per entity type and are not globally uniform (FR-012).
- Resource pricing (expected_value / estimated_cost per execution class: HTTP, API, document parsing, browser, OCR, vision, TDA) is a first-class input to the scheduler, with numeric pricing defined in the planning phase.