# COGNITIVE

Event-driven, evidence-first, process-centric distributed OSINT intelligence fabric.

Analysts drive `Investigations` through a continuous loop: Discovery → Frontier → Acquisition → immutable Observations (S3 + Kafka) → Interpretation → Admission/Resolution → Knowledge projections (graph/search/analytics/TDA) → Findings → Feedback into acquisition utility.

The OSINT core is complemented by a scientific reasoning layer (calibrated claims, hypotheses, causal/temporal/structural inference, robustness, experiments) and a zero-layer contact-harvesting pipeline, surfaced through a single three-module console: OSINT / Economics / SpecOps.

## Layout

| Path | Purpose |
| --- | --- |
| `apps/control-plane` | FastAPI API + CQRS: investigations, policy/budget, frontier, review, query planner |
| `apps/acquisition` | Rust workers (HTTP/browser) + dispatcher / frontier / discovery / content-router |
| `apps/bulk-ingestion` | Historical archive replay, reservoir sampling, bulk collectors |
| `apps/interpretation` | parsers → segments → mentions → candidates/assertions; deterministic entity-extraction stack (spec 007) |
| `apps/admission` | admission engine + entity resolution + calibration |
| `apps/projection` | graph / search / analytics / TDA materializers |
| `apps/feedback` | feedback engine, utility scorer, stopping policy |
| `apps/science` | Scientific intelligence fabric: calibrated claims, hypotheses, causal/temporal/structural inference, robustness, experiments |
| `apps/zero` | Zero-layer contact harvesting: any input → contacts, deterministic, no AI (spec 010) |
| `apps/shared` | contracts, events (protobuf), storage, scoring, OTEL |
| `apps/webapp` | React + TypeScript console: OSINT / Economics / SpecOps modules, intel board, TDA and network analysis, science review |
| `apps/deploy` | docker-compose dev profiles, k8s manifests, Grafana dashboards |
| `bench/` | benchmark harness + fixtures (`uv run python -m bench.run --scenario smoke-val`) |
| `donors/` | donor repositories used as pattern/code sources (specs 002–005, 009) |
| `specs/` | Speckit feature artifacts (spec/plan/research/data-model/tasks) |
| `docs/` | architecture overviews, ADRs, contributing guide |

## Quick start

Prerequisites: Docker Compose, `uv` + Rust toolchain, Node 20+ / `pnpm`.

```bash
cp .env.example .env                                       # stack endpoints (Postgres/Kafka/S3/…)
docker compose -f apps/deploy/docker-compose.yml --profile core --profile analytics up -d
uv sync                                                    # Python workspace (control-plane, science, zero, …)
cargo build --manifest-path apps/acquisition/Cargo.toml    # Rust acquisition workers
cd apps/control-plane && uv run uvicorn api.main:app --port 8000   # control-plane API
cd apps/webapp && pnpm install && pnpm dev                 # UI on :5173 (proxies /api → :8000)
```

Compose profiles stage the stack: `core` (minio/kafka/postgres/redis/temporal) → `streaming` (redpanda/flink/nessie) → `collectors` (browsertrix) → `analytics` (opensearch/clickhouse/neo4j).

Full validation: `uv run python -m bench.run --scenario smoke-val` walks the whole closed loop against a clean stack (`--dry-run` validates the harness and fixtures without one) — see `specs/001-global-osint-platform/quickstart.md`.

## Specs

| Spec | Feature |
| --- | --- |
| `001-global-osint-platform` | Global OSINT intelligence platform (closed investigation loop) |
| `002-donor-pattern-integration` | Donor pattern integration |
| `003-donor-code-integration` | Donor code extraction & integration |
| `004-donor-coverage-complete` | Full donor coverage |
| `005-donor-core-subsystems` | Donor core subsystems |
| `006-scientific-intelligence-fabric` | Scientific intelligence fabric |
| `007-deterministic-entity-extraction-stack` | Deterministic entity extraction stack |
| `008-discovery-search-fabric` | Event-driven discovery & rebuildable search projection fabric |
| `009-donor-full-catalogue` | Donor full catalogue |
| `010-zero-layer-contact-harvesting` | Zero-layer contact harvesting pipeline |
| `011-atomic-entity-commoncrawl-tda` | Atomic entity × Common Crawl pilot × TDA |
| `012-dynamic-entity-invariant` | Dynamic entity invariant (atomic-entity graph model, TDA-ready temporality) |

## Documentation

- [Docs index](docs/README.md)
- Architecture: [overview](docs/architecture/overview.md) · [collection fabric](docs/architecture/fabric-collection.md) · [multi-region topology](docs/architecture/multi-region.md) · [dynamic entity invariant](docs/architecture/dynamic-entity-invariant.md) · [stream processing](docs/architecture/stream-processing.md)
- [Quickstart / validation guide](specs/001-global-osint-platform/quickstart.md)
- [Contributing](docs/CONTRIBUTING.md)

## Governance

See `specs/` for the constitution-bound specs, plans, and task lists. Architecture decisions require an ADR (`docs/adr/`).

