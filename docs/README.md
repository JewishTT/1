# COGNITIVE Documentation

Event-driven, evidence-first, process-centric OSINT intelligence fabric.

Raw observations are immutable and content-addressed in S3; every analytical
result must resolve back to a raw object through an unbroken lineage chain;
every projection (graph, search, analytics, TDA) is a rebuildable artifact. The
OSINT core is complemented by a scientific-reasoning layer and a zero-layer
contact-harvesting pipeline, surfaced through one console.

> **Read this first.** This document describes the platform **as it actually
> is**, not as the specs intend it to be. Section [Known gaps](#known-gaps--verified-inconsistencies)
> lists what is stubbed, unwired, or contradicted between docs and code. Several
> documents in this repo describe a target architecture; the code is ahead on
> some layers and behind on others.

---

## Orientation — read in this order

| # | Read | What you get |
| --- | --- | --- |
| 1 | `.specify/memory/constitution.md` | 7 core principles, 12 domain invariants, tech baseline, governance. **Supersedes all other practice.** |
| 2 | `AGENTS.md` | Working rules for agents and humans: donor reuse is the default, boundaries are not waivable, exceptions are not yours to decide. |
| 3 | `architecture/overview.md` | The closed loop, app table, data plane, compose profiles. |
| 4 | `../apps/control-plane/api/main.py` | The 23 routers that constitute the entire HTTP surface. |
| 5 | `../apps/shared/events/topics.py` | `EVENT_CATALOG` — ~100 event types → 28 lanes + `events.dlq` / `events.quarantine`. The routing authority. |
| 6 | `../specs/024-context-driven-continuous-intelligence/` | Where the platform is going, and the honest audit of where it is. |

---

## Architecture

| Document | Scope |
| --- | --- |
| [architecture/overview.md](architecture/overview.md) | Closed investigation loop, app roles, data plane, phased deployment. |
| [architecture/fabric-collection.md](architecture/fabric-collection.md) | Collection fabric: content-addressed gate, ETag re-observation, WARC archival/range retrieval, bulk replay, partitioned frontier. |
| [architecture/dynamic-entity-invariant.md](architecture/dynamic-entity-invariant.md) | The two-kind entity model (`GraphInvariant` / `StaticObject`) and why it is the substrate for everything temporal. |
| [architecture/multi-region.md](architecture/multi-region.md) | Region-pinned topology, regional backpressure (GO/THROTTLE/HALT). |
| [architecture/stream-processing.md](architecture/stream-processing.md) | Stream-processing narrative. **Partly aspirational** — the Flink engines it names are not in this repo (see Known gaps). |
| [architecture/donors/](architecture/donors/00-INDEX.md) | 11 donor dossiers (00 index … 10 zero-layer) + integration matrix. Source of the 146 YAML source definitions. |

## Applications

| Path | Role | Runtime |
| --- | --- | --- |
| `apps/shared` | Contracts, event catalog, storage, scoring, domain invariants, OTEL, semantic fabric, DLQ | Python |
| `apps/control-plane` | 122-endpoint FastAPI API + CQRS, policy/budget, frontier, review, query planner, Temporal workflows | Python |
| `apps/acquisition` | Discovery, frontier, dispatcher, content router, observation gate, worker runtimes, 146-source catalogue; 8 Rust crates | Rust + Python |
| `apps/bulk-ingestion` | Common Crawl historical replay + Wayback CDX backfill → `FrontierSink` | Python |
| `apps/interpretation` | Parsers (primproc/payload/WARC), 15-kind relation-signal substrate, 5 deterministic extractors, candidate aggregation, relation extraction, evidence manifests | Python |
| `apps/admission` | Blocking → pairwise → collective resolution, admission ladder, temporal consistency, source independence, correlation | Python |
| `apps/projection` | Graph abstraction + Neo4j, relation store, snapshots, search (BM25/bm25s/Quickwit), analytics, TDA, metrics, observation lake | Python |
| `apps/feedback` | Feedback engine, stopping policy, 3 branches (source/entity/finding), frontier sinks | Python |
| `apps/science` | Calibrated claims, hypotheses, causal/temporal/structural inference, robustness, experiments, review ladder, anchoring | Python |
| `apps/zero` | Zero-layer contact harvesting: 13 harvesters, Fellegi–Sunter resolution, enrichment, feedback loop | Python |
| `apps/webapp` | Console: legacy 3-module (OSINT/Economics/SpecOps) + UI-2.0 Investigation Workspace | Vite + React + TS |
| `apps/deploy` | docker-compose profiles, k8s, Grafana | — |
| `bench/` | E2E smoke harness, micro-benchmarks, knowledge-quality harness | Python |

**Layer order is mechanically enforced**: `shared → interpretation → admission → projection → control-plane → science`
(`apps/shared/tools/layer_boundaries.py:29`). The guard is a **ratchet, not a fix** — 25
pre-existing violations are recorded and allowed to persist; the count may not grow
(`apps/shared/tests/unit/test_layer_boundaries.py:27`).

## Storage & infrastructure

| Store | Role | Compose service |
| --- | --- | --- |
| MinIO / S3 | Immutable raw + derived evidence, `s3://knowledge/raw/{tenant}/{ym}/{sha256}` | `minio` |
| PostgreSQL 16 | **Authoritative operational state + authoritative relational graph** (D2/ADR-0027) | `postgres` |
| Redpanda | Event backbone. "Kafka" in this repo names the *protocol*, never a product (ADR-0026) | `redpanda` (`kafka` = legacy profile) |
| OpenSearch | Search projection target per docs/ADR-0004 | `opensearch` |
| ClickHouse | Observation metrics, source aggregates, cost accounting | `clickhouse` |
| Neo4j | Rebuildable **serving** projection only — demoted by ADR-0027 | `neo4j` |
| Temporal | Investigation lifecycle + recrawl + temporal materialization | `temporal` |
| Redis | Declared for frontier leases; **no client exists in the repo** (see Known gaps) | `redis` |
| Flink / Nessie / Browserterix | Streaming + collectors profiles | `flink-*`, `nessie`, `browsertrix` |

Compose profiles stage the stack: `core` (minio/redpanda/postgres/redis/temporal/searxng)
→ `streaming` (flink/nessie/redpanda-console) → `collectors` (browsertrix) →
`analytics` (opensearch/clickhouse/neo4j) → `legacy-kafka` (confluent kafka + schema-registry).

## Event model

`EventEnvelope` is protobuf, 16 fields, versioned, and **not extended** by feature 024
(decision D5): `apps/shared/events/event_envelope.proto:7`. It carries `event_id`
(idempotency key), `event_type`/`event_version`, `investigation_id`, `correlation_id`,
`causation_id`, producer identity, `produced_at`, `observation_id`, `entity_id`,
`tenant_id`, `source_id`, `work_id`, `region_id`, and a **refs-only** `payload`
(no blobs — I-5).

Logical time (`observed_at`, `logical_time`) travels **inside typed payloads** under a
mandatory convention, validated broker-free by `apps/shared/events/timestamps.py`.
The rule that makes it checkable: `produced_at` may never be copied into a payload's
`observed_at`.

---

## Design decisions (ADRs)

26 ADRs in [`adr/`](adr/). **The numbering skips 0025** — no such file exists.

| Group | ADRs |
| --- | --- |
| Foundations | `0001` Kafka vs alternatives · `0002` object storage · `0003` PostgreSQL role · `0004` OpenSearch · `0005` ClickHouse · `0006` Flink role · `0007` Temporal |
| Knowledge layer | `0008` graph abstraction · `0009` graph backend · `0010` TDA architecture · `0011` event schema · `0012` provenance |
| Reasoning | `0013` entity resolution · `0014` admission engine · `0015` frontier architecture · `0016` scheduling · `0017` recrawl strategy |
| Operations | `0018` multi-region topology · `0019` reconstruction frontier · `0020` outbox lease and reclaim · `0021` atomic stream sequence |
| Fabric | `0022` indexed worldline relations · `0023` relation identity and arity · `0024` claim and context persistence |
| Feature 024 | `0026` Redpanda transport runtime · `0027` PostgreSQL is graph authority |

> **Amendment sweep outstanding.** ADR-0026 records that the ADRs naming Kafka as the
> transport are now imprecise. The sweep (task T012) has not been done.

---

## Specs

22 feature folders in [`../specs/`](../specs/). `.specify/feature.json` points at the
active one. **Task checkboxes are not a reliable progress ledger** — for features
015, 017, 018, 021, 023 and 024 the code is ahead of the file. Verify against
`git status` and the source tree before trusting `tasks.md`.

| Spec | Feature | Real state |
| --- | --- | --- |
| `001-global-osint-platform` | Closed investigation loop | Baseline; quickstart is the validation reference |
| `002`–`005`, `009-donor-*` | Donor pattern/code integration, coverage, catalogue | Landed in `donors/` and `docs/architecture/donors/` |
| `006-scientific-intelligence-fabric` | Science layer | Landed in `apps/science` |
| `007-deterministic-entity-extraction-stack` | No-ML extraction lane | Landed in `apps/interpretation/extractors` |
| `008-discovery-search-fabric` | Discovery + rebuildable search fabric | Landed in `apps/projection/search` |
| `010-zero-layer-contact-harvesting` | Zero-layer pipeline | Landed in `apps/zero` |
| `011-atomic-entity-commoncrawl-tda` | CC pilot × TDA | **In progress** (14/18); the CC/TDA chain is load-bearing |
| `012-dynamic-entity-invariant` | Two-kind entity model | Landed: `apps/shared/domain/graph_invariant.py`, 28 tests |
| `014-temporal-materialization` | Governed event-time windows | **30/30** — the only feature with a fully checked task list |
| `015-worldline-reconstruction` | Worldline as unit of materialization | Draft, 11/104 declared; substrate landed without bookkeeping |
| `016-relation-evidence-graph-fabric` | Content-addressed `RelationClaim` | Draft, 32/93; **the most load-bearing built substrate** |
| `017-semantic-fabric` | Ontology-as-tool | Implemented via 018 (`apps/shared/semantic/`) |
| `018-world-substrate` | Four P0s: identity anchor, capture lineage, build/validate/admit split | Implemented via migration 019 (44 KB) |
| `019-universal-relation-extraction` | Relations as invariants from observation flow | **44/44**; migration 020 landed |
| `021-entity-relation-extraction-finalization` | Structural predicate signatures, n-ary signals, type vocabulary | Draft, 0/94; **migration `021` does not exist** |
| `022-estorides-donor-mining` | Mine `estorides` for primitives | **Aborted on a licence hazard** — see Known gaps |
| `023-acquisition-integration-searxng` | 5 runtime families on one capture seam | Live-proven 29/29 across SearXNG/Airbyte/BBOT/Maigret/SpiderFoot; `tasks.md` says 0/214 |
| `024-context-driven-continuous-intelligence` | **Active.** Durable research context as primary driver | Phases 0–7, 12–13 have real code; phases 8, 9, 10, 11 essentially empty; UI track ~half done |

Feature 024's [`wave0-verified-state.md`](../specs/024-context-driven-continuous-intelligence/wave0-verified-state.md)
is the most valuable artifact in `specs/` — a worked example of auditing a source
brief against the code and rejecting 15 of 33 claims. Read it before trusting any
spec prose.

---

## Governance

- `constitution.md` supersedes all other practice. Verified on every PR.
- Architecture decisions require an ADR. Rejected analysis outputs (admission
  rejections, TDA signals) are preserved with decision, reasons, score vectors,
  versions and timestamps for replay.
- Source independence is judged by derivation lineage, not publication count.
- PowerShell (`.ps1`) is the script type for Speckit automation on Windows.
- Speckit workflow spine: `specify → [review-spec gate] → plan → [review-plan gate] → tasks → implement`.
  Gates abort on reject. Commands live in `.opencode/` (`speckit.converge` is the
  command that reconciles `tasks.md` against built code).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) — repo layout, tooling, tests-first
convention, gateway contracts that must not regress.

Validation record: [quickstart-validation.md](quickstart-validation.md).

```bash
uv run python -m bench.run --scenario smoke-val   # closed-loop traceability chain
cd apps/webapp && pnpm test                       # UI suite (baseline: webapp/tmp/vitest-baseline.json)
```

---

## Known gaps — verified inconsistencies

Everything below was checked against the source, not inferred from docs.

### Blocks "is this thing real?"

| Finding | Evidence |
| --- | --- |
| **The 8 Rust crates have no `fn main` and no `[[bin]]`.** They produce only rlibs; nothing outside their own tests links them. `cargo build` yields no runnable worker. | `apps/acquisition/Cargo.toml:3-12`; no `main.rs` anywhere |
| **`worker-browser` (Rust) contains no browser automation** — only an admission gate and a semaphore. The render path is `worker_browser/renderer.py`, whose only implementation is `NoopRenderer`. | `apps/acquisition/worker_browser/renderer.py:89-93` |
| **No process consumes `acquisition.request`.** The only `confluent_kafka.Consumer` in the workspace is a hand-rolled one in a proof script. | `apps/interpretation/_consume_searxng.py:22` |
| **`InvestigigationWorkflow.acquire_batch` can never dispatch**: it calls a `db.session.get_session` that does not exist, and passes `investigation_id` where `tenant_id` is expected. | `apps/control-plane/workflows/investigation_activities.py:88,126-134` |
| **Layer 0 (`layer0_pipeline.py` / `acquisition_loop.py`) is dead code** — imported only by tests, no HTTP route, no Temporal registration. Spec 021 FR-172 already ordered its deletion. Its four hook Protocols are the only reused part. | `specs/024-.../wave0-verified-state.md:139-155` |
| **`context_engine/` and `semantic_path/` are test-only** and absent from the wheel `packages` list. `CognitiveLoop` runs entirely on `InMemoryContextStore`. | `apps/control-plane/context_engine/`, `pyproject.toml:6` |

**The only end-to-end path that writes real rows to Postgres today** is
`POST /api/v1/discovery/run` → `frontier_items`
(`apps/control-plane/api/routes/discovery.py:324-335` → `services/frontier.py:235-271`).

### Data layer

| Finding | Evidence |
| --- | --- |
| **Alembic migrations start at `014` with `down_revision = None`.** There are no revisions 001–013, so `alembic upgrade head` on an empty database creates **none** of the ~35 pre-014 tables (`investigations`, `frontier_items`, `entities`, …). Those exist only via `create_all()`. The parity test **skips silently** when Postgres is unreachable, so the gap is invisible in CI. | `db/migrations/versions/014_temporal_materialization.py:9-10`; `db/session.py:34-41`; `tests/integration/test_orm_migration_parity.py:112-114` |
| **All `downgrade()` implementations raise `NotImplementedError`** — forward-only by design. | all 7 revisions |
| **`relation_claim.created_at` NULLability has known ORM/migration drift** since rev 016; the parity test deliberately excludes both tables. | `tests/integration/test_orm_migration_parity.py:58-86` |
| **Redis is declared as the frontier lease store but no Redis client exists.** Leases are Postgres columns. | `services/frontier.py:3`, `.env.example:22` |
| **Search backend is ambiguous.** Compose ships OpenSearch; ADR-0004 names OpenSearch; but `search/mappings.py` and `search/quickwit.py` are Quickwit-targeted and **no Quickwit service exists in compose**. | `apps/projection/search/mappings.py:15,93` |
| **`search/tantivy_backend.py` is a 22-line stub** — docstring and two constants, no class, no methods. The real ranked paths are `search/relevance.py` (stdlib BM25) and `search/bm25s_backend.py`. | `apps/projection/search/tantivy_backend.py` |

### API surface is partly fixture-driven

| Finding | Evidence |
| --- | --- |
| **`GET /api/v1/metrics` returns hard-coded numbers** — `throughput_per_s=142.3`, `useful_observations=1_048_576`, `duplicate_ratio=0.12`. Never measured. A green demo built on it is not real. | `api/routes/metrics.py:37-46` |
| **Investigations live in a module-level dict**, lost on restart and split across uvicorn workers. Creation sets `state=RUNNING` directly, bypassing the state machine. | `api/routes/investigations.py:28,76,82` |
| **The entities API is fixture-seeded** (`ENT-2001`, `OBS-1001`, `CE-200001`) with in-memory streams. | `api/routes/entities.py:39-82` |
| **`GET /api/v1/dlq` reads an in-process `QuarantineStore` seeded with one fake record**, not the `events.dlq` / `events.quarantine` topics that real failures are written to. | `api/routes/quarantine.py:21-25`; `shared/events/topics.py:137-138` |
| **`POST /api/v1/search/rebuild` always rebuilds from an empty bus** — it replays a process-local `MemoryEventBus` that nothing in the control-plane process publishes to. | `api/routes/search_rebuild.py:132`, `services/event_bus.py:44` |
| **7 routers have no auth dependency at all** — 22 endpoints without a `TenantContext`. | `api/routes/{network,science_*}.py` |
| **Auth is a JSON stub, and a missing token grants `Role.ADMIN` on `default-tenant`.** Token is `json.loads`'d, not JWT-verified. This must not reach production. | `api/auth.py:39-69` |

### Duplicated authorities

| Finding | Evidence |
| --- | --- |
| **Two frontiers in one process.** `/api/v1/fabric/frontier/*` drives an in-memory singleton; `/api/v1/discovery/run` writes real Postgres rows. They never see each other. | `routes/fabric.py:83` vs `services/discovery_frontier.py:288` |
| **Two dispatchers in the same app with different semantics** (`services/dispatcher.py` vs `dispatcher/scheduler.py`), plus a third in Rust. None calls the others. Backpressure math and retry budgets are duplicated verbatim across Python and Rust. | `services/dispatcher.py:65-262` vs `dispatcher/scheduler.py:79-205` vs `dispatcher/src/lib.rs` |
| **The Rust dispatcher applies backpressure after popping**; the Python one checks it before popping so leases aren't churned. The Python behaviour is the correct one. | `dispatcher/src/lib.rs:91-104` vs `services/dispatcher.py:108-119` |
| **`ScopeLimits.allows()` always returns `(True, "")`** — stage-B resource limiting is a no-op. | `dispatcher/scheduler.py:58-69` |
| **The dispatcher hard-codes `policies/default` / `budget/default`** regardless of the investigation's tenant. | `services/dispatcher.py:159-166` |

### Event catalog integrity

- **~25 catalogued events have no producer anywhere**: `mention.created`, `candidate.created`,
  `assertion.created`, `admission.decided`, `entity.resolved`, `entity.version_created`,
  `evidence.link_created`, `finding.created`, `graph.projected`, `analytics.projected`,
  `projection.completed`, `discovery.seed`, `discovery.discovered`, `frontier.enqueued`,
  `acquisition.outcome/completed/failed`, `feedback.source/entity/system`, all `cc.*`,
  `science.claim.discarded`, `science.structure.analyzed`, `science.robustness.report`,
  `zero_layer.enrichment`.
- **Two events are emitted but not in the catalog** — `feedback.source_policy` and
  `feedback.defer` raise `UnknownEventTypeError` if routed through `topic_for()`.
- **`science.claim.scope_rejected` is effectively dead** — the scope guard always emits
  `science.causal.scope_rejected`, even when called from `register_claim`.
- `specops.tool_requested` and `cc.temporality` exist only on the SSE hub, not in the catalog.

### Feature 024 bookkeeping

- **`tasks.md` shows 0/168 checked while ~7 phases have real code.** The file's own
  claim of FR coverage (`tasks.md:303`) is therefore unauditable. Run
  `/speckit.converge` before trusting it.
- **`test-baseline.md` contradicts itself**: line 24 declares `123 failed, 2604 passed`;
  line 135 still says `106 failed, 2585 passed`. T006's premise (delta against one
  fixed reference) depends on picking one.
- **9 `EvidenceContext` contract-drift failures were recorded as a Phase-4 blocker**
  and are not recorded as cleared — yet Phase-4 code exists.
- **Phases 8, 9, 10, 11 have essentially nothing**: no `WorldlineSnapshot` type exists
  anywhere; Phase 10 has ADR-0027 but no tables and no migration.
- **`data-model.md`, `research.md`, `quickstart.md` are declared in `plan.md` and do
  not exist** for 024.
- **ADR amendment sweep (T012) not done.**

### Licensing — unresolved hazard

`donors/estorides/` is measured as **AGPL-3.0**. `specs/022-.../repair/LICENCE-ANALYSIS.md:5-9`
states that a qualified human must confirm this reading before any derived code, file
or spec moves into the repository. The 146-source YAML catalogue
(`apps/acquisition/sources/estorides/`) is nevertheless treated as a live,
load-bearing resource by feature 024. **This is an open legal question, not a
technical one, and it is not resolved on paper.**

### Documentation drift in this repo

- `docs/architecture/stream-processing.md:28-29` points Flink and ClickHouse at
  engines not present in this repository.
- `specs/015-worldline-reconstruction/quickstart.md:598` documents
  `python -m services.worker`; the real entry point is `python -m workflows.worker`.
- `apps/deploy/docker-compose.yml:42-82` still ships Confluent Kafka + schema-registry
  under `legacy-kafka` alongside Redpanda in `core`.
- `README.md` still lists 12 specs (22 exist), omits `science`/`zero`/`bulk-ingestion`
  from its app table, and describes `core` as "kafka".
- `apps/shared/contracts/` is missing three docs its code cites:
  `contracts/storage.md`, `contracts/utility-scorer.md`, `contracts/scope-boundary.md`.
- `apps/acquisition/pyproject.toml:6` lists Rust-only dirs as Python packages and
  omits the real `sources` and `runtime` packages — a non-editable install is broken.
