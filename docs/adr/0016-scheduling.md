# ADR-0016: Scheduling (task/work ordering)

Status: Accepted
Date: 2026-09-07

## Context

Workers must pick tasks (HTTP/browser/document/OCR/vision/TDA) while respecting
priorities, budgets, backpressure, and pool isolation, without overloading
sources or a single failing pool stopping others.

## Decision

A **policy-driven scheduler** in the dispatcher, backed by the frontier and
worker pools: work is pulled by priority + policy, backpressure/retry budgets
are enforced in the dispatcher (`backpressure.rs`, T063/T064), and each worker
kind (HTTP/browser/document/OCR/vision/TDA) runs an **isolated pool** (T066) so
one failing pool doesn't stop others.

## Rationale

- Budgets (task/source/investigation/global) and queue-depth/lag feed a rate
  limiter that prevents unbounded Kafka backlog (T063/T064).
- Escalation-only routing (browser fabric, T067) keeps isolated pools from
  cross-contaminating.
- Pools are independent for failure isolation (R-4/FR-030).
- Durable orchestration across long investigations is handled by Temporal
  (ADR-0007), while the dispatcher optimizes short-horizon ordering.

## Consequences

- Scheduler policy must remain explainable and auditable (T062 audit).
- Backpressure tuning must be observable (T068 metrics, T073 panels).
- Scheduling is separate from durable workflow state (Temporal owns the latter).
