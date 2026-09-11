# Architecture Overview

COGNITIVE runs a closed investigation loop (spec §84). Every hop emits a
traceable event; projections are rebuildable; findings resolve to raw evidence.

## Closed loop

```
Investigation → seeds → discovery → frontier → acquisition → Observation (immutable, S3)
    → Kafka → parse → mentions → candidates → assertions
    → resolution → admission → projections (OpenSearch/ClickHouse/Neo4j)
    → GraphSnapshot → TDA → TopologicalFeature → Finding
    → feedback → new acquisition
```

## Applications

| App | Role | Stack |
| --- | --- | --- |
| `apps/shared` | Contracts, events, storage, domain invariants, observability | Python |
| `apps/control-plane` | Investigations, policy/budget, frontier, review, query planner, HTTP API | Python/FastAPI |
| `apps/acquisition` | Discovery, frontier, dispatcher, content router, HTTP/browser workers | Rust + Python |
| `apps/interpretation` | Parsers, NER/normalization, candidate aggregation | Python |
| `apps/admission` | Blocking/resolution, assertion extraction, source independence, calibrated admission | Python |
| `apps/projection` | Graph abstraction, search/analytics projectors, snapshots, TDA | Python |
| `apps/feedback` | Recrawl/priority feedback, stopping policy | Python |
| `apps/webapp` | Investigation/search/entity/finding/ops UI + lineage walker | Vite + React + TS |
| `apps/deploy` | Docker Compose dev topology, Grafana, k8s configs | — |
| `bench/` | E2E smoke harness + micro-benchmarks + knowledge-quality harness | Python |

## Key properties (Constitution invariants)

- **I-1**: observations are immutable — content-addressed in S3, updates rejected.
- **I-5**: no blob bodies on Kafka; raw objects live in storage, events carry refs.
- **I-6**: identity claims come exclusively from entity resolution; TDA is structural-only.
- **I-11/I-12**: graph projections are idempotent and rebuildable from Kafka offsets.
- **Multi-tenant isolation & RBAC**: tenant-scoped queries, per-tenant ACLs/indexes/prefixes.

## Messaging

Events follow a versioned `EventEnvelope` (protobuf) with `event_id`/`correlation_id`/
`provenance`; idempotent producers dedup on `event_id`/`task_id`/`observation_id`.
Topic catalog and schemas: `apps/shared/events/`.

## Data plane

- **MinIO** — raw + derived evidence (`s3://knowledge/raw/{tenant}/{ym}/{sha256}`).
- **PostgreSQL 16** — operational state (investigations, frontier, decisions, reviews).
- **OpenSearch/E2** — search indices (observations…findings).
- **ClickHouse** — observation metrics, source aggregates, cost accounting.
- **Neo4j** — graph backend behind the `graph/abstraction.py` interface.
- **Temporal** — investigation lifecycle + recrawl workflows.

## Run it

Single-node dev topology + validation:

```bash
docker compose -f apps/deploy/docker-compose.yml up -d
uv run python -m bench.run --scenario smoke-val
```

See [quickstart.md](../specs/001-global-osint-platform/quickstart.md) and
[bench/run.py](../../bench/run.py).