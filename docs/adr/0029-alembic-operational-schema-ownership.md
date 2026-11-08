# ADR-0029: Alembic is the sole operational schema authority

- Status: Accepted
- Date: 2026-11-04
- Owners: Platform engineering

## Context

The control-plane ORM metadata evolves through ordered, forward-only Alembic revisions. Calling ORM metadata create_all from dispatch, relay, workflow, or source-materialization code silently makes application requests responsible for schema deployment. Fresh development databases can then differ from upgraded production databases, and a service can partially create tables while another service is already running.

Temporal launch also requires a durable SQL outbox record before the external workflow start. Continuing to Temporal after an outbox write fails can create non-durable work which cannot be recovered or audited.

## Decision

1. Alembic migrations are the only mechanism that changes operational schema.
2. Operational API, worker, workflow, relay, and CLI code must not call create_all() or create_tables().
3. db.session.create_tables() remains available only to explicit test/dev fixtures; it is not a production bootstrap path.
4. Deployment/startup orchestration applies and verifies migrations before enabling services.
5. Materialization dispatch returns DEFERRED and does not contact Temporal unless the idempotent, tenant-scoped outbox write has committed.
6. The outbox identity remains deterministic across retries; a transport failure after persistence leaves recoverable work rather than losing the request.

## Consequences

- Schema drift fails loudly at the database boundary instead of being masked by runtime DDL.
- Local developers and CI must run migrations or use explicitly scoped fixtures.
- The deploy pipeline must own migration ordering and verification.
- A database outage prevents new Temporal launches; this is deliberate fail-closed behavior.
- Static AST tests prevent runtime DDL from reappearing outside migration and fixture modules.

## Verification

- test_operational_schema_ownership.py scans control-plane operational Python modules.
- test_temporal_materialization_dispatch.py proves DB failure does not start Temporal and request IDs are deterministic.
- Live-stack acceptance remains responsible for migration-upgrade and durable outbox read-back.
