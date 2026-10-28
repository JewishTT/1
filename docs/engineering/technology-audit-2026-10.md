# COGNITIVE technology audit

Review date: 2026-10-29. Evidence basis: checked-in manifests, source code, generated `docs/platform/*` views, and CI runs available on PR #5. This is a source/configuration audit. It is not a live load test, penetration test, production deployment check, or a claim that every container was started.

## Executive verdict

**Architecture direction: coherent; production readiness: not established.** The repository has real components for evidence acquisition, parsing, identity/relation admission, event transport, contextual reasoning, projections and analyst UI. The critical shortfall is not lack of libraries; it is uneven operational integration and inconsistent authority boundaries. Several surfaces are genuine implementations, several are opt-in sidecars, and a number remain fixtures, test-only modules or declarations.

Do not advertise a capability as production-ready solely because its module exists, its event type is catalogued, a route answers, or its unit tests pass.

## Technology matrix

| Subsystem | Observed technology / source evidence | Assessed maturity | Required production gate |
|---|---|---|---|
| API and application composition | Python 3.11+, FastAPI, Pydantic, workspace packages; `apps/control-plane/api/main.py`, `apps/control-plane/composition.py` | Real API/composition root; some routes are still fixture-backed | Clean installed-wheel smoke test, startup dependency probes, auth/tenant contracts, route-level end-to-end validation |
| Workspace / packaging | `uv` workspace in root `pyproject.toml`; Hatchling package list in `apps/control-plane/pyproject.toml` | Workspace exists; the control-plane wheel explicitly omits `context_engine` and `semantic_path` package roots | Build wheel, install into a clean environment, import all declared entrypoints, start API and run context-engine contracts against the installed wheel |
| Operational database | PostgreSQL, SQLAlchemy async sessions, Alembic | Real database models and migration code; migration head `014_temporal_materialization` declares `down_revision = None`; operational temporal dispatch calls `create_tables()` | Establish a valid base/revision chain from an empty database; production must migrate via Alembic only; test upgrade from every supported deployed revision and recovery after failed migration |
| Event transport | Redpanda as canonical Kafka-compatible broker; Confluent Kafka under the legacy profile; Protobuf event envelope; `apps/shared/events/kafka.py`, `apps/shared/events/topics.py` | Producer/envelope and idempotency primitives exist; catalogue presence does not prove deployed producer/consumer registration | For every topic, record owner, producer, consumer, schema/version, tenant key, retry/DLQ policy and a live broker contract. Replay must prove idempotent effects |
| Raw and derived object storage | MinIO/S3-compatible client; content-addressed object and observation paths | Real storage abstraction is present; full end-to-end retention/erasure and restart proof is not established by source inventory | Verify immutable raw digest, metadata, tenant scope, retry semantics, retention and deletion behavior using a real local object store |
| Search / analytics | OpenSearch, ClickHouse, Redis configuration; app adapters | Stack is declared in developer Compose. Generated inventory marks some paths test-only or orphan; metrics route currently returns seeded constants, not real telemetry | Validate index rebuild from canonical records, ClickHouse query/projection correctness, backpressure under broker lag, measured metrics and recovery/replay |
| Knowledge graph | Neo4j adapter in `apps/projection/graph/neo4j.py`, `GraphStore` abstraction, tenant-scoped uniqueness constraints | A real adapter exists; it does not itself prove every relation/claim projection is production-reachable | Live graph integration test for tenant isolation, idempotent upsert, n-ary hyperedges, revision supersession, deletion/reconciliation and deterministic rebuild |
| Lakehouse | Package description refers to ClickHouse/Iceberg/Parquet; `apps/projection/lakehouse/__init__.py` only declares `NAME` / `VERSION` | **Not a demonstrated lakehouse implementation**; the generated golden path marks it orphaned | Either implement storage/catalog/write/read/replay paths and end-to-end tests, or mark it planned and remove production-ready wording from capability descriptions |
| Orchestration | Temporal client/workflow definitions; `apps/control-plane/services/temporal_materialization_dispatch.py` and `apps/control-plane/db/materialization_outbox.py` | Real workflow seam and outbox code exist, but dispatch catches a database-enqueue failure and can still launch Temporal; the launch request currently sets `source_record_ids = ()` | Outbox durability must be a precondition or return an explicit deferred state; no workflow should report success without durable intent; source-cut input must be real; test process crash between enqueue, launch and ack |
| Extraction / Tenzir | Native lossless parser + optional Tenzir Node sidecar, pinned Node/TQL integration contract; `docs/platform/tenzir-layer1-integration.md` | Genuine opt-in execution and live-node TQL contract are documented; transform emits structural sidecar annotations only; production-scale throughput is not benchmarked | Keep native parser authoritative; prove replay, bounded resource use, backpressure, per-tenant quotas and persisted lineage before broad enablement or promotion into semantic claims |
| Rust acquisition | Rust crates and toolchain; generated audit lists nine crates without executable target | Libraries exist, but they are not independently runnable workers without `[[bin]]` / `main.rs` / an actual host invocation | For each claimed worker, identify executable entrypoint, deployment unit, health/readiness, queue contract, shutdown, retry and end-to-end acquisition proof. Libraries may remain libraries if that is the intended architecture |
| SpecOps / governed lab | Donor-backed Caldera / PhishSlayer lab, ROE API and gate | Explicitly labelled lab mode, but ROE currently derives `approved_by` from request body and stores sign-offs in an in-process registry. Docker host ports were previously published on all interfaces despite a “loopback-only” comment | Treat live destructive/active capabilities as **no-go** until approvals are authenticated-principal-bound, tenant-scoped, durable and auditable; bind dev lab ports to 127.0.0.1; pin donor images by digest before non-lab use; validate egress and license policy |
| Analyst UI | React/TypeScript, Cytoscape graph view, typed API client, component library, Playwright | Core shell builds; screenshot and geometry coverage exist. UI/API mismatch has been found and is being guarded; fixture-backed panels are not all backed by investigation-specific services | Every visible control must map to a served endpoint or explicit unavailable status. Contract-test scope, fixture state, loading, error, empty, unavailable and destructive-action confirmation on desktop/tablet/phone |
| AI documentation / CI | `platform_model.build` plus Python/TS/JS/Rust source-derived semantic graph; Markdown local-link gate and context packet CLI | Strict source inventory is in place; semantic graph parser coverage is not universal: CSS/HTML/SQL/proto are currently inventory nodes, not AST-parsed. Structural coverage is not semantic/runtime coverage | Keep separate metrics for inventoried files, parser-backed AST files, resolved source edges, spec/acceptance traceability, passing contract tests, and live runtime evidence. Never collapse them into a single “100% coverage” badge |

## Local deployment and supply-chain posture

The developer Compose file is intentionally a workstation topology, not a secure production deployment. It uses demo/local service credentials and publishes several infrastructure ports on all host interfaces (for example PostgreSQL, MinIO, Redis, analytics services and Redpanda). Keep it local-only, bind published ports to loopback by default, inject credentials from an ignored local environment file or secret manager, and avoid reusing those credentials outside development. Tenzir's API is explicitly loopback-bound; that safer convention should be consistent across the stack.

The SpecOps lab now binds the host-published Caldera and PhishSlayer APIs to `127.0.0.1`, and the contract suite checks that boundary and `internal: true`. That does not replace image pinning, container hardening, tenant-aware ROE state or a security review of donor behavior.

## Architecture consistency checks

These checks are more important than adding another dependency:

1. **One authority per fact.** Raw observation, assertion/claim, identity decision and projection must have separate types and explicit authority. No dashboard number may be inferred from an empty result or a fixture.
2. **Replay is an invariant.** At-least-once transport means idempotent consumers, durable deduplication, stable event IDs and tested crash windows, not an “exactly once” assumption.
3. **Time is a domain contract.** Keep valid time, observed/capture time and transaction/ingest time distinct; use UTC-normalized intervals, explicit revision supersession and well-defined source cuts.
4. **Identity is not merge-by-score.** Correlation candidates, admission verdicts, merge/split history and graph edges are different lifecycle stages. Every decision needs evidence references and a reversibility story.
5. **Tenant scope must cross every store.** API dependency injection is not enough if the service then reads a process-global registry, DLQ or graph key without tenant filtering.
6. **Degraded is not healthy.** Keep `/health` as liveness and `/api/v1/platform/health` as readiness. Dashboards distinguish healthy, degraded, unavailable and measured zero.
7. **Build artefacts are test subjects.** The checked-out import path can hide broken wheels; a developer database populated by `create_all` can hide missing migrations; a UI mock can hide a 404 or fixture-only route.

## Prioritized remediation

### P0 — before any live/real-target SpecOps use
- Bind ROE sign-off to the validated auth principal, tenant, exact target/scope/policy, expiry and audit-event ID.
- Persist ROE atomically and validate the same durable state in every effectful emulation, phishing, voice and social action.
- Add cross-tenant, forged-approver, restart, expiry and replay tests; otherwise keep effectful actions hard-disabled.

### P1 — before a production readiness claim
- Fix Alembic lineage and remove production-path `create_all`; test clean install + upgrade path.
- Correct package manifest and test the installed control-plane wheel.
- Fix temporal launch durability and supply real source-cut IDs.
- Replace fake DLQ/metrics data with real adapters or return explicitly typed unavailable states.
- Demonstrate graph/search/lakehouse rebuild and broker replay with live service contracts.
- Mark unimplemented lakehouse and unreferenced event families as planned/absent until they have end-to-end proof.

### P2 — to strengthen AI-driven engineering
- Link each spec acceptance criterion to owning implementation symbol, serving route/event, and a test that asserts an externally observable result.
- Keep spec-local decision records normative; generate docs/ADR reader views from them. Enforce zero spec-to-`docs/` Markdown links.
- Make AST parsing scope explicit per language and report both parsed-symbol coverage and file-inventory coverage.
- Add drift contracts for installed packages, Compose topology, image pins, API route parity and screenshot artifacts.

## Evidence boundary

Verified in CI at the time of review: source inventory + semantic graph strict check, platform-model test at an earlier commit, auth and donor-registry contracts, Tenzir live-node TQL contract, webapp typecheck/API contract and responsive screenshot sweep. Subsequent UI changes add a fixture-scope guard and require a fresh green run before the PR can be considered ready. These checks do not establish production latency, full-stack availability, security under adversarial deployment, or 100% behavioral coverage.

## Specification/documentation authority boundary

Normative specs do not link to reader-facing `docs/` views. Feature-local `decisions.md` is normative; stable decision IDs are traced by the semantic graph; generated ADRs and `docs/platform/*` are projections. The graph reports static linkage separately from tested and live-runtime evidence.
