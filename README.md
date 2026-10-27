# COGNITIVE

Event-driven, evidence-first, process-centric distributed OSINT intelligence fabric.

Analysts drive `Investigations` through a continuous loop: Discovery → Frontier → Acquisition → immutable Observations → Interpretation → Admission/Resolution → Knowledge projections (graph/search/analytics/TDA) → Findings → Feedback into acquisition utility.

The OSINT core is complemented by a scientific reasoning layer and a zero-layer contact-harvesting pipeline, surfaced through one console.

> This file is **generated** by `platform_model/narrative.py` from the tree. Do not edit it by hand; run `python -m platform_model.build`. The machine model lives in [`docs/platform/`](docs/platform/index.md).

## Scale (from the tree)

| Metric | Value |
|---|---|
| Components | 16 |
| Python modules | 1007 |
| TypeScript modules | 255 |
| Rust source files / crates | 15 / 9 |
| Resolved local import edges | 2806 |
| HTTP routes / routers | 182 / 33 |
| Event types / lanes | 99 / 29 |
| Test files / test functions | 340 / 5271 |
| Untested platform modules | 268 |

## Components

| Component | Python | TypeScript | Rust | Description |
|---|---|---|---|---|
| `acquisition` | 105 | 0 | 15 | Discovery, frontier, dispatcher, content router, HTTP/browser workers, ArtifactSink. |
| `admission` | 30 | 0 | 0 | Blocking/resolution, assertion extraction, source independence, calibrated admission. |
| `bench` | 16 | 0 | 0 | E2E smoke harness, micro-benchmarks, knowledge-quality harness. |
| `bulk-ingestion` | 6 | 0 | 0 | Common Crawl / Wayback / WARC / dataset backfill profiles. |
| `control-plane` | 241 | 0 | 0 | FastAPI control plane: investigations, context engine, frontier, review, query planner, HTTP API. |
| `feedback` | 11 | 0 | 0 | Recrawl/priority feedback, stopping policy. |
| `interpretation` | 112 | 0 | 0 | Parsers, deterministic entity-extraction stack, NER/normalization, candidate aggregation. |
| `platform_model` | 13 | 0 | 0 | The generator that produces docs/platform from the tree. |
| `projection` | 67 | 0 | 0 | Graph abstraction, search/analytics projectors, snapshots, TDA. |
| `root` | 1 | 0 | 0 | Repo-root wiring: pytest conftest and the import roots it installs. |
| `science` | 139 | 0 | 0 | Context operators, fabric, retrieval economics, abstraction ladder. |
| `shared` | 196 | 0 | 0 | Contracts, events, domain invariants, storage, security — the substrate every app imports. |
| `specops` | 30 | 0 | 0 | Isolated spec-ops lab profile (never in the routine path). |
| `tools` | 10 | 0 | 0 | Generators, capability/owner/donor tools, probes. |
| `webapp` | 0 | 255 | 0 | React analyst surfaces: investigation, search, entity, finding, ops, lineage. |
| `zero` | 30 | 0 | 0 | Zero-layer contact harvesting from arbitrary seeds. |

## Quick start

Prerequisites: Docker Compose, `uv` + Rust toolchain, Node 20+ / `pnpm`.

```bash
cp .env.example .env                                       # stack endpoints (Postgres/Kafka/S3/…)
docker compose -f apps/deploy/docker-compose.yml --profile core --profile analytics up -d
uv sync                                                    # Python workspace
cargo build --manifest-path apps/acquisition/Cargo.toml    # Rust acquisition workers
cd apps/control-plane && uv run uvicorn api.main:app --port 8000   # control-plane API
cd apps/webapp && pnpm install && pnpm dev                 # UI on :5173 (proxies /api → :8000)
```

Compose profiles stage the stack: `core` → `streaming` → `collectors` → `analytics` (see [docs/architecture/overview.md](docs/architecture/overview.md)).

Full validation: `uv run python -m bench.run --scenario smoke-val` walks the closed loop against a clean stack (`--dry-run` validates the harness without one).

## Documentation

- [Platform model (generated)](docs/platform/index.md) — the source of truth for the platform's shape.
- [Docs index](docs/README.md)
- Architecture: [overview](docs/architecture/overview.md) · [collection fabric](docs/architecture/fabric-collection.md) · [multi-region](docs/architecture/multi-region.md) · [dynamic entity invariant](docs/architecture/dynamic-entity-invariant.md) · [stream processing](docs/architecture/stream-processing.md)
- [Contributing](docs/CONTRIBUTING.md)

## Governance

See `specs/` for the constitution-bound specs, plans, and task lists. Architecture decisions require an ADR (`docs/adr/`).
