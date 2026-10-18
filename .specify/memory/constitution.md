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
- Event backbone: Kafka-compatible protocol, **Redpanda runtime (pinned by image digest)**, Protobuf, Schema Registry. "Kafka" in this platform names the wire protocol, never a specific product. See [ADR-0026](docs/adr/0026-redpanda-transport-runtime.md).
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

## Enforced Engineering Obligations (P1–P15)

Adopted 2026-10-17 by feature `030-global-platform-upgrade` (`plan.md §Constitution Check`). These do
not renumber or replace Principles I–VII; they bind them to checks that can fail. Each obligation is
written so that a named artefact, a named test, or a recorded command can falsify it. An obligation
with no imaginable failing check is not an obligation and must be rewritten until one exists.

Scope note: P1–P15 are stated over *this repository*. Where an obligation names a path or a task,
that citation is verified against the executing tree on the adoption date and must be re-verified
before it is used to reject work.

### P1 — Immutable evidence substrate

No code path may write to, mutate, overwrite or delete a raw object after it is stored. A test that
snapshots every raw-blob digest before and after a full pipeline run (parser upgrade, re-ingest,
rollback, donor disable) must observe **zero** digest changes. An attempted mutation raises
`IMMUTABLE_VIOLATION` rather than succeeding quietly. *Falsified by:* any digest delta.

### P2 — Evidence-first derivation

Every accepted claim resolves to a content address and an exact span in the stored bytes. A span
carries a `selector_semantics_version`; two producers with different values are refused, not
reconciled. A finding whose lineage chain has a broken hop renders as `partial`/`unsupported` and
never as grounded. *Falsified by:* a stored `Segment.offset` that means byte offset in one producer
and segment index in another (`apps/interpretation/extractors/lane.py` is the known site), or by a
mention whose span is computed and then discarded.

### P3 — Identity is a resolution decision

No similarity probability, structural centrality, graph adjacency, topological feature, or model
output may by itself commit a merge. Every merge and split is an append-only decision row carrying
its author, time, rule version and rationale; a superseded decision stays retrievable and claims
written under an earlier identity interpretation stay traceable to it. A matcher whose own profile
declares itself uncalibrated cannot commit a merge at any threshold. *Falsified by:* a test in which
a high-score pair with no admission decision produces a nonzero merge count.

### P4 — Open-world semantics

An unknown relation predicate is a first-class value with its raw label and span intact. It survives
storage, projection and API unchanged, and is never silently dropped, defaulted, or coerced into a
known predicate. *Falsified by:* any code path where an unrecognised predicate disappears between
the parser and the API response.

### P5 — No scalar truth

A single untyped score may not stand for candidate discovery, expansion, relevance, fusion, action
utility or policy decision. Score components stay stored separately. Any composite score carries the
`policy_version` that produced it **and** retains the component vector it was derived from. A
probability-like quantity that has not been calibrated is labelled `uncalibrated_score`, never a bare
float. *Falsified by:* a stored score with no component breakdown, or with a breakdown that cannot be
recombined into it.

### P6 — Epistemic discipline

The thirteen research states stay distinct through storage, events, API and UI. Support is
four-valued and `TRUE_ONLY`/`FALSE_ONLY` are incomparable; confidence is a separate field from
support. An absence claim requires declared detection power; zero results from a source of unknown
detection power is `SEARCHED_NO_RESULT / INFORMATIONAL_ONLY`, never `QUALIFIED_ABSENCE`. A
contradiction is never resolved by recency, document majority, or a single high score. A bare `[]` is
never an API response — status, coverage, provenance and limitations accompany it. *Falsified by:* any
round-trip that collapses two of the thirteen states into one.

### P7 — Temporal semantics

Eight clocks are separately typed and separately defined: source-published, source-valid-from,
source-valid-until, source-observed, captured/fetched, recorded/known, processed, projected — each
with its own timezone, null semantics and query usage. `CURRENT`, `AS_OF(known-time)` and
`INTERVAL(valid-time a, b)` are three distinct query dimensions that cannot be aliased onto one
another. Unknown source time stays unknown and is never defaulted to now. Late-arriving evidence
rewrites the current reconstruction of past valid time **without** altering what was recorded as
known at an earlier known-time. *Falsified by:* an `AS_OF` query whose result set equals a `CURRENT`
query's, or a null source time arriving as `now()`.

### P8 — Process-centric ownership

The unit of work is an investigation, not a graph. The five responsibilities — obligation generation,
satisfaction evaluation, action proposal, decision recording, revision management — stay separate
types with separate call sites (`apps/control-plane/context_engine/engine.py`). New code extends an
existing responsibility; it does not merge them into one object and does not create a second context
engine at a new path. *Falsified by:* a class that both decides an obligation is satisfied and writes
the decision record.

### P9 — Projection rebuildability

Every projection family declares its eleven properties (FR-070) and a rebuild from durable evidence
reproduces the manifest's recorded `output_digest`. Exactly one production owner exists per
graph/TDA/temporal operation; a duplicate execution path is removed or explicitly marked inert.
`rebuildable = true` is refused when no tested rebuild route exists. A failed, crashed or killed
projection deletes no evidence and mutates no canonical claim. Each projection family has a kill
switch and a staleness indicator, and a stale projection may satisfy a freshness-requiring obligation
only through an explicit profile. *Falsified by:* a rebuild that yields a different digest on
identical fixtures, or a registered projection missing any of the eleven declarations.

### P10 — Determinism at declared boundaries

Every operator declares one of two replay modes. `deterministic`: a pure function of fingerprinted
inputs, where replay recomputes and the output digest must match. `result_replay`: the exact returned
result is preserved with its inputs and the mode is stated. The deterministic core performs no network
access, no remote model call, no durable write and no identity mutation. Identity-critical hashing
uses canonical serialization — stable key order, normalized timezones, no uncontrolled `repr()` or
memory-address stringification. The invariant reducer's revision counter advances per `reduce()` call
and not per event; `InvariantReducer.restore(stream, history=)` is the mitigation that rebuilds at
the recorded position, and the property pinned by
`test_a_cold_fold_is_not_equivalent_to_a_restore` must not be "fixed" away. *Falsified by:* a cold
fold of an accumulated stream reproducing the digest of an incremental fold of the same stream.

### P11 — Hard constraints outrank utility

Policy, budget, capability availability, required approval and legal restriction are filters, not
terms in a sum. They run **before** ranking, and a candidate excluded by one records which one and
why. No expected-gain value can outweigh an excluded candidate. A proposed action marked
`approval_required` does not execute until the decision is recorded, regardless of what the client
claims. *Falsified by:* a ranking pass in which an excluded candidate appears in the output, or a
client-supplied approval that executes an action with no `DecisionRecord`.

### P12 — Cost-aware process

Cost is a vector — network IO, CPU/GPU, memory, parser/model execution, model tokens, latency,
storage (raw and projections), retries, operator time, expected human review, licensing,
maintenance. The component vector is retained; any composite carries its policy version. Acquisition
throughput is not intelligence throughput, and the fastest request is the request correctly avoided.
*Falsified by:* a stored cost field holding one scalar with no components.

### P13 — Donor reuse with boundaries

Donor reuse is the default (Additional Constraints), bounded by FR-110–FR-115. A third-party
capability is **not** integrated until: the exact upstream revision or package version is pinned;
code licence, dependency licences, model/dataset terms and attribution are recorded **separately**;
a contract adapter exists; a real production call site uses it; provenance is preserved through the
adapter; error, timeout, partial and unsupported outcomes are distinguished; tests pass; and the
platform's own benchmark shows gain. A donor adapter writes no canonical evidence, identity,
investigation-state or projection store. Every integration has a disable switch, a rollback route and
an operational owner, and disabling deletes no evidence, candidate or derived artifact. An upstream
whose identity, source or licence cannot be established is recorded `unverified` and is not
integrated. *Falsified by:* a declared dependency with no registry licence/version entry, or a
kill-switch test that loses a prior derived artifact.

### P14 — Security and acceptable acquisition

All external input is untrusted (Principle VII). Private, loopback, link-local and metadata address
ranges are blocked; DNS is validated before **and** after redirect; DNS-rebinding is handled; archive
depth, decompressed size and file count are bounded. Tenant scope is enforced on every durable read,
write, cache key and replay key at the repository layer, and cross-tenant access returns the same
response shape as a genuinely absent object. No registered acquisition adapter holds a privilege that
bypasses authentication, CAPTCHA, paywall or any other access control. Secrets and raw sensitive
payloads appear in no log, metric, trace or decision record. *Falsified by:* a cross-tenant cache-key
collision, or a raw payload reachable from an observability backend.

### P15 — Truthful reporting

Every test result is reported as exactly one of **pass / fail / blocked / not-run**, with the command
and its exit status. Blocked is not pass; a service that did not start is reported blocked with the
reason, never as a product failure and never as a pass. No metric reaches an interface unless a
recorded command produced it; an unavailable measurement serialises as `null` with the missing
instrumentation named, and is never imputed, defaulted or estimated. A capacity, latency or quality
claim with no measurement behind it is prohibited. *Falsified by:* a number in a report that no
recorded command produced, or a green gate whose run contained a blocked step.

---

## Additional Constraints

- **No MVP/mini-architecture**: implement contracts of all major planes (Investigation, Acquisition, Evidence, Interpretation, Admission, Projection, Analysis, Feedback) up front; components may be introduced incrementally but must never break final domain/event contracts.
- **Script type**: PowerShell (ps) for Speckit automation on Windows.
- **Backpressure**: downstream queue growth must reduce acquisition rate, not expand Kafka backlog.
- **Retry budgets**: task / source / investigation / global retry budgets to avoid retry storms.
- **Dead letter / quarantine** for malformed data, repeated parser failures, policy uncertainty, resource abuse, unsupported formats; rejected candidates are never auto-deleted (replay/re-evaluation supported).
- **Idempotency**: every consumer is idempotent using event_id / task_id / observation_id / projection offsets.
- **HTTP-first acquisition**, browser escalation only on insufficiency; separate browser fabric pool; resource classes priced by expected_value / estimated_cost.
- **Donor reuse is the default, not an exception**: taking tuned, field-tested functionality from donor projects is the normal way to build. The concept defines *what*; the gap between concept and working code is the hardening against real edge cases, upstream quirks and garbage input — and donors have already paid that cost. Rewriting it re-runs a path someone else already walked. Architectural purity is not a price worth paying for implementation. This is bound by two limits: a donor may not write through a boundary the platform prohibits (§1–VII), and a donor that carries its own defect is *repaired on transfer* — never grounds to decline the transfer.
- **Conceptual contradiction is the sole exception, and it is not the agent's call**: when donor functionality appears to contradict the platform's architecture, the agent stops and asks the owner, presenting the conflicting invariant and the options (take as-is / adapt / write fresh). The agent does not unilaterally decide and silently rewrite. See `AGENTS.md` §1.1.

## Governance

Constitution supersedes all other practices. Changes to architectural decisions require an ADR (e.g., Kafka vs alternatives, object storage, PostgreSQL role, OpenSearch, ClickHouse, Flink, Temporal, graph abstraction/backend, TDA architecture, event schema, provenance, entity resolution, admission engine, frontier architecture, scheduling, recrawl, multi-region topology).

Compliance is verified on every PR/review. Rejected analysis outputs (admission rejections, TDA signals) are preserved with decision, reasons, score vectors, versions, and timestamps for replay. Source independence (copied/derived sources) is considered in evidence fusion; publication count is not treated as independent-source count.

**Version**: 2.0.0 | **Ratified**: 2026-09-07 | **Last Amended**: 2026-10-17
**Amendment log**:
- 1.1.0 (2026-09-29) — donor reuse is the default, not an exception.
- 1.2.0 (2026-10-02) — Technology Baseline: event backbone is the Kafka-compatible *protocol* with Redpanda as the pinned *runtime* (ADR-0026, Feature 024 D1=a).
- 2.0.0 (2026-10-17) — feature `030-global-platform-upgrade`, task T015. Adds *Enforced Engineering
  Obligations (P1–P15)* from `plan.md §Constitution Check`, each phrased as a falsifiable obligation.
  Principles I–VII, the Domain Invariants, the Technology Baseline and the Additional Constraints are
  unchanged; P1–P15 bind them rather than restate them. Major bump because fifteen new binding
  obligations now constrain the acceptance gates.

**Provenance note (2.0.0).** `plan.md`, `research.md §6` and `current-state-audit.md §2` each record
`.specify/memory/constitution.md` as a 50-line unfilled template carrying `[PRINCIPLE_1_NAME]`,
`[SECTION_2_CONTENT]` and `[CONSTITUTION_VERSION] | [RATIFICATION_DATE]`. That is **not true of this
file**, which has been committed and ratified since 2026-09-07 and carried version 1.2.0. The
measurement conflated this file with `.specify/templates/constitution-template.md`, which is the
50-line unfilled template and matches the quoted line count exactly. The file was therefore amended,
not overwritten, and the losing record in the feature documents is a defect to be corrected at T014.