# Phase 0 Research: COGNITIVE Global Platform Upgrade

**Feature**: `030-global-platform-upgrade`
**Date**: 2026-10-14
**Input**: `spec.md` (consolidating "Global Platform Upgrade" + "CE-001 Context Engine as Research Process Kernel")

---

## 0. Method, and what this document is allowed to claim

Every entry below is one of three kinds, and the kind is stated:

| Marker | Meaning |
|---|---|
| **[MEASURED]** | Read from this working tree on 2026-10-14 by a command recorded in `quickstart.md §0`. Not a literature claim. |
| **[DECIDED]** | A decision this plan makes, with the evidence that drove it and the alternative rejected. |
| **[UNVERIFIED]** | Cannot be settled without work this plan schedules. Carries a task ID, not a guess. |

No entry is sourced from vendor marketing, published benchmark numbers, or a project README.
Where a donor's own README is the only source, that is called out explicitly.

### 0.1 Verified starting point

**[MEASURED]** `git rev-parse HEAD` → `608c3ad8f4743e4e729807c903b0364ed571b311`
**[MEASURED]** `git branch --show-current` → `main`
**[MEASURED]** `git status --porcelain | Measure-Object -Line` → 147 entries

The revision the two source specifications assert exists. The specification treats that assertion
as unproven; it is now proven for `HEAD`. The 147 dirty entries mean **no acceptance claim may be
made against a clean tree** until WP-0 records which of them are this feature's work.

---

## 1. Technical Context — resolved

### 1.1 Language, runtime, workspace **[MEASURED]**

| Item | Value | How |
|---|---|---|
| Python | 3.11.9 (installed); `requires-python = ">=3.11"` | `python --version`, `pyproject.toml` |
| Package manager | uv 0.12.12, `[tool.uv.workspace]` | `uv --version`, `pyproject.toml:1-14` |
| Node | v24.19.0 | `node --version` |
| Workspace members | `apps/{shared,control-plane,acquisition,bulk-ingestion,interpretation,admission,projection,feedback,science,zero}` + `bench` | `pyproject.toml:2-14` |
| Migrations | `apps/control-plane/db/migrations/versions` (Alembic), latest `015_worldline_reconstruction` | directory listing |

**No `NEEDS CLARIFICATION` remains here.** The one genuine toolchain risk is recorded in §5.

### 1.2 Primary dependencies **[MEASURED]** — per workspace member

| Member | Declared dependencies (abridged) |
|---|---|
| `apps/shared` | pydantic 2.7, pydantic-settings, asyncpg, confluent-kafka, redis, aioboto3, httpx, protobuf, grpcio, grpcio-tools, opentelemetry-sdk, otel-exporter-otlp, prometheus-client, pyahocorasick, charset-normalizer |
| `apps/control-plane` | fastapi 0.111, httpx, alembic 1.13, temporalio 1.4, clickhouse-connect, neo4j 5.21, orjson |
| `apps/acquisition` | certstream, pyarrow 25, scrapy 2.19, warcio 1.8.1 (`requires-python = ">=3.11,<3.14"`) |
| `apps/interpretation` | numpy, trafilatura, selectolax, extruct, phonenumbers, nameparser, pypdf, python-docx, openpyxl, pillow, rapidfuzz, simplemma, jieba, fugashi, unidic-lite |
| `apps/admission` | numpy, scipy |
| `apps/projection` | **bm25s 0.2**, **duckdb 1.0**, **giotto-tda 0.6.1**, **gudhi 3.10**, numpy, scipy |
| `apps/feedback` | numpy |
| `apps/science` | numpy |
| `apps/zero` | cognitive-shared |

Three observations that change the plan:

1. **`giotto-tda` is already a declared dependency of `apps/projection`.** The source specification
   lists giotto-tda as a candidate to be benchmarked against GUDHI. It is already installed.
   The question is therefore not "adopt or not" but "which is the canonical production path" — and
   per §3.7 of the donor matrix, giotto-tda is **AGPL-3.0**. **[DECIDED]** See §2.9.
2. **No vector/ANN dependency exists.** `pgvector` is absent from every member. The "vector retrieval"
   arm of the retrieval benchmark must therefore be scoped as *optional profile*, not baseline.
   **[DECIDED]** See §2.5.
3. **No LLM provider dependency exists.** No `anthropic`, `openai`, `litellm`, `instructor`,
   `tiktoken`. The LLM-routing work package (WP10 in the source spec) has **no substrate** and
   must not be scheduled before an operator-evals contract exists. **[DECIDED]** See §2.8.

### 1.3 Storage **[MEASURED]**

| Store | Declared env var | State |
|---|---|---|
| PostgreSQL | `POSTGRES_HOST/PORT/DB/USER/PASSWORD` | canonical relational store; asyncpg + Alembic |
| Redis | `REDIS_URL` | declared |
| Kafka-compatible | `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_SCHEMA_REGISTRY_URL` | confluent-kafka + protobuf registry |
| OpenSearch | `OPENSEARCH_URL` | declared |
| ClickHouse | `CLICKHOUSE_URL` | clickhouse-connect |
| Neo4j | *(no env var found)* | **neo4j driver declared but no connection variable** — flag for WP-0 |
| Temporal | `TEMPORAL_HOST` | temporalio |
| S3-compatible | *(no env var in the grep window)* | aioboto3 declared; variable name needs WP-0 confirmation |
| Vault | `VAULT_ADDR` | declared |

**[DECIDED]** The authority division in the source specification (§5.1) is adopted **as the target**,
but WP-0 must record the *actual* division before any code is written, because `neo4j` being
declared without a configuration variable is exactly the "client library installed ≠ service
available" failure mode the specification forbids.

### 1.4 Testing **[MEASURED]**

From `pyproject.toml:23-88`, with load-bearing comments already written by feature 029:

- `testpaths = ["apps"]` and `norecursedirs` excluding `donors`, `tmp`, `logs`, `node_modules`.
  The comment records the measured reason: before this line, bare `pytest -q` collected 6769 tests
  with **831 collection errors**, every one from a vendored third-party checkout.
- `markers = ["contract", "integration", "live", "unit"]`.
- `asyncio_mode = "auto"` — the comment records that its absence was silent and produced 71
  context-engine tests failing only when run from the repo-root config.
- `addopts = "--import-mode=importlib"` — six sibling packages named `contract` and two named
  `integration` collapse under the default `prepend` mode, hiding 98 passing tests including the
  three transport-critical modules.
- `bench` is deliberately excluded from `testpaths` and must run from its own workspace member.

**This is a constraint on this feature, not a detail.** Any new test directory named `contract` or
`integration` inherits the `importlib` requirement; any new async test requires `asyncio_mode = auto`.

Baseline last recorded by feature 029 (2026-10-13): `22 failed, 4288 passed, 27 skipped`, ~19 min;
collection `4336 tests, 0 errors`. **[UNVERIFIED]** for this feature — must be re-run under WP-0.

### 1.5 Target platform, project type, scale

| Item | Value |
|---|---|
| Target platform | Linux server / Docker Compose profiles; Windows dev host **[MEASURED]** (this machine) |
| Project type | Multi-service web-service + worker fleet + SPA; uv workspace of 10 members |
| Performance goals | **Deliberately unset.** Per spec §18.5, numeric thresholds follow the baseline. Measured in §5 below, not invented. |
| Constraints | Immutability of raw evidence; reproducibility of every derived artifact; no fabricated metrics; safety/provenance/identity gates are non-negotiable and are not tradeable for throughput |
| Scale/Scope | **[UNVERIFIED]** — no authoritative figure exists in the repo. WP-0 measures corpus size, tenant count, event volume and graph cardinality before any capacity claim is made. |

---

## 2. Architecture decisions

The source specifications require ADRs for 14 questions. The repo has **39 files** in `docs/adr/`
**[MEASURED]** — many may already cover some. Each decision below names the ADR to write.

### 2.1 Is ContextGraph authoritative durable state? **[DECIDED]**

**Decision**: `ContextGraph` is **authoritative durable state for research-process relationships
only**, backed by `PostgresContextGraphStore` **[MEASURED]** `context_graph_store.py:74`, whose
`apply(tenant_id, transaction) -> DecisionRecord` signature **[MEASURED]** already makes the
decision record and the graph mutation one transaction. It is **not** authoritative for
real-world entity relations, which live in the canonical entity/claim stream and are projected
into a rebuildable graph view.

**Evidence**: `PostgresContextGraphStore.apply()` takes an explicit `transaction` and returns the
`DecisionRecord` it wrote. That is CE-001 §13.5 ("revision update and DecisionRecord MUST be
atomic") already satisfied at the storage layer.

**Rejected**: replacing ContextGraph with normalized tables. Reason: the atomicity, decision-record
coupling and history semantics the specification demands are already implemented here; a rewrite
would destroy working, tested behaviour to reach a shape that is not demonstrably better.

**ADR**: `ADR-030-01`.

### 2.2 Canonical transaction boundary for Observation + membership + publication **[DECIDED]**

**Decision**: transactional outbox, reusing what already exists.

**Evidence [MEASURED]**: an outbox already exists and is not hypothetical —
`apps/control-plane/db/materialization_outbox.py`, `services/materialization_outbox_relay.py`,
`services/temporal_materialization_dispatch.py`, and migrations
`014_temporal_materialization.py` / `015_worldline_reconstruction.py`. A DLQ exists:
`apps/shared/events/dlq.py`, `dlq_durable.py`, with `apps/control-plane/api/routes/quarantine.py`
and `tests/integration/test_quarantine.py`. Idempotent consumers exist:
`apps/shared/tests/unit/test_idempotent_consumer.py`.

**Rejected**: inventing a second consistency mechanism. The gap is not the mechanism — it is that
*observation placement* is not yet routed through the one that exists. WP-C of 029 and WP-4 of 030
are the same work; 030 absorbs it.

**ADR**: `ADR-030-02`.

### 2.3 Identity model supporting merge/split **[DECIDED]**

**Decision**: identity is a resolution decision; merge and split are **append-only decisions that
supersede, never rewrite**. Every claim records the identity interpretation it was written under.

**Evidence**: feature 029 WP-E is recorded as **closed** — "a merge can no longer be decided by a
threshold whose own profile declares itself uncalibrated, and corroboration counts lineage roots
rather than hostnames, with the measure used named on every decision" (`specs/029-.../tasks.md`,
WP-E section).

**Consequence**: Splink (§2.6) is a **proposer**, never a writer. This is FR-081.

**ADR**: `ADR-030-03`.

### 2.4 Bitemporal representation **[DECIDED]**

**Decision**: split every timestamp into typed fields (`source_published_at`,
`source_valid_from/until`, `source_observed_at`, `captured/fetched_at`, `recorded/known_at`,
`processed_at`, `projected_at`) and expose `CURRENT` / `AS_OF(known-time)` / `INTERVAL(valid-time)`
as three distinct query dimensions that cannot be aliased onto one another.

**Open defect carried forward [MEASURED]**: the 029 ledger item "Verify current exact time
semantics and whether `recorded_at` flows beyond migration/table" is still `[ ]`. `recorded_at` is
**not yet proven to flow past the migration into the ORM and the query layer**. This is WP-0's
first correctness finding, and it is a prerequisite for SC-008.

**ADR**: `ADR-030-04`.

### 2.5 Which retrieval fusion policy is the default? **[DECIDED]**

**Decision**: the **existing** lexical path is the default. RRF is implemented clean-room as the
*first comparison candidate*, not assumed correct. Vector retrieval is an **optional profile**,
because no vector dependency exists in the workspace (§1.2, point 2).

**Evidence [MEASURED]**: `bm25s>=0.2` and `duckdb>=1.0` are declared in `apps/projection`. There is
no `pgvector`, no ANN library, no embedding model runtime.

**Rejected**: making RRF the default fusion. The specification explicitly forbids it
("RRF is a valid fusion candidate, not a hard-coded universal truth"), and shipping a default
before the frozen judged query set exists would be exactly the "no baseline, no claim" violation.

**Rejected**: adding a vector stack now. That is new runtime, new dependency, new licence and new
operational burden before a baseline exists — forbidden by FR-110.

**ADR**: `ADR-030-05`.

### 2.6 Canonical matcher per workload profile **[DECIDED — deferred with a gate]**

**Decision**: the **existing** matcher remains canonical. Splink is admitted as a **benchmark-only
adapter** behind the same resolution contract, compared on a frozen labelled pair corpus.

**Rationale**: the specification's own donor matrix marks Splink **DEFERRED — after contracts hold**.
Its own words: "All are individually sound. None should receive data while the gate and identity
defects stand." The gate defect (029 WP-C) and the span defect (029 WP-F) are open. Scheduling
Splink before them would violate the source specification's own ordering.

**ADR**: `ADR-030-06`.

### 2.7 Which graph/TDA/temporal operation has which owner? **[DECIDED — mapping deferred to audit]**

**Decision**: exactly one production owner per operation, named in an ADR. The *principle* is
decided here; the *table* is a WP-0 output because the specification forbids naming owners for
code the audit has not yet traced.

**Evidence [MEASURED]**: the specification's own warning applies directly — three TDA trees exist
(`apps/projection/tda/`, `apps/science/scitda/`, `GraphInvariant.to_tda_input`) and both GUDHI
**and giotto-tda** are installed. Which is canonical, and whether either is *called*, is unproven.
Finding a function that exists is not finding a production path.

**ADR**: `ADR-030-07`, filled from the audit table.

### 2.8 What may update ranking policy? **[DECIDED]**

**Decision**: only the **deterministic policy core** may decide. Learned/adaptive components may
*propose a reordering*; the proposal is recorded, the deterministic core validates the hard
constraints, and the applied policy version is stored with its inputs. There is **no substrate for
any of this yet** (§1.2, point 3).

**Consequence**: the LLM work package is **not scheduled as a vertical** in this feature. It is
scheduled as: (a) an operator-evals contract, (b) a deterministic-routing baseline, and (c) only
then an optional provider profile behind a feature flag. This is a deliberate narrowing of the
source specification's WP10, justified by the measured absence of any provider dependency.

**ADR**: `ADR-030-08`.

### 2.9 Licensing and deployment policy for copyleft **[DECIDED]**

**Decision**: copyleft is permitted. AGPL/GPL components are admitted as **separately deployed
executables or sidecars behind a versioned contract**, with the deployment model recorded. Process
separation is explicitly *not* treated as a legal conclusion.

**Evidence [MEASURED]**: `giotto-tda` is **AGPL-3.0** and is *already a declared dependency of
`apps/projection`*; Raphtory is GPL-3.0; Browsertrix is AGPL-3.0-or-later; Phoenix is Elastic
License 2.0 (source-available, not OSI). The 029 donor matrix reached the same conclusion and
requires "a documented deployment/compliance design for AGPL — not a blocker, but a decision, not a
default."

**Immediate consequence [DECIDED]**: because giotto-tda is already installed, this feature must
produce a **retroactive licence disposition** for it — keep as canonical, or isolate as a sidecar,
or remove — before any further TDA work. That disposition is a WP-0 deliverable, not a later task.

**ADR**: `ADR-030-09`.

### 2.10 When is deterministic recomputation possible? **[DECIDED]**

**Decision**: two declared replay modes, and every operator declares which it is.

- **`deterministic`** — pure function of fingerprinted inputs; replay recomputes and the output
  digest must match.
- **`result-replay`** — model-hosted or otherwise non-deterministic; the exact returned result is
  preserved with its inputs and the replay mode is stated as result replay.

**Evidence [MEASURED]**: `InvariantReducer` already implements the hard part — `restore(stream,
history=)` rebuilds *at the recorded position*. Feature 029 recorded the property that forced it:
the reducer advances its revision counter once per `reduce()` call, not once per event, so a cold
fold of a three-event stream lands at revision 1 while an incremental fold reaches revision 3, and
because the revision is inside the invariant identity **the two produce different digests over
identical evidence**. `test_a_cold_fold_is_not_equivalent_to_a_restore` pins this.

**This is the single most important existing behaviour in the repo and must not be regressed.**

**ADR**: `ADR-030-10`.

### 2.11 What defines qualified saturation? **[DECIDED]**

**Decision**: saturation is a *profile-scoped, evidence-backed* verdict that requires all of:
declared source universe, declared detection power, effective **independent** evidence counted by
lineage root (not hostname, not document count), and a marginal-gain threshold. Absent a declared
detection power, zero results is `SEARCHED_NO_RESULT / INFORMATIONAL_ONLY` — never absence.

**Rejected**: saturation inferred from an empty queue, exhausted retries, task count, or low model
confidence. All four are named prohibitions in the specification.

### 2.12 What is retained under retention/erasure? **[DECIDED — policy deferred]**

**Decision**: the *policy* is a deliverable, not a constant. Raw objects, derived artifacts,
decision records and audit entries have **different** retention classes. Referential tombstones
preserve lineage when content is lawfully deleted; redaction of derived projections must not break
provenance. No raw text in logs or decision records.

**Evidence**: `apps/shared/isolation.py` exists **[MEASURED]**; a policy file must be located in
WP-0 before this decision can be finalised.

**ADR**: `ADR-030-11` (written after the policy audit, not before).

### 2.13 Which metrics are authoritative? **[DECIDED]**

**Decision**: a metric is authoritative only if a recorded command produced it. The final report
classifies every test as **pass / fail / blocked / not-run**. Unavailable services are reported as
**blocked**, never as passing. Unmeasured values surface as null with the missing instrumentation
named.

**This is a zero-tolerance gate, not a guideline.** Fabricated KPIs are a release blocker.

### 2.14 Cost unit **[DECIDED]**

**Decision**: cost is a **vector** — network IO, CPU/GPU, memory, parser/model execution, LLM
tokens, latency, storage (raw + projections), retries, operator time, expected human review,
licensing and maintenance. A composite score may be produced by a **versioned policy**, and the
component vector is retained with it. No single scalar is ever the stored truth.

---

## 3. Donor strategy — carried forward, not re-researched

The donor matrix at `specs/029-research-closed-loop-upgrade/donors/donor-matrix.md` (2026-10-13,
verified via GitHub REST API, raw licence files, HuggingFace API) **[MEASURED]** already resolved
45 candidate names. Re-verifying them from scratch would be waste. 030 **extends** that matrix.

### 3.1 Verified verdicts carried forward

| Verdict | Donors | Consequence for 030 |
|---|---|---|
| **REJECT — no such project** | ranknexus, fuse, QUANTA, IntelShed, worker-browser, Stablerank, OptLLM, lcc, nax | Not integrable on the name given. Nothing may be added as a dependency. |
| **BLOCKED — needs URL** | WebFind, Ontograph, grounded-context, vincio | Await a canonical URL from the owner. |
| **BLOCKED — licence** | Common Crawl data | Indemnity clause over the platform's own use case. |
| **BLOCKED — no grant** | RCL | No LICENSE file = all rights reserved. Methodology-only at most. |
| **METHODOLOGY ONLY** | Microsoft GraphRAG, FrugalGPT, RouteLLM, AutoMix (if confirmed), OpenCTI, Timesketch | Patterns to study; generated summaries are **not** evidence. |
| **DEFERRED — after contracts hold** | Docling, GROBID, Splink, Redpanda Connect, H3, DuckDB Spatial, OpenAleph, Browsertrix | Individually sound. None receives data while the gate and identity defects stand. |
| **Verified with blocker** | Docling (MIT code, models separate — one model repo returned HTTP 401), dedupe (MIT, ~14 months stale), giotto-tda (**AGPL-3.0**, ~16 months stale), Raphtory (GPL-3.0), RCL (no licence), Common Crawl, Phoenix (**Elastic 2.0**), TorchGeo (MIT code, per-dataset terms unenumerated), OpenSanctions (MIT code, data separately licensed) | Each needs a disposition before use. |

### 3.2 The nine that do not resolve

This is the most consequential finding in the donor work, and it is a **scope reduction, not a
detail**. Nine of the retrieval/context/automation candidates named in the source specifications do
not exist as described. Consequences:

- The retrieval work package loses its named fusion donors and must be built clean-room from the
  algorithm, labelled honestly as `clean-room-inspired` — **not** called donor code.
- The context-assembly work package loses `lcc` and `nax`; deterministic packing becomes owned code.
- The routing work package loses `OptLLM` outright.

### 3.3 Internal donor catalogue **[MEASURED]**

`donors/` holds **40+ vendored third-party checkouts** (ABa-KiTo, adversarygraph, caldera,
email2phonenumber, estorides, gitsnitch, …) and `docs/architecture/donors/` holds
`00-INDEX.md` … `10-ZERO-LAYER.md`. `donors/registry.yaml` **does not exist** **[MEASURED]**.

**[DECIDED]** This feature creates `donors/registry.yaml` as the single machine-readable registry
and reconciles the 11 existing markdown catalogues into it. Per FR-115, wiring or repairing an
existing useful internal capability is preferred over adding a second implementation of it.

### 3.4 Supply-chain file to create

**[MEASURED]** `donors/registry.yaml` — absent. This is the single most concrete deliverable in the
donor track: it is required by FR-113 and by every §G4 gate.

---

## 4. Structural defects already found

**[MEASURED]** From the 029 audit and ledger, carried forward as WP-0 verification targets:

| Defect | Location | Consequence |
|---|---|---|
| `Segment.offset` is byte offset in one parser, segment index in another, and always `0` in a third — all three summed into one field | `extractors/lane.py:82-86` | FR-006 is violated at the producer side. Spans are not trustworthy, which is why 029 WP-F is still open. |
| `document_adapter.py:271-300` consumes the span to mint `mention_id` then discards it | `apps/interpretation/…/document_adapter.py` | The span that grounds a mention is destroyed. |
| `ResolutionMention` has no span field at all | admission/resolution | Identity candidates cannot be shown to an analyst with evidence. |
| Revision counter advances per `reduce()` call, not per event | `invariant_reducer.py` | Documented property; `restore(stream, history=)` is the mitigation. Must not regress. |
| `neo4j` driver declared with no configuration variable | `apps/control-plane/pyproject.toml` | The "library installed ≠ service available" failure mode. |

These are **inputs to the audit**, not accepted findings for this feature. WP-0 re-verifies each
against the executing commit and records line numbers.

---

## 5. The blocking environment condition **[MEASURED] — carried forward, still live**

Recorded by feature 029 on 2026-10-13 and **re-measured today, unchanged**:

| Probe | Result |
|---|---|
| TCP `localhost:5432` | **OPEN** |
| TCP `localhost:9000` | **OPEN** |
| TCP `localhost:8123` (ClickHouse) | connection refused |
| TCP `localhost:6379` (Redis) | OPEN |
| Owning process for 5432 and 9000 | **pid 12640 `com.docker.backend`** |
| `docker ps` | **empty — no running containers** |

**Diagnosis [DECIDED]**: Docker's backend is holding published host ports 5432 and 9000 while
reporting no containers. Either a container exited without releasing its publication, or the
backend is proxying to something outside this workspace.

**Consequence**: PostgreSQL- and object-store-backed tests cannot reach a clean baseline. Per
feature 029's own measurement this flips ~13 tests from *skipped* to *failing* on handshake
timeout, and makes two acquisition integration modules **hang** rather than skip.

**This is not a code regression and must not be read as one.** It is the documented reason the
last honest full-suite baseline is `22 failed, 4288 passed, 27 skipped`.

**Consequence for this plan**: WP-0 **cannot declare a green baseline** until this is resolved. It
has a bounded, mechanical unblock: identify the Docker publication and release it, or point the
suite at a working instance. If unresolved, WP-0 reports every affected test as **blocked**, and
every downstream gate that needs them is reported as blocked rather than passed.

---

## 6. Constitution status — a real finding

**[MEASURED]** `.specify/memory/constitution.md` is **50 lines of unfilled template**. Every
placeholder survives verbatim:

```
### [PRINCIPLE_1_NAME]        [PRINCIPLE_1_DESCRIPTION]
## [SECTION_2_NAME]           [SECTION_2_CONTENT]
**Version**: [CONSTITUTION_VERSION] | **Ratified**: [RATIFICATION_DATE]
```

There is no ratified constitution. `AGENTS.md` is an *assistant operating specification*, not a
software constitution — it governs how the agent behaves, not how the platform is built.

**Consequence [DECIDED]**: the Constitution Check in `plan.md` cannot cite a document that does not
exist. The honest move is to check against the **semantic principles restated by the two source
specifications** — evidence-first, process-centric, relation-centric, immutable evidence, separate
scores, open-world semantics, epistemic discipline, no scalar truth, hard constraints outrank
utility — and to make **filling the constitution a WP-1 deliverable**, not an assumption.

This is flagged rather than silently passed. A programme of this size proceeding against an empty
constitution is a governance defect, not a paperwork detail.

---

## 7. Scope narrowing this plan applies, and why

Three places where this plan delivers **less** than the source specifications request, with reasons:

| Narrowing | Reason | Evidence |
|---|---|---|
| LLM routing/evaluation is not a scheduled vertical | No provider dependency, no token accounting, no eval harness substrate exists in any workspace member | §1.2 measured dependency lists |
| Vector/ANN retrieval is an optional profile, not a baseline arm | No vector dependency exists; adding one before a baseline violates FR-110 | §1.2 |
| Nine named donor integrations are dropped | They do not exist as projects | 029 donor matrix §1 |

Each narrowing is reversible and is recorded as such. None of them weakens an acceptance criterion
in `spec.md` — SC-011/SC-012 measure *the platform's* evidence yield, not a named library's presence.

---

## 8. Unresolved items carried to tasks, not guessed

| ID | Question | Why it cannot be resolved now | Scheduled as |
|---|---|---|---|
| U-01 | Which operation has which production owner (graph / TDA / temporal)? | Requires tracing real callers; the specification forbids naming owners for untraced code | WP0-04 |
| U-02 | Is giotto-tda canonical, isolated, or removed? | Requires the caller trace plus a licence disposition | WP0-04, WP1 |
| U-03 | Does `recorded_at` flow past migration into ORM and query? | Requires runtime verification, not reading | WP0-06 |
| U-04 | Is there a second authority for any field? | Requires a store-by-store ownership map | WP0-05 |
| U-05 | What are the real scale figures? | Nobody has measured them; inventing them is forbidden | WP0-03 |
| U-06 | Where is the retention/erasure policy? | `apps/shared/isolation.py` exists; the policy document was not located | WP0-07 |
| U-07 | What is the S3-compatible endpoint variable? | Not present in the `.env.example` grep window | WP0-02 |
| U-08 | Which docker publication holds 5432/9000? | `docker ps` is empty; requires host-level inspection | WP0-00 |

No other item is left as "NEEDS CLARIFICATION". Everything above has a concrete next action.

---

## 9. Research method note

No web research was performed for this document. It would have been the wrong tool: the donor
identity questions were already answered by verified API queries in the 029 matrix, and the
remaining questions are about **this repository's actual code**, which no external source can
answer. Re-querying GitHub would produce a fresher date on facts that are already recorded, at the
cost of discarding a verified record for a newer unverified one.