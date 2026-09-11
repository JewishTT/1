# ADR-0017: Recrawl strategy

Status: Accepted
Date: 2026-09-07

## Context

Sources change over time; we must decide when and how to re-fetch targets to
keep knowledge fresh under budgets, without recrawling too eagerly or going
stale. Recrawl must interact with temporal admission (FR-016).

## Decision

A **recrawl strategy** governed by scheduled investigations and the workflow
signal `schedule_recrawl` (T078): a per-source/domain cadence modeled on
discovery yield + change likelihood, executed through the durable workflow layer
with budget-aware dispatch.

## Rationale

- T078's `RecrawlWorkflow` owns cadence and lifecycle; the frontier (ADR-0015)
  enqueues the re-fetch tasks.
- Cadence is informed by obsolescence/change signals and freshness-lag KPIs
  (T073), avoiding either over-fetch or staleness.
- Temporal policy (APPEND_ONLY / SUPERSEDABLE / EXPIRED, FR-016, T084) decides
  whether a re-fetch retracts/updates rather than blindly appending.
- Budgets (T064) cap recrawl volume so it never starves discovery.

## Consequences

- Recrawl decisions must be auditable and re-runnable (I-11 idempotency).
- Cadence tuning requires freshness-lag measurement (T073).
- Recrawl must not create false temporal contradictions; tickets go through
  admission (T086).
