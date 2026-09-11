# ADR-0015: Frontier architecture

Status: Accepted
Date: 2026-09-07

## Context

The crawler must decide what URLs/tasks to fetch next under budgets, cooldowns,
and retries while keeping the queue durable and never unbounded on Kafka.

## Decision

The **frontier is an in-memory + Postgres-backed hierarchical queue** (T026, T079
partitioning): GLOBAL→TENANT→INVESTIGATION→SOURCE→HOST→TASK with lease/cooldown/
retry states (Ready/Leased/Done/Cooldown/Retry/Quarantined). Postgres is
authoritative; Redis is hot lease/cooldown cache; Kafka is never the queue
(I-5, R-4).

## Rationale

- Postgres authority keeps the frontier durable and queryable (ADR-0003) and
  enables regional shards (T069).
- Redis leases/cooldowns avoid hot-path DB contention for lease acquisition.
- Hierarchical keys support per-tenant/source/host budgets and escalation.
- Regional partition config (T069) restricts each frontier shard to its region's
  tenants via the rebuildable-projection invariant (I-12).

## Consequences

- Redis is hot state only; a Redis loss must recover from Postgres.
- Frontier throughput depends on lease efficiency; T074/backpressure (T063/T064)
  bound queue depth to avoid unbounded growth.
- Multi-region adds fan-out + routing (T069).
