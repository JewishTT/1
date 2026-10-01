# Implementation Plan: Acquisition Integration — Five Runtime Families on One Capture → Observation → EventEnvelope Seam

**Branch**: `023-acquisition-integration-searxng` | **Date**: 2026-09-29 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/023-acquisition-integration-searxng/spec.md`
**Directive**: `specs/023-acquisition-integration-searxng/input.md` — 204 sections, source of truth (§-numbers below are its sections). Where this plan and `input.md` differ, `input.md` wins. `§196` fixes the execution order and is not deviated from.

**Baseline (verified at `fe3eb448`, not re-derived)**: 118 untracked paths, 0 modified tracked files. Docker Desktop availability **UNKNOWN** — this plan provisions for starting it and never assumes it is up.

---

## Summary

The platform has a declarative acquisition layer, an `ObservationGate`, a protobuf `EventEnvelope`, a `Capture` value type, a Redpanda/Kafka path — and **zero runtime integrations that have ever completed the path from a real external source to a really-processed downstream observation**.

Two defects block everything (spec D1/D2, §4):

1. `apps/shared/events/observation_gate.py:74` mints `observation_id = "OBS-" + uuid.uuid4().hex[:12]`.
2. `apps/acquisition/sources/connector.py:143-171` builds a plain dict and `apps/acquisition/worker_acquisition.py:366-377` publishes it as `json.dumps(...)`; `ObservationGate`/`EventEnvelope` are never reached from the live path.

§196 forbids building the five runtime integrations on a broken seam. The plan therefore fixes the seam first, end to end, then adds five runtime families onto a single contract, then proves each one with a real source → real event → real consumer → real persisted result.

**Technical approach, in one paragraph.** One frozen `AcquisitionArtifact` (§5, unchanged) is the only thing a runtime emits; a declarative `SourceDefinition`/`ToolDefinition` carries `worker_ref`, `runtime_ref`, `source_family`, `time_basis`, `resource_class` and limits; the dispatcher resolves `runtime_ref` by name and uses capabilities only as a compatibility check (§13/§57); a single `ObservationGate` computes `OBS-{digest128(identity_schema|tenant_id|capture_id|locator|record_digest)}` and one `RecordLocator` grammar resolves a record back out of stored raw bytes with no network (§10/§11/§132/§174); the broker receives a refs-only canonical `EventEnvelope`; a real consumer in `apps/interpretation` reads `raw_ref`, resolves the locator, parses through the already-written `parsers/payload` + `extractors/payload` seam, and writes a `ProcessingResult` with a concrete `derived_ref`.

---

## Technical Context

**Language/Version**: Python 3.11–3.13 (`requires-python = ">=3.11,<3.14"`); Bash/PowerShell for the 15-phase procedure (constitution "Script type: PowerShell on Windows"); the acquisition substrate also has Rust crates (`dispatcher/src/`, `contracts/src/`) that are **not** touched by this feature.

**Primary Dependencies**: `confluent-kafka` (reaches `apps/acquisition` transitively via the `cognitive-shared` workspace dep — **not** declared in `apps/acquisition/pyproject.toml`; add it explicitly, decision D-11), `httpx`, `pydantic`/`pydantic-settings`, `sqlalchemy`+`asyncpg`+`alembic`, `pytest`/`pytest-asyncio`. Airbyte connectors are executed as OCI images, never as a Python dependency. BBOT and SearXNG likewise.

**Storage**: MinIO / S3-compatible ObjectStore for raw (`raw/{tenant}/{yyyy}/{mm}/{sha256}` via `storage/s3.py:ObjectStore.put_raw_dedup`); PostgreSQL 16 for `captures`, `observations`, `processing_results`; Confluent Kafka (9092, `core`) **and** Redpanda (19092, `streaming`) are both already in `apps/deploy/docker-compose.yml` — see decision D-01 and Open Decision O-1.

**Testing**: `pytest` with `asyncio_mode = "auto"`. Six test classes per runtime (§152): Unit, Fixture, Process, Redpanda, Live, Replay = 30 cells. Live tests carry `@pytest.mark.live_integration` (§76) and are **never** auto-skipped.

**Target Platform**: Linux containers for the five runtimes; Windows 11 + Docker Desktop for the operator/host. Host-side code is cross-platform; the sandbox path is Linux-container-based (see D-07).

**Project Type**: multi-app platform — this feature lands in `apps/acquisition`, `apps/shared`, `apps/interpretation`, `apps/control-plane` (migration), `apps/deploy`, `bench`.

**Performance Goals**: §170/§171/§172 — no unbounded memory, no runaway process, no Kafka backlog runaway, no raw-to-Kafka blob transfer, no O(N²) routing. Bounded RSS during a 50k-record Airbyte `read()`; a bounded stdout parser that never accumulates a run; streamed, bounded ObjectStore writes; `STATE` processing that cannot block the connector; publish that cannot block the connector.

**Constraints**: §66 backpressure is `backlog ↑ → acquisition rate ↓` (never the reverse). §65 no Docker socket, no host FS, no host credentials, no platform secrets, no unbounded egress to any tool. §30/§184 no secret value in Redpanda, logs, envelopes, capture metadata, argv, config digests or git.

**Scale/Scope**: 215 FRs, 22 work packages (§195), 5 runtime families, 6-column × 5-row acceptance matrix (§194), 8 mandatory final artifacts (§201).

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design. Verdict: **PASS**, with two items referred to ADRs and one that cannot be fully satisfied inside this plan — named at the end of this section.*

### Principles I–VII

| # | Principle | Verdict | FRs that satisfy it | Where it is enforced / what fails |
|---|---|---|---|---|
| I | Observation-Immutable Evidence Substrate | **PASS** | FR-029 (no second capture model), FR-040 (`capture_id`/`observation_id` unique), FR-041 (same bytes → same raw object, no overwrite), FR-026 (Capture/Observation split), FR-027 (raw independent of the projection), FR-149 (§109 core fields immutable after durable persistence) | `domain/capture.py` `Capture.__post_init__` verifies `capture_id` against its own material; `domain.enforce_observation_immutable`; new `UNIQUE` constraints in migration 021. **Fails if** the `observations.capture_id` column is left nullable or if any run path calls `Capture.from_dict` on a tampered row without the verification raising. |
| II | Evidence-First | **PASS** | FR-003/FR-004 (full chain per family, all ids inspectable), FR-026, FR-126 (§116 provenance `Observation → Capture → Runtime → Source → Tool/version`), FR-131/FR-132 (§117/§157 trace form) | `Capture.to_hop`; `run-manifest.json`. **Fails if** `observations.capture_id` is nullable — an observation without a capture hop is untraceable. |
| III | Projection-First Knowledge Architecture | **PASS** | FR-013/FR-014 (no `tool output → entity/relation/fact`), FR-015 (§118 no `GraphWriter`/`GraphEdge`/`RelationClaim`/`EntityStore`/`KnowledgeGraph` on the acquisition path), FR-016 (§119 no entity resolution in acquisition), FR-017/FR-018/FR-019 (§112/§113/§114 no zero-layer, no frontier, no catalog-as-observation in the runtime), FR-069 (§94 reparse without HTTP), FR-133–FR-136 (downstream rebuilds interpretation from durable raw) | An AST test asserts the new packages import no graph symbol. **Fails if** `runtime/` or the consumer gains a `GraphWriter` import. |
| IV | No Single Store / Graph / Score | **PASS** | FR-027/FR-028 (raw→ObjectStore, refs→broker), FR-123 (§69 refs-only payload), FR-071 (§103 five distinct SearXNG outcomes), FR-087 (§37 fourteen Airbyte failure states), FR-104 (§105 eight Maigret states), FR-090 (§93 STATE≠evidence), FR-102 (§102 4xx≠`results=[]`), FR-101 (`status.is_found()` ≠ `entity_exists`) | `runtime/airbyte.py` `AirbyteFailureCode`; `runtime/external_tool.py` `ToolOutcome`. **Fails if** any collapse-to-binary shortcut is added "for simplicity". |
| V | Plugability by Contract | **PASS** (see N-1) | FR-049/FR-050/FR-051 (§13 explicit runtime, capability as check, `BBOT→http` forbidden), FR-052/FR-053 (§14 `worker_ref`/`runtime_ref` on `SourceDefinition`), FR-055 (§57 dispatch order), FR-075/FR-076 (§24/§25 Airbyte is a protocol, not an HTTP source), FR-097/FR-098 (§40/§41 one `ExternalToolRuntime`) | One registry (`adapters/registry.py`), one protocol shape (`Runtime` ≡ `capabilities()/estimate()/acquire()`), one registration. **Fails if** a second runtime registry is created that the dispatcher does not consult. ADR-0025. |
| VI | Process-Centric | **PASS** | FR-054 (§56 single `InvestigationWorkflow` entrypoint, ids present on the whole path), FR-150/FR-151 (§110/§111 tenant + investigation identity, no `default-tenant` on the live path), FR-127/FR-130/FR-131 (§117/§155/§156 causation + correlation), FR-125 (§71 the trace manifest is itself an operational artifact) | `InvestigationWorkflow` in `apps/acquisition/workflow/`; `correlation_id` threaded scheduler→worker→gate→broker→consumer. **Fails if** any envelope reaches the broker with an empty `investigation_id` on a live run. |
| VII | Security-First | **PASS** | FR-153 (§64 SSRF/DNS-rebinding/redirect/max-bytes/timeouts), FR-154 (§65 no socket/host FS/creds/secrets/unbounded egress), FR-155/FR-156 (§66/§143 resource class + per-tool limits), FR-157 (§144 explicit outbound policy), FR-158 (§145 existing policy layer, no silent bypass), FR-159/FR-160/FR-161 (§146/§147/§148 timeouts, child tracking, separate stdout/stderr caps), FR-082/FR-163/FR-164 (§30/§184/§182/§183 secrets and digests), FR-147/FR-148 (§107/§108 quarantine, no auto-drop), FR-171/FR-172 (§134/§135 metric labels carry no secret or raw user data) | `runtime/sandbox.py`, `runtime/limits.py`, `shared/security.py`, `donors/estorides/estorides_core/ssrf_guard.py` (adapted). **Fails if** a tool is launched with any bind mount, or `--cap-add`, or without `--read-only`. |

### Domain Invariants 1–12

| # | Invariant | Verdict | FRs | How it is checked |
|---|---|---|---|---|
| 1 | Observation is immutable | **PASS** | FR-149, FR-040 | `observations` core columns have no UPDATE path; `enforce_observation_immutable` raises. `processing_results` is a separate table, so processing state never overwrites the observation. |
| 2 | Mention ≠ Candidate ≠ Entity | **PASS** | FR-013, FR-014, FR-015, FR-016 | Acquisition emits `ObservationRecord` only. The consumer's output is a `ProcessingResult`; mention/candidate minting stays behind `domain/mention_occurrence_index`. |
| 3 | Assertion ≠ truth | **PASS** | FR-014, FR-020 (§115), FR-101 | Provenance schema carries `producer`/`producer_version`/`tool`, so a record states it is an observation of a tool's execution output. |
| 4 | Graph ≠ source of truth | **PASS** | FR-015, FR-117 | Same as Principle III. No graph import exists in the new code; the import-check test fails the build. |
| 5 | Kafka ≠ object store | **PASS** | FR-027, FR-028, FR-123 | `enforce_no_blobs(body, max_inline=1024)` on every publish; `enforce_no_blobs` is a hard raise. Payload is `{capture_id, observation_id, raw_ref, locator, tenant_id, investigation_id, source_id, task_id}`. |
| 6 | TDA ≠ truth oracle | **PASS** (negatively evidenced) | FR-013, FR-015, FR-017, FR-020 | This feature mints no topological feature. A test asserts the new packages import neither `gudhi` nor `giotto_tda` and emit no `TopologicalFeature`. |
| 7 | Admission ≠ Priority | **PASS** | FR-134 | `ProcessingResult.status` is an outcome word (`processed`/`failed`/`quarantined`) and the row carries `derived_ref`; no score, no rank, no priority column exists on the new tables. §85's "status = processed is permissible but a link to a concrete result is mandatory" is exactly this invariant. |
| 8 | Entity novelty ≠ evidence novelty ≠ structural novelty | **PASS** | FR-074 (§176 new capture, no overwrite), FR-090 (§178 full refresh ⇒ new occurrences), FR-095/FR-096 (§177/§178), FR-072 (§139 duplicate policy explained separately) | `Capture.payload_key` vs `capture_id` — the two counts stay separate by construction. |
| 9 | Search ≠ Graph traversal ≠ OLAP | **PASS** | FR-133, FR-135, FR-136 | The consumer's entire input set is `{envelope, observations row, raw_ref, locator}`. No graph read, no search read, no ClickHouse read. |
| 10 | Acquisition throughput ≠ intelligence throughput | **PASS** | FR-005 (§198), FR-193/FR-194/FR-195/FR-196/FR-197/FR-198 (§137–§142), FR-173 (§136 lag) | Reconciliation counts four independent numbers — `source records`, `observations durable`, `Redpanda events`, `downstream processed` — and green requires the last one. An event present but unprocessed is `FAIL`, not green. |
| 11 | The fastest request is the request correctly avoided | **PASS** | FR-038 (§96), FR-069 (§94), FR-167/FR-168 (§132/§133), FR-010/FR-011 (§153/§161) | `replay_observation(observation_id)` reads `raw_ref` only; a test asserts zero network calls on that path (transport is a refusing sentinel). A fixture never substitutes for a live source. |
| 12 | All downstream projections must be rebuildable from durable evidence/events | **PASS** | FR-069, FR-167, FR-168, FR-170 (§95), FR-200 (§169) | Raw is the source of truth; unknown fields retained (§62); parser version on every observation (§63); `same raw capture → reparse → different interpretation version` needs no refetch. |

### N-1 — Principle V, the one item that needs a signature

Principle V names `AcquisitionWorker` (`capabilities() / estimate(task) / acquire(task)`). §13/§25/§40 require `runtime_ref`, an async-iterator `run()`, and `spec/check/discover/read` — a shape `AcquisitionWorker` does not express.

**Decision**: keep the interface shape and keep the registry. `apps/acquisition/runtime/base.py` defines `Runtime` with `capabilities() / estimate(task) / acquire(task)` (async generator) — structurally identical to `AcquisitionWorker` plus a streaming `acquire`. `adapters/registry.py::SourceRegistration` gains `worker_ref: str = ""` and `runtime_ref: str = ""` (both defaulted, so the 146 existing catalogue registrations are untouched). `AcquisitionWorker` becomes a thin adapter over `Runtime` so any existing consumer keeps working. Recorded as **ADR-0025**.

*If the user rejects the adapter reading*, Principle V is in violation in its letter and this becomes a constitution amendment request, not a plan change. **This is a user decision (O-2).**

### N-2 — the one item that cannot be fully satisfied here

The **Technology Baseline** names "Event backbone: Apache Kafka (KRaft)". The directive says "Redpanda" in §0.1, §67, §70, §75, §127, §136, §159, §190, §204 and nowhere mentions Kafka. Compose runs both. They cannot both be the canonical backbone.

**Bounded decision D-01 (runnable now)**: the acceptance run points the existing `confluent-kafka` client at Redpanda by setting `KAFKA_BOOTSTRAP_SERVERS=localhost:19092` and running the `streaming` profile. Redpanda is wire-compatible; the platform code has no broker-brand branch; therefore the §0/§204 gate is satisfiable unchanged, and no Kafka code is modified. **What this does not settle**: the permanent topology. That is Governance's "Kafka vs alternatives" and needs **ADR-0026**, signed by the user (**O-1**).

---

## Decisions (each with the rejected alternative)

| # | Decision | Rejected alternative | Why |
|---|---|---|---|
| **D-01** | Acceptance runs against Redpanda (`streaming` profile, `:19092`) via `KAFKA_BOOTSTRAP_SERVERS=localhost:19092`; no code change. | Move the canonical backbone to Redpanda permanently / point acceptance at Kafka `:9092` and re-read the directive's "Redpanda" as loose usage. | The directive's gate names the artifact, not the product. Redpanda is wire-compatible so the gate is satisfiable with one env var and zero code risk. The permanent choice is an ADR, not a plan. → O-1 |
| **D-02** | `AcquisitionArtifact` is **exactly** the 13 fields of §5, frozen, unchanged. `source_family` and `time_basis` are **declarative fields on `SourceDefinition`/`ToolDefinition`**, read by the artifact sink when it constructs the `Capture`. | (a) Add `source_family`/`time_basis` to the frozen dataclass; (b) infer them from the `runtime_ref` string prefix. | (a) makes transport make a semantic decision — AGENTS.md §2 forbids exactly that, and it puts identity material in five runtimes' hands. (b) is guesswork, and §97 forbids a non-declared derivation reaching an id. Declarative beats both. `Capture.__post_init__` still refuses an undeclared basis, so a definition that omits it fails closed. |
| **D-03** | `ObservationGate` is **repaired in place**, not extended alongside: `observation_gate.py:74` is replaced by `observation_identity(...)`; `ingest()` keeps its signature; `ingest_capture()` and `ingest_record()` are added as siblings; `observation_gate.py:106`'s `evt-{sha256}-{lifecycle}` is replaced by `deterministic_event_id(...)`; `kafka.py:49`'s `uuid4()` fallback gets a `require_deterministic_event_id: bool = False` keyword that the gate and the scheduler pass as `True`. | A new `DeterministicObservationGate` beside the old one. | §160 lists "observation_id random" as a release blocker. A parallel path leaves the random id reachable from `ingest()`, so the blocker is not cleared. Also: making `event_id` a *required* positional in `build_envelope` would touch 22 call sites across 8 apps, most outside §196's scope, for zero gate benefit — the guard flag clears the same blocker with one signature addition. |
| **D-04** | One `RecordLocator` grammar, one parser, one resolver, five schemes: `json:results[N]`, `airbyte:message:N` \| `airbyte:stream=<ns>/<stream>:record:<n>`, `bbot:event:N`, `spiderfoot:event:N`, `maigret:site:<canonical>`, `blob` (empty body, the blob-level parent record). `apps/shared/events/record_locator.py`. | Per-family free-form locator strings with per-family resolvers. | Five parsers is five chances to drift, and §96 requires determinism over the locator. One grammar makes `resolve()` total and makes `observation_id` material uniform. |
| **D-05** | `record_digest = SHA256(canonical_json(record).encode("utf-8"))` where `canonical_json` = `domain.relation_identity.canonical_material` semantics **pinned explicitly**: `sort_keys=True`, `separators=(",",":")`, `ensure_ascii=False`, `allow_nan=False`, after `_normalise` (datetime→isoformat, set/frozenset→sorted list, StrEnum→value, unknown→`str`). | `json.dumps(..., sort_keys=True)` with `ensure_ascii=True` (the default). | `ensure_ascii=True` makes the digest a function of the transport encoding, not the text: `"é"` and `"é"` must be one record's digest, not two. `allow_nan=False` because `NaN`/`Infinity` are not facts and would serialise to a token another language cannot parse. The `_normalise` pass is what makes a donor's `set`/tuple/datetime order-independent (§97). |
| **D-06** | The downstream consumer is a **new service in `apps/interpretation`**: `apps/interpretation/observation_consumer/`. It imports its own `parsers.payload` and `extractors.payload` directly — the seam ACQ-18 must reach, which today no non-test code calls. It never refetches. | (a) Put the consumer in `apps/acquisition`; (b) create a fourth "consumers" app. | (a) inverts the layer arrow: `parsers/payload/__init__.py` states the parser layer does not import `sources`, and the parser layer is *below* acquisition. Acquisition importing interpretation would make acquisition depend on a semantic layer, and §118/§119 then become hard to keep. (b) duplicates the interpretation app. `apps/interpretation` already owns the parser/extractor/mention seam, and §22's "SearXNG observation decoder → structured observation → discovery/mention producer" is its job. |
| **D-07** | External-tool isolation = **host-run `ToolRunner` service → Linux container**. The runner shells to the `docker` CLI using the host's Docker context; the engine pipe/socket is **never bind-mounted into any container**; the tool container gets an explicit argv array, no mounts, `--read-only`, `--cap-drop ALL`, `--security-opt no-new-privileges`, `--pids-limit`, `--memory`, `--cpus`, `--network <policy>`, tmpfs scratch, `--rm`. | (a) A containerised runner that mounts `/var/run/docker.sock`; (b) bare host process, no container. | (a) is the exact configuration §65 names, and on win32 the engine is a named pipe `\\.\pipe\docker_engine` rather than `/var/run/docker.sock`, so the socket path is host-specific — the `docker` CLI abstracts it and nothing is mounted. (b) is §42's "direct embedding", admissible only *after* the isolated runtime succeeds, and it cannot give CPU/memory/pid/network containment. Container is the production branch; a bounded process executor exists behind the same interface for offline protocol tests only and must be recorded as `isolation: process` in the run manifest. |
| **D-08** | One registry, one protocol: `adapters/registry.py::SourceRegistration` gains `worker_ref`/`runtime_ref` (defaulted `""`); `REGISTRY.resolve_explicit(task)` resolves by `runtime_ref` and then **validates** capabilities; `Dispatcher.schedule` takes the explicit branch when `task["runtime_ref"]` is present, the legacy capability branch otherwise. Runtimes live in `apps/acquisition/runtime/` (singular). | (a) A new `RuntimeRegistry` the dispatcher never consults; (b) inferring `runtime_ref` from `execution_class`. | (a) leaves the scheduler inferring, which is the §13 failure. (b) is the forbidden `BBOT → capability=http → HttpWorker` route by another name. Defaulted fields keep the 146 existing catalogue sources on the legacy path untouched. |
| **D-09** | Migration `021_capture_observation_persistence`, `down_revision = "020_universal_relation_extraction"`, forward-only, additive. New `captures` and `processing_results` tables; `observations` gains `capture_id` / `locator` / `record_digest` / `record_metadata` / `event_id`. Legacy backfill uses `time_basis = ABSENT`, `fetched_at = NULL` — the honest basis, because the migration knows when it wrote the row, not when anything was fetched. | (a) Leave everything in JSONB on `observations`; (b) backfill with `time_basis = FETCH, fetched_at = created_at`. | (a) is forbidden by §122 and breaks durable query/reconstruction. (b) is exactly the conflation `capture.py` refuses (`fetch_fetch_time_substituted`): `created_at` is a row-write time, not a fetch time. `ABSENT` + NULL is a stated absence. |
| **D-10** | `observation.processed` is **added** to `EVENT_CATALOG` at version `1.0` on topic `observation`, registered in `events/registry.py`. `observation.created` stays at `2.0` with unchanged semantics. | Republish `observation.created` at `3.0`; or skip the event and use only a journal. | (a) breaks the §157 trace example and invalidates any existing consumer for no gain. (b) §85 names the event as an option *or* a durable journal — but §156 requires a causation chain, and a chain needs an event. Adding a *new* type, not changing an existing version's meaning, is what §121 demands. |
| **D-11** | `confluent-kafka` is declared explicitly in `apps/acquisition/pyproject.toml`, and `live_integration` is added to `[tool.pytest.ini_options] markers`. | Rely on the transitive `cognitive-shared` dep; reuse the existing `live` marker. | A transitive dep that the code imports directly is an undeclared dependency (packaging correctness). `live` is already used for "needs broker + egress"; §76 names `live_integration` exactly, and the release-validation guard keys on the marker name. |
| **D-12** | SearXNG production pagination lives in a `SearXNGRuntime` that owns content-derived stop conditions; `HttpSourceExecutor.capture` is **not** modified. | Patch `executor.py:220-255` to add a content-aware stop. | `executor.py` serves the 146-entry catalogue under a uniform `Pagination` contract, and §19 forbids body-emptiness as a stop rule — a change there would silently alter every legacy source's page count. The SearXNG-specific rule belongs in the SearXNG runtime; the shared executor keeps its documented contract. |
| **D-13** | SearXNG, Maigret, BBOT, SpiderFoot run as **containers**; **Airbyte** runs connector **images** one `docker run` per invocation (the connector *is* the image). A `ToolDefinition` may declare `isolation: process` for offline protocol tests. | Build BBOT/Maigret/SpiderFoot as Python deps in the worker. | §42 requires the isolated boundary for the first production branch; dependency isolation and version pinning are two of the six reasons it gives. Airbyte's image is not a choice — it is the connector. |
| **D-14** | The acquisition worker and the `ToolRunner` stay **host-run**; only the five tool runtimes are containers. | Containerise the acquisition worker too. | It keeps the Python app on the operator's machine where `InvestigationWorkflow` runs, avoids a second parallel infra stack (§126), and keeps secrets handling inside the app. §65's path `Acquisition Service → dedicated runner → isolated container` is satisfied. |
| **D-15** | Existing estorides catalogue YAML stays the source corpus; the five new definitions live in `apps/acquisition/runtime/definitions/` and are **adapted** to the existing loader, not copied literally. | Copy the estorides `20_system_tools/kali_maigret.yaml` shape verbatim. | §16 says so explicitly. And `catalogue.py` is the registry layer (§58): donor YAML may be a data source but may not determine entity/relation/claim/admission (FR-023). |

---

## Donor reuse (AGENTS.md §1 — what is taken, what is written fresh)

Searched: `donors/` (99 projects), `donors/estorides/estorides_core/` (49 modules), `apps/*` for existing seams. Findings:

**Present in `donors/`:** `maigret/` (full upstream, incl. `maigret/maigret.py`, `maigret/result.py`, `maigret/sites.py`, `maigret/settings.py`, `sites.md`, `Dockerfile`), `spiderfoot/` (full upstream, incl. `sf.py`, `sfscan.py`, `sflib.py`, `modules/`, `correlations/`, `Dockerfile`, `docker-compose*.yml`).
**Absent from `donors/`:** any BBOT tree, any Airbyte tree, any SearXNG tree. Confirmed by directory scan. → those three are image-pinned integrations, not code transfers.

### Taken from donors (adapted, not rewritten)

| Component | Donor module | What is taken | Repair on transfer (AGENTS.md §2) |
|---|---|---|---|
| SSRF / DNS-rebinding guard | `donors/estorides/estorides_core/ssrf_guard.py` (270) | `check_url`, `assert_safe`, `GuardResult`, the allowlist loader, the v4+v6 blocked-range tables | Replace the module's own env-var allowlist with `apps/shared/security.py::EgressPolicy` so the policy layer is the single source (donor reads env directly). Keep `SSRFError`. |
| HTTP client, cache, circuit breaker | `.../async_client.py` (454) | `AsyncClient`, `ResponseCache`, `CircuitBreaker`, `sync_fetch`, SOCKS handling, `_redact_proxy` | `ResponseCache` key must include tenant + source + credential context + request (§100). Donor keys on URL only — that is the exact `query A → cached result of query B` bug the platform already fixed in `catalogue._flatten_params`. Reject, don't inherit. |
| Pagination param construction | `.../pagination.py` (124) | `PaginationConfig`, `build_page_params`, `extract_cursor`, `count_results` | `count_results` is exactly the "inspect the result collection" primitive §19 requires. `extract_cursor` is **not** used for SearXNG (SearXNG paginates by integer `pageno`), but is kept for the generic `HttpRuntime`. |
| Source definition loading | `.../source_loader.py` (371) | `Source` / `SourceRegistry` shape — the declared-field set and the corpus-driven loading model | Not imported. `apps/acquisition/sources/catalogue.py` already **is** this module, adapted, with the six upstream schema defects corrected. Reusing the donor's own loader would regress those fixes. |
| Tool CLI invocation | `.../tool_runner.py` (~230) | `SHELL_METACHAR_RE`, `_check_injection`, `_check_allowlist`, `ToolError` taxonomy, `ToolResult`/`ToolErrorResult` | Kept as a **process** executor behind the container one (D-07). The metacharacter check is retained as a *second* layer — `shell=False` is the primary defence. |
| Tool install/version pinning | `.../tool_install.py` (~500) | The version-resolution approach behind `ToolDefinition.version` | OCI digests are resolved at acceptance time (`docker image inspect`), not pip pins. |
| Maigret CLI + JSON shape | `donors/maigret/maigret/maigret.py`, `result.py`, `sites.py`; `apps/acquisition/sources/estorides/20_system_tools/kali_maigret.yaml` | The exact argv (`<user> --json simple --timeout 30`), the result-object field set (`site_name`, `status`, `url_user`, `http_status`, `rank`, `ids_data`), the site-database version accessor | The estorides YAML is the argv donor. `status.is_found()` **must not** become `entity_exists` (§44) — the site database is data, the status is the tool's claim. |
| SpiderFoot CLI boundary | `donors/spiderfoot/sf.py`, `sfscan.py` | The `-s TARGET -m modules -t types -u use case -o json` argv surface, the `docker-compose.yml` shape, the module registry | All argv supplied by `ToolDefinition`; `shell=False` (§52). SpiderFoot's `correlations/` is **not** imported — §54. |
| HTTP result parsers | `.../parsers.py` (1293) | 55 tuned `parse_*` functions, incl. `parse_wayback_cdx` and `parse_nominatim` — the shape a SearXNG result parser should have | Used as the **style and totality reference** for the SearXNG result normaliser, not imported: those parsers return entity-shaped dicts, which §59/§60 forbid. The donor's own docstring admits totality is honoured for ~5 of 55. |
| Username canonicalisation | `.../transliteration.py` (146) | The variant-generation approach used for Maigret's `canonical_username` vs `raw_username` | Both retained (§43); canonicalisation never destroys the original. |
| Result validation | `.../validation.py` (135) | The shape of a "validate a parsed record, record what is missing, do not raise" pass | Becomes the quarantine classifier's shape for §107. |

### Taken from platform code (not donor)

`domain/capture.py` (`Capture`, `CaptureTimeBasis`, `digest128`, `canonical_material`, `payload_key`, `to_hop`, `assert_single_tenant`) · `domain/relation_identity.py` (`digest128`, `canonical_material`, `_normalise`) · `events/content_router.py` (`ContentRouter.classify`, `sniff_mime`, `validate_content`, `RequestDedupKey`) · `events/kafka.py` (`IdempotentProducer`, `IdempotentConsumer`, `DedupStore`, `build_envelope`) · `events/topics.py` (`EVENT_CATALOG`, `topic_for`) · `events/registry.py` (`SchemaRegistryClient`) · `storage/s3.py` (`ObjectStore.put_raw_dedup`, `read_range`) · `domain/__init__.py` (`enforce_no_blobs`, `enforce_observation_immutable`) · `security.py` (`EgressPolicy`, `ssrf_guard`, `DnsRebindingGuard`, `ResourceLimits`) · `isolation.py` (`TenantIsolation`) · `adapters/registry.py` (`REGISTRY`, `SourceRegistration`, `CapabilityGap`) · `dispatcher/scheduler.py` (`Dispatcher`, `ScheduleDecision`, `Verdict`) · `sources/catalogue.py` (`SourceDefinition`, `load_catalogue`, `Pagination`, `IDENTITY_PARSERS`) · `observation_gate/replay.py` (`FileReplayJournal`) · `interpretation/parsers/payload/*` and `interpretation/extractors/payload/*` (the entire downstream parse seam) · `bench/run.py` (`ScenarioResult`, `Step`, the `--scenario/--compose/--dry-run` entrypoint).

### NOT taken, and why

| Not taken | Why |
|---|---|
| `estorides_core/orchestrator.py` (43 k), `entity_store.py`, `knowledge_graph.py`, `graph_kuzu.py`, `entity_resolution.py` (27 k), `fusion_store.py` (30 k), `pivot_engine.py`, `relationship_inference.py` | §59/§60/§118/§119: graph mutation, entity semantics, identity decisions, evidence adjudication. Taking any of them puts a graph write on the acquisition path. |
| `estorides_core/entity_extraction.py` (550), `intel_resolver.py` (33 k), `hypothesis_engine.py` (24 k), `reliability_scoring.py` | Type hypothesis and scoring are interpretation/admission work. §112 forbids acquisition re-implementing the zero-layer semantic model. |
| `estorides_core/scope.py`, `target_management.py`, `target_scoring.py` | The platform's own policy layer (§145) is authoritative. A second scope model would be a parallel authority, not a donor component. |
| `sources/executor.py` `capture()` pagination loop | §19 forbids `200 + non-empty body → next page`. D-12. |
| BBOT / Airbyte / SearXNG *code* | Not in `donors/`. Image-pinned integrations (D-13); nothing to transfer. |
| SpiderFoot `correlations/` | §54: the correlation engine must not write to the platform graph. |
| BBOT's native Kafka output module | §47: it is a BBOT schema, not our `EventEnvelope`. |

---

## Key designs

### 1. Record locator grammar (D-04) — `apps/shared/events/record_locator.py`

```text
RecordLocator  := Scheme ":" Body
Scheme         := "json" | "airbyte" | "bbot" | "spiderfoot" | "maigret" | "blob"
Body(json)     := "results" "[" Uint "]"                       # 1-based, per §20 §10 examples
Body(airbyte)  := "message" ":" Uint
                | "stream=" Namespace "/" Stream ":record:" Uint
Body(bbot)     := "event" ":" Uint
Body(spiderfoot):= "event" ":" Uint
Body(maigret)  := "site" ":" CanonicalSite
Body(blob)     := <empty>                                      # the capture-level parent record
Uint           := [0-9]{1,19}
Namespace/Stream := [A-Za-z0-9_.\-]{1,128}   ":" and "/" are not members of the set
CanonicalSite  := canonicalise_site(raw) := NFKC → casefold → [^a-z0-9._-]→"-" → collapse
                  runs of "-" → strip leading/trailing "-" → truncate to 64; empty ⇒ LocatorError("site_name_empty")
```

Three functions, no others: `make_locator(scheme, **parts) -> RecordLocator`, `parse_locator(str) -> RecordLocator`, `RecordLocator.resolve(raw: bytes) -> bytes`.
`resolve` is the only reader: `json` walks the JSON path; `airbyte message:N` re-reads the Nth line of the stored NDJSON; `airbyte stream=…:record:N` selects the Nth message in that namespace/stream; `bbot`/`spiderfoot` index the Nth NDJSON line; `maigret` re-canonicalises each result's `site_name` and matches; `blob` returns the whole body. Every `resolve` is a pure function of the stored bytes — zero network (FR-136, FR-167).

### 2. Deterministic identity (D-03) — `apps/shared/events/observation_identity.py`

```text
IDENTITY_SCHEMA          = "obs/v1"      # versioned: an upgrade opens a new id space, never reinterprets an old one
observation_id           = "OBS-" + digest128(canonical_material([
                             IDENTITY_SCHEMA, tenant_id, capture_id, locator.as_string(), record_digest ]))
deterministic_event_id   = "EVT-" + digest128(canonical_material([
                             event_type, event_version, subject_id, producer, producer_version, lifecycle ]))
                             subject_id = observation_id on observation.* events (§11 verbatim)
                             subject_id = task_id      on acquisition.request/assigned (same rule, §160 forbids random)
```

`ingest()` (blob) uses `locator = blob`, `record_digest = content sha256`, so the blob-level parent record has an id from the same material as every record under it. `lifecycle` comes from the existing `resolve_lifecycle()`; `unchanged` is never `not acquired` (§101).

### 3. Runtime package (D-08) — `apps/acquisition/runtime/`

| Module | Contents |
|---|---|
| `base.py` | `Runtime` Protocol — `runtime_ref`, `execution_class`, `capabilities()`, `estimate(task)`, `acquire(task) -> AsyncIterator[AcquisitionArtifact]` |
| `registry.py` | `register_runtime(cls)`, `resolve_runtime(runtime_ref)`, `RUNTIME_REFUSAL_CODES`; the single registration path, mirroring `adapters/registry.py` |
| `http.py` | `HttpRuntime` — httpx, `security.ssrf_guard`, `ContentRouter.classify`, `hard_max_pages` + `hard_runtime_budget` |
| `searxng.py` | `SearXNGRuntime` — `/config` preflight, `GET /search`, content-derived pagination, `results[]` expansion |
| `airbyte.py` | `AirbyteRuntime` — `spec/check/discover/read`, `AirbyteMessage`, `AirbyteFailureCode` (14), STDIO streaming parser, STATE ordering |
| `external_tool.py` | `ExternalToolRuntime` + `ToolDefinition` + `ToolOutcome` (8 states) |
| `sandbox.py` | `ContainerExecutor` (production) / `ProcessExecutor` (offline tests), argv construction, stdout/stderr caps, `SIGTERM→grace→SIGKILL`, child tracking |
| `limits.py` | `ResourceClass` (small/medium/large) + `RuntimeLimits`, concrete numbers (below) |
| `definitions/` | `searxng.search.yaml`, `airbyte.github.yaml`, `tools/{maigret,bbot,spiderfoot}.yaml` |

### 4. Downstream consumer (D-06) — `apps/interpretation/observation_consumer/`

```text
consume observation.created (group interpretation-1)
  → resolve observation row (tenant-scoped)
  → load raw_ref from ObjectStore                       # never HTTP (FR-136)
  → RecordLocator.resolve(raw)                          # one grammar, five schemes (D-04)
  → parsers.payload.default_registry().parse(body=..., content_type=..., declared_parser=...)
  → extractors.payload.*  (keytable/structure/hypotheses)
  → write structured artifact to ObjectStore            # derived_ref
  → INSERT processing_results (unique: observation_id, consumer, consumer_version)
  → publish observation.processed (causation_id = input event_id, correlation_id carried through)
```

Idempotency (§192): the unique constraint is the dedup key; a doubled envelope produces one row and one `observation.processed` and the test asserts `count == 1` with the duplicate's `idempotency_key` recorded.

### 5. Resource classes and limits (FR-155/FR-156) — concrete, not "tune later"

| Runtime | class | cpu / mem / runtime | max_output | max_records | tool-specific limits |
|---|---|---|---|---|---|
| SearXNG | small | 1.0 / 512 MiB / 120 s | 16 MiB | 200 | `hard_max_pages=10`, connect 5 s, read 15 s, `max_results_per_task=200`, `parallel_queries=1` |
| Airbyte | medium | 2.0 / 2 GiB / 900 s | 256 MiB | 50 000 | `max_record_bytes=8 MiB`, `max_buffered_messages=10 000`, `max_buffered_bytes=32 MiB`, `connector_timeout=900 s` |
| Maigret | medium | 2.0 / 2 GiB / 300 s | 64 MiB stdout | 2 000 | `max_sites=200`, `max_connections=20`, `timeout=20 s`, `max_stderr_bytes=8 MiB` |
| BBOT | large | 4.0 / 4 GiB / 900 s | 128 MiB stdout | 100 000 | `scan_timeout=600 s`, `--pids-limit=200`, `max_stderr_bytes=16 MiB` |
| SpiderFoot | large | 4.0 / 4 GiB / 900 s | 128 MiB | 10 000 | `max_threads=10`, `runtime_limit=600 s`, `output_limit=128 MiB` |

Class table: `small` = 1.0 cpu / 512 MiB / 300 s / 32 MiB / 1 000 rec / conc 2 · `medium` = 2.0 / 2 GiB / 900 s / 128 MiB / 10 000 / conc 4 · `large` = 4.0 / 4 GiB / 1 800 s / 512 MiB / 100 000 / conc 8. Every runtime also declares `connect_timeout`, `read_timeout`, `overall_timeout`, `shutdown_grace` (default 10 s). Backpressure: the dispatcher's `limits.allows()` consults the class's `concurrency`; a growing `acquisition` queue length **reduces** the permit count — asserted by `test_backpressure.py::backlog_up_reduces_rate` (§66).

### 6. DB migration (D-09) — `021_capture_observation_persistence`

```text
captures
  capture_id           String(36)  PK
  capture_fingerprint  String(32)  NOT NULL
  tenant_id            String(36)  NOT NULL
  source_id            String(36)  NOT NULL
  source_family        String(64)  NOT NULL
  target_uri           Text         NOT NULL DEFAULT ''
  locator              Text         NOT NULL DEFAULT ''
  content_digest       String(64)  NOT NULL
  content_length       BigInteger   NULL
  media_type           String(128) NOT NULL DEFAULT ''
  fetched_at           DateTime(tz) NULL
  time_basis           String(32)  NOT NULL
  transport            String(32)  NOT NULL
  ingest_batch_id      String(64)  NOT NULL
  ingest_attempt       Integer      NOT NULL DEFAULT 1
  recorded_by          String(64)  NOT NULL
  raw_ref              Text         NOT NULL
  created_at           DateTime(tz) server_default now()
  UNIQUE (tenant_id, capture_fingerprint)
  INDEX  (tenant_id, content_digest), (tenant_id, source_id, fetched_at), (tenant_id, ingest_batch_id)

observations  (ALTER)
  + capture_id      String(36)  NULL → backfilled → SET NOT NULL
  + locator         Text         NULL → backfilled → SET NOT NULL   # first-class, not JSONB
  + record_digest   String(64)   NULL
  + record_metadata JSONB        NULL
  + event_id        String(64)   NULL
  UNIQUE (capture_id, locator, record_digest)                       # record-level idempotency (§123)
  INDEX  (tenant_id, capture_id), (tenant_id, status)
  # legacy rows: capture_id = CAP-digest128(ABSENT basis over the row's own fields),
  #              locator = 'blob', record_digest = content_hash, recorded_by = 'migration-021'

processing_results
  processing_run_id  String(36)  PK
  observation_id     String(36)  NOT NULL
  capture_id         String(36)  NOT NULL
  raw_ref            Text         NOT NULL
  record_locator     Text         NOT NULL
  consumer           String(64)  NOT NULL
  consumer_version   String(32)  NOT NULL
  processed_at       DateTime(tz) NOT NULL
  status             String(32)  NOT NULL
  derived_ref        Text         NOT NULL
  idempotency_key    String(64)  NOT NULL
  payload            JSONB        NULL
  UNIQUE (observation_id, consumer, consumer_version)
  INDEX  (tenant_id, processed_at)
```

### 7. `docker-compose.yml` additions (§126, §127) — existing file, new `runtimes` profile, no second stack

| Service | Image (digest-pinned at acceptance) | Notes |
|---|---|---|
| `searxng` | `searxng/searxng` + mounted `settings.yml` with `search.formats: [html, json]` | JSON disabled ⇒ `/search?format=json` returns 403 ⇒ `SEARXNG_JSON_FORMAT_DISABLED` |
| `tool-runner` | built from the platform runner image; **no** socket mount (it uses the host Docker context) | §65 |
| `acq-airbyte` | `airbyte/source-github:2.7.1` invoked per run | §31 pin + digest recorded in provenance |
| `acq-maigret` | `ghcr.io/soxoj/maigret` (built from `donors/maigret/Dockerfile`) | `--network none` except the policy egress |
| `acq-bbot` | `blacklanternsecurity/bbot` | scan target allowlist |
| `acq-spiderfoot` | built from `donors/spiderfoot/Dockerfile` | bounded passive use case |
| `observation-consumer` | platform image, `interpretation` app | group `interpretation-1` |

### 8. Failure classification (FR-203, §73) — runnable, not prose

Every failure writes one `FailureRecord` with a `class` from the closed vocabulary of 20: `build, configuration, dependency, container, process, network, DNS, TLS, authentication, protocol, parsing, identity, storage, Kafka, schema, consumer, downstream, performance, security policy, determinism`. `classify_error()` in `runtime/base.py` maps every runtime exception to one; an unmapped code **raises** `UnclassifiedFailure` rather than defaulting (§203 forbids a generic "integration failed").

### 9. Redpanda-first debugging (FR-205, §75) — runnable

```powershell
# 0. broker identity — resolve the current bootstrap from settings, do not assume
$env:KAFKA_BOOTSTRAP_SERVERS = "localhost:19092"

# I. event present? (§75 line 1)
uv run python -m bench.acquisition inspect-kafka --event-id $evtId `
    --expect-topic observation --expect-observation-id $obsId
# -> topic / partition / offset / event_id / observation_id / key
#    FAIL topic mismatch  -> configuration  (routing or a per-donor topic, FR-056)
#    FAIL event absent    -> producer|topic routing|delivery callback|serialization

# II. event present, downstream not processed? -> consumer group / offset / lag / poison
uv run python -m bench.acquisition inspect-consumer --group interpretation-1 --topic observation `
    --event-id $evtId --lag --poison

# III. raw present, event absent -> ObservationGate / producer seam
uv run python -m bench.acquisition dump-capture --capture-id $capId --raw
# IV. raw absent -> artifact sink / ObjectStore
uv run python -m bench.acquisition dump-capture --capture-id $capId --meta-only
# V. capture present, observation absent -> record expander
uv run python -m bench.acquisition dump-observation --capture-id $capId --count
# VI. observation present, no downstream result -> consumer / parser / downstream stage
uv run python -m bench.acquisition dump-observation --observation-id $obsId --processing
# VII. replay with zero network (FR-167)
uv run python -m bench.acquisition replay-observation --observation-id $obsId
```

Each command exits non-zero and prints `{"failed_stage": ..., "task_id":..., "capture_id":..., "observation_id":..., "reason":..., "failure_class":...}` — the §159 failure shape (FR-206).

---

## Project Structure

### Documentation (this feature)

```text
specs/023-acquisition-integration-searxng/
├── input.md             # the 204-section directive (source of truth)
├── spec.md              # rendering into the Speckit template (215 FRs)
├── plan.md              # this file
├── research.md          # Phase 0: ADRs 0025 (runtime contract) and 0026 (broker identity)
├── data-model.md        # Phase 1: Capture/ObservationRecord/RecordLocator/EventEnvelope/ProcessingResult
├── quickstart.md        # Phase 1: how to run one scenario end to end
├── contracts/           # Phase 1: AcquisitionArtifact, Runtime, ToolDefinition, FailureRecord
└── tasks.md             # Phase 2 (NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
apps/shared/
├── events/
│   ├── observation_identity.py       # NEW  D-03: observation_id + deterministic_event_id
│   ├── record_locator.py             # NEW  D-04: one grammar, make/parse/resolve
│   ├── canonical_json.py             # NEW  D-05: pinned canonical_json for record_digest
│   ├── observation_gate.py           # EDIT line 74 (uuid4 -> observation_identity), line 106 (evt- -> deterministic_event_id); + ingest_capture/ingest_record
│   ├── kafka.py                      # EDIT build_envelope: + require_deterministic_event_id
│   ├── topics.py                     # EDIT + "observation.processed": "observation"
│   └── registry.py                   # EDIT register observation.processed v1.0
├── domain/
│   ├── capture.py                    # UNCHANGED (already carries source_family + time_basis)
│   └── relation_identity.py          # UNCHANGED (digest128 / canonical_material reused)
└── isolation.py, security.py         # UNCHANGED (reused)

apps/acquisition/
├── runtime/                          # NEW package  D-08
│   ├── base.py  registry.py  limits.py  sandbox.py  http.py
│   ├── searxng.py  airbyte.py  external_tool.py
│   └── definitions/
│       ├── searxng.search.yaml  airbyte.github.yaml
│       └── tools/{maigret,bbot,spiderfoot}.yaml
├── tool_runner/                     # NEW host-run service  D-07/D-14
│   ├── __main__.py  executor.py  policy.py
├── workflow/                         # NEW InvestigationWorkflow  (FR-054, §56)
│   └── investigation_workflow.py
├── sources/
│   ├── catalogue.py                  # EDIT SourceDefinition + worker_ref/runtime_ref/source_family/time_basis/resource_class/limits (§14)
│   ├── connector.py                  # EDIT: stop publishing a dict; call the gate  (D-15 keeps YAML corpus)
│   └── executor.py                   # UNCHANGED (D-12)
├── adapters/registry.py              # EDIT SourceRegistration + worker_ref/runtime_ref; + resolve_explicit
├── dispatcher/
│   ├── scheduler.py                  # EDIT: explicit-runtime branch before capability match
│   └── plan_driver.py                # EDIT: register the five runtime surfaces
├── observation_gate/replay.py        # UNCHANGED (FileReplayJournal reused for §131)
└── pyproject.toml                    # EDIT: + confluent-kafka, + live_integration marker

apps/interpretation/
└── observation_consumer/             # NEW  D-06  (ACQ-18)
    ├── __main__.py  consumer.py  processing.py  idempotency.py
    └── parsers_borrowed: uses the existing parsers/payload/ and extractors/payload/ unchanged

apps/control-plane/
└── db/
    ├── schema.py                     # EDIT: Capture, ObservationRecord columns, ProcessingResult  (D-09)
    └── migrations/versions/021_capture_observation_persistence.py   # NEW, forward-only

apps/deploy/
├── docker-compose.yml                # EDIT: `runtimes` profile — the five runtimes + tool-runner + consumer (§126)
└── searxng/settings.yml              # NEW  (search.formats includes json)

bench/
└── acquisition/                      # NEW  §130 executable trace commands
    ├── __main__.py  scenarios.py  reconcile.py  inspect.py  report.py  replay.py

artifacts/acquisition-integration/    # NEW  §201 — 8 mandatory files
```

**Structure Decision**: existing multi-app layout, extended in place. `apps/shared` holds the identity/locator/canonical-JSON primitives (below every app, imported by both acquisition and interpretation — no cycle). `apps/acquisition/runtime/` is the new host for the three runtime classes. `apps/interpretation/observation_consumer/` owns the downstream consumer, because the parser layer it must reach is already interpretation's and `parsers/payload/__init__.py` explicitly refuses to import `sources`. No new app, no new stack.

---

## Phased execution (§196 order, not deviated from)

### Phase 0 — Preconditions (not a work package; blocks everything)

1. Record `git rev-parse HEAD` and `git status --porcelain` into `artifacts/acquisition-integration/run-manifest.json` (FR-177, §186). Baseline: `fe3eb448`, 118 untracked, 0 modified. "Dirty" is a **recorded state**, not an unknown.
2. Probe infra: `docker version`; if unavailable, record `failure_class: container` + `reason: docker_desktop_unavailable` as a §72 infrastructure blocker and **continue with offline phases**. Do not fabricate green (FR-007).
3. Write ADR-0025 (runtime contract) and ADR-0026 (broker identity). O-1 and O-2 need answers here.

### Phase 1 — The seam (`ACQ-01 → 02 → 03 → 04 → 05 → 06 → 17 → 18`)

Runs strictly in this order; each is green before the next starts. §196: *"Нельзя строить пять runtime integrations на неисправном seam."*

| Order | WP | Deliverable | Exit assertion |
|---|---|---|---|
| 1.1 | ACQ-01 | `AcquisitionArtifact` (D-02) + `ArtifactSink.accept()` streaming; `worker.run(task)` async generator | A generator emitting 100 artifacts never holds more than 1 in memory (FR-025) |
| 1.2 | ACQ-02 | migration `021` + `CaptureRepository`; `Capture` registered as a first-class durable object | `capture_id` unique; same bytes twice → one row; legacy backfill lands with `time_basis=ABSENT` (FR-029/030/048) |
| 1.3 | ACQ-03 | `observation_identity.py`; `observation_gate.py:74` and `:106` repaired; `build_envelope` guard | `OBS-` id is byte-equal over 100 replays; `uuid4`/`now`/`pid`/`id()` appear nowhere on the id path (FR-033/034/035) |
| 1.4 | ACQ-04 | connector stops building a dict; `worker_acquisition.observation_publisher` publishes `envelope.SerializeToString()` | A dict cannot reach the broker; `enforce_no_blobs` never trips (FR-004/012) |
| 1.5 | ACQ-05 | `RecordLocator` grammar + `ingest_capture` + `ingest_record` | `resolve()` returns the exact bytes with a refusing HTTP transport installed (FR-045/032) |
| 1.6 | ACQ-06 | `SourceDefinition` fields; `SourceRegistration.worker_ref/runtime_ref`; `resolve_explicit`; `Dispatcher` explicit branch | Two sources sharing `http` land on different `runtime_ref`s; `BBOT→http` is refused by name (FR-049/050/051/055) |
| 1.7 | ACQ-17 | canonical publish + `inspect-kafka`; `observation.processed` registered (D-10); Redpanda precheck (topic exists / produce / subscribe / roundtrip) | All 15 §23 steps reach step 10 (`observation.created` in Redpanda) for a fixture-backed capture |
| 1.8 | ACQ-18 | `observation_consumer/` (D-06) | `processing_results` row with a non-null `derived_ref`; replay → 0 network calls (FR-133/134/135/136) |

**Phase 1 gate**: FR-012's first, second and fifth blockers are provably absent: `observation_id` deterministic, `event_id` content-derived, event carries the canonical `EventEnvelope`, every observation resolves to raw lineage.

### Phase 2 — Foundational runtimes (`ACQ-07`, `ACQ-09`, `ACQ-12` — parallel)

| WP | Runtime | Done when |
|---|---|---|
| ACQ-07 | `SearXNGRuntime` | `/config` probe passes; content-derived pagination stops on an empty `results[]` under both `hard_max_pages` and `hard_runtime_budget`; every page durable (FR-063/064/065) |
| ACQ-09 | `AirbyteRuntime` | `spec/check/discover/read` over a process/container boundary with an async stdout reader; no `subprocess.run(capture_output=True)` on `read` (FR-076/078) |
| ACQ-12 | `ExternalToolRuntime` + `ToolDefinition` | one generic boundary; container executor; `ToolRunner` reachable; a refused run is refused **before** the process starts (FR-097/098/099) |

### Phase 3 — Per-runtime specifics (`ACQ-08, 10, 11, 13, 14, 15`)

- **ACQ-08** SearXNG JSON validation: `SEARXNG_JSON_FORMAT_DISABLED` is a named non-runtime-ready state, distinct from `results=[]` and from 429/5xx (FR-061/071/081).
- **ACQ-10** Airbyte streaming parser: `buffered line → UTF-8 → JSON → AirbyteMessage → dispatch`; an unknown type is preserved to quarantine with its line index and never crashes the run; several streams may interleave and no `groupby(stream)` is used (FR-084/046/093).
- **ACQ-11** State checkpointing: `receive → persist → acknowledge durable → process STATE`; on retry `state_before` is the last durable checkpoint (FR-085/090).
- **ACQ-13/14/15** Maigret / BBOT / SpiderFoot definitions. §143 limits; all fields retained, none invented; `parent_chain` is provenance; SpiderFoot correlation is an observation (FR-101/102/109/114/115/116/117).

### Phase 4 — Governance then proof (`ACQ-16 → 19 → 20 → 21 → 22`)

- **ACQ-16** sandbox + resource controls: every tool launched with the container flags in D-07; separate `max_stdout_bytes`/`max_stderr_bytes`; `SIGTERM→grace→SIGKILL`; child tracking; explicit per-runtime egress (FR-154/156/159/160/161).
- **ACQ-19** five live scenarios `@pytest.mark.live_integration`, launched through `InvestigationWorkflow`; all 15 cells of the §152 matrix.
- **ACQ-20** replay: `replay(task_id)` under a new `integration_run_id`; `replay_observation(observation_id)` with zero network; parser v1/v2 from one raw.
- **ACQ-21** failure journal: `FailureRecord` with the 20-class vocabulary, the §74 evidence set, secrets redacted before storage.
- **ACQ-22** clean-stack acceptance: fresh DB, Redis, ObjectStore namespace, Redpanda topics/consumer group; `migration up → smoke → migration replay`; then `uv run python -m bench.run --scenario acquisition-integration`; the 8 artifacts land under `artifacts/acquisition-integration/`.

**§162 procedure** (A Build → … → O Final acceptance) is executed literally for each of the five runtimes, and `artifacts/acquisition-integration/<runtime>.json` records the phase-by-phase result.

---

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Two brokers in compose (`core` Kafka:9092, `streaming` Redpanda:19092) and the acceptance run points at Redpanda while the constitution's Technology Baseline names Kafka KRaft | The directive's gate (§0.1, §67, §75, §127, §204) names Redpanda in nine places; the code has no broker-brand branch; Redpanda is wire-compatible, so one env var satisfies the gate with zero code risk | Pointing acceptance at Kafka and reading the directive's "Redpanda" as loose usage would satisfy the constitution's letter but not the contract's language, and §0 says the Russian is the authority. Moving the canonical backbone to Redpanda permanently is an ADR, not a plan change, and would contradict the Technology Baseline without a Governance decision. → **ADR-0026, O-1** |
| A second acquisition contract surface (`Runtime`) beside `AcquisitionWorker` | §25's `spec/check/discover/read` and §40's argv-based `ToolDefinition` cannot be expressed by `capabilities()/estimate()/acquire()`; a `read()` is an async iterator of protocol messages, not a returned value | Forcing all three runtime classes through `AcquisitionWorker.acquire()` would make the streaming protocol parser a return value rather than an iterator, and would put the Airbyte message-dispatch loop inside a method whose contract says "one result". The interface **shape** and the **registry** are preserved; `AcquisitionWorker` becomes an adapter. → **ADR-0025, O-2** |

---

## Verification

| Gate | How it is checked |
|---|---|
| Determinism | `test_identity.py`: 100 replays byte-equal `capture_id`/`observation_id`/`event_id`; AST scan of the id path for `uuid4`/`now`/`os.getpid`/`threading.get_ident`/`id()`; `test_replay.py`: `replay_observation` with a transport that raises on any call |
| Locator | `test_record_locator.py`: 5 schemes × round-trip; a cross-scheme string is refused by name; `resolve` on a resolved body equals the original bytes |
| Routing | `test_routing.py`: two sources, same capability, different `runtime_ref` → two workers; `BBOT`-shaped task with `runtime_ref` unset and `capabilities={http}` → explicit `CapabilityGap`, never `HttpWorker` |
| Envelope | `test_envelope.py`: broker bytes parse as `EventEnvelope`; a dict cannot be serialised; payload ≤ 1 KiB and contains only refs; no secret key name appears |
| Isolation | `test_sandbox.py`: assert no bind mount, no `/var/run/docker.sock`, `--read-only`, `--cap-drop ALL`, `--pids-limit`, bounded `--network`; a socket-mount request is refused by `policy.py` |
| Boundedness | RSS sampled during a 50k-record `read()` stays under the class limit; the stdout parser never holds more than `max_buffered_messages` |
| Failure taxonomy | all 14 Airbyte codes and all 8 Maigret states individually constructed and observed; an unmapped exception raises `UnclassifiedFailure` |
| Secrets | a corpus of fake `access_token`/`api_key`/`password` strings is pushed through every run; `rg` over the Redpanda dump, the logs, the run manifest and `git diff` returns zero |
| No false green | a test asserts no `pytest.mark.live_integration` test carries `skip`/`xfail`, and that `--strict-markers` accepts the marker |
| The gate itself | `bench.run --scenario acquisition-integration` emits §159's PASS/FAIL shape; PASS requires all 30 matrix cells and the 8-factor product non-zero for all five families |

---

## Open decisions

| # | Decision needed | Why it is not mine to take | What I need from the user |
|---|---|---|---|
| **O-1** | Which broker is the **canonical backbone** — Kafka KRaft (constitution baseline) or Redpanda (directive's language, nine sections)? | Constitution Governance: "Kafka vs alternatives" requires an ADR. D-01 makes the *acceptance run* work either way, but the permanent topology is a platform decision. | Sign ADR-0026, or tell me to write it as "Redpanda is the canonical backbone; the Kafka service remains for schema-registry compatibility". |
| **O-2** | Is `Runtime` + `AcquisitionWorker`-as-adapter an acceptable reading of Principle V, or is that a constitutional violation requiring an amendment? | AGENTS.md §1.1: a conceptual contradiction with the platform is the one thing the agent must not decide alone. | Confirm the adapter reading, or rule that Principle V must be amended first. |
| **O-3** | Which **Airbyte connector** proves §38/§39, and do external credentials exist in this execution context? | A credential decision is an environment/owner decision. §39 mandates a deterministic fixture connector as the protocol harness **and** a real connector run; the fixture part I can plan, the credential part I cannot. | Name the connector + whether a token is available. Default plan: `airbyte/source-github:2.7.1` with `credential_ref` to a Vault path; fixture connector `airbyte/source-hardcoded-data` for the protocol harness. |
| **O-4** | Are the image **digests** for searxng / bbot / maigret / spiderfoot / airbyte approved? | §31/§150 require a digest in provenance; picking a digest is a supply-chain decision, and `bbot` and `airbyte` have no donor tree here to derive a version from. | Approve tags, or have me resolve digests at acceptance time and record them (§150's manifest exists for exactly this). Default: resolve at acceptance, record, and re-run. |
| **O-5** | `InvestigationWorkflow` — a new component, a rename of an existing workflow, or a wrapper over the current `Investigation` lifecycle? | No symbol by that name exists; the spec flags it as undetermined. It is a control-plane naming decision. | Default plan: a thin `apps/acquisition/workflow/investigation_workflow.py` that owns task creation + dispatch and delegates lifecycle to the existing `Investigation`. Say if you want it elsewhere. |
| **O-6** | BBOT's **scan target** and SpiderFoot's **use case** for the live scenarios (§83/§84) | These are targets against third parties. The constitution's tool constraint and §145's policy layer mean the target must be operator-approved, not agent-chosen. | Default plan: a self-owned test host under the operator's control + SpiderFoot `Passive` use case. Confirm. |

---

## Not planned, and why

| Item | Why |
|---|---|
| Sourcing the BBOT and Airbyte **code** from donors | They are not in `donors/`. Image-pinned integrations; nothing to transfer (D-13). |
| `async_client.ResponseCache` reuse as-is | Its cache key omits tenant and credential context — the §100 cross-tenant leak. Adapted, not inherited; recorded in the donor table. |
| Choosing between a *real* and a *fixture* Airbyte connector for acceptance | §161 forbids substituting the fixture. Both are planned (fixture = protocol harness, real = integration proof); which real one is O-3. |
| Any claim about live infrastructure being available | Docker Desktop was down at last check. Phase 0 probes and records; no phase below depends on an assumption. |
| The `platform/` and `src/` trees | Not part of the dependency graph for this feature; untouched. |
