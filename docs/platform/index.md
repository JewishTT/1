# COGNITIVE Platform — Dynamic Model

Generated from the source tree by `platform_model/build.py`. **Do not edit by hand**;
regenerate with `python -m platform_model.build`. `--check` fails the build when the
committed model no longer matches the tree.

## Scale

| Metric | Value |
|---|---|
| Components | 16 |
| Python modules | 957 |
| TypeScript modules | 251 |
| Rust crates | 9 |
| Rust source files | 15 |
| Import edges (local) | 2617 |
| Broken local imports | 1 |
| Test files | 321 |
| Test functions | 5177 |
| Untested platform modules | 639 |
| HTTP routes | 174 |
| Contracts (python/docs/root) | 6 / 73 / 12 |
| Capabilities | 30 |

## Pages

- [Components](components.md) — every service and what it owns.
- [Contracts](contracts.md) — the typed cross-layer surface.
- [API](api.md) — the HTTP surface.
- [Data flow](data-flow.md) — the canonical pipeline and the gaps.
- [Import graph](imports.md) — who imports whom, and what does not resolve.
- [Tests](tests.md) — coverage and what is untested.
- [Capabilities](capabilities.md) — WIRED vs TEST_ONLY vs MISSING.
- [Ownership](ownership.md) — one writer per object, and the competing writers.
- [Donors](donors.md) — the supply-chain record.
- [Findings](findings.md) — what the model says is broken.

## Components

| Component | Python | TS | Description |
|---|---|---|---|
| acquisition | 98 | 0 | Discovery, frontier, dispatcher, content router, HTTP/browser workers, ArtifactSink. |
| admission | 30 | 0 | Blocking/resolution, assertion extraction, source independence, calibrated admission. |
| bench | 16 | 0 | E2E smoke harness, micro-benchmarks, knowledge-quality harness. |
| bulk-ingestion | 6 | 0 | Common Crawl / Wayback / WARC / dataset backfill profiles. |
| control-plane | 214 | 0 | FastAPI control plane: investigations, context engine, frontier, review, query planner, HTTP API. |
| feedback | 11 | 0 | Recrawl/priority feedback, stopping policy. |
| interpretation | 109 | 0 | Parsers, deterministic entity-extraction stack, NER/normalization, candidate aggregation. |
| platform_model | 5 | 0 | The generator that produces docs/platform from the tree. |
| projection | 65 | 0 | Graph abstraction, search/analytics projectors, snapshots, TDA. |
| root | 1 | 0 | Repo-root wiring: pytest conftest and the import roots it installs. |
| science | 139 | 0 | Context operators, fabric, retrieval economics, abstraction ladder. |
| shared | 193 | 0 | Contracts, events, domain invariants, storage, security — the substrate every app imports. |
| specops | 30 | 0 | Isolated spec-ops lab profile (never in the routine path). |
| tools | 10 | 0 | Generators, capability/owner/donor tools, probes. |
| webapp | 0 | 251 | React analyst surfaces: investigation, search, entity, finding, ops, lineage. |
| zero | 30 | 0 | Zero-layer contact harvesting from arbitrary seeds. |
