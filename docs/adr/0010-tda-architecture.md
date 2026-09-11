# ADR-0010: TDA architecture

Status: Accepted
Date: 2026-09-07

## Context

The trajectory/temporal analysis (TDA) materializes persistence, recurrence,
and structure signals over normalized entity data. We must define its
architecture: what it computes, on what data, and how it remains a rebuildable
projection.

## Decision

TDA is a **projection layer** (`apps/projection/tda/`, T041) over immutable
normalized observations that emits persistence diagrams / structure summaries,
keeping computation structural and reproducible (no hidden ML magic).

## Rationale

- TDA is a derived materializer over provenance-tracked, immutable inputs
  (I-1, I-12 rebuildable).
- Uses proven libraries (gudhi/giotto-tda) for persistence homology, with the
  output being deterministic structure stats usable by admission.
- Structural (deterministic) outputs keep behavior auditable and reproducible
  vs. opaque black-box features.

## Consequences

- TDA outputs must be versioned with the input schema so they can be rebuilt.
- Requires scipy/numpy + TDA libs (already in projection deps).
- TDA cost must be bounded and reported (T074 perf, T071 bench).
