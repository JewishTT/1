# Science API — REST Surface

**Date**: 2026-09-09 | **Feature**: [spec.md](spec.md)

REST endpoints exposed by the `science` router mounted in `apps/control-plane/api` → served by
FastAPI. All responses are JSON; error semantics per FastAPI + the contract-style used by
existing control-plane routes. Events emitted on writes (see `science-events.md`).

Base path: `/api/science`

| Method | Path | Purpose | Story |
|--------|------|---------|-------|
| `POST` | `/claims` | register a ScientificClaim (calls `ensure_scoped` first) | US1 |
| `GET` | `/claims/{claim_id}` | fetch claim + provenance chain | US1 |
| `GET` | `/claims?project_id=` | list claims for a project | US1 |
| `POST` | `/claims/{claim_id}/status` | transition status (append-only event) | US1 |
| `POST` | `/calibration` | run calibration harness, return report | US1 |
| `GET` | `/calibration/{model_id}` | latest calibration report for model | US1 |
| `POST` | `/hypotheses` | propose hypothesis | US2 |
| `GET` | `/hypotheses?project_id=` | hypothesis register for project | US2 |
| `POST` | `/hypotheses/{id}/evidence` | attach direction-tagged EvidenceLink | US2 |
| `POST` | `/hypotheses/{id}/discard` | discard with DecisionRecord | US2 |
| `POST` | `/hypotheses/plan` | information-gain collection plan (budget in body) | US2 |
| `GET` | `/hypotheses/coverage?project_id=` | per-project coverage | US2 |
| `POST` | `/causal/classify` | CORRELATIONAL vs CAUSAL classification | US3 |
| `POST` | `/causal/models` | register a CausalModel (scope-validated) | US3 |
| `GET` | `/causal/models/{id}` | fetch model (graph, confounders, assumptions) | US3 |
| `POST` | `/temporal/series` | build TemporalSeries from samples | US4 |
| `POST` | `/temporal/change-points` | detect change points | US4 |
| `GET` | `/temporal/series/{id}` | series + credence trajectory | US4 |
| `POST` | `/structure/analyze` | bounded spectral/motif/higher-order analysis | US5 |
| `GET` | `/structure/results/{id}` | result + null significance | US5 |
| `POST` | `/robustness` | run robustness analysis on a claim | US6 |
| `GET` | `/robustness/{report_id}` | fetch report (flip rates) | US6 |
| `POST` | `/experiments` | record an ExperimentRun | US6 |
| `POST` | `/experiments/{run_id}/reproduce` | reproduce with pinned seeds/versions | US6 |
| `GET` | `/experiments/{run_id}` | fetch run + reproductions | US6 |
| `POST` | `/review/{claim_id}/comments` | add review comment | US7 |
| `POST` | `/review/{claim_id}/status` | change claim status (reviewed) | US7 |
| `GET` | `/review/{claim_id}` | ladder position + gating + review events | US7 |

## Error semantics

| Status | Body | Meaning |
|--------|------|---------|
| `422` | `{"error": "scope_refused", "policy": "contracts/scope-boundary.md", "event_id": "..."}` | forbidden person-level sensitive outcome; audit emitted |
| `400` | `{"error": "provenance_required"}` | claim without full evidence chain (FR-001) |
| `400` | `{"error": "unknown_model", "model": "..."}` | undeclared probability source (FR-002) |
| `400` | `{"error": "decision_required"}` | hypothesis discard without DecisionRecord |
| `409` | `{"error": "deferred", "budget": {...}}` | structure analysis exceeds complexity budget (DEFFERED) |
| `404` | `{"error": "not_found"}` | unknown id |

All write endpoints are idempotent by deterministic ids (event_id / claim_id / run_id),
matching Constitution idempotency rules.