# COGNITIVE Platform — Dynamic Model

Generated from the source tree by `platform_model/build.py`. **Do not edit by hand**;
regenerate with `python -m platform_model.build`. `--check` fails the build when the
committed model no longer matches the tree.

## Scale

| Metric | Value |
|---|---|
| Components | 20 |
| Python modules | 1060 |
| TypeScript modules | 283 |
| Rust crates | 9 |
| Rust source files | 16 |
| Import edges (local) | 2949 |
| Unresolved imports (no local target) | 35 |
| Unresolved: local | 4 |
| Unresolved: stale-platform-path | 0 |
| Unresolved: guarded-local | 30 |
| Unresolved: guarded-gap | 1 |
| Unresolved: unknown (undeclared) | 0 |
| Test files | 384 |
| Test functions | 5523 |
| Untested platform modules | 274 |
| HTTP routes | 222 |
| Contracts (python/docs/root) | 7 / 74 / 12 |
| Capabilities | 30 |

## Pages

- [Components](components.md) — every service and what it owns.
- [Contracts](contracts.md) — the typed cross-layer surface.
- [API](api.md) — the HTTP surface.
- [Data flow](data-flow.md) — the canonical pipeline and the gaps.
- [Import graph](imports.md) — who imports whom, and what does not resolve.
- [Maturity](maturity.md) — which modules are built, primitive, or stubs.
- [Reachability](reachability.md) — what production can actually reach.
- [Tests](tests.md) — coverage and what is untested.
- [Capabilities](capabilities.md) — WIRED vs TEST_ONLY vs MISSING.
- [Ownership](ownership.md) — one writer per object, and the competing writers.
- [Donors](donors.md) — the supply-chain record.
- [Findings](findings.md) — what the model says is broken.
- [Gaps](gaps.md) — machine-checked defects with re-checkable evidence.
- [Golden path](golden-path.md) — the person-background path, capability by capability.

## Components

| Component | Python | TS | Description |
|---|---|---|---|
| acquisition | 124 | 0 | Discovery, frontier, dispatcher, content router, HTTP/browser workers, ArtifactSink. |
| admission | 30 | 0 | Blocking/resolution, assertion extraction, source independence, calibrated admission. |
| bench | 16 | 0 | E2E smoke harness, micro-benchmarks, knowledge-quality harness. |
| bulk-ingestion | 6 | 0 | Common Crawl / Wayback / WARC / dataset backfill profiles. |
| control-plane | 265 | 0 | FastAPI control plane: investigations, context engine, frontier, review, query planner, HTTP API. |
| deploy | 1 | 0 | Docker Compose dev topology, Grafana, k8s configs. |
| economics | 4 | 0 |  |
| feedback | 11 | 0 | Recrawl/priority feedback, stopping policy. |
| intelligence | 3 | 0 |  |
| interpretation | 120 | 0 | Parsers, deterministic entity-extraction stack, NER/normalization, candidate aggregation. |
| platform_model | 13 | 0 | The generator that produces docs/platform from the tree. |
| projection | 67 | 0 | Graph abstraction, search/analytics projectors, snapshots, TDA. |
| root | 1 | 0 | Repo-root wiring: pytest conftest and the import roots it installs. |
| science | 139 | 0 | Context operators, fabric, retrieval economics, abstraction ladder. |
| shared | 201 | 0 | Contracts, events, domain invariants, storage, security — the substrate every app imports. |
| specops | 1 | 0 | Isolated spec-ops lab profile (never in the routine path). |
| specops_ci | 4 | 0 |  |
| tools | 14 | 0 | Generators, capability/owner/donor tools, probes. |
| webapp | 0 | 283 | React analyst surfaces: investigation, search, entity, finding, ops, lineage. |
| zero | 40 | 0 | Zero-layer contact harvesting from arbitrary seeds. |
