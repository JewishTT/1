# Quickstart: Scientific Intelligence Fabric

**Date**: 2026-09-09 | **Feature**: [spec.md](spec.md)

Validation guide proving US1–US7 work end-to-end. Entry points and expected outcomes only;
see [data-model.md](data-model.md) and [contracts/](contracts/interface-contracts.md) for
shapes, [tasks.md](tasks.md) for implementation.

## Prerequisites

- Repo root `C:\Users\tim\Desktop\COGNITIVE`, uv workspace, Python ≥3.11.
- Baseline green before starting: `shared` 144, `admission` 41, `projection` 20, `webapp` 43;
  new suite: `science` (grows with this track).
- `apps/science` is a workspace member (root `pyproject.toml` `[tool.uv.workspace] members`).

```pwsh
uv run --project apps/science pytest
uvx ruff check apps/science apps/webapp/src/lib/science apps/webapp/src/pages/SciencePage.tsx
```

## Validate per user story

### 1. Claims + calibration + provenance (US1)
```pwsh
uv run --project apps/science pytest apps/science/tests -k "claim or calibration"
```
Expect: registering a claim with full provenance succeeds and emits
`science.claim.registered`; a claim with empty provenance is rejected
(ProvenanceRequiredError); unknown probability method → UnknownModelError (no fabricated
probability); calibration harness returns decile buckets + Brier + ECE and labels a synthetic
overconfident model `OVERCONFIDENT`.

### 2. Hypotheses + information gain + coverage (US2)
```pwsh
uv run --project apps/science pytest apps/science/tests -k "hypothesis or gain or coverage"
```
Expect: proposing two competing hypotheses yields both alive; attaching evidence updates
credences only through the claims layer; planner returns opportunities ranked by expected
KL information gain over alive hypotheses only; discarding without a DecisionRecord is
rejected; coverage per project computable.

### 3. Causal + scope boundary (US3)
```pwsh
uv run --project apps/science pytest apps/science/tests -k "causal or scope"
```
Expect: correlated inputs without a model → `CORRELATIONAL` with candidate confounders; with a
declared model → `CAUSAL` carrying confounders+assumptions; any person-level sensitive
outcome → `ScopeBoundaryError` + `science.causal.scope_rejected` audit, with NO computation.

### 4. Temporal + change-point + supersede (US4)
```pwsh
uv run --project apps/science pytest apps/science/tests -k "temporal or changepoint"
```
Expect: UTC-normalized series preserve originals; injected discontinuity detected with
confidence and segment summaries; reprojection produces a new version linked `SUPERSEDES`
while the prior stays queryable.

### 5. Structure + null significance (US5)
```pwsh
uv run --project apps/science pytest apps/science/tests -k "structure or null"
```
Expect: bounded spectral/centrality scores normalized to documented range; motif counts come
with permutation-null significance; graph exceeding the budget returns `DEFERRED` with
budget+sample plan (no truncated guess).

### 6. Robustness + reproducible experiments (US6)
```pwsh
uv run --project apps/science pytest apps/science/tests -k "robustness or experiment or reproduction"
```
Expect: perturbation over missing/flip/subsample families reports flip rates per family; null
distribution, observed statistic and comparison stored; re-running identical seeds+versions
reproduces within tolerance and logs a reproduction event.

### 7. Scientific review UI + ladder gating (US7)
```pwsh
npm test -- --run         # webapp SciencePage/HypothesesPage/ExperimentContainer tests
npx tsc -b
```
Expect: claims with full provenance render on the evidence ladder; claims missing
calibration/robustness render `REVIEW_PENDING` and cannot reach the top rung; review comments
and status transitions persist and render inline.

## End-to-end smoke

```pwsh
uv run --project apps/science pytest           # full science suite
uv run --project apps/shared pytest            # envelope/topics still green (science.* topics added)
uv run --project apps/admission pytest         # dependents untouched
npm test -- --run && npx tsc -b                # webapp green with science pages
```

## Full regression gate (acceptance)

- `science` suite grows to cover US1–US7 (no fixed floor yet; >0 per story required).
- `shared` ≥144, `admission` ≥41, `projection` ≥20, `webapp` ≥43 — all either grow or remain green.
- `ruff check` clean on all touched Python; `npx tsc -b` clean.
- Hard boundary verified by test: person-level sensitive outcome requests return
  `422 scope_refused` and emit audit — every science entry point guarded via `ensure_scoped`.
- No fabricated confidence: every registered claim's method resolves to a declared model;