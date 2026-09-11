# Quickstart / Validation Guide: Full Donor Coverage

**Date**: 2026-09-08 | **Feature**: [spec.md](spec.md)

Validation guide proving the four remaining donor modules work end-to-end.
See [data-model.md](data-model.md) for shapes, [tasks.md](tasks.md) for
implementation.

## Prerequisites

- Repo root `C:\Users\tim/Desktop/COGNITIVE`, uv workspace + pnpm.
- Track 003 must be complete (donor package scaffold exists).
- Baseline green before starting: shared 77+, admission 37, bench 18,
  webapp ≥26.

## Validate per module

### 1. Temporal conflict detection (investigator, MIT)

```bash
uv run --project apps/shared pytest apps/shared/tests/unit/donor/test_temporal.py -q
```

Expect:
- Spread conflict: dates spanning more than `tol_days` (30) return a conflict
  record with min/max/daysApart.
- Ordering conflict: an `event_followed_by` edge whose later endpoint is
  attested before the earlier one by > 30 days is flagged.
- Year-only dates never produce conflicts.
- `dates_compatible(a, b, window_days)` returns correct bool.
- `to_iso_date` handles RFC-2822, GDELT, and ISO formats.

### 2. Target normalization (SpiderFoot, MIT logic)

```bash
uv run --project apps/shared pytest apps/shared/tests/unit/donor/test_target.py -q
```

Expect:
- Mixed-case hostname with trailing dot → canonical lower-case domain without
  trailing dot.
- URL string → inferred `URL` / `DOMAIN` type with hostname as target.
- IPv4/IPv6 literal → canonical IP address (no leading zeros, shortened ranges).
- Email → lowercased local@domain.
- Invalid inputs rejected gracefully (no unhandled exception).

### 3. Link kind styling (kafSIEM, Apache-2.0)

```bash
cd apps/webapp && pnpm vitest run src/lib/donor/links.test.ts
```

Expect:
- `linkLabel`/`linkColor`/`linkStyle` return correct values per LinkKind.
- Unknown link kind → safe default (no crash).

### 4. Confidence + relationship typing (vitni, Apache-2.0)

```bash
cd apps/webapp && pnpm vitest run src/lib/donor/confidence.test.ts src/lib/donor/relationshipTypes.test.ts
```

Expect:
- `confidenceBadgeClass` / `formatConfidenceLabel` return correct values per
  Confidence.
- `lookupRelationshipType` returns registry entry or safe default for unknown
  id.

## Consumer integration validation

### Temporal conflicts → admission resolution export

```bash
uv run --project apps/admission pytest apps/admission/tests/test_collective_temporal.py -q
```

Expect: `CorrelationService.export_graph(conflict_days=30)` includes temporal
conflict data in the export summary.

### Target normalization → bench harness

```bash
uv run --project apps/bench pytest bench/tests/test_harness.py -q -k "temporal or target"
```

Expect:
- `bench_donor` includes temporal `scan` latency + correctness metric.
- Target classification/normalization latency + correctness scenario.

### Link kind styling → GraphPanel

```bash
cd apps/webapp && pnpm vitest run --reporter=verbose
```

Expect: GraphPanel and LineageWalker tests pass with styled edges and
confidence badges.

## Full regression gate

```bash
# Python suites
uv run --project apps/shared pytest apps/shared/tests -q
uv run --project apps/admission pytest apps/admission/tests -q
uv run --project apps/bench pytest bench/tests -q
# TypeScript
cd apps/webapp && pnpm vitest run
# Lint
uvx ruff check apps/shared/donor apps/admission/resolution bench/bench/harness.py
```

Expected:
- shared ≥111, admission ≥39, bench ≥19, webapp ≥26.
- `ruff check` clean on all touched Python; `tsc` + vitest clean on webapp.
- Every extracted module is referenced by a consumer (grep-verified).
- Attribution header present (FR-001) on all four adapted modules.
