# ADR-0019: Per-entity reconstruction frontier

Status: Accepted
Date: 2026-09-25
Feature: 015-worldline-reconstruction (T031-T039, D3)

## Context

`materialization_cursors` is keyed by `(tenant_id, entity_id, run_id, crawl, page)`.
That is correct for resuming **one** run, and its `prepare → PROCESSING → append →
COMPLETED` path is already verified live. But because the key contains `run_id`, no
statement about outstanding work survives the run. The next run recomputes the candidate
partition list from scratch and slices it, so `CC_MAX_CRAWLS` decides what history
exists rather than what this invocation happens to do.

Two different questions need two different lifetimes:

- *What did this run already compute?* (cursor — crash recovery, run-scoped)
- *What work still exists for this entity?* (frontier — completeness, entity-scoped)

## Decision

Add a **new `reconstruction_frontier` table keyed by `(tenant_id, entity_id, query_id,
partition, page)` with no `run_id`**, alongside the existing cursor. The cursor keeps its
current responsibility unchanged. The frontier is the single authority for the
completeness verdict; per-run limits become a budget that *selects* frontier work and
leaves the rest OPEN.

Exhaustion is earned by evidence, not assumed: only a confirmed empty provider response
yields `EXHAUSTED`. A transient failure leaves the entry `RETRYABLE` with bounded
attempts, and a page identical to the previous page digest yields the distinct terminal
state `EXHAUSTED_NO_PROGRESS` so a provider that ignores paging cannot loop forever and
cannot be reported as proven empty.

## Rationale

- Completeness must survive across runs; only an entity-scoped key can express it.
- Re-keying the existing cursor would discard in-flight resume state and break the
  crash-recovery guarantee that is already verified in production.
- Terminal states are distinguishable, so coverage can honestly separate "proven empty"
  from "stopped without proof".
- Budgets that defer rather than truncate make exhaustive coverage an operational
  property (schedule) instead of a semantic one (history), which is the defect this
  replaces.

## Consequences

- Two tables are written per work item: the frontier entry (what remains) and the cursor
  (what this run computed). This is intentional duplication of purpose, not of data.
- The publication gate reads the frontier, never the cursor, to decide whether a new
  generation may be published.
- A partition index is required on `(tenant_id, entity_id, status, partition, page)` for
  coverage queries to stay inside the latency budget.
- Extends ADR-0015 (frontier architecture) for the historical-reconstruction domain;
  it does not replace the crawl frontier, which governs live URL acquisition.
