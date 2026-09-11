# Quickstart / Validation Guide: Donor Code Integration

**Date**: 2026-09-08 | **Feature**: [spec.md](spec.md)

Validation guide proving the three adapted donor modules work end-to-end.
Entry points and expected outcomes only; see [data-model.md](data-model.md)
for shapes, [tasks.md](tasks.md) for implementation.

## Prerequisites

- Repo root `C:\Users\tim\Desktop\COGNITIVE`, uv workspace, Python ≥3.12.
- Baseline green before starting: shared 77+, admission 37, bench 18.
- Donor clones must be present under `donors/` (OpenOSINT, FollowTheMoney,
  NetForensicAI).

## Validate per module

### 1. Correlation graph (OpenOSINT)

```bash
uv run --project apps/shared pytest apps/shared/tests/unit/donor/test_correlation_graph.py -q
```

Expect:
- Identity dedup: adding the same node twice yields one node.
- Non-merge: `possible_match` edges exist but no merge is triggered.
- Exports valid: `to_json` produces valid D3 node-link; `to_graphml` parses;
  `to_mermaid` is well-formed; `summary` counts are deterministic.

### 2. Statement provenance (FollowTheMoney)

```bash
uv run --project apps/shared pytest apps/shared/tests/unit/donor/test_statement.py -q
```

Expect:
- `make_key()` is deterministic across calls (same dataset/entity/prop/value).
- `lang` and `ext` compose into the key deterministically.
- `original_value` collapse (e.g. "ACME GmbH" vs "acme") preserves original.
- `from_dict`/`to_dict` round-trip preserves all fields.
- `to_db_row` produces a flat dict for persistence.

### 3. Evidence vault (NetForensicAI)

```bash
uv run --project apps/shared pytest apps/shared/tests/unit/donor/test_evidence.py -q
```

Expect:
- `ingest` → creates `manifest.json` + read-only stored file.
- `load` verifies; tampered file → hash mismatch, returns None.
- `list` skips corrupt manifest entries.
- Missing source file raises a clear error.
- `evidence_id` sequence increments.

## Pipeline integration validation

### Correlation graph → admission resolution

```bash
uv run --project apps/admission pytest apps/admission/tests/test_collective_export.py -q
```

Expect: `CorrelationService.export_graph()` builds a `CorrelationGraph` from
`CorrelationEdge`s and returns `{"node_link": {...}, "mermaid": str}`.

### Statement + evidence → bench harness

```bash
uv run --project apps/bench pytest bench/tests/test_harness.py -q
```

Expect:
- `bench_donor` includes statement `make_key` latency scenario.
- Evidence ingest + verify throughput scenarios emit
  `evidence_ingest_per_s`, `evidence_verify_per_s`.

## Full regression gate

```bash
# Python suites
uv run --project apps/shared pytest apps/shared/tests -q
uv run --project apps/admission pytest apps/admission/tests -q
uv run --project apps/bench pytest bench/tests -q
# Lint
uvx ruff check apps/shared/donor apps/admission/resolution bench/bench/harness.py
```

Expected:
- shared ≥77 (new donor tests add on top), admission ≥37, bench ≥18.
- `ruff check` clean on all touched Python.
- Attribution header present (FR-001), license gate verified, on every
  adapted module.
