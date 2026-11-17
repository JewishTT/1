# Feature 042 — Task ledger

## Contracts and graph
- [x] T001 Add immutable, schema-versioned OperationSpec and SpecStep contracts.
- [x] T002 Validate spec digest, target roster, step vocabulary, approval requirement,
  topological dependencies and expiry window.
- [x] T003 Build a versioned LangGraph StateGraph with deterministic routing and
  conditional blocked/rejected/completed/manual-review paths.
- [x] T004 Add Temporal Workflow and dedicated Worker using the Temporal LangGraph
  plugin.
- [x] T005 Implement Query/Signal/Command(resume) HITL pause and resume.
- [x] T006 Add worker-side authorization and operator-decision adapter protocols.
- [x] T007 Add PostgreSQL-backed authorization/decision verification adapter.

## API and persistence
- [x] T010 Add append-only operator decision ORM model.
- [x] T011 Add Alembic revision 038 for durable step decisions.
- [x] T012 Add API to submit immutable operations against existing authorizations.
- [x] T013 Add API to query pending approval challenges.
- [x] T014 Persist authenticated admin decisions before sending Temporal Signals.
- [x] T015 Make decision submission idempotent for the same operation/step/spec digest.
- [ ] T016 Add tests for PostgreSQL gate and HTTP tenant/admin authorization behavior.
- [x] T017 Add transactional decision outbox and lease-based Signal relay for automatic
  recovery after Temporal outages.

## ARTEX and production integration
- [x] T020 Define Asset Graph and Exploration Graph adapter protocols.
- [x] T021 Define bounded assessment result schema and idempotent append key.
- [ ] T022 Implement concrete ARTEX Asset Graph / Exploration Graph adapter. The
  repository did not contain those implementations when Feature 042 was created.
- [ ] T023 Implement the approved read-only/synthetic assessment evaluator.
- [ ] T024 Deliver a deployment runtime factory combining the PostgreSQL gate,
  concrete graph adapter and evaluator.
- [ ] T025 Migrate existing SpecOps service/API/UI consumers to the new operation
  lifecycle; keep legacy execution paths blocked from this API.

## Reliability, security and observability
- [x] T030 Add isolated, pinned worker dependencies and startup fail-closed behavior.
- [x] T031 Keep raw evidence and credential payloads out of Temporal state/results.
- [ ] T032 Configure a KMS-backed Temporal Payload Codec and test ciphertext.
- [ ] T033 Implement continue-as-new/cache propagation for long event histories.
- [ ] T034 Define workflow version/build-ID compatibility for running operations.
- [ ] T035 Add complete operation lifecycle audit UI and metrics.
- [ ] T036 Add Temporal integration tests for interrupt/resume, retries, crash recovery,
  duplicate submission/signal and authorization revocation during a wait.
- [ ] T037 Run full repository CI, database migration acceptance and full-stack
  synthetic ARTEX canary before production rollout.
- [x] T038 Add unit tests for spec validation, runtime idempotency, graph build and
  rejection-before-executor behavior.
- [x] T039 Add unit tests for durable decision outbox identity and idempotent enqueue.
