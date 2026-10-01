# Feature Specification: Acquisition Integration — Five Runtime Families on One Capture → Observation → EventEnvelope Seam

**Feature Branch**: `023-acquisition-integration-searxng`

**Created**: 2026-09-29

**Status**: Draft

**Input**: `specs/023-acquisition-integration-searxng/input.md` — a 204-section IMPLEMENTATION DIRECTIVE, declared "источник истины для spec/plan/tasks" (source of truth for spec/plan/tasks). This spec is a **rendering** of that directive into the Speckit template. Where this document and `input.md` differ, `input.md` wins; no requirement below exists that is not traceable to a numbered section of it, and every `FR` carries its `§` source inline.

**Base**: `main` / `JewishTT/1` @ `fe3eb4486fecf89574dfb78b13c3d28a51ffa04b` (§ header).

---

## Completion Gate — the contract's definition of done

This block precedes all feature content because §0 and §204 are the contract's own definition of done and are not weakened anywhere in this spec. They are quoted in the directive's own words, followed by a faithful English rendering for readers working in English; the Russian is the authority, the English is a rendering and not a substitute.

### §0 — «КРИТЕРИЙ ВЫПОЛНЕНИЯ — ИСТИННЫЙ GATE»

> ТЗ **не считается выполненным**, если выполнено только одно или несколько из:
> написаны адаптеры; зарегистрированы source definitions; проходят unit-тесты; проходят fixture-тесты; worker умеет запуститься; контейнер инструмента корректно вызывается; сообщение появилось в stdout; сообщение было отправлено в Kafka; `observation.created` существует в коде; Redpanda содержит какие-либо сообщения; downstream consumer существует, но реально ничего не обработал.

**Rendering.** The directive is **NOT** considered fulfilled if only one or more of the following is true: adapters are written; source definitions are registered; unit tests pass; fixture tests pass; the worker can start; the tool container is invoked correctly; a message appeared in stdout; a message was sent to Kafka; `observation.created` exists in code; Redpanda contains some messages; a downstream consumer exists but has actually processed nothing.

### §0.1 — «Единственный финальный критерий»

> Feature считается выполненной только после подтверждения полного runtime-path:
> `Investigation → AcquisitionTask → Scheduler/Dispatcher → конкретный worker_ref + source/runtime definition → реальный запуск внешнего источника → реальный output source → Capture/raw artifact → ObjectStore → Observation/ObservationRecord → canonical EventEnvelope → Redpanda → реальный downstream consumer → успешная обработка наблюдения → идентифицируемый persisted result`
>
> Для **каждого** из пяти семейств должен существовать хотя бы один доказанный runtime trace. Минимально: `source start → task_id → worker_ref → capture_id → raw_ref → observation_id → event_id → topic → partition/offset → consumer group → downstream processing result`. Все перечисленные идентификаторы должны быть доступны для forensic inspection.

### §204 — «ФИНАЛЬНАЯ ФОРМУЛА»

> ```
> REAL SOURCE × REAL RUNTIME × REAL CAPTURE × REAL OBSERVATION
>   × REAL REDPANDA EVENT × REAL CONSUMER × REAL DOWNSTREAM PROCESSING × REAL REPLAY
> = INTEGRATION COMPLETE
> ```
> Если хотя бы один множитель равен нулю — `FEATURE = NOT COMPLETE`.
> И после появления первой реальной ошибки применяется **не пересмотр acceptance criteria**, а: `debug → patch → replay → verify → repeat`.

> These three blocks are reproduced in `SC-001` (§0/§0.1), `SC-002` (§204) and `SC-003` (§200) below. They are the primary success criteria, not a summary of them.

---

## Problem Statement

The platform has a declarative acquisition layer — a source catalogue, an HTTP source executor, a two-stage scheduler, a source connector, a content router, a Redpanda/Kafka path, a protobuf `EventEnvelope`, a `Capture` value type and an `ObservationGate` — and **no runtime integration that has ever completed the path from a real external source to a really-processed downstream observation**. The directive's purpose is stated as moving the fabric "от декларативного набора источников и тестовых seam-ов до фактического получения, долговременного сохранения и downstream-обработки потока наблюдений" (§ header).

### Two confirmed defects, verified at HEAD `fe3eb448` (§4)

**D1 — `observation_id` is random.** §4 states it and the code confirms it: `apps/shared/events/observation_gate.py:74` reads `observation_id = "OBS-" + uuid.uuid4().hex[:12]`. §11 forbids `uuid.uuid4()` as the basis of observation identity and requires `OBS-{digest128(identity_schema | tenant_id | capture_id | locator | record_digest)}`. This is a **release blocker in the directive's own terms** (§160: "observation_id random") and it is the reason no replay can be proved (§11, §12, §165, §189).

A second randomness site is adjacent: `apps/shared/events/kafka.py:49` defaults `event_id` to `str(uuid4())` whenever a caller does not supply one, and `observation_gate.py:106` supplies `evt-{ref.sha256}-{lifecycle}` — content-derived but **not** derived from the §11 material `event_type | event_version | observation_id | producer | producer_version | lifecycle`. §160 lists "event_id random for replay-sensitive events" as a release blocker.

**D2 — the live path does not go through `ObservationGate` or `EventEnvelope`.** §4 states it and the code confirms it: `ObservationGate` and `EventEnvelope` are not invoked from `apps/acquisition/sources/connector.py`, which builds a plain Python dict (lines 143–171) and yields it. `apps/acquisition/worker_acquisition.py:366-377` then publishes that dict as `json.dumps(event, sort_keys=True)` — JSON on the wire, not the canonical protobuf envelope. §4's closing rule is explicit: these problems MUST be fixed **before** any of the five sources is declared integrated; §196 repeats it: "Нельзя строить пять runtime integrations на неисправном Capture → ObservationGate → EventEnvelope seam." §160 lists "event without canonical EventEnvelope" as a release blocker.

### Supporting facts about the tree at HEAD (recorded as facts, not problems to solve in this spec)

- None of SearXNG / Airbyte / Maigret / BBOT / SpiderFoot appear in `apps/deploy/docker-compose.yml`; its profiles are `core`, `analytics`, `streaming`, `collectors`. §126 forbids creating a second parallel infrastructure stack, so the five runtime services must land in the existing compose file.
- No `apps/acquisition/runtime` or `apps/acquisition/runtimes` package exists. §1's three runtime classes and §25's `AirbyteRuntime` have no host package.
- `apps/acquisition/acquisition_loop.py` does not exist; §64 already records this ("проверено: отсутствует в репозитории") and forbids its use — a prohibition against a file that is not there.
- The dispatcher's stage B is a capability match over `adapters.registry.REGISTRY` with a default requirement of `{"http"}` (`dispatcher/scheduler.py:112`), and `PlanDriver.ensure_capability()` registers exactly one surface: `("catalogue-http", execution_class="http", capabilities={"http"})` (`dispatcher/plan_driver.py:293`). At HEAD a BBOT task **would** route to the generic HTTP worker — the exact forbidden situation §13 names.
- `HttpSourceExecutor.capture` iterates `for page in range(1, total + 1)` and returns early only on truncation or an empty body when `page_size` is declared (`sources/executor.py:220-255`) — i.e. it stops on body emptiness, which §19 names as the inadmissible rule.
- `event_id` in `observation_gate.py:106` and the connector's `observation_id()` in `sources/connector.py:28` (which digests `source_id | query | page | content_digest`) are two competing identity schemes, neither of which is the §11 formula.
- `observation.processed` is not in `EVENT_CATALOG` (`apps/shared/events/topics.py`), so §85's downstream processing result needs a newly registered, registry-validated event version (§120).
- `bench/run.py` already provides `uv run python -m bench.run --scenario <name> [--compose …] [--dry-run]` with per-scenario steps and a `PASS`/`FAIL` result; §158's acceptance command names that existing entrypoint rather than proposing a new harness.

### Execution order is mandated, not chosen

§196 fixes the order: seam repair → capture persistence → gate repair → envelope bridge → record seam → worker routing → canonical publish → downstream consumer → the three runtime classes → per-runtime specifics → sandbox/resource controls → live scenarios → replay → failure journal → clean-stack acceptance. Every "Why this priority" below is written against that order. §194 makes each of the five runtime families **independently** release-blocking.

---

## User Scenarios & Testing *(mandatory)*

> **On the P-numbers.** P1–P5 are the five runtime families in the order the directive presents them (§2, §80–§84). Per §194 the P-number orders **construction sequence only**; it expresses no relative release weight. Each of the five is `BLOCKED until all green` on its own row, and no runtime's acceptance may be satisfied by, substituted for, or inferred from another runtime's green pass.

### User Story 1 - The Canonical Seam Carries Deterministic Identity (Priority: P0 — prerequisite)

An operator replays an acquisition and gets the same identifiers back. Today the `Capture → Observation → EventEnvelope` path does not exist end-to-end: the gate mints a random `observation_id`, the live path bypasses the gate and the protobuf envelope entirely, and there is no way to address an individual record inside a stored artifact. After this story, a replayed artifact produces the same `capture_id`, the same `observation_id` and the same `event_id`, every observation resolves to raw bytes and a byte-exact locator, and the canonical envelope — not a dict — is what reaches the broker.

**Why this priority**: §196 forbids building any of the five runtime integrations on a broken Capture → ObservationGate → EventEnvelope seam, and §4 requires both defects fixed *before* any source is declared integrated. §160 lists "observation_id random", "event without canonical EventEnvelope" and "observation without raw lineage" as release blockers. This story is not a side quest; nothing downstream of it is admissible until it is green.

**Independent Test**: Construct one artifact twice from identical material and assert equal `capture_id`, `observation_id` and `event_id` (§11, §12, §165); expand one stored capture into N record observations and assert each `observation_id` is a pure function of `(identity_schema, tenant_id, capture_id, locator, record_digest)` (§11); assert the live publish path emits a serialized protobuf `EventEnvelope` and a dict does not reach the broker (§68, §69, §4/D2).

**Acceptance Scenarios**:

1. **Given** one `Capture` and one record locator and one record digest, **When** the record observation is created twice, **Then** both creations yield the identical `OBS-…` id, and no `uuid4`, wall clock, process id, thread id, random source or memory address participates (§11).
2. **Given** a stored raw artifact, **When** a downstream consumer resolves a record by its locator, **Then** it obtains the exact record bytes without any network acquisition (§132, §173, §174).
3. **Given** a produced observation event, **When** it is inspected on the broker, **Then** it is a canonical protobuf `EventEnvelope` carrying the full §68 routing field set and a refs-only payload (§68, §69, §160).
4. **Given** an HTTP 4xx, a connector error or a tool timeout, **When** the run ends, **Then** the outcome is recorded as a failure with its evidence metadata, never as a fabricated empty result (§102, §203).

---

### User Story 2 - Dispatch Resolves the Runtime Explicitly and Reaches a Real Consumer (Priority: P0 — prerequisite)

An operator creates one `InvestigationWorkflow` and a source, and the platform routes the task to the runtime the source actually names — not to a generic worker that happens to advertise a matching capability. After this story, every task carries `investigation_id`, `tenant_id`, `task_id`, `source_id`, `worker_ref` and `runtime_ref` end to end; the canonical topic catalogue is used as-is with no per-donor topics; and a real consumer turns an `observation.created` event into a persisted, machine-readable processing result.

**Why this priority**: §196 places worker routing, canonical publish and the downstream consumer in the first wave alongside the seam repair, and before any runtime class. §13 makes the `BBOT task → capability=http → generic HttpWorker` route a forbidden outcome, and at HEAD that is what the dispatcher does. §85 states that "Observation пришла в Kafka" is insufficient; §136 states an acceptance run is not green until the event has actually been processed by a consumer.

**Independent Test**: Register two sources that share a capability but name different runtimes, dispatch both, and assert each lands on its own `runtime_ref` (§13, §57). Publish one real envelope, run a real consumer, and assert a `ProcessingResult` with a concrete `derived_ref` is persisted (§85, §86).

**Acceptance Scenarios**:

1. **Given** a task whose `source_id` names an explicit `runtime_ref`, **When** the scheduler dispatches it, **Then** the runtime is resolved by name and capability matching serves only as a compatibility check (§13, §57).
2. **Given** an `observation.created` event on the canonical observation topic, **When** the real consumer receives it, **Then** it resolves the observation, loads `raw_ref`, resolves the locator, validates the payload and writes a processing result carrying `processing_run_id`, `observation_id`, `consumer`, `consumer_version`, `processed_at`, `status` and `derived_ref` (§85, §86).
3. **Given** five different donor tools, **When** they publish, **Then** all of them publish onto the same canonical topic catalogue; no per-donor topic such as `maigret-observations` exists and tool identity lives in metadata/provenance (§67).
4. **Given** a source definition with `enabled=false`, **When** the scheduler plans, **Then** no task is created for it and the runtime id remains stable (§167).

---

### User Story 3 - SearXNG Delivers Page-by-Page Search Observations (Priority: P1)

An operator runs one search task against a real SearXNG instance and gets one durable capture per response page and one addressable observation per search result, with the whole result object preserved. Today `HttpSourceExecutor` is a fixed-`max_pages` loop that advances on body emptiness, and there is no JSON-format preflight — an instance with JSON disabled returns HTTP 403 and the failure is indistinguishable from an empty result set.

**Why this priority**: first in the directive's own ordering (§2, §15–§23, §80) and the cheapest runtime that still exercises the full HTTP path. Per §194 it blocks release on its own row.

**Independent Test**: Run the real `live_searxng_smoke` scenario end to end — `investigation = int-searxng-smoke`, query `"SearXNG GitHub"`, source `searxng.search`, worker `http`, runtime `searxng` — and assert all **15** acceptance steps in §23 (§80).

**Acceptance Scenarios**:

1. **Given** a SearXNG instance that has not yet answered, **When** the health probe runs, **Then** it confirms the instance responds, that JSON format is enabled, that `/search` is available and that at least one engine is enabled; if JSON is absent the source is `SEARXNG_JSON_FORMAT_DISABLED` and is **not** runtime-ready (§17).
2. **Given** a task with `query`, **language`, `categories`, `page`, `max_pages`, `time_range`, `safesearch`, **When** pages are fetched, **Then** pagination continues while the parsed result collection still has results and stops on a content-derived condition under both `hard_max_pages` and `hard_runtime_budget`; `HTTP 200 + body != empty → fetch next` is not an admissible stop rule (§19).
3. **Given** a fetched page, **When** records are expanded, **Then** each page is a durable capture and each result is its own observation with a locator such as `json:results[0]`, `json:results[1]`, referencing its `capture_id` (§10, §20).
4. **Given** a result object, **When** it is normalized, **Then** `title`, `url`, `content`, `engine`, `category`, `publishedDate`, `thumbnail`, `template`, `score` and every other genuinely present field survive, no field is invented, an absent field is `null` rather than a semantic claim, and unknown top-level fields remain reachable in the raw artifact (§21, §62).
5. **Given** a completed 15-step run, **When** it is inspected, **Then** every one of: task created; task dispatched; searxng runtime invoked; HTTP 200; JSON parsed; ≥1 result emitted; capture stored; raw_ref exists; ≥1 observation persisted; `observation.created` in Redpanda; consumer receives; consumer fetches raw_ref; consumer resolves locator; downstream processing completes; processing record persisted — is individually evidenced (§23).
6. **Given** a stored raw response, **When** a new parser or extractor is introduced, **Then** re-parsing produces new observations without any repeat network request (§94).

---

### User Story 4 - Airbyte Runs as a Connector Execution Protocol, Not an HTTP Source (Priority: P2)

An operator pins a connector image and runs `spec → check → discover → read`, and the platform consumes a real `RECORD` stream as acquisition evidence while treating `STATE`, `LOG` and `TRACE` as control-plane data that must never become an observation. After this story, a real connector run has yielded at least N ≥ 10 records, each captured and observed, with the `STATE` checkpoint ordered strictly after durable record persistence.

**Why this priority**: §24 makes Airbyte "особая ветка" — it must not be integrated as "ещё один HTTP source". §194 makes it independently release-blocking. It follows SearXNG in §196 only because the runtime class lands in the same wave; the ordering is construction sequence, not release weight.

**Independent Test**: Run `live_airbyte_smoke` against a real connector: spec = success; check = success; discover = success; read started; RECORD observed; STATE observed **or** an explicit connector limitation recorded; Capture; Observation; Redpanda event; consumer succeeds — with `N >= 10` real records, or `all available records >= 1` where the connector physically yields fewer and **the reason is recorded, not masked** (§38, §81).

**Acceptance Scenarios**:

1. **Given** a connector, **When** it is executed, **Then** the call is `spec` / `check --config` / `discover --config` / `read --config --catalog --state` over a process or container boundary using a streaming stdout reader; `subprocess.run(..., capture_output=True)` is not used for `read()` (§25, §27).
2. **Given** a STDIO message stream, **When** messages are dispatched, **Then** `RECORD` and `STATE` are handled distinctly, and an unknown or unexpected protocol message type preserves the raw line to a quarantine/diagnostic lane rather than being silently discarded (§32).
3. **Given** `read STATE`, **When** the preceding records have not reached durable persistence, **Then** the state checkpoint is not processed: the order `receive record → persist observation → acknowledge durable persistence → process state checkpoint` is mandatory, or an irreversible evidence gap results (§35).
4. **Given** a connector run, **When** it fails, **Then** the failure is one of the observable, distinguishable states: `image_not_found`, `container_start_failed`, `spec_failed`, `check_failed`, `discover_failed`, `protocol_malformed`, `record_invalid`, `state_invalid`, `connector_runtime_failed`, `timeout`, `resource_limit_exceeded`, `network_denied`, `credential_unavailable`, `credential_rejected` (§37, §104).
5. **Given** 100 records and a crash at 101, **When** the run is recovered, **Then** the partial capture, the partial observations and a failure marker are preserved and the run is replayable — there is no rollback of the first 100 (§91, §92, §93).

---

### User Story 5 - A Generic External Tool Runtime Runs Maigret (Priority: P3)

An operator asks for a username and gets per-site Maigret results as observations, obtained through one generic `ExternalToolRuntime` boundary rather than a bespoke worker stack per tool. The `status.is_found()` flag stays an observation of the tool's execution, never an `entity_exists` fact.

**Why this priority**: §40 requires one generic `ExternalToolRuntime` for all three tools, so it is the natural point at which Maigret lands; §194 makes it independently release-blocking.

**Independent Test**: Run `live_maigret_smoke` with a controlled test username: tool starts; sites checked; ≥1 result record; Capture; Observation; Redpanda; consumer — and separately assert `≥1 observation`, `≥1 identifiable site result`, a raw artifact, a resolvable observation locator, an event visible in Redpanda and a completed downstream parser. Accuracy of individual site checks is **not** an acceptance condition; passing the acquisition protocol is (§46, §82).

**Acceptance Scenarios**:

1. **Given** a task, **When** it is executed, **Then** the first production branch uses the isolated external-tool boundary — not direct Python embedding — for security, fault isolation, dependency isolation, version pinning, resource limits and replay; direct embedding is only admissible after the isolated runtime succeeds (§42).
2. **Given** a username, **When** it is canonicalized, **Then** both the canonical and the raw username are retained and canonicalization never destroys the original value (§43).
3. **Given** a per-site result, **When** it becomes an observation, **Then** `site_name`, `status`, `url_user`, `http_status`, `rank`, `ids_data` and every additional genuinely present field are preserved, `status.is_found()` is not converted into `entity_exists = true`, and a timeout or HTTP error yields `observation status = failed/indeterminate` rather than `not_found` unless Maigret itself gives grounds for that conclusion (§44, §45, §105).

---

### User Story 6 - BBOT Events Cross a Donor-Schema Bridge (Priority: P4)

An operator runs a bounded BBOT scan and gets each BBOT event as a platform observation that carries the full donor provenance — `parent_chain` included — without BBOT's own event schema becoming the platform's, and without BBOT's native Kafka output module writing to the canonical observation topic.

**Why this priority**: second of the three tools on the one generic runtime; §194 makes it independently release-blocking.

**Independent Test**: Run `live_bbot_smoke` against a safe bounded test target with a hard timeout: scan starts; event stream exists; ≥1 event; Capture; Observation; Redpanda; consumer (§83).

**Acceptance Scenarios**:

1. **Given** a BBOT event, **When** it is bridged, **Then** the path is `BBOT event JSON → validate donor event → AcquisitionArtifact → Capture → Observation → EventEnvelope`, and the BBOT Kafka output module is **not** connected to the canonical observation topic (§47, §48).
2. **Given** a BBOT event, **When** it is captured, **Then** `type`, `id`, `uuid`, `data`/`data_json`, `scope`, `parent`, `parent_uuid`, `timestamp`, `module`, `module_sequence`, `discovery_context`, `discovery_path` and `parent_chain` are preserved **if present**, with no semanticisation at acquisition time (§48).
3. **Given** a `parent_chain`, **When** it is stored, **Then** it is donor provenance on the observation, and `A parent-of B` is not automatically a platform `RelationClaim` (§49, §3).

---

### User Story 7 - SpiderFoot CLI JSON Becomes Observations (Priority: P5)

An operator runs a bounded SpiderFoot scenario from a declarative tool definition and gets SpiderFoot's event stream as platform observations, with SpiderFoot's own correlation engine kept out of the platform graph.

**Why this priority**: last of the three tools on the one generic runtime; §194 makes it independently release-blocking.

**Independent Test**: Run `live_spiderfoot_smoke` as a bounded passive/investigative scenario: process starts; JSON emitted; event parsed; Observation created; Redpanda event; downstream processing. Do not require more than 1 event where runtime/source variation makes the count unstable (§84); ≥1 event required, ≥10 desirable where the target genuinely produces more (§55).

**Acceptance Scenarios**:

1. **Given** a tool definition, **When** SpiderFoot is executed, **Then** CLI parameters are supplied by the `ToolDefinition` as an argv array, `shell=True` is not used, and no argument is hardcoded in the runtime (§51, §52).
2. **Given** SpiderFoot JSON output, **When** it is converted, **Then** `scan / event / target / module / event type / data` become platform Observations, and the SpiderFoot JSON is not treated as a finished platform observation on arrival (§53).
3. **Given** a SpiderFoot correlation event, **When** it arrives, **Then** it is a tool observation that flows onward to interpretation; if the correlation is retained as an inference artifact it is retained as a provenance-bound observation, and the correlation engine does not write to the platform graph (§54, §118).

---

### User Story 8 - The Runtime Is Sandboxed, Governed and Bounded (Priority: P6)

An operator can state, in one declarative place, what each runtime is allowed to touch: how much CPU, memory, wall time, output, stdout, stderr, network, filesystem and concurrency it may consume, and under which resource class. After this story, no acquisition tool receives the Docker socket, host filesystem, host credentials, platform secrets or unbounded outbound egress, and a growing backlog reduces acquisition rate rather than expanding the Kafka backlog.

**Why this priority**: §196 places sandbox/resource controls after all runtime classes and before the live scenarios, because the live scenarios are what the controls make safe to run. It is P6 because until the runtimes exist there is nothing to bound.

**Independent Test**: Attempt to run a tool with the Docker socket mounted, with host filesystem access, and with unrestricted egress, and assert each is refused; assert a per-runtime limit breach yields `resource_limit_exceeded` with partial run state retained and replay possible; assert backlog growth reduces acquisition rate (§65, §36, §66).

**Acceptance Scenarios**:

1. **Given** any acquisition tool, **When** it is launched, **Then** it receives none of: the Docker socket, the host filesystem, host credentials, platform secrets, or unbounded outbound network; the path is `Acquisition Service → dedicated runner → isolated container` and `/var/run/docker.sock` is never mounted into an untrusted tool process (§65).
2. **Given** a runtime, **When** limits are declared, **Then** they are tool-specific rather than a single uniform `all tools = 2 GB / 10 m` ceiling: Maigret has `max_sites`/`max_connections`/`timeout`; Airbyte has max records, max output and connector timeout; BBOT has scan timeout and process/resource limits; SpiderFoot has max threads, runtime limit and output limit; SearXNG has max pages, request timeout and result-count limit (§143).
3. **Given** a growing backlog, **When** the scheduler considers concurrency, **Then** it does not expand concurrency with backlog; backpressure runs the other way, `backlog ↑ → acquisition rate ↓` (§66; constitution Backpressure constraint).
4. **Given** a donor project being integrated, **When** the manifest is written, **Then** it records `tool`, `source_repository`, `license`, `version`, `image`, `digest`, `integration_role`, `adapted_components`, `non_transferred_semantics` and `known_patches`, with upstream repo, commit, license, copied code, adapted code and the dynamic/external execution boundary — and no "magic clean room" is claimed (§150, §151).

---

### User Story 9 - An Operator Can Reproduce the Whole Result From a Clean Stack (Priority: P7)

An operator takes a clean stack, runs one command, and gets a machine-readable report plus a forensic artifact tree — and can then do it again from another clean stack and get the same result. After this story, the acceptance is not "the tests pass" but: the §204 eight-factor product is non-zero for all five families, the §200 sequence completes, and the required artifacts exist on disk with the ids an inspector needs.

**Why this priority**: §196 puts live scenarios, replay, the failure journal and clean-stack acceptance last, because each is a verification layer over a finished integration. This is P7, and it is nevertheless the story that decides whether the feature is complete at all: §0 and §204 make it the gate, not a formality.

**Independent Test**: From a fresh DB, fresh Redis, fresh ObjectStore namespace and fresh Redpanda topics/consumer group, run the acceptance command and read `artifacts/acquisition-integration/run-manifest.json` (§158, §188, §201); then `kill consumer → resume → all pending observations processed` (§200).

**Acceptance Scenarios**:

1. **Given** a clean stack, **When** the §200 sequence is executed — start stack, create investigation, run SearXNG, observe records in Redpanda, observe downstream processing, then the same for Airbyte, Maigret, BBOT and SpiderFoot — **Then** all five runtime paths are green, after which `kill consumer → resume` processes all pending observations, and `replay raw observation → same observation identity → same deterministic parser result` (§200).
2. **Given** an integration that has failed, **When** the work does not stop, **Then** the loop `RUN → OBSERVE → CLASSIFY FAILURE → PATCH → RESTART AFFECTED COMPONENT → REPLAY TASK → VERIFY → RUN AGAIN` runs until green acceptance or until a clearly recorded infrastructure blocker that genuinely cannot be removed from this execution context (§72).
3. **Given** a failure, **When** it is recorded, **Then** it is classified — build, configuration, dependency, container, process, network, DNS, TLS, authentication, protocol, parsing, identity, storage, Kafka, schema, consumer, downstream, performance, security policy, determinism — because a generic "integration failed" is forbidden (§73).
4. **Given** a DB migration is required, **When** acceptance is claimed, **Then** green is not accepted on an already-mutated local database: `migration up → smoke → migration replay/clean environment`, and the final smoke runs on a clean stack (§187, §188).

---

### Edge Cases

- **Pagination**: pages 1..N fetched but only the last page persisted is forbidden; every fetched page must be durable (§98). `HTTP 200 + non-empty body` is not a continue signal (§19). Page identity, request material and cache key must include `q`, `language`, `category`, `pageno`, `time_range` and `safesearch`, so `query A → cache hit → result of query B` cannot happen (§99).
- **Cache isolation**: a cache key must not permit `tenant A credential → cached response → tenant B`; at minimum it includes tenant, source, credential context and request (§100). Cross-tenant replay may share a content digest but access and control lineage stay tenant-scoped, and `tenant A event → tenant B observation resolution` must not occur (§166).
- **SearXNG responses**: HTTP 403 because JSON is disabled, HTTP 429, HTTP 5xx, an empty result set and a successful search with zero results are five distinct outcomes (§103). `HTTP 403` is `acquisition outcome: failed / access_denied`, not `results=[]` (§102). A changed page produces a **new** capture plus a new observation or lifecycle event, never an overwrite of the old capture (§176).
- **Airbyte streams**: an unknown message type is preserved to quarantine rather than discarded (§32); a malformed line must not poison the whole process when the protocol permits continuing, and a terminally corrupt connector is aborted, quarantined and its artifact retained (§149). `exit_code == 0` does not guarantee data, and `exit_code != 0` does **not** license discarding observations already received — partial data is preserved (§90). `no records` is not the same as `connector failed` (§104).
- **Airbyte state**: a state checkpoint processed before its preceding records are durable yields `STATE persisted / records lost / next run starts after state` — an irreversible evidence gap (§35). On retry, `state_before` is the last durable checkpoint, not an arbitrary stdout tail (§93). Full-refresh must be verified separately from incrementality: same source state yields new acquisition occurrences, not a semantic overwrite of previous evidence (§177, §178).
- **Record counts**: a connector that physically returns fewer than 10 records is reported as `all available records >= 1` **with the reason recorded, not masked** (§38). A SpiderFoot target whose event count is unstable must not be held to more than 1 event (§55, §84). Nondeterministic live tools are reconciled as `at least one` plus an explanation (§137).
- **Multi-record proof**: the first successful run must use a source that genuinely emits several records, to disprove `first record only`, `last record only` and `one observation per process` bugs — `record_count > 1` for Airbyte, `results_count > 1` for SearXNG where the engine returns them (§164).
- **Tool outcomes**: Maigret must distinguish `site unavailable`, `timeout`, `blocked`, HTTP 404, `not found`, `found`, `indeterminate` and `tool failure`, and must not collapse into a binary `found / not_found` (§105). BBOT and SpiderFoot must separate tool process failure, module failure, target result, transport error and partial run (§106).
- **Ordering and duplicates**: global Kafka ordering must not be assumed; ordering guarantees are scoped to key/partition and record identity must not depend on incidental global ordering (§193). The same `EventEnvelope` deliberately delivered twice must yield one semantic processing result with idempotency evidence (§192). A consumer crash mid-processing must replay the event without semantically duplicating the observation (§191). Producer-active/consumer-stopped must lose no observations once the consumer resumes (§190).
- **Resource and process edges**: on timeout, `SIGTERM → grace → SIGKILL` with the result recorded (§146); child processes are tracked so no orphan survives a timeout (§147); `max_stdout_bytes` and `max_stderr_bytes` are separate ceilings, and exceeding them either kills the process with `reason = output_limit_exceeded` or performs controlled truncation only where the protocol safely supports it, with partial raw output retained (§148). RSS stays bounded, the stdout parser never accumulates a whole run, ObjectStore writes are streamed and bounded, state processing does not block indefinitely and Kafka publish does not block the connector forever (§171).
- **Lifecycle**: `unchanged` is not `not acquired` (§101). HTTP 4xx, connector errors and tool timeouts never become fabricated empty results (§102).
- **Version drift**: changing `runtime_version` must not silently mutate old observations; old records preserve their original provenance (§168). A SearXNG page that changed yields a new capture, and a refetch decided by the frontier is a **new acquisition task and a new Capture**, never a mutation of an existing observation (§175).

---

## Requirements *(mandatory)*

### Functional Requirements

Every FR below carries the numbered section of `input.md` it is rendered from. An FR with no `§` source would be fabricated; none is present.

#### A. Completion Gate, Insufficiency Conditions and Prohibitions (§0, §0.1, §76, §160, §202, §203)

- **FR-001** (§0): The feature MUST NOT be declared complete on the strength of any of the following alone: adapters written; source definitions registered; unit tests passing; fixture tests passing; the worker being able to start; the tool container being invoked correctly; a message appearing in stdout; a message having been sent to Kafka; `observation.created` existing in code; Redpanda containing messages; a downstream consumer existing but having processed nothing.
- **FR-002** (§0.1): The system MUST prove the full runtime path `Investigation → AcquisitionTask → Scheduler/Dispatcher → concrete worker_ref + source/runtime definition → real launch of the external source → real output source → Capture/raw artifact → ObjectStore → Observation/ObservationRecord → canonical EventEnvelope → Redpanda → real downstream consumer → successful processing of the observation → identifiable persisted result`.
- **FR-003** (§0.1): At least one proven runtime trace MUST exist **for each of the five families**, minimally exhibiting `source start → task_id → worker_ref → capture_id → raw_ref → observation_id → event_id → topic → partition/offset → consumer group → downstream processing result`.
- **FR-004** (§0.1): Every identifier in that chain MUST be available for forensic inspection.
- **FR-005** (§0, §198): The primary unit of progress is the length of the runtime path actually traversed. `"event_id E123 at partition 2 offset 847 consumed by group G123"` outranks `"event_id appeared in topic observation"`, which outranks `"adapter implemented"`.
- **FR-006** (§202): A final `PASS` MUST NOT be recorded if any of the five acceptance paths has been replaced by a `mock source`, `fake subprocess`, `fake Kafka`, `fake observation`, `manual DB insert` or `manual topic publication`. These are permitted only at lower testing levels.
- **FR-007** (§203): The system MUST NOT emit `observation.created` via a `catch Exception` path, MUST NOT convert a tool failure into an empty result, MUST NOT mark something processed when Kafka is unavailable, and MUST NOT turn a consumer failure into a green test. Any failure MUST remain a failure until it is eliminated.
- **FR-008** (§76): After a real acceptance requirement exists, the system MUST NOT reach green through `xfail`, `skip`, `mock`, `monkeypatch`, fake Redpanda or fake source output. Offline unit/fixture tests are permitted but do not replace the live gate.
- **FR-009** (§76): A live test MUST carry the marker `@pytest.mark.live_integration` and MUST NOT be automatically skipped during release validation.
- **FR-010** (§153): A live test MUST NOT be synthetic. `producer.produce(fake_observation)` is not SearXNG acceptance; an actual HTTP request and actual SearXNG response are required, and likewise an actual Airbyte/Maigret/BBOT/SpiderFoot process.
- **FR-011** (§161): A failure MUST NOT lower the acceptance bar. If SearXNG fails, SearXNG is not skipped but inspected, patched and re-run; if an Airbyte connector fails it is not replaced by a fixture as a final decision. A fixture remains a protocol test; a live connector remains integration proof.
- **FR-012** (§160): Any single one of the following MUST block release: `observation_id random`; `event_id random for replay-sensitive events`; `raw artifact absent`; `observation without raw lineage`; `event without canonical EventEnvelope`; `tool bypasses policy`; `tenant information lost`; `investigation_id lost`; `consumer cannot replay`; `pagination loses pages`; `Airbyte STATE treated as evidence`; `donor event written directly to graph`; `secret appears in logs/events`; `live source never actually executed`; `Redpanda path not exercised`; `downstream consumer not exercised`. This list is a floor, not a ceiling.
- **FR-013** (§3): No donor runtime may produce `tool output → entity`, `tool output → relation → graph edge`, or `tool output → "fact"`. The only admissible path is `tool output → Capture → Observation → Interpretation → Mention / TypeSignal / RelationSignal / Candidate → Validation → Admission → Claim → Projection`.
- **FR-014** (§3): Maigret `status=found` MUST be treated as a tool observation, not an Entity. BBOT `parent_chain` MUST be treated as donor provenance / derivation context, not automatically a `RelationClaim`. A SpiderFoot correlation event MUST be treated as SpiderFoot's own observation/inference, not the platform's assertion about the world. Airbyte `State` MUST be treated as a control-plane checkpoint, not evidence. A SearXNG search result MUST be treated as an observation of a search engine response, not proof of the truth of the target URL.
- **FR-015** (§118): Acquisition code MUST NOT import or call `GraphWriter`, `GraphEdge`, `RelationClaim`, `EntityStore` or `KnowledgeGraph` on the ordinary acquisition path, even when the donor tool produces relationship-like output.
- **FR-016** (§119): Acquisition MUST NOT perform direct entity resolution. It may produce `raw identifier`, `username`, `URL`, `IP`, `domain`, `email-like string` and `tool id`; resolution is downstream.
- **FR-017** (§112): The integration MUST NOT re-implement the zero-layer semantic model. The path is `zero-layer request → acquisition task → source runtime → observation → zero-layer interpreter`, not `source → ZeroLayerObservation directly`.
- **FR-018** (§113): SearXNG is a natural discovery source, but frontier enqueue is a downstream interpretation/discovery step; the SearXNG runtime itself MUST NOT create canonical frontier state.
- **FR-019** (§114): `discover() → catalog` is source metadata usable by a planner (`discover → available streams → configured catalog → read`); the catalog MUST NOT be an observation of the world.
- **FR-020** (§115): For Maigret, BBOT and SpiderFoot, a `tool-produced event` is an observation **of a tool's execution output**, not a raw world fact, and that distinction MUST be expressed in the provenance schema.
- **FR-021** (§60): Donor reuse is the default and is expected for CLI invocation, request construction, pagination, result parsing, site catalogues, event schemas, tool wrappers, retry mechanics and resource estimation.
- **FR-022** (§60): Entity semantics, claim semantics, graph mutation, identity decisions, evidence adjudication, ontology assumptions and automatic trust decisions MUST NOT be transferred from a donor without adaptation.
- **FR-023** (§58, §59): `apps/acquisition/sources/catalogue.py` remains the registry/catalogue layer. A donor YAML catalogue may be used as a data source, but every source is adapted to platform semantics, and donor YAML MUST NOT be permitted to determine `Entity / Relation / Graph edge / Claim / Admission` directly. Graph mutation from a donor path is forbidden.

#### B. Canonical Artifact, Capture and Raw Storage (§5, §6, §7, §8, §61)

- **FR-024** (§5): The system MUST define `AcquisitionArtifact` carrying `task_id`, `source_id`, `worker_ref`, `target_uri`, `locator`, `body`, `content_type`, `fetched_at`, `transport`, `producer`, `producer_version` and `metadata`.
- **FR-025** (§5): Streaming runtimes MUST NOT be required to buffer the entire run before emitting. The preferred interface is `async for artifact in worker.run(task): await artifact_sink.accept(artifact)`.
- **FR-026** (§6): `Capture` MUST mean what was physically obtained or produced by the runtime; `Observation` MUST mean the addressable object/record extracted from a capture. Per runtime: SearXNG capture = whole JSON response for a query page, observation = `result[0]`, `result[1]`, …; Airbyte capture = connector run / ordered message stream, observation = RECORD #0, #1, …; Maigret capture = complete tool result artifact or stream, observation = site=GitHub, site=Reddit, site=VK, …; BBOT capture = scan output, observation = event #0, #1, …; SpiderFoot capture = scan result export / event stream, observation = event #0, #1, …
- **FR-027** (§7): Raw bytes MUST NEVER go to Redpanda. They are stored in the ObjectStore at `raw/{tenant}/{yyyy}/{mm}/{sha256}` or the existing equivalent.
- **FR-028** (§7): Redpanda MUST receive only `capture_id`, `observation_id`, `raw_ref`, `locator`, `tenant_id`, `investigation_id`, `source_id`, `task_id` and other refs/metadata.
- **FR-029** (§8): The existing `Capture` MUST be used; a second competing capture model MUST NOT be created. `Capture` is registered as a first-class durable object.
- **FR-030** (§8): `Capture` MUST preserve `tenant_id`, `source_id`, `source_family`, `target_uri`, `locator`, `content_digest`, `content_length`, `media_type`, `fetched_at`, `time_basis`, `transport`, `ingest_batch_id`, `ingest_attempt` and `recorded_by`.
- **FR-031** (§61): Every persisted artifact MUST have a `sha256`, and `record_digest = SHA256(canonical_json(record))` with canonical JSON using deterministic key ordering and normalized encoding.

#### C. Deterministic Identity and the Replay Invariant (§10, §11, §12, §96, §97, §123, §124, §165)

- **FR-032** (§10): A `RecordLocator` MUST be deterministic and reproducible, using the family-specific forms `json:results[N]` (SearXNG), `airbyte:message:17` or `airbyte:stream=<namespace>/<stream>:record:<sequence>` (Airbyte), `bbot:event:<message_index>` (BBOT), `spiderfoot:event:<sequence>` (SpiderFoot) and `maigret:site:<canonical_site_name>` (Maigret). The locator is a provenance address, not a semantic identity.
- **FR-033** (§11): Observation identity MUST NOT be based on `uuid.uuid4()`, `datetime.now()` as part of identity, `random`, process id, thread id or memory address.
- **FR-034** (§11): Observation id MUST be `OBS-{digest128(identity_schema | tenant_id | capture_id | locator | record_digest)}`.
- **FR-035** (§11): `Capture` id MUST remain deterministic per the existing `Capture` model, and event id MUST be deterministic relative to `event_type | event_version | observation_id | producer | producer_version | lifecycle`.
- **FR-036** (§11, §12): Replaying the same acquisition artifact MUST yield `capture_id == same`, `observation_id == same` and `event_id == same` when the semantic material has not changed.
- **FR-037** (§12): Re-running one source task on an identical fixture or live response MUST NOT produce a logical avalanche of duplicates. The same observation id / same content hash / same event id on redelivery is admissible, and the consumer MUST be idempotent. Kafka exactly-once MUST NOT be relied upon.
- **FR-038** (§96): Determinism MUST be verified at minimum over source task identity, capture identity, observation identity, record locator, canonical JSON hashing, event identity, pagination and tool result normalization. Live runs may vary in order, but re-parsing a persisted raw artifact MUST be deterministic.
- **FR-039** (§97): Every persisted collection that is a semantic projection of one raw payload MUST be sorted deterministically. Reliance on `dict insertion order from donor`, `set order`, `thread timing` or `async completion order` is forbidden wherever it affects ids or canonical serialization.
- **FR-040** (§123): Database idempotency MUST be enforced by unique constraint on deterministic identity: `capture_id` unique, `observation_id` unique, and under record-level semantics additionally `(capture_id, locator, record_digest)`.
- **FR-041** (§124): ObjectStore idempotency MUST hold: identical bytes produce the same `sha256` and therefore the same raw object, with no overwrite.
- **FR-042** (§165): Performing `capture → record extraction → observation IDs` twice MUST yield the same capture identity, the same observation identities and the same locator identities.

#### D. The Record-Level Observation Seam (§9, §33, §34, §122)

- **FR-043** (§9): `ObservationGate.ingest(body=...)` remains the blob/capture-level path, and a second, explicitly expressed path MUST be added for record-oriented sources.
- **FR-044** (§9): `ingest_capture` MUST accept the physical payload (`body`, `metadata`, `source`, `task`, `investigation`, `tenant`) and create the `Capture`, the `raw_ref` and a parent Observation/Capture record.
- **FR-045** (§9): `ingest_record` MUST NOT re-store the whole blob. It accepts `capture_id`, `record_locator`, `record_digest` and `record_metadata` and creates an addressable `ObservationRecord`.
- **FR-046** (§33): Every `RECORD` MUST be stored with `namespace`, `stream`, `data`, `emitted_at`, `sequence` and `message_index`. Records from several streams may interleave, and `groupby(stream)` with an assumption of stream-serialized input MUST NOT be used.
- **FR-047** (§34): Airbyte observation identity MUST be built on `capture_id | record_locator | record_digest`, not on record content alone, because `record A in stream X` and `record A in stream Y` may have identical JSON yet represent different observed occurrences.
- **FR-048** (§122): If the DB schema lacks first-class capture persistence, a migration MUST be added, with minimum relational relationships `captures` / `observations` where `observations.capture_id` and `observations.locator` are first-class fields. Everything MUST NOT be pushed into a generic JSONB when durable query/reconstruction requires structural columns.

#### E. Routing, Registration and Dispatch (§13, §14, §56, §57, §67, §167, §168)

- **FR-049** (§13): Routing MUST distinguish `execution_class`, `required_capabilities`, `worker_ref` and `runtime_ref`, and the pair `worker_ref: http` / `runtime_ref: searxng` MUST be expressible.
- **FR-050** (§13): The scheduler MUST resolve the **explicit runtime first** and use capability matching only as a compatibility check.
- **FR-051** (§13): The routing `BBOT task → capability=http → generic HttpWorker` is forbidden, and an Airbyte task MUST NOT land in the HTTP worker.
- **FR-052** (§14): `SourceDefinition` MUST be extended with the minimum necessary fields: `source_id`, `name`, `enabled`, `worker_ref`, `runtime_ref`, `execution_class`, `capabilities`, `input_schema`, `output_schema`, `contact_class`, parser/interpreter hint, `resource_class`, `timeout`, `max_output_bytes`, `source_version`, `runtime_version`, `provenance`.
- **FR-053** (§14): `source_id` remains content-addressed and `runtime_ref` determines the concrete executable implementation.
- **FR-054** (§56): All five sources MUST be launched through the single production entrypoint `InvestigationWorkflow`, not through a direct worker/connector/graph call, and `investigation_id`, `tenant_id`, `task_id`, `source_id`, `worker_ref` and `runtime_ref` MUST be present along the entire live path.
- **FR-055** (§57): Dispatch MUST be `AcquisitionTask → resolve worker_ref → resolve runtime_ref → validate capabilities → validate policy → execute`, not `infer worker from capabilities` when the source is already explicitly defined.
- **FR-056** (§67): The existing canonical topic catalogue MUST be used with the minimum path `acquisition.request → acquisition worker → observation.created → interpretation / discovery consumer`. One topic per donor tool is forbidden — `maigret-observations`, `bbot-observations` and `spiderfoot-observations` are prohibited; tool identity lives in metadata/provenance.
- **FR-057** (§167): Setting `enabled=false` MUST disable scheduling without deleting the definition; no task is created for a disabled source and the runtime id stays stable.
- **FR-058** (§168): Changing `runtime_version` MUST NOT silently mutate old observations; old records preserve their original provenance.

#### F. HTTP Runtime — SearXNG (§15–§23, §94, §99, §103, §139, §172, §176)

- **FR-059** (§15.1): The SearXNG source MUST register `worker_ref = http`, `runtime_ref = searxng`, `execution_class = api/http`, and against a local container MUST address `http://searxng:8080/search`. The platform MUST NOT call Google/Bing/Brave or similar directly; SearXNG performs federation.
- **FR-060** (§16): The minimum request MUST be `GET /search` with `q`, `format=json`, `pageno`, `language`, `categories`, `safesearch`, `time_range`. `q` is mandatory, `pageno` starts at `1`, and JSON MUST be permitted by the instance configuration. The YAML MUST NOT be copied literally without checking the current catalogue loader; it is adapted to the existing source schema.
- **FR-061** (§17): Before the first acquisition task the system MUST prove via `GET /config` or an equivalent local probe that SearXNG responds, that JSON format is enabled, that `/search` is available and that at least one engine is enabled. If JSON is absent, the outcome is `SEARXNG_JSON_FORMAT_DISABLED` and the source is not runtime-ready; an undeclared output format may return HTTP 403.
- **FR-062** (§18): The task MUST carry `query`, `language`, `categories`, `page`, `max_pages`, `time_range` and `safesearch`, with `query` the minimum. The query is an acquisition instruction, not semantic truth.
- **FR-063** (§19): A fixed-`max_pages` `HttpSourceExecutor` MUST NOT be the production SearXNG implementation. Pagination MUST advance through `page 1, 2, 3, …` with a stop condition that inspects response **content**, following `JSON parse → inspect result collection → continue while results remain → obey hard max_pages`. `HTTP 200 + body != empty → fetch next page` is inadmissible.
- **FR-064** (§19): Two safeguards are mandatory — `hard_max_pages` and `hard_runtime_budget` — so that a misbehaving pagination source cannot become an infinite task.
- **FR-065** (§20): Every HTTP response page MUST become a durable capture, and the parser/expander MUST produce `OBS-001 → results[0]`, `OBS-002 → results[1]`, `OBS-003 → results[2]`, each observation referencing its `capture_id` and `locator`.
- **FR-066** (§21): The original result object MUST NOT be destroyed after extracting `title`, `url`, `content`, `engine`, `category`, `publishedDate`, `thumbnail`, `template`, `score` or any other genuinely present field. Fields MUST NOT be invented; an absent field is `null` and is not a semantic assertion; unknown top-level fields stay reachable in the raw artifact.
- **FR-067** (§22): A real consumer MUST exist on the path `observation.created → SearXNG observation decoder → structured observation → discovery / mention producer`, minimally `search result → URL candidate / document discovery candidate`, remaining provenance-bound to the source capture via `source = SearXNG`, `observation_id`, `capture_id` and `result_locator`.
- **FR-068** (§23): The SearXNG acceptance run MUST evidence all **15** steps: task created; task dispatched; searxng runtime invoked; HTTP 200; JSON parsed; ≥1 result emitted; capture stored; raw_ref exists; ≥1 observation persisted; `observation.created` in Redpanda; consumer receives; consumer fetches raw_ref; consumer resolves locator; downstream processing completes; processing record persisted.
- **FR-069** (§94): When the raw response is stored, re-parsing without HTTP MUST work — a new parser/extractor/normalization with no repeat network request.
- **FR-070** (§99): Query and params MUST participate in request identity. For SearXNG, `q`, `language`, `category`, `pageno`, `time_range` and `safesearch` are part of the canonical request material; `query A → cache hit → result of query B` MUST NOT occur.
- **FR-071** (§103): The system MUST distinguish `HTTP 403 because JSON disabled`, `HTTP 429`, `HTTP 5xx`, `empty result set` and `successful search with zero results`.
- **FR-072** (§139): SearXNG reconciliation MUST report `pages fetched`, `results reported by parser` and `observations persisted`, with `pages >= 1`, `results >= 1` and `observations == retained result count`; any duplicate policy is explained separately.
- **FR-073** (§172): SearXNG-specific performance limits MUST cover page limit, result count limit, HTTP timeout, parallel query limit and engine upstream variance. Latency differences between upstream engines MUST NOT be counted as a routing-layer error.
- **FR-074** (§176): A changed SearXNG page MUST produce a new capture plus a new observation or lifecycle event, never an overwrite of the old capture.

#### G. Airbyte — Connector Execution Protocol (§24–§39, §93, §104, §138, §149, §171, §177, §178)

- **FR-075** (§24): Airbyte MUST NOT be integrated as "ещё один HTTP source". It is a connector execution protocol requiring an `AirbyteRuntime`, not an `HttpSourceExecutor` plus a random connector URL.
- **FR-076** (§25): The runtime interface MUST provide `spec`, `check`, `discover` and `read`, where `read` is an async iterator of `AirbyteMessage`, executed over a process/container boundary.
- **FR-077** (§26): The **STDIO JSON protocol** MUST be used for the first phase even where socket mode is available, for maximum transparency of `subprocess stdout → line parser → AirbyteMessage` and simpler forensic debugging. Socket mode is a separate optimization track and is not a blocker.
- **FR-078** (§27): Invocation MUST correspond to `spec` / `check --config` / `discover --config` / `read --config --catalog --state`. `subprocess.run(..., capture_output=True)` MUST NOT be used for a potentially large `read()` stream; a streaming stdout reader is required.
- **FR-079** (§28): Message classification MUST be preserved: `spec` = control-plane metadata, `check` = connectivity/credential diagnostic, `discover` = catalog metadata, `read RECORD` = **acquisition evidence**, `read STATE` = checkpoint / control-plane state, `LOG` = operational telemetry, `TRACE` = connector runtime diagnostics.
- **FR-080** (§28): `STATE`, `LOG` and `TRACE` MUST NOT automatically become observations.
- **FR-081** (§29): The catalog MUST be stored separately as immutable run metadata: `connector_ref`, `image_digest`, `config_ref`, `catalog_ref`, `state_before_ref`, `state_after_ref`. A secret config MUST NOT be placed in raw evidence; secrets are referenced via secret manager / secret refs.
- **FR-082** (§30): `access_token`, `api_key`, `password`, OAuth refresh tokens and private credential material MUST NEVER appear in Redpanda, logs, `EventEnvelope`, `Capture` metadata or Git. Provenance stores `credential_ref` and `credential_version`, never a credential value.
- **FR-083** (§31): An indefinitely mutable tag MUST NOT be the sole provenance identity. The `connector image`, `connector version`, `image digest`, `protocol version` and `runtime version` MUST be pinned — for example `airbyte/source-github:2.7.1` plus `sha256:...` — and the version written into acquisition provenance.
- **FR-084** (§32): The read stream MUST be `docker/process → stdout line → JSON decode → AirbyteMessage → switch(type)`, handling `RECORD`, `STATE`, `LOG` and `TRACE`, and MUST NOT crash on new or unexpected protocol message types. An unknown type is handled as `preserve raw line → quarantine / diagnostic lane → do not silently discard`.
- **FR-085** (§35): State checkpointing order is mandatory: `receive record → persist observation → acknowledge durable persistence → process state checkpoint`. A `STATE` MUST NOT be treated as confirmation of a fact when the preceding records are not guaranteed durable; otherwise `STATE persisted / records lost / next run starts after state` is an irreversible evidence gap.
- **FR-086** (§36): The stdout reader MUST remain naturally flow-controlled. Reading entire stdout into RAM and an unbounded `asyncio.Queue` are both forbidden. Limits MUST exist for `max buffered messages`, `max buffered bytes`, `max record bytes`, `max run bytes`, `max runtime` and `max records/run`; on breach the outcome is `resource_limit_exceeded` with partial run state preserved and replay/retry possible.
- **FR-087** (§37): The failure matrix MUST cover at minimum `image_not_found`, `container_start_failed`, `spec_failed`, `check_failed`, `discover_failed`, `protocol_malformed`, `record_invalid`, `state_invalid`, `connector_runtime_failed`, `timeout`, `resource_limit_exceeded`, `network_denied`, `credential_unavailable` and `credential_rejected`, and every state MUST be observable.
- **FR-088** (§38): The real acceptance MUST cover `connector image resolved → spec succeeds → check succeeds → discover succeeds → catalog persisted → read starts → ≥ N real RECORD → RECORD → Capture/Observation → STATE processed correctly → observation.created into Redpanda → downstream consumer receives → consumer resolves record → processing succeeds`, with **N >= 10**. Where a connector physically returns fewer than 10 records, `all available records >= 1` is permitted but **the reason MUST be recorded, not masked**.
- **FR-089** (§39): Before arbitrary enterprise connectors, at least one near-baseline connector MUST exist that starts without manual UI, works in a test environment, has a deterministic source, yields several streams or at least one, emits multiple RECORDs, emits STATE and allows resume verification. If a real live connector requires external credentials, a **deterministic fixture connector as a protocol-validation harness** MUST be added — and a real connector run MUST still be performed afterwards. The fixture proves correctness of the protocol bridge; the live connector proves correctness of the integration.
- **FR-090** (§93): `state_before` / `state_after` MUST be preserved and state MUST NOT be an observation. On retry, `state_before` MUST be the last durable checkpoint, never an arbitrary current stdout tail.
- **FR-091** (§104): The system MUST distinguish `check failed`, `read failed`, `no records`, `catalog empty`, `malformed protocol`, `connector crash`, `auth denied` and `network denied`. `no records` is NOT equivalent to `connector failed`.
- **FR-092** (§138): Airbyte reconciliation MUST count `TOTAL messages`, `RECORD`, `STATE` and `LOG/TRACE` separately, with `record_count > 0` and `observation_count == record_count` when no RECORD was filtered by a policy layer. STATE is not part of the observation count.
- **FR-093** (§149): The streaming parser MUST be a stateful `buffered line → UTF-8 decode → JSON decode → AirbyteMessage validation → dispatch`. A malformed line MUST NOT poison the whole process when the protocol permits continuing; a terminally corrupt connector is aborted, quarantined and its artifact retained.
- **FR-094** (§171): Airbyte-specific performance MUST hold: RSS remains bounded, the stdout parser does not accumulate the entire run, ObjectStore writes are streamed/bounded, STATE processing does not block indefinitely, and Kafka publish does not block the connector forever.
- **FR-095** (§177): Airbyte incrementality MUST be verified as `run 1 → observations → state checkpoint`, `run 2 → resumes`, confirming that duplicate prevention does not suppress legitimately new records.
- **FR-096** (§178): Airbyte full-refresh semantics MUST be verified separately: the same source state yields **new acquisition observation occurrences**, not a semantic overwrite of previous evidence.

#### H. Generic External Tool Runtime (§40, §41, §42)

- **FR-097** (§40): Maigret, BBOT and SpiderFoot MUST NOT each receive a separate heavyweight worker stack. A single `ExternalToolRuntime` with a declarative `ToolDefinition` MUST be provided, carrying `tool_id`, `runtime`, `image`, `entrypoint`, `argv`, `input_mapping`, `output_mode`, `record_parser`, `timeout`, `max_stdout_bytes`, `max_stderr_bytes`, `max_records`, `network_policy`, `filesystem_policy`, `resource_class` and `version`.
- **FR-098** (§41): The runtime principle MUST be `AcquisitionTask → ToolDefinition → argv/config construction → sandbox/container → stdout/event/artifact stream → parser → AcquisitionArtifact → Observation Gate`. Donor-specific internals MUST NOT be carried into the canonical domain.
- **FR-099** (§42): The first production branch for Maigret MUST use the **isolated external-tool boundary** even where direct library embedding is possible — for security, fault isolation, dependency isolation, version pinning, resource limits and replay. Direct Python embedding is admissible only after the isolated runtime succeeds.

#### I. Maigret (§43, §44, §45, §46, §82, §105, §140, §179)

- **FR-100** (§43): The task MUST carry `username`, `id_type`, site selection/filter, `timeout`, `max sites` and profile parsing mode. Both the canonical and the raw username are stored, and canonicalization MUST NOT destroy the original value.
- **FR-101** (§44): Each site result MUST preserve `site_name`, `status`, `url_user`, `http_status`, `rank`, `ids_data` and all additional genuinely present fields. `status.is_found()` MUST NOT be turned into `entity_exists = true`.
- **FR-102** (§45): Observation metadata MUST carry `tool = maigret`, `tool_version`, `database_version`, `site_name`, `site_rank` and `request_username`; under proxy, `proxy_mode` and `proxy_ref` but never a secret. A result with a timeout or HTTP error yields `observation status = failed/indeterminate`, not `not_found`, unless Maigret itself gives grounds for a `not_found` inference.
- **FR-103** (§46): The Maigret live acceptance is `username → Maigret → several site checks → stdout/result → capture → observation(s) → Redpanda → consumer`, evidencing `≥1 observation`, `≥1 identifiable site result`, an existing raw artifact, a resolvable observation locator, an event visible in Redpanda and a completed downstream parser. The accuracy of individual site checks is not an acceptance condition; passing the acquisition protocol is.
- **FR-104** (§105): The system MUST distinguish `site unavailable`, `timeout`, `blocked`, `HTTP 404`, `not found`, `found`, `indeterminate` and `tool failure`, and MUST NOT collapse them into a binary `found / not_found`.
- **FR-105** (§140): Maigret reconciliation MUST report `sites scheduled`, `sites completed`, `results yielded` and `observations persisted`.
- **FR-106** (§179): The Maigret site database is part of provenance and a database change MUST be recorded in run provenance.

#### J. BBOT (§47, §48, §49, §50, §83, §106, §141, §180)

- **FR-107** (§47): `JSON/NDJSON output` MUST be used. The BBOT Kafka module MUST NOT be connected to the canonical observation topic, because its event schema is a BBOT schema and not the platform's `EventEnvelope`.
- **FR-108** (§48): The event bridge MUST be `BBOT event JSON → validate donor event → AcquisitionArtifact → Capture → Observation → EventEnvelope`, preserving where present: `bbot event type`, `bbot event id`, `bbot uuid`, `bbot data/data_json`, `scope`, `parent`, `parent_uuid`, `timestamp`, `module`, `module_sequence`, `discovery_context`, `discovery_path` and `parent_chain`. No semanticisation occurs at acquisition time.
- **FR-109** (§49): `parent_chain` MUST be preserved as donor provenance (`OBS-BBOT-EVENT-X → provenance.parent_chain → [...]`) and MUST NOT imply that `A parent-of B` is automatically a platform `RelationClaim`.
- **FR-110** (§50): The BBOT acceptance is `BBOT starts → scan completes / bounded stop → events received → at least one event persisted → raw run preserved → observation created → Redpanda event emitted → downstream consumer receives → donor event parser succeeds`, using a safe test target and a scan with a hard timeout.
- **FR-111** (§106): Tool process failure, module failure, target result, transport error and partial run MUST be kept separate for BBOT and SpiderFoot.
- **FR-112** (§141): BBOT reconciliation MUST report `events seen`, `events parsed`, `events persisted`, `events published` and `events processed`.
- **FR-113** (§180): BBOT event provenance MUST preserve `BBOT version`, `preset/config identity` and `module identity`.

#### K. SpiderFoot (§51, §52, §53, §54, §55, §84, §142, §181)

- **FR-114** (§51): The CLI JSON boundary is `-s TARGET -m modules -t event types -u use case -o json`; export of scan data as JSON MUST be supported.
- **FR-115** (§52): Parameters MUST be supplied by the `ToolDefinition` and MUST NOT be hardcoded in the runtime. `shell=True` MUST NOT be used; argv is passed as `argv: list[str]`.
- **FR-116** (§53): SpiderFoot JSON MUST NOT be treated as a finished platform observation on arrival. `scan / event / target / module / event type / data` becomes a platform Observation.
- **FR-117** (§54): The SpiderFoot correlation engine MUST NOT write to the platform graph automatically. The path is `SpiderFoot correlation output → tool observation → interpretation`; where the correlation is retained as an inference artifact it is retained as a provenance-bound observation.
- **FR-118** (§55): The SpiderFoot acceptance is `target → SpiderFoot → JSON event stream/export → Capture → Observation(s) → Redpanda → consumer → downstream processing`, with a minimum of `≥1 event` and a desirable `≥10` where the target genuinely produces more.
- **FR-119** (§84): The live scenario is a bounded passive/investigative scenario asserting process start, JSON emitted, event parsed, Observation created, Redpanda event and downstream processing. An event count above 1 MUST NOT be required where runtime/source variation makes it unstable.
- **FR-120** (§142): SpiderFoot reconciliation MUST report `events exported`, `events parsed`, `events observed` and `events processed`.
- **FR-121** (§181): The run MUST preserve `selected modules`, `use case`, `event filters` and `tool version`, without which the same CLI target is not reproducible.

#### L. Events, Topics, Envelope and Causal Chain (§68, §69, §70, §71, §116, §117, §120, §121, §155, §156, §157)

- **FR-122** (§68): The existing protobuf `EventEnvelope` MUST be used, carrying the mandatory routing fields `event_id`, `event_type`, `event_version`, `producer`, `producer_version`, `produced_at`, `tenant_id`, `investigation_id`, `source_id`, `work_id`, `region_id`, `observation_id`.
- **FR-123** (§69): The payload MUST be small and replayable and carry **refs only** — for example `{"capture_id": "CAP-...", "observation_id": "OBS-...", "raw_ref": "s3://...", "locator": "airbyte:message:17"}`. Raw body, large JSON arrays, an entire BBOT scan, an entire Airbyte result stream and a large SpiderFoot scan MUST NOT be sent.
- **FR-124** (§70): The following MUST be observable: `topic`, `partition`, `offset`, `event_id`, `observation_id`, `task_id`, `consumer group`, `consumer lag` and `processing result`. A diagnostic snapshot MUST be saved for every acceptance run.
- **FR-125** (§71): Every E2E run MUST create an `integration_run_id` and a trace manifest carrying `integration_run_id`, `tenant_id`, `investigation_id`, `task_id`, `source_id`, `worker_ref`, `runtime_ref`, `runtime_version`, `capture_ids`, `observation_ids`, `event_ids`, `topics`, `consumer_group`, `offsets` and `processing_results`. The trace manifest is itself an operational artifact.
- **FR-126** (§116): Provenance graph edges MUST be expressible as `Observation → Capture → Runtime → Source → Tool/version`; derivation as `ProcessedObservation → Observation → Parser version`; evidence lineage as `Claim → Evidence → Observation → Capture`. Evidence lineage and derivation lineage MUST NOT be mixed.
- **FR-127** (§117): `causation_id = input event_id` and `correlation_id = investigation/run correlation`, so that `observation.created(E1) → mention.created(causation_id=E1)`.
- **FR-128** (§120): Canonical event schemas MUST be registry-validated. Each new event version requires an `event schema`, `version`, `producer` and `consumer compatibility` — never an ad hoc JSON shape.
- **FR-129** (§121): Where existing consumers expect v2 observation events, the integration MUST either preserve v2 or add a new version, and MUST NOT silently modify semantics under the same version.
- **FR-130** (§155): Everything originating from an Investigation MUST carry `correlation_id`, unchanged across `scheduler → worker → observation gate → Kafka → downstream`.
- **FR-131** (§156): The causation chain MUST be expressible as `investigation.started → acquisition.request → observation.created → discovery.discovered` with `E_investigation ↓ causation E_acquisition ↓ causation E_observation ↓ causation E_discovery`.
- **FR-132** (§157): A final E2E trace MUST be recoverable in the form `INV-123 / TSK-123 / worker http / runtime searxng / GET … / HTTP 200 sha256=… / CAP-abc / json:results[0] / OBS-def / EVT-ghi / topic observation / partition 3 / offset 812 / consumer interpretation-1 / processing processed / derived ref`.

#### M. Downstream Processing (§85, §86, §173, §174, §175)

- **FR-133** (§85): A real consumer MUST exist on the path `consume event → resolve observation → load raw_ref → resolve locator → validate observation payload → write processing result` (for example `observation.processed` or a durable processing journal). "The observation reached Kafka" is not sufficient.
- **FR-134** (§85): Successful processing MUST leave machine-readable evidence: `processing_run_id`, `observation_id`, `consumer`, `consumer_version`, `processed_at`, `status`, `derived_ref`. `status = processed` is permissible but a link to a concrete result is mandatory.
- **FR-135** (§173): The consumer MUST be able to `load observation → resolve capture → load raw → resolve locator → parse record` and MUST NOT require donor-specific HTTP calls.
- **FR-136** (§174): The observation consumer MUST NOT refetch from the internet; it uses the captured raw artifact.
- **FR-137** (§175): When the frontier decides to `refetch URL`, that is a **new acquisition task and a new Capture**, not a mutation of an existing Observation.

#### N. Content Routing, Protocol Parsing and Exit Semantics (§87, §88, §89, §90, §62, §91, §92)

- **FR-138** (§87): The existing `ContentRouter` MUST be used, with no separate content-classification mechanism per donor. `application/json`, `text/json`, `application/x-ndjson` and `text/plain` MUST have deterministic routing, and file extension alone MUST NOT be trusted.
- **FR-139** (§88): The system MUST distinguish a JSON document, a JSON array, NDJSON/JSONL and mixed stdout. For Airbyte STDIO, `one JSON object = one line`; the official protocol requires line-delimited messages in STDIO mode.
- **FR-140** (§89): `stdout = data channel` and `stderr = logs/errors`, following the Airbyte protocol's own statement that STDERR carries log messages. stdout and stderr MUST NOT be mixed in one parser.
- **FR-141** (§90): `exit_code == 0` MUST NOT be treated as a guarantee of data — success requires `exit_code == 0 AND protocol valid AND expected stream/data observed`. Conversely `exit_code != 0` MUST NOT mean already-received observations are discarded; partial data MUST be preserved.
- **FR-142** (§62): Unknown, unmapped, unexpected or vendor-specific fields MUST NOT be deleted. The raw artifact, structured metadata, parser version and producer version are preserved, and an unknown mapping means `record → retained → not mapped`, never `drop`.
- **FR-143** (§91): On a partial run — 100 records with a crash at 101 — the system MUST NOT roll back all 100. The partial capture, the partial observations, a failure marker and resume/replay capability are preserved.
- **FR-144** (§92): Retry MUST occur at the task/run level, not as blind subprocess duplication. Before retry the system MUST check idempotency, previous partial observations, connector state and the raw artifact.

#### O. Errors, Lifecycle, Quarantine, Immutability and Isolation (§101–§111)

- **FR-145** (§101): Lifecycle values MUST be `created`, `changed`, `unchanged`, `duplicate` and `failed` where applicable, and `unchanged` MUST NOT be confused with `not acquired`.
- **FR-146** (§102): HTTP 4xx, connector errors and tool timeouts MUST NOT become fabricated empty results. `HTTP 403` is `acquisition outcome: failed / access_denied` with evidence metadata preserved, not `results=[]`.
- **FR-147** (§107): Malformed messages — invalid JSON, invalid `AirbyteMessage`, invalid BBOT event, invalid SpiderFoot record, invalid Maigret result — MUST go to `quarantine` with `reason`, `source`, `runtime`, `raw ref` and `line/message index`.
- **FR-148** (§108): Malformed or unknown output MUST NOT mean delete; the raw artifact is preserved for replay and debug.
- **FR-149** (§109): Observation core fields MUST be immutable after durable persistence. Later updates are limited to `processing status`, `derived metadata` and `review state`, and MUST NOT include `raw_ref`, `tenant_id`, `source_id`, `capture_id` or the original locator.
- **FR-150** (§110): Every `Capture`, `Observation`, `EventEnvelope`, ObjectStore key, task and run MUST carry tenant identity, and cross-tenant raw retrieval via a guessable URI MUST be impossible.
- **FR-151** (§111): `investigation_id` MUST be preserved in all event envelopes. `default-tenant` / `default-investigation` MUST NOT be used on the live production path for a real investigation; fixtures may use defaults only inside isolated tests.
- **FR-152** (§166): Under cross-tenant replay, two test tenants may share a content digest while access and control lineage remain tenant-scoped, and `tenant A event → tenant B observation resolution` MUST NOT occur.

#### P. Security, Network, Target and Resource Governance (§64, §65, §66, §143, §144, §145, §146, §147, §148, §170)

- **FR-153** (§64): The HTTP security boundary MUST include allow/deny network policy, DNS resolution controls, SSRF protection, redirect policy, max bytes, timeout and connection limits. The legacy `acquisition_loop.py` MUST NOT be used; it is recorded as absent from the repository.
- **FR-154** (§65): An acquisition tool MUST NOT be given the Docker socket, host filesystem, host credentials, platform secrets or unbounded outbound network. The path is `Acquisition Service → dedicated runner → isolated container`, and `/var/run/docker.sock` MUST NOT be mounted into an untrusted tool process.
- **FR-155** (§66): Every runtime MUST receive a `resource_class` — at minimum `small` / `medium` / `large` — with `cpu`, `memory`, `runtime`, `max_output`, `max_records` and `concurrency`, and the scheduler MUST account for the acquisition budget. Expanding concurrency as backlog grows is forbidden; backpressure runs `backlog ↑ → acquisition rate ↓`.
- **FR-156** (§143): Tool-specific resource limits MUST be used rather than a single uniform `all tools = 2 GB / 10m` ceiling: Maigret `max_sites`, `max_connections`, `timeout`; Airbyte max records, max output, connector timeout; BBOT scan timeout, max process/resources; SpiderFoot max threads, runtime limit, output limit; SearXNG max pages, request timeout, result count limit.
- **FR-157** (§144): Network policy MUST be explicit per runtime. SearXNG's worker sees only the internal SearXNG endpoint; Airbyte has network access per connector requirements but through controlled egress; Maigret/BBOT/SpiderFoot have an **explicit** outbound policy and MUST NOT be granted unrestricted egress "because the tool is OSINT".
- **FR-158** (§145): Tool runtimes MUST pass the existing policy layer. The task encodes `target`, `target_scope` and contact level, and the acquisition layer MUST NOT silently bypass operator policy.
- **FR-159** (§146): Every runtime MUST declare `connect timeout`, `read timeout`, `overall task timeout` and `shutdown grace period`. After a timeout the sequence is `SIGTERM → grace → SIGKILL` with the result recorded.
- **FR-160** (§147): The worker MUST track child processes — particularly for BBOT and SpiderFoot — and MUST NOT leave orphan processes after a timeout.
- **FR-161** (§148): `max_stdout_bytes` and `max_stderr_bytes` MUST be separate limits. On breach the process is killed with `reason = output_limit_exceeded`, or controlled truncation is applied only where the protocol safely supports it, with raw partial output preserved.
- **FR-162** (§170): The platform MUST exhibit `no unbounded memory`, `no runaway process`, `no Kafka backlog runaway`, `no raw-to-Kafka blob transfer` and `no O(N²) acquisition routing`.
- **FR-163** (§30, §184): Secrets MUST NOT leak into hashed configs: plaintext secrets MUST NOT be hashed into manifests where that would be a credential fingerprint; `secret_ref` is used instead.
- **FR-164** (§182, §183): Each tool run MUST have a deterministic `config_digest` with secrets excluded or replaced by stable secret references, and an `argv_normalized_digest` computed from the normalized command **without secrets**.

#### Q. Observability, Replay Operations and Trace Commands (§70, §72, §73, §74, §75, §130, §131, §132, §133, §134, §135, §136, §154, §163, §164, §186, §189)

- **FR-165** (§130): A single **executable** instruction/command MUST exist for `run integration / dump task / dump capture / dump observation / inspect Kafka / inspect consumer / replay task` — not README prose alone.
- **FR-166** (§131): `replay(task_id)` MUST work without manually rewriting the acquisition config, reproducing `worker_ref`, `runtime_ref`, `source_id`, `input`, `limits`, `tenant` and `investigation` under a **new** `integration_run_id`.
- **FR-167** (§132): `replay_observation(observation_id)` MUST NOT trigger network acquisition; it reads `raw_ref` from the ObjectStore.
- **FR-168** (§133): Parser replay MUST be possible: `raw capture → parser v1` and `raw capture → parser v2` with no change to source acquisition.
- **FR-169** (§63): Every observation MUST be traceable to `collector`, `collector_version`, `parser`, `parser_version`, `runtime_version` and `source_version`. On runtime upgrade, `same raw capture → reparse → different interpretation version` MUST NOT require repeat network acquisition.
- **FR-170** (§95): Tool outputs MUST be provenance-bound (`producer: bbot`, `producer_version: 3.x`, `runtime_ref: bbot.default`, `parser_version: 1.x`). Changing a donor tool yields `new version != old derivation` while the raw evidence remains.
- **FR-171** (§134): Metrics MUST exist per runtime: `tasks started`, `tasks completed`, `tasks failed`, `records emitted`, `observations created`, `duplicates`, `quarantine count`, `bytes fetched`, `bytes stored`, `runtime seconds`, `Kafka publish failures`, `consumer failures`.
- **FR-172** (§135): Metrics MUST be labelled by `source_id`, `worker_ref`, `runtime_ref`, `producer_version` and `tenant_id`, and MUST NOT carry secret or raw user data as labels.
- **FR-173** (§136): `consumer lag` MUST be accessible, and an acceptance run is not green until the event has physically been processed by a consumer.
- **FR-174** (§154): Structured logs MUST carry `integration_run_id`, `task_id`, `source_id`, `worker_ref`, `runtime_ref`, `capture_id`, `observation_id` and `event_id`, and every log line MUST belong to a concrete runtime execution.
- **FR-175** (§163): After the first green smoke, scale-up from `1 task → N tasks` MUST be performed within the resource budget, verifying `concurrency`, `backpressure`, `ordering`, `dedup`, `Kafka lag`, `ObjectStore pressure`, `DB pressure` and `tool isolation`.
- **FR-176** (§164): The first successful run MUST use a source that genuinely emits several records, disproving `first record only`, `last record only` and `one observation per process`. For Airbyte `record_count > 1`; for SearXNG `results_count > 1` where the engine returns them.
- **FR-177** (§186): Before live acceptance the run MUST record `git rev-parse HEAD` and `git status --porcelain`; "the working tree happened to be dirty" is not an acceptable unknown state.
- **FR-178** (§189): After a clean live run, `stop downstream → replay Kafka events / observations` MUST reproduce the same durable interpretation with no new network acquisition.
- **FR-179** (§190, §191, §192, §193): The failure drills MUST be executable: producer-active/consumer-stopped loses no observations once the consumer resumes; a consumer crash mid-processing replays the event without semantically duplicating the observation; a deliberately doubled `EventEnvelope` yields one semantic processing result with idempotency evidence; and global Kafka ordering MUST NOT be assumed, with ordering guarantees scoped to key/partition and record identity independent of incidental global ordering.
- **FR-180** (§126): The integration environment MUST run through the existing `apps/deploy/docker-compose.yml` and its existing profiles. Creating a second parallel infrastructure stack for this feature is forbidden.
- **FR-181** (§127): The services required are `Postgres`, `Redis`, `ObjectStore`, `Redpanda`, schema/event infrastructure, an acquisition worker, the `ObservationGate` and a downstream consumer, plus `SearXNG`, `Airbyte runtime`, `Maigret runtime`, `BBOT runtime` and `SpiderFoot runtime` for the corresponding scenarios.
- **FR-182** (§128): Before a live run, `docker compose ps` and machine-readable health checks MUST pass. E2E MUST NOT start before `Redpanda healthy` / `Postgres healthy` / `ObjectStore healthy`, where health means **capability to process, not merely container status**.
- **FR-183** (§129): A Redpanda precheck MUST confirm `topic exists`, `producer can connect`, `consumer can subscribe` and `schema can serialize/deserialize`, using an ephemeral integration consumer group for smoke tests.

#### R. Test Classes, Live Scenarios and the Test Matrix (§77, §78, §79, §80–§84, §152)

- **FR-184** (§77): Offline tests MUST be deterministic, fast, fixture-based and internet-free, covering parser and protocol correctness. Live tests MUST use a real process, real container/tool, real Redpanda, real ObjectStore, real Kafka event and a real consumer, covering integration acceptance. **Both are mandatory.**
- **FR-185** (§78): Five live scenarios MUST be created — `live_searxng_smoke`, `live_airbyte_smoke`, `live_maigret_smoke`, `live_bbot_smoke`, `live_spiderfoot_smoke` — each launched through the standard `InvestigationWorkflow`.
- **FR-186** (§79): Each scenario MUST declare `scenario id`, `target/query`, `source id`, `worker ref`, `runtime ref`, `expected minimum observations`, `expected topic`, `expected consumer`, `assertions` and `cleanup`.
- **FR-187** (§80): `live_searxng_smoke` uses `investigation = int-searxng-smoke`, query `"SearXNG GitHub"`, source `searxng.search`, worker `http`, runtime `searxng`, asserting HTTP reachable, JSON response, ≥1 result, Capture, raw_ref, Observation, `observation.created`, consumer processed and discovery/result downstream.
- **FR-188** (§81): `live_airbyte_smoke` uses a connector guaranteed to emit data, asserting spec = success, check = success, discover = success, read started, RECORD observed, STATE observed **or** an explicit connector limitation recorded, Capture, Observation, Redpanda event and consumer success.
- **FR-189** (§82): `live_maigret_smoke` uses a controlled test username, asserting tool start, sites checked, ≥1 result record, Capture, Observation, Redpanda and consumer. Site-check accuracy is not an acceptance condition.
- **FR-190** (§83): `live_bbot_smoke` uses a safe bounded test target, asserting scan start, event stream existence, ≥1 event, Capture, Observation, Redpanda and consumer, under a hard timeout.
- **FR-191** (§84): `live_spiderfoot_smoke` is a bounded passive/investigative scenario asserting process start, JSON emitted, event parsed, Observation created, Redpanda event and downstream processing.
- **FR-192** (§152): For each of the five runtimes the test matrix MUST be complete across Unit, Fixture, Process, Redpanda, Live and Replay.

#### S. Reconciliation Identities (§137–§142)

- **FR-193** (§137): A zero-data-loss check MUST compare, for a bounded smoke with known expected `N`: `source records >= N`, `observations durable >= N`, `Redpanda events >= N` and `downstream processed >= N`. For nondeterministic live tools the requirement is `at least one` plus reconciliation with an explanation.
- **FR-194** (§138): Airbyte reconciliation MUST separately count `TOTAL messages`, `RECORD`, `STATE` and `LOG/TRACE`, with `record_count > 0` and `observation_count == record_count` when no RECORD was filtered by a policy layer, and STATE excluded from the observation count.
- **FR-195** (§139): SearXNG reconciliation MUST report `pages fetched`, `results reported by parser` and `observations persisted`, with `pages >= 1`, `results >= 1` and `observations == retained result count`; duplicate policy is explained separately.
- **FR-196** (§140): Maigret reconciliation MUST report `sites scheduled`, `sites completed`, `results yielded` and `observations persisted`.
- **FR-197** (§141): BBOT reconciliation MUST report `events seen`, `events parsed`, `events persisted`, `events published` and `events processed`.
- **FR-198** (§142): SpiderFoot reconciliation MUST report `events exported`, `events parsed`, `events observed` and `events processed`.

#### T. Donor Versioning, Licensing and Reproducible Reporting (§150, §151, §169, §185)

- **FR-199** (§150, §151): Every integration runtime MUST have a donor version manifest recording `tool`, `source_repository`, `license`, `version`, `image`, `digest`, `integration_role`, `adapted_components`, `non_transferred_semantics` and `known_patches`, and the run manifest MUST record `upstream repo`, `commit`, `license`, `copied code`, `adapted code` and the dynamic/external execution boundary. License compliance MUST be preserved, especially for copyleft source projects, and no legal "magic clean room" may be claimed.
- **FR-200** (§169): When a tool output parser changes, unknown data MUST be retained and the raw artifact remains the source of truth for replay.
- **FR-201** (§185): The acceptance report MUST contain `git commit`, `image digests`, `source version`, `runtime version`, `schema version` and `test scenario version`.

#### U. Debugging Procedure and Failure Reporting (§72, §73, §74, §75, §159, §162, §197)

- **FR-202** (§72): On an unsuccessful integration the work MUST NOT stop at "adapter written" / "the test fails because of infrastructure" / "the connector does not answer yet" / "Redpanda did not accept something". The loop `RUN → OBSERVE → CLASSIFY FAILURE → PATCH → RESTART AFFECTED COMPONENT → REPLAY TASK → VERIFY → RUN AGAIN` runs until green acceptance or until a clearly recorded infrastructure blocker that genuinely cannot be removed from this execution context.
- **FR-203** (§73): Every failure MUST be classified as `build`, `configuration`, `dependency`, `container`, `process`, `network`, `DNS`, `TLS`, `authentication`, `protocol`, `parsing`, `identity`, `storage`, `Kafka`, `schema`, `consumer`, `downstream`, `performance`, `security policy` or `determinism`. A generic "integration failed" without classification is forbidden.
- **FR-204** (§74): Each failure MUST preserve `task_id`, `integration_run_id`, `worker_ref`, `runtime_ref`, tool version, image digest, argv sans secrets, exit code, bounded stdout/stderr artifact, source response metadata, event ids, Kafka topic/partition/offset and consumer error. Secrets MUST be redacted before storage.
- **FR-205** (§75): Debugging MUST be Redpanda-first. If a worker claims `observation created`, verify in Redpanda that `topic == observation`, `event_id exists` and `observation_id exists`. Event present but downstream not processed → inspect consumer group / offset / lag / poison. Event absent → inspect producer / topic routing / delivery callback / serialization. Raw present but event absent → inspect `ObservationGate` / producer seam. Raw absent → inspect artifact sink / ObjectStore. Capture present but observation absent → inspect record expander. Observation present but no downstream result → inspect consumer / parser / downstream stage.
- **FR-206** (§159): The final report MUST be machine-readable. Success: `{"status": "PASS", "sources": {"searxng": {"tasks":1,"captures":1,"observations":12,"published":12,"processed":12}, "airbyte": {...}}}`. Failure: `{"status":"FAIL","failed_stage":"observation_gate.publish","task_id":"...","capture_id":"...","observation_id":"...","reason":"..."}`.
- **FR-207** (§162): For each runtime the iterative debugging procedure MUST be followed literally: `PHASE A Build → B Start infrastructure → C Healthcheck → D Start one task → E Inspect process → F Inspect raw output → G Inspect Capture → H Inspect Observation → I Inspect Redpanda event → J Inspect consumer → K Inspect persisted downstream result → L Replay → M Verify deterministic identity → N Increase workload → O Final acceptance`.
- **FR-208** (§197): The implementing agent MUST `inspect current implementation → patch smallest coherent seam → run focused tests → run process-level test → run Redpanda test → inspect real event → fix discovered failure → repeat`, and MUST NOT return to paper work after a first compile-green.

#### V. Acceptance Evidence, Release Gate and Final Artifacts (§158, §187, §188, §194, §200, §201)

- **FR-209** (§158): A single release acceptance entrypoint MUST run `prepare / healthcheck / run 5 sources / reconcile / inspect Kafka / inspect downstream / emit final report` — the command is `uv run python -m bench.run --scenario acquisition-integration` or the existing equivalent.
- **FR-210** (§187): When a DB migration is required, green on an already-mutated local database is NOT accepted. The sequence is `migration up → smoke → migration replay/clean environment`.
- **FR-211** (§188): The final smoke MUST run on a clean stack: fresh DB, fresh Redis, fresh ObjectStore namespace, fresh Redpanda topics/consumer group.
- **FR-212** (§194): The final acceptance matrix MUST show, per runtime, `Source reached`, `Raw captured`, `Observation`, `Redpanda`, `Consumer` and `Replay` all `required`. Each of SearXNG, Airbyte, Maigret, BBOT and SpiderFoot is **BLOCKED until all green**; no row is satisfied by another row.
- **FR-213** (§200): An operator MUST be able to take a clean stack and execute `start stack → create investigation → launch SearXNG task → observe records in Redpanda → observe downstream processing → launch Airbyte task → observe RECORD stream → observe Redpanda → observe processing → launch Maigret task → observe site results → observe Redpanda → observe processing → launch BBOT task → observe event stream → observe Redpanda → observe processing → launch SpiderFoot task → observe JSON/event stream → observe Redpanda → observe processing`, then `kill consumer → resume → all pending observations processed`, then `replay raw observation → same observation identity → same deterministic parser result`, then `clean stack → repeat` with all five runtime paths green again. This repeatable sequence — not the number of classes, not the number of YAML definitions, not passing unit tests, not the presence of containers — is the final completion criterion.
- **FR-214** (§201): A mandatory final artifact tree MUST exist at `artifacts/acquisition-integration/` containing `run-manifest.json`, `searxng.json`, `airbyte.json`, `maigret.json`, `bbot.json`, `spiderfoot.json`, `redpanda-trace.json` and `replay-report.json`.
- **FR-215** (§201): `run-manifest.json` MUST contain git sha, deployment identity, source versions, runtime versions, image digests, schema versions, integration run ids, task ids, capture ids, observation ids, event ids, Kafka topics, partitions, offsets, consumer groups, processing counts and replay counts.

### Key Entities

- **AcquisitionArtifact**: The unit emitted by a runtime for one addressable piece of acquired material. Attributes: `task_id`, `source_id`, `worker_ref`, `target_uri`, `locator`, `body`, `content_type`, `fetched_at`, `transport`, `producer`, `producer_version`, `metadata`. Produced by a runtime, accepted by the artifact sink, never by the platform itself.
- **Capture**: One fetch/ingest event — what was physically obtained or produced. Attributes: `capture_id`, `tenant_id`, `source_id`, `source_family`, `target_uri`, `locator`, `content_digest`, `content_length`, `media_type`, `fetched_at`, `time_basis`, `transport`, `ingest_batch_id`, `ingest_attempt`, `recorded_by`. Content-addressed and immutable; first-class durable; the single capture model.
- **ObservationRecord**: An addressable record extracted from a capture. Attributes: `observation_id`, `capture_id`, `record_locator`, `record_digest`, `record_metadata`, `tenant_id`, `investigation_id`, `source_id`, `task_id`, `lifecycle`, `status`, `raw_ref`. Immutable core fields after durable persistence; created by `ingest_record` without re-storing the blob.
- **RecordLocator**: A deterministic, reproducible provenance address within a capture. Attributes: `scheme` (e.g. `json`, `airbyte`, `bbot`, `spiderfoot`, `maigret`), `expression` (index, sequence, message index or canonical site name). Explicitly a provenance address, not a semantic identity.
- **EventEnvelope**: The canonical protobuf event on the backbone. Attributes: `event_id`, `event_type`, `event_version`, `producer`, `producer_version`, `produced_at`, `tenant_id`, `investigation_id`, `source_id`, `work_id`, `region_id`, `observation_id`, `entity_id`, `correlation_id`, `causation_id`, `payload`. Payload is refs-only.
- **AcquisitionTask**: One unit of scheduled acquisition work. Attributes: `task_id`, `tenant_id`, `investigation_id`, `source_id`, `worker_ref`, `runtime_ref`, `execution_class`, `required_capabilities`, `input` (query/username/target/connector config), `limits`, `correlation_id`, `target`, `target_scope`, `contact_level`.
- **SourceDefinition**: A validated, registered source. Attributes: `source_id` (content-addressed), `name`, `enabled`, `worker_ref`, `runtime_ref`, `execution_class`, `capabilities`, `input_schema`, `output_schema`, `contact_class`, `parser`/interpreter hint, `resource_class`, `timeout`, `max_output_bytes`, `source_version`, `runtime_version`, `provenance`.
- **ToolDefinition**: The declarative manifest for one external tool under `ExternalToolRuntime`. Attributes: `tool_id`, `runtime`, `image`, `entrypoint`, `argv`, `input_mapping`, `output_mode`, `record_parser`, `timeout`, `max_stdout_bytes`, `max_stderr_bytes`, `max_records`, `network_policy`, `filesystem_policy`, `resource_class`, `version`, `config_digest`, `argv_normalized_digest`, `license`/`upstream` provenance.
- **IntegrationRun**: One E2E run and its forensic trace manifest. Attributes: `integration_run_id`, `tenant_id`, `investigation_id`, `task_id`, `source_id`, `worker_ref`, `runtime_ref`, `runtime_version`, `capture_ids`, `observation_ids`, `event_ids`, `topics`, `consumer_group`, `offsets`, `processing_results`, `git_sha`, `deployment_identity`, `schema_versions`. An operational artifact in its own right.
- **AirbyteRun**: One connector execution's control-plane and stream record. Attributes: `connector_ref`, `image_digest`, `protocol_version`, `runtime_version`, `config_ref`, `credential_ref`/`credential_version`, `catalog_ref`, `state_before_ref`, `state_after_ref`, `spec_status`, `check_status`, `discover_status`, `read_status`, `total_messages`, `record_count`, `state_count`, `log_trace_count`, `failure_code`.
- **ProcessingResult**: The durable downstream outcome for one observation. Attributes: `processing_run_id`, `observation_id`, `capture_id`, `raw_ref`, `record_locator`, `consumer`, `consumer_version`, `processed_at`, `status`, `derived_ref`. A `status = processed` without a concrete `derived_ref` is not a result.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001 (§0, §0.1) — The gate, unsoftened.** The feature is **NOT COMPLETE** if any of: adapters are written; source definitions are registered; unit tests pass; fixture tests pass; the worker can start; the tool container is invoked correctly; a message appeared in stdout; a message was sent to Kafka; `observation.created` exists in code; Redpanda contains messages; a downstream consumer exists but processed nothing. It is complete only when the full runtime path `Investigation → AcquisitionTask → Scheduler/Dispatcher → concrete worker_ref + source/runtime definition → real external source launch → real output source → Capture/raw artifact → ObjectStore → Observation/ObservationRecord → canonical EventEnvelope → Redpanda → real downstream consumer → successful processing → identifiable persisted result` is proven, with at least one proven runtime trace per family exposing `source start → task_id → worker_ref → capture_id → raw_ref → observation_id → event_id → topic → partition/offset → consumer group → downstream processing result`, all identifiers available for forensic inspection.
- **SC-002 (§204) — The eight-factor formula.** `REAL SOURCE × REAL RUNTIME × REAL CAPTURE × REAL OBSERVATION × REAL REDPANDA EVENT × REAL CONSUMER × REAL DOWNSTREAM PROCESSING × REAL REPLAY = INTEGRATION COMPLETE`. **If any single factor is zero, `FEATURE = NOT COMPLETE`.** And after the first real error appears, the response is `debug → patch → replay → verify → repeat` — never a revision of the acceptance criteria.
- **SC-003 (§200) — The operator-reproducible sequence.** From a clean stack, an operator runs: start stack → create investigation → SearXNG task → records in Redpanda → downstream processing → Airbyte task → RECORD stream → Redpanda → processing → Maigret task → site results → Redpanda → processing → BBOT task → event stream → Redpanda → processing → SpiderFoot task → JSON/event stream → Redpanda → processing. Then `kill consumer → resume → all pending observations processed`. Then `replay raw observation → same observation identity → same deterministic parser result`. Then `clean stack → repeat`, with all five runtime paths green again. **This repeatable sequence is the final completion criterion** — not class count, not YAML definition count, not passing unit tests, not the presence of containers.
- **SC-004 (§194) — The acceptance matrix.** All six columns (`Source reached`, `Raw captured`, `Observation`, `Redpanda`, `Consumer`, `Replay`) read `required` for all five of SearXNG, Airbyte, Maigret, BBOT and SpiderFoot. Any row reading anything other than all-green is `BLOCKED`, and no row is satisfiable by another.
- **SC-005 (§23) — SearXNG 15-step acceptance.** 15 of 15 steps individually evidenced: task created; task dispatched; searxng runtime invoked; HTTP 200; JSON parsed; ≥1 result emitted; capture stored; raw_ref exists; ≥1 observation persisted; `observation.created` in Redpanda; consumer receives; consumer fetches raw_ref; consumer resolves locator; downstream processing completes; processing record persisted.
- **SC-006 (§38, §39) — Airbyte real acceptance.** `spec` = success, `check` = success, `discover` = success, catalog persisted, `read` started, `N >= 10` real RECORDs (or `all available records >= 1` with the shortfall **recorded**, not masked), RECORD → Capture/Observation, STATE processed in the mandatory order, `observation.created` in Redpanda, consumer receives, consumer resolves the record, processing succeeds. At least one real connector run is always performed; a fixture connector never substitutes for it.
- **SC-007 (§46, §55, §80, §82, §84) — Tool-family minimums.** Maigret: ≥1 observation, ≥1 identifiable site result, raw artifact present, locator resolves, event in Redpanda, downstream parser completes — site-check accuracy excluded. SpiderFoot: ≥1 event, ≥10 desirable where the target genuinely produces more, never required above 1 where source variation makes the count unstable. SearXNG/BBOT: ≥1 result / ≥1 event.
- **SC-008 (§137–§142) — Reconciliation identities hold.** `source records >= N`, `observations durable >= N`, `Redpanda events >= N`, `downstream processed >= N` for a bounded smoke with known `N`; `at least one` plus a written explanation for nondeterministic live tools. Airbyte: `observation_count == record_count` when no RECORD was filtered by policy, STATE excluded. SearXNG: `pages >= 1`, `results >= 1`, `observations == retained result count`. Maigret, BBOT and SpiderFoot report their four- and five-stage counts.
- **SC-009 (§11, §12, §165) — Determinism is measurable.** Replaying the same acquisition artifact yields byte-equal `capture_id`, `observation_id` and `event_id` in 100% of replay attempts. Zero `uuid4`/clock/process/thread/random/memory-address inputs participate in observation or replay-sensitive event identity. Performing `capture → record extraction → observation IDs` twice yields identical capture identity, observation identities and locator identities.
- **SC-010 (§131, §132, §189) — Replay is real and network-free.** `replay_observation(observation_id)` performs zero network acquisitions. After a clean live run with downstream stopped, replaying Kafka events/observations reproduces the same durable interpretation.
- **SC-011 (§190, §191, §192) — The failure drills pass.** Consumer-stopped: 0 observations lost on resume. Consumer crash mid-processing: event replayed, observation not semantically duplicated. Doubled `EventEnvelope`: exactly 1 semantic processing result with idempotency evidence.
- **SC-012 (§37) — Failure observability.** All 14 Airbyte failure states (`image_not_found`, `container_start_failed`, `spec_failed`, `check_failed`, `discover_failed`, `protocol_malformed`, `record_invalid`, `state_invalid`, `connector_runtime_failed`, `timeout`, `resource_limit_exceeded`, `network_denied`, `credential_unavailable`, `credential_rejected`) are distinguishable and individually observable; 0 occurrences of a generic unclassified "integration failed".
- **SC-013 (§158, §159, §201) — The evidence exists and is machine-readable.** One command performs `prepare / healthcheck / run 5 sources / reconcile / inspect Kafka / inspect downstream / emit final report`. `artifacts/acquisition-integration/` contains all 8 required files, and `run-manifest.json` carries git sha, deployment identity, versions, image digests, schema versions, integration run ids, task/capture/observation/event ids, topics, partitions, offsets, consumer groups, processing counts and replay counts. On failure the report names `failed_stage` plus `task_id`, `capture_id`, `observation_id` and `reason`.
- **SC-014 (§30, §74, §163, §164, §184) — Secret containment.** Zero occurrences of `access_token`, `api_key`, `password`, OAuth refresh tokens or private credential material in Redpanda, logs, `EventEnvelope`, `Capture` metadata, Git, argv, normalized argv digests, config digests or manifests.
- **SC-015 (§152, §162) — The matrix and the procedure are complete.** All 30 cells (5 runtimes × 6 test classes) are green. The 15-phase debugging procedure (§162) has been executed literally for each of the five runtimes.
- **SC-016 (§66, §170, §171) — No runaway.** Under scale-up from 1 task to N tasks: no unbounded memory, no runaway process, no Kafka backlog runaway, no raw-to-Kafka blob transfer, no O(N²) acquisition routing. A growing backlog reduces the acquisition rate. Consumer lag is available and an acceptance run is not green until the event has physically been processed.
- **SC-017 (§187, §188) — Clean-stack proof.** The final five-scenario smoke runs against a fresh DB, fresh Redis, fresh ObjectStore namespace and fresh Redpanda topics/consumer group, and is not accepted on an already-mutated local database.
- **SC-018 (§160) — Release blockers.** Zero of the 16 listed release blockers is present at the moment of release, each verified explicitly rather than by absence of complaint.

---

## Assumptions

### Verified facts about the tree (recorded as facts, not problems this spec sets out to solve)

- HEAD is `fe3eb4486fecf89574dfb78b13c3d28a51ffa04b`.
- `apps/shared/events/observation_gate.py:74` contains `observation_id = "OBS-" + uuid.uuid4().hex[:12]` — a confirmed release blocker under §160 and §11.
- `ObservationGate` / `EventEnvelope` are not invoked from `apps/acquisition/sources/connector.py`; the connector builds a plain dict (`sources/connector.py:143-171`), and `worker_acquisition.py:366-377` publishes it as JSON rather than as the canonical protobuf envelope.
- None of SearXNG / Airbyte / Maigret / BBOT / SpiderFoot appear in `apps/deploy/docker-compose.yml`, whose profiles are `core`, `analytics`, `streaming` and `collectors`.
- No `apps/acquisition/runtime` or `apps/acquisition/runtimes` package exists.
- `apps/acquisition/acquisition_loop.py` does not exist; §64's prohibition on it is against an absent file.
- The working tree is **dirty**: 118 untracked paths and 0 modified tracked files were observed at the time this spec was authored. This is recorded as a fact about the state the work starts from, not as a defect to be fixed here. §186 nonetheless requires `git rev-parse HEAD` and `git status --porcelain` to be recorded before live acceptance, and treats "the working tree happened to be dirty" as not an acceptable unknown state — so the plan phase must record this baseline explicitly rather than leave it implicit.
- `bench/run.py` already implements `uv run python -m bench.run --scenario <name>` with `--compose` and `--dry-run`, per-step results and a `PASS`/`FAIL` render; §158's acceptance command targets this existing entrypoint.
- `observation.processed` is absent from `EVENT_CATALOG`, so the §85 processing result requires a newly registered, registry-validated event version under §120, and a backward-compatibility decision under §121.

### Two unanswered architectural questions — not resolved here

1. **Which broker is the canonical backbone: Kafka or Redpanda?** The constitution's Technology Baseline names "Apache Kafka (KRaft)" as the event backbone, and the platform's actual producer/consumer code is `apps/shared/events/kafka.py` against `KAFKA_BOOTSTRAP_SERVERS` (default `localhost:9092`, the Confluent Kafka service in the `core` compose profile). The directive, by contrast, speaks only of Redpanda — §0.1, §67, §70, §75, §127, §136, §159, §190 and §204 all say Redpanda, and §127 lists Redpanda among required services. `apps/deploy/docker-compose.yml` runs both, on different ports (Kafka `9092`, Redpanda `19092`) and in different profiles (`core` vs `streaming`). The directive never says whether the canonical path moves to Redpanda, or whether "Redpanda" is used loosely for "the event backbone". **This needs an ADR** under the constitution's Governance section, because it decides the event backbone, the event schema registry and the deployment topology. The spec above uses the directive's word "Redpanda" for the event path because that is the contract's language, and flags the conflict rather than picking a side.
2. **Where `runtime_ref` resolves, and whether the new runtimes conform to the existing acquisition contract.** The constitution (Principle V) mandates that all acquisition implementations conform to the `AcquisitionWorker` interface (`capabilities() / estimate(task) / acquire(task)`), which exists at `apps/acquisition/worker_acquisition.py:220` and is registered through `adapters.registry.REGISTRY`. The directive introduces `worker_ref` / `runtime_ref` on `SourceDefinition` (§14), explicit runtime resolution ahead of capability matching (§13, §57), three runtime classes (§1) and `AirbyteRuntime` with its own `spec/check/discover/read` surface (§25) — none of which the existing `AcquisitionWorker` protocol expresses, and no `runtime` package exists to host them. The directive therefore requires an explicit-runtime resolution path while the constitution requires contract-conformant plugability behind a registry, and does not say whether the runtime registry is the existing `adapters.registry`, a new one, or an extension of the former. **This also needs an ADR**, because it decides scheduling and the acquisition contract surface. The spec above states the required behaviour (§13, §14, §52, §54, §55) without prescribing the registry layout.

### Genuinely undetermined by the directive

- **Runtime image and version selection.** §31 requires pinning and digesting, and §150 requires a manifest with `image` and `digest`, but the directive names no specific image tag or digest for SearXNG, Airbyte, BBOT or SpiderFoot, and only gives `airbyte/source-github:2.7.1` as a format example.
- **Credential availability for a live Airbyte connector.** §39 anticipates that a real connector may require external credentials and mandates a fixture connector as protocol-validation harness, while still requiring one real connector run afterwards. Whether the required credentials are available in this execution context is not stated and is not assumed here.
- **Live infrastructure availability.** Docker Desktop was down when last checked, so the availability of the compose stack, Redpanda/Kafka, ObjectStore, Postgres and the four tool runtimes is **unknown**, not working and not broken. This affects only when §194/§200 can be executed, not what they require.
- **The Airbyte connector chosen for §38/§39.** The directive requires one that "physically yields" at least 10 records and says a shortfall must be recorded rather than masked, but does not name the connector or the source.
- **`InvestigationWorkflow` as a named entrypoint.** §56 requires a single production entrypoint of that name. No symbol by that name exists in the tree today, and the directive does not say whether it is a new component, an existing workflow under a different name, or a wrapper over the current `Investigation` lifecycle.
- **Language of record.** `input.md` is Russian; this spec is English, following the existing spec corpus, with the three gate blocks (§0, §0.1, §204) quoted verbatim in Russian because they are the definition of done and a translation is a rendering, not the text. Any dispute about the gate resolves to `input.md`.
