# Quickstart: Donor Core Subsystems

**Date**: 2026-09-08 | **Feature**: [spec.md](spec.md)

Validation guide proving the five subsystems work end-to-end. Entry points and
expected outcomes only; see [data-model.md](data-model.md) and
[contracts/](contracts/interface-contracts.md) for shapes, [tasks.md](tasks.md) for implementation.

## Prerequisites

- Repo root `C:\Users\tim\Desktop\COGNITIVE`, uv workspace, Python ≥3.12.
- Baseline green before starting: `shared` 144, `admission` 41, `bench` 20, `webapp` 43.

```pwsh
# run a whole app's suite from repo root
uv run --project apps/shared pytest
uv run --project apps/admission pytest
uv run --project apps/bench pytest
# lint of touched paths
uvx ruff check apps/shared/domain apps/interpretation/evidence apps/admission/resolution apps/acquisition/registry.py apps/control-plane/domain
```

## Validate per subsystem

### 1. Knowledge Model (FTM)
```pwsh
uv run --project apps/shared pytest apps/shared/tests/unit/ -k "entity or statement or schema"
```
Expect: statement round-trip preserves provenance/dataset/temporal; unknown `schema_name`
raises; missing provenance raises `StatementProvenanceError`.

### 2. Resolution candidates + non-destructive merge (OpenOSINT)
```pwsh
uv run --project apps/admission pytest apps/admission/tests -k "candidate or resolution"
```
Expect: two indicative entities yield a Candidate with deterministic `pair_key`; accept
produces a ResolutionRecord keeping both source entities queryable; reject is preserved with
reasons and not re-proposed; reverse records a new state.

### 3. Parser + evidence manifest (NetForensicAI)
```pwsh
uv run --project apps/interpretation pytest apps/interpretation/tests -k "manifest or parser"
```
Expect: a registered adapter's parse yields Finding; manifest chains
`Finding → Evidence → Observation → Raw(sha256)`; oversized input raises and is quarantined,
never parsed.

### 4. Connector module registry (SpiderFoot)
```pwsh
uv run --project apps/acquisition pytest apps/acquisition/tests -k "connector or registry"
```
Expect: two dummy modules register; a scan pushes events on the shared channel; stop is prompt;
a faulting module is contained (task quarantine) while others continue; events normalize to the
existing canonical target via `shared/donor/target.py`.

### 5. Investigation monitor (investigator)
```pwsh
uv run --project apps/control-plane pytest apps/control-plane/tests -k "monitor or investigation"
```
Expect: counters advance atomically; snapshot persists on close; a late event after COMPLETED
is parked (dead-letter) and state is not mutated.

## End-to-end smoke

```pwsh
uv run --project apps/bench pytest           # bench harness still green (FR-008 gate: bench-only is NOT a consumer; these are pipeline-level tests)
uv run --project apps/admission pytest -k collective
uv run --project apps/shared pytest
```

## Full regression gate (acceptance)

- shared ≥144 (new model/statement/ontology tests add on top)
- admission ≥41
- bench ≥20
- webapp ≥43 (untouched this track)
- `ruff check` clean on all touched Python
- Attribution header present (FR-001), license gate verified, on every adapted module