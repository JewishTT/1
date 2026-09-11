# Implementation Plan: Global OSINT Intelligence Platform

**Branch**: `001-global-osint-platform` | **Date**: 2026-09-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-global-osint-platform/spec.md`

**Note**: This is a multi-component system plan produced by `/speckit.plan`.

## Summary

Build an event-driven, evidence-first, process-centric distributed OSINT intelligence fabric. Analysts drive `Investigations` (objective, seeds, scope, policy, budget, freshness) through a continuous loop: Discovery → Frontier → Acquisition → immutable Observations (S3 + Kafka events) → Interpretation (mentions/candidates/assertions) → Admission (ACCEPT/DEFER/REJECT/QUARANTINE) → Entity resolution → Knowledge projections (graph/search/analytics/TDA) → Findings → Feedback back into acquisition utility/priority.

Architecture is split into Control / Data / Feedback planes with strict contracts (AcquisitionWorker, Graph* abstraction, EventEnvelope over Kafka) so engines, graph backends, and scorers are replaceable. Sources of truth: raw objects (S3), event history (Kafka), operational state (PostgreSQL/Redis), workflow (Temporal); OpenSearch/ClickHouse/graph/TDA are all rebuildable projections. Competing contract set is implemented first (spec FR-033/§81): never a broken MVP skeleton with breakable final contracts.

## Technical Context

**Language/Version**: Python 3.11+ (API + control plane), Rust 1.8x (acquisition workers + high-throughput utils), TypeScript 5.x / React 18 (frontend); infrastructure-as-code + Dockerfile-based images; Go not used.

**Primary Dependencies**: FastAPI, Pydantic v2, Temporal Python SDK, confluent-kafka, protobuf + Schema Registry (Redpanda-compatible protocol), SQLAlchemy 2 (async) + asyncpg, redis-py, boto3/aioboto3 (S3/MinIO), OpenSearch client, clickhouse-connect, GUDHI + giotto-tda + NumPy + SciPy (TDA), opencensus/OpenTelemetry SDK, pytest/pytest-asyncio/Testcontainers; Rust: tokio, reqwest, hyper, sha2. Frontend: Vite, React Router, TanStack Query, Zustand, Cytoscape.js (graph panel), ECharts (dashboards).

**Storage**: PostgreSQL 16 (operational state: investigations, sources, frontier operational data, entities/versions/assertions, admission decisions, policies/budgets, audit), Redis (lease/cooldown/locks for frontier), S3-compatible object storage (MinIO dev) for immutable raw observations (content-addressed), OpenSearch (search projection), ClickHouse (analytics projection), pluggable graph backend (default Neo4j 5 community for dev; contract-backed), Kafka KRaft (event backbone, event history), Temporal/PostgreSQL (workflow state).

**Testing**: pytest + pytest-asyncio (backend), Testcontainers (Kafka, Postgres, MinIO, OpenSearch, ClickHouse) for integration; Rust cargo test (unit + worker integration); Vitest + React Testing Library (frontend); contract tests for AcquisitionWorker + Graph* + EventEnvelope; benchmark harness under `bench/`.

**Target Platform**: Linux containers (Docker), Kubernetes (dev: docker-compose / kind), multi-region-ready. Windows only for local dev of control-plane/API contributors.

**Project Type**: distributed back-end platform (event-driven microservices + workers + TDA batch jobs) + React SPA frontend.

**Performance Goals**: useful_observations/sec growth-bound; acquisition workers target ~1k req/s/worker-class at 95th-percentile latency budget per class; search p50<100ms / p95<500ms; graph traversal p95<200ms; projection lag tracked in seconds-minutes, not hours; TDA jobs bounded by budget (configurable dims).

**Constraints**: SSRF/DNS-rebinding-safe acquisition; strict sandboxing per worker class; per-task timeout/size budgets; backpressure tied to downstream queue depth; retry budgets at task/source/investigation/global; all consumers idempotent; no exactly-once assumptions; projection failure never drops evidence.

**Scale/Scope**: single-region control plane v1 with region-striped acquisition topology designed; multi-tenant; ~1M+ observations/day target; dozens of worker classes; ~30 first-class event types; ~24 domain entities.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **C-1 Observation-Immutable**: raw stored content-addressed; only append-only path for observation artifacts. ✓ compatible.
- **C-2 Evidence-First**: every finding carries provenance chain; all artifacts store extractor/model/collector versions. ✓ compatible.
- **C-3 Projection-First**: search/clickhouse/graph/TDA are projections; rebuild pipeline smoke-tested. ✓ compatible.
- **C-4 No Single Store/Graph/Score**: separate engines per workload; graph abstraction; separate score vectors stored. ✓ compatible.
- **C-5 Plugability by Contract**: AcquisitionWorker + GraphProjector/Reader/Traversal/Snapshot interfaces; no vendor imports in domain. ✓ compatible.
- **C-6 Process-Centric**: Investigation is the unit of user work; projections materialize automatically. ✓ compatible.
- **C-7 Security-First**: untrusted input defaults; sandboxing/limits/isolation/RBAC/audit. ✓ compatible.
- **Domain Invariants 1-12**: enforced as design invariants (see data-model.md Invariants section). ✓ compatible.

No constitution violations — Complexity Tracking left empty.

## Project Structure

### Documentation (this feature)

```text
specs/001-global-osint-platform/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
apps/
├── control-plane/                 # FastAPI API + CQRS command/query separation
│   ├── api/
│   ├── application/               # use-cases: investigation, source registry, policy, budgets
│   ├── domain/                    # domain models + invariants (no vendor imports)
│   └── tests/
├── acquisition/                   # Rust workers + Python orchestrators
│   ├── worker-http/               # Rust HTTP worker (AcquisitionWorker impl)
│   ├── worker-browser/            # Playwright-based browser fabric
│   ├── dispatcher/                # scheduler + dispatch loop (Rust)
│   └── tests/
├── interpretation/                # parser → segments → mentions → candidates → assertions
│   ├── parsers/
│   ├── ner/                       # extractor registry, versioned extractors
│   └── tests/
├── admission/                     # admission engine + entity resolution
│   ├── resolution/
│   ├── engine/
│   └── tests/
├── projection/                    # materializers: graph / search / analytics / tda
│   ├── graph/
│   ├── search/
│   ├── analytics/
│   ├── tda/
│   └── tests/
├── feedback/                      # feedback engine, utility scorer, stopping policy
│   └── tests/
├── shared/                        # shared schemas, event envelope, kafka helpers, s3 utils
│   ├── contracts/
│   ├── events/
│   └── storage/
├── webapp/                        # React + TypeScript SPA
│   ├── src/
│   │   ├── pages/                 # investigation pipeline, entity view, finding view, ops dashboard
│   │   ├── components/            # graph panel (cyto), charts, lineage walker
│   │   └── api-client/
│   └── tests/
├── deploy/                        # docker-compose dev, helm charts, k8s manifests
│   └── k8s/
└── bench/                         # benchmark harness (reproducible, per FR-034)
```

**Structure Decision**: monorepo of process-aligned apps, mirroring the planes (Control, Acquisition, Interpretation, Admission, Projection, Feedback), shared contracts/events/storage in `apps/shared`, and a single React SPA. This matches Constitution C-5 (contracts) and keeps acquisition libs in Rust isolated from Python planes.

## Complexity Tracking

> No constitution violations to justify — all gates pass.