# Multi-Region Topology Design (T069, US3, FR-030)

## Objective

Design the multi-region deployment topology and regional partition scheme for
the global OSINT platform. The primary driver is **data-sovereignty and egress
locality**: observations, candidates, and projections for a tenant must be
processed within the region that hosts that tenant's data, while the control
plane stays globally schedulable.

This is a **design + deploy-config** deliverable; the runtime behavior follows
from the existing invariants (I-5 Kafka is never a durable store, I-6 identity
only from resolution, I-12 projections rebuildable) so regions can be added and
removed without corrupting global state.

## 1. Topology Overview

```
                        ┌──────────────────────────────────────────────┐
                        │           GLOBAL CONTROL PLANE               │
                        │  Scheduler · Policies · Quota · Audit sink    │
                        │  Global Kafka (metadata bus, low volume)      │
                        └───────────────┬──────────────────────────────┘
                                        │
        ┌───────────────┬───────────────┼───────────────┬───────────────┐
        │               │               │               │               │
   ┌────┴─────┐   ┌─────┴────┐    ┌─────┴────┐    ┌─────┴────┐    ┌─────┴────┐
   │ REGION A │   │ REGION B │    │ REGION C │    │   …      │    │ REGION N │
   └────┬─────┘   └──────────┘    └──────────┘    └──────────┘    └──────────┘
        │   Regional control: Frontier partition · Workers · Projections
        │   Regional Kafka (high volume) · Regional Object store · Regional search
        │   Regional Redis (leases/cooldown) · Aurora/Postgres regional copy
```

- **Regions are the unit of capacity and isolation.** Each region owns the
  full data plane for the tenants assigned to it.
- **A tenant is pinned to exactly one home region** (per-tenant routing). The
  mapping lives in the control plane and is consulted on admission.
- **Frontier is partitioned per region**: global seeds fan out to regions;
  each region runs its own frontier with its own leases and cooldowns.

## 2. Frontier Partition Configuration

The frontier is hierarchical
(GLOBAL → TENANT → INVESTIGATION → SOURCE → HOST → TASK) and Postgres-backed.
In a multi-region deployment each region runs an isolated frontier shard whose
seed set is a **projection of the global frontier restricted to that region's
tenants**, materialized via the rebuildable-projection invariant (I-12).

Top-level partition keys in the frontier item (see
`apps/acquisition/frontier/src/lib.rs` `FrontierItem`):

- `region` — owning region id (added at admission time).
- `tenant_id` — existing field; scoping key for the regional shard.
- `host_key`, `source_id`, `investigation_id` — existing hierarchy keys that
  remain globally unique.

### Partitioning rules

| Concern | Rule |
| --- | --- |
| Tenant → region | Pinned by control plane; immutable during a region's life, migrated only via re-projection. |
| Host locality | A host is owned by the region of the tenant that discovered it; cross-region host reuse requires escalation. |
| Frontier shard | Each region's frontier selects rows where `region == self.region`; global seeds are fanned out at admission. |
| Lease scoping | Redis leases are per-region namespaced (`region:{r}:lease:*`) so regions never contend. |
| Cooldown/backoff | Per-region, per-tenant. |

## 3. Data-Locality Mapping

Regional stores hold only that region's tenants' data:

| Store | Regional placement |
| --- | --- |
| Object store (S3-equivalent) | `s3://{bucket}/region/{r}/{tenant}/…` prefix, consistent with T061 prefix scheme. |
| Kafka (high volume) | Regional cluster; topics partitioned by tenant and region; no durable blob on Kafka (I-5). |
| OpenSearch | Per-region index alias `region-{r}-{tenant}-*`, consistent with T061 index-alias scheme. |
| Graph | Regional graph namespace per T061 graph-namespace scoping. |
| Postgres (control state) | Global DB holds routing + quotas; regional DB holds frontier/projection checkpoints; audit copied to a global sink (FR-029). |
| Redis | Regional for leases/cooldowns; global only for routing/rate-limit coordination. |

## 4. Consistency & Recovery

- Projections are **rebuildable** (I-12) per region, so a region can be
  rebuilt from its own event history without touching other regions.
- Identity and de-duplication are resolved only from the resolution layer
  (I-6); regions emit immutable observations and let the global resolution
  layer fuse identities — a regional outage cannot corrupt identity.
- Dead-letter/quarantine is regional with a **global replay path** (T065):
  a rejected candidate in region A can be re-evaluated by the control plane.

## 5. Rollout / Decommissioning

1. Add region → register routing entry → fan out unassigned tenants.
2. Re-project the frontier partitions for moved tenants (I-12).
3. Decommission → drain frontier shard → let leases expire → re-home tenants →
   re-project → retire region.

Regional addition/removal is therefore **safe and reversible** without global
state corruption, satisfying R-4 and US3's operational requirements.
