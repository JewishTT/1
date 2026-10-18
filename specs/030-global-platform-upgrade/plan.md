# Implementation Plan: COGNITIVE Global Platform Upgrade

**Branch**: `030-global-platform-upgrade` | **Date**: 2026-10-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/030-global-platform-upgrade/spec.md`

**Prerequisites**: [`research.md`](./research.md) — all `NEEDS CLARIFICATION` markers resolved there.
Every claim below is marked **[MEASURED]** (read from this tree on 2026-10-14), **[DECIDED]** (this
plan's decision, rationale in `research.md §2`) or **[UNVERIFIED]** (carried to `tasks.md` with an ID).

---

## Summary

Turn COGNITIVE from a platform that *documents* an auditable research loop into one that
**demonstrates** it, by finishing the chain
`context → gap → obligation → action → acquisition → observation → interpretation → admission →
invariant/worldline → projections → finding → context revision` and proving it end to end on a
clean stack.

The programme is delivered as **verticals**, each reaching a passing test before the next begins.
The ordering is inherited from feature 029's own execution order and its measured findings, and is
not re-invented here: the gate and span defects that 029 identified are still open, and the 029 donor
matrix explicitly defers every document/linkage donor until they close.

**Three things this plan does that the specification did not ask for, because measurement demanded
them:**

1. It treats the **empty constitution** (§ Constitution Check) as a WP-1 deliverable rather than an
   assumption.
2. It produces a **retroactive licence disposition** for `giotto-tda`, which is already an AGPL-3.0
   dependency of `apps/projection` and was installed without one.
3. It treats the **live port conflict** (§ Blocking condition) as a WP-0 gate, because without it
   no clean baseline exists and no acceptance claim can be made.

---

## Technical Context

| Field | Value | Source |
|---|---|---|
| **Language/Version** | Python 3.11.9 installed; `requires-python = ">=3.11"` (`apps/acquisition` pins `>=3.11,<3.14`) | `python --version`, `pyproject.toml` |
| **Runtime/PM** | uv 0.12.12, workspace of 10 `apps/*` members + `bench` | `uv --version`, `pyproject.toml:1-14` |
| **Node** | v24.19.0 | `node --version` |
| **Primary Dependencies** | shared: pydantic 2.7 / asyncpg / confluent-kafka / redis / aioboto3 / protobuf / grpc / OTel / prometheus-client. control-plane: fastapi 0.111 / alembic 1.13 / temporalio 1.4 / neo4j 5.21 / clickhouse-connect / orjson. acquisition: certstream / pyarrow 25 / scrapy 2.19 / warcio. interpretation: pypdf / python-docx / openpyxl / trafilatura / selectolax / extruct / rapidfuzz / simplemma / jieba / fugashi. admission: numpy / scipy. projection: **bm25s 0.2 / duckdb 1.0 / gudhi 3.10 / giotto-tda 0.6.1 (AGPL)** / numpy / scipy. feedback, science: numpy. | per-member `pyproject.toml` |
| **Storage** | PostgreSQL (asyncpg + Alembic, migrations at `apps/control-plane/db/migrations/versions`, latest `015_worldline_reconstruction`), Kafka-compatible (confluent-kafka + schema registry), Redis, OpenSearch, ClickHouse, Neo4j (driver declared, **no config variable**), Temporal, S3-compatible (aioboto3), Vault | `pyproject.toml`, `.env.example` |
| **Testing** | pytest; `testpaths=["apps"]`; `norecursedirs` excludes `donors`/`tmp`/`logs`; markers `contract`/`integration`/`live`/`unit`; **`asyncio_mode = "auto"`**; **`addopts = --import-mode=importlib"`**; `bench` runs from its own workspace member | `pyproject.toml:23-88` |
| **Lint/format** | `ruff.toml` + `.pre-commit-config.yaml` | file listing |
| **Target Platform** | Linux server / Docker Compose; Windows dev host | this machine |
| **Project Type** | Multi-service platform: API + worker fleet + SPA, 10-member uv workspace | workspace layout |
| **Performance Goals** | **Deliberately unset** — per spec §18.5 thresholds follow the baseline. Latency/resource budget is recorded p50/p95, never asserted as a universal SLA. | spec §18.5 |
| **Constraints** | Raw evidence immutable; every derived artifact reproducible; no fabricated metrics; safety/provenance/identity gates are non-tradeable against throughput; unknown ≠ absent; contradiction persists | spec §2, §26.2 |
| **Scale/Scope** | **[UNVERIFIED]** — no authoritative figure exists. `WP0-03` measures corpus, tenants, event volume and graph cardinality before any capacity claim. | research §1.5 |

### Hard constraints this plan inherits from `pyproject.toml`

These are load-bearing and were each the cause of a measured, silent test failure. New code must
not fight them:

- **`asyncio_mode = "auto"`** — without it, 71 context-engine tests fail *only* when run from the
  repo-root config and pass from the member config.
- **`--import-mode=importlib`** — six sibling packages named `contract` and two named `integration`
  collapse under the default `prepend` mode, hiding 98 passing tests including the three
  transport-critical ones.
- **`testpaths = ["apps"]`** — without it, bare `pytest -q` collects 6769 tests with **831 collection
  errors**, every one from a vendored checkout under `donors/`.
- **`bench` must not share a collection root with `apps`** — collected together they fail with
  `ImportError: cannot import name 'harness' from 'bench'`.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

### Gate status: **PASS WITH ONE FINDING**

**[MEASURED]** `.specify/memory/constitution.md` is **50 lines of unfilled template**. Every
placeholder survives verbatim — `[PRINCIPLE_1_NAME]`, `[PRINCIPLE_1_DESCRIPTION]`,
`[SECTION_2_CONTENT]`, `[GOVERNANCE_RULES]`, `[CONSTITUTION_VERSION] | [RATIFICATION_DATE]`.
**There is no ratified constitution for this project.**

`AGENTS.md` exists but is an *assistant operating specification*: role, capabilities, values,
content/safety policy, refusal handling, tool-use conduct, response style, session conduct. It
governs how the agent behaves. It is **not** a software constitution and contains no engineering
principle, gate or quality bar for the platform.

**Decision [DECIDED]**: the Constitution Check is executed against the principles the two source
specifications state normatively, and **filling the constitution becomes a WP-1 deliverable**
(`T0100`). A programme of this size proceeding against an empty constitution is a governance
defect; it is reported, not silently passed.

### Principles enforced (from the source specifications)

| # | Principle | How this plan complies | Gate |
|---|---|---|---|
| P1 | **Immutable evidence substrate** | No task may write to or mutate a raw object. FR-001–003, FR-092, SC-005. Byte-digest comparison before/after every scenario. | Zero digest changes |
| P2 | **Evidence-first derivation** | FR-004–006. Span semantics fixed at the producer (`extractors/lane.py:82-86`) before any consumer is trusted. | SC-004 |
| P3 | **Identity is a resolution decision** | FR-080–084. No score, centrality, topology or model output commits a merge. | SC-009 |
| P4 | **Open-world semantics** | FR-013. Unknown predicates survive storage, projection and UI. | SC-003 |
| P5 | **No scalar truth** | FR-016. Component vectors retained; composites carry a policy version. | FR-016 tests |
| P6 | **Epistemic discipline** | FR-010–012, FR-014–015. 13 states preserved; four-valued support; qualified absence only with declared detection power. | SC-003 |
| P7 | **Temporal semantics** | FR-020–025. Eight typed clocks; `CURRENT`/`AS_OF`/`INTERVAL` are three distinct dimensions. | SC-008 |
| P8 | **Process-centric ownership** | FR-030–049. Five responsibilities already separated in `engine.py` **[MEASURED]**: `ObligationGenerator`, `SatisfactionEvaluator`, `ActionProposer`, `DecisionRecorder`, `RevisionManager`. Plan preserves and extends; does not re-implement. | FR-037 |
| P9 | **Projection rebuildability** | FR-070–079. Every projection declares offsets, snapshot digest, builder version, staleness and kill switch. | SC-006 |
| P10 | **Determinism at declared boundaries** | FR-036, §2.10. Two replay modes; `InvariantReducer.restore(stream, history=)` is the existing mechanism and must not regress. | SC-006 |
| P11 | **Hard constraints outrank utility** | FR-043. Filters run before ranking; exclusions are recorded with reasons. | FR-043 tests |
| P12 | **Cost-aware process** | FR-042, §2.14. Cost is a vector; the composite is policy-derived and versioned. | SC-011 |
| P13 | **Donor reuse with boundaries** | FR-110–115. Pinned revision, licence + asset inventory, real production call site, benchmark, kill switch. | SC-014 |
| P14 | **Security / acceptable acquisition** | FR-090–096. Egress, tenant isolation, untrusted content, no access-control bypass. | §G8 |
| P15 | **Truthful reporting** | FR-100–103. Pass/fail/blocked/not-run. No fabricated metric. Blocked ≠ pass. | SC-015, SC-016, SC-017 |

### Post-design re-evaluation

Re-run after Phase 1. Result recorded in §Post-design Check below.

---

## Project Structure

### Documentation (this feature)

```text
specs/030-global-platform-upgrade/
├── spec.md                 # normative requirements (7 stories, 115 FRs, 17 SCs)
├── plan.md                 # this file
├── research.md             # Phase 0 — decisions + measured baseline
├── data-model.md           # Phase 1 — entities, states, transitions
├── quickstart.md           # Phase 1 — runnable validation, measured
├── current-state-audit.md  # WP0 deliverable — verified implementation matrix
├── donor-matrix.md         # WP0 deliverable — extends 029's verified matrix
├── benchmarks/             # WP0+ — measured artifacts, versioned
├── contracts/
│   ├── README.md           # contract index + versioning policy
│   ├── operator-result.md  # unified operator envelope (FR-007)
│   ├── evidence-span.md    # span selectors (FR-004, FR-006)
│   ├── stage-outcome.md    # 9 typed stage outcomes (FR-047)
│   ├── obligation.md       # obligation/action/attempt/decision (FR-038, FR-042)
│   ├── projection-manifest.md
│   ├── context-revision.md # revision + decision atomicity (FR-032, §2.1)
│   └── errors.md           # stable machine-readable codes
└── tasks.md                # Phase 2 — /speckit.tasks, NOT created here
```

### Source Code (repository root)

**[MEASURED]** — verified against the executing tree. `apps/control-plane/context_engine/` contains
exactly: `engine.py` (38 KB), `loop.py` (32 KB), `enrichment_service.py` (29 KB),
`postgres_store.py` (26 KB), `context_graph.py` (23 KB), `obligations.py` (20 KB),
`invariant_reducer.py` (17 KB), `fabric_store.py` (16 KB), `context_graph_store.py` (13 KB),
`dossier_store.py` (13 KB), `return_path.py` (10 KB), `catalogue_bridge.py` (9 KB),
`query_cycle.py` (9 KB), `fabric_runner.py` (8 KB), `store.py` (8 KB), `fabric_bridge.py` (8 KB),
`science_bridge.py` (6 KB), `worldline.py` (3 KB), `__init__.py`.

```text
1/                                   # git root (HEAD 608c3ad8…, branch main)
├── apps/
│   ├── shared/
│   │   ├── domain/                  # graph_invariant.py, investigation_context.py, temporal models
│   │   ├── events/                  # dlq.py, dlq_durable.py, topics.py, idempotent_consumer
│   │   ├── isolation.py             # existing isolation control — retention policy target
│   │   ├── contracts/               # shared contract primitives
│   │   ├── storage/                 # raw/evidence store adapters
│   │   └── observability/           # OTel + Prometheus
│   ├── control-plane/
│   │   ├── context_engine/          # ← THE KERNEL. 19 modules, listed above.
│   │   │                            #   engine.py   loop.py   obligations.py   query_cycle.py
│   │   │                            #   return_path.py  store.py  postgres_store.py
│   │   │                            #   context_graph.py  context_graph_store.py
│   │   │                            #   invariant_reducer.py  worldline.py
│   │   │                            #   fabric_runner.py  fabric_store.py  fabric_bridge.py
│   │   │                            #   science_bridge.py  catalogue_bridge.py  dossier_store.py
│   │   ├── db/
│   │   │   ├── schema.py            # ORM
│   │   │   ├── materialization_outbox.py   # ← EXISTING outbox (§2.2)
│   │   │   └── migrations/versions/        # Alembic; latest 015_worldline_reconstruction
│   │   ├── services/                # materialization_outbox_relay.py, temporal_materialization_dispatch.py, throttle.py
│   │   ├── api/routes/quarantine.py # ← existing DLQ surface
│   │   └── workflows/worker.py
│   ├── acquisition/
│   │   ├── adapters/browsertrix/collect.py   # existing AGPL adapter — harden, don't duplicate
│   │   ├── registry.py  worker_acquisition.py  source_query_set.py  frontier/  discovery/
│   ├── interpretation/              # parsers/registry.py, extractors/lane.py ← SPAN DEFECT
│   ├── admission/resolution/        # resolution contracts + decision store
│   ├── projection/
│   │   ├── search/                  # bm25s baseline; no vector dep exists
│   │   ├── graph/  metrics/         # temporal_paths.py — temporal donor comparison baseline
│   │   └── tda/                     # gudhi + giotto-tda ← OWNERSHIP UNRESOLVED (U-01/U-02)
│   ├── feedback/                    # frontier, stopping, review branches
│   ├── science/context/             # 21 pure modules: fabric, epistemic, lattice, locality,
│   │                                # hierarchy, circularity, coverage, completeness, dialectics,
│   │                                # query_ast, query_binding, query_grammar, argumentation,
│   │                                # natural_language, semantic_graph, dossier, worldline
│   ├── zero/zero/resolution/fellegi_sunter.py   # current matcher baseline
│   └── bulk-ingestion/  deploy/     # deploy holds ONE compose file: deploy/specops/lab/
├── bench/                           # own workspace member; MUST NOT share a collection root with apps/
│   ├── run.py  harness.py  quality.py
│   ├── fixtures/  scenarios/  reports/
├── donors/                          # 40+ vendored checkouts; registry.yaml ABSENT → create
├── docs/
│   ├── adr/                         # 39 files; this feature writes ADR-030-01..11
│   └── architecture/donors/         # 00-INDEX.md … 10-ZERO-LAYER.md (11 catalogues)
├── specs/001..029/                  # occupied; 029 carries the donor matrix + audit
├── deploy/specops/lab/docker-compose.yml    # the ONLY compose file
├── .env.example                     # 17 service variables
├── pyproject.toml  ruff.toml  uv.lock  conftest.py
└── .specify/memory/constitution.md  # ← UNFILLED TEMPLATE (P-gate finding)
```

**Structure Decision**: extend the existing 10-member uv workspace in place. **No new package, no
new service, no second context engine, no second identity authority.** The kernel stays at
`apps/control-plane/context_engine/`; pure reasoning stays at `apps/science/context/` with the
existing one-way dependency (science must not import control-plane internals). New code lands
*beside* existing modules of the same responsibility, never as a parallel tree — which is why the
specification's own warning applies: a second `apps/context-engine/` would be created purely because
the term is prominent in the spec.

---

## Work package sequence

Each vertical reaches a passing test before the next. Inherited from 029's execution order and
extended. `tasks.md` carries the granular breakdown.

| WP | Name | Gate to exit | Depends on |
|---|---|---|---|
| **WP0** | Truthful baseline | Audit published; every capability classified with real callers, persistence, tests; donors inventoried; **port conflict resolved or reported blocked** | — |
| **WP1** | Governance + ADRs | Constitution filled; ADR-030-01…11 written from the audit | WP0 |
| **WP2** | Contracts | `OperatorResult`, `EvidenceSpanRef`, stage outcomes, canonical digest/fingerprint | WP1 |
| **WP3** | Invariant & worldline integrity | Accumulated-stream reduction in production; revision on digest change only; `supersedes` chain durable; restart + late-evidence + redelivery tests | WP2 |
| **WP4** | Gate + identity | One admission gate; uncalibrated thresholds cannot merge; evidence dependency counted by lineage root | WP3 |
| **WP5** | Spans to the finding | `Segment.offset` semantic split at the producer; span survives into `ResolutionMention`; Finding → page/span | WP4 |
| **WP6** | Operator envelope | Unified result envelope; adapters cannot write canonical stores | WP5 |
| **WP7** | Projections that are real | Manifests; rebuild reproduces digests; features persisted **and consumed** | WP6 |
| **WP8** | Open world & absence algebra | 13 epistemic states round-trip; qualified absence gated on detection power | WP7 |
| **WP9** | Retrieval & frontier economics | BM25/fusion benchmark on a frozen judged set; action utility; suppression | WP8 |
| **WP10** | Closed loop E2E | ≥2 iterations; new observation changes the next action; explicit stop reason | WP9 |
| **WP11** | Donor verticals | Only after WP8–WP10 hold — the 029 matrix's own deferral condition | WP10 |
| **WP12** | Operations, security, rollout | Budgets, egress, backpressure, DLQ, SBOM, migration/rollback, final report | WP11 |

**Why WP4 precedes WP5**: spans are worthless while identity and the gate are unsound. This is
029's recorded reasoning and it still holds.

**Why donor verticals are WP11, not earlier**: the 029 donor matrix says, verbatim, that Docling,
GROBID, Splink, Redpanda Connect, H3, DuckDB Spatial, OpenAleph and Browsertrix are "individually
sound" but "none should receive data while the gate and identity defects stand". Scheduling them
earlier would violate the source specification's own ordering.

---

## Blocking condition

**[MEASURED]** TCP `localhost:5432` and `localhost:9000` are **OPEN**, owned by **pid 12640
`com.docker.backend`**, while `docker ps` returns **empty**. Feature 029 recorded the identical
condition on 2026-10-13 and measured its effect: ~13 PostgreSQL/object-store tests flip from
*skipped* to *failing* on handshake timeout, and two acquisition integration modules **hang**
rather than skip.

**This is not a code regression.** It is why the last honest full-suite baseline is
`22 failed, 4288 passed, 27 skipped`.

WP0 must resolve it (identify and release the Docker publication, or point the suite at a working
instance). If unresolved, WP0 reports every affected test as **blocked**, and any downstream gate
requiring them is reported **blocked**, never passed. No acceptance criterion is evaluated against a
run that did not execute.

---

## Complexity Tracking

> Filled because the Constitution Check produced a finding that requires justification.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| **Proceeding without a ratified constitution** | `.specify/memory/constitution.md` is an unfilled template; no engineering principle is ratified anywhere in the repo. `AGENTS.md` governs agent behaviour, not the platform. | Stopping the programme pending ratification. Rejected: the owner has issued two normative specifications that state the principles normatively (evidence-first, process-centric, relation-centric, immutable evidence, open-world, no scalar truth, hard constraints outrank utility). The principles are ratified by the owner even though the file is empty. **Mitigation**: filling the constitution is `T0100` in WP1, not an assumption — and the Constitution Check above cites the source specifications explicitly rather than citing an empty file. |
| **Scope narrower than the specification requests** (LLM routing not scheduled as a vertical; vector retrieval optional; nine donors dropped) | Measured: no LLM provider dependency, no vector/ANN dependency, and nine named projects do not exist. | Adding the dependencies anyway so the plan matches the specification's wording. Rejected: that is precisely the FR-110 violation the specification exists to prevent — a dependency in `pyproject.toml` is not an integration. Each narrowing is reversible and is recorded in `research.md §7`. |

---

## Post-design Check (Phase 1 re-evaluation)

Re-run after `data-model.md`, `contracts/` and `quickstart.md` were produced.

| Gate | Before design | After design | Note |
|---|---|---|---|
| P1 Immutable evidence | PASS | **PASS** | `evidence-span.md` defines selectors; no contract permits raw-object mutation |
| P2 Evidence-first | FAIL (span defect open) | **FAIL — carried to WP5** | `extractors/lane.py:82-86` is a *code* defect, not a design defect. The contract now makes the required semantics explicit; the producer fix is WP5 |
| P3 Identity | PASS (design) | **PASS** | `ADR-030-03`; Splink deferred to WP11 per §2.6 |
| P4 Open world | PASS | **PASS** | `operator-result.md` carries raw predicate + mapping status |
| P5 No scalar truth | PASS | **PASS** | `obligation.md` requires the component vector |
| P6 Epistemic | PASS | **PASS** | `stage-outcome.md` separates no-result from unsupported from failure |
| P7 Temporal | PASS (design) | **PASS — U-03 open** | `recorded_at` flow is a WP0 runtime check |
| P8 Process-centric | PASS | **PASS** | Five responsibilities preserved; no god object added |
| P9 Rebuildability | PASS | **PASS** | `projection-manifest.md` |
| P10 Determinism | PASS | **PASS** | `operator-result.md` declares both replay modes |
| P11 Hard constraints | PASS | **PASS** | `obligation.md` filters before ranking |
| P12 Cost-aware | PASS | **PASS** | Vector cost, composite policy-versioned |
| P13 Donor boundaries | PASS | **PASS** | giotto-tda disposition added as WP0 deliverable |
| P14 Security | PASS | **PASS** | `errors.md` separates expected-negative from retryable |
| P15 Truthful reporting | PASS | **PASS** | `quickstart.md` records measured output only |

**Result**: 14/15 gates pass by design. **P2 fails by code defect, not by design**, and is the
reason WP5 exists. **P1–P15 cannot be promoted to PASS overall until WP3–WP5 close**, because a
contract that describes correct semantics does not make the producer emit them.

---

## Notes for `/speckit.tasks`

- Do not create `apps/context-engine/`. The kernel is `apps/control-plane/context_engine/`.
- Any new test package named `contract` or `integration` inherits `--import-mode=importlib`; any
  new `async def` test inherits `asyncio_mode = "auto"`.
- `bench` tests run from the `bench` workspace member, never alongside `apps`.
- Task status markers: `[x]` verified implemented, `[~]` partial, `[!]` blocked with a named
  dependency and next action, `[ ]` not executed. A task is `[x]` only with evidence — a code
  reference or a recorded command output — never because code was written.
- `donors/registry.yaml` does not exist. Creating it is a concrete, high-value early task.