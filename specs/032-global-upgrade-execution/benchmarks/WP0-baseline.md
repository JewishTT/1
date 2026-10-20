# WP0 Baseline Record — COGNITIVE Global Platform Upgrade (Feature 032)

**Task**: T001 — Record the executing baseline  
**Status**: Executed  
**Date**: 2026-10-20  
**Operator**: opencode assistant  
**Spec**: `specs/032-global-upgrade-execution/spec.md` (§12 WP0, FR-058, US1-AS3)

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

## Next actions

- T002: Run the full baseline suite from repo root; record command, exit status, pass/fail/skip/error counts; label pre-existing failures as *baseline*.
- T003: `pytest --co -q` collection count and errors.
- T004: Data profile (source-catalogue entry count, capture/observation counts, claim/candidate counts, event volume, graph cardinality, tenant count, storage footprint).
- T005–T011: capability matrix, owner map, donor registry, classification, ambiguity resolution.
- T012: WP0 sign-off record (gate for WP1+).

---

**Evidence**: this file is the T001 artifact. Commands and exit statuses for T002–T004 follow in subsequent records.
