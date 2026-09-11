# ADR-0003: PostgreSQL role (authoritative operational state)

Status: Accepted
Date: 2026-09-07

## Context

The system needs authoritative, transactional, queryable operational state: the
frontier hierarchy (GLOBAL→TENANT→INVESTIGATION→SOURCE→HOST→TASK), investigation
lifecycle state machines, audit events, budgets/quotas, and routing. Strong
consistency and referential integrity are required; eventual consistency is not
acceptable for these.

## Decision

Use **PostgreSQL** as the authoritative store for operational/control state.

## Rationale

- Strong ACID + relational integrity for the frontier hierarchy and state
  machines (R-4).
- Postgres is the frontier source of truth (I-5 complement: Redis is hot cache,
  Kafka is transport, Postgres is authoritative — T026).
- Mature, portable, supports logical replication for regional/global copies.
- JSONB lets semi-structured control state coexist with relational joins.

## Consequences

- Postgres must not be used for raw blobs (object store owns those, ADR-0002).
- Sequencing/idempotency of mutations must be handled explicitly (I-11).
- Regional control copies need replication strategy (FR-030, T069).
