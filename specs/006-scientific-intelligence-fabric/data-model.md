# Data Model: Scientific Intelligence Fabric

**Date**: 2026-09-09 | **Feature**: [spec.md](spec.md)

## 1. ScientificClaim

A probabilistic statement about a structure or process, carrying a declared probability
source and a full provenance chain. Lives in `apps/science/claims/model.py`.

| Field | Type | Notes |
|-------|------|-------|
| `claim_id` | str | deterministic, `SC-` prefixed. |
| `project_id` | str | owning investigation/project. |
| `statement` | str | the claim text (structural or process claim; NEVER a person-verdict). |
| `distribution` | CredenceDistribution | probability over states (below). |
| `status` | enum | `DRAFT \| CONFIRMED \| WEAKENED \| DISCARDED \| UNCERTAIN` (FR-001). |
| `model_id` | str | declared method id + version (`model_id@version`), FR-001. |
| `provenance` | list[EvidenceLink] | chain `Claim → EvidenceLink → Observation → Raw` (FR-001/II). |
| `producer_run` | str \| None | `ExperimentRun.run_id` that produced this claim (US6 cross-link). |
| `ladder_rung` | int \| None | evidence-ladder position (US7); `None` = `REVIEW_PENDING`. |
| `review_state` | enum | `REVIEW_PENDING \| IN_REVIEW \| CONFIRMED \| DISCARDED` (derived, US7). |
| `timestamps` | dict | created / updated (UTC; original precision preserved). |

Validation: `distribution.method` must be resolvable to a declared model —
`UnknownModelError`; empty provenance → registration rejected (FR-001). Person-level
sensitive `statement` content → `ScopeBoundaryError` at registration.

## 2. CredenceDistribution

| Field | Type | Notes |
|-------|------|-------|
| `states` | list[str] | the states the distribution ranges over. |
| `labels` | list[str] | human-readable state labels. |
| `probs` | list[float] | probabilities (sum ≈ 1; never fabricated, FR-002). |
| `method` | str | declared method id + version that produced `probs`. |
| `calibration_ref` | str \| None | `CalibrationReport.report_id` for the producing model. |

Relationships: produced by `ScientificClaim.distribution`; referenced by
`Hypothesis.credence` (derived, not duplicated).

## 3. Hypothesis (US2)

Competing explanatory statement with lifecycle and direction-tagged evidence.

| Field | Type | Notes |
|-------|------|-------|
| `hypothesis_id` | str | `HY-` prefixed. |
| `project_id` | str | owning project. |
| `text` | str | the hypothesis statement. |
| `status` | enum | `PROPOSED \| ACTIVE \| STRENGTHENED \| WEAKENED \| DISCARDED \| CONFIRMED \| RESOLVED` (FR-004). |
| `credence` | CredenceDistribution \| None | derived from linked evidence via claims (US1 precedence). |
| `evidence_links` | list[EvidenceLink] | direction `supports \| refutes \| discriminates` (FR-004). |
| `decisions` | list[DecisionRecord] | append-only; discards require who/when/why (SC-003). |
| `gain_priority` | float \| None | last expected information gain (US2 planner). |
| `coverage` | CoverageRecord \| None | requirement coverage mapping (FR-005). |

Validation: discard without a `DecisionRecord` → `DecisionRequiredError`. Dead hypotheses
have `gain_priority = None` (no collection pull).

## 4. EvidenceLink

| Field | Type | Notes |
|-------|------|-------|
| `link_id` | str | deterministic. |
| `observation_id` | str | immutable observation reference. |
| `raw_sha256` | str | content-addressed raw (Constitution I). |
| `direction` | enum | `supports \| refutes \| discriminates`. |
| `weight` | float | US1-calibrated weight (never a bare guess). |
| `attached_at` | datetime | UTC. |

Relationships: attached to claims (provenance) and hypotheses (evidence); never edited or
deleted (append-only, FR-015).

## 5. CalibrationReport (FR-003)

| Field | Type | Notes |
|-------|------|-------|
| `report_id` | str | `CL-` prefixed. |
| `model_id` | str | model being calibrated. |
| `buckets` | list[dict] | per-decile observed-vs-expected frequencies. |
| `brier` | float | aggregate Brier score. |
| `ece` | float | expected calibration error (m=10). |
| `verdict` | enum | `CALIBRATED \| OVERCONFIDENT \| UNCALIBRATED`. |
| `thresholds` | dict | the config used (ECE threshold, mean-conf/accuracy tolerance). |

Relationships: produced per model; referenced by claims and hypotheses; immutable.

## 6. CausalModel (US3)

| Field | Type | Notes |
|-------|------|-------|
| `model_id` | str | |
| `graph` | dict | directed influence structure (nodes → parent sets). |
| `confounders` | list[str] | explicitly named and controlled confounders (FR-006). |
| `assumptions` | list[str] | stated assumptions. |
| `scope_decl` | set[str] | allowed outcome attribute classes (structural/systemic only). |

Validation: no scope class for person-sensitive attributes may be declared
(political-affiliation, illegal-activity-involvement, marginalized-group-membership are
hard-excluded); a scoped-out outcome → `ScopeBoundaryError` before any computation (FR-007).

## 7. CausalClassification / CausalConclusion (US3)

| Field | Type | Notes |
|-------|------|-------|
| `conclusion_id` | str | `CS-` prefixed. |
| `label` | enum | `CORRELATIONAL \| CAUSAL` (FR-006). |
| `model_ref` | str \| None | model id when causal. |
| `controlled_confounders` | list[str] | when causal. |
| `assumptions` | list[str] | when causal. |
| `possible_confounders` | list[str] | when correlational. |
| `evidence_links` | list[EvidenceLink] | underlying evidence. |

## 8. TemporalSeries / ChangePoint (US4)

| Field | Type | Notes |
|-------|------|-------|
| `series_id` | str | `TS-` prefixed. |
| `variable` | str | the traced credence/quantity. |
| `timestamps` | list[datetime] | UTC-normalized; original local values preserved. |
| `values` | list[float] | per-sample values. |
| `change_points` | list[ChangePoint] | detected discontinuities (below). |
| `scenario_spec` | dict | versioned reprojection params. |
| `parent_version` | str \| None | prior projection this `SUPERSEDES` (FR-015). |

`ChangePoint`: `index`, `time`, `confidence`, `pre_segment` (summary), `post_segment`
(summary), `rationale` (detector id + params).

## 9. StructureAnalysisResult (US5)

| Field | Type | Notes |
|-------|------|-------|
| `result_id` | str | `ST-` prefixed. |
| `graph_ref` | str | source graph/projection ref. |
| `kind` | enum | `SPECTRAL \| MOTIF \| HYPERGRAPH \| TEMPORAL_NETWORK`. |
| `algorithm` | str | declared algorithm id + version. |
| `scores` | dict[str, float] | normalized (documented, bounded) outputs. |
| `significance` | NullModelResult \| None | nullable-absent = `DEFERRED` (budget/sampling note instead). |
| `budget_rationale` | str \| None | when deferred. |

Always structural: outputs describe membership counts / density / motif counts — no
person-verdict interpretation layer (US5/FR-010; Constitution IV, invariant 6).

## 10. NullModelResult (FR-010)

| Field | Type | Notes |
|-------|------|-------|
| `null_id` | str | |
| `shuffle_kind` | str | e.g. `degree_preserving_stub_swap`. |
| `n_permutations` | int | |
| `observed_statistic` | float. | |
| `null_distribution` | list[float] | histogram/bins. |
| `effect` | float \| None | effect measure vs null. |
| `p_value` | float \| None | `None` when unreliable (warning instead). |
| `warning` | str \| None | e.g. "too few permutations for reliable p". |

## 11. RobustnessReport (FR-011)

| Field | Type | Notes |
|-------|------|-------|
| `report_id` | str | `RB-` prefixed. |
| `claim_ref` | str | the claim analyzed. |
| `perturbations` | list[dict] | each family (missing / flip / biased-subsample), grid spec. |
| `flip_rates` | dict[str, float] | conclusion flip rate per family. |
| `sensitivity_summary` | dict | per-input sensitivity. |
| `noise_regions` | list[dict] | conditions where the conclusion flipped. |

## 12. ExperimentRun (FR-012)

| Field | Type | Notes |
|-------|------|------|
| `run_id` | str | `EX-` prefixed. |
| `input_refs` | list[str] | corpus/evidence refs. |
| `output_refs` | list[str] | result/claim refs. |
| `seed` | int | entropy seed. |
| `pipeline_version` | str. | |
| `dependency_freeze` | dict | uv-lock anchor / versions. |
| `tolerance` | float | reproduction tolerance. |
| `reproductions` | list[str] | `EX-` ids of re-runs (US6). |

## 13. ReviewEvent (US7)

| Field | Type | Notes |
|-------|------|------|
| `event_id` | str | |
| `claim_id` | str. | |
| `actor` | str. | |
| `kind` | enum | `COMMENT \| STATUS_CHANGE \| LADDER_CHANGE`. |
| `body` | str \| None | comment text. |
| `from_status` / `to_status` | str \| None | for status change. |
| `at` | datetime | UTC. |

## Relationships

```text
Project ── owns ──► ScientificClaim ◄─ attached ── EvidenceLink ──► Observation ──► Raw
Project ── owns ──► Hypothesis  ── attached ── EvidenceLink
ScientificClaim ── has ──► CredenceDistribution ── calibrated by ──► CalibrationReport
Hypothesis ── derived credence ──► CredenceDistribution
ScientificClaim ── produced by ──► ExperimentRun ── reproduces ──► ExperimentRun
ScientificClaim ── analyzed by ──► RobustnessReport
CausalModel ── produces ──► CausalConclusion (CORRELATIONAL | CAUSAL)
TemporalSeries ── contains ──► ChangePoint   (SUPERSEDES prior projections)
StructureAnalysisResult ── has ──► NullModelResult
ScientificClaim ◄─ events ── ReviewEvent (comments, status, ladder)
```

## State transitions

- **ScientificClaim.status**: `DRAFT → CONFIRMED|WEAKENED|DISCARDED|UNCERTAIN`
  (all transitions append-only events; no silent mutation).
- **Hypothesis.status**: `PROPOSED → ACTIVE → STRENGTHENED|WEAKENED → CONFIRMED|RESOLVED`
  or `→ DISCARDED` (requires DecisionRecord).
- **CausalConclusion.label**: `CORRELATIONAL → CAUSAL` allowed only by registering a
  CausalModel and re-running; never automatic.
- **evidence ladder**: claim `ladder_rung` climbs only when the machine-checked gate for that
  rung holds (calibration + null + robustness + reproduction for top rung, FR-013).