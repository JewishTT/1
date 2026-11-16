# Feature 042 — Durable SpecOps&CI operations

## Problem

SpecOps&CI preparation currently validates a bounded assessment context and durable
engagement authorization, but there is no durable operation state machine, resumable
human review, or execution ledger for long-lived assessment workflows.

## Goal

Add a versioned, deterministic LangGraph planning definition that runs inside a
Temporal Workflow. Preserve Intelligence as the only evidence producer, PostgreSQL as
the authority for engagement approvals and operator decisions, and ARTEX Asset /
Exploration Graphs as domain state.

The first release supports safe defensive review and synthetic validation only.

## User stories

- As an authorized analyst, I can submit a fully specified operation bound to one
  tenant-scoped Intelligence snapshot and one existing engagement authorization.
- As an operator with admin approval rights, I can inspect a pending step, approve or
  reject it, and have the durable workflow resume or terminate.
- As an auditor, I can trace each step to the spec digest, snapshot, authorization,
  operator decision, result ID and evidence references.
- As an operator, I can rely on retries and worker restarts without duplicate ARTEX
  graph writes.

## Functional requirements

- **FR-001 Immutable spec:** canonical JSON payload, schema version and SHA-256 digest.
- **FR-002 Closed step vocabulary:** evidence review, configuration review, detection
  coverage review, synthetic lab simulation and report generation only.
- **FR-003 Scope binding:** every target must belong to the authorization roster and
  exact Intelligence snapshot; no runtime expansion.
- **FR-004 Preflight:** reject invalid, expired, revoked, duplicate or out-of-scope specs
  before scheduling any assessment.
- **FR-005 Durable orchestration:** execute the static LangGraph through a Temporal
  Workflow and registered worker.
- **FR-006 Step-level HITL:** Query exposes the challenge; Signal carries the correlated
  decision; the database decision ledger is authoritative.
- **FR-007 Revalidation:** authorization and operation expiry are rechecked before
  every assessment Activity, including after a long approval wait.
- **FR-008 Idempotent graph writes:** Activity retries reuse a stable idempotency key.
- **FR-009 Bounded payloads:** Temporal histories and graph writes contain compact
  metadata and opaque refs, never raw evidence bodies or credentials.
- **FR-010 Fail closed:** missing worker adapters, invalid approvals or invalid runtime
  outputs prevent execution.

## Non-goals

- Arbitrary user-supplied LangGraph graphs, Python or tool code.
- Autonomous exploitation, initial access, privilege escalation, lateral movement,
  phishing, credential capture or scope expansion.
- Adding a second evidence/asset graph or duplicating Intelligence facts.
- Replacing the legacy SpecOps UI and executor integrations in this feature.
- Claiming production readiness for a public-preview Temporal integration.

## Architecture

See docs/architecture/specops-durable-orchestration.md.

- LangGraph: trusted, versioned StateGraph and deterministic transitions.
- Temporal: durable workflow history, retries, timeouts, Query and Signal.
- PostgreSQL: active authorization and append-only per-step decision ledger.
- ARTEX: external Asset/Exploration Graph adapter ports; no production adapter exists
  in this repository yet.

## Acceptance criteria

1. Contract tests cover spec digest, schema, targets, expiry, approval requirement,
   dependency ordering and assessment authorization.
2. Graph tests prove that rejected decisions cannot reach the evaluator.
3. Runtime tests prove revalidation precedes graph I/O and result append uses an
   idempotency key.
4. PostgreSQL migrations and ORM metadata agree on authorization and decision tables.
5. API tests verify tenant isolation, admin-only decisions and durable-before-signal
   ordering.
6. A Temporal test server proves interrupt/query/signal/resume behavior, worker crash
   recovery and duplicate signal handling.
7. An ARTEX synthetic adapter proves idempotent read/write semantics.
8. Payload Codec/KMS, continue-as-new, version compatibility, metrics and operation
   audit UI are complete before production rollout.
