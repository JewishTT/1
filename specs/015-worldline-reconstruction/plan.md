# Implementation Plan: Worldline Reconstruction

**Branch**: `015-worldline-reconstruction` | **Date**: 2026-09-25 | **Spec**: [spec.md](./spec.md)

**Input**: Completed feature specification from `specs/015-worldline-reconstruction/spec.md`

## Summary

Change the unit of materialization and make historical coverage honest and durable.

The current pipeline is a real vertical slice: a Common Crawl index query yields a
locator, a byte-range GET yields WARC bytes, a parser yields a document, deterministic
extractors yield relations, the admission engine yields decisions, and a durable cursor
plus a SQL stream plus a publication head yield a worldline. What it does not yet do is
execute every search route, exhaust history, or represent a change in the entity's
asserted state rather than the fact that a capture happened.

This feature therefore does three things at once:

1. **Execution becomes multi-route.** A single prioritized Common Crawl plan is replaced
   by an ordered, deduplicated `SourceQuerySet` derived from every dimension of the
   entity search surface. Routes that no provider can execute are declared unsupported
   with a reason instead of vanishing.
2. **History becomes exhaustive and durable.** A run-keyed cursor becomes a per-entity,
   run-independent frontier. Crawl, page and capture limits stop being a semantic limit
   on history and become a per-invocation scheduler budget: exhausting the budget defers
   remaining work and reports it, it does not end reconstruction.
3. **The stream stops lying about what it contains.** One WARC with a hundred relations
   no longer becomes one worldline event. The pipeline emits an observation, then
   per-candidate assertions, then only admitted assertions become temporal events,
   relations and entity state transitions. Rejected, deferred and quarantined claims
   stay retrievable and contribute nothing.

Alongside those, entity creation becomes the transactional boundary of the
reconstruction request, dispatch gains leases and reclaim, stream sequence allocation
becomes atomic under concurrency, relation derivation stops being quadratic, and all
schema changes ship as a new forward-only migration rather than an edit to the
already-applied revision 014.

The feature preserves every verified capability of the existing slice. Nothing is
rebuilt from scratch; the retrieval, parsing, extraction and admission stages keep their
current authority, and the publication model from feature 014 is reused.

## Technical Context

**Language/Version**: Python 3.11+ (existing monorepo baseline)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async, PostgreSQL, Temporal
(`temporalio`), httpx, existing `acquisition` / `interpretation` / `admission` /
`domain` / `network` packages, React + TypeScript webapp

**Storage**: PostgreSQL is the publication authority and the durable frontier authority.
Raw WARC payloads remain in the content-addressed object store; payloads carry refs only.

**Testing**: pytest (existing suites under `apps/shared/tests/unit/domain/`,
`apps/control-plane/tests/unit/`, `apps/acquisition/tests/unit/`), ruff, compileall,
live Docker E2E against a real Common Crawl target

**Target Platform**: Linux server, Docker Compose core stack (PostgreSQL, Redis, MinIO,
Kafka, Temporal), API on `:8000`

**Project Type**: single monorepo with shared domain / acquisition / control-plane /
webapp separation

**Performance Goals**: worldline request for a 10,000-event entity under 3 seconds at
p95; coverage query under 1 second at p95; relation derivation over 10,000 events
without a hard size failure

**Constraints**: no generative model may decide admission, event identity, temporal
relations or completeness; no raw evidence mutation; tenant isolation on every read and
write; no unbounded retry or backlog growth; payload refs only

**Scale/Scope**: at least 10,000 events per entity; all currently advertised archive
partitions; per-run budgets configurable and operator-chosen

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle / Gate | Applicable | Status | Notes |
| --- | --- | --- | --- |
| I. Observation-immutable evidence substrate | Yes | PASS | Observations remain immutable and content-addressed. The new `cc.observation` kind adds identity and retrievability; it does not permit mutation. FR-016, FR-020. |
| II. Evidence-first | Yes | PASS | Each assertion carries a provenance chain to the raw source record; each event carries evidence references. Splitting one capture record into stages strengthens traceability. FR-016, FR-022. |
| III. Projection-first knowledge architecture | Yes | PASS | Worldline, relations and state transitions remain rebuildable projections over accepted assertions. No projection becomes a source of truth. |
| IV. No single store / graph / score | Yes | PASS | PostgreSQL remains the publication authority; no universal graph is introduced; admission, relevance and structural significance stay separate fields. |
| V. Plugability by contract | Yes | PASS | Query planning, frontier storage, observation writing, assertion projection and worldline building are defined behind contracts. No vendor types in domain logic. |
| VI. Process-centric | Yes | PASS | The user still creates an entity; reconstruction is an automatic consequence inside the investigation lifecycle and its budgets. |
| VII. Security-first | Yes | PASS | Tenant isolation enforced on every new read and write (FR-039); no new egress path beyond the existing archive client; existing SSRF and transport protections reused unchanged. |
| Invariant 2: Mention != Candidate != Entity | Yes | PASS | The new chain models mention, candidate and entity as distinct identified stages. FR-015. |
| Invariant 3: Assertion != truth | Yes | PASS | Only admitted assertions produce events; admission outcome is stored per assertion and never inferred. FR-017, FR-018. |
| Invariant 7: Admission != Priority | Yes | PASS | Queue priority and admission decision remain separate fields; the budget affects scheduling only, never acceptance. FR-008, FR-017. |
| Invariant 12: projections rebuildable from durable evidence | Yes | PASS | The worldline is rebuildable from accepted assertions alone (FR-022) and the frontier is durable. |
| Backpressure | Yes | PASS | Exhausting a budget defers work and reports it rather than expanding a backlog. FR-008, FR-014. |
| Retry budgets | Yes | PASS | Bounded attempts per frontier entry and per dispatch claim, with explicit lease expiry. FR-010, FR-027. |
| Dead letter / quarantine preserved | Yes | PASS | Rejected and quarantined claims are retained with decision, reasons, score vector and version for replay. FR-018. |
| Idempotency | Yes | PASS | Fingerprint idempotency retained; dispatch is idempotent; prepared work is replayed exactly. FR-030, FR-032. |
| No MVP/mini-architecture | Yes | PASS | All planes touched by the pipeline are extended within their existing contracts; no new plane is introduced. |
| ADR governance | Yes | PASS WITH PREREQUISITE | Frontier architecture, outbox leasing, sequence allocation and relation indexing are architectural decisions requiring an accepted ADR before implementation. |
| Migration safety | Yes | PASS WITH PHASE 0 GATE | Revision 014 is treated as applied. A new forward-only revision is required, verified on both fresh install and upgrade paths (FR-033, SC-012). |

**Gate result**: No constitutional violation and no unjustified complexity exception.
Implementation is blocked until the frontier, outbox-lease, sequence-allocation and
relation-index ADRs are accepted, and until the migration is verified on both paths.

## Architecture

```text
entity creation (single transaction)
  -> entity row
  -> reconstruction request row (PENDING, available_at=now)

relay / worker
  -> claim request with lease (available_at <= now, lease not expired)
  -> dispatch workflow (idempotent by request id)

materialization activity
  -> SourceQueryPlanner: EntitySearchSurface -> SourceQuerySet (multi-route, deduped,
     unsupported routes declared with reason codes)
  -> FrontierStore: per-entity, run-independent frontier of unexhausted work
       per-run budget selects a deterministic subset, leaves the rest OPEN
  -> for each selected frontier entry (route x partition x page):
       Common Crawl index query
         -> confirmed-empty?       -> mark EXHAUSTED
         -> transient error?       -> stay RETRYABLE, bounded attempts
         -> no forward progress?   -> stop partition, mark EXHAUSTED_NO_PROGRESS
         -> hits                   -> dedupe by locator
              -> WARC range GET -> parse -> deterministic extraction
              -> Observation (cc.observation)      [always, even with no claims]
              -> Candidate -> Assertion (entity.assertion) + Admission Decision
              -> admitted assertions only:
                     Temporal Event (entity.event) -> Temporal Relation
                     -> Entity State Transition
              -> rejected/deferred/quarantined: persisted, retrievable, contributes nothing
       frontier entry -> EXHAUSTED when the partition is confirmed done

publication
  -> only when every frontier entry for the entity is terminal
  -> counts of accepted/rejected/deferred/quarantined recorded
  -> atomic head advance, previous publication retained on failure
  -> worldline rebuilt from accepted assertions (deterministic, order-independent)
  -> relations via indexed sweep-line + ordered adjacency, pairwise kept as test oracle

reads
  -> coverage report, query set, observations, assertions, events, worldline
  -> all tenant-isolated, all labelled with completeness verdict and staleness
```

### Unit of materialization

```text
WARC capture
  -> Observation            (immutable, content-addressed, always written)
       -> Candidate         (proposed relation from extraction)
            -> Assertion    (normalized claim with interval + precision)
                 -> Admission Decision
                      ACCEPT_*   -> Temporal Event -> Temporal Relation -> State Transition
                      REJECT / DEFER / QUARANTINE -> persisted only, contributes nothing
```

The previous chain produced one `cc.capture` record whose payload nested every relation
and decision. That shape is retained for backward compatibility, but it is no longer
the unit the worldline folds over.

### Budget semantics

| Setting | Previous meaning | New meaning |
| --- | --- | --- |
| `CC_MAX_CRAWLS` | hard cap on partitions, silently truncating history | per-invocation cap on partitions processed; unprocessed frontier entries stay OPEN |
| `CC_MAX_PAGES` | hard cap on pages per partition | per-invocation cap on pages per partition; remaining pages stay OPEN |
| `CC_PAGE_LIMIT` | results per page | unchanged, but paging continues across invocations until the partition is confirmed exhausted |

When a budget is hit, the run result carries `complete: false` and a non-empty
`remaining_work`, and the worldline is labelled incomplete. This is the core semantic
change and is measured by SC-002.

### Publication boundary

1. Confirm every frontier entry for the entity is in a terminal state.
2. Replay accepted assertions under a run identity.
3. Build candidate events, relations and state transitions deterministically.
4. Compare expected coverage and every canonical fingerprint.
5. Advance the publication head in one transaction.
6. Publish output events from the outbox after commit.
7. Keep the previous valid publication available on any later failure.

No cross-system distributed transaction is assumed. PostgreSQL is the publication
authority. A run that cannot satisfy step 1 publishes nothing new and reports
`partial`, with the failing partitions named.

## Project Structure

### Documentation (this feature)

```text
specs/015-worldline-reconstruction/
в”њв”Ђв”Ђ spec.md
в”њв”Ђв”Ђ plan.md                    # This file
в”њв”Ђв”Ђ research.md                # Phase 0 output
в”њв”Ђв”Ђ data-model.md              # Phase 1 output
в”њв”Ђв”Ђ quickstart.md              # Phase 1 output
в”њв”Ђв”Ђ contracts/
в”‚   в”њв”Ђв”Ђ service-contracts.md
в”‚   в”њв”Ђв”Ђ api.md
в”‚   в”њв”Ђв”Ђ events.md
в”‚   в””в”Ђв”Ђ operations.md
в”њв”Ђв”Ђ checklists/
в”‚   в””в”Ђв”Ђ requirements.md
в””в”Ђв”Ђ tasks.md                   # Phase 2 output
```

### Source Code (planned)

```text
apps/
в”њв”Ђв”Ђ acquisition/
в”‚   в”њв”Ђв”Ђ entity_search.py                     # EntitySearchSurface (existing, extended)
в”‚   в””в”Ђв”Ђ source_query_set.py                  # NEW: SourceQuery, SourceQuerySet, planner
в”њв”Ђв”Ђ shared/
в”‚   в”њв”Ђв”Ђ domain/
в”‚   в”‚   в”њв”Ђв”Ђ temporal_worldline.py            # extended: assertion-level fold, indexed relations
в”‚   в”‚   в”њв”Ђв”Ђ temporal_worldline_store.py      # extended: level-aware reads
в”‚   в”‚   в””в”Ђв”Ђ worldline_relations_index.py     # NEW: sweep-line + ordered adjacency
в”‚   в”њв”Ђв”Ђ network/
в”‚   в”‚   в”њв”Ђв”Ђ commoncrawl.py                   # exhaustion-signal classification
в”‚   в”‚   в””в”Ђв”Ђ range_pull.py                    # unchanged
в”‚   в””в”Ђв”Ђ events/                              # event envelope additions
в”њв”Ђв”Ђ interpretation/                          # candidate/assertion emission
в”њв”Ђв”Ђ admission/                               # decision emission (authority, unchanged)
в””в”Ђв”Ђ control-plane/
    в”њв”Ђв”Ђ db/
    в”‚   в”њв”Ђв”Ђ schema.py                        # new tables/columns
    в”‚   в”њв”Ђв”Ђ migrations/versions/015_worldline_reconstruction.py   # NEW forward-only
    в”‚   в”њв”Ђв”Ђ source_query_store.py            # NEW
    в”‚   в”њв”Ђв”Ђ reconstruction_frontier.py       # NEW per-entity frontier
    в”‚   в”њв”Ђв”Ђ materialization_outbox.py        # lease + reclaim + available_at filter
    в”‚   в”њв”Ђв”Ђ entity_stream.py                 # atomic sequence allocation
    в”‚   в””в”Ђв”Ђ temporal_materialization.py      # coverage-aware publication
    в”њв”Ђв”Ђ services/
    в”‚   в”њв”Ђв”Ђ cc_cursor_materialization.py     # frontier-driven execution
    в”‚   в”њв”Ђв”Ђ capture_interpretation.py        # observation/assertion emission
    в”‚   в”њв”Ђв”Ђ entity_pipeline.py               # route fan-out wiring
    в”‚   в”њв”Ђв”Ђ materialization_outbox_relay.py  # lease-aware relay
    в”‚   в””в”Ђв”Ђ coverage_report.py               # NEW
    в”њв”Ђв”Ђ workflows/
    в”‚   в”њв”Ђв”Ђ temporal_materialization.py      # frontier-driven activity
    в”‚   в””в”Ђв”Ђ worker.py
    в””в”Ђв”Ђ api/routes/entities.py               # coverage/queries/observations/assertions/events
```

**Structure Decision**: the existing single monorepo with shared / acquisition /
control-plane / webapp separation is retained. New modules are added inside existing
packages that already own the concern; no new top-level project, service or
architectural layer is introduced. This satisfies the "No MVP/mini-architecture"
constraint while keeping the change reviewable.

## Phase Strategy

User stories are ordered so that each phase is independently valuable and
independently verifiable. US6 is retained in scope by explicit decision, but scheduled
last because the honest full-history capability of US1 is what makes scale necessary,
and because the relation oracle must exist before the indexed algorithm can be proven
equivalent to it.

| Phase | Stories | Deliverable | Gate |
| --- | --- | --- | --- |
| 0 | none | ADRs accepted; forward-only migration verified on both paths | No code before migration proof |
| 1 | US2 | `SourceQuerySet` multi-route execution replaces single-plan execution | AS-006..AS-009 pass offline |
| 2 | US1 | Per-entity durable frontier; budgets defer instead of truncating | AS-001..AS-005 pass offline and live |
| 3 | US3 | Observation / assertion / event separation with admission gating | AS-010..AS-014 pass; no rejected claim yields an event |
| 4 | US4, US5 | Transactional entity+request, dispatch leases, coverage reporting | AS-015..AS-021 pass on live PostgreSQL |
| 5 | US6 | Indexed relation derivation replacing the quadratic pair loop | AS-022..AS-024 pass; oracle equivalence holds at 10k events |

Phases 1 and 2 are ordered because frontier entries are keyed by query route: the
frontier cannot be built before the query set exists. Phase 3 depends on both because
assertions reference the observations produced by frontier execution. Phase 4 is
independent of the projection semantics and could proceed in parallel with phase 3.
Phase 5 must be last.

## Complexity Tracking

> No constitutional violations require justification. The following entries are recorded
> because they are non-obvious engineering risks with cheaper-looking alternatives that
> were rejected on correctness grounds.

| Concern | Chosen approach | Cheaper alternative rejected because |
| --- | --- | --- |
| Frontier storage | New per-entity, run-independent frontier table alongside the existing run-keyed cursor | Re-keying the existing cursor would discard resume state for in-flight runs and break the crash-recovery guarantee already verified live |
| Relation derivation | Sweep-line plus ordered adjacency, with the pairwise implementation retained as a test oracle | Raising `max_events` would leave the quadratic term intact, which is the actual limit identified |
| Uniqueness of requests | Unique constraint on the active request per entity and identity fingerprint | An application-level check-then-insert races under concurrent entity creation |
| Sequence allocation | Dedicated per-entity counter row with `UPDATE ... RETURNING` | Client-side `max(sequence) + 1` is the current code and is racy under concurrent runs |
| Unsupported routes | Explicit declaration with reason codes, no new providers | Implementing phone, username or email providers would invent data sources beyond the agreed scope |

