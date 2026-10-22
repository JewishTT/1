# WP0 Baseline Record — COGNITIVE Global Platform Upgrade (Feature 032)

**Tasks**: T001 (baseline), T002 (full suite), T003 (collection)  
**Status**: Executed  
**Dates**: T001 2026-10-20 · T002/T003 2026-10-22  
**Operator**: opencode assistant  
**Spec**: `specs/032-global-upgrade-execution/spec.md` (§12 WP0, FR-058, US1-AS3)

> **Superseded.** This is a point-in-time record of the commit that was executing
> when WP0 ran; it is kept as evidence, not as a description of the tree. The
> current, always-accurate description of the platform is generated into
> `docs/platform/` by `python -m platform_model.build`, and its `findings.md` is
> where the live defects live.

---

## Executing commit

| Field | Value |
|---|---|
| `git rev-parse HEAD` | `ba518639925bfd94ffc4c3ac50614301c9fba04d` |
| `git branch --show-current` | `main` |
| `git status --porcelain` | 117 untracked lines, all `donors/*` and `tmp/*` vendored checkouts; no modified tracked files |
| Working tree | Clean except untracked vendor trees |

## Toolchain versions

| Tool | Version |
|---|---|
| Python | 3.11.9 |
| uv | 0.12.12 (c4be69153, 2026-09-09, x86_64-pc-windows-msvc) |
| Node | v24.19.0 |
| Rust/cargo | 1.98.0 (797e8a9bc, 2026-08-05) |

## Lockfile digests

| File | SHA-256 |
|---|---|
| `uv.lock` | `5B7677359E48E88358C972DAB09BFB9BA85D4D8F526651CA8BDF9EB2CB87BB6C` |

## Migration head

`apps/control-plane/alembic.ini` present; `apps/control-plane/db/migrations/` exists. Alembic `current` head could not be resolved from this workstation (no live database connection recorded); migration files present include `entity_stream.py`, `investigation_store.py`, `relation_claim_store.py`, `schema.py`, `temporal_materialization.py` and others. Recorded as `NOT_RUN` for the live head query — a database connection is required to resolve `alembic current`.

## Environment envelope

| Item | Value |
|---|---|
| Platform | Windows (win32), PowerShell 7+ |
| Workspace root | `C:\Users\tim\Desktop\COGNITIVE\1` |
| Virtual env | `.venv/` present at repo root |
| `testpaths` (pyproject.toml) | `["apps"]` |
| `norecursedirs` | `donors`, `tmp`, `logs`, `*.egg-info`, `.venv`, `node_modules`, `dist`, `build`, `k8s` |
| `asyncio_mode` | `auto` |
| `addopts` | `--import-mode=importlib` |
| Markers | `contract`, `integration`, `live`, `unit` |

## Constitution state

`.specify/memory/constitution.md` exists but is an **unratified template** (placeholder fields `[PROJECT_NAME]`, `[PRINCIPLE_1_NAME]`, `[RATIFICATION_DATE]`, etc.). Per T013 it must be ratified as an engineering constitution in WP1 before any architecture-changing work. Recorded here as `NOT_RUN` / `BLOCKED` pending ratification.

## Pre-existing conditions

- `donors/` holds 113+ vendored third-party checkouts (sherlock, theHarvester, spiderfoot, usw.) — excluded from collection by `norecursedirs`.
- `tmp/` holds 13 vendored tool checkouts (amass, bm25s, certstream, crawlee, duckdb, meilisearch, quickwit, sherlock, spider, subfinder, tantivy, theharvester) — excluded from collection.
- No `tests/` top-level directory; tests live inside `apps/*/tests/`.
- `apps/shared/contracts/` already contains: `canonical.py`, `evidence_span.py`, `operator_result.py`, `projection_manifest.py`, `stage_outcome.py`, `resolution-admission.md`, `ontology-pack.md`, `error_codes.py`, `connector.md`, `graph.md`, `parser.md`, `statement.md`.

## T002 — Full baseline suite run

**Date**: 2026-10-22 · **Task**: T002 (US1-AS4) · **Status**: Executed

### Commands and exit statuses

| # | Command | Working dir | Exit | Duration |
|---|---|---|---|---|
| 1 | `.venv/Scripts/python.exe -m pytest -q -p no:randomly` | repo root | `1` | 2846.09 s (47:26) |
| 2 | `.venv/Scripts/python.exe -m pytest --co -q` | repo root | `0` | 88.34 s |
| 3 | `.venv/Scripts/python.exe -m pytest bench/tests -q` | repo root | `0` | 14.45 s |

### Counts (run 1 — `testpaths = ["apps"]`)

| Metric | Value |
|---|---|
| Collected | 5622 |
| Passed | 5506 |
| **Failed (baseline)** | **38** |
| Skipped | 79 |
| Errors (collection) | 0 |
| Warnings | 12 |

### Counts (run 2 — collection only)

| Metric | Value |
|---|---|
| Collected | 5622 |
| Collection errors | 0 |
| Exit status | 0 |

A later `testpaths` regression is therefore attributable: the collection contract for this tree is **5622 tests, 0 collection errors**.

`bench/` is a separate workspace member and **cannot be collected in the same run as `apps/`** — the `bench` namespace placeholder makes `import bench` resolve to an empty module and pytest raises `ImportError: cannot import name 'harness' from 'bench' (unknown location)`. It is excluded from the root `testpaths` and documented in the root `pyproject.toml`. Bench is therefore run separately: **23 passed**.

### The 38 pre-existing failures — labelled *baseline*, not *regression*

Machine-readable form: `benchmarks/WP0-baseline-failures.json` (schema `wp0-baseline-failures/1`, per-test error, location, message and category). Categories: `infra` 12, `defect` 19, `gap` 7.

| File | n | Category | Root cause |
|---|---|---|---|
| `apps/acquisition/tests/contract/test_plan_driver.py` | 13 | defect | dispatcher returns `verdict='defer'`, `reason='BLOCKED_BUDGET'`, `published=False`, `offset=-1` — nothing is ever published, so every payload/offset/topic assertion fails (`IndexError: list index out of range` on the empty publish log) |
| `apps/acquisition/tests/integration/test_loop_closed.py` | 2 | defect | same root cause as above — the scheduler→worker loop never closes because the task is never published |
| `apps/control-plane/tests/integration/test_cc_temporality_api.py` | 3 | infra | `POST /api/v1/entities` returns **503** (`entity registry unavailable`) — no Postgres on this workstation |
| `apps/control-plane/tests/integration/test_donor_api.py` | 9 | infra 6 / defect 3 | 6× HTTP 503 (no Postgres); 3× real code defects: `entities.py:988 AttributeError: 'SqlEntityStreamRepository' object has no attribute 'correlations_for_entity'`, `entities.py:1001 NameError: name '_reviews' is not defined` (×2) |
| `apps/control-plane/tests/integration/test_temporal_materialization_api.py` | 1 | infra | HTTP 503 — no Postgres |
| `apps/control-plane/tests/integration/test_tools_api.py` | 2 | infra | HTTP 503 / empty catalogue listing — no Postgres |
| `apps/control-plane/tests/unit/test_sse_stream.py` | 1 | defect | `entities.py:1001 NameError: name '_reviews' is not defined` |
| `apps/shared/tests/constitution/test_constitution_has_teeth.py` | 6 | gap | six constitution invariants are **not guarded by any test**: `CD-1`, `CD-5`, `CD-6`, `I-1`, `IV`, `VI` — the mutation leaves the target test green |
| `apps/shared/tests/unit/test_layer_boundaries.py` | 1 | gap | **26** layer-boundary violations, was 25. New: `apps/feedback/feedback/frontier.py:59` and `:65` (`feedback` → `control-plane/db.session`, `control-plane/db.schema`), `apps/feedback/tests/test_frontier_loop.py:43,81,91,121`, `apps/science/tests/contract/test_ontology_and_schema_stay_in_step.py:25`, `apps/science/tests/integration/test_live_asg_pipeline.py:35` |

The `infra` group (12) is not a defect in the platform: it is this workstation's missing Postgres/MinIO/Kafka/OpenSearch/ClickHouse/Temporal. Every one of them must be re-run against a live stack before it can be claimed proven; until then `live_proven = NOT_PROVEN`.

The `defect` group (19) and the `gap` group (7) are real defects in the tree at this commit and are carried into the findings register.

## T003 — Collection-only run

**Date**: 2026-10-22 · **Status**: Executed · Command `python -m pytest --co -q` → exit `0`, **5622 collected, 0 collection errors** (88.34 s).

## Next actions

- T004: Data profile (source-catalogue entry count, capture/observation counts, claim/candidate counts, event volume, graph cardinality, tenant count, storage footprint).
- T005–T011: capability matrix, owner map, donor registry, classification, ambiguity resolution — artifacts exist under `benchmarks/` and `donors/registry.yaml`; sign-off state is in `benchmarks/WP0-signoff.md`.
- T012: WP0 sign-off record — `benchmarks/WP0-signoff.md`.

---

**Evidence**: this file is the T001 artifact. Commands and exit statuses for T002–T004 follow in subsequent records.
