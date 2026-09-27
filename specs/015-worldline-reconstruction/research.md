# Phase 0 Research: Worldline Reconstruction

**Feature**: [015-worldline-reconstruction](./spec.md) | **Date**: 2026-09-25

This document records the technical decisions taken during planning, the evidence in
the current code that motivates them, and the alternatives that were considered and
rejected. Each decision cites the functional requirements it satisfies.

## Evidence from the current implementation

The following facts were read directly from the repository and drive every decision
below.

| Observation | Location | Consequence |
| --- | --- | --- |
| The workflow executes a single `surface.cc_plan` and raises if it is `None` | `apps/control-plane/services/cc_cursor_materialization.py:25-27` | One route per entity; the rest of the search surface is unused |
| The search surface already carries 15 identity dimensions | `apps/acquisition/entity_search.py:32-48` | The planning information exists and is simply discarded at execution |
| `build_cc_plan` uses a fixed priority `url > domain/host/site > name` | `apps/acquisition/cc_plan.py:32-37` | Priority is a one-dimensional winner-take-all choice |
| `available` is sliced by `CC_MAX_CRAWLS` before any work is recorded | `cc_cursor_materialization.py:38` | The cap decides history, not schedule |
| Pages are iterated `range(CC_MAX_PAGES)` | `cc_cursor_materialization.py:47` | Pagination stops at the budget and the remainder is never enqueued |
| An empty hit list is marked `COMPLETED` | `cc_cursor_materialization.py:70-73` | Absence of results is conflated with completion of the partition |
| A discovery exception marks the cursor `FAILED` and continues, then the run still publishes | `cc_cursor_materialization.py:66-69` and `:98-118` | A partition failure can be masked by records from other partitions, and a partial result publishes as `READY` |
| Sequence is computed in Python as `max(existing.sequence) + n` | `cc_cursor_materialization.py:88` and `:60` | Read-then-write race between concurrent runs |
| One `StreamRecord` of kind `cc.capture` carries `relations` and `admission` as nested payload JSON | `apps/control-plane/services/capture_interpretation.py:89-101` and `cc_cursor_materialization.py:88` | One WARC becomes one worldline event; 100 relations collapse to one timeline entry |
| Admission decisions are produced but the resulting record is appended unconditionally | `cc_cursor_materialization.py:88-95` | A rejected claim can live inside an accepted record |
| `claim_ready` orders by `available_at` but does not filter on it, and has no lease | `apps/control-plane/db/materialization_outbox.py:53-66` | Backoff-delayed work is claimed early; a dead claimer strands rows in `DISPATCHING` |
| `create_entity` calls the dispatcher directly and additionally spawns an in-process pipeline task | `apps/control-plane/api/routes/entities.py:208-231` | Entity creation is not the transactional boundary; recovery depends on in-process luck |
| `derive_temporal_relations` is an explicit nested loop with `max_events=512` and raises `WorldlineError` beyond it | `apps/shared/domain/temporal_worldline.py:995-1016` | Quadratic cost and a hard failure exactly where large histories begin |
| `MaterializationCursor` is keyed by `(tenant, entity, run, crawl, page)` | `apps/control-plane/db/materialization_cursor.py:23-25` and `schema.py:921-951` | Frontier state dies with the run; nothing carries forward to the next run |
| Only migration revision `014` exists | `apps/control-plane/db/migrations/versions/` | A new forward-only revision is required; 014 must not be edited |

## D1: Multi-route `SourceQuerySet` replaces the single `CcQueryPlan`

**Context**: `EntitySearchSurface` already normalizes 15 identity dimensions, but
`build_cc_plan` collapses them to one winner by fixed priority, and the workflow
consumes only that winner.

**Decision**: Introduce `SourceQuery` and `SourceQuerySet` in
`apps/acquisition/source_query_set.py`. A `SourceQuerySet` is an ordered, deduplicated
tuple of `SourceQuery` values derived from the whole surface. Each query carries a
`route_kind` (`exact_url`, `url_prefix`, `domain`, `name`, `alias`, `historical_name`,
`username_derived`, `email_derived`, `phone_derived`), a normalized query value, a
`match_type`, an optional SURT prefix, and the list of originating identity attributes
that produced it. `build_cc_plan` is retained unchanged and remains reachable through
the surface for backward compatibility.

**Rationale**: The planning information is already computed and correct; only the
execution side is one-dimensional. Fixing execution preserves the deterministic,
allocation-light character of the existing planner. Deduplicating on the normalized
value while keeping both provenance references means an entity that lists
`example.com` as both `domain` and `site` produces one query that still records where
it came from.

**Consequences**: The frontier becomes keyed by query, so the planner must run before
frontier construction. The legacy single-plan shape stays available and inspectable for
deployments that depend on it.

**Rejected alternatives**:
- *Extend `CcQueryPlan` to hold a list.* Rejected: `CcQueryPlan` is consumed by
  existing code and tests as a single query; changing its shape breaks the contract
  without adding capability.
- *Concatenate the raw identity values into one query string.* Rejected: loses
  per-route match semantics and cannot be deduplicated or attributed.

**Satisfies**: FR-001, FR-002, FR-003, FR-005

## D2: Unsupported routes are declared, never silently dropped

**Context**: Not every identity dimension has an executable provider. A phone number
or a bare username cannot be turned into a Common Crawl index query without inventing
a derivation rule that no provider defines.

**Decision**: A route that no registered provider can execute is emitted into the query
set as a `SourceQuery` with `executable=False` and a machine-readable `unsupported_reason`
(`no_provider_for_route`, `normalization_failed`, `value_too_short`). Unsupported
queries are never dispatched, are never counted as executed, and are reported verbatim
through the query inspection interface. Route registration is an explicit registry, so
adding a provider later makes a previously unsupported route executable without changing
the planner.

**Rationale**: This is the agreed scope decision. The failure mode being avoided is a
silent drop, which currently makes a partially-executed surface indistinguishable from a
fully-executed one. Declaring the reason converts an invisible gap into a visible,
queryable fact.

**Consequences**: Completeness claims must distinguish "route executed and empty" from
"route not executable". Coverage reporting gains an `unsupported` category. No new data
source is introduced.

**Rejected alternative**: *Derive Common Crawl queries for phone and username values.*
Rejected: it would invent retrieval semantics that no provider documents, producing
results whose provenance cannot be justified.

**Satisfies**: FR-004, FR-006

## D3: A per-entity, run-independent frontier table, added alongside the existing cursor

**Context**: `MaterializationCursor` is keyed by `(tenant, entity, run, crawl, page)`.
That is correct for resuming *one* run, and it is already verified live. But because
the key contains `run_id`, no statement about work remaining after a run survives the
run. The slice of available partitions is recomputed from scratch on the next run, which
is exactly why a budget becomes a semantic limit.

**Decision**: Add a new `reconstruction_frontier` table keyed by
`(tenant_id, entity_id, query_id, partition, page)` with **no** `run_id`. The existing
`MaterializationCursor` is left intact and keeps its current responsibility: it
checkpoints the *prepared output* of a single run's work item so a crash between
`prepare` and `append` can replay exactly that output without re-fetching. The frontier
answers "what work exists for this entity"; the cursor answers "what did this run
already compute".

**Rationale**: Two different questions with two different lifetimes. Re-keying the
cursor would either destroy in-flight resume state or conflate the two. Keeping both
means the already-verified crash-recovery path is untouched while history-across-runs
becomes durable for the first time.

**Consequences**: Two tables must be written per work item: the frontier entry (what
remains) and the cursor (what this run computed). The publication gate reads the
frontier, not the cursor, to decide completeness.

**Rejected alternative**: *Re-key `MaterializationCursor` to drop `run_id`.* Rejected:
it would break the live-verified crash-recovery guarantee and mix "remaining work" with
"computed output".

**Satisfies**: FR-007, FR-011, FR-013, FR-014

## D4: Per-run limits become a scheduler budget that defers work

**Context**: `CC_MAX_CRAWLS`, `CC_MAX_PAGES` and `CC_PAGE_LIMIT` currently decide what
history exists. Removing them entirely is not an option: operational capacity is finite
and a single invocation cannot scan an entire archive.

**Decision**: Keep all three settings, but redefine them as a **per-invocation budget**.
When a budget is reached, the current run stops selecting work, leaves every unselected
frontier entry in its current non-terminal state, and returns a result containing
`complete: false`, the budget that was hit, and a non-empty `remaining_work` summary.
The worldline derived from that run is labelled incomplete. The next invocation selects
from the same frontier and continues.

**Rationale**: The distinction that matters to a user is between "history ends here"
and "history continues". Budgets must express the second. Keeping the settings means
operators keep the same knobs and the same blast radius, but the semantic consequence
of reaching them changes from truncation to deferral.

**Consequences**: Every run result must carry completeness. The API cannot answer
"ready" without also answering "complete". Tests that assert a bounded record count
under a fixed budget must be rewritten to assert bounded *per-run* work with an
explicit remainder.

**Rejected alternative**: *Delete the limits and scan everything in one run.* Rejected:
unbounded runtime, unbounded memory, no backpressure, and a single failure would lose
all progress rather than a bounded slice of it.

**Satisfies**: FR-008, FR-014, FR-025

## D5: Exhaustion requires a confirmed provider signal

**Context**: The current code marks a page `COMPLETED` when the hit list is empty,
which conflates three different situations: the partition genuinely has no more
results, the request failed and was swallowed, and the provider returned a degenerate
response.

**Decision**: Frontier state transitions are driven by an explicit classification of
the provider outcome:

| Provider outcome | Frontier transition |
| --- | --- |
| successful response, zero results | `EXHAUSTED` (confirmed absence) |
| successful response, results returned | advance page, `IN_PROGRESS` |
| transport error, timeout, 5xx, 429 | `RETRYABLE`, attempts incremented, bounded |
| malformed response, unparseable body | `RETRYABLE` up to the attempt budget, then `FAILED` |
| page identical to a previously recorded page for the same partition | `EXHAUSTED_NO_PROGRESS` |

The no-forward-progress guard records a digest of each processed page and stops paging
when a page repeats, which prevents an infinite loop when a provider ignores the page
parameter. `EXHAUSTED_NO_PROGRESS` is a distinct terminal state from `EXHAUSTED`
because the partition was not proven empty, and coverage reporting must say so.

**Rationale**: "Exhausted" is a claim about the archive, so it must be earned by
evidence. Making the terminal states distinguishable prevents a silent hole in
coverage from being reported as a completed scan.

**Consequences**: The coverage interface must distinguish confirmed-exhausted from
stopped-without-progress. Both are terminal for scheduling purposes; neither means the
partition was proven empty.

**Rejected alternative**: *Treat an empty page as exhausted and add a retry for
exceptions only.* Rejected: this is the current behaviour and it still records a
partition as complete on a single empty response regardless of whether more pages
exist.

**Satisfies**: FR-009, FR-010, FR-012, FR-013

## D6: Separate observation, assertion and event stream kinds

**Context**: One WARC currently becomes one `cc.capture` record whose payload nests
`relations` and the whole `admission` block. The worldline folds over that record, so a
capture with a hundred relations contributes exactly one event.

**Decision**: Introduce three new `entity_stream` record kinds alongside the retained
`cc.capture`:

| Kind | Identity | Carries |
| --- | --- | --- |
| `cc.observation` | `OBS-` + content/warc-record identity | locator, url, crawl, page, content hash, byte length, warc record id, record type, digest verification, untrustworthy flags |
| `entity.assertion` | `ASR-` + deterministic hash of (subject, predicate, object, interval, observation) | subject, predicate, object, subject/object kind, interval, precision, confidence, source observation id, source record id, candidate id |
| `entity.event` | `EVT-` + deterministic hash of (assertion id, interval, generation) | assertion id, subject, predicate, object, interval, precision, participants, before/after state, evidence refs, confidence |

`cc.capture` is still written for backward compatibility and still carries the full
capture payload, but the worldline no longer folds over it as its unit.

**Rationale**: Each level needs its own identity so it can be referenced, deduplicated,
queried and re-derived independently. An event must be able to point at the assertion
that produced it and the observation behind that; nesting them in one blob makes none
of them independently addressable.

**Consequences**: Write volume per capture increases from one row to one observation row
plus one row per extracted relation. Batching per observation keeps this to a single
transaction per capture. All payloads carry refs only; raw bytes stay in the
content-addressed object store, preserving constitution I-5.

**Rejected alternative**: *Keep one record and add sibling arrays with ids inside the
payload.* Rejected: it preserves the exact defect the user identified, because nothing
in the stream would be independently addressable or independently queryable.

**Satisfies**: FR-015, FR-016, FR-020, FR-021

## D7: Admission gates worldline contribution

**Context**: `interpret_warc_capture` produces real decisions
(`ACCEPT_NEW`, `ACCEPT_EXISTING`, `DEFER`, `REJECT`, `QUARANTINE`) and the materializer
then appends the record regardless of what those decisions were.

**Decision**: Admission becomes a gate on projection, not merely a field in a payload.
`entity.assertion` rows are written for every extracted claim and always carry their
decision, reason codes, score vector and policy version. Only assertions whose decision
is in the accepted set are eligible to become `entity.event` rows; only events feed
temporal relations and entity state transitions. Non-accepted claims remain fully
retrievable through the assertions interface with their reasons intact. Publication
records the accepted, rejected, deferred and quarantined counts of the work it covers,
and a work item that produced zero accepted assertions cannot be published as a
completed reconstruction result.

**Rationale**: `Assertion != truth` and `Admission != Priority` are constitutional
invariants. A rejected claim living inside an accepted record violates the first in
practice even when the record type says otherwise. Gating at projection time keeps the
evidence of rejection intact while making it structurally impossible for a rejected
claim to influence the worldline.

**Consequences**: The worldline can legitimately be empty for an interval that produced
only rejected claims, and that emptiness is now meaningful rather than a bug. Tests
must assert zero events for rejected input, not merely a recorded decision.

**Satisfies**: FR-017, FR-018, FR-019, FR-023, FR-024

## D8: Atomic per-entity sequence allocation

**Context**: `cc_cursor_materialization.py` computes
`sequence = max(existing.sequence) + len(records) + 1` in Python after a `replay()`,
and the `StreamAppendRejected` recovery path recomputes it again. Two concurrent runs
for one entity can read the same maximum and write colliding sequences.

**Decision**: Add a `entity_stream_sequence` table with primary key
`(tenant_id, entity_id)` holding `next_sequence`. Allocation is a single statement:

```sql
INSERT INTO entity_stream_sequence (tenant_id, entity_id, next_sequence)
VALUES (:tenant, :entity, :count)
ON CONFLICT (tenant_id, entity_id)
DO UPDATE SET next_sequence = entity_stream_sequence.next_sequence + :count
RETURNING next_sequence;
```

The returned value is the first allocated sequence for the batch, and the batch occupies
`[first, first + count)`. Allocation happens inside the same transaction as the append,
so a rollback returns the range to the pool. `entity_stream`'s primary key
`(tenant_id, entity_id, sequence)` remains the final enforcement: a collision still
fails, but it can now only happen if the counter and the table diverge, which the
concurrent test asserts cannot occur.

**Rationale**: `UPDATE ... RETURNING` on a single counter row serializes allocation per
entity without a table lock and without a client-side read. It is the standard Postgres
idiom and needs no new extension.

**Consequences**: The client-side `max(sequence) + 1` computation is removed from the
materialization path. The recovery path stops recomputing sequences.

**Rejected alternatives**:
- *`SELECT max(sequence) ... FOR UPDATE`.* Rejected: `FOR UPDATE` cannot lock an
  aggregate result, so this does not actually serialize the read.
- *A Postgres sequence per entity.* Rejected: sequences cannot be pre-allocated and
  returned on rollback, which would leave permanent gaps and break the contiguous
  sequence contract.

**Satisfies**: FR-031, FR-032

## D9: Outbox leases, reclaim, and a real `available_at` filter

**Context**: `claim_ready` selects rows with `status IN ('PENDING','FAILED')`, orders by
`available_at`, but never filters on it, so a row scheduled five seconds into the future
is claimed immediately and its backoff is a no-op. It also sets `DISPATCHING` with no
lease, so a relay that dies between claiming and dispatching strands the row forever.

**Decision**: Add `lease_owner` and `lease_expires_at` to the outbox. `claim_ready`
filters `available_at <= now()` and claims both due rows and rows whose `DISPATCHING`
lease has expired, reclaiming the latter by incrementing `attempts` and recording the
reclaim. A successful dispatch clears the lease. A failed dispatch sets `FAILED` with a
new `available_at`. A batch dispatch reports per-row outcomes, and the relay's return
value distinguishes `dispatched`, `failed` and `reclaimed` so a partial failure is never
reported as a fully successful batch.

**Rationale**: Backoff without a filter is decoration, and an un-leased claim is a
silent data-loss path. Both are prerequisites for the no-orphan-entity guarantee,
because a stranded request means an entity nobody will ever reconstruct.

**Consequences**: Lease duration becomes a tuned operational value. Claim queries gain
one more predicate and remain index-supported on `(status, available_at)`.

**Rejected alternative**: *Recover `DISPATCHING` rows by age alone.* Rejected: without a
lease, age is a guess, and a slow but healthy dispatcher would have its work stolen.

**Satisfies**: FR-027, FR-028, FR-029

## D10: Entity creation is the transactional boundary of the request

**Context**: `create_entity` inserts the entity, then calls
`start_entity_materialization(...)` directly, then, if the launch is deferred and no
source records were supplied, spawns `asyncio.create_task(run_live_entity_pipeline(...))`
as an in-process fallback.

**Decision**: The entity row and the reconstruction request row are written in **one**
transaction. The request starts `PENDING` with `available_at = now()`. The API no longer
invokes the dispatcher inline and no longer spawns an in-process pipeline task; the
relay is the only dispatcher. The request carries a unique constraint on
`(tenant_id, entity_id, identity_fingerprint)` for active requests, so a replayed
creation cannot enqueue a second reconstruction. The in-memory repository remains
available only as an explicit test and development fallback selected by configuration,
never as a production default.

**Rationale**: The primary user action of the platform currently has a silent data-loss
window: if the process dies between the entity insert and the launch, the entity exists
and nothing will ever reconstruct it. Making the request part of the same commit closes
that window. Removing the in-process fallback is what makes the durable path the real
path rather than a preferred one.

**Consequences**: Entity creation latency no longer depends on Temporal being reachable.
Dispatch becomes asynchronous by construction, which the API already models with
`202 Accepted`.

**Rejected alternative**: *Keep the inline dispatch and additionally write the request.*
Rejected: the inline call reintroduces exactly the race the request is meant to close.

**Satisfies**: FR-026, FR-030

## D11: Indexed relation derivation, with the pairwise loop retained as an oracle

**Context**: `derive_temporal_relations` sorts events and then evaluates a nested loop
over all pairs, guarded by `max_events=512`, raising `WorldlineError` above it.

**Decision**: Keep the existing function unchanged and reachable as a reference
implementation, and add a new indexed derivation used in production:

- **Ordering**: events are sorted once by the canonical order key. `precedes` and
  `follows` follow from that order, so they are produced by walking the sorted list
  rather than by comparing every pair.
- **Overlaps**: a sweep line over interval starts with an active-interval structure
  closed on interval end. Each event is compared only against currently overlapping
  events, which is proportional to actual overlap count rather than to `nВІ`.
- **Declared causes**: resolved through the existing id map, which is a hash lookup, and
  remain labelled as declared rather than derived.

The new derivation must produce a relation set identical to the reference implementation
on the same inputs; this equivalence is asserted by test on randomized interval sets and
on the full 10,000-event fixture. A configurable relation budget triggers explicit,
labelled degradation reporting what was not computed, replacing the exception.

**Rationale**: The relation semantics are already correct and well specified; only the
complexity is wrong. Keeping the pairwise version as an oracle means the optimization is
provably behaviour-preserving rather than a rewrite of proven semantics.

**Consequences**: `max_events` no longer causes a hard failure. The oracle remains in the
codebase as test-only surface and must not be deleted.

**Rejected alternative**: *Raise `max_events` to 100,000.* Rejected: this is precisely the
change identified as wrong; the quadratic term remains the fundamental limit.

**Satisfies**: FR-034, FR-035, FR-036, FR-037

## D12: Forward-only migration; revision 014 is treated as applied

**Context**: `014_temporal_materialization.py` was edited repeatedly after it had already
been applied to a live database. Editing an applied revision means an existing deployment
will never receive the new tables and columns, because the recorded revision already
matches.

**Decision**: Treat `014` as released and immutable. All new tables, columns and indexes
for this feature ship in a new forward-only revision. Verification runs on both paths: a
fresh install applying every revision in order, and an upgrade from a database that
already has `014` applied. Both must reach an identical schema state, compared
programmatically rather than by inspection.

**Rationale**: This is a deployment-correctness requirement, not a style preference. A
feature that only works on a clean database is not shippable.

**Consequences**: The upgrade path is a first-class test. Any future feature touching
these tables must add a revision rather than editing an existing one.

**Rejected alternative**: *Continue editing 014.* Rejected: it silently breaks every
already-deployed database, which is the failure mode this decision exists to prevent.

**Satisfies**: FR-033


## D13: Partial failure blocks completion, not publication of prior truth

**Context**: When discovery raises for one partition, the cursor is marked `FAILED` and
the loop continues; the run then publishes whatever records exist and returns
`status: READY`. Records from other partitions mask the failure.

**Decision**: Publication of a *new* generation requires every frontier entry for the
entity to be in a terminal state. If any entry is `RETRYABLE`, `FAILED` or
`PENDING`, the run reports `partial`, names the offending partitions with their reasons,
and does not advance the publication head. The previously published generation remains
the current one and is served with an explicit staleness label. Partial evidence
already committed to the stream is retained; only the completion claim is withheld.

**Rationale**: A completeness claim that is false is worse than a stale but honest view.
The user's requirement is that a partial result never presents as final, which is
distinct from saying partial work must be thrown away.

**Consequences**: `READY` becomes a strictly stronger claim than "no exception was
raised". Coverage and worldline responses both carry the verdict.

**Satisfies**: FR-025, FR-040

## D14: Determinism preserved by canonicalization, not by input order

**Context**: Correctness of the worldline depends on the same assertion set producing
the same output regardless of arrival order.

**Decision**: Every identity for every level is a hash over explicitly
canonicalized fields with a fixed separator and fixed field order, and every fold sorts
its input by that identity before processing. Identifiers are additionally mapped into
the event id space before relation derivation so that a declared cause naming either a
record id or an event id resolves. Nothing in the derivation reads dictionary or arrival
ordering.

**Rationale**: Determinism is a constitutional requirement, and the current
implementation already achieves it for the capture level. Extending the same discipline
to assertions and events is what makes SC-006 testable.

**Consequences**: Randomization tests over input permutation are part of the acceptance
set for both the assertion fold and the relation derivation.

**Satisfies**: FR-002, FR-022

## Open questions carried into implementation

| Question | Handling |
| --- | --- |
| Exact per-invocation budget defaults | Configurable; the default must be small enough that a live demonstration shows deferral rather than immediate exhaustion |
| Lease durations for dispatch and frontier claims | Configurable with a conservative default; validated by the crash-and-reclaim test |
| Relation budget value and degradation thresholds | Configurable; the degradation report must name what was not computed |
| Whether the observation-level timeline remains permanently available | Retained; it is required by FR-021 and is the bridge for existing consumers of capture payloads |

