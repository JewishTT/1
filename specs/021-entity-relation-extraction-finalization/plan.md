# Implementation Plan: 021-entity-relation-extraction-finalization

**Branch**: `021-entity-relation-extraction-finalization` | **Date**: 2026-09-27 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/021-entity-relation-extraction-finalization/spec.md`
(5 constitutional invariants, 9 user stories, and the functional requirements and measurable
outcomes `spec.md` defines — see **Scale/Scope** for the counts and who owns them). The
unabridged user brief is `input.md` in this directory (4898 lines, §0–§114).

**Authority order — the constitution wins.** `.specify/memory/constitution.md` v1.0.0 states
verbatim: *"Constitution supersedes all other practices."* The order of authority is, highest
first: the constitution; then `input.md` wherever the constitution is **silent**; then this
feature's own artefacts wherever both are silent. Where `input.md` and the constitution conflict,
the constitution wins, this feature implements the constitution, and the conflict is recorded in
`docs/adr/` with a worked example naming the clause on each side. Where `input.md` fills a
silence, `input.md` governs. Where this feature's own artefacts conflict with either, the
artefact is wrong and is corrected. **An artefact MUST NOT state a rule of interpretation that
reverses this order**, and the Constitution Check gate MUST be evaluated on at least one case
where the constitution and `input.md` **disagree**. Two worked examples — one of agreement
(`input.md` §20 against Domain Invariant 3) and one of disagreement (Principle **VI**. Process-Centric, which
the brief does not address) — are in `repair/A1-constitution-investigation.md` §D2.4.

> **Correction to the previous revision of this file.** The text this replaces read: *"The
> unabridged user brief is `input.md` in this directory and governs over this document wherever
> the two appear to differ."* That inverts the clause above and is withdrawn. The inversion is
> recorded as a `violated` Governance row below, not merely edited away.

**Provenance of this revision.** Rebuilt mechanically from, in authority order:
`repair/ARBITRATION.md` (binding), `repair/A1-constitution-investigation.md`,
`repair/A8prep-ownership-and-dag.md`, A6's task-graph deliverable in `repair/A6-fr-triage.md`,
`repair/A7-migration-021.md`.
`spec.md` is owned by a separate integrator in the same pass; this plan states no requirement
that is not allocated by A1 D6 or A8prep O2.3, and every number it assumes is listed in
**FR placement** below.

## Summary

Turn 019's *raw surface string is logical identity* into a durable hypothesis-and-evidence
substrate, and repair the 20+ defects the code audit found while doing so.

The technical approach: **structural `PredicateSignature` as the identity carrier.**
`RelationSignal` becomes natively n-ary with a variadic participant list and a real polarity
field, declares a normalised `PredicateSignature` (normalised predicate, arity, role names,
argument shape, direction, polarity) alongside the raw surface it observed, and derives
`logical_candidate_id` from the signature instead of the surface. `relation_surface` becomes
pure evidence/revision material. Mention binding moves to a pre-resolution mention index so
producers cite real `MN-…` ids and a mention is never confused with an entity. The type layer
gains a bounded, versioned foundational vocabulary (`core:*`, `value:*`) plus a first-class
multi-hypothesis `TypeHypothesis` with a controlled vocabulary for the type space, while the
relation space stays open — an unrecognised predicate stays `UNKNOWN` forever rather than being
dropped. Persistence gains real columns (signature, signal refs, direction, polarity,
`candidate_id`, plus a typed n-ary `participants`) via migration `021` on top of the
forward-only `020`.

**The lifecycle is wired into an `InvestigationWorkflow`, not into an entity pipeline.** The
previous revision nominated `interpret_warc_capture` on the live `interpret_warc_capture` path as
*the* production seam. That seam is real and the interpretation work stays; but the function that
reaches it (`services/entity_pipeline.py::run_live_entity_pipeline`) takes no `investigation_id`,
which is the exact shape Principle **VI** forbids. The seam becomes **an activity of the
investigation workflow**, and the investigation becomes the only production entry point.

**Non-goal carried from the brief**: no giant relation ontology, no majority voting, no
mention × mention sweep, no producer that emits a claim or an edge.

## Technical Context

**Language/Version**: Python >= 3.11 (`requires-python = ">=3.11"`, ruff `target-version = "py311"`,
`line-length = 100`)

**Primary Dependencies**: `cognitive-shared` (workspace), `fastapi>=0.111`, `uvicorn[standard]>=0.30`,
`alembic>=1.13`, `httpx>=0.27`, `temporalio>=1.4`, `neo4j>=5.21`, `clickhouse-connect>=0.7`,
`orjson>=3.10`. Test/dev: `pytest>=8.2`, `pytest-asyncio>=0.23` (`asyncio_mode = "auto"`),
`ruff>=0.5`. Build: `hatchling`. Workspace manager: `uv` (11 members — the 10 `apps/*` packages
plus `bench`, all installed editable, so cross-app imports like `from extractors.registry import …`
resolve from any project). `apps/deploy` and `apps/webapp` are **not** workspace members.

**Storage**: PostgreSQL via SQLAlchemy 2.0 declarative (`mapped_column` + `__table_args__`),
migrated by Alembic (`014`…`020` exist; `020_universal_relation_extraction.py` is HEAD and
forward-only). Graph projection has `InMemoryGraphStore` (the only wired one), `Neo4jGraphStore`
(unwired, and it does not import the driver) and `RebuildableGraphStore` (unwired replay/snapshot
store). Also available: ClickHouse, OpenSearch, Kafka, Temporal, Redis via
`apps/deploy/docker-compose.yml`. **Live PostgreSQL is not reachable in this environment**, so DB
work is verified offline (ORM/DDL parity + in-memory round trip) and any live round trip is
reported as `verified only offline`.

**Testing**: `pytest` with per-app projects and `markers = ["contract","integration","unit"]`.
Canonical command form (`docs/CONTRIBUTING.md:37`): `uv run --project apps/<app> pytest apps/<app>/tests -q`.
There is **no CI** (`.github/` does not exist), no Makefile, no tox/nox, and no test-runner
script — the gate is run by hand. See **Complexity and risk**.

**Target Platform**: Linux server / Docker; Windows dev host (current environment is win32,
`pwsh`).

**Project Type**: multi-app Python workspace (FastAPI service + Temporal worker + libraries).

**Performance Goals**: bounded neighbourhood only — no global O(N²) mention sweep; a producer
that enumerates pairs MUST report a real count and MUST stay under its declared
`max_pairs_considered`.

**Constraints**, each with its clause. **Determinism under replay** (content-addressed ids
re-derived, never trusted) — *unnumbered*; anchored to **Domain Invariant 12** and to the Additional
Constraints' "Idempotency" clause, and **not** to Principle **VI**, which is Process-Centric.
**Tenant isolation** — constitution **VII**; *not* IV, which is "No Single Store / Graph / Score".
**Lossless persistence** (a digest may identify data but must never be the only copy) —
Principles **I** and **III**. **Raw predicate surface is evidence, never logical identity** —
Principle **II**, `input.md` §19. **No `ENT-`/`RES-` literals in producer code** — Principle
**V**, no domain type leaking into a producer. **No `TYPE_CHECKING` except in type positions** —
house rule. **The Investigation is the only production entry point** — Principle **VI**, and the
constraint the previous revision of this file omitted entirely.

**Scale/Scope**: 020 created 3 tables; 021 adds migration `021` plus new columns and new domain
types. The scope is the requirement set in `spec.md` — `FR-001`…`FR-100` **plus all seven
`repair/ARBITRATION.md` §14 bands**, each occupied band named in `spec.md`'s **Reserved number
space** block and in **FR placement** below — over 9 user stories, with the measurable outcomes
`spec.md` defines. **Measured against the current `spec.md`, not at pass start: 149 requirements
are defined in requirement form — the 100 slots in `FR-001`…`FR-100`, of which 4 are tombstone
records and therefore carry no requirement, leaving 96 live, plus 53 defined above `FR-100`
(6 already-live appends and 47 §14-band appends).** 5 constitutional invariants, 43 measurable
outcomes (`SC-001`…`SC-043`, contiguous, no gaps), 9 user stories, 6 tombstone records. Corpus
target: 8 golden end-to-end HTML cases (§109) + the §82/§83 type and relation case sets.

**The A7 band is narrower than §14's table says, and the table is the thing that is wrong.**
`ARBITRATION.md` §14 allocates A7 a range of 11 slots and counts it as 11, but
`repair/A7-migration-021.md` authors **9** requirements in that range and no more; all 9 are
applied in `spec.md`. §14's own arithmetic inherits the error: its "49 new normative FRs" is 47 by
A7's content. Nothing is unapplied, so §14 rule 6 is not violated by the document — the two spare
slots are named in the integrator's report as an arbitration correction, not written here, because
§14 rule 1 forbids inventing a number and a citation to an id nothing defines is itself a defect.

**Count conventions in this document.** Three id namespaces are in play and this plan keeps them
apart, because conflating them is a defect the checker reports:

| Namespace | Form | Owner | Scope |
|---|---|---|---|
| the constitution's Domain Invariants | `Domain Invariant 1` … `Domain Invariant 12` (an unlabelled numbered list in `constitution.md`) | the constitution | 12, constitutional |
| this feature's constitutional invariants | `INV-001` … `INV-005` (zero-padded) | A1, in `spec.md` | 5, feature-specific |
| functional requirements | `FR-` + three digits (zero-padded) | A8prep's allocation map | see **FR placement** |

The previous revision of this file used the unpadded two-or-three-digit form for *constitution*
invariants, which collides with the feature's own zero-padded ids. The unpadded form is not used
anywhere below.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design and after every ADR in
`docs/adr/0025`…`0028` is Accepted.*

**Verdict: FAIL.** 4 Core Principles `violated`, 2 `lip service`; 2 Domain Invariants `violated`;
the `Temporal` baseline clause `violated`; 4 Additional Constraints `violated`; **all 3**
Governance clauses `violated`. This feature does not proceed past Phase 0 until every `violated`
row is closed by a named requirement.

*Coverage: all 7 Core Principles (verbatim names), all 12 Domain Invariants, all 15 Technology
Baseline clauses, all 7 Additional Constraints, all 3 Governance clauses. Every row cites the
correct numeral. Status vocabulary: `satisfied` / `violated` / `lip service` / `not engaged`.*

> **The previous table is replaced in full, not extended. All seven of its rows were defective.**
> It carried four numbered rows and one prose row, and **not one** of them was a correct Core
> Principle citation. `I-2` / `I-3` / `I-4` are Domain Invariants wearing a Principle prefix;
> `VI determinism` cites a Process-Centric principle for a determinism requirement that does not
> exist in it; `IV tenancy` cites "No Single Store / Graph / Score" for a Security-First
> requirement; and the supersession row rested on a worked example where the two documents
> *agree*. The table omitted Principles **I**, **II**, **V**, **VI** and **VII** entirely, so
> its coverage of the Core Principles was **0 of 7**. Two verdicts are carried forward and marked
> `preserved`; one is downgraded.

### Core Principles (verbatim names from `constitution.md`)

| # | Principle | Status | Evidence (verbatim) |
|---|---|---|---|
| **I** | `I. Observation-Immutable Evidence Substrate` — every observation is immutable once recorded; raw objects are content-addressable; nothing downstream may edit an observation | **satisfied** | `apps/shared/tests/constitution/test_i1_i3_immutability_and_preservation.py`; `layer0_pipeline.py:219-222` `if res.lifecycle in ("duplicate", "unchanged"): # Three-way split (R-08): fresh bytes only get interpreted/indexed.` The re-observation split runs *before* the store write (`acquisition_loop.py:79-90`, `gate.ingest(…, previous_digest=prev_digest …)`). The old table had no row for I. |
| **II** | `II. Evidence-First` — any knowledge must trace fully: Finding → Analytical/Topological Feature → Graph/Assertion → Evidence → Observation → Raw Object → Source | **violated** | `EVIDENCE_BACKWARD_CHAIN` (`evidence_lineage.py:81-89`) is `RELATION, ASSERTION, MENTION, SEGMENT, OBSERVATION, CAPTURE, SOURCE`; `DERIVATION_FORWARD_CHAIN` (`evidence_lineage.py:102-112`) is `SOURCE, CAPTURE, OBSERVATION, SEGMENT, MENTION, CANDIDATE, ASSERTION, RELATION, ENTITY`. `HopKind` (`:50-65`) has **no `SIGNAL` member** and no member for `Analytical/Topological Feature`. SC-013's `edge → claim → candidate → signals → observations → source` is unachievable in either direction. See **F-1**, FR-169, ADR-0026. |
| **III** | `III. Projection-First Knowledge Architecture` — all projections are rebuildable artifacts; projection failure must never destroy evidence | **violated** | Measured by the spec itself at its "Production reachability, as measured" table: `db/relation_claim_store.py::SqlRelationClaimStore` has `**none**` importers; `relation_signal` / `relation_candidate` / `source_temporal_observation` have `**no repository, writer or reader at all**`; `projection/graph/snapshot.py::RebuildableGraphStore` has `**none**`. The old table's own `III` row said `**GAP**`; it is `violated` rather than `GAP` because *no* store is written, so there is nothing to rebuild from. |
| **IV** | `IV. No Single Store / Graph / Score` — different workloads use different engines; no universal graph as source of truth; no single score equates to truth | **lip service** | *First half holds:* `relation_store.py:353-355` — `The graph is a PROJECTION, not the source of truth (constitution III, I-4): no read path may answer a claim, context or verdict question from a graph store alone`. *Second half does not:* `dispatcher.py:74-85` fabricates `task_spec = {"expected_gain": 0.6, "relevance": 0.7, … "source_quality": 0.7, …}` and `dispatcher.py:86` collapses it — `score = self._scorer.score(task_spec, {"downstream_lag_s": 0.0})`. `relevance` and `source_quality` are **hardcoded constants, not measurements**, so they are not "stored separately" in any meaningful sense. The *correct* treatment already exists at `query_planner.py:14-15`; `dispatcher.py` is the counter-example. |
| **V-a** | `V. Plugability by Contract` — *acquisition half:* `All acquisition implementations conform to the AcquisitionWorker interface (capabilities() / estimate(task) / acquire(task)).` | **satisfied** | `source_registry.py:4` — `capabilities()/estimate()/acquire() (Constitution V, AcquisitionWorker contract);` and `:145` — `f"connector '{name}' must satisfy AcquisitionWorker "` — the gate is enforced, not asserted. `api/routes/connectors.py:36-45` is a conforming implementation. Split into V-a/V-b because the two halves have different verdicts. |
| **V-b** | `V. Plugability by Contract` — *graph half:* `Application code interacts with graphs only through GraphProjection / GraphReader / GraphSnapshot / GraphTraversal.` | **lip service** | `abstraction.py:154-167` is a single `class GraphStore(Protocol):` with `write_node` / `write_edge` / `write_hyperedge` / `neighbors` / `node`. There is **no** `GraphReader`, **no** `GraphProjection` and **no** `GraphTraversal` anywhere in the repository; only `snapshot.py:36 class GraphSnapshot:` matches. The backend that would demonstrate swappability is inert — `neo4j.py` never imports `neo4j`, and `neo4j>=5.21` is declared in `control-plane` while `projection`, which would need it, does not. ADR-0008/0009 exist and neither records that two of the four named roles were never built. |
| **VI** | `VI. Process-Centric` — `The user creates an Investigation — not a graph. Graphs, search indices, analytical structures, and TDA complexes materialize automatically within the investigation lifecycle and its policy/budget/freshness constraints.` | **violated** | `entity_pipeline.py:38` — `async def run_live_entity_pipeline(*, tenant_id: str, entity_id: str, identity: dict[str, Any], source_records: list[dict[str, Any]], catalog: Catalog, operations: Any) -> None:` — **no `investigation_id` parameter**, on the live user-reachable path. `layer0_pipeline.py:301` — `investigation_id: str = ""`, i.e. optional on the other candidate entry point. `worker.py:20-25` registers no investigation workflow. `input.md` contains no occurrence of `investigation`. The old table's `VI determinism` row did not check this at all. |
| **VII** | `VII. Security-First` — mandatory: SSRF protection, DNS-rebinding protection, sandboxed parsers, browser isolation, network egress policy, CPU/memory/timeout/size limits, archive-depth and file-count limits, `tenant isolation at every level`, RBAC, audit logs, secret isolation | **violated** | Four distinct failures. **(a) No egress policy on the fetch path:** `acquisition_loop.py:51-53` — `self._client = client or httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers={"User-Agent": "cognitive-acquisition/0.1"})` and `:63` — `resp = await self._client.get(item.uri)`; `follow_redirects=True` on an untrusted URL with no allowlist, no DNS-rebinding check, no egress policy. **(b) The audit log is a process-lifetime list:** `audit.py:41` — `self._events: list[AuditEvent] = []` — and `audit.py` has **one** importer repo-wide, a test; the real table `db/schema.py:596 class AuditLog(Base):` has no writer. **(c) Tenancy is one tenant deep:** `policy_service.py:24` hard-codes `tenant_id="default-tenant"` on the `Policy`, and `PolicyEngine.check` never compares a request's tenant to the policy's tenant. **(d) The two enforced VII items are cited to the wrong numeral** at 26 sites — see **F-4**. |

### Domain Invariants (all twelve, verbatim)

| # | Invariant | Status | Evidence (verbatim) |
|---|---|---|---|
| **Domain Invariant 1** | `Observation is immutable.` | **satisfied** | `apps/shared/tests/constitution/test_i1_i3_immutability_and_preservation.py`; `apps/control-plane/tests/test_observation_immutability.py`; the `layer0_pipeline.py:219-222` re-observation split. |
| **Domain Invariant 2** | `Mention != Candidate != Entity.` | **violated** | The spec's own defect table records that `metadata.py` uses a *property name* as the signal subject (`attribute:<key>`, `jsonld:<key>`), and falls back to the literal `document:current` when `document_ref` is empty. The old table's `I-2` verdict was `**PASS with work**`; it is **downgraded to violated**. A `document:current` fallback collapses every document in a batch onto one participant ref, and that is the invariant failing, not work remaining. |
| **Domain Invariant 3** | `Assertion != truth.` | **satisfied** *(preserved from the old `I-3` row)* | `PredicateResolutionState.UNKNOWN` exists and is retained; `material_requires_resolved_predicate` is the correct line for that invariant: a candidate may stay unresolved and is never dropped. UNKNOWN is a retained state, not a drop. **Correction:** the old row justified this with a label the constitution does not define — its Domain Invariants are an unlabelled numbered list. The anchor is Domain Invariant 3. |
| **Domain Invariant 4** | `Graph != source of truth.` | **satisfied** *(preserved from the old `I-4` row)* | `relation_store.py:362` — `def to_node(self, claim: RelationClaim, ref: str = "") -> GraphNode:` — typed on a claim with no overload, so a candidate or signal cannot be projected even by mistake. |
| **Domain Invariant 5** | `Kafka != object store.` | **not engaged** | No defect found; no 021 requirement touches it. `events/kafka.py:8` — `as ``events.kafka.IdempotentProducer``` and the shared ```Producer`` protocols —`. |
| **Domain Invariant 6** | `TDA != truth oracle (topological features are structural signals, not proof of identity).` | **not engaged** | 021 adds no TDA surface; `apps/science/` is untouched by this feature's requirement set. |
| **Domain Invariant 7** | `Admission != Priority.` | **satisfied** | `apps/admission/engine/admission.py` `AdmissionResult` carries `policy_version: str = "UNCALIBRATED-v1"` … `replayable: bool = True  # FR-013: rejected kept replayable`. The decision and the queue position are separate fields. |
| **Domain Invariant 8** | `Entity novelty != evidence novelty != structural novelty.` | **not engaged** | Not asserted in 021's requirement set and not asserted in the code either. Recorded as `not engaged` rather than `satisfied`: nothing enforces it. |
| **Domain Invariant 9** | `Search != Graph traversal != OLAP.` | **satisfied** | `query_planner.py:12-14` — a backend failure **degrades** a query, it never ends it, "because an empty list means *no matches*"; the code's own comment anchors that to Domain Invariant 9. |
| **Domain Invariant 10** | `Acquisition throughput != intelligence throughput.` | **not engaged** | No 021 requirement measures either quantity. The boundedness report measures `pairs considered`, not throughput. |
| **Domain Invariant 11** | `The fastest request is the request correctly avoided.` | **satisfied** | `dispatcher.py:104-106` — `if decision.value == "DENY": self._frontier.cooldown(item.frontier_id, time.time() + 60.0)` — a refusal becomes a cooldown, not a retry. |
| **Domain Invariant 12** | `All downstream projections must be rebuildable from durable evidence/events.` | **violated** | Same evidence as Principle III — the honest reading. Concretely, the spec's own reachability table records that `relation_signal` / `relation_candidate` / `source_temporal_observation` have `**no repository, writer or reader at all**`. Rebuildability is not merely unproven; the substrate it would rebuild from is unwritten. FR-097 and `relation_signal_store.py` are the whole remedy; there is no second one. The old table cited the *principle* and not the *invariant*, which is why this row was missed. |

### Technology Baseline (all fifteen clauses)

| Baseline clause (verbatim) | Status | Evidence (verbatim) |
|---|---|---|
| `Frontend: React + TypeScript` | **not engaged** | `apps/webapp/` is out of scope. |
| `API: FastAPI / Python` | **satisfied** | `fastapi>=0.111`, `uvicorn[standard]>=0.30`; 22 route modules carrying 120 route decorators under `apps/control-plane/api/routes/`. |
| `High-throughput components: Rust` | **not engaged** | Rust crates exist only under `apps/acquisition` (worker-http, worker-browser, target/ artifacts). Unmet rather than violated; 021 adds none. |
| `Workflow: Temporal` | **violated** | `temporalio>=1.4` is declared and one workflow is registered (`worker.py:20-25`), but the constitution-named `InvestigationWorkflow` is not registered, and the two activities the dead file calls do not exist anywhere. A baseline technology is present and its central workflow surface is dead. |
| `Event backbone: Apache Kafka (KRaft), Protobuf, Schema Registry` | **satisfied** | `docker-compose.yml` provisions `kafka:` and `schema-registry:`; `events/kafka.py::build_envelope` used by `dispatcher.py`. |
| `Raw storage: S3-compatible object storage (MinIO for dev/self-hosted)` | **satisfied** | `docker-compose.yml` provisions `minio:` and `minio-init:`; `gate.ingest(…)` at `acquisition_loop.py:79-90` returns `obs["raw_ref"]`. |
| `Operational state: PostgreSQL` | **satisfied** | `docker-compose.yml` provisions `postgres:`; `db/session.py::create_tables, make_session_factory` used by `temporal_materialization.py`. |
| `Search: OpenSearch projection` | **satisfied** | `docker-compose.yml` provisions `opensearch:`; `search_backends.py` declares `SearchProjectionStore` and `SearchIndexBackendClient`. |
| `Analytical storage: ClickHouse projection` | **satisfied** | `docker-compose.yml` provisions `clickhouse:`; `clickhouse-connect>=0.7` is declared. |
| `Stateful stream processing: Apache Flink (only for genuine stateful work, not transport)` | **not engaged** | `docker-compose.yml` provisions `flink-jobmanager:` and `flink-taskmanager:`. A repository-wide `flink` search matches only `README.md`, `docs/` and `docs/adr/0006-flink-role.md` — **no application code**. Provisioned-and-unused is the correct reading: the clause's own test is that it is not used for transport, and it is not used at all. |
| `Graph serving: replaceable abstraction layer` | **satisfied** | `abstraction.py:154-167 class GraphStore(Protocol):` with `InMemoryGraphStore`, `Neo4jGraphStore`, `RebuildableGraphStore`. This is the clause the *no vendor-specific classes* half of V-b rests on. |
| `TDA: Python (GUDHI, giotto-tda, NumPy, SciPy)` | **not engaged** | `apps/science/` untouched by 021. |
| `Runtime: Docker, Kubernetes` | **satisfied** (Docker) / **not engaged** (Kubernetes) | `apps/deploy/docker-compose.yml`; no k8s manifest under `apps/`. |
| `Observability: OpenTelemetry, Prometheus, Grafana` | **not engaged** | Not present in `apps/`. 021 adds no instrumentation — which is itself worth an ADR note, because honest reporting of production reachability is required and there is no production telemetry to report from. |
| `Secrets: Vault` | **not engaged** | Not present in `apps/`; a root `.env.example` exists. |

### Additional Constraints (all seven, verbatim)

| Constraint (verbatim) | Status | Evidence (verbatim) |
|---|---|---|
| `**No MVP/mini-architecture**: implement contracts of all major planes (Investigation, Acquisition, Evidence, Interpretation, Admission, Projection, Analysis, Feedback) up front; components may be introduced incrementally but must never break final domain/event contracts.` | **violated** | The **Investigation** plane is the one plane in that list with no contract. `worker.py:20-25` registers `TemporalEntityMaterializationWorkflow` only; `InvestigationWorkflow` is unregistered. The clause says "contracts of all major planes … up front", and the investigation contract is the one this plan adds. |
| `**Script type**: PowerShell (ps) for Speckit automation on Windows.` | **not engaged** | No Speckit automation scripts in this feature's deliverable set. |
| `**Backpressure**: downstream queue growth must reduce acquisition rate, not expand Kafka backlog.` | **lip service** | The mechanism exists — `dispatcher.py:125-130 def pump(...)` and the `HeuristicUtilityScorer.score` `context` parameter — but the only caller passes a **hardcoded** lag: `dispatcher.py:86` `score = self._scorer.score(task_spec, {"downstream_lag_s": 0.0})`. `downstream_lag_s` is a literal `0.0`, so backpressure is structurally present and permanently switched off. |
| `**Retry budgets**: task / source / investigation / global retry budgets to avoid retry storms.` | **violated** | `cp_domain/policy.py` declares one `Budget` keyed `budget/default` with per-`worker_class` limits. There is **no** task, source, investigation or global tier — `policy_service.py`'s `commit_usage` takes a `budget_id`, a `worker_class` and an amount, and nothing else. One tier is not four. No investigation-scoped budget exists to bound the new `acquire` activity's retries. |
| `**Dead letter / quarantine** for malformed data, repeated parser failures, policy uncertainty, resource abuse, unsupported formats; rejected candidates are never auto-deleted (replay/re-evaluation supported).` | **violated** | Quarantine and replay exist and are correct: `dlq.py` `class QuarantineStore:` / `"""Preserves rejected candidates for replay/re-evaluation."""` and `def replay(self, record_id: str)` returns the preserved payload unchanged. / `# Replay hands the preserved payload back to the pipeline unchanged.` **But `dlq.py:76-80` is an auto-delete** — `def purge(self, record_id: str) -> bool:` / `record = self._records.pop(record_id, None)` — and it is reachable from a live route: `api/routes/quarantine.py:64` `_store.purge(record_id)`. See **F-2**. Governance reinforces it: `Rejected analysis outputs (admission rejections, TDA signals) are preserved with decision, reasons, score vectors, versions, and timestamps for replay.` |
| `**Idempotency**: every consumer is idempotent using event_id / task_id / observation_id / projection offsets.` | **violated** | No consumer in the 021 path declares a key. `temporal_materialization.py:24-25` `async def reconcile_and_publish(tenant_id, entity_id, source_record_ids, run_id, entity_identity) -> dict[str, Any]:` — `run_id` is a *label*, and the body's only durability guard is `if source_record_ids: raise RuntimeError("source record resolution requires the durable entity_stream repository")`. The workflow's `run` passes `RetryPolicy(maximum_attempts=3)` and no idempotency key, so Temporal's own retry is a double-write. The two real idempotency implementations in the repository are `dlq.py`'s fingerprint dedupe and the re-observation digest split — neither is in the 021 path. |
| `**HTTP-first acquisition**, browser escalation only on insufficiency; separate browser fabric pool; resource classes priced by expected_value / estimated_cost.` | **lip service** | HTTP-first holds on the one live fetch path (`collector="worker-http"`). Browser escalation and the separate pool are declared in `docker-compose.yml` (`browsertrix:`) and nowhere in code. Resource classes are priced by the fabricated vector at `dispatcher.py:74-85`, so `expected_value` is the constant `0.6` for every task in the repository. |

### Governance (all three clauses)

| Clause (verbatim) | Status | Evidence (verbatim) |
|---|---|---|
| `Constitution supersedes all other practices.` | **violated** | The superseded text of this file stated that `input.md` `governs over this document wherever the two appear to differ`; `spec.md` stated the same in a blockquote at the top of the document. Both inverted it. The old gate row marked this `**PASS**` — on a worked example where the two documents **agree** (`input.md` §45 "no majority vote" against Domain Invariant 3 "Assertion != truth"). A rule cannot be tested on the one input where both operands already agree. Replaced by the **Authority order** at the head of this file, and demonstrated below on a case where they **disagree**. |
| `Changes to architectural decisions require an ADR (e.g., Kafka vs alternatives, object storage, PostgreSQL role, OpenSearch, ClickHouse, Flink, Temporal, graph abstraction/backend, TDA architecture, event schema, provenance, entity resolution, admission engine, frontier architecture, scheduling, recrawl, multi-region topology).` | **violated** | Four architectural changes are in flight with no ADR. **(a) `Temporal`** — adding the constitution-named investigation workflow is a `Temporal` decision, and `docs/adr/0007-temporal.md` already exists and predates it. **(b) `recrawl`** — `docs/adr/0017-recrawl-strategy.md` exists; the code being deleted and the code being added must both be reconciled against it. **(c) `entity resolution`** — the `owns`/`controls` synonym example in `data-model.md` N5 is entity-resolution-grade and has no ADR. **(d) `provenance`** — the Evidence-First chain repair is a `provenance` decision and `docs/adr/0012-provenance.md` exists. FR-167 closes all four. |
| `Compliance is verified on every PR/review.` | **violated** | `Test-Path .github` → `False`. There is no CI, no Makefile, no tox/nox and no test-runner script; a change to a constitutional layer is gated by a person remembering to run `uv run --project apps/<app> pytest apps/<app>/tests -q`. The previous revision of this file asserted `No constitutional violations are being accepted`, which is unfalsifiable in practice. FR-168 closes it. |

**Worked example — the two documents DISAGREE (this is the gate demonstrating itself).** The
brief is silent; the constitution is not. `input.md` contains no occurrence of `investigation`
across all 4898 lines. Its complete architecture statement is a five-stage chain — *what was
observed → what could it be → what our regime calls it → what survived validation and admission
→ what graph view do we project* — which is a **pipeline**, and says nothing about who starts it,
what bounds it, or when it stops. Principle **VI**. Process-Centric asserts a *subject*:
`The user creates an Investigation — not a graph.` Under the corrected authority order the
resolution is forced: the Investigation becomes the production entry point, the brief's five
stages become the workflow's stage sequence inside it, and the entity pipeline becomes a caller
of the workflow rather than its owner. That is FR-161 and ADR-0025.

**Worked example — the two documents AGREE (kept, but no longer the gate's only evidence).**
`input.md` §20 forbids forcing semantic equivalence where it is unknown — `Only unify when
deterministic normalization or explicit semantic mapping establishes that configuration` — and
Domain Invariant 3 forbids `Assertion != truth` from the other end. They compose. This example is the only
reason the old gate row's *conclusion* was true, and it is not evidence about the clause.

**Determinism, re-anchored.** The determinism defect the old table described is real, and its
row cited the wrong clause. `signal_refs` is identity material
(`relation_candidate.py:539 "signal_refs",`) and `__post_init__` normalises `supporting_spans`
(`:826-830`), `observation_refs` (`:831-833`) and `evidence_refs` (`:834-836`) — and **not**
`signal_refs`. Order-independence therefore survives only because a call site sorts by hand:
`assembly.py:253 ordered = tuple(sorted(signals, key=lambda s: s.signal_id))`. Its constitutional
home is **Domain Invariant 12** and the Additional Constraints' "Idempotency" clause. It is **not** Principle
**VI**, which is Process-Centric.

**Re-check after Phase 1 design** has three conditions, not one: (i) the `PredicateSignature` in
the data model keeps exactly two identity terms (structural signature + participant identity) and
does not reintroduce a surface-dependent term; (ii) `relation_candidate.py::__post_init__` sorts
`signal_refs` the way it already sorts `observation_refs` and `evidence_refs`; (iii) every
constitutional citation in the changed files names the correct numeral (FR-173).

### FR placement (A1 D6 vs A8prep O2.3) — settled by `ARBITRATION.md` §14; every requirement now has a number

`repair/ARBITRATION.md` §1's instruction to wait for an A8prep allocation is **withdrawn** — it was
unsatisfiable, because A8prep O2.3 allocated no band at all to A2 or A6 and left most of A1's band
unallocated. §14 replaces it with a definitive allocation and renumbers A1's band out of the range
A8prep had provisionally used. This plan cites real numbers throughout; **no requirement is cited by
handle any more**, because no free slot was the reason and the reason no longer holds.

| Requirement (subject) | Cited here as | Owner | Status |
|---|---|---|---|
| The Investigation is the only production entry point | FR-161 | A1 | applied in `spec.md` |
| The `user → extractor → graph` shape is prohibited as a class | FR-162 | A1 | applied in `spec.md` |
| Workflow and every activity it calls are registered, test-enforced | FR-163 | A1 | applied in `spec.md` |
| Stage order; mention binding is its own stage; no reimplementation of `reconcile_and_publish` | FR-164 | A1 | applied in `spec.md` |
| Every consumer declares an idempotency key; content-addressed `admission_id`; `projection_offset` | FR-165 | A1 | applied in `spec.md` |
| Policy / budget / freshness gate before any network call, tenant-scoped, four budget tiers | FR-166 | A1 | applied in `spec.md` |
| An architectural change ships an ADR before it merges | FR-167 | A1 | applied in `spec.md` |
| Compliance is verified automatically, or by a dated named attestation | FR-168 | A1 | applied in `spec.md` |
| A `SIGNAL` hop traversable both ways; the candidate is *resolvable from* the warrant path | FR-169 | A1 | applied in `spec.md` |
| A rejected candidate is never deleted by any production path, including its own re-evaluation | FR-170 | A1 | applied in `spec.md`; the A8prep collision is gone |
| The audit log is durable, not a process-lifetime list | FR-171 | A1 | applied in `spec.md`; the A8prep collision is gone |
| The dead investigation surface is deleted; exactly one investigation lifecycle exists | FR-172 | A1 | applied in `spec.md`; the A8prep collision is gone |
| Every constitutional citation names the correct numeral | FR-173 | A1 | applied in `spec.md`; the A8prep collision is gone |

**What changed, exactly.** A1 D6's band runs from the single-entry-point requirement to the
citation-numeral requirement, and §14 allocates the whole of it. `ARBITRATION.md` §14 places it at
`FR-161`…`FR-173`, which is disjoint from the A5/A7/A7b appends A8prep O2.3 had provisionally
placed at `FR-110`…`FR-115`. That is why the four handles this file previously used are gone: they
existed because A1's last four numbers pointed at requirements with entirely different subjects, and
citing them by number would have been a mis-citation. They now have numbers of their own.

**The gap this section used to flag is closed.** `ARBITRATION.md` §14 is the decision the previous
revision asked for, and it supersedes §1's withdrawn instruction.

## Findings the implementation must not inherit

These are **live code facts**, recorded so a future wave does not rediscover them as design
decisions. None is a specification issue; two are bugs in code this feature will touch.

### F-1 — `HopKind` has no `SIGNAL` member, so `SC-013` is unreachable in both directions

`apps/shared/domain/evidence_lineage.py:50-65` declares nine members — `SOURCE`, `CAPTURE`,
`OBSERVATION`, `SEGMENT`, `MENTION`, `CANDIDATE`, `ASSERTION`, `RELATION`, `ENTITY` — and
**`SIGNAL` is not one of them**. `SC-013` requires the round trip
`edge → claim → candidate → signals → observations → source` and back. Neither
`EVIDENCE_BACKWARD_CHAIN` (`:81-89`) nor `DERIVATION_FORWARD_CHAIN` (`:102-112`) can traverse to
a signal. Adding `CANDIDATE` to the backward chain **would not fix it**: the walk would still
stop one hop short. This is a **type-vocabulary defect, not a tuple-ordering defect**, and no
reordering of either tuple fixes it.

The `CANDIDATE` exclusion from the backward chain is a *deliberate* decision with a written
argument (`:75-80`: `A candidate is a hypothesis about a relation, not a carrier of the evidence
for one`). That argument is sound and this plan does not overturn it. The fix is therefore two
moves: add `SIGNAL` to `HopKind` and to both chains, and make a candidate **resolvable from** a
warrant path as a second step rather than a hop in it. FR-169; ADR-0026. `ARBITRATION.md` §9
adopts the same split and states the two lineages as permanently separate:

```text
EVIDENCE lineage      edge → claim → evidence → observation → capture/raw → source
DERIVATION lineage    edge → claim → candidate → signal → observation
```

### F-2 — `QuarantineStore.purge` deletes the rejected candidate it just re-evaluated

`apps/shared/events/dlq.py:76-80`:

```python
    def purge(self, record_id: str) -> bool:
        record = self._records.pop(record_id, None)
        if record is not None:
            self._by_fingerprint.pop(record.fingerprint(), None)
        return record is not None
```

and `apps/control-plane/api/routes/quarantine.py:58-65`:

```python
@router.post("/{record_id}/re-evaluate")
async def re_evaluate(record_id: str, ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None) -> dict:
    record = _store.get(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="record not found")
    mark = "rejected" if "malformed" in record.reason else "accepted"
    _store.purge(record_id)
```

`POST /dlq/{record_id}/re-evaluate` **purges the record it just re-evaluated**. The route's own
module docstring claims the opposite — replay "keeps the original payload byte-for-byte so
re-evaluation is faithful to the poison message that produced the failure" — and re-evaluation is
*less* faithful than replay, because the record is gone afterwards. This is a direct violation of
`rejected candidates are never auto-deleted (replay/re-evaluation supported)`. It is a **live code
bug, not a spec issue**, and the implementation must not inherit it: the route records the
re-evaluation outcome *on* the preserved record and leaves the payload byte-for-byte intact.
`tests/integration/test_quarantine.py` currently pins the violating behaviour
(`assert store.purge(rid) is True`) and must be inverted. FR-170.

### F-3 — `workflows/investigation.py` is unrunnable, not merely unwired

`apps/control-plane/workflows/investigation.py` is 291 lines with **zero** non-test importers.
It is unregistered (`worker.py:20-25` registers one workflow), it executes two activities —
`"acquisition.acquire_batch"` and `"acquisition.recrawl"` — that have **no definition anywhere in
the repository** (the only `@activity.defn` in the tree is
`temporal_materialization.reconcile_and_publish`), and at `:286` it contains

```python
workflow.signal(InvestigationWorkflow, "schedule_recrawl")
```

a call on a workflow **class** issued from inside a *different* workflow's `run`. Temporal signals
address a running workflow by workflow-id; they are not a method dispatch. Even with both missing
activities supplied, that line cannot reach a target. The file is therefore **unrunnable as
written**, which is a stronger statement than "unwired" and is why it is deleted rather than
registered.

### F-4 — Two competing investigation lifecycles, and 26 mis-cited constitutional numerals

`cp_domain/investigation.py:143-154` declares `class InvestigationState` with the transition
table `DRAFT → {PLANNING, ARCHIVED}`, `PLANNING → {RUNNING, DRAFT}`, `RUNNING → {PAUSED,
COMPLETED}`, `PAUSED → {RUNNING, COMPLETED, ARCHIVED}`, `COMPLETED → {ARCHIVED}`,
`ARCHIVED → {}`. `workflows/investigation.py:57-66` declares a **second, conflicting** one —
`CREATED / QUEUED / ACQUIRING / AWAITING_APPROVAL / APPROVED / REJECTED / RECRAWL / COMPLETED /
PAUSED` — with a different transition table, a different terminal set, and `PAUSED → QUEUED` where
`cp_domain` has `PAUSED → RUNNING`. Two answers to one question is a fork, not a reference
implementation. `cp_domain`'s wins: it already carries the Process-Centric claim in its own module
docstring, it owns the "persist once at close" monitor, and it is the one `investigation.py:37`
already imports. FR-172; ADR-0025.

Separately, the mis-citation this plan's own table was built on is **repo-wide**. The origin is
`apps/interpretation/extractors/signals/protocol.py:299`:

```python
            "cross-tenant output is refused fail-closed (constitution IV)",
```

— tenancy is **VII**, and Principle **IV** is `No Single Store / Graph / Score`. The same error
is at `semantic_path/assembly.py`. A repository-wide sweep finds **26** sites: tenancy-as-IV at
**20** and determinism-as-VI at **6**, spanning `apps/acquisition/`, `apps/control-plane/db/schema.py`,
four Alembic migrations (`016`, `018`, `019`, `020`), `apps/shared/domain/temporal_observation.py`,
`extractors/signals/signal.py` and `apps/shared/tests/constitution/` — including that suite's own
filename, `test_iv_vi_tenancy_and_determinism.py`. A constitutional citation that is wrong in 26
places is not a typo; it is an uncited convention, and it is why a gate could pass on a mis-cited
row. The codebase already knows the right numeral elsewhere: `query_planner.py:12-15` cites
`Constitution IV` for the no-single-score rule correctly. FR-173.

### F-5 — A count that is wrong in the file that reports counts

The `What the skips hide` section of `phase0-results.md` is headed *"14 tests never executed"* and then lists `10 + 2 + 2 + 1 + 7
= 22`, and its own boxed conclusion says **22**. The heading's 14 is the miscount; the list and
the conclusion are right. Recorded because this feature's honesty requirements are exactly about
not inheriting a number from prose when the prose's own arithmetic disagrees with it.

## The `InvestigationWorkflow` contract

**A new, minimal, registered workflow. Not a resurrection of `workflows/investigation.py`.**

| Field | Value |
|---|---|
| **Workflow** | `InvestigationWorkflow`; Temporal type name `investigation.lifecycle` via `@workflow.defn(name="investigation.lifecycle")` |
| **Module** | `apps/control-plane/workflows/investigation_lifecycle.py` — a **new** file. The module name cannot be reused, because the old file is deleted (F-3). |
| **Task queue** | `cognitive-investigations` — the same queue the dead file declared, because that name is already the event catalog's name for this plane. |
| **Registration** | `workflows/worker.py` adds the workflow to `workflows=[…]` and every activity to `activities=[…]`. **Test-enforced**: a test imports the worker's registry and asserts membership. "It exists" has been claimed four times in this repository and been true zero times. |
| **Activities** | Eight `@activity.defn`s, all declared on the worker. **Zero** string-only `execute_activity` calls — the two string names at `investigation.py:213,288` are gone and are not replaced by strings. |
| **Determinism** | No I/O in the workflow body. All network, store and clock access is in activities. |

**What it deliberately does not carry**: no approval gate (`AWAITING_APPROVAL` / `APPROVED` /
`REJECTED` are dropped — no FR in 021 requires human approval, and an unexercised gate is a second
dead workflow); no `RecrawlWorkflow` (recrawl is `docs/adr/0017-recrawl-strategy.md`'s subject and
is out of 021's scope); no lifecycle enum of its own (it reuses
`cp_domain.investigation.InvestigationState`, per F-4); and no stage logic — every stage is a thin,
typed activity call.

### Stages and activities

The sequence is the brief's five-stage chain made executable, wrapped in acquire and validate.
Stage 2 is **not** folded into stage 4: mention binding must be a distinct layer, and folding it
re-creates the exact defect where a producer fabricates its own mention refs. "Minimal" here means
minimal *logic*, not a merged stage list that hides a required seam.

| # | Stage | Activity | Output |
|---|---|---|---|
| 1 | acquire | `investigation.acquire` | `AcquireOutput(observation_ids, rejected: tuple[RejectedItem, …], degraded: bool)` |
| 2 | interpret — mention binding | `investigation.bind_mentions` | `BindMentionsOutput(mention_index_revision, bound, unbound)` |
| 3 | interpret — type signals | `investigation.extract_type_signals` | `TypeSignalOutput(type_signal_ids, type_hypothesis_ids)` |
| 4 | interpret — relation signals | `investigation.extract_relation_signals` | `RelationSignalOutput(relation_signal_ids)` |
| 5 | interpret — candidate assembly | `investigation.assemble_candidates` | `AssembleOutput(candidate_ids, conflicted, unknown_retained)` |
| 6 | validate | `investigation.validate_candidates` | `ValidateOutput(claim_material_ids, rejected_ids, reasons)` |
| 7 | admit | `investigation.admit_claims` | `AdmitOutput(decision_ids, decision_by_candidate, quarantined_ids, preserved_rejections)` |
| 8 | project | `investigation.project` | `ProjectOutput(projected_edge_ids, projected_hyperedge_ids, projection_offset, skipped)` |

`RejectedItem` is a first-class type, not a `str`: it carries
`(kind, reason_code, ref, preserved_at, score_vector, policy_version)`, because the constitution
requires rejections to be preserved *"with decision, reasons, score vectors, versions, and
timestamps for replay"* and a bare id cannot hold a score vector.

### Idempotency keys

The clause, verbatim: `every consumer is idempotent using event_id / task_id / observation_id /
projection offsets.`

| Consumer | Key | Behaviour on replay |
|---|---|---|
| `investigation.acquire` | `task_id`, content-addressed over `(investigation_id, sorted(seeds), policy_id, freshness_seconds)`, written to the activity's idempotency table **before** the fetch | A completed `task_id` returns the stored output and issues **no** network call. A *partial* one resumes from the observation gate's digest, not from a refetch. |
| `investigation.bind_mentions` | `observation_id` — and the index key **includes the capture**, so two captures of one segment produce two mentions, not one | Re-binding an already-bound occurrence returns the existing `MENTION-…` id. |
| `investigation.extract_type_signals` | `event_id` | Upsert on the derived `signal_id`. Never an append. |
| `investigation.extract_relation_signals` | `event_id` + `task_id` — `task_id` distinguishes two acquisitions of the same bytes at different times, which must be two observations | Upsert on `signal_id`. |
| `investigation.assemble_candidates` | the derived `candidate_id` | Upsert on `candidate_id`. Two input orderings MUST give one id — today only because a call site sorts by hand (see the determinism re-anchor above). |
| `investigation.validate_candidates` | the derived `relation_id` | Upsert on `relation_id`. |
| `investigation.admit_claims` | a **content-addressed** `admission_id`, a digest of `(candidate_id, policy_version, reason_codes, score_vector)` — **replacing** `admission.py`'s `field(default_factory=lambda: "AD-" + uuid.uuid4().hex[:12])` | Upsert on the derived `admission_id`. Two identical admissions derive one id; two differing `reason_codes` derive two. Without this, a Temporal retry double-admits. |
| `investigation.project` | a monotonic per-`(tenant_id, investigation_id)` `projection_offset` watermark, written on success only | Skip any `relation_id` at or below the watermark. `GraphProjectionBridge` is one-way by construction (`"""Map a stored claim onto the existing graph types (one way, no back-flow).`), so re-projection cannot back-flow a rejection into the graph. |

Two of these are new and are the substance of FR-165: the content-addressed `admission_id` and
the `projection_offset` watermark. The other six have an existing derivation to lean on.

### How it subsumes rather than duplicates `reconcile_and_publish`

`reconcile_and_publish` is **not** deleted and **not** reimplemented. It becomes the `acquire`
activity's WARC-pull implementation for the Common Crawl source class, and nothing more. It keeps
its library function; it loses its inline `materialize_history` and `from_entity_stream` calls,
which are interpretation and move to stages 5 and 8. Its four near-duplicate `StreamRecord(...)`
literals collapse into one helper — each currently hard-codes
`"admission": {"decision": "ACCEPT_NEW", "status": "ACCEPTED", "confidence": 0.91, …}`, a single
hard-coded score standing in for an admission decision, which is a Principle **IV** problem in the
one place Principle **IV** is most concrete. The non-duplication test is mechanical: the
call-site count of `materialize_history` must not grow, and the Common Crawl discovery block must
exist in exactly one place. `entity_pipeline.py` becomes a thin client that starts the workflow
and returns a run id; the duplication between it and `reconcile_and_publish` is deleted.

## Dead-code dispositions

Importer counts are **non-test** and exclude `donors/` and `tmp/`.

| File | Lines | Non-test importers | Disposition | Why |
|---|---|---|---|---|
| `apps/control-plane/workflows/investigation.py` | 291 | **0** | **DELETE**, lifecycle relocated first | F-3. Unregistered, unrunnable, and 291 lines of `@workflow.defn` surface that reads as *the* investigation workflow is the specific trap Principle **VI** creates. `InvestigationLifecycle` / `LifecycleState` / `LifecycleConfig` / `InvalidLifecycleTransition` are relocated **first** into `cp_domain/investigation.py`, beside the monitor the dead file already imports — one lifecycle, one home — and its 12 unit tests are re-pointed there and must stay green. FR-172. |
| `apps/control-plane/services/layer0_pipeline.py` | 355 | **0** (one integration test only) | **DELETE the orchestrator; KEEP the four hook `Protocol`s** | `seed()`'s `investigation_id: str = ""` (`:301`) makes the primary way to start work investigation-less, and the class calls itself *the missing composition root* while a constitutional one is being built. Two entry points is a Principle **VI** violation. `InterpretHook`, `FabricHook`, `SearchHook` and `LakeHook` are kept verbatim, moved onto the investigation path, and become the shape of stages 2–8. FR-172. |
| `apps/control-plane/services/acquisition_loop.py` | 117 | **1**, and that one is itself dead | **DELETE** | It is the fetch path Principle **VII**'s mandatory list forbids: `follow_redirects=True` on an untrusted URL with no allowlist, no DNS-rebinding protection and no egress policy is SSRF by construction. **Wiring it into the new workflow would convert a dead violation into a live one.** It is replaced by an `AcquisitionWorker`-conformant implementation, which is the only shape that can carry the VII controls. `FrontierItem` and `PgFrontier` are kept and used by the replacement; `LoopResult` becomes the activity's output type. FR-172. |
| `apps/control-plane/services/dispatcher.py` | 211 | **0** | **KEEP-AND-WIRE, narrowly corrected** | Principle **VI** requires the lifecycle to run *"within its policy/budget/freshness constraints"*, and this is the only in-repo policy/budget gate: `dispatcher.py:96-103` calls `self._policy.check(policy_id="policies/default", …)` and `:104-106` turns a `DENY` into a cooldown. Deleting it deletes the constitution's only budget gate. Two corrections are mandatory and are Principle **IV** work, not cleanup: the fabricated `task_spec` (`:74-85`) is replaced by per-investigation state, and `run_recon_plan` is dropped — a second planning path with its own lifecycle the brief never asked for. `DispatchResult` becomes the `acquire` activity's scheduling result. FR-166; ADR-0027. |
| `apps/control-plane/services/policy_service.py` | 54 | **1**, and that one is itself dead | **KEEP-AND-WIRE, with a tenancy defect fixed** | Same reasoning one link closer to dead: it is the only wrapper over `cp_domain.policy.PolicyEngine` and the only consumer of the retry budget the constitution mandates. The defect: `:24` hard-codes `tenant_id="default-tenant"` on the `Policy`, and `PolicyEngine.check` looks the policy up by id and evaluates it without ever comparing the requesting tenant — so a second tenant is evaluated against the first tenant's policy. Fix: the service becomes tenant-keyed and `check()` refuses a tenant that does not own the named policy, failing closed. That is Principle **VII**, cited correctly this time. FR-166; ADR-0027. |
| `apps/control-plane/services/audit.py` | 67 | **0** (one unit test only) | **KEEP-AND-WIRE, as a durable sink** | Principle **VII** names `audit logs` in its **mandatory** list and the durable table already exists (`db/schema.py:596 class AuditLog(Base):`). The defect is the implementation: `audit.py:41 self._events: list[AuditEvent] = []` is a process-lifetime list with an optional sink nothing supplies. An audit log that dies with the pod is not an audit log, and 021 changes the admission and projection layers, which is exactly what must be audited. `investigation.admit_claims` writes the decision, `investigation.project` writes the projection, each with reason codes and score vector attached. `AuditEvent.immutable` stays `True`. FR-171. |

### Which of these touch "rejected candidates are never auto-deleted"

| File | Touches it? | Why |
|---|---|---|
| `audit.py` | **Yes — the fix *is* the obligation.** | A `REJECT` decision that leaves no durable record *is* an auto-delete in everything but name: the candidate survives in memory and is gone with the process. A `list[AuditEvent]` preserves none of the required decision, reasons, score vector, versions or timestamps across a restart. |
| `investigation.py` | **No, and that is a reason to delete it.** | `LifecycleState.REJECTED` is an *investigation*-level state with nothing to do with *candidate* preservation. Its `@workflow.defn` surface invites someone to wire it and then add a "reject the investigation, drop its candidates" branch. Deleting removes the temptation. |
| `layer0_pipeline.py` | **No.** | It never rejects anything; it returns `StageOutcome(ok=False, …)` and a tick. Its `seed()` is a Principle **VI** problem, not a preservation problem. |
| `acquisition_loop.py` | **No — but adjacent.** | Its `fail_retry` and `last_digest` calls are a retry/degradation path, not a candidate path. The frontier does delete rows, but frontier rows are *work items*, not rejected candidates. The new `acquire` activity MUST NOT propagate that delete to any rejected candidate. |
| `dispatcher.py` | **No.** | `self._frontier.cooldown(...)` on `DENY` is a deferral, which is the correct behaviour for a refusal to spend. |
| `policy_service.py` | **No.** | `PolicyEngine.check` returning `DENY` is a *refusal to spend*, not a rejection of a consideration. |
| `apps/shared/events/dlq.py` *(not in the table above — recorded here because leaving it would make the requirement unsatisfiable)* | **Yes — this is the violation.** | F-2. `purge` deletes the record the re-evaluation route just handled. |

## Architecture Decision Records

Governance requires an ADR for each architectural decision, and four separate decisions are in
flight. **Four records, not one**: a single document covering four decisions would repeat the
gate's own error at a larger scale. The house format is `# ADR-NNNN: Title`, then `Status:` /
`Date:` / `Feature:`, then `## Context` / `## Decision` / `## Rationale` / `## Consequences`,
matching `docs/adr/0019-reconstruction-frontier.md` and `docs/adr/0021-atomic-stream-sequence.md`.
`0024-claim-and-context-persistence.md` is the highest existing number, so **0025** is the next
free one. Full text for all four is in `repair/A1-constitution-investigation.md` §D5.

| # | File under `docs/adr/` | Decision | Governance trigger | Extends | FRs |
|---|---|---|---|---|---|
| 0025 | `0025-investigation-lifecycle-entry-point.md` | The Investigation is the only production entry point; `entity_pipeline.py` becomes a client; `reconcile_and_publish` is delegated to, not reimplemented | `Temporal`, `scheduling` | ADR-0007, ADR-0019 | FR-161, FR-162, FR-164, FR-166, FR-163, FR-172 |
| 0026 | `0026-evidence-warrant-resolution.md` | A `SIGNAL` hop exists and is traversable both ways; the candidate stays **out** of the evidence chain and becomes *resolvable from* it — a second step, not a hop | `provenance` | ADR-0012 | FR-169, SC-013, US9, INV-005 |
| 0027 | `0027-invocation-boundary-tenant-scoped-policy.md` | An explicit invocation boundary owned by the `acquire` activity: tenant-keyed policy, four budget tiers, absent lag read as **maximum** lag, `AcquisitionWorker`-conformant fetch | `PostgreSQL role`, `frontier architecture`, `scheduling` | ADR-0003, ADR-0014, ADR-0015 | FR-166, FR-171, FR-172 |
| 0028 | `0028-structural-predicate-equivalence.md` | Structural predicate identity admits **no** synonym table. `normalized_predicate` is a deterministic normalisation of a *surface realisation* and nothing else; `owns` / `controls` / `manages` remain three logical hypotheses | `entity resolution` | ADR-0013 | FR-004, SC-007, FR-167 |

All four files are owed; none exists at the time of writing. `FR-167` requires each to be
non-empty and to carry a `## Decision` section before the change it records merges.

**Location conflict, flagged.** A6's rewrite of `FR-083` places the feature's decision records in
`specs/021-…/adr/`, while A1 D5 and the repository's own convention place them in `docs/adr/`.
`ARBITRATION.md` does not settle it. This plan follows A1 and the house convention — `docs/adr/`,
numbered continuously with ADR-0024 — because Governance's ADR list is repository-wide and a
second ADR tree inside one feature directory would itself be an ownership defect. Recorded for the
arbitration of record.

## Persistence ordering: `021` after the domain types

Migration `021` **cannot** be written before the value types exist, and the reason is the ORM path
rather than the migration path. The migration writes literals (correctly — a migration that reads
a value type is a migration whose meaning changes when that type is edited); the ORM imports the
enum. A CHECK written against an enum that does not exist cannot be mirrored, and a column whose
writer does not exist produces the very defect this feature exists to fix — `spec.md:803`'s
`no repository, writer or reader at all`.

> **`021` that adds 23 columns and no writer reproduces the exact defect it was created to fix.**

The ordering is therefore a hard dependency:

| Order | Prerequisite | Exists at HEAD? |
|---|---|---|
| 1 | `SignalBasis` — a new closed vocabulary; **named by no artefact at all** | **no** |
| 2 | `Polarity` | **no** |
| 3 | `PredicateSignature` + normalisation | **no** |
| 4 | `RelationCandidate.direction` / `.polarity` fields; `signal_refs` canonicalisation | **no** / field exists, canonicalisation does not |
| 5 | `SignalKind` widened, and the obsolete CHECK constraints dropped | **no** |
| 6 | **migration `021`** | — |
| 7 | store writes the new columns | — |
| 8 | repository / writer / reader for all three 020 tables | — |
| 9 | round-trip tests, reporting `verified only offline` | — |

`SignalBasis` is the ordering defect this plan must name: it is the subject of a replacement
CHECK, it is the ninth new column on `relation_signal`, and **no artefact mentions it**. Under
the phase DAG below, `021` sits in Phase 8's entry gate, which is *after* Phase 1 (signature and
polarity) and Phase 4A (`SignalBasis`, additively). Two dependencies are currently missing from
the task list entirely: `021` depends on the signal-contract and identity work, and its parity work
touches two test files no task owns.

## Phase DAG

**One notation only** (`ARBITRATION.md` §5: `4A/4B/4C` and `4a/4b/4c` must not both appear
anywhere; A6's two-way `4A/4B` split is superseded by the three-way split):

```text
P0 → P1a → P1b → P2 → P3 → P4A → P4B → P4C → P5 → P6 → P7 → P8 → P9
```

`P1a` and `P1b` are the two commit stages **inside** the single phase `P1`, so the DAG above has
**twelve phase headers** — `P0`, `P1`, `P2`, `P3`, `P4A`, `P4B`, `P4C`, `P5`, `P6`, `P7`, `P8`,
`P9` — and **thirteen commit stages**. This is the canonical spelling: `tasks.md` carries the same
line, and an earlier revision of this file printed `P1` without the split, which contradicted both
the C-2 resolution below and `tasks.md`'s own header.

| Phase | Subject | §110 coverage |
|---|---|---|
| **P0** | Spec / constitution / traceability — a **gate**: no production code, no test | none; new and additive (Phase −1 relative to §110, which §110 itself endorses) |
| **P1** | Identity + `PredicateSignature` + `RoleSignature` | §110-1, §110-5 (merged) |
| **P2** | Type vocabulary + `TypeHypothesis` substrate | §110-2, §110-3 first half |
| **P3** | Mention binding / occurrence index | §110-3 second half |
| **P4A** | Additive structural contract — new fields and derived compatibility accessors only | §110-4, §110-6 |
| **P4B** | Producer migration — the 7 construction sites, one commit | §110-4, §110-6 |
| **P4C** | Enum / lifecycle / corpus cleanup — deletions and CHECK-constraint drops | §110-4, §110-6 |
| **P5** | Candidate assembly | §110-7 |
| **P6** | Claim material / validation / admission | §110-8 first half |
| **P7** | `InvestigationWorkflow` production wiring | §110-8 second half, plus §101 / §108 / §114 |
| **P8** | Graph projection | §110-9 substrate (hoisted, see below), §110-10 |
| **P9** | Replay / determinism / golden corpus | §110-9 proof, §110-11, §110-12 |

**§110 coverage: 12 of 12 phases covered, none skipped.** 1→P1, 2→P2, 3→P2+P3, 4→P4, 5→P1,
6→P4, 7→P5, 8→P6+P7, 9→P8+P9, 10→P8, 11→P9, 12→P9.

`P4A` is additive-only precisely so the sequence stays committable: it introduces the variadic
`participants` field and `SignalBasis` **without** removing the binary columns or the `SignalKind`
members, so `P4A` is green on its own. `P4B` migrates the 7 producer construction sites. `P4C`
performs the deletions, drops the obsolete CHECK constraints, and carries its own two call-site
migrations in the same commit. This is why the measured breakage is **2 breaking lines**, not 12.

### Conflicts with `input.md` §110 — 8 found, 2 of them real inversions

| Id | Conflict | Kind | Resolution |
|---|---|---|---|
| **C-1** | §110 has no Phase 0; its phase 1 is *code* | not substantive — Phase −1 | Label P0 a **gate**; it produces no production code and no test. |
| **C-2** | **P1 merges §110-1 with §110-5 across three intervening phases** | **real inversion** | See below. |
| **C-3** | The mandated Phase 4 omits §110-5 | consequence of C-2 | Resolved by C-2's split. Without the split, §110-5 is genuinely skipped and P4's producers cannot emit a signature. |
| **C-4** | **P8 (projection) precedes P9 (persistence + replay), inverting §110** | **real inversion** | See below. |
| **C-5** | P7 has no §110 counterpart | additive, not a conflict | Authorising sections recorded: §101 (recommended final domain model), §108 (acceptance criteria), §114 (deliverables). |
| **C-6** | §110-3 spans P2 and P3 | split, not a skip | §110-3's own text is "type hypothesis + mention binding" — two subjects. |
| **C-7** | §110-8 spans P6 and P7 | split, not a skip | — |
| **C-8** | §110-12 has no home of its own | absorbed | Absorbed into P9. This makes the Phase-0 baseline freeze a **repeated** obligation: it must be re-read at P9's entry, not only at P0. |

**The first real inversion — C-2, handled by a split, not a reorder.** §110 deliberately orders
identity cleanup (1) *before* the signature (5), with 2/3/4 in between. The mandated structure
places them together. The resolution keeps one phase named "Identity + `PredicateSignature` +
`RoleSignature`" with one entry condition and one exit condition, and makes the **commit boundary**
mandatory: **P1a** = §110-1 identity cleanup, committable and green on its own; **P1b** = §110-5
signature + `RoleBinding` + candidate identity. This satisfies §110 (1 precedes 5 in the commit
history) and the mandated phase name, and it is **mandatory, not optional** — without it §110-5
is skipped and C-3 becomes a real gap. The reversal is also visible in the task list today: a P1
task names a **P3** task as its dependency, carrying a "temporary fallback" in identity material,
which is itself forbidden. That task is re-created in P1b with the fallback removed.

**The second real inversion — C-4, handled by a dependency split, not a reorder.** §110 puts
persistence at 9 and projection at 10; the mandated order is projection (8) then persistence (9).
The mandated order is **preserved**; §110 is satisfied by splitting §110-9. The persistence
**substrate** — migration `021`, ORM/migration parity, the relation store's writer and reader — is
an **entry condition of P8** and executes as P8's entry gate. The **proof** — build → store → read
round trips, replay, corpus, mutations, regression, benchmark — is P9. Persistence therefore exists
before projection is verified, and no phase is reordered. This is the same split the persistence
ordering section above requires, seen from the phase side.

**Task-count conflict, closed against the file.** A6's task-graph deliverable in
`repair/A6-fr-triage.md` specifies **13 phases, 0–12, 94 tasks** in a single `T1xx`…`T9xx` series,
with ids `^T\d{3}$` and no letter suffix. The DAG above is A8prep's, as `ARBITRATION.md` §5
assigns, and §5 also merges the signature phase into `P1` ahead of the phases A6 numbered in
between — which is why applying A6's id table literally would have put the candidate-identity task
on the page before the type pack. **`tasks.md` has since been rebuilt and the conflict is no longer
live: it carries 94 tasks, `T101`…`T194`, contiguous, ascending in document order, with no letter
suffix, under the twelve phase headers above.** The re-assignment is lossless — A6 owns each task's
content, its phase and its FR citations, and only the label moved. A6's *content* count (94 tasks)
and A8prep's *phase* count (12 headers, 13 commit stages) are therefore both satisfied, and no
artefact may cite a pre-repair `T0xx` id: `tasks.md` states that such a citation reintroduces the
very phantom its id grammar closes, and pre-repair tasks are named by what they did.

## Gate assertions

`repair/tools/reference_check.py` runs **87 machine-checkable assertions** in nine groups
(G1 ownership and geometry 6, G2 numbering and traceability 13, G3 task graph 13, G4 data model vs
the diagram 9, G5 reference integrity 10, G6 constitutional 8, G7 phase-gate coherence 7, G8
persistence and migration 8, G9 honesty 8). **Any assertion failing means the revision is not
PASS**; there is no partial pass.

**21 of the 87 fail against the revision as it stands.** Each has a named owner:

| Assertion | Measured failure | Owner |
|---|---|---|
| G2.3 / G2.4 | the stop-conditions requirement is stranded after the production-wiring requirement in document order, so the sequence rewinds | A6 |
| G2.5 | **52** orphan FRs | A6 + every band owner |
| G2.8 | 5 checklist rows depend on a phantom task id | A6 |
| G2.10 | `input.md` is 4898 lines but two artefacts say 3411; a mutation count says "Four" and lists six | A6 |
| G3.2 / G3.3 | **9** phantom task ids, including a letter-suffixed class | A8prep |
| G3.4 | **0** tasks carry a `FILES:` line | A7b |
| G3.5 | **6** `[P]` groups share files or read each other, plus one linter task | A8prep |
| G3.6 | **1** backwards edge: a P1 task depends on a P3 task | A8prep |
| G3.9 | No task carries an entry/exit condition; no phase states one | A8prep |
| G3.10 | The declared MVP names one story; its phases carry five | A8prep |
| G4.1 | **4** dangling diagram node names | A6 |
| G4.2 | distinct-type level counts 7 / 8 / 12 in three places | A1 + A6 |
| G4.3 | **3** alias collisions for one concept | A5 (×2), A6 (×1) |
| G4.4 | **2** Key Entities with no entity-summary row | A5, A4b |
| G4.5 | `relation_ref` declared authoritative on two types | A4b |
| G6.8 | the distinct-type invariant is stated with a count in 2 places, with 2 values | A1 |
| G7.4 | C-2's P1a/P1b split is absent | A8prep |
| G7.5 | C-4's persistence hoist is absent | A8prep |
| G7.7 | the 7 construction sites and 12 enum references have no owning task | A8prep |
| G9.6 | a stated floor of "≥ 20" against 18 measured field groups; "17 mutations" against 6 named | A6 |
| G9.8 | the baseline is run once, not re-read at P9's entry | A8prep |

Standing additions from `ARBITRATION.md` §12: the checker's overall verdict must reach **0 FAIL**
on the canonical revision, with every check id present in the summary so a check that silently
stopped running cannot hide.

## Project Structure

### Documentation (this feature) — real names, no artefact is claimed missing that exists

```text
specs/021-entity-relation-extraction-finalization/
├── input.md                   # the user's unabridged brief — 4898 lines, §0–§114
├── spec.md                    # the requirement set; counts mid-revision this pass (see below)
├── plan.md                    # this file — rebuilt from its previous 236-line revision
├── tasks.md                   # Phase 2 output
├── research.md                # Phase 0 output
├── data-model.md              # Phase 1 output
├── phase0-results.md          # the T101/T102 baseline and the review verdict
├── checklists/
│   └── requirements.md        # gate checklist
├── repair/                    # ARBITRATION.md, A1, A2, A4b, A5, A6, A7, A7b, A8prep, tools/
├── quickstart.md              # owed — does not exist yet
└── contracts/                 # owed — does not exist yet: producer protocol, mention-index
                               #          contract, store contract
```

**File lengths, and a concurrency caveat.** The frozen measurement that governs *patch geometry*
is `repair/A8prep-ownership-and-dag.md` §0, taken at pass start: `input.md` 4898, `spec.md` 936,
`plan.md` 236, `tasks.md` 281, `data-model.md` 303, `checklists/requirements.md` 158,
`research.md` 247, `phase0-results.md` 204. That table is what A8prep O5 S2 validates hunk headers
against, so it is the figure to cite when checking a patch.

`spec.md` and `data-model.md` are being rewritten by their own integrators **in this same pass**,
and both have already moved well past their pass-start length, as has this file. A length quoted
from §0 is therefore a *baseline*, not a live measurement, for those three artefacts. Re-measure
before using any of them as a patch target; a patch authored against the pass-start figures will
land on the wrong range. The figures above are stated in the tree without per-file line counts for
exactly that reason.

**The previous listing's errors, corrected.** It marked four artefacts as missing when
three of them — `tasks.md`, `research.md` and `data-model.md` — and `checklists/requirements.md`
all exist; it listed an `adr/` directory inside the feature when the records live in `docs/adr/`;
and it gave the brief's stale `3411 lines` figure for the brief.

Architecture Decision Records do **not** live in this directory; they live in `docs/adr/` and are
numbered continuously with the repository (0025…0028, above).

### Source Code (repository root)

Directory names are the real ones at HEAD. `NEW` marks a file this feature creates.

```text
apps/
├── shared/                                # value types + contracts (cognitive-shared)
│   ├── domain/
│   │   ├── relation_candidate.py          # signal_refs is identity material and is not sorted
│   │   ├── predicate_hypothesis.py        # 4 states; no PredicateSignature
│   │   ├── predicate_signature.py         # NEW — structural normalised identity
│   │   ├── relation_claim_material.py
│   │   ├── relation_claim.py
│   │   ├── relation_identity.py           # canonical_material / digest128 / logical_material
│   │   ├── evidence_lineage.py            # 9 HopKinds, no SIGNAL member; CANDIDATE deliberately
│   │   │                                 #   absent from the backward chain (F-1, F-4)
│   │   └── temporal_observation.py
│   ├── semantic/
│   │   ├── blocking.py                    # thin TypeHypothesis today
│   │   ├── contracts.py                   # RelationRef, TypeAssertion
│   │   ├── vocabularies.py                # type vocabulary / mapping architecture
│   │   ├── type_vocabulary.py             # NEW — bounded versioned core:*/value:* pack
│   │   └── operators.py                   # known operators, explicitly not a closed universe
│   ├── events/
│   │   └── dlq.py                         # QuarantineStore; purge reachable from a live route (F-2)
│   └── tests/{constitution,contract,integration,unit}/   # 47 files; constitution/ has 4 modules
├── interpretation/
│   ├── extractors/
│   │   ├── types.py                       # TypedMention.kind: str — the only type surface today
│   │   ├── relations.py                   # RelationalReading.to_candidate(): a dead 2nd path
│   │   ├── registry.py
│   │   └── signals/
│   │       ├── signal.py                  # binary; SignalKind overloads; asserts_something
│   │       ├── protocol.py                # run_producer, _stamp, assert_bounded; the origin of
│   │       │                             #   the tenancy-as-IV mis-cite at :299 (F-4)
│   │       ├── lexical.py                 # synthetic surface:* refs; dead MAX_PAIRS_CONSIDERED
│   │       ├── links.py                   # anchor:*/href:*; pairs_considered = scanned//16
│   │       ├── tables.py                  # TableExtractor + ListExtractor; zip(strict=False)
│   │       └── metadata.py                # attribute:*/jsonld:* subjects; document:current
│   ├── mention_index.py                   # NEW — pre-resolution mention binding seam
│   ├── pipeline.py
│   └── tests/                             # 14 files (contract/ and others)
├── control-plane/
│   ├── semantic_path/
│   │   ├── assembly.py                    # _arity_of majority vote; reading_key; no production
│   │   │                                 #   caller; sorts signals by hand at :253
│   │   ├── execution.py                   # 14 stages, no production caller
│   │   ├── corpus.py, corpus_cases.py, signal_corpus.py, signal_corpus_baseline.py
│   │   └── record_corpus.py
│   ├── services/
│   │   ├── capture_interpretation.py      # an activity of the investigation workflow, not a user
│   │   │                                 #   entry point (FR-161)
│   │   ├── entity_pipeline.py             # run_live_entity_pipeline has no investigation_id (VI)
│   │   ├── layer0_pipeline.py             # DELETED (FR-172); the four hook Protocols are retained
│   │   │                                 #   on the investigation path
│   │   ├── acquisition_loop.py            # DELETED (FR-172) — SSRF by construction (VII)
│   │   ├── dispatcher.py                  # KEEP-AND-WIRE; fabricated score vector corrected
│   │   ├── policy_service.py              # KEEP-AND-WIRE; one tenant deep (VII)
│   │   ├── audit.py                       # KEEP-AND-WIRE as a durable sink (VII)
│   │   ├── cc_cursor_materialization.py
│   │   └── search_backends.py             # holds the process-wide InMemoryGraphStore
│   ├── workflows/
│   │   ├── temporal_materialization.py    # the one registered workflow and activity
│   │   ├── investigation.py               # DELETED (FR-172) — unregistered, 2 non-existent
│   │   │                                 #   activities, unrunnable signal call (F-3)
│   │   ├── investigation_lifecycle.py     # NEW — the Process-Centric entry point (FR-161…164)
│   │   └── worker.py                      # gains the workflow and all eight activities
│   ├── db/
│   │   ├── schema.py                      # 020 tables + AuditLog(Base) with no writer
│   │   ├── relation_claim_store.py        # SqlRelationClaimStore, 0 importers
│   │   ├── relation_signal_store.py       # NEW — no repository exists for the 020 tables
│   │   └── migrations/versions/            # 014…020; 020 is HEAD and forward-only; 021 is owed
│   ├── api/routes/                        # 22 modules, 120 route decorators
│   └── tests/{unit,integration}/          # 41 files
├── projection/
│   ├── graph/
│   │   ├── abstraction.py                 # GraphStore(Protocol) + InMemoryGraphStore
│   │   ├── neo4j.py                       # Neo4jGraphStore — never imports the driver
│   │   ├── snapshot.py                    # RebuildableGraphStore — unwired
│   │   ├── relation_store.py              # GraphProjectionBridge — unwired
│   │   └── adjacency.py
│   └── tests/                             # 17 files
├── acquisition/
│   ├── stream.py                          # capture_with_observations(): 1 caller, no production path
│   ├── registry.py, cc_plan.py, cc_extract.py, entity_search.py, source_query_set.py
│   ├── worker-http/, worker-browser/      # Rust crates
│   └── tests/{contract,integration,unit}/
├── admission/                             # engine/admission.py mints admission_id from uuid4
├── science/  zero/  bulk-ingestion/  feedback/    # no importers of extractors
├── deploy/docker-compose.yml              # infrastructure only; no app or test services
└── webapp/                                # vite; not a workspace member; out of scope

docs/adr/                                  # 0025…0028 owed; 0024 is the current highest
```

**Corrections to the previous structure listing**: `apps/acquisition/adapters/{sec_edgar,
common_crawl}.py` **does not exist** and has been removed from this tree; the route layer is 22
modules and 120 routes, not 24 and ~122; `shared/tests` is 47 files, not 43;
`control-plane/tests` is 41, not 40; `interpretation/tests` is 14 files and has **no** `unit/`
subdirectory; `signal_corpus_baseline.py` and `projection/graph/adjacency.py` were missing; and
the old tree listed four artefacts as missing when three of them — `tasks.md`,
`research.md`, `data-model.md` — and `checklists/requirements.md` all exist, measured above.

**Structure Decision**: the existing `uv` workspace is kept exactly as it is. This feature adds no
new app and no new top-level directory. New code lands in the app that already owns the concern —
domain value types in `apps/shared/domain` and `apps/shared/semantic`, extraction in
`apps/interpretation`, lifecycle and persistence in `apps/control-plane`, graph projection in
`apps/projection`, acquisition wiring in `apps/control-plane/workflows`. The only structural
additions are a small number of new modules (`predicate_signature.py`, `type_vocabulary.py`,
`mention_index.py`, `relation_signal_store.py`, `investigation_lifecycle.py`) plus `contracts/`
under the feature directory and four records in `docs/adr/`. Justification for not introducing a
new app: the concern is already split across exactly the apps that own each stage, and the
constitution's layering is a *dependency* rule (`interpretation` must not import
`admission`/`projection`) which the current workspace already enforces by declaration — a new app
would add a boundary without adding a constraint.

## Complexity and risk

> **Correction (2026-09-27).** The previous revision of this section read *"No constitutional
> violations are being accepted."* That was false, and false in the way that mattered: it is the
> sentence that would have surfaced the Principle **II** defect. The corrected gate above records
> four `violated` Core Principles, two `violated` Invariants, one `violated` baseline clause, four
> `violated` Additional Constraints and three `violated` Governance clauses. No `violated` row is
> *accepted* — each is closed by a named requirement.

Two items are recorded because they look like violations and are not:

| Item | Why it looks like a violation | Why it is not |
|---|---|---|
| `RelationSignal._material()` keeps `producer_ref` | It means two producers reading one structure get different `signal_id`s, contradicting three docstrings | Domain Invariant 3: corroboration counting needs producer identity. The docstrings are wrong, the behaviour is right. The *new* defect — `extra`/arity being excluded — is fixed separately under FR-089. |
| Bounded `core:*`/`value:*` type vocabulary, open relation space | A closed type list could read as a fixed ontology | §104 asks for exactly this asymmetry, and the vocabulary is a blocking/mapping/validation instrument rather than an extraction gate — an unknown type stays `UNKNOWN`. |

### Risk register

| Risk | Detail | Mitigation |
|---|---|---|
| **No CI at all** | `.github/` does not exist. Governance requires `Compliance is verified on every PR/review`; the gate is run by hand from `docs/CONTRIBUTING.md:37`. A constitutional-layer change is gated by a person remembering. | FR-168 requires CI, or failing that a dated, named attestation with per-suite failure counts, and forbids the word `verified` for any check that was not run. |
| **No Makefile, tox, nox or test-runner** | There is no single command that runs the whole gate. The canonical form is per-app and must be repeated eleven times by hand, and its per-app result is not aggregated anywhere. | FR-168. A gate with eleven invocations and no aggregator is a gate whose result depends on how many times the operator pressed enter. |
| **22 tests never execute** | MinIO, PostgreSQL and tantivy are absent, so 22 tests self-skip instead of failing: 10 in `acquisition` (MinIO), 2 in `feedback` (Postgres), 2 in `bulk-ingestion` (MinIO), 1 in `projection` (a module-level `pytest.importorskip("tantivy")` that skips the **entire file**'s assertions about tenant isolation, idempotent writes and provenance), and 7 in `control-plane` needing a live PostgreSQL/dev stack. A green run proves 558 of 572 for the small apps, not 572. | Any DB-dependent verification is reported `verified only offline` and never as `verified`. If Docker is ever started the shared baseline changes to roughly 11 failed / 571 passed / 3 skipped — **re-baseline before trusting any comparison**. |
| "Complete" could be claimed on a test-only harness | The 019 lifecycle has **no production caller**; `ExecutionRequest.producers` is never assigned; `lexical_signals` has never run | FR-100 makes the live `interpret_warc_capture` seam mandatory. FR-084 governs the completion report: it forbids a completion report that claims `complete` while a check was not run, and requires the report to distinguish implemented, verified and verified-only-offline |
| **FR-100 wires an entry point that is not constitutional** | The seam is real and is the right seam, but the function that reaches it has no `investigation_id`, and Principle **VI** names an Investigation as the subject | FR-161 nests the seam inside `InvestigationWorkflow` and makes that workflow the only production entry point. **FR-100 alone is insufficient** and is superseded in part for the entry-point question. ADR-0025. |
| **Registration has been claimed repeatedly and was false every time** | `InvestigationWorkflow`, `SqlRelationClaimStore`, `RebuildableGraphStore`, `GraphProjectionBridge`, `InterpretationPipeline` and `Neo4jGraphStore` are all present and unwired | The registration requirement's test reads the worker's own `workflows=` / `activities=` lists. A claim of availability that no test reads is not a claim. |
| **Twenty-six constitutional citations name the wrong numeral** | Tenancy-as-IV at 20 sites (the origin is a code comment at `protocol.py:299`) and determinism-as-VI at 6; one of the 26 is the constitution test suite's own filename | FR-173 test-enforces the correct numeral everywhere and renames the mis-cited test module. A gate that cites the wrong clause is not a gate. |
| **Migration ordering** | `021` adds 23 columns whose ORM enums and writers do not exist yet; the store is the half that matters and the migration is the easy half | The persistence ordering section above makes the dependency explicit and puts `021` in P8's entry gate, after the domain types. |
| **The boundedness guarantee is currently unmeasured** | Two producers fabricate `pairs_considered` and the third always reports `0`, so `max_pairs_considered` is policed against an invented number or not policed at all | FR-093 requires a real count or a stated `0` with a reason, and makes the ceiling live. |

## Phase 0 research — status

`research.md` and `data-model.md` both exist. Decisions recorded there:
parser choice (R-001), signature-as-identity (R-002), bounded type vocabulary / open relation space
(R-003), production wiring seam (R-004), migration `021` (R-005), graph backend scope (R-006), and
the baseline freeze (R-000).

**The open-question register has moved.** `research.md` R-007 lists seven questions; their status
is no longer uniform:

| Question | Status |
|---|---|
| Q1 — exact `PredicateSignature` normalisation rule set | **Load-bearing** under ADR-0028: normalising a term of the logical id is an identity decision, not a quality nicety. One test per rule. |
| Q2 — controlled type-space vocabulary vs free-form strings | Open; the §7 open vocabulary is drafted in `data-model.md` §6. |
| Q3 — bounded-neighbourhood scope definition | Open; `Neighbourhood` currently carries a substring-tested `precision` string rather than a real scope. |
| Q4 — whether n-ary identity uses role bindings or positional arguments | **CLOSED.** Answered by A2 D2/D4: structural `canonical_argument_slot` ordering, with `commutative_slots` as the only commutation marker, and multiplicity preserved. `T112` is the task that carries the answer, so it is a build task and not a decision to be made; `tasks.md`'s own Q4 register names `T112` as the task Q4 blocks. **No task owns the "record Q4 as an ADR" obligation** — see the report's `[NEEDS-OTHER-FILE]` list. (Distinct from A2's epistemic-axes Q4, which `ARBITRATION.md` §3 closes: predicate-level conflict and candidate-level structural conflict are different axes, are never collapsed, and a structural conflict that is not a denial yields the new `assembly_state = CONFLICTING` rather than `candidate_status = CONTRADICTED`.) |
| Q5 — producer ↔ lifecycle import direction | Open; belongs with P6. |
| Q6 — whether the `InterpretHook` seam is the intended binding point | **CLOSED in substance** by the dead-code disposition above: the seam's orchestrator is deleted and the four hook Protocols are retained on the investigation path, so the question is answered by construction rather than by argument. |
| Q7 — whether `source_temporal_observation` gets a repository in 021 | Open; default is yes, and it is now an **entry condition of P8** rather than a Phase-9 task, because a projection with nothing to rebuild from is the Principle **III** violation. |

**`TypeSignal` provenance is closed as a decision, not left open.** A5's `OQ-A5-6` is **closed by
`ARBITRATION.md` §7**: `source_vocab` is an external vocabulary reference **or `null`**; it answers
*"whose semantic system said this"*, while `producer_ref` / `producer_version` are independent
coordinates answering *"which instrument did we extract it with"*. **No synthetic vocabularies** —
`local`, `internal`, `regex` and `ner` must not be introduced to avoid a `null`. A detector that
reads no external vocabulary has `source_vocab = null`, which is what makes the §8 families that
legitimately have no vocabulary legal. A5's own withdrawn `TypeSignalSource` enum stays withdrawn:
it duplicated `source_vocab` + `producer_ref`.

**FR renumbering is unnecessary, and the append count is now measured rather than inherited.**
All 100 numeric ids `FR-001`…`FR-100` are present with **zero gaps**, so there is nothing to
renumber and `ARBITRATION.md` §1 is satisfied. The namespace work that remained is **2 folds**
(each letter-suffixed id folds into its allocated numeric slot — the `FR-035` slot and the `FR-040`
slot respectively; a folded id is tombstoned and MUST NOT be cited as a live normative target) and
**1 move** (`FR-082`, which was stranded after `FR-100` in document order). **Appends: 47, not
29.** The earlier "29 appends" was A8prep O2's pre-§14 estimate; §14 withdrew §1's deferred
instruction and replaced the target space with seven disjoint bands, and the current `spec.md`
carries **53** defined ids above `FR-100`: the 6 already-live `FR-110`…`FR-115` (§14 rule 3) and
**47** §14-band appends — A4b 8 (`FR-130`…`FR-137`), A5 10 (`FR-140`…`FR-149`), A7 9
(`FR-150`…`FR-158`), A1 13 (`FR-161`…`FR-173`), A2 5 (`FR-174`…`FR-178`) and A6 2 (`FR-179`,
`FR-180`). §14's table counts A7's range as 11 and its total as 49; A7 authored 9 and 47 are
applied, so the discrepancy is §14's arithmetic (see **Scale/Scope**), not an unapplied
requirement — nothing is minted here, because §14 rule 1 forbids it. The 4 slots retired inside
`FR-001`…`FR-100` are tombstone records in `spec.md`, not requirements, so of the 100 numeric
numbers **96 carry a live requirement and 4 are historical records** — the previous revision's
"51 of the 100 … never change" was A8prep's pre-§14 arithmetic over a 102-id baseline and
understated the surviving set on every axis. What makes parallel requirement work safe is
unchanged and is now stronger: no number moves, so no two authors can collide on one.

## Still owed before the §100 deliverables gate

- `docs/adr/0025`…`0028` — four records, not one; full text in `repair/A1-constitution-investigation.md` §D5
- `contracts/` — the producer protocol, the mention-index contract and the store contract
- `checklists/requirements.md` — it currently maps **zero** of the feature's FRs (it has no FR
  column at all), so the FR verification map is still owed
- `quickstart.md` — the commands that actually work, including the eleven per-app invocations
- CI, or the dated named attestation FR-168 accepts in its place
