# ADR-0018: Multi-region topology

Status: Accepted
Date: 2026-09-07

## Context

Data sovereignty and egress locality (FR-030, T069) require processing a
tenant's data in its home region. We must define how regions isolate data, how
the frontier partitions across regions, and how regions can be added/removed
without corrupting global state.

## Decision

**Region-first topology** (T069, `docs/architecture/multi-region.md`): a tenant is
pinned to one home region; regions own the full data plane (frontier shard,
regional Kafka/S3/search/graph/Redis/DB) for their tenants; the global control
plane owns routing, quotas, and audit sink. Frontier is partitioned per region
as a rebuildable projection (I-12).

## Rationale

- Per-tenant pinning + regional stores satisfy data-locality and fail-closed
  isolation (T061).
- Because projections are rebuildable (I-12) and identity comes only from
  global resolution (I-6), a regional outage or migration never corrupts
  cross-regional identity/state.
- Regional frontier shards fan out from global seeds at admission; leases are
  region-namespaced so regions never contend.
- Adding/removing a region is a re-projection, hence safe and reversible.

## Consequences

- Regional deploy config (`apps/deploy/k8s/`) codifies regions,
  tenant→region routing, partitions, and prefixes (must stay layered under the
  T061 tenant isolation prefix scheme).
- Adds operational complexity: replication, routing, and cross-region replay
  (T065 global replay path).
- Requires careful egress/locality policy review (T072 security).
