# Science Events — Kafka Envelope Contract

**Date**: 2026-09-09 | **Feature**: [spec.md](spec.md)

Topics registered in `apps/shared/events/topics.py` `EVENT_CATALOG` (research §9). All events
use `events.kafka.build_envelope`; payloads are refs/fields-only JSON (no blobs, Constitution
I-5). Keys are stable per type; consumer idempotency by `event_id`.

## Topic list and payload shape

| Topic | Key fields |
|-------|------------|
| `science.claim.registered` | `claim_id`, `project_id`, `status`, `model_id@version`, `provenance_refs[]`, `distribution_ref` |
| `science.claim.status_changed` | `claim_id`, `from_status`, `to_status`, `actor(or system)`, `at` |
| `science.claim.discarded` | `claim_id`, `decision` (who/when/why), `evidence_refs[]` |
| `science.hypothesis.proposed` | `hypothesis_id`, `project_id`, `text` |
| `science.hypothesis.evidence_attached` | `hypothesis_id`, `link_id`, `observation_id`, `direction`, `weight` |
| `science.hypothesis.status_changed` | `hypothesis_id`, `from_status`, `to_status`, `actor`, `at` |
| `science.hypothesis.discarded` | `hypothesis_id`, `decision` (who/when/why) |
| `science.calibration.report` | `report_id`, `model_id`, `ece`, `brier`, `verdict`, `thresholds_ref` |
| `science.causal.classified` | `conclusion_id`, `label` (CORRELATIONAL/CAUSAL), `model_ref?`, `evidence_refs[]` |
| `science.causal.scope_rejected` | `event_id`, `outcome_class`, `entry_point`, `actor`, `policy` |
| `science.temporal.change_point` | `series_id`, `change_points[]` (time, confidence, segments), `supersedes_ref?` |
| `science.structure.analyzed` | `result_id`, `graph_ref`, `kind`, `algorithm`, `significance_ref`, `status` (OK/DEFERRED) |
| `science.robustness.report` | `report_id`, `claim_ref`, `flip_rates{}`, `sensitivity_ref` |
| `science.experiment.run` | `run_id`, `input_refs[]`, `output_refs[]`, `seed`, `pipeline_version`, `dependency_freeze_ref` |
| `science.experiment.reproduction` | `run_id`, `reproduced` (bool), `tolerance`, `delta` |
| `science.review.commented` | `event_id`, `claim_id`, `actor`, `body` |
| `science.review.status_changed` | `event_id`, `claim_id`, `actor`, `from_status`, `to_status`, `ladder_rung?` |

## Rules

- **Immutability**: topics are append-only; a status change is a new event, never a
  retraction of the previous one (Supersedes semantics live in the store, not the log).
- **Refs not blobs** (I-5): statement text appears on proposal; evidence/raw content is
  referenced by id/sha, never embedded.
- **Idempotency**: consumers dedupe on `event_id`; producers derive deterministic ids
  (claim_id, hypothesis_id, report_id, run_id) so replay is safe.
- **Boundary**: scope rejections always emit `*.scope_rejected` with policy attached.
- **Rebuildability** (I-12): state projections (claims, hypotheses, calibration reports,
  experiment registry) replay fully from these topics.