# Implementation Plan: Donor Pattern Integration

**Branch**: `002-donor-pattern-integration` | **Date**: 2026-09-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-donor-pattern-integration/spec.md`

**Note**: This is a multi-component system plan produced by `/speckit.plan`.

## Summary

Integrate the validated *conceptual* subsystems of ten external OSINT projects into COGNITIVE behind the existing contracts and invariants of feature 001 — no imported code, no vendor lock-in, no Frankenstein. Five user stories map donors to concrete platform capabilities:

- **US1**: FollowTheMoney statement-level knowledge model (provenance, dataset boundary, temporal validity, schema/ontology).
- **US2**: OpenOSINT correlation-without-destruction (possible_match edges, non-destructive dedup, human review) + Vitni review semantics.
- **US3**: Kipi investigation/evidence workspace + PANO analyst workbench (graph/timeline/map).
- **US4**: SpiderFoot connector ecosystem + reNgine recon orchestration + NetForensicAI parser interface.
- **US5**: investigator evidence reasoning (corroboration/claim verdict/storyline) + kafSIEM stream provenance/ontology packs.

All integration reuses the existing event-driven architecture: immutable observations (S3 + Kafka), EventEnvelope, AcquisitionWorker/Graph*/UtilityScorer contracts, rebuildable projections, admission engine, and the bench harness. Donors contribute *patterns*; COGNITIVE contributes the *machine*.

## Technical Context

**Language/Version**: Python 3.11+ (control-plane, interpretation, admission, projection, feedback, shared), Rust 1.8x (acquisition workers), TypeScript 5.x / React 18 (analyst workbench).

**Primary Dependencies**: No new donor dependencies. Existing: Pydantic v2, protobuf + Schema Registry, confluent-kafka, SQLAlchemy 2 async, redis-py, aioboto3 (S3/MinIO), OpenSearch client, clickhouse-connect, GUDHI + giotto-tda, pytest/pytest-asyncio; Rust: tokio, reqwest, sha2; frontend: Vite, React Router, TanStack Query, Zustand, Cytoscape.js, ECharts.

**Storage**: PostgreSQL 16 (statement/correlation/review/connector operational state), S3-compatible (MinIO dev) immutable raw observations, Kafka (event backbone, ontology packs), Redis (leases), pluggable graph backend / OpenSearch / ClickHouse as rebuildable projections.

**Testing**: pytest + pytest-asyncio (backend contract/integration/unit), Rust cargo test, Vitest + React Testing Library (frontend), benchmark harness `bench/`. Donor-pattern integrity is enforced via contract tests (SC-001…SC-010).

**Target Platform**: Linux containers (Docker), Kubernetes; Windows for local dev of the control plane/API.

**Project Type**: distributed back-end platform (event-driven microservices + workers) + React SPA analyst workbench; a cross-cutting integration feature on top of feature 001.

**Performance Goals**: unchanged from feature 001 (acquisition ~1k req/s per worker class, search p50<100ms/p95<500ms, graph traversal p95<200ms, rebuildable projections). Donor additions (correlation graph, claim verdicts, connector registry) must not degrade the bench harness (`bench/run --scenario smoke-val` stays green).

**Constraints**: no vendor imports in application logic (C-5); observation immutability (I-1); stored score fields separate (I-7); projections rebuildable (I-12); donation ≠ import — adopt concepts only (FR-014).

**Scale/Scope**: one cross-cutting integration feature over the existing monorepo `apps/`; ~10 donor concepts mapped to concrete existing modules.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I-1 Observation Immutable** — donor patterns never mutate observations; statement provenance strengthens the evidence chain. ✓ compatible.
- **I-2 Mention != Candidate != Entity** — correlation edges live between Candidates, never collapse them into Entities without admission. ✓ compatible.
- **I-3 Assertion != truth** — statements carry confidence + provenance, never "fact" status. ✓ compatible.
- **I-4/I-12 Projections rebuildable** — correlation graph, review, and timeline are projection artifacts rebuilt from events. ✓ compatible.
- **I-5 Kafka != object store** — ontology packs and events carry refs, not blobs. ✓ compatible.
- **I-7 Admission != Priority** — claim verdicts and corroboration stored as separate typed signals, never a single score. ✓ compatible.
- **C-4/C-5 Plugability by Contract** — connectors implement AcquisitionWorker; parsers behind a registry; no vendor imports in domain logic. ✓ compatible.
- **C-6 Process-Centric** — investigations remain the unit of work; workbench is a surface over existing state. ✓ compatible.
- **C-7 Security-First** — connectors/parsers inherit worker isolation and egress policy; adoption is pattern-only. ✓ compatible.

No constitution violations. Complexity Tracking left empty.

## Project Structure

### Documentation (this feature)

```text
specs/002-donor-pattern-integration/
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
├── shared/
│   ├── contracts/                 # + connector.md, parser.md, correlation-review.md, statement.md
│   ├── domain/                    # + enforce_statement_provenance, enforce_correlation_no_merge
│   ├── events/                    # + ontology pack registry (kafSIEM pattern)
│   └── scoring/                   # + claim verdict / corroboration signals (investigator)
├── admission/
│   ├── engine/temporal.py         # exists — temporal policies (US1, FR-016)
│   ├── evidence/independence.py   # exists — extend: reprint collapse + claim verdict
│   └── resolution/                # exists — expose possible_match correlation graph
├── interpretation/
│   ├── parsers/registry.py        # exists — add can_parse/parse Adapter protocol
│   └── extractors/registry.py     # + schema/ontology admissible-type constraints
├── control-plane/                 # investigation/evidence workspace + review endpoints
├── acquisition/                   # connector adapters behind AcquisitionWorker
├── projection/                    # correlation-graph + review projections
├── webapp/src/                    # PANO/Vitni workbench: graph/timeline/map + review
└── deploy/                        # no new services; reuse compose topology
```

**Structure Decision**: donors map onto the existing process-aligned apps — no new top-level packages, no new services, no vendor deps. Connectors live behind the AcquisitionWorker contract; parsers behind a registry; correlation/review/ontology as typed Postgres/event/projection artifacts. Matches Constitution C-5 and the No-MVP rule.

## Complexity Tracking

> No constitution violations — no added complexity to justify. Donor adoption is pattern-only and reuses existing planes/contracts.
