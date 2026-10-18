# WP0 — Verified Current-State Audit

**Feature**: 028-closed-research-loop
**Commit**: `608c3ad8f4743e4e729807c903b0364ed571b311`
**Branch**: `main`
**Working tree**: 117 dirty entries at audit time (not committed — this feature's
changes sit alongside whatever was already in flight)
**Date**: 2026-10-13

This document is the evidence base for the specification and plan. Every claim below
was checked against source, not against a prior audit or a task list. Where a claim
could not be verified it says so.

---

## 1. Test baseline — measured, twice

### Before this feature

| Command | Result |
|---|---|
| `pytest apps -q --ignore=bench` | **22 failed, 4273 passed, 27 skipped** — 1097.95s |
| `pytest -q` (repo root) | **831 collection errors**, 6769 collected — 304.19s |
| `bench/tests/test_harness.py` | **collection error** — `ImportError: cannot import name 'harness' from 'bench'` |

The root figure is the important one. A single `pytest` at the repo root reported 831
errors, and **not one of them was ours** — they were vendored third-party checkouts in
`donors/` (sherlock, bm25s, theharvester, user-scanner) and `tmp/`, collected because
the root `pyproject.toml` declared no `testpaths`. The real suite had to be selected by
hand on every run, so "the tests pass" was not a claim anyone could make from a
one-line command.

### After WP-0 + WP-A

| Command | Result |
|---|---|
| `pytest -q` (repo root) | **22 failed, 4288 passed, 27 skipped** — 1166.59s |
| `pytest -q` (from `bench/`) | **2 failed, 21 passed** — 14.11s |

**Net: +15 passing, same 22 failing, zero new failures.** The 15 are the closed-loop
tests added by WP-A. The 22 are the same 22 as before, by name.

### The 22 pre-existing failures, triaged by cause

| Cluster | Count | Common cause | In scope for 028? |
|---|---|---|---|
| `test_evidence_context.py` | 8 | One module. All `test_t03x_*` fail together. | Yes — it is the provenance contract WP-F touches |
| `test_frontier_provenance.py` | 4 | Requires a live Postgres | No — infrastructure, not logic |
| `test_donor_api.py` | 2 | Live backend | No |
| `test_end_to_end_pipeline.py` | 1 | Live backend; traverses dead `Layer0Pipeline` | Yes — see §4 |
| `test_evidence_lineage.py` | 1 | Same module as the 8 above | Yes |
| `test_layer_boundaries.py` | 1 | Architectural guard; needs triage against WP-C | Yes |
| `test_migration_016_forward_only.py` | 1 | Schema drift | No |
| `test_migration_024_...` | 1 | Migration chain | No |
| `test_badges_facade.py` | 1 | Test isolation (class-scoped fixture) | No |
| `test_websearch.py` | 2 | Two independent | No |

**14 of 22 are in three files.** That is a small number of causes, not twenty-two
independent defects — which is why the plan attacks them in three work packages rather
than filing twenty-two tickets.

---

## 2. Capability map — declared / implemented / tested / wired / proven

The single most important column is the last one. The platform's pattern is that code
exists, is unit-tested, is marked done in `tasks.md`, and has no production caller.

| Capability | Declared | Implemented | Unit | Contract | Wired into a live path | Proven end-to-end | Evidence |
|---|---|---|---|---|---|---|---|
| Research loop can reach a terminal state | Y | **Y (WP-A)** | Y | — | Y | **Y (WP-A)** | `loop.py:461-540`, `test_closed_research_loop.py` |
| Obligation ledger | Y | Y | Y | Y | Y | Y | `obligations.py:115`, `postgres_store.py:83` |
| Satisfaction evaluator | Y | Y | Y | — | Y (WP-A) | Y (WP-A) | `engine.py:185` |
| Decision record | Y | Y | Y | — | **N** | **N** | `engine.py:350` — in-memory list, no store method |
| Revision manager | Y | Y | Y | Y | Y | Y | `engine.py:407`, `postgres_store.py:74` |
| `ContextDefinition` (ADR-0028) | Y | **N** | — | — | — | — | Zero code hits; spec/ADR only |
| Incremental invariant reducer | Y (`026-F2-01 [x]`) | Y | Y | — | **N** | **N** | `invariant_reducer.py:170`; only importer is its test |
| Digest-gated revision | Y | **N** | — | — | **N** | **N** | `cc_cursor_materialization.py:104` mints `generation+1` unconditionally |
| Single Observation Gate | Y | **Partial** | Y | Y | **Partial** | N | 3 producers bypass it (§3) |
| Deterministic event id | Y | **N** | — | **N (test pins the bug)** | — | — | `kafka.py:50` `uuid4`; `test_event_envelope.py:77` asserts it |
| One observation-identity scheme | Y | **N** | Y | — | **N** | **N** | 4 derivations (§3) |
| Observation + membership atomic | Y | **N** | — | — | **N** | **N** | Dead writer splits its own txn (`interpretation_bridge.py:368`, `:440`) |
| Captures persisted | Y | **N** | — | — | **N** | **N** | `artifact_sink.py:187` builds one, discards it |
| Parser routing capability-based | Y | **Partial** | Y | Y | Y | N | 3 coexisting routing systems (§3) |
| Exact spans to the finding | Y | **N** | — | — | **N** | **N** | Spans hashed into id, then dropped (`document_adapter.py:271`) |
| Auto-merge requires calibration | Y (`ADR-0014`) | **N** | Y | — | Y (wrongly) | N | `admission.py:139` vs `calibration.py:40` = `"UNCALIBRATED-v1"` |
| `n_eff` / independence | Y | **Y, but unwired here** | Y | Y | Y (in `science`) | N | `admission/independence/` has no non-test importer |
| CURRENT / AS_OF / INTERVAL | Y | **Partial** | Y | — | Y | N | CURRENT is a byte-identical route duplicate; INTERVAL unexposed |
| Graph projection rebuild | Y | **N** | Y | — | **N** | **N** | `snapshot.py:77` replays a process-local list |
| Search projection | Y | **Y** | Y | Y | **Y** | Y | The one projection with a full producer→consumer loop |
| Temporal materialization | Y | Y | Y | Y | Y | Partial | Durable at domain+SQL; features table defaults to memory |
| TDA / topological | Y (`011` all `[x]`) | Y | Y | Y | **N** | **N** | `TopologicalInvariant.run` has no non-test caller |
| Spatial | Y (map in UI) | **N — does not exist** | — | — | — | — | No `h3`, no geometry, no producer; `map_points` has 4 TS hits, 0 backend |
| Vector / semantic retrieval | Y (`mode: hybrid` in API) | **N** | — | — | — | — | `mode` is never passed to the planner |
| Feedback plane | Y (`010` all `[x]`) | Y | Y | Y | **N** | **N** | Zero non-test importers of `apps/feedback` |
| L0 zero capture | Y | Y | Y | Y | **Y** | Y | `cc_temporality.py:41` |
| L1/L2 zero (harvest, FS) | Y | Y | Y | — | **N** | **N** | No deploy target |
| Tenant isolation (storage) | Y | Y | Y | Y | Y | Y | Best-tested surface in the repo |
| Tenant isolation (consumer) | Y | **N** | — | — | — | — | `kafka.py:171` has no `tenant_id` parameter |

### Claims that could not be verified

- Whether the four observation-id schemes are deliberate migration or drift. No ADR or
  spec text reconciles them.
- Whether the 7 `[x]`-but-absent tasks in `specs/027` were completed and then reverted,
  or never implemented. The paths do not exist and git history was not walked for each.
- The 12 assertions in `specs/024/wave0-verified-state.md` about test counts are stale
  relative to today's measured baseline and were not re-verified individually.

---

## 3. The four findings that made this plan

### 3.1 The loop could not close (D1) — fixed in WP-A

`CognitiveLoop.tick` has exactly one production call site:
`services/cycle_service.py:454`, `await self._loop.tick(context, outcomes=outcomes)`.

It passes no `saturation` and no `feedback`. With `saturation=None`, `_reevaluate`
fabricated a basis with a hardcoded `marginal_gain=1.0`. Every threshold the loop ships
with is below 1.0, so `is_saturated` was a constant `False`, so `SatisfactionEvaluator`
never returned satisfied, so **no obligation could ever reach a terminal state**. The
platform's central claim — that it investigates to a conclusion — had no reachable code
path.

The unit tests covered closure. They covered it by passing `saturation=` explicitly, from
tests, which is why 104 tests were green over an inert loop.

### 3.2 The gate has four exits and the identity has four schemes (D3)

Producers that write an observation without the gate:

| Site | What it does |
|---|---|
| `acquisition/sources/connector.py:161` | Builds `observation.created` inline. **No `raw_ref`, no store write.** The event cannot be resolved to bytes. |
| `acquisition/worker_acquisition.py:442` | Publishes the connector's dict verbatim. |
| `control-plane/services/pow_run.py:187` | Writes a `db.schema.Observation` row directly. |
| `zero/observation_gate.py:102` | A second, independent gate. |

Identity derivations:

| Scheme | Material |
|---|---|
| `shared/domain/observation_identity.py:120` | `identity_schema, tenant, capture, locator, digest` — canonical |
| `control-plane/services/interpretation_bridge.py:592` | `tenant \| digest` — drops locator, capture and schema |
| `acquisition/sources/connector.py:28` | `source \| query \| page \| digest` |
| `zero/observation_gate.py:110` | `uuid4()` — **random, on the identity path**, contradicting its own docstring |

### 3.3 The platform edits the edges off its own evidence (D10)

`Segment.offset` means byte offset in `html_full.py:83`, segment index in
`registry.py:247`, and is always `0` in `documents.py:224` — then all three are summed
into one field at `extractors/lane.py:82-86`.

Downstream, `document_adapter.py:271-300` consumes `(offset, end_offset)` to mint
`mention_id` and discards it; `ResolutionMention` has no span field at all. So the
platform records that a mention exists and throws away where in the document it was.

### 3.4 Silent zeros (D7, D12, D13)

- `worker_acquisition.py:312-314`: `getattr(artifact, "observation_id", "") or ""`
  followed by `continue`. `AcquisitionArtifact` has no such field, so the value is always
  empty and **every runtime artefact is dropped, uncounted**.
- `search.py:52` accepts `mode: hybrid`; `query_planner.plan` has no mode parameter.
  The API accepts a capability it does not have.
- The TDA plane has no production caller and persists nothing.
- `science_tantivy_backend.py` is 22 lines, defines no class, and its test is permanently
  skipped by `importorskip("tantivy")` for a package that is not a declared dependency.

---

## 4. Dead and unwired code — the honest inventory

| Component | Status | Note |
|---|---|---|
| `services/layer0_pipeline.py` | **dead** | Only importers are tests, 4 of which fail |
| `services/acquisition_loop.py` | **dead** | Importer is the dead pipeline above |
| `services/interpretation_bridge.py` | **dead** | Zero importers including tests; it is also the only atomic writer, and it splits its own transaction |
| `services/pow_run.py` | **dead** | Zero importers; also a gate bypass |
| `apps/feedback/**` | **test-only** | Zero non-test importers anywhere in the tree |
| `apps/specops/**` | **test-only** | Routers mounted, but every registry is a module-level dict lost on exit |
| `context_engine/invariant_reducer.py` | **test-only** | 33 passing tests, no caller |
| `context_engine/context_graph_store.py` | **test-only** | `PostgresContextGraphStore` imported by nothing |
| `projection/tda/**` | **test-only** | The bridge's own docstring admits it |
| `apps/zero` L1/L2 | **test-only** | Only `cc_capture` is wired |
| `services/capture_interpretation.py` | **live** | The one real ingestion path |

### Specifications that over-claim

| Spec | Claim | Reality |
|---|---|---|
| `027` T017, T018, T019, T020, T025, T026, T051 | `[X]` on 7 tasks | 6 claimed files do not exist; the 7th (`vendor/`) exists but is empty |
| `026` F4-01..03, F2-01, F1-06, F3-01..05 | `[x]` | Every one is test-only |
| `011` T3-01..T3-04, T4-01 | `[x]` TDA | No non-test importer of `projection/tda` |
| `010` T100–T132 | `[x]` zero layer | No non-test importer of L1/L2 |
| `024` §8.2 "5 323 tests" | — | Measured 4 336 collected, 4 288 passing |

### Documentation defects

| Document | Defect |
|---|---|
| `AGENTS.md` | 30+ citations across specs for a "donor reuse is the default" doctrine. `rg -i donor AGENTS.md` → **0 matches**. The doctrine is documented nowhere it is cited from. |
| `docs/README.md:102` | "26 ADRs". `docs/adr/` holds **38**. |
| `README.md:43` | `core` profile contains kafka. Compose puts kafka in `legacy-kafka` and redpanda in `core`. |
| `.specify/feature.json` | `docs/README.md:120` says it exists; it did not until WP-0 created it. |
| `specs/025/tasks.md` | 11 ADRs marked OPEN; the ADR files say Accepted. |

---

## 5. What changed in this session

| File | Change |
|---|---|
| `context_engine/obligations.py` | `SaturationState` gains `coverage_known`, `marginal_gain_known`, `required_independent_sources`, `required_source_families`. Defaults preserve every prior construction bit-for-bit. |
| `context_engine/fabric_bridge.py` | `to_engine_saturation()` — one translation point from the fabric's verdict to the engine's language; unknown stays unknown. |
| `context_engine/loop.py` | The 1.0 placeholder is gone. Basis selection: supplied → fabric pass → what the outcomes actually reported. Stop reason on every terminal path. |
| `services/cycle_service.py` | `TickReport.loop_status` and `.stop_reason`; the legacy `saturated` field no longer reports the previous pass. |
| `pyproject.toml` | `testpaths` + `norecursedirs`. |
| `conftest.py` | `bench/` on the path. |
| `bench/__init__.py` | **Deleted.** 2 bytes, imported by nothing, and it shadowed the real package. |
| `tests/integration/test_closed_research_loop.py` | 15 new tests. |

### Why `bench` is not in the root `testpaths`

Measured, not preferred. Adding it reproduces two different failures depending on the
rest of the command line: collected alone it works; collected alongside `apps/…` it
fails with `cannot import name 'harness' from 'bench' (unknown location)`, because
pytest has already installed a namespace placeholder for `bench` in `sys.modules` and a
namespace package cannot be corrected afterwards. Both trees are legitimate; they cannot
share one collection root. The bench suite runs from its own workspace member.

### Verifying the claims in this feature

| Claim | Command | Result |
|---|---|---|
| Root suite collects cleanly | `pytest --co -q` | 4336 collected, **0 collection errors** |
| No regression | `pytest -q` | 22 failed (same 22), 4288 passed, 27 skipped |
| The loop closes | `pytest apps/control-plane/tests/integration/test_closed_research_loop.py` | **15 passed** |
| Bench suite | `pytest -q` from `bench/` | 2 failed, 21 passed |

The 2 bench failures (`test_donor_code_extracted_benchmarks_present`,
`test_donor_round2_benchmarks_present`) assert metrics the donor benchmark scenario does
not emit. They were invisible before WP-0 because the module could not be imported at
all. Fixing the blocker revealed a real gap; it is recorded rather than suppressed.

---

## 6. What is deliberately not claimed

- No claim is made that the platform now closes its loop **in production**. The WP-A
  proof runs against the in-memory store with real `CognitiveLoop` and real
  `ContextEngine` objects. `PostgresContextStore` is untouched by it, and the audit
  found `postgres_store.py:572` calls `ActionMemoryEntry.from_dict`, which does not
  exist — so `propose_action` against the real store raises `AttributeError`. That is
  WP-C work and it is not fixed.
- No claim is made about any donor's runtime behaviour. Nothing was integrated.
- No benchmark numbers are reported, because no benchmark was run. §11 of the
  specification requires a reproducible baseline and one does not yet exist for
  retrieval quality, false-merge rate or cost per grounded finding.