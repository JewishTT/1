# ADR-0020: Outbox lease, reclaim, and availability filtering

Status: Accepted
Date: 2026-09-25
Feature: 015-worldline-reconstruction (T062-T068, D9)

## Context

`SqlMaterializationOutbox.claim_ready` selects rows with
`status IN ('PENDING','FAILED')` and **orders by** `available_at` but never **filters** on
it. A row scheduled five seconds into the future by `mark_failed` is therefore claimed
immediately, which makes the backoff a no-op.

The same method sets `DISPATCHING` with no lease. If the relay dies between claiming a
row and starting the workflow, that row stays `DISPATCHING` forever. Because entity
creation must commit its reconstruction request in the same transaction, a stranded row
is not a queue nuisance — it is an entity that nobody will ever reconstruct, which is the
platform's primary user action silently lost.

## Decision

Add `lease_owner` and `lease_expires_at` to `materialization_outbox`.

- `claim_ready` filters `available_at <= now()` **and** additionally claims rows whose
  `DISPATCHING` lease has expired, incrementing `attempts` and `reclaim_count`.
- A successful dispatch clears the lease; a failure sets `FAILED` with a future
  `available_at`.
- Uniqueness of an active request is enforced by a **partial unique index** on
  `(tenant_id, entity_id, identity_fingerprint)` for active states, not by a
  check-then-insert in application code, which races.
- Dispatch reports per-row outcomes; a partially failed batch is never reported as a
  full success.

## Rationale

- Backoff without a filter is decoration; a claim without a lease is silent data loss.
- Reclaim by lease is safe: a slow but healthy dispatcher keeps its work, whereas
  reclaim-by-age would steal it.
- The database constraint is the only race-free place to enforce one-active-request.
- Per-row outcomes make partial failure observable instead of averaged away.

## Consequences

- Lease duration becomes a tuned operational value that the crash-and-reclaim test
  calibrates.
- `claim_ready` gains a predicate but stays index-supported on `(status, available_at)`.
- `identity_fingerprint` must be backfilled from the existing `identity` JSONB **before**
  the partial unique index is created, or pre-existing rows collide inside it.
- Entity creation no longer performs inline dispatch; the relay becomes the only
  dispatcher, which is what makes the lease meaningful.
