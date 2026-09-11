# ADR-0014: Admission engine

Status: Accepted
Date: 2026-09-07

## Context

Candidates become assertions only after review against evidence quality,
temporal policy, and calibration. We must decide what gets accepted/rejected/
deferred/quarantined and how risk is injected.

## Decision

A **risk-sensitive, calibrated admission engine** (`apps/admission/engine/`, T086):
categorical hard-reject rules run FIRST (invalid identifier → REJECT, explicit
strong contradiction → REJECT/QUARANTINE per policy, insufficient evidence →
DEFER, strong corroboration → ACCEPT), then a `CalibrationProfile` picked by
entity_type/language/script applies per-type thresholds; UNCALIBRATED bootstrap
v1 is later replaced by a CALIBRATED profile from T085.

## Rationale

- Hard rules give deterministic safety; calibrated thresholds give principled
  risk on top (FR-019, R-6).
- Assertion ≠ truth (I-3): the engine labels assertions with state and
  confidence, not ground truth.
- Per-type/language/script profiles let domain-specific thresholds vary
  correctly.
- Quarantine/re-evaluation path (T065) preserves rejected candidates instead of
  destroying them.

## Consequences

- Calibration quality directly affects usefulness; T085 measures and improves it.
- POLICY changes must be versioned and audited (FR-029, T062).
- The engine must remain deterministic given the same evidence + profile.
