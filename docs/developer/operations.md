# Service operations and production gates

## Local stack

The canonical local stack is Compose-based. Start with make doctor and make up; profiles are documented in the architecture overview. The core acceptance workflow provisions PostgreSQL, MinIO, Redpanda, and SearXNG, applies Alembic revisions, exercises real source acquisition, and reads the produced observation/event path back.

    cp .env.example .env
    make up
    uv run python -m bench.run --scenario smoke-val
    make down

Never use production secrets in local fixtures. Do not commit .env, raw captures, object-store data, provider responses, or run output.

## Schema ownership

- PostgreSQL is authoritative operational state.
- Alembic is the only production schema migration mechanism.
- Do not invoke Base.metadata.create_all() from an operational API/workflow path.
- Migrations must be forward-compatible, tested from the supported deployed revision, and have an explicit rollback/recovery story.
- Schema drift must fail acceptance instead of being repaired implicitly during a request.

The generated gaps and engineering audit identify migration-chain defects separately. Operational services do not call Base.metadata.create_all() or create_tables(); the Alembic schema must be applied before service startup. The helper in db/session.py is reserved for hermetic tests and explicit local fixtures.

## Evidence and event path

Raw bytes are stored immutably and content-addressed. The event bus carries references and metadata, not blob bodies. Capture and Observation records must preserve tenant, investigation, source, task, capture time basis, content hash and lineage. Replays must be idempotent and must not manufacture duplicate observations.

A runtime is not integrated until the real worker writes through ArtifactSink and the broker/read-back proof observes the resulting event and downstream processing.

## Health and telemetry truth

An endpoint may report only values backed by a real source and a defined time window/scope. Do not show a pool as healthy merely because a process-local registry was initialized. Do not translate missing data into numeric zero.

The current metrics endpoint deliberately returns availability=unavailable for pipeline measurements and pool telemetry. Tenant-scoped time-series, queue lag, object growth, cost attribution, and source-yield adapters remain to be connected. The ops UI shows dashes for unknowns rather than plausible sample values.

The DLQ API also fails closed with 503 until a durable tenant-scoped repository with enumeration, payload replay, re-evaluation history, and immutable retention is wired. An empty queue is not the same as an unavailable queue.

## Recovery and release validation

Before a release, require:

- Migration from the supported current schema to head against an empty and an upgraded database.
- A clean stack acceptance run covering real object-store persistence, Capture/Observation, Redpanda event read-back, consumer replay, and deterministic reprocessing.
- Source-specific rate-limit, retry, cancellation, timeout, and egress tests.
- Tenant-isolation tests for APIs, raw objects, quarantine, projections and caches.
- Snapshot/screenshot regression for changed analyst surfaces.
- A deployment artifact with immutable image digests, software bill of materials, config/secrets references, schema revision and traceable commit SHA.

A green CI run on a branch is not a deployment. Production readiness requires a named deployment environment, migrations, rollout/rollback evidence, service-level objectives, alert routing, backup/restore tests, and an operator runbook.
