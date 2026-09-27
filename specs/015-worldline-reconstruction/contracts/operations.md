# Operations Contract: Worldline Reconstruction

**Feature**: [015-worldline-reconstruction](../spec.md) | **Date**: 2026-09-25

## Run lifecycle

```text
QUEUED ──dispatch──> RUNNING ──budget exhausted──> PARTIAL
                        │                              │
                        │                              └──next invocation──> RUNNING
                        │
                        ├──all frontier terminal──> COMPLETE ──publish──> PUBLISHED
                        │
                        └──fatal error──> FAILED (previous generation stays current)
```

| State | Meaning | Publishes? |
| --- | --- | --- |
| `QUEUED` | durable request exists, not yet claimed | no |
| `RUNNING` | claimed and executing | no |
| `PARTIAL` | budget hit or some frontier entries non-terminal; work deferred | no |
| `COMPLETE` | every frontier entry terminal and healthy | yes |
| `FAILED` | unrecoverable error for this attempt | no |
| `PUBLISHED` | head advanced for the new generation | already done |

`PARTIAL` is a normal, expected outcome, not an error. It is the honest representation
of "this invocation did not finish the history" and replaces the current silent
truncation (FR-008, FR-025, AS-002).

## Frontier lifecycle

| State | Terminal | Asserts partition empty |
| --- | --- | --- |
| `PENDING` | no | no |
| `IN_PROGRESS` | no | no |
| `RETRYABLE` | no | no |
| `EXHAUSTED` | yes | **yes** |
| `EXHAUSTED_NO_PROGRESS` | yes | no |
| `FAILED` | yes | no |

## Configuration

| Setting | Previous meaning | New meaning | Default |
| --- | --- | --- | --- |
| `CC_MAX_CRAWLS` | cap on partitions, truncating history | partitions processed per invocation | small enough to demonstrate deferral |
| `CC_MAX_PAGES` | cap on pages per partition | pages per partition per invocation | 1 |
| `CC_PAGE_LIMIT` | results per page | unchanged | 50 |
| `CC_HISTORICAL_PARTITIONS` | enable archive list discovery | unchanged | 0 |
| `CC_CRAWL` | pinned known-good crawl | unchanged | `CC-MAIN-2025-30` |
| `COGNITIVE_DURABLE_SQL` | gate durable execution | removed; durable is the default | n/a |
| Frontier attempt budget | n/a | attempts before `FAILED` | configurable |
| Frontier lease seconds | n/a | claim lease on a frontier entry | configurable |
| Request lease seconds | n/a | claim lease on a dispatch request | configurable |
| Relation budget | `max_events` (hard failure) | soft budget with labelled degradation | configurable |

When a budget is hit the run result must contain `complete: false` and a non-empty
`remaining_work`. A run reporting `complete: true` must have no non-terminal frontier
entry (FR-008, FR-014, FR-025).

## Retry and backoff

| Operation | Policy |
| --- | --- |
| Frontier page request | bounded attempts, exponential backoff, then `FAILED` |
| Dispatch claim | `FAILED` with future `available_at`; never claimed before that instant |
| Dispatch reclaim | expired `DISPATCHING` lease is reclaimable; `reclaim_count` increments |
| Publication | not retried in place; a failed run leaves the previous generation current |

No unbounded retry, no unbounded backlog growth (constitution backpressure and retry
budgets).

## Health and readiness

| Signal | Meaning |
| --- | --- |
| `/health` liveness | process is up; no dependency requirement |
| `/ready` readiness | PostgreSQL reachable and migrations applied |
| Relay metrics | claimed, dispatched, failed, reclaimed counts per interval |
| Frontier metrics | entries by state, open work per entity, oldest open entry age |
| Staleness metric | entities whose current generation is not the newest attempted |

An entity with open frontier work is **not** unhealthy. It is incomplete, and that is a
different state from failure; the two must not share an alert.


## Acceptance evidence per success criterion

| Criterion | Verification procedure |
| --- | --- |
| SC-001 | Unit: identity with four or more route types produces a query per route; assert `len(executable) + len(unsupported) == len(routes)` and zero silent drops |
| SC-002 | Live: set a per-invocation budget below the available work, invoke repeatedly until no open entries remain, assert every entry reached a terminal state and none was skipped |
| SC-003 | Unit + integration: interrupt between prepared-output commit and append, resume, assert no duplicate observations and no re-fetch |
| SC-004 | Unit: inject a transport error, assert the entry stays `RETRYABLE` and the run is not complete |
| SC-005 | Unit: feed rejected, deferred and quarantined claims, assert zero events, zero relations, zero state transitions, and full retrievability of the decisions |
| SC-006 | Unit: permute the same accepted-assertion set, assert identical worldline, ordering, state transitions and fingerprint |
| SC-007 | Unit: 10,000-event fixture, assert the indexed derivation equals the retained pairwise oracle exactly and completes without a size error |
| SC-008 | Benchmark: worldline request and coverage query at p95 against the 10,000-event fixture |
| SC-009 | Integration: create an entity with no worker running, query the durable request store, assert exactly one pending request |
| SC-010 | Integration: kill the relay between claim and dispatch, wait for lease expiry, assert reclaim and exactly-once dispatch |
| SC-011 | Integration: two concurrent appenders for one entity, assert no lost or duplicated records and no sequence collisions |
| SC-012 | Migration: apply all revisions to a fresh database, and apply through 014 then 015 to another, compare resulting schemas programmatically |
| SC-013 | Integration: cross-tenant probes against every new read endpoint, assert zero cross-tenant rows returned |
| SC-014 | Integration: publish a valid generation, then force a failing run, assert the previous generation is returned with a staleness label |

## Operational invariants

1. No entity exists without a durable reconstruction request.
2. A `PENDING` or `DISPATCHING` row is never stranded: leases guarantee reclaim.
3. `available_at` in the future is never claimed early.
4. A budget hit defers work; it never terminates history.
5. A partition is reported exhausted only on a confirmed empty response.
6. A partial run never advances the publication head.
7. A rejected claim never produces an event, a relation or a state transition.
8. The last valid publication is always available and always labelled.
