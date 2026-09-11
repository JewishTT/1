# COGNITIVE

Event-driven, evidence-first, process-centric distributed OSINT intelligence fabric.

Analysts drive `Investigations` through a continuous loop: Discovery → Frontier → Acquisition → immutable Observations (S3 + Kafka) → Interpretation → Admission/Resolution → Knowledge projections (graph/search/analytics/TDA) → Findings → Feedback into acquisition utility.

## Layout

| Path                | Purpose                                             |
|---------------------|-----------------------------------------------------|
| `apps/control-plane`| FastAPI API + CQRS command/query separation         |
| `apps/acquisition`  | Rust workers (HTTP/browser) + dispatcher/frontier    |
| `apps/interpretation` | parsers → segments → mentions → candidates/assertions |
| `apps/admission`    | admission engine + entity resolution + calibration   |
| `apps/projection`   | graph / search / analytics / TDA materializers       |
| `apps/feedback`     | feedback engine, utility scorer, stopping policy     |
| `apps/shared`       | contracts, events (protobuf), storage, scoring, OTEL |
| `apps/webapp`       | React + TypeScript SPA                               |
| `apps/deploy`       | docker-compose dev, helm/k8s manifests, grafana      |
| `bench/`            | benchmark harness + fixtures (`bench/run --scenario smoke-val`) |
| `specs/`            | Speckit feature artifacts (spec/plan/research/data-model/tasks) |

## Quick start

```bash
docker compose -f apps/deploy/docker-compose.yml up -d
uv sync            # Python workspace (control-plane etc.)
cargo build        # apps/acquisition
pnpm install && pnpm dev   # apps/webapp
```

Full validation: `bench/run --scenario smoke-val` (see `specs/001-global-osint-platform/quickstart.md`).

## Governance

See `specs/001-global-osint-platform/` for the constitution-bound spec, plan, and task list. Architecture decisions require an ADR (`docs/adr/`).