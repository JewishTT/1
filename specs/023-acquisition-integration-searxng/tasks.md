# Tasks: Acquisition Integration — Five Runtime Families on One Capture → Observation → EventEnvelope Seam

**Input**: Design documents from `specs/023-acquisition-integration-searxng/`
**Prerequisites**: [input.md](./input.md) (204-section directive — source of truth), [plan.md](./plan.md), [spec.md](./spec.md)

**Tests**: MANDATORY. This directive overrides the template's "tests are optional". §77 makes offline **and** live classes both mandatory; §76/§202/§203 forbid reaching green through `xfail` / `skip` / `mock` / fake broker / fake source output. Every user story carries an offline group **and** a live group.

**Organization**: Phases follow §196's mandated order, not user-story priority. User stories are *labels inside* phases, not the phase order.

---

## ⚠️ ORDERING CONTRACT — the ID is the schedule

`input.md` §196 fixes a **strict, serial** order and says in its own words:
*«Нельзя строить пять runtime integrations на неисправном Capture → ObservationGate → EventEnvelope seam.»*

### ID scheme: `T<W><NN>`

| Part | Meaning |
|---|---|
| `W` | The §196 **wave** digit. `0` = preconditions · `1` = the seam · `2` = foundational runtimes · `3` = per-runtime specifics · `4` = governance · `5` = live scenarios · `6` = replay · `7` = failure journal · `8` = clean-stack acceptance · `9` = final artifacts. |
| `NN` | Monotonic sequence **within** the wave. |

**Four mechanically checkable rules:**

- **R1 — Numeric order is §196 order.** Sorting this file by task ID reproduces the directive's execution order exactly. If sorting your view of this file does not produce the §196 order, you are reading it wrong.
- **R2 — Waves close in order.** No task of wave `N` may be *started* while any task of wave `< N` is open. Phase 1 does not start before Checkpoint 0 is green; Phase 2 does not start before Checkpoint 1 is green; and so on.
- **R3 — Inside Phase 1 the eight steps are individually serial.** Every Phase 1 task carries a second label `§196-1.k`, `k = 1…8`, in the fixed order `ACQ-01 → ACQ-02 → ACQ-03 → ACQ-04 → ACQ-05 → ACQ-06 → ACQ-17 → ACQ-18`. **Checkpoint `G1.k` must be green before `§196-1.(k+1)` starts.** A reader who cannot tell which step a task belongs to is looking at a defective task list.
- **R4 — The only parallelism is `[P]`.** `[P]` is used solely where tasks touch **different files** with **no ordering dependency**. The bar is deliberately conservative: a false `[P]` here means five runtime integrations built on a broken seam, and the tests that would catch it need a live broker (§76).

**Reordering is not a style choice.** Moving any `T2*` above `T1*`, or any `§196-1.k` above `§196-1.(k+1)`, has not reordered work — it has broken a mandate, and you will not notice from the test suite.

**Work-package grep-ability**: every task carries an `[ACQ-nn]` tag matching `input.md` §195, so `rg 'ACQ-19' specs/023-acquisition-integration-searxng/tasks.md` returns exactly the live-scenario group.

---

## P0 defects — read before Phase 1

Two defects are release blockers under §160 and are repaired at the head of the seam:

- **D1 — random `observation_id`.** `apps/shared/events/observation_gate.py:74` reads `observation_id = "OBS-" + uuid.uuid4().hex[:12]`. Adjacent: `:106` reads `event_id=f"evt-{ref.sha256}-{lifecycle}"` — content-derived, but not from the §11 material `event_type | event_version | observation_id | producer | producer_version | lifecycle`; and `apps/shared/events/kafka.py:49` defaults `event_id` to `str(uuid4())` whenever a caller supplies none.
- **D2 — the live path bypasses the gate and the envelope.** `ObservationGate` / `EventEnvelope` are not called from `apps/acquisition/sources/connector.py`, which builds a plain Python dict (`lines 143–171`); `apps/acquisition/worker_acquisition.py:366-377` publishes that dict as `json.dumps(event, sort_keys=True)` — JSON on the wire, not the canonical protobuf envelope.

**Both repairs are `§196-1.3` (ACQ-03) and `§196-1.4` (ACQ-04).**

> **A tension, surfaced rather than hidden.** The brief asked for these to be *literally the first* implementation tasks. §196 places them at positions 3 and 4, after ACQ-01 (the frozen artifact contract) and ACQ-02 (the capture migration) — and §196 is the governing mandate for this feature, with `input.md` the declared source of truth. The two defect packages are therefore the **first tasks that change runtime behaviour** and the **last tasks before any of the five runtimes exists**; ACQ-01/ACQ-02 are inert scaffolding — a frozen dataclass and a schema — with no runtime attached. This deviation is recorded here on purpose rather than silently resolved.

---

## §162-PROC — reusable per-runtime debugging checklist (defined once, referenced everywhere)

§162 requires this to be executed **literally, for each runtime**. It is defined **once** here and referenced by every live task. It is **not** restated five times.

| Phase | Action | Evidence written |
|---|---|---|
| **A** | Build | build log, `git rev-parse HEAD`, resolved image digests |
| **B** | Start infrastructure | `docker compose ps`, profile used |
| **C** | Healthcheck | machine-readable health for Postgres / Redis / ObjectStore / Redpanda / schema registry / acquisition worker / `ObservationGate` / consumer — capability, **not** container status (§128) |
| **D** | Start one task | `integration_run_id, task_id, worker_ref, runtime_ref` |
| **E** | Inspect process | argv (secrets stripped), exit code, bounded stdout/stderr artifact, child pids |
| **F** | Inspect raw output | raw bytes, sha256, byte count, content type |
| **G** | Inspect Capture | `capture_id, raw_ref, content_digest, time_basis, transport` |
| **H** | Inspect Observation | `observation_id, locator, record_digest`, count |
| **I** | Inspect Redpanda event | `topic / partition / offset / event_id / observation_id / key` |
| **J** | Inspect consumer | `consumer group`, lag, poison, redelivery count |
| **K** | Inspect persisted downstream result | `processing_run_id, status, derived_ref` |
| **L** | Replay | `replay_observation` under a refusing transport; 0 network calls |
| **M** | Verify deterministic identity | same `capture_id / observation_id / event_id` across 100 attempts |
| **N** | Increase workload | 1 task → N tasks within the resource class; backpressure, dedup, lag, storage, DB pressure |
| **O** | Final acceptance | the runtime's six §194 columns all `required` |

**Result recording**: each runtime writes its A→O result to `artifacts/acquisition-integration/<runtime>.json`.

**The first real error triggers `debug → patch → replay → verify → repeat` (§204) — never a revision of the acceptance criteria (§161).**

**Redpanda-first order (§75)**, used whenever the procedure stalls: event present but unprocessed → consumer group / offset / lag / poison. Event absent → producer / topic routing / delivery callback / serialization. Raw present, event absent → `ObservationGate` / producer seam. Raw absent → artifact sink / ObjectStore. Capture present, observation absent → record expander. Observation present, no downstream result → consumer / parser / downstream stage. The executable commands are T139, T615, T616.

**If infra is down** at any point: the procedure halts at phase **B**, a `FailureRecord` with `class: container` is written, and the offline phases continue. Nothing is ever marked green on an assumption.

---

## Phase 0: Preconditions (Wave 0) — `T001`…`T009`

**Purpose**: record the state the work starts from, settle the two open architectural questions, declare the dependencies the seam repair needs, and establish whether live infrastructure exists at all. Not a work package; blocks everything.

**⚠️ R2**: nothing in Wave 1+ starts until Checkpoint 0 is green.

- [ ] **T001** [US9] `§186` Record the pre-work git state — `git rev-parse HEAD` and `git status --porcelain` — into `artifacts/acquisition-integration/run-manifest.json` under `git.sha` / `git.status_porcelain`. Baseline at authoring time: `fe3eb448`, 118 untracked paths, 0 modified tracked. "Dirty" is a **recorded state**, not an unknown. Create the directory here. (FR-177)
- [ ] **T002** [US9] 🔴 **LIVE-INFRA PROBE — engine.** `docker version`; record `docker_desktop_available`. This task exists because Docker Desktop was **down** at last check: availability is *unknown*, not working and not broken. **No task anywhere in this file may assume infra is up; every 🔴 LIVE task below is gated on this probe being green at the moment it runs.** (FR-182, §72)
- [ ] **T003** [US9] 🔴 **LIVE-INFRA PROBE — stack.** `docker compose -f apps/deploy/docker-compose.yml ps` plus machine-readable capability health for Postgres, Redis, ObjectStore, Redpanda and the schema registry. "Container status" is **not** health; health is capability to process (§128). (FR-182)
- [ ] **T004** [US9] `§72` If T002/T003 fail: write a `FailureRecord` with `class: container`, `reason: docker_desktop_unavailable` into the failure journal, and **continue with the offline phases**. Do not fabricate green, do not mark a live test skipped-as-green, do not start Docker-dependent work. (FR-007)
- [ ] **T005** [US9] Write **ADR-0025** (runtime contract: `Runtime` + `AcquisitionWorker`-as-adapter, plan N-1) and get it **signed by the user**. AGENTS.md §1.1: whether Principle V's letter is satisfied is not the agent's call. Blocking. (O-2)
- [ ] **T006** [US9] Write **ADR-0026** (canonical backbone: Kafka KRaft per the constitution's Technology Baseline vs Redpanda per the directive's nine sections) and get it signed. D-01 makes the *acceptance run* work either way; the permanent topology is Governance's. Blocking. (O-1)
- [ ] **T007** [P] [US1] `apps/acquisition/pyproject.toml` — declare `confluent-kafka` explicitly. It reaches `apps/acquisition` **transitively** via `cognitive-shared`, and the code imports it directly; a transitive dep that code imports directly is an undeclared dependency. (D-11)
- [ ] **T008** [P] [US1] `pyproject.toml` `[tool.pytest.ini_options]` — register the `live_integration` marker and enable `--strict-markers`. The existing `live` marker means "needs broker + egress"; §76 names `live_integration` exactly and the release-validation guard keys on that name. (D-11, FR-009)
- [ ] **T009** [US1] Offline **baseline audit** `apps/acquisition/tests/unit/test_release_blockers.py` — assert the *current* §160 state at `fe3eb448`: the blockers `observation_id random`, `event_id random for replay-sensitive events`, `event without canonical EventEnvelope`, `observation without raw lineage` are all **present**. This test is deliberately red-then-green: T113/T114/T120/T126 invert it, and T919 re-asserts absence. (FR-012, SC-018)

### ✅ Checkpoint 0 — GATE `G0`

**Must be green**: T001 recorded `fe3eb448` + the 118/0 baseline · T002/T003 executed and their outcome written down either way · ADR-0025 and ADR-0026 signed · `confluent-kafka` declared · `live_integration` marker registered · T009 green against the known-bad baseline.
**Blocking**: **R2** — no `T1*` task may start until this is green.

---

## Phase 1: The seam (Wave 1) — `T101`…`T148`

**Purpose**: repair `Capture → ObservationGate → EventEnvelope` end to end. §196's first wave, run **strictly in order**; each of the eight steps is green before the next begins.

**⚠️ R3**: `§196-1.1 → §196-1.8` is serial. `§196-1.3` and `§196-1.4` are the two P0 defects.

### `§196-1.1` — ACQ-01 · Canonical artifact seam

- [ ] **T101** [US1] `ACQ-01` Offline test `apps/acquisition/tests/unit/test_artifact_contract.py` — `AcquisitionArtifact` carries **exactly** the 13 §5 fields and is frozen; a 100-artifact generator never holds more than one in memory. Must fail first. (FR-024, FR-025)
- [ ] **T102** [US1] `ACQ-01` Implement the frozen `AcquisitionArtifact` in `apps/acquisition/contracts/`. **Donor: none — this is a platform contract, not a transfer.** Per **D-02** the 13 §5 fields are unchanged; `source_family` and `time_basis` are **declarative fields on the definition**, NOT added here — adding them would make the transport make a semantic decision (AGENTS.md §2) and put identity material into five runtimes' hands, while deriving them from the `runtime_ref` string prefix is guesswork that §97 forbids reaching an id. `Capture.__post_init__` still refuses an undeclared basis, so a definition that omits it fails closed. (FR-024)
- [ ] **T103** [US1] `ACQ-01` Implement the streaming `ArtifactSink.accept()` and `worker.run(task)` as an **async generator** — a streaming runtime must not be required to buffer the entire run before emitting. (FR-025)
- [ ] **T104** [US1] `ACQ-01` Offline test — peak in-memory artifacts `== 1` across a 100-artifact run; the `AsyncGenerator` type is asserted at the call site.

**Checkpoint `G1.1`** — T101–T104 green; `enforce_no_blobs` never trips on the artifact path.

### `§196-1.2` — ACQ-02 · Capture persistence

- [ ] **T105** [US1] `ACQ-02` Offline test `apps/acquisition/tests/integration/test_capture_persistence.py` — migration up; `capture_id` unique; the same bytes twice produce exactly one row; the legacy backfill lands with `time_basis = ABSENT`. Must fail first. (FR-029, FR-030, FR-040, FR-041, FR-048)
- [ ] **T106** [US1] `ACQ-02` Migration `apps/control-plane/db/migrations/versions/021_capture_observation_persistence.py`, `down_revision = "020_universal_relation_extraction"`, forward-only, additive. **Donor: none.** Per **D-09**: new `captures` and `processing_results` tables; `observations` gains `capture_id / locator / record_digest / record_metadata / event_id` and is then set `NOT NULL`. `locator` is a **first-class column, not JSONB** — §122 forbids pushing everything into JSONB when durable query/reconstruction requires structural columns. Legacy backfill uses `time_basis = ABSENT, fetched_at = NULL`: the migration knows when it *wrote* the row, not when anything was *fetched*, and backfilling `fetched_at = created_at` is exactly the `fetch_fetch_time_substituted` conflation `domain/capture.py` already refuses. (FR-048, FR-122)
- [ ] **T107** [US1] `ACQ-02` Implement `CaptureRepository` in `apps/acquisition/observation_gate/` and register `Capture` as a **first-class durable object** on the real acquisition path. **Taken from platform (not donor): `apps/shared/domain/capture.py` (`Capture`, `CaptureTimeBasis`, `digest128`, `canonical_material`, `payload_key`, `to_hop`, `assert_single_tenant`) and `apps/shared/storage/s3.py::ObjectStore.put_raw_dedup` — reused unchanged.** A second competing capture model is forbidden. (FR-029, FR-030)
- [ ] **T108** [US1] `ACQ-02` `apps/control-plane/db/schema.py` — `Capture` / `ObservationRecord` / `ProcessingResult` columns matching T106. **Donor: none; platform schema.**
- [ ] **T109** [US1] `ACQ-02` Offline test — `UNIQUE (capture_id)`, `UNIQUE (observation_id)`, `UNIQUE (capture_id, locator, record_digest)`; identical bytes → identical `sha256` → one raw object, no overwrite; a tampered row passed through `Capture.from_dict` raises on `__post_init__` verification. (FR-040, FR-041, FR-123)

**Checkpoint `G1.2`** — T105–T109 green; the migration replays cleanly on a fresh DB (the full clean-environment replay proof is T810).

### `§196-1.3` — ACQ-03 · 🔴 P0 defect #1 — deterministic observation identity

- [ ] **T110** [US1] `ACQ-03` Offline test `apps/shared/tests/test_identity.py` — build the same artifact 100 times; assert byte-equal `capture_id` / `observation_id` / `event_id`; assert `OBS-` equals `digest128(identity_schema | tenant_id | capture_id | locator | record_digest)`. Must fail first. (FR-034, FR-036, FR-042)
- [ ] **T111** [US1] `ACQ-03` Create `apps/shared/events/canonical_json.py`. **Donor: none — taken from platform, `apps/shared/domain/relation_identity.py::canonical_material` + `_normalise`, whose semantics are pinned explicitly rather than re-invented (D-05).** `sort_keys=True`, `separators=(",",":")`, `ensure_ascii=False`, `allow_nan=False`, applied after `_normalise` (datetime→isoformat, set/frozenset→sorted list, StrEnum→value, unknown→`str`). `ensure_ascii=True` is the rejected default because it makes the digest a function of the *transport encoding* rather than the text, so `"é"` and `"é"` would be two records instead of one; `allow_nan=False` because `NaN`/`Infinity` are not facts and serialise to a token another language cannot parse. (FR-031, FR-039)
- [ ] **T112** [US1] `ACQ-03` Create `apps/shared/events/observation_identity.py`. **Donor: none — `apps/shared/domain/relation_identity.py::digest128` reused unchanged.** `IDENTITY_SCHEMA = "obs/v1"` (versioned: an upgrade opens a new id space and never reinterprets an old one); `observation_id = "OBS-" + digest128(canonical_material([IDENTITY_SCHEMA, tenant_id, capture_id, locator.as_string(), record_digest]))`; `deterministic_event_id = "EVT-" + digest128(canonical_material([event_type, event_version, subject_id, producer, producer_version, lifecycle]))` with `subject_id = observation_id` on `observation.*` events and `= task_id` on `acquisition.request` / `assigned` (§160 forbids random for replay-sensitive events). (FR-033, FR-035)
- [ ] **T113** [US1] `ACQ-03` **Repair in place** `apps/shared/events/observation_gate.py:74` — replace `"OBS-" + uuid.uuid4().hex[:12]` with `observation_identity.observation_id(...)`. Per **D-03** the gate is repaired, **not** extended alongside: a parallel `DeterministicObservationGate` leaves the random id reachable from `ingest()`, so the §160 blocker is not cleared. (FR-033, FR-034)
- [ ] **T114** [US1] `ACQ-03` **Repair in place** `apps/shared/events/observation_gate.py:106` — replace `f"evt-{ref.sha256}-{lifecycle}"` with `deterministic_event_id(...)` over the §11 material. (FR-035)
- [ ] **T115** [US1] `ACQ-03` Edit `apps/shared/events/kafka.py:49` `build_envelope` — add `require_deterministic_event_id: bool = False`; the gate and the scheduler pass `True`. Per **D-03** the rejected alternative is making `event_id` a required positional, which would touch 22 call sites across 8 apps — most outside §196's scope — for zero gate benefit; the guard keyword clears the same §160 blocker with one signature addition. (FR-035)
- [ ] **T116** [US1] `ACQ-03` Offline test — **AST scan** of the id path asserts `uuid.uuid4`, `datetime.now`, `os.getpid`, `threading.get_ident`, `random` and `id()` appear **nowhere** in `observation_identity.py`, `canonical_json.py` or the gate's id construction. (FR-033, SC-009)
- [ ] **T117** [US1] `ACQ-03` Offline test — §165: performing `capture → record extraction → observation IDs` twice yields the same capture identity, the same observation identities and the same locator identities. (FR-042)

**Checkpoint `G1.3` — 🔴 P0** — T110–T117 green. §160 blockers `observation_id random` and `event_id random for replay-sensitive events` are **provably** absent. T009's baseline test is now red and must be inverted at T919.

### `§196-1.4` — ACQ-04 · 🔴 P0 defect #2 — the `EventEnvelope` bridge

- [ ] **T118** [US1] `ACQ-04` Offline test `apps/acquisition/tests/integration/test_envelope_bridge.py` — broker bytes parse as `EventEnvelope`; a plain dict cannot be serialised onto the wire; `enforce_no_blobs(body, max_inline=1024)` never trips. Must fail first. (FR-122, FR-123)
- [ ] **T119** [US1] `ACQ-04` Edit `apps/acquisition/sources/connector.py:143-171` — stop building the plain Python dict; route through `ObservationGate.ingest_capture` / `ingest_record` and yield refs. (FR-029, FR-122)
- [ ] **T120** [US1] `ACQ-04` Edit `apps/acquisition/worker_acquisition.py:366-377` — `observation_publisher` publishes `envelope.SerializeToString()`, not `json.dumps(event, sort_keys=True)`. (FR-122, FR-123)
- [ ] **T121** [US1] `ACQ-04` Offline test — **a dict cannot reach the broker**: the publish call site's argument type is a serialised `EventEnvelope`; raw bytes are never in the payload; the payload is `{capture_id, observation_id, raw_ref, locator, tenant_id, investigation_id, source_id, task_id}` and is ≤ 1 KiB. (FR-027, FR-028, FR-123)
- [ ] **T122** [US1] `ACQ-04` Offline test — the envelope carries the full §68 routing field set `event_id, event_type, event_version, producer, producer_version, produced_at, tenant_id, investigation_id, source_id, work_id, region_id, observation_id`, plus `correlation_id` / `causation_id` (§117) threaded unchanged `scheduler → worker → observation gate → Kafka → downstream`. (FR-122, FR-127, FR-130)

**Checkpoint `G1.4` — 🔴 P0** — T118–T122 green. §160 blocker `event without canonical EventEnvelope` provably absent; `apps/acquisition/sources/connector.py` no longer contains a dict-producing publish path.

### `§196-1.5` — ACQ-05 · Record observation seam

- [ ] **T123** [US1] `ACQ-05` Offline test `apps/shared/tests/test_record_locator.py` — five schemes round-trip; a cross-scheme string is **refused by name**; `resolve()` on a resolved body equals the original bytes; `resolve()` with a refusing HTTP transport installed makes **zero** calls. Must fail first. (FR-032, FR-045)
- [ ] **T124** [US1] `ACQ-05` Create `apps/shared/events/record_locator.py`. **Donor: none — platform.** Per **D-04** one grammar, one parser, one resolver, five schemes: `json:results[N]`, `airbyte:message:N` | `airbyte:stream=<ns>/<stream>:record:N`, `bbot:event:N`, `spiderfoot:event:N`, `maigret:site:<canonical>`, plus `blob` (empty body, the capture-level parent record). Per-family free-form locator strings with per-family resolvers are the rejected alternative: five parsers is five chances to drift, and §96 requires determinism over the locator. `CanonicalSite := NFKC → casefold → [^a-z0-9._-]→"-" → collapse runs → strip → truncate 64`; empty ⇒ `LocatorError("site_name_empty")`. Three functions only: `make_locator`, `parse_locator`, `RecordLocator.resolve`. (FR-032)
- [ ] **T125** [US1] `ACQ-05` Add `ObservationGate.ingest_capture(body, metadata, source, task, investigation, tenant)` and `ObservationGate.ingest_record(capture_id, record_locator, record_digest, record_metadata)` in `apps/shared/events/observation_gate.py`. `ingest_capture` creates the `Capture`, the `raw_ref` and a parent Observation; `ingest_record` **does not re-store the blob** and creates an addressable `ObservationRecord`. **Taken from platform: the existing `apps/acquisition/observation_gate/` module, extended in place, and `apps/acquisition/observation_gate/replay.py::FileReplayJournal`.** (FR-043, FR-044, FR-045)
- [ ] **T126** [US1] `ACQ-05` Offline test — resolve an individual record inside a stored artifact by its locator and obtain the **exact** record bytes with **no network acquisition**. (FR-045, FR-135)
- [ ] **T127** [US1] `ACQ-05` `record_digest = SHA256(canonical_json(record).encode("utf-8"))` per **D-05**; Airbyte observation identity is built on `capture_id | record_locator | record_digest`, **not** record content alone, because the same JSON in two streams represents two different observed occurrences; every RECORD is stored with `namespace, stream, data, emitted_at, sequence, message_index`; records from several streams may interleave and **no `groupby(stream)` with an assumption of stream-serialized input is used**. (FR-046, FR-047)

**Checkpoint `G1.5`** — T123–T127 green. §160 blocker `observation without raw lineage` provably absent: every `observation_id` resolves `raw_ref → capture_id → exact bytes`.

### `§196-1.6` — ACQ-06 · Worker routing — `worker_ref`, `runtime_ref`

- [ ] **T128** [US2] `ACQ-06` Offline test `apps/acquisition/tests/unit/test_routing.py` — two sources sharing capability `http` but naming different `runtime_ref`s land on two workers; a `BBOT`-shaped task with `runtime_ref` unset and `capabilities={http}` yields an explicit `CapabilityGap` and **never** `HttpWorker`; an Airbyte task never lands in the HTTP worker. Must fail first. (FR-049, FR-051)
- [ ] **T129** [US2] `ACQ-06` Edit `apps/acquisition/sources/catalogue.py` `SourceDefinition` — add `source_id, name, enabled, worker_ref, runtime_ref, execution_class, capabilities, input_schema, output_schema, contact_class, parser_hint, resource_class, timeout, max_output_bytes, source_version, runtime_version, provenance`. **Donor: the estorides `donors/estorides/estorides_core/source_loader.py` was already adapted into this module, with six upstream schema defects corrected — its own loader is deliberately NOT re-imported, because reusing it would regress those fixes.** `catalogue.py` remains the registry/catalogue layer; a donor YAML catalogue may be a *data source* but must never determine `Entity / Relation / Graph edge / Claim / Admission` directly. (FR-052, FR-053, FR-023)
- [ ] **T130** [US2] `ACQ-06` Edit `apps/acquisition/adapters/registry.py` `SourceRegistration` — add `worker_ref: str = ""` and `runtime_ref: str = ""`, **both defaulted so the 146 existing catalogue registrations are untouched**, and add `REGISTRY.resolve_explicit(task)` which resolves by `runtime_ref` and then **validates** capabilities. Per **D-08**: one registry, one protocol shape. A second `RuntimeRegistry` the dispatcher never consults is the rejected alternative — it leaves the scheduler inferring, which is the §13 failure. (FR-049, FR-050)
- [ ] **T131** [US2] `ACQ-06` Edit `apps/acquisition/dispatcher/scheduler.py` — take the explicit branch when `task["runtime_ref"]` is present, the legacy capability branch otherwise. Dispatch order is `AcquisitionTask → resolve worker_ref → resolve runtime_ref → validate capabilities → validate policy → execute`; the **explicit runtime is resolved first** and capability matching serves only as a compatibility check. Inferring a worker from capabilities when the source is already explicitly defined is the forbidden route. (FR-050, FR-055)
- [ ] **T132** [US2] `ACQ-06` Edit `apps/acquisition/dispatcher/plan_driver.py` `ensure_capability()` — register the five runtime surfaces (`searxng`, `airbyte`, `maigret`, `bbot`, `spiderfoot` as their own execution classes), not only the existing `("catalogue-http", execution_class="http", capabilities={"http"})`. At HEAD a BBOT task **would** route to the generic HTTP worker — the exact forbidden outcome §13 names. (FR-051)
- [ ] **T133** [US2] `ACQ-06` Offline test — dispatch order asserted end to end; `enabled=false` creates no task and leaves the runtime id stable; changing `runtime_version` does not silently mutate old observations. (FR-055, FR-057, FR-058)

**Checkpoint `G1.6`** — T128–T133 green. The forbidden route `BBOT task → capability=http → generic HttpWorker` is **unreachable by name**, and the 146 existing catalogue sources still resolve on the legacy path.

### `§196-1.7` — ACQ-17 · Redpanda integration — canonical publish + event inspection

- [ ] **T134** [P] [US2] `ACQ-06` Offline test — `enabled=false` disables scheduling without deleting the definition and the runtime id stays stable; a `runtime_version` change preserves original provenance on old records. (FR-057, FR-058)
- [ ] **T135** [US2] `ACQ-17` Offline test `apps/shared/tests/test_event_registry.py` — `observation.processed` is registry-validated; `observation.created` stays at `2.0` with unchanged semantics; no ad hoc JSON shape. Must fail first. (FR-128, FR-129)
- [ ] **T136** [US2] `ACQ-17` Edit `apps/shared/events/topics.py` — add `"observation.processed": "observation"` to `EVENT_CATALOG`. **Donor: none — taken from platform, `apps/shared/events/topics.py::EVENT_CATALOG` / `topic_for`.** Per **D-10** the rejected alternatives are republishing `observation.created` at `3.0` (breaks the §157 trace example and invalidates any existing consumer for no gain) and skipping the event in favour of a journal only (§156 requires a causation chain, and a chain needs an event). One topic per donor tool is forbidden: `maigret-observations`, `bbot-observations` and `spiderfoot-observations` are **prohibited** — tool identity lives in metadata/provenance. (FR-056, FR-128)
- [ ] **T137** [US2] `ACQ-17` Edit `apps/shared/events/registry.py` — register `observation.processed` at version `1.0`. (FR-128)
- [ ] **T138** [US2] `ACQ-17` Wire the canonical publish from the gate to the broker through `IdempotentProducer` — `topic / partition / offset / event_id / observation_id / task_id / consumer group / consumer lag / processing result` observable, and a diagnostic snapshot saved for **every** acceptance run. **Donor: none — `apps/shared/events/kafka.py::IdempotentProducer / IdempotentConsumer / DedupStore` reused.** (FR-124)
- [ ] **T139** [US2] `ACQ-17` Create `bench/acquisition/__main__.py` with `inspect-kafka`, `inspect-consumer`, `dump-task`, `dump-capture`, `dump-observation`, `replay-observation`, `run` — §130 requires a single **executable** command set, not README prose alone. **Donor: none — taken from platform, `bench/run.py` (`ScenarioResult`, `Step`, the existing `--scenario / --compose / --dry-run` entrypoint).** Every command exits non-zero and prints `{failed_stage, task_id, capture_id, observation_id, reason, failure_class}` — the §159 shape. (FR-165, FR-206)
- [ ] **T140** [US9] `ACQ-17` 🔴 **LIVE** — Redpanda precheck: `topic exists` / `producer can connect` / `consumer can subscribe` / `schema can serialize+deserialize`, using an **ephemeral integration consumer group**. Per **D-01** point the existing `confluent-kafka` client at Redpanda via `KAFKA_BOOTSTRAP_SERVERS=localhost:19092` with the `streaming` profile — Redpanda is wire-compatible and the platform code has no broker-brand branch, so **no Kafka code is modified**. **Run §162-PROC A–C, then I.** If the stack is down, halt at phase B, record `class: container`, and continue — never mark green. (FR-006, FR-182, FR-183)
- [ ] **T141** [US1] `ACQ-17` Offline test — all **15** §23 steps reach step 10 (`observation.created` in Redpanda) for a fixture-backed capture through the real publish path.

**Checkpoint `G1.7`** — T134–T141 green; T140 green against a real broker.

### `§196-1.8` — ACQ-18 · Downstream observation consumer

- [ ] **T142** [US2] `ACQ-18` Offline test `apps/interpretation/tests/unit/test_observation_consumer.py` — `consume event → resolve observation → load raw_ref → resolve locator → validate payload → write processing result`, with a transport that raises on any call; **zero** network calls on the whole path. Must fail first. (FR-133, FR-135, FR-136)
- [ ] **T143** [US2] `ACQ-18` Create `apps/interpretation/observation_consumer/consumer.py` and `__main__.py`. **Donor: none — taken from platform: the existing `apps/interpretation/parsers/payload/` and `apps/interpretation/extractors/payload/` seam, imported directly and unchanged. That seam is exactly what this consumer exists to reach, and today no non-test code calls it.** Per **D-06** the consumer is a new service *inside* `apps/interpretation`, because `parsers/payload/__init__.py` states the parser layer does not import `sources` and the parser layer sits **below** acquisition — putting the consumer in `apps/acquisition` inverts the layer arrow, and a fourth "consumers" app duplicates an app that already owns this seam. It never refetches; it uses the captured raw artifact. (FR-133, FR-135, FR-136)
- [ ] **T144** [US2] `ACQ-18` Create `apps/interpretation/observation_consumer/processing.py` — `ProcessingResult` with `processing_run_id, observation_id, capture_id, raw_ref, record_locator, consumer, consumer_version, processed_at, status, derived_ref`, where `status = processed` **without** a concrete `derived_ref` is **not** a result. Write the structured artifact to the ObjectStore to obtain `derived_ref`. No score, no rank, no priority column exists on the new tables (Invariant 7). (FR-134)
- [ ] **T145** [US2] `ACQ-18` Create `apps/interpretation/observation_consumer/idempotency.py` — `UNIQUE (observation_id, consumer, consumer_version)` is the dedup key; the duplicate's `idempotency_key` is recorded as evidence. Kafka exactly-once is **not** relied upon. (FR-037)
- [ ] **T146** [US2] `ACQ-18` Publish `observation.processed` with `causation_id = input event_id` and `correlation_id` carried through, so that `observation.created(E1) → mention.created(causation_id=E1)`. (FR-127, FR-131)
- [ ] **T147** [US2] `ACQ-18` Offline test — a deliberately doubled `EventEnvelope` yields exactly **one** `processing_results` row and exactly one `observation.processed`. (FR-037)
- [ ] **T148** [US2] `ACQ-18` 🔴 **LIVE** — a real envelope on real Redpanda is received by the real consumer; it loads `raw_ref`, resolves the locator, validates the payload and persists a `processing_results` row with a non-null `derived_ref`, consumer group `interpretation-1`. **Run §162-PROC A–C, then I–K.** T140 must be green first. (FR-133, FR-134)

**Checkpoint `G1.8`** — T142–T148 green; `replay → 0 network calls` holds.

### ✅ Checkpoint 1 — GATE `G1` — the §196 seam gate

**Must be green**: `G1.1` … `G1.8` all green. Specifically, §160's first, second and fifth blockers are **provably** absent — `observation_id` deterministic, `event_id` content-derived, event carries the canonical `EventEnvelope`, every observation resolves to raw lineage. A real `processing_results` row exists with a non-null `derived_ref`.

**Blocking**: **R2** — no `T2*` task, i.e. **no runtime whatsoever**, may start until this is green. This is the gate the §196 warning exists for.

**If it is not green: go back. Do not start SearXNG.**

---

## Phase 2: Foundational runtimes (Wave 2) — `T210`…`T239`

**Purpose**: land the three runtime families onto the **repaired** seam. §196 allows these three **in parallel** — they touch disjoint files and share no dependency.

**⚠️ R4**: the only `[P]` set in this phase is the three branch heads **T210 / T220 / T230**. Nothing else here is parallel; inside a branch everything is serial.

**Donor note applying to all three branches**: `donors/` contains full `maigret/` and `spiderfoot/` trees and **no** BBOT tree, **no** Airbyte tree, **no** SearXNG tree (confirmed by directory scan). SearXNG, Airbyte and BBOT are therefore **image-pinned integrations, not code transfers** — their donor note is version/digest pinning, and a task for them that says "implement" with no image and no pin procedure is a defect.

### Branch S — `ACQ-07` · `SearXNGRuntime` (`T210`…`T219`) · US3

- [ ] **T210** [P] [US3] `ACQ-07` 🔺 **BRANCH HEAD.** `apps/deploy/searxng/` compose service + `settings.yml` with `search.formats: [html, json]`. **No donor tree — image-pinned**: resolve and record the `searxng/searxng` image digest at acceptance (§31/§150) and write it into the `ToolDefinition`/provenance. JSON disabled ⇒ `/search?format=json` returns 403 ⇒ `SEARXNG_JSON_FORMAT_DISABLED`. (D-13, FR-059)
- [ ] **T211** [US3] `ACQ-07` Create `apps/acquisition/runtime/definitions/searxng.search.yaml` — `worker_ref = http`, `runtime_ref = searxng`, `execution_class = api/http`, against a local container addressing `http://searxng:8080/search`. **Donor: the estorides catalogue YAML corpus under `apps/acquisition/sources/estorides/` is the data source, and its lineage is `donors/estorides/estorides_core/source_loader.py`; per D-15 it is *adapted* to the existing loader and never copied literally** — §16 says so explicitly, and the YAML must be checked against the current catalogue loader rather than pasted. The platform MUST NOT call Google/Bing/Brave directly; SearXNG performs the federation. (FR-059, FR-060, FR-062)
- [ ] **T212** [US3] `ACQ-07` Offline test — request material and cache key include `q, language, categories, pageno, time_range, safesearch`; `query A → cache hit → result of query B` is impossible; the key also includes tenant, source and credential context, so `tenant A credential → cached response → tenant B` cannot happen. (FR-070, FR-100)
- [ ] **T213** [US3] `ACQ-07` Create `apps/acquisition/runtime/http.py` `HttpRuntime` — httpx client, `security.ssrf_guard`, `ContentRouter.classify`, `hard_max_pages` + `hard_runtime_budget`. **Donor, adapted: `donors/estorides/estorides_core/async_client.py` — `AsyncClient`, `CircuitBreaker`, `sync_fetch`, SOCKS handling, `_redact_proxy` — and `.../pagination.py` — `PaginationConfig`, `build_page_params`, `count_results`.** **Donor defect repaired on transfer (AGENTS.md §2): `ResponseCache` is REJECTED as-is** — the donor keys on URL only, which is precisely the `query A → cached result of query B` bug the platform already fixed in `catalogue._flatten_params`. Its `count_results` **is** the "inspect the result collection" primitive §19 requires; `extract_cursor` is not used for SearXNG (SearXNG paginates by integer `pageno`) but is kept for the generic `HttpRuntime`. (FR-153, FR-138, FR-070)
- [ ] **T214** [US3] `ACQ-07` Create `apps/acquisition/runtime/searxng.py` `SearXNGRuntime` — `/config` preflight, then `GET /search` with `q, format=json, pageno, language, categories, safesearch, time_range`; `q` mandatory, `pageno` starts at 1. **Per D-12 the SearXNG production pagination lives in `SearXNGRuntime` and `apps/acquisition/sources/executor.py:220-255` is NOT modified** — that executor serves the 146-entry catalogue under a uniform `Pagination` contract, and patching it would silently alter every legacy source's page count. (FR-060, FR-061, FR-063)
- [ ] **T215** [US3] `ACQ-07` `SearXNGRuntime` content-derived pagination: `JSON parse → inspect result collection → continue while results remain → obey hard max_pages`, enforced under **both** `hard_max_pages` and `hard_runtime_budget` so a misbehaving source cannot become an infinite task. `HTTP 200 + body != empty → fetch next page` is **inadmissible**. (FR-063, FR-064)
- [ ] **T216** [US3] `ACQ-07` `SearXNGRuntime` `results[]` expansion — every HTTP response page becomes a **durable capture**; each result becomes its own observation `OBS-001 → results[0]`, `OBS-002 → results[1]`, `OBS-003 → results[2]`, each referencing its `capture_id` and `locator` through T125's `ingest_capture`/`ingest_record`. Pages 1..N are all persisted, never only the last. (FR-065, FR-026)
- [ ] **T217** [US3] `ACQ-07` Offline test `apps/acquisition/tests/fixture/test_searxng_pages.py` — five fixture pages; pagination stops on an empty `results[]` and **not** on body emptiness, under both safeguards. Must fail first. (FR-063, FR-064)
- [ ] **T218** [US3] `ACQ-07` Offline test — result normalisation: `title, url, content, engine, category, publishedDate, thumbnail, template, score` and every other genuinely present field survive; **no field is invented**; an absent field is `null` and is **not** a semantic assertion; unknown top-level fields stay reachable in the raw artifact; an unknown mapping means `record → retained → not mapped`, never `drop`. **Donor, as style reference only — not imported: `donors/estorides/estorides_core/parsers.py` (1293 lines, 55 tuned `parse_*` functions including `parse_wayback_cdx` and `parse_nominatim`)**. Its value is the shape and the totality standard (its own docstring admits totality is honoured for ~5 of 55); its parsers return entity-shaped dicts, which §59/§60 forbid on the acquisition path. (FR-066, FR-142)
- [ ] **T219** [US3] `ACQ-07` 🔴 **LIVE** — a **real** HTTP request to a **real** SearXNG instance returning a **real** JSON response: pages fetched ≥ 1, results ≥ 1, every page captured, observations persisted. **Run §162-PROC A–H** for SearXNG and write `artifacts/acquisition-integration/searxng.json` (A–H portion; I–O complete at T526). §153: `producer.produce(fake_observation)` is **not** acceptance. T002/T003 must be green at run time. (FR-010, FR-068, FR-193)

### Branch A — `ACQ-09` · `AirbyteRuntime` (`T220`…`T229`) · US4

- [ ] **T220** [P] [US4] 🔺 **BRANCH HEAD.** `apps/deploy/docker-compose.yml` `acq-airbyte` service: connector images run one `docker run` per invocation — the connector **is** the image. **No Airbyte tree in `donors/` — image-pinned, not a code transfer.** Per D-13, Airbyte connectors are executed as OCI images and never as a Python dependency. Resolve and record the digest at acceptance; the pin format is §31's, e.g. `airbyte/source-github:2.7.1` + `sha256:…`, and the version is written into acquisition provenance. (D-13, FR-083)
- [ ] **T221** [US4] `ACQ-09` Create `apps/acquisition/runtime/definitions/airbyte.github.yaml` — `runtime_ref = airbyte`, `execution_class = connector/protocol`, connector image + digest, `credential_ref` (**never a value**), `protocol_version`, `runtime_version`. **Donor: no Airbyte donor tree. The YAML *shape* is adapted from `apps/acquisition/sources/catalogue.py::SourceDefinition` per D-15, not copied from the estorides corpus verbatim.** The connector choice is open decision **O-3** and needs the user; the default is `airbyte/source-github:2.7.1` with a `credential_ref` to a Vault path, plus the deterministic fixture connector for the protocol harness. (D-15, FR-083)
- [ ] **T222** [US4] `ACQ-09` Offline test — invocation corresponds exactly to `spec` / `check --config` / `discover --config` / `read --config --catalog --state`; `subprocess.run(..., capture_output=True)` is **not** used on `read`; a streaming stdout reader is required. Must fail first. (FR-076, FR-078)
- [ ] **T223** [US4] `ACQ-09` Create `apps/acquisition/runtime/airbyte.py` — `spec` / `check` / `discover` / `read` over a **process or container boundary**; `read` is an **async iterator** of `AirbyteMessage`; the **STDIO JSON protocol** is used for the first phase even where socket mode is available, for maximum transparency of `subprocess stdout → line parser → AirbyteMessage` and simpler forensic debugging — socket mode is a separate optimisation track and not a blocker. Airbyte MUST NOT be integrated as "ещё один HTTP source" with a random connector URL. (FR-075, FR-076, FR-077)
- [ ] **T224** [US4] `ACQ-09` `AirbyteMessage` model + message classification preserved: `spec` = control-plane metadata, `check` = connectivity/credential diagnostic, `discover` = catalog metadata, `read RECORD` = **acquisition evidence**, `read STATE` = checkpoint/control-plane state, `LOG` = operational telemetry, `TRACE` = connector runtime diagnostics. `STATE`, `LOG` and `TRACE` MUST NOT automatically become observations. `discover() → catalog` is source metadata for a planner, **never** an observation of the world. (FR-079, FR-080, FR-019)
- [ ] **T225** [US4] `ACQ-09` `AirbyteRun` catalog + run metadata stored **separately and immutably**: `connector_ref, image_digest, protocol_version, runtime_version, config_ref, credential_ref, credential_version, catalog_ref, state_before_ref, state_after_ref, spec_status, check_status, discover_status, read_status, total_messages, record_count, state_count, log_trace_count, failure_code`. A secret config MUST NOT be placed in raw evidence; secrets are referenced through the secret manager. (FR-081)
- [ ] **T226** [US4] `ACQ-09` Offline test — secret containment: `access_token, api_key, password`, OAuth refresh tokens and private credential material appear in **no** manifest, `config_digest`, `argv_normalized_digest`, `EventEnvelope`, `Capture` metadata, argv or log. Provenance stores `credential_ref` + `credential_version`, never a credential value; plaintext secrets are not hashed into manifests as a credential fingerprint. (FR-082, FR-163)
- [ ] **T227** [US4] `ACQ-09` Offline test — `exit_code == 0` is **not** a guarantee of data (success requires `exit_code == 0 AND protocol valid AND expected stream/data observed`); `exit_code != 0` does **not** license discarding observations already received — partial data is preserved. `stdout = data channel`, `stderr = logs/errors`, following the Airbyte protocol's own statement that STDERR carries log messages; the two are never mixed in one parser. `no records` ≠ `connector failed`. (FR-139, FR-140, FR-141, FR-091)
- [ ] **T228** [US4] `ACQ-09` Offline test — deterministic `config_digest` (secrets excluded or replaced by stable secret references) and `argv_normalized_digest` computed from the normalized command **without secrets**. (FR-164)
- [ ] **T229** [US4] `ACQ-09` 🔴 **LIVE** — a **real** `docker run airbyte/source-hardcoded-data:<pinned>` executing real `spec`, `check`, `discover`, `read`, with real NDJSON on real stdout from a real container. This is the deterministic **protocol-validation harness** §39 mandates; it does **not** substitute for the real-connector acceptance, which is T515. **Run §162-PROC A–F** for Airbyte. (FR-010, FR-089)

### Branch T — `ACQ-12` · `ExternalToolRuntime` (`T230`…`T239`) · US5 / US6 / US7

- [ ] **T230** [P] [US5] 🔺 **BRANCH HEAD.** `apps/acquisition/tool_runner/` host-run service — `__main__.py`, `executor.py`, `policy.py`. **Donor, adapted: `donors/estorides/estorides_core/tool_runner.py` (~230 lines) — `SHELL_METACHAR_RE`, `_check_injection`, `_check_allowlist`, the `ToolError` taxonomy, `ToolResult` / `ToolErrorResult`.** Per **D-07** the runner shells to the `docker` CLI using the host's Docker context; the engine pipe/socket is **never** bind-mounted into any container — on win32 the engine is a named pipe rather than `/var/run/docker.sock`, so the socket path is host-specific and the CLI abstracts it, meaning nothing is mounted at all. (FR-154)
- [ ] **T231** [US5] `ACQ-12` Offline test — `ToolDefinition` carries all its fields: `tool_id, runtime, image, entrypoint, argv, input_mapping, output_mode, record_parser, timeout, max_stdout_bytes, max_stderr_bytes, max_records, network_policy, filesystem_policy, resource_class, version, config_digest, argv_normalized_digest` plus license/upstream provenance. Must fail first. (FR-097)
- [ ] **T232** [US5] `ACQ-12` Create `apps/acquisition/runtime/external_tool.py` — `ExternalToolRuntime` + `ToolDefinition` + `ToolOutcome`. **Donor: the declarative shape is adapted from `apps/acquisition/sources/catalogue.py::SourceDefinition`** (platform code, already-adapted estorides lineage). Maigret, BBOT and SpiderFoot MUST NOT each receive a separate heavyweight worker stack. Runtime principle: `AcquisitionTask → ToolDefinition → argv/config construction → sandbox/container → stdout/event/artifact stream → parser → AcquisitionArtifact → Observation Gate`; donor-specific internals are **not** carried into the canonical domain. (FR-097, FR-098)
- [ ] **T233** [US5] `ACQ-12` `ToolOutcome` — 8 distinguishable states; collapsing them into a binary `found / not_found` is forbidden. (FR-104)
- [ ] **T234** [US5] `ACQ-12` Create `apps/acquisition/runtime/sandbox.py` — `ContainerExecutor` (production) and `ProcessExecutor` (offline tests only): argv construction with **no** mounts, `--read-only`, `--cap-drop ALL`, `--security-opt no-new-privileges`, `--pids-limit`, `--memory`, `--cpus`, `--network <policy>`, tmpfs scratch, `--rm`. **Donor, adapted: `donors/estorides/estorides_core/ssrf_guard.py` (270 lines) — `check_url`, `assert_safe`, `GuardResult`, the allowlist loader, the v4+v6 blocked-range tables — with the module's own env-var allowlist replaced by `apps/shared/security.py::EgressPolicy` so the policy layer is the single source.** The donor reads env directly, which is a boundary violation rather than a component; `SSRFError` is kept. (FR-154, FR-153)
- [ ] **T235** [US5] `ACQ-12` Offline test — a socket-mount request is **refused by `policy.py` before the process starts**; no bind mount, no `/var/run/docker.sock`, `--read-only`, `--cap-drop ALL`, `--pids-limit`, bounded `--network`; `ProcessExecutor` records `isolation: process` in the run manifest and is admissible **only** for offline protocol tests. (FR-099, FR-154)
- [ ] **T236** [US5] `ACQ-12` Create `apps/acquisition/runtime/limits.py` — `ResourceClass` `small` / `medium` / `large` plus `RuntimeLimits` carrying `cpu, memory, runtime, max_output, max_records, concurrency`, and per-runtime `connect_timeout, read_timeout, overall_timeout, shutdown_grace`. **Donor: none — `apps/shared/security.py::ResourceLimits` reused.** (FR-155)
- [ ] **T237** [US5] `ACQ-12` Offline test — the task encodes `target`, `target_scope` and contact level; the acquisition layer passes the **existing policy layer** and does not silently bypass operator policy. (FR-158)
- [ ] **T238** [US5] `ACQ-12` Offline test — the **isolated external-tool boundary is the first production branch** for all three tools (security, fault isolation, dependency isolation, version pinning, resource limits, replay); direct Python embedding is admissible **only after** the isolated runtime succeeds, and must be recorded as such when used. (FR-099)
- [ ] **T239** [US5] `ACQ-12` 🔴 **LIVE** — a real container launches, a real tool process runs, and the container flags are verified from the engine side after the fact (`docker inspect`): no mount, `--read-only`, `--cap-drop ALL`, bounded network. **Run §162-PROC A–E** for the generic tool runtime. (FR-010, FR-154)

### ✅ Checkpoint 2 — GATE `G2`

**Must be green**: Branch S — `SearXNGRuntime` captures every page and expands `results[]` · Branch A — `AirbyteRuntime` runs `spec/check/discover/read` over a real boundary with an async stdout reader and no `subprocess.run(capture_output=True)` on `read` · Branch T — one generic `ExternalToolRuntime` exists, the container executor is the production branch, and a refused run is refused **before** the process starts.

**Blocking**: **R2** — Phase 3 (per-runtime specifics) may not start until all three branches are green.

---

## Phase 3: Per-runtime specifics (Wave 3) — `T310`…`T366`

**Purpose**: the §196 third wave — the six per-runtime packages.

**⚠️ R2**: all of Wave 2 green first.

### `ACQ-08` · SearXNG JSON validation (`T310`…`T314`) · US3

- [ ] **T310** [US3] `ACQ-08` Offline test — **five distinct** SearXNG outcomes: `HTTP 403 because JSON disabled`, `HTTP 429`, `HTTP 5xx`, `empty result set`, `successful search with zero results`. Must fail first. (FR-071)
- [ ] **T311** [US3] `ACQ-08` Implement `SEARXNG_JSON_FORMAT_DISABLED` as a **named non-runtime-ready state**, distinct from `results=[]` and from 429/5xx; the `/config` preflight proves the instance responds, JSON format is enabled, `/search` is available and at least one engine is enabled. (FR-061)
- [ ] **T312** [US3] `ACQ-08` Offline test — `HTTP 403` is `acquisition outcome: failed / access_denied` with evidence metadata preserved, **never** `results=[]`; HTTP 4xx, connector errors and tool timeouts never become fabricated empty results. (FR-146)
- [ ] **T313** [US3] `ACQ-08` Offline test — a changed SearXNG page produces a **new** capture plus a new observation or lifecycle event and **never** overwrites the old capture; `Capture.payload_key` and `capture_id` remain separate counts; the SearXNG runtime creates **no** canonical frontier state (frontier enqueue is a downstream interpretation/discovery step). (FR-074, FR-018, Invariant 8)
- [ ] **T314** [US3] `ACQ-08` 🔴 **LIVE** — real `/config` probe on the real instance: the instance responds, JSON format is confirmed enabled, `/search` is available, at least one engine is enabled. **Run §162-PROC B–C** for this runtime. (FR-061)

### `ACQ-10` · Airbyte streaming protocol parser (`T320`…`T325`) · US4

- [ ] **T320** [US4] `ACQ-10` Offline test — stateful `buffered line → UTF-8 decode → JSON decode → AirbyteMessage validation → dispatch`; an **unknown or unexpected** message type is preserved as the raw line into a quarantine / diagnostic lane with its `reason, source, runtime, raw ref` and line/message index, and does **not** crash the run. Must fail first. (FR-084, FR-147)
- [ ] **T321** [US4] `ACQ-10` Implement the streaming parser in `apps/acquisition/runtime/airbyte.py`. For Airbyte STDIO, `one JSON object = one line` — the official protocol requires line-delimited messages in STDIO mode. (FR-084, FR-139)
- [ ] **T322** [US4] `ACQ-10` Offline test — records from several streams may **interleave**; `groupby(stream)` with an assumption of stream-serialized input is **not** used; every RECORD is stored with `namespace, stream, data, emitted_at, sequence, message_index`. (FR-046)
- [ ] **T323** [US4] `ACQ-10` Offline test — a malformed line does **not** poison the whole process when the protocol permits continuing; a terminally corrupt connector is `abort`ed, `quarantine`d, and its artifact retained. Malformed or unknown output never means delete — the raw artifact is preserved for replay and debug. **Donor, adapted: `donors/estorides/estorides_core/validation.py` (135 lines)** — the shape of a "validate a parsed record, record what is missing, **do not raise**" pass becomes the §107 quarantine classifier. (FR-093, FR-147, FR-148)
- [ ] **T324** [US4] `ACQ-10` Offline test — naturally flow-controlled reader: reading entire stdout into RAM and an unbounded `asyncio.Queue` are both forbidden; limits exist for `max_buffered_messages, max_buffered_bytes, max_record_bytes, max_run_bytes, max_runtime, max_records/run`; a breach yields `resource_limit_exceeded` with partial run state preserved and replay/retry possible. (FR-086)
- [ ] **T325** [US4] `ACQ-10` 🔴 **LIVE** — a real connector run emitting a real unknown message type; the raw line is observed on disk in the quarantine lane with its line index and the run does not crash. **Run §162-PROC E–F** for Airbyte. (FR-084)

### `ACQ-11` · Airbyte state checkpoint (`T330`…`T334`) · US4

- [ ] **T330** [US4] `ACQ-11` Offline test — the mandatory order `receive record → persist observation → acknowledge durable persistence → process state checkpoint`; a `STATE` is **not** confirmation of a fact; `state_before` / `state_after` are preserved and `state` is **never** an observation. Processing a `STATE` before its preceding records are durable yields `STATE persisted / records lost / next run starts after state` — an irreversible evidence gap. Must fail first. (FR-085, FR-090)
- [ ] **T331** [US4] `ACQ-11` Implement the ordering; on retry `state_before` is the **last durable checkpoint**, never an arbitrary current stdout tail. (FR-090)
- [ ] **T332** [US4] `ACQ-11` Offline test — §37's **14** Airbyte failure states are each individually constructible and observable: `image_not_found, container_start_failed, spec_failed, check_failed, discover_failed, protocol_malformed, record_invalid, state_invalid, connector_runtime_failed, timeout, resource_limit_exceeded, network_denied, credential_unavailable, credential_rejected`. The system also distinguishes `check failed / read failed / no records / catalog empty / malformed protocol / connector crash / auth denied / network denied`. (FR-087, FR-091, SC-012)
- [ ] **T333** [US4] `ACQ-11` Offline test — partial-run recovery: 100 records with a crash at 101 preserves the partial capture, the partial observations and a failure marker; the first 100 are **not** rolled back; retry happens at the **task/run** level, not as blind subprocess duplication, and checks idempotency, previous partial observations, connector state and the raw artifact first. (FR-143, FR-144)
- [ ] **T334** [US4] `ACQ-11` 🔴 **LIVE** — real run 1 → observations → STATE checkpoint; real run 2 resumes (incrementality: duplicate prevention does not suppress legitimately new records); full-refresh semantics verified **separately** — the same source state yields **new acquisition observation occurrences**, not a semantic overwrite of previous evidence. **Run §162-PROC E–G** for Airbyte. (FR-095, FR-096)

### `ACQ-13` · Maigret definition (`T340`…`T346`) · US5

- [ ] **T340** [P] [US5] `ACQ-13` Create `apps/acquisition/runtime/definitions/tools/maigret.yaml`. **Donor: `apps/acquisition/sources/estorides/20_system_tools/kali_maigret.yaml` is the argv donor**, adapted per D-15 to the existing loader; image `ghcr.io/soxoj/maigret` built from `donors/maigret/Dockerfile`, digest recorded. **No uniform `all tools = 2 GB / 10 m` ceiling**: `max_sites=200, max_connections=20, timeout=20 s`. (FR-156, FR-199)
- [ ] **T341** [US5] `ACQ-13` Offline test — argv comes from the `ToolDefinition` as an array; `shell=False`; **nothing** is hardcoded in the runtime. **Donor: the exact argv `<user> --json simple --timeout 30` is taken from `donors/maigret/maigret/maigret.py`; the metacharacter check from `donors/estorides/estorides_core/tool_runner.py` is retained as a *second* layer behind `shell=False`.** (FR-115, FR-102)
- [ ] **T342** [US5] `ACQ-13` Offline test — the task carries `username, id_type, site selection/filter, timeout, max sites, profile parsing mode`; **both** the canonical and the raw username are retained and canonicalization never destroys the original. **Donor, adapted: `donors/estorides/estorides_core/transliteration.py` (146 lines)** — the variant-generation approach, used as the shape for `canonical_username` vs `raw_username`. (FR-100)
- [ ] **T343** [US5] `ACQ-13` Implement the Maigret result parser. **Donor: `donors/maigret/maigret/result.py` and `sites.py`** — the result-object field set `site_name, status, url_user, http_status, rank, ids_data` and the site-database version accessor. Every additional genuinely present field is preserved. The site database is **data**; `status` is the tool's claim, never the platform's. (FR-101, FR-106)
- [ ] **T344** [US5] `ACQ-13` Offline test — `status.is_found()` is **not** converted into `entity_exists = true`; a timeout or HTTP error yields `observation status = failed/indeterminate`, **not** `not_found`, unless Maigret itself gives grounds for that inference; observation metadata carries `tool = maigret, tool_version, database_version, site_name, site_rank, request_username` and, under proxy, `proxy_mode` + `proxy_ref` — **never a secret**. (FR-101, FR-102)
- [ ] **T345** [US5] `ACQ-13` Offline test — the 8 Maigret states `site unavailable / timeout / blocked / HTTP 404 / not found / found / indeterminate / tool failure` are distinguishable and are **not** collapsed into a binary; reconciliation reports `sites scheduled, sites completed, results yielded, observations persisted`. (FR-104, FR-196)
- [ ] **T346** [US5] `ACQ-13` 🔴 **LIVE** — a real Maigret container, a real controlled test username, real site checks, real stdout/result artifact. **Run §162-PROC A–H** for Maigret. Site-check **accuracy is not an acceptance condition**; passing the acquisition protocol is. §145 + **O-6**: the target must be operator-approved, not agent-chosen. (FR-103)

### `ACQ-14` · BBOT definition (`T350`…`T356`) · US6

- [ ] **T350** [P] [US6] `ACQ-14` Create `apps/acquisition/runtime/definitions/tools/bbot.yaml`. **No BBOT tree in `donors/` — image-pinned, not a code transfer**: `blacklanternsecurity/bbot`, digest resolved and recorded at acceptance (**O-4**), scan target allowlist, `scan_timeout=600 s`, `--pids-limit=200`. (D-13, FR-156)
- [ ] **T351** [US6] `ACQ-14` Offline test — the bridge path is exactly `BBOT event JSON → validate donor event → AcquisitionArtifact → Capture → Observation → EventEnvelope`; `type, id, uuid, data/data_json, scope, parent, parent_uuid, timestamp, module, module_sequence, discovery_context, discovery_path, parent_chain` are preserved **if present**; **no semanticisation occurs at acquisition time**. Must fail first. (FR-107, FR-108)
- [ ] **T352** [US6] `ACQ-14` Implement the BBOT JSON/NDJSON event bridge. **The BBOT native Kafka output module is NOT connected to the canonical observation topic** — its event schema is a BBOT schema, not the platform's `EventEnvelope`. **No donor code: image-pinned.** (FR-107)
- [ ] **T353** [US6] `ACQ-14` Offline test — `parent_chain` is donor **provenance** on the observation (`OBS-BBOT-EVENT-X → provenance.parent_chain → [...]`) and does **not** imply a platform `RelationClaim`; `A parent-of B` is not automatically a platform assertion about the world. (FR-109, FR-014)
- [ ] **T354** [US6] `ACQ-14` Offline test — **AST import check**: no module under `apps/acquisition/runtime/`, `apps/acquisition/sources/` or `apps/interpretation/observation_consumer/` imports or calls `GraphWriter, GraphEdge, RelationClaim, EntityStore, KnowledgeGraph` — **even when the donor tool produces relationship-like output**. This test fails the build on violation. (FR-015, Principle III, Invariant 4)
- [ ] **T355** [US6] `ACQ-14` Offline test — BBOT provenance preserves `BBOT version`, `preset/config identity` and `module identity`; reconciliation reports `events seen, events parsed, events persisted, events published, events processed`; tool process failure / module failure / target result / transport error / partial run stay **separate**. (FR-113, FR-111, FR-197)
- [ ] **T356** [US6] `ACQ-14` 🔴 **LIVE** — a real BBOT container, a safe bounded test target, a hard timeout: scan starts → bounded stop → events received → ≥ 1 event persisted → raw run preserved → observation created. **Run §162-PROC A–H** for BBOT. §145 + **O-6**: the target is operator-approved. (FR-110)

### `ACQ-15` · SpiderFoot definition (`T360`…`T366`) · US7

- [ ] **T360** [P] [US7] `ACQ-15` Create `apps/acquisition/runtime/definitions/tools/spiderfoot.yaml`. **Donor: `donors/spiderfoot/sf.py`, `sfscan.py`, `docker-compose*.yml` and the module registry** — the CLI argv surface and the image build, the image being built from `donors/spiderfoot/Dockerfile`. `max_threads=10, runtime_limit=600 s, output_limit=128 MiB`, bounded passive use case. **`donors/spiderfoot/correlations/` is NOT imported** (§54). (FR-156, FR-199)
- [ ] **T361** [US7] `ACQ-15` Offline test — the CLI JSON boundary is `-s TARGET -m modules -t event types -u use case -o json` and export of scan data as JSON is supported; every parameter is supplied by the `ToolDefinition` as `argv: list[str]`; `shell=True` is **not** used; nothing is hardcoded in the runtime. Must fail first. (FR-114, FR-115)
- [ ] **T362** [US7] `ACQ-15` Implement the SpiderFoot JSON bridge: `scan / event / target / module / event type / data` become platform Observations; the SpiderFoot JSON is **not** treated as a finished platform observation on arrival. **Donor, adapted: `donors/spiderfoot/sf.py` / `sfscan.py` event shapes.** (FR-116)
- [ ] **T363** [US7] `ACQ-15` Offline test — the SpiderFoot correlation engine does **not** write to the platform graph; the path is `SpiderFoot correlation output → tool observation → interpretation`; if a correlation is retained as an inference artifact it is retained as a provenance-bound observation. **Donor explicitly NOT taken: `donors/spiderfoot/correlations/`.** (FR-117, FR-014)
- [ ] **T364** [US7] `ACQ-15` Offline test — the run preserves `selected modules`, `use case`, `event filters` and `tool version`; without them the same CLI target is not reproducible. Reconciliation reports `events exported, events parsed, events observed, events processed`; tool process failure / module failure / target result / transport error / partial run stay separate. (FR-121, FR-198, FR-111)
- [ ] **T365** [US7] `ACQ-15` Offline test — ≥ 1 event is required; ≥ 10 is desirable where the target genuinely produces more; an event count **above 1 must not be required** where runtime/source variation makes the count unstable. (FR-118, FR-119)
- [ ] **T366** [US7] `ACQ-15` 🔴 **LIVE** — a real SpiderFoot container, a bounded passive/investigative scenario: process starts → JSON emitted → event parsed → observation created. **Run §162-PROC A–H** for SpiderFoot. **O-6**: the use case is operator-approved. (FR-119)

### ✅ Checkpoint 3 — GATE `G3`

**Must be green**: all six per-runtime packages delivered; each has an offline group and a live group; the live tasks T219, T229, T239, T314, T325, T334, T346, T356, T366 have written their A–H evidence to the per-runtime artifact files.

**Blocking**: **R2** — no governance work (`T4*`) and no live scenario (`T5*`) before this.

---

## Phase 4: Governance and resource controls (Wave 4) — `T410`…`T425`

**Purpose**: `ACQ-16` — make the five runtimes safe to run at load. §196 places this **after** all runtime classes and **before** the live scenarios, because the live scenarios are what the controls make safe to run. It is P6 because until the runtimes exist there is nothing to bound.

- [ ] **T410** [US8] `ACQ-16` Offline test — for **all five** runtimes the launched container has no bind mount, no `/var/run/docker.sock`, `--read-only`, `--cap-drop ALL`, `--security-opt no-new-privileges`, `--pids-limit`, `--memory`, `--cpus`, bounded `--network`, tmpfs scratch, `--rm`; and no acquisition tool receives host filesystem, host credentials, platform secrets or unbounded outbound network. The path is `Acquisition Service → dedicated runner → isolated container`. (FR-154)
- [ ] **T411** [US8] `ACQ-16` `limits.py` **concrete** numbers, not "tune later": SearXNG `small · 1.0 cpu / 512 MiB / 120 s · 16 MiB out · 200 rec · hard_max_pages=10, connect 5 s, read 15 s, max_results_per_task=200, parallel_queries=1` · Airbyte `medium · 2.0 / 2 GiB / 900 s · 256 MiB · 50 000 · max_record_bytes=8 MiB, max_buffered_messages=10 000, max_buffered_bytes=32 MiB, connector_timeout=900 s` · Maigret `medium · 2.0 / 2 GiB / 300 s · 64 MiB stdout · 2 000 · max_sites=200, max_connections=20, timeout=20 s, max_stderr_bytes=8 MiB` · BBOT `large · 4.0 / 4 GiB / 900 s · 128 MiB stdout · 100 000 · scan_timeout=600 s, pids=200, max_stderr_bytes=16 MiB` · SpiderFoot `large · 4.0 / 4 GiB / 900 s · 128 MiB · 10 000 · max_threads=10, runtime_limit=600 s, output_limit=128 MiB`. Class table: `small = 1.0/512 MiB/300 s/32 MiB/1 000/conc 2` · `medium = 2.0/2 GiB/900 s/128 MiB/10 000/conc 4` · `large = 4.0/4 GiB/1 800 s/512 MiB/100 000/conc 8`. (FR-156)
- [ ] **T412** [US8] `ACQ-16` Offline test — `max_stdout_bytes` and `max_stderr_bytes` are **separate** ceilings; a breach kills the process with `reason = output_limit_exceeded`, or performs controlled truncation only where the protocol safely supports it, with raw partial output preserved. (FR-161)
- [ ] **T413** [US8] `ACQ-16` Offline test — every runtime declares `connect timeout, read timeout, overall task timeout, shutdown grace period`; after a timeout the sequence is `SIGTERM → grace → SIGKILL` **with the result recorded**. (FR-159)
- [ ] **T414** [US8] `ACQ-16` Offline test — the worker tracks child processes, especially for BBOT and SpiderFoot, and **no orphan process survives a timeout**. (FR-160)
- [ ] **T415** [US8] `ACQ-16` Offline test — network policy is **explicit per runtime**: SearXNG's worker sees only the internal SearXNG endpoint (SearXNG does the federation); Airbyte has access per connector requirements but through controlled egress; Maigret/BBOT/SpiderFoot have an **explicit** outbound policy and are **not** granted unrestricted egress "because the tool is OSINT". SearXNG upstream engine latency variance is **not** counted as a routing-layer error. (FR-157, FR-073)
- [ ] **T416** [US8] `ACQ-16` Offline test `apps/acquisition/tests/integration/test_backpressure_growth.py` — backpressure runs the other way: `backlog ↑ → acquisition rate ↓`. Expanding concurrency as backlog grows is forbidden; the dispatcher's `limits.allows()` consults the class concurrency and a growing `acquisition` queue length **reduces** the permit count. (FR-155, §66, Invariant Backpressure)
- [ ] **T417** [US8] `ACQ-16` Offline test — boundedness: RSS sampled during a 50 000-record Airbyte `read()` stays under the class limit; the stdout parser never holds more than `max_buffered_messages`; ObjectStore writes are streamed and bounded; `STATE` processing does not block indefinitely; Kafka publish does not block the connector forever; no O(N²) acquisition routing. (FR-162, FR-094, Invariant 12)
- [ ] **T418** [US8] `ACQ-16` Offline test — the legacy `acquisition_loop.py` is **not** used; it is recorded as absent from the repository, and §64's prohibition is against a file that is not there. (FR-153)
- [ ] **T419** [US8] `ACQ-16` Offline test — a corpus of fake `access_token` / `api_key` / `password` / OAuth refresh token strings is pushed through every run; `rg` over the Redpanda dump, the structured logs, the run manifest and `git diff` returns **zero** hits; no secret appears in argv, normalized argv digests, config digests or manifests. (FR-082, FR-163, FR-164, SC-014)
- [ ] **T420** [US8] `ACQ-16` Edit `apps/deploy/docker-compose.yml` — add a `runtimes` profile with `searxng`, `tool-runner` (**no** socket mount — it uses the host Docker context), `acq-airbyte`, `acq-maigret`, `acq-bbot`, `acq-spiderfoot`, `observation-consumer`. **The existing file, the existing profiles (`core`, `analytics`, `streaming`, `collectors`) — a second parallel infrastructure stack is forbidden (§126).** (FR-180, FR-181)
- [ ] **T421** [US8] `ACQ-16` Create `apps/deploy/searxng/settings.yml` with `search.formats` including `json`; verify the `runtimes` profile resolves inside the existing compose file and that no second stack file appears. (FR-059, FR-180)
- [ ] **T422** [US8] `ACQ-16` Create the **donor version manifest** per runtime: `tool, source_repository, license, version, image, digest, integration_role, adapted_components, non_transferred_semantics, known_patches`; and record in the run manifest `upstream repo, commit, license, copied code, adapted code, dynamic/external execution boundary`. License compliance preserved, especially for copyleft source projects; **no legal "magic clean room"** is claimed. **O-4** (digest approval) is a user decision; the default is to resolve digests at acceptance and record them. (FR-199)
- [ ] **T423** [US9] `ACQ-16` 🔴 **LIVE-INFRA PROBE (re-run)** — before any live scenario, `docker compose ps` and machine-readable health checks must pass; E2E MUST NOT start before `Redpanda healthy` / `Postgres healthy` / `ObjectStore healthy`, where healthy means **capability to process, not merely container status**. (FR-182)
- [ ] **T424** [US8] `ACQ-16` 🔴 **LIVE** — with the `runtimes` profile up, all five runtime containers start under policy and the consumer is subscribed. **Run §162-PROC B–C** for all five runtimes. If the stack is down, halt at B and record `class: container`. (FR-154, FR-181)
- [ ] **T425** [US8] `ACQ-16` Offline test — AST check that the new packages import neither `gudhi` nor `giotto_tda` and emit no `TopologicalFeature` (Invariant 6), and that acquisition performs **no direct entity resolution** — it may produce only `raw identifier, username, URL, IP, domain, email-like string, tool id`; resolution is downstream. (FR-016, FR-017)

### ✅ Checkpoint 4 — GATE `G4`

**Must be green**: every tool launched under policy; per-runtime limits declared and enforced; backpressure direction asserted; no secret leakage; the `runtimes` profile resolves in the **existing** compose file; donor version manifests written; T423/T424 green against real infra.

**Blocking**: **R2** — the five live scenarios (`T5*`) may not start before this. Running them without the sandbox is precisely what §196 orders against.

---

## Phase 5: Live scenarios (Wave 5) — `T510`…`T536`

**Purpose**: `ACQ-19` — five live smoke scenarios, each launched through the standard `InvestigationWorkflow`, completing the §152 test matrix.

- [ ] **T510** [US9] `ACQ-19` Create `apps/acquisition/tests/live/test_matrix.py` — the §152 matrix as executable assertions: 5 runtimes × 6 classes (Unit, Fixture, Process, Redpanda, Live, Replay) = **30 cells**, each of which must be green. A cell with no test is a red cell, not an empty one. (FR-192, SC-015)
- [ ] **T511** [US2] `ACQ-19` Create `apps/acquisition/workflow/investigation_workflow.py` — the single production entrypoint owning task creation and dispatch, delegating lifecycle to the existing `Investigation`. **Donor: none — the existing `Investigation` lifecycle in the platform is wrapped, not replaced.** No symbol by this name exists in the tree today; **O-5** is a user naming decision and the default plan is a thin module here. (FR-054)
- [ ] **T512** [P] [US2] `ACQ-19` Offline test — all five sources launch **only** through `InvestigationWorkflow`, never through a direct worker/connector/graph call, and `investigation_id, tenant_id, task_id, source_id, worker_ref, runtime_ref` are present along the entire live path. `default-tenant` / `default-investigation` are **not** used on the live production path; fixtures may use defaults only inside isolated tests. (FR-054, FR-151)
- [ ] **T513** [P] [US9] `ACQ-19` Create `bench/acquisition/scenarios.py` — the five scenario definitions, each declaring the §79 contract: `scenario id, target/query, source id, worker ref, runtime ref, expected minimum observations, expected topic, expected consumer, assertions, cleanup`. **Donor: none — taken from platform, `bench/run.py`'s `ScenarioResult` / `Step` model.** (FR-185, FR-186)
- [ ] **T514** [US3] `ACQ-19` 🔴 **LIVE** — `live_searxng_smoke`: `investigation = int-searxng-smoke`, query `"SearXNG GitHub"`, source `searxng.search`, worker `http`, runtime `searxng`. All **15** §23 steps individually evidenced: task created; task dispatched; searxng runtime invoked; HTTP 200; JSON parsed; ≥ 1 result emitted; capture stored; raw_ref exists; ≥ 1 observation persisted; `observation.created` in Redpanda; consumer receives; consumer fetches raw_ref; consumer resolves locator; downstream processing completes; processing record persisted. **Run §162-PROC A–K, L–O.** (FR-068, FR-187, SC-005)
- [ ] **T515** [US4] `ACQ-19` 🔴 **LIVE** — `live_airbyte_smoke` against a **real** connector: `connector image resolved → spec succeeds → check succeeds → discover succeeds → catalog persisted → read starts → N ≥ 10 real RECORD → RECORD → Capture/Observation → STATE processed in the mandatory order → observation.created into Redpanda → downstream consumer receives → consumer resolves the record → processing succeeds`. Where a connector physically returns fewer than 10 records, `all available records ≥ 1` is permitted **but the reason MUST be recorded, not masked**. A fixture connector is never the final decision (§161). **Run §162-PROC A–K, L–O.** (FR-088, FR-188, SC-006, **O-3**)
- [ ] **T516** [US5] `ACQ-19` 🔴 **LIVE** — `live_maigret_smoke` with a controlled test username: tool starts; sites checked; ≥ 1 result record; Capture; Observation; Redpanda; consumer; and a completed downstream parser. Site-check accuracy is **not** an acceptance condition. **Run §162-PROC A–K, L–O.** (FR-103, FR-189)
- [ ] **T517** [US6] `ACQ-19` 🔴 **LIVE** — `live_bbot_smoke` against a safe bounded test target under a hard timeout: scan starts; event stream exists; ≥ 1 event; Capture; Observation; Redpanda; consumer; donor event parser succeeds. **Run §162-PROC A–K, L–O.** (FR-110, FR-190)
- [ ] **T518** [US7] `ACQ-19` 🔴 **LIVE** — `live_spiderfoot_smoke` as a bounded passive/investigative scenario: process starts; JSON emitted; event parsed; Observation created; Redpanda event; downstream processing. An event count above 1 is **not** required where source variation makes the count unstable. **Run §162-PROC A–K, L–O.** (FR-118, FR-191)
- [ ] **T519** [P] [US3] `ACQ-19` Offline test — a real consumer exists on the path `observation.created → SearXNG observation decoder → structured observation → discovery / mention producer`, minimally `search result → URL candidate / document discovery candidate`, remaining provenance-bound to the source capture via `source = SearXNG, observation_id, capture_id, result_locator`. **Donor: the platform's existing `apps/interpretation/parsers/payload/` + `extractors/payload/` + `domain/mention_occurrence_index`, reused unchanged.** (FR-067)
- [ ] **T520** [US9] `ACQ-19` Offline test — **no false green**: no `pytest.mark.live_integration` test carries `skip` or `xfail`; `--strict-markers` accepts the marker; every live scenario is reachable from `uv run python -m bench.run --scenario acquisition-integration` and is **not** automatically skipped during release validation. (FR-008, FR-009)
- [ ] **T521** [US1] `ACQ-19` Create `integration_run_id` and the **trace manifest** on every E2E run, carrying `integration_run_id, tenant_id, investigation_id, task_id, source_id, worker_ref, runtime_ref, runtime_version, capture_ids, observation_ids, event_ids, topics, consumer_group, offsets, processing_results`. The trace manifest is **itself** an operational artifact. (FR-125)
- [ ] **T522** [US1] `ACQ-19` Structured logs carry `integration_run_id, task_id, source_id, worker_ref, runtime_ref, capture_id, observation_id, event_id`; every log line belongs to a concrete runtime execution. (FR-174)
- [ ] **T523** [P] [US1] `ACQ-19` Metrics per runtime: `tasks started, tasks completed, tasks failed, records emitted, observations created, duplicates, quarantine count, bytes fetched, bytes stored, runtime seconds, Kafka publish failures, consumer failures`; labelled by `source_id, worker_ref, runtime_ref, producer_version, tenant_id` and carrying **no** secret or raw user data as a label. (FR-171, FR-172)
- [ ] **T524** [P] [US1] `ACQ-19` `consumer lag` is accessible, and an acceptance run is **not green** until the event has physically been processed by a consumer. (FR-173, Invariant 10)
- [ ] **T525** [US9] `ACQ-19` **§162-PROC A–O executed for SearXNG** — record the phase-by-phase result into `artifacts/acquisition-integration/searxng.json` (completing the A–H portion written at T219). (FR-207)
- [ ] **T526** [US9] `ACQ-19` **§162-PROC A–O executed for Airbyte** → `artifacts/acquisition-integration/airbyte.json` (completing T229/T325/T334). (FR-207)
- [ ] **T527** [US9] `ACQ-19` **§162-PROC A–O executed for Maigret** → `artifacts/acquisition-integration/maigret.json` (completing T239/T346). (FR-207)
- [ ] **T528** [US9] `ACQ-19` **§162-PROC A–O executed for BBOT** → `artifacts/acquisition-integration/bbot.json` (completing T239/T356). (FR-207)
- [ ] **T529** [US9] `ACQ-19` **§162-PROC A–O executed for SpiderFoot** → `artifacts/acquisition-integration/spiderfoot.json` (completing T239/T366). (FR-207)
- [ ] **T530** [US9] `ACQ-19` 🔴 **LIVE** — **multi-record proof**: the first successful run uses a source that genuinely emits several records, disproving `first record only`, `last record only` and `one observation per process` — `record_count > 1` for Airbyte, `results_count > 1` for SearXNG where the engine returns them. (FR-176)
- [ ] **T531** [US9] `ACQ-19` 🔴 **LIVE** — **zero-data-loss check**: for a bounded smoke with known `N`, `source records ≥ N`, `observations durable ≥ N`, `Redpanda events ≥ N`, `downstream processed ≥ N`. For nondeterministic live tools the requirement is `at least one` **plus a written explanation**; the explanation is part of the artifact, not a footnote. (FR-193, SC-008)
- [ ] **T532** [US9] `ACQ-19` 🔴 **LIVE** — **cross-tenant**: two test tenants; the same raw bytes may share a content digest, but `tenant A event → tenant B observation resolution` MUST NOT occur, and cross-tenant raw retrieval via a guessable URI is impossible. (FR-152, FR-150)
- [ ] **T533** [P] [US9] `ACQ-19` Offline test — every `Capture, Observation, EventEnvelope, ObjectStore key, task, run` carries tenant identity; `investigation_id` is preserved in all event envelopes. (FR-150, FR-151)
- [ ] **T534** [P] [US9] `ACQ-19` Offline test — the four/five-stage reconciliation counters per family: Airbyte `TOTAL messages, RECORD, STATE, LOG/TRACE` with `record_count > 0`, `observation_count == record_count`, STATE excluded; SearXNG `pages fetched, results reported by parser, observations persisted` with `pages ≥ 1, results ≥ 1, observations == retained result count`; Maigret `sites scheduled/completed, results yielded, observations persisted`; BBOT `events seen/parsed/persisted/published/processed`; SpiderFoot `events exported/parsed/observed/processed`. (FR-194, FR-195, FR-196, FR-197, FR-198)
- [ ] **T535** [US9] `ACQ-19` 🔴 **LIVE** — **Redpanda class** for each runtime: `inspect-kafka` confirms `topic == observation`, `event_id exists`, `observation_id exists`, and the trace is recoverable in the §157 form `INV-123 / TSK-123 / worker http / runtime searxng / GET … / HTTP 200 sha256=… / CAP-abc / json:results[0] / OBS-def / EVT-ghi / topic observation / partition 3 / offset 812 / consumer interpretation-1 / processing processed / derived ref`. All identifiers available for forensic inspection. (FR-124, FR-132, FR-003, FR-004)
- [ ] **T536** [US9] `ACQ-19` Offline test — §0/§0.1 insufficiency conditions are encoded as *negative* assertions in the suite: the harness must not report PASS when adapters merely exist, when a consumer processed nothing, or when only `observation.created` exists in code. **The unit of progress is the length of the runtime path actually traversed**: `"event_id E123 at partition 2 offset 847 consumed by group G123"` outranks `"event_id appeared in topic observation"`, which outranks `"adapter implemented"`. (FR-001, FR-002, FR-005, FR-006)

### ✅ Checkpoint 5 — GATE `G5`

**Must be green**: all five live scenarios green; the §152 matrix's Process / Redpanda / Live cells green for all five runtimes; §162-PROC A–O recorded for all five; the zero-data-loss and multi-record checks pass; cross-tenant isolation holds; no live test is `skip`/`xfail`.

**Blocking**: **R2** — no replay work (`T6*`) before this. Replay without a green live run replays nothing.

---

## Phase 6: Replay (Wave 6) — `T610`…`T620`

**Purpose**: `ACQ-20` — replay infrastructure, both task-level and observation-level. §196 places replay after the live scenarios because replay of an unproven run proves nothing.

- [ ] **T610** [US9] `ACQ-20` Create `bench/acquisition/replay.py` — `replay(task_id)` works **without manually rewriting the acquisition config**, reproducing `worker_ref, runtime_ref, source_id, input, limits, tenant, investigation` under a **new** `integration_run_id`. **Donor: none — taken from platform, `apps/acquisition/observation_gate/replay.py::FileReplayJournal`, reused.** (FR-166)
- [ ] **T611** [P] [US9] `ACQ-20` Offline test — `replay(task_id)` reproduces the full acquisition configuration and produces a **new** `integration_run_id`. (FR-166)
- [ ] **T612** [US9] `ACQ-20` `replay_observation(observation_id)` performs **zero** network acquisitions; it reads `raw_ref` from the ObjectStore. (FR-167)
- [ ] **T613** [P] [US9] `ACQ-20` Offline test — `replay_observation` with a transport that raises on any call makes **0** calls; a sentinel transport is installed for the assertion, not a mock of the result. (FR-167, SC-010)
- [ ] **T614** [US9] `ACQ-20` **Parser replay**: `raw capture → parser v1` and `raw capture → parser v2` with **no change to source acquisition**; `same raw capture → reparse → different interpretation version` MUST NOT require repeat network acquisition; unknown data is retained and the raw artifact remains the source of truth. (FR-168, FR-169, FR-200, Invariant 11)
- [ ] **T615** [US9] `ACQ-20` Extend `bench/acquisition/__main__.py` — `inspect-consumer --group <g> --topic observation --event-id <e> --lag --poison`, per the Redpanda-first ladder in §162-PROC. (FR-205, FR-165)
- [ ] **T616** [US9] `ACQ-20` Complete the command set: `run integration / dump task / dump capture / dump observation / inspect Kafka / inspect consumer / replay task` — a single **executable** instruction per operation, not README prose. (FR-165)
- [ ] **T617** [US9] `ACQ-20` 🔴 **LIVE** — after a clean live run with downstream stopped, replay Kafka events / observations reproduces the **same durable interpretation** with **no new network acquisition**. (FR-178, SC-010)
- [ ] **T618** [US9] `ACQ-20` 🔴 **LIVE** — `replay raw observation → same observation identity → same deterministic parser result`, exercised for each of the five families. (FR-213, SC-003)
- [ ] **T619** [P] [US9] `ACQ-20` Offline test — the §165 determinism invariant over the full chain: `capture → record extraction → observation IDs` performed twice yields the same capture identity, the same observation identities and the same locator identities; every persisted collection that is a semantic projection of one raw payload is sorted deterministically, with no reliance on donor `dict` insertion order, `set` order, thread timing or async completion order. (FR-042, FR-039, FR-038)
- [ ] **T620** [US9] `ACQ-20` **§162-PROC L (Replay) and M (Verify deterministic identity)** recorded for all five runtimes into the per-runtime artifact files. (FR-207)

### ✅ Checkpoint 6 — GATE `G6`

**Must be green**: `replay(task_id)` reproduces the config under a new run id; `replay_observation` makes zero network calls; parser v1/v2 from one raw; T617/T618 green for all five families; determinism holds over 100 attempts.

**Blocking**: **R2** — no failure journal (`T7*`) before this. The journal must record real failures, and there are none until replay is proven.

---

## Phase 7: Failure journal (Wave 7) — `T710`…`T724`

**Purpose**: `ACQ-21` — a machine-readable integration failure report, so that "it didn't work" becomes a classifiable, actionable record instead of a shrug.

- [ ] **T710** [US9] `ACQ-21` Create the `FailureRecord` model in `apps/acquisition/runtime/base.py` — one record per failure, carrying `task_id, integration_run_id, worker_ref, runtime_ref, tool version, image digest, argv sans secrets, exit code, bounded stdout/stderr artifact, source response metadata, event ids, Kafka topic/partition/offset, consumer error`, with `class` drawn from the **closed 20-member vocabulary**: `build, configuration, dependency, container, process, network, DNS, TLS, authentication, protocol, parsing, identity, storage, Kafka, schema, consumer, downstream, performance, security policy, determinism`. Secrets are **redacted before storage**. (FR-203, FR-204)
- [ ] **T711** [US9] `ACQ-21` Implement `classify_error()` mapping **every** runtime exception to one of the 20; an unmapped code **raises `UnclassifiedFailure`** rather than defaulting. A generic "integration failed" without classification is forbidden. (FR-203)
- [ ] **T712** [P] [US9] `ACQ-21` Offline test — all **14** Airbyte failure codes (`image_not_found, container_start_failed, spec_failed, check_failed, discover_failed, protocol_malformed, record_invalid, state_invalid, connector_runtime_failed, timeout, resource_limit_exceeded, network_denied, credential_unavailable, credential_rejected`) are individually constructed and individually observable. (FR-087, SC-012)
- [ ] **T713** [P] [US9] `ACQ-21` Offline test — all **8** Maigret states are individually constructed and observable; BBOT and SpiderFoot keep tool process failure, module failure, target result, transport error and partial run separate. (FR-104, FR-111)
- [ ] **T714** [US9] `ACQ-21` Offline test — the §74 evidence set survives a round trip and the secret-redaction pass removes every credential material before the record is written to disk. (FR-204, SC-014)
- [ ] **T715** [P] [US9] `ACQ-21` Offline test — **0** occurrences of a generic unclassified "integration failed" across the full failure vocabulary. (FR-203)
- [ ] **T716** [US9] `ACQ-21` Create `bench/acquisition/report.py` — the final report is **machine-readable**: success `{"status": "PASS", "sources": {"searxng": {"tasks":1,"captures":1,"observations":12,"published":12,"processed":12}, "airbyte": {…}}}`; failure `{"status":"FAIL","failed_stage":"observation_gate.publish","task_id":"…","capture_id":"…","observation_id":"…","reason":"…","failure_class":"…"}`. (FR-206, FR-159)
- [ ] **T717** [US9] `ACQ-21` Create `bench/acquisition/inspect.py` — every inspection command exits non-zero and prints the §159 failure shape with `failed_stage`, so a stall is located, not guessed. (FR-205, FR-206)
- [ ] **T718** [US9] `ACQ-21` 🔴 **LIVE** — the §72 loop, executed for real: `RUN → OBSERVE → CLASSIFY FAILURE → PATCH → RESTART AFFECTED COMPONENT → REPLAY TASK → VERIFY → RUN AGAIN`, applied to a **deliberately induced** failure in each of the five runtimes. The work does **not** stop at "the adapter is written" / "the test fails because of infrastructure" / "the connector does not answer yet" / "Redpanda did not accept something". The loop runs until green acceptance or until a clearly recorded infrastructure blocker that genuinely cannot be removed from this execution context. (FR-202, FR-208, §161)
- [ ] **T719** [US2] `ACQ-21` 🔴 **LIVE** — **failure drill: producer active / consumer temporarily stopped.** The source emits; after the consumer restarts, **all observations are eventually processed with zero data loss**. (FR-179)
- [ ] **T720** [US2] `ACQ-21` 🔴 **LIVE** — **failure drill: consumer crashes mid-processing.** After restart the event is replayed and the observation is **not** semantically duplicated. (FR-179)
- [ ] **T721** [US2] `ACQ-21` 🔴 **LIVE** — **failure drill: duplicate delivery.** One `EventEnvelope` is deliberately delivered twice → exactly **one** semantic processing result, with the `idempotency_key` recorded as evidence. (FR-179)
- [ ] **T722** [US9] `ACQ-21` Offline test — **global Kafka ordering is not assumed**: ordering guarantees are scoped to key/partition, and record identity does not depend on incidental global ordering. (FR-179)
- [ ] **T723** [US9] `ACQ-21` 🔴 **LIVE** — **scale-up** from `1 task → N tasks` within the resource budget, verifying `concurrency, backpressure, ordering, dedup, Kafka lag, ObjectStore pressure, DB pressure, tool isolation`. (FR-175)
- [ ] **T724** [US9] `ACQ-21` 🔴 **LIVE** — **no runaway** under that scale: no unbounded memory, no runaway process, no Kafka backlog runaway, no raw-to-Kafka blob transfer, no O(N²) acquisition routing; a growing backlog **reduces** the acquisition rate. (FR-162, FR-155, SC-016)

### ✅ Checkpoint 7 — GATE `G7`

**Must be green**: the 20-class vocabulary complete; 0 unclassified failures; T718's debug→patch→replay→verify loop executed and green for all five runtimes; T719–T721 failure drills pass; T723/T724 scale-up shows no runaway.

**Blocking**: **R2** — no clean-stack acceptance (`T8*`) before this. A clean stack with an unproven failure path is a clean stack that fails silently.

---

## Phase 8: Clean-stack acceptance (Wave 8) — `T810`…`T818`

**Purpose**: `ACQ-22` — run all five scenarios against a **fresh** stack. This is where §0 / §0.1 / §204 stop being prose.

- [ ] **T810** [US9] `ACQ-22` **Migration gate**: `migration up → smoke → migration replay / clean environment`. Green on an already-mutated local database is **not accepted**. (FR-210, §187)
- [ ] **T811** [US9] `ACQ-22` Provision the **clean stack**: fresh DB, fresh Redis, fresh ObjectStore namespace, fresh Redpanda topics and consumer group. (FR-211, §188)
- [ ] **T812** [US9] `ACQ-22` Wire the single release-acceptance entrypoint `uv run python -m bench.run --scenario acquisition-integration` to perform `prepare / healthcheck / run 5 sources / reconcile / inspect Kafka / inspect downstream / emit final report`. **Donor: none — the existing `bench/run.py` entrypoint, extended, not a new harness.** (FR-209)
- [ ] **T813** [US9] `ACQ-22` 🔴 **LIVE** — the §200 sequence, executed from the clean stack: start stack → create investigation → SearXNG task → records in Redpanda → downstream processing → Airbyte task → RECORD stream → Redpanda → processing → Maigret task → site results → Redpanda → processing → BBOT task → event stream → Redpanda → processing → SpiderFoot task → JSON/event stream → Redpanda → processing. **This repeatable sequence — not the class count, not the YAML definition count, not passing unit tests, not the presence of containers — is the final completion criterion.** (FR-213, SC-003)
- [ ] **T814** [US9] `ACQ-22` 🔴 **LIVE** — `kill consumer → resume → all pending observations processed`, with zero loss. (FR-213, FR-179, SC-011)
- [ ] **T815** [US9] `ACQ-22` 🔴 **LIVE** — `replay raw observation → same observation identity → same deterministic parser result`; then `clean stack → repeat`, with all five runtime paths green **again** from a second fresh stack. (FR-213, SC-003)
- [ ] **T816** [US9] `ACQ-22` The §194 **acceptance matrix**: per runtime, `Source reached, Raw captured, Observation, Redpanda, Consumer, Replay` all read `required`; any row not all-green is `BLOCKED`; **no row is satisfied by another row** and no runtime's acceptance may be substituted for, or inferred from, another runtime's green pass. (FR-212, SC-004)
- [ ] **T817** [US9] `ACQ-22` The §204 **eight-factor product** evaluated per family: `REAL SOURCE × REAL RUNTIME × REAL CAPTURE × REAL OBSERVATION × REAL REDPANDA EVENT × REAL CONSUMER × REAL DOWNSTREAM PROCESSING × REAL REPLAY`. If any single factor is zero, `FEATURE = NOT COMPLETE`. (FR-001, SC-002)
- [ ] **T818** [US9] `ACQ-22` **§162-PROC O (Final acceptance)** recorded for all five runtimes against the clean stack. (FR-207)

### ✅ Checkpoint 8 — GATE `G8`

**Must be green**: T810 migration replay clean; T811–T815 executed on a genuinely fresh stack; T816 matrix all-`required` on all five rows; T817 eight factors non-zero per family; T818 recorded.

**Blocking**: **R2** — no final artifact emission (`T9*`) before this. Emitting a manifest over an unproven run would be a fabricated artifact.

---

## Phase 9: Final artifacts and release gate (Wave 9) — `T910`…`T921`

**Purpose**: §201's mandatory artifact tree, the machine-readable acceptance report, and the explicit §160 release-blocker audit. The template's "Polish" phase does not exist for this feature — there is no polish; there is a gate.

- [ ] **T910** [US9] Emit `artifacts/acquisition-integration/run-manifest.json` containing `git sha, deployment identity, source versions, runtime versions, image digests, schema versions, integration run ids, task ids, capture ids, observation ids, event ids, Kafka topics, partitions, offsets, consumer groups, processing counts, replay counts` — plus the §186 git state recorded at T001. (FR-215, FR-201, FR-177)
- [ ] **T911** [P] [US9] Emit `artifacts/acquisition-integration/searxng.json` — the complete §162-PROC A→O result. (FR-214, FR-207)
- [ ] **T912** [P] [US9] Emit `artifacts/acquisition-integration/airbyte.json` — the complete §162-PROC A→O result. (FR-214, FR-207)
- [ ] **T913** [P] [US9] Emit `artifacts/acquisition-integration/maigret.json` — the complete §162-PROC A→O result. (FR-214, FR-207)
- [ ] **T914** [P] [US9] Emit `artifacts/acquisition-integration/bbot.json` — the complete §162-PROC A→O result. (FR-214, FR-207)
- [ ] **T915** [P] [US9] Emit `artifacts/acquisition-integration/spiderfoot.json` — the complete §162-PROC A→O result. (FR-214, FR-207)
- [ ] **T916** [P] [US9] Emit `artifacts/acquisition-integration/redpanda-trace.json` — topic / partition / offset / event_id / observation_id / consumer group / lag / processing result for every event of the acceptance run. (FR-214, FR-124)
- [ ] **T917** [P] [US9] Emit `artifacts/acquisition-integration/replay-report.json` — every replay executed, its new `integration_run_id`, and the identity comparison proving `same observation_id`, `same event_id`, `same parser result`, **zero** network acquisitions. (FR-214, FR-178)
- [ ] **T918** [US9] The acceptance report is **reproducible**: it contains `git commit, image digests, source version, runtime version, schema version, test scenario version`. (FR-201)
- [ ] **T919** [US9] 🔴 **§160 RELEASE-BLOCKER AUDIT** — each of the 16 blockers **explicitly verified absent**, not merely uncomplained-about: `observation_id random` · `event_id random for replay-sensitive events` · `raw artifact absent` · `observation without raw lineage` · `event without canonical EventEnvelope` · `tool bypasses policy` · `tenant information lost` · `investigation_id lost` · `consumer cannot replay` · `pagination loses pages` · `Airbyte STATE treated as evidence` · `donor event written directly to graph` · `secret appears in logs/events` · `live source never actually executed` · `Redpanda path not exercised` · `downstream consumer not exercised`. This test **inverts T009**. §160 is a floor, not a ceiling. (FR-012, SC-018)
- [ ] **T920** [US9] The §159 machine-readable report is emitted: `{"status": "PASS", "sources": {…}}` only if all 30 matrix cells and the eight-factor product are non-zero for all five families; otherwise `{"status":"FAIL","failed_stage":…,"reason":…}`. **A final `PASS` is forbidden if any of the five acceptance paths was replaced by a `mock source`, `fake subprocess`, `fake Kafka`, `fake observation`, `manual DB insert` or `manual topic publication`.** (FR-006, FR-206, SC-013)
- [ ] **T921** [P] [US9] Update `specs/023-acquisition-integration-searxng/quickstart.md` with the single command an operator runs from a clean stack, and record the six open decisions' final answers (O-1…O-6) in the run manifest. (FR-209)

### ✅ Checkpoint 9 — GATE `G9` — the feature's definition of done

**Must be green**: all **8** mandatory artifacts exist on disk under `artifacts/acquisition-integration/` and contain the ids an inspector needs · T919 shows **0 of 16** release blockers · T920 emits `status: PASS` · every live test ran against real infrastructure and none was `skip`/`xfail`/mocked.

**Any failure stays a failure until it is eliminated. The acceptance criteria are never revised down (§161, §204).**

---

## Dependencies & Execution Order

### Wave dependencies

| Wave | Phase | Depends on | Blocks |
|---|---|---|---|
| 0 | Preconditions | — | **everything** |
| 1 | The seam (ACQ-01→02→03→04→05→06→17→18) | Checkpoint 0 | **all five runtimes** |
| 2 | Foundational runtimes (ACQ-07 ‖ 09 ‖ 12) | Checkpoint 1 `G1` | per-runtime specifics |
| 3 | Per-runtime specifics (ACQ-08,10,11,13,14,15) | Checkpoint 2 `G2` | governance |
| 4 | Governance (ACQ-16) | Checkpoint 3 `G3` | live scenarios |
| 5 | Live scenarios (ACQ-19) | Checkpoint 4 `G4` | replay |
| 6 | Replay (ACQ-20) | Checkpoint 5 `G5` | failure journal |
| 7 | Failure journal (ACQ-21) | Checkpoint 6 `G6` | clean-stack acceptance |
| 8 | Clean-stack acceptance (ACQ-22) | Checkpoint 7 `G7` | final artifacts |
| 9 | Final artifacts + release gate | Checkpoint 8 `G8` | — |

### User story dependencies

| Story | Priority | Can start after | Notes |
|---|---|---|---|
| **US1** Canonical seam carries deterministic identity | **P0** | Phase 0 | Blocker for every other story. Nothing downstream is admissible until green. |
| **US2** Dispatch resolves the runtime; real consumer reached | **P0** | `G1.6` | Pairs with US1; the consumer is the *only* thing that makes an event count. |
| **US3** SearXNG page-by-page observations | P1 | `G1` + `G2` (Branch S) | First runtime; cheapest full HTTP path. |
| **US4** Airbyte as a connector execution protocol | P2 | `G1` + `G2` (Branch A) | Not an HTTP source. |
| **US5** Generic external tool runtime runs Maigret | P3 | `G1` + `G2` (Branch T) | First of three tools on one generic runtime. |
| **US6** BBOT events cross a donor-schema bridge | P4 | Branch T green | Second tool. |
| **US7** SpiderFoot CLI JSON becomes observations | P5 | Branch T green | Third tool. |
| **US8** Runtime is sandboxed, governed and bounded | P6 | `G3` | There is nothing to bound until the runtimes exist. |
| **US9** Operator reproduces the whole result from a clean stack | **P7** | every wave | The gate, not a formality. |

Per **§194** the P-number orders **construction sequence only**; it expresses **no relative release weight**. Each of the five families is `BLOCKED until all green` on its own row, and no runtime's acceptance may be satisfied by, substituted for, or inferred from another runtime's green pass.

### Within each phase

- Tests are written and **fail** before implementation (this is mandatory here, not optional).
- Models/identities before services, services before endpoints, core implementation before integration.
- A story is complete — including its live task — before the next priority begins.

### Parallel opportunities

- Phase 0: T007 and T008 touch different `pyproject.toml` files.
- Phase 2: **only** T210 / T220 / T230, the three branch heads. Nothing inside a branch is parallel.
- Phase 3: T340 / T350 / T360 — three separate `ToolDefinition` YAML files.
- Phases 5, 7 and 9: `[P]` marks are confined to genuinely independent artifact or test files.

### The `[P]` discipline, stated once

`[P]` is **not** a throughput hint. A false `[P]` on a Wave 2 or Wave 3 task means a runtime is being built on a seam that has not passed Checkpoint 1 — the exact thing §196 forbids and the exact thing no offline test will catch. If in doubt, the task is not `[P]`.

---

## Parallel Example: Phase 2 branch heads

```text
# Only after Checkpoint 1 (G1) is green. These three may run concurrently:
Task: "T210 — ACQ-07 · SearXNG compose service + settings.yml (image pinning)"
Task: "T220 — ACQ-09 · acq-airbyte compose service (connector images, one docker run per invocation)"
Task: "T230 — ACQ-12 · apps/acquisition/tool_runner/ host-run service (donor: estorides tool_runner.py)"

# Everything inside a branch is serial and NOT [P]:
#   T210 → T211 → T212 → T213 → T214 → T215 → T216 → T217 → T218 → T219
```

---

## Implementation Strategy

### MVP first (the seam — US1 + US2)

1. Complete Phase 0 (preconditions) → Checkpoint 0.
2. Complete Phase 1 (the seam) → **Checkpoint 1**. This is the MVP: a repaired `Capture → Observation → EventEnvelope` path with a real consumer producing a real `derived_ref`.
3. **STOP and VALIDATE**: §160's first, second and fifth blockers are provably absent, and `OBS-…` ids are byte-equal over 100 replays.
4. Do **not** deploy/demo a runtime. There is none.

### Incremental delivery

1. Phase 0 + Phase 1 → foundation ready.
2. Phase 2 + Phase 3 → five runtimes exist, each with offline and live evidence.
3. Phase 4 → they are safe to run.
4. Phase 5 → the five live scenarios are green.
5. Phase 6–8 → replay, failure journal, clean-stack acceptance.
6. Phase 9 → the artifacts and the release gate.

### Parallel team strategy

With multiple developers, parallelism is bounded by the gate structure, not by enthusiasm:

- **Phase 0–1**: one developer. The seam is serial by mandate.
- **Phase 2**: three developers, one per branch (S / A / T). Three-way split, no more.
- **Phase 3**: three developers, one per per-runtime package group.
- **Phase 4–8**: sequential; each wave's gate must be green before the next is staffed.
- **Phase 9**: two developers, artifacts + audit.

---

## FR Traceability — 215 of 215

Ranges are **inclusive**; every FR in a range is covered by the listed tasks. The ranges below are contiguous from FR-001 to FR-215 with **no gap**.

| FR range | § source | Covered by |
|---|---|---|
| FR-001…FR-006 | §0, §0.1, §202 | T140, T514, T515, T516, T517, T518, T536, T719–T721, T920 |
| FR-007…FR-011 | §203, §76, §153, §161 | T004, T520, T711, T714, T718, T920 |
| FR-012 | §160 | T009, T113, T114, T120, T126, T919 |
| FR-013…FR-016 | §3, §118, §119 | T344, T353, T354, T363, T425 |
| FR-017…FR-020 | §112, §113, §114, §115 | T224, T313, T344, T353, T363, T425 |
| FR-021…FR-023 | §60, §58, §59 | T129, T211, T212, T221, T234, T340, T343, T350, T360, T422 |
| FR-024…FR-025 | §5 | T101, T102, T103, T104 |
| FR-026 | §6 | T102, T125, T216, T223, T232, T352, T362 |
| FR-027…FR-031 | §7, §8, §61 | T106, T107, T108, T109, T111, T119, T121, T127 |
| FR-032…FR-042 | §10, §11, §12, §96, §97, §123, §124, §165 | T110, T111, T112, T113, T114, T115, T116, T117, T123, T124, T126, T127, T145, T147, T619 |
| FR-043…FR-048 | §9, §33, §34, §122 | T106, T108, T125, T127, T322 |
| FR-049…FR-058 | §13, §14, §56, §57, §67, §167, §168 | T128, T129, T130, T131, T132, T133, T134, T511, T512, T136 |
| FR-059…FR-074 | §15–§23, §94, §99, §103, §139, §172, §176 | T210, T211, T212, T213, T214, T215, T216, T217, T218, T310, T311, T312, T313, T314, T415, T419, T514, T519, T534, T614 |
| FR-075…FR-096 | §24–§39, §90, §93, §104, §138, §149, §171, §177, §178 | T220–T229, T320, T321, T322, T323, T324, T325, T330, T331, T332, T333, T334, T417, T515, T534, T712 |
| FR-097…FR-099 | §40, §41, §42 | T231, T232, T233, T235, T238, T239, T346, T356, T366 |
| FR-100…FR-106 | §43, §44, §45, §46, §82, §105, §140, §179 | T340, T341, T342, T343, T344, T345, T346, T516, T534, T713 |
| FR-107…FR-113 | §47–§50, §83, §106, §141, §180 | T350, T351, T352, T353, T354, T355, T356, T517, T534, T713 |
| FR-114…FR-121 | §51–§55, §84, §142, §181 | T360, T361, T362, T363, T364, T365, T366, T518, T534, T713 |
| FR-122…FR-132 | §68–§71, §116, §117, §120, §121, §155–§157 | T118, T121, T122, T135, T136, T137, T138, T141, T144, T146, T511, T512, T521, T522, T535, T616, T916 |
| FR-133…FR-137 | §85, §86, §173, §174, §175 | T142, T143, T144, T145, T147, T148, T330, T331, T332, T531, T612, T613, T617, T618, T710 |
| FR-138…FR-144 | §62, §87–§92 | T213, T218, T223, T227, T320, T321, T322, T323, T330, T331, T332, T333, T334, T422 |
| FR-145…FR-152 | §101–§111, §166 | T106, T109, T112, T122, T125, T127, T136, T144, T146, T227, T311, T312, T320, T323, T325, T512, T532, T533, T919 |
| FR-153…FR-164 | §64–§66, §143–§148, §170, §182–§184 | T213, T226, T228, T234, T235, T236, T237, T238, T340, T350, T360, T410, T411, T412, T413, T414, T415, T416, T417, T418, T419, T423, T424, T724 |
| FR-165…FR-183 | §70, §72–§75, §95, §126–§137, §154, §163, §164, §186, §189 | T001, T002, T003, T129, T138, T139, T140, T355, T364, T420, T421, T423, T424, T522, T523, T524, T530, T610, T611, T612, T613, T614, T616, T617, T719, T720, T721, T722, T723, T910 |
| FR-184…FR-192 | §77, §78, §79, §80–§84, §152 | T008, T219, T229, T239, T314, T325, T334, T346, T356, T366, T510, T513, T514, T515, T516, T517, T518, T520, T534 |
| FR-193…FR-198 | §137–§142 | T219, T334, T345, T355, T364, T531, T534 |
| FR-199…FR-201 | §150, §151, §169, §185 | T340, T350, T360, T422, T614, T910, T918 |
| FR-202…FR-208 | §72–§75, §159, §162, §197 | T139, T615, T716, T717, T718, T710, T711, T714, T715, T525–T529, T620, T818, T911–T915, T920 |
| FR-209…FR-215 | §158, §187, §188, §194, §200, §201 | T001, T810, T811, T812, T813, T814, T815, T816, T817, T818, T910, T911, T912, T913, T914, T915, T916, T917, T918, T919, T920, T921 |

### FRs not covered by a task — none

**215 / 215 covered.** No FR was dropped. Three FRs (`FR-021`, `FR-199`, `FR-022`) are *governance* requirements about donor handling rather than code; they are satisfied by T422 (the donor version manifest), by the donor notes carried on every module-creation task, and by T919's audit — not by a line of application code, and saying otherwise would be dishonest.

---

## Work-package coverage — all 22 (`§195`)

| WP | Deliverable | Tasks | Phase |
|---|---|---|---|
| `ACQ-01` | Canonical artifact seam + streaming sink | T101–T104 | 1.1 |
| `ACQ-02` | Capture persistence, first-class `Capture` | T105–T109 | 1.2 |
| `ACQ-03` | Observation Gate repair: random → deterministic | T110–T117 | 1.3 🔴 |
| `ACQ-04` | `EventEnvelope` bridge; remove raw dict publication | T118–T122 | 1.4 🔴 |
| `ACQ-05` | Record seam: `capture_id`, `locator`, `record_digest` | T123–T127 | 1.5 |
| `ACQ-06` | Worker routing: `worker_ref`, `runtime_ref` | T128–T134 | 1.6 / 1.7 |
| `ACQ-07` | SearXNG runtime: health, query, pagination, capture, expansion | T210–T219 | 2 (Branch S) |
| `ACQ-08` | SearXNG JSON validation, explicit fail | T310–T314 | 3 |
| `ACQ-09` | Airbyte runtime: `spec/check/discover/read` | T220–T229 | 2 (Branch A) |
| `ACQ-10` | Airbyte streaming JSONL protocol bridge | T320–T325 | 3 |
| `ACQ-11` | Airbyte state checkpoint, separate from evidence | T330–T334 | 3 |
| `ACQ-12` | `ExternalToolRuntime` generic boundary | T230–T239 | 2 (Branch T) |
| `ACQ-13` | Maigret definition: manifest + argv + output parser | T340–T346 | 3 |
| `ACQ-14` | BBOT definition: JSON event bridge + provenance | T350–T356 | 3 |
| `ACQ-15` | SpiderFoot definition: CLI JSON bridge + event parser | T360–T366 | 3 |
| `ACQ-16` | Sandbox/resource controls | T410–T425 | 4 |
| `ACQ-17` | Redpanda integration: canonical publish + inspection | T134–T141 | 1.7 |
| `ACQ-18` | Downstream observation consumer | T142–T148 | 1.8 |
| `ACQ-19` | E2E live scenarios: five live smokes | T510–T536 | 5 |
| `ACQ-20` | Replay infrastructure: task + observation replay | T610–T620 | 6 |
| `ACQ-21` | Failure journal: machine-readable report | T710–T724 | 7 |
| `ACQ-22` | Clean-stack acceptance | T810–T818 | 8 |
| — | §201 mandatory artifacts + §160 release gate | T910–T921 | 9 |

---

## Notes

- `[P]` = different files, no ordering dependency. Used sparingly and deliberately — see the `[P]` discipline section.
- `[Story]` labels map every task to a user story; every task carries an `ACQ-nn` tag from `input.md` §195.
- Every module-creation task names its donor, or states explicitly that there is **no donor and the note is image pinning**. A task that says "implement X" with no donor note is a defect.
- Tests are **mandatory** here: offline (deterministic, fixture, no network) **and** live (`@pytest.mark.live_integration`) for every story, ordered with the runtime it proves rather than lumped at the end.
- `xfail`, `skip`, `mock`, `monkeypatch`, fake Redpanda and fake source output are forbidden after a real acceptance requirement exists.
- Every 🔴 **LIVE** task runs §162-PROC and records A→O; every live task re-checks infra and never assumes it is up.
- Open decisions **O-1…O-6** (plan.md) are user decisions. T005, T006, T221, T346, T350, T356, T360, T422 and T511 are blocked on them. Do not self-resolve an O-decision.

