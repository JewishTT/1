# ADR-0007: Temporal for long-running orchestration

Status: Accepted
Date: 2026-09-07

## Context

Investigations run long-lived, multi-step workflows with durable execution,
retries, human approval gates, pauses/resumes, and checkpoint recovery (T078).
Plain queues or ad-hoc job tables don't give durable, replayable workflow
semantics.

## Decision

Use **Temporal** for durable workflow orchestration.

## Rationale

- Durable execution: a workflow survives worker restarts and resumes from
  checkpoint (T078 checkpoint recovery).
- First-class signals (pause/resume/approve/reject) for the investigation
  lifecycle (T046, T078).
- Deterministic workflow code + activity retries map to our idempotency (I-11).
- Timeline/visibility for audits and ops dashboards (T068).

## Consequences

- Workflow business logic must be deterministic and pure (tested separately
  from Temporal, per T078's `InvestigationLifecycle`).
- Adds an operational component (Temporal server, history store).
- A Temporal outage pauses new orchestration but not the already-durable data
  plane.
