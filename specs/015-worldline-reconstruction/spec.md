# Feature Specification: Worldline Reconstruction

**Feature Branch**: `015-worldline-reconstruction`
**Created**: 2026-09-25
**Status**: Draft
**Relationship**: Extends `014-temporal-materialization`. Closes the four structural gaps found in review of the working Common Crawl vertical slice.

**Input**: User description: "Run SpecKit for the next architecture iteration. The
current pipeline is a real vertical slice вЂ” Common Crawl index в†’ WARC range GET в†’
WARC parser в†’ deterministic extraction в†’ admission в†’ durable cursor/stream в†’
worldline вЂ” but four architectural defects prevent calling it a correct end-to-end
system. (1) The search surface is multidimensional while execution is
one-dimensional: only a single `cc_plan` is executed, so an identity carrying a
URL, domain, alias, username and email only ever uses one of them. (2) 'All
time' is still not all time: `max_crawls`, `max_pages` and `CC_PAGE_LIMIT` act as
a semantic limit on history instead of a scheduler budget over a persistent
frontier. (3) The unit of materialization is still the capture: relations, claims
and admission decisions are nested JSON inside one `cc.capture` record, so one
WARC becomes one worldline event and the worldline mostly says 'a capture happened
at T' rather than 'the entity's property changed at T'. (4) Admission is real but
its result does not gate admission of the stream record, so a rejected claim can
live inside an accepted record. In addition, entity creation is not the
transactional boundary of the outbox, and pairwise worldline relation derivation
cannot scale past a few hundred events. The requested next step is a change of the
unit of materialization: WARC в†’ Observation в†’ Mention/Candidate в†’ Assertion в†’
Admission в†’ Temporal Event в†’ Temporal Relation в†’ Entity state transition в†’
Worldline, with crawl and page caps turned into execution budget only."

## Problem Statement

Why this feature exists, in the user's current reality:

- A researcher creates an entity with a URL, a domain, an alias, a username and an
  email. The system records all of them, then executes only one of them.
- A researcher asks for the whole history. The system returns a bounded slice and
  cannot say what part of history it skipped, because the skip is decided by an
  in-memory slice of the advertised archive list.
- A researcher sees a hundred extracted relations in the interface and one timeline
  entry, because the relations, claims and admission decisions are nested inside a
  single capture record.
- A rejected claim is visible inside a record the worldline treats as accepted
  evidence of the entity's history.
- A reviewer asks whether the entity was ever reconstructed, and the answer depends
  on whether an in-process fallback happened to run rather than on the existence of
  a durable request.

After this feature the same researcher gets every applicable search route
executed, a resumable frontier that is eventually exhaustive, a timeline of
property changes in which every event is an admitted assertion with its own
identity and provenance, rejected and quarantined claims that stay visible but are
never asserted as entity history, and an honest queryable statement of what has
been covered and what remains.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reconstruct the Whole Available History (Priority: P1)

An analyst creates an entity and the platform automatically reconstructs that
entity's history across the entire available archive. Work continues across
scheduled runs, resumes after interruption, and is never silently truncated. The
analyst can always see how far reconstruction has reached, what remains, and
whether the presented history is complete or still partial.

**Why this priority**: Without exhaustive and resumable coverage, every downstream
conclusion is a statement about an arbitrary slice of the past. This is the
difference between searching a few captures and reconstructing a worldline.

**Independent Test**: Configure a small per-run budget against an archive with many
partitions, run the scheduler repeatedly, and verify that all partitions eventually
become exhausted, that each run reports its own position and remaining work, that
interrupting and restarting loses no work and re-fetches nothing already recorded,
and that the history is labelled complete only when the frontier is exhausted.

**Acceptance Scenarios**

1. **AS-001 - Budget does not truncate history**: **Given** an archive exposing more
   partitions than a single run's budget allows, **When** the scheduler runs
   repeatedly, **Then** every partition is eventually processed and no partition is
   permanently skipped because a per-run limit was reached.
2. **AS-002 - Honest partial state**: **Given** a run stops because its budget is
   exhausted, **When** the analyst views the entity, **Then** coverage shows the
   current position and the remaining work, and the history is explicitly marked
   incomplete rather than presented as final.
3. **AS-003 - Empty page is not exhaustion**: **Given** a partition returns no
   results on a page, **When** the frontier evaluates that partition, **Then** the
   partition is not marked exhausted until absence is confirmed by the provider
   response, and a genuinely empty partition is marked exhausted without
   fabricating observations.
4. **AS-004 - Transient failure is not exhaustion**: **Given** a partition request
   fails with a transport or server error, **When** the run ends, **Then** that
   partition remains open and retryable, and the run is not reported as complete.
5. **AS-005 - Resume without rework**: **Given** a process interruption in the middle
   of a partition, **When** work resumes, **Then** it continues from the persisted
   frontier position, records no duplicate evidence, and re-fetches nothing that was
   already durably recorded.

---

### User Story 2 - Execute Every Search Route (Priority: P1)

An entity is described by several kinds of identifier at once: an exact URL, a site
domain, a name, a former name, an alias, a username, an email address, a phone
number, and possibly source or locale constraints. The platform executes each
applicable route as an independent source query instead of choosing a single winner
by priority.

**Why this priority**: The identity evidence already collected is the main reason to
run acquisition at all. Discarding eight of nine routes because a URL exists throws
away the value of the surface and biases the reconstructed history toward one site.

**Independent Test**: Build an identity with a URL, a domain, an alias, a former
name, a username and an email, then verify that every supported route produced its
own query, that queries are stable and deduplicated, that a capture found by two
routes is stored once with both route references, and that a route which cannot be
executed is listed as unsupported with a reason instead of disappearing.

**Acceptance Scenarios**

1. **AS-006 - One query per route**: **Given** an identity with several route types,
   **When** a reconstruction run starts, **Then** the executed query set contains an
   independent query for each supported route - exact URL, URL prefix, domain, name
   and alias, username-derived, email-derived, phone-derived - and the result is not
   a single prioritized query.
2. **AS-007 - Stable, deduplicated queries**: **Given** two identity attributes that
   normalize to the same route value, **When** the query set is built, **Then** it
   contains one query carrying both provenance references, and the query set is
   byte-identical for equivalent identities regardless of input ordering.
3. **AS-008 - Unsupported routes are visible**: **Given** an identity route that
   cannot be executed by the currently available providers, **When** the query set is
   built, **Then** that route appears as explicitly unsupported with a reason and is
   not silently dropped.
4. **AS-009 - Per-route budgets**: **Given** more routes than one run's budget allows,
   **When** the run executes, **Then** it processes a deterministic subset, records
   which routes remain, and resumes with the rest.

---

### User Story 3 - Read a Worldline of Property Changes, Not of Captures (Priority: P1)

An analyst opens an entity's worldline and sees what the entity's properties and
relations were believed to be at each point in time, with the admitted assertion
that carries each change, the observation and evidence behind it, the admission
decision that allowed it, and the resulting before and after state. The analyst can
distinguish a statement derived from an admitted claim from a raw observation that
was seen but not admitted.

**Why this priority**: The current worldline reports that a capture happened. An
investigation needs to know when and why a property became known, which is the
difference between a capture log and a reconstructed history.

**Independent Test**: Materialize a known history in which one capture yields several
relations and one relation is rejected, then verify that the worldline contains one
event per admitted assertion with subject, predicate, object, interval, precision,
evidence, admission decision and before/after state; that the rejected relation
produces no event; and that the raw observation remains retrievable as a separate,
clearly labelled object.

**Acceptance Scenarios**

1. **AS-010 - One event per admitted assertion**: **Given** a capture whose
   interpretation yields several admitted relations, **When** the worldline is built,
   **Then** each admitted relation appears as its own event with subject, predicate,
   object, interval, precision, evidence reference, admission decision and
   before/after state.
2. **AS-011 - Rejected claims never become events**: **Given** a capture whose
   interpretation yields a rejected, deferred or quarantined claim, **When** the
   worldline is built, **Then** that claim produces no temporal event and no state
   transition, and the decision remains retrievable with its reason codes.
3. **AS-012 - Observations remain addressable**: **Given** any admitted event, **When**
   the analyst follows its evidence reference, **Then** the underlying observation,
   source record identifier, content hash and retrieval locator are resolvable, and
   the observation can be viewed independently of any assertion.
4. **AS-013 - Deterministic history**: **Given** the same admitted assertions supplied
   in a different order, **When** the worldline is rebuilt, **Then** the events, their
   ordering, their state transitions and the resulting fingerprint are identical.
5. **AS-014 - Empty and contradictory input**: **Given** an interpretation that yields
   no admitted assertion, **When** the worldline is built, **Then** the entity's
   worldline is explicitly empty for that interval, the observation is still recorded,
   and no property is asserted.

---

### User Story 4 - Entity Creation Durably Requests Reconstruction (Priority: P2)

An operator creates an entity. Whether or not any worker is available, the request
for reconstruction becomes part of the same durable commit as the entity itself, so
a crash cannot leave an entity that nobody will ever reconstruct, and a duplicated
request cannot start a duplicated reconstruction.

**Why this priority**: Today the request to reconstruct is a best-effort call made
after the entity already exists. That is a silent data-loss path for the primary
user action of the platform.

**Independent Test**: Create an entity while no worker is running, then inspect the
durable request store and confirm exactly one pending request bound to the entity;
then run the dispatch relay twice concurrently and confirm the reconstruction starts
exactly once.

**Acceptance Scenarios**

1. **AS-015 - Atomic entity and request**: **Given** an entity creation request,
   **When** it succeeds, **Then** the entity and its pending reconstruction request are
   committed together, and a failure of either leaves neither.
2. **AS-016 - No orphan entity**: **Given** a crash immediately after entity creation,
   **When** the system restarts, **Then** a durable pending request exists for the
   entity and the reconstruction is eventually started without any external trigger.
3. **AS-017 - Duplicate suppression**: **Given** the same creation or a replayed
   request submitted more than once, **When** requests are persisted, **Then** only one
   active reconstruction request exists per entity and per identity fingerprint.
4. **AS-018 - Recoverable dispatch**: **Given** a worker takes a request and dies
   before completing it, **When** another worker becomes available, **Then** the
   request becomes claimable again after its lease expires and is dispatched again
   without creating a second entity or a duplicated published generation.

---

### User Story 5 - Inspect Coverage and Partial Failures Honestly (Priority: P2)

An operator or analyst can see, for one entity, which archive partitions and pages
have been covered, which are in progress, which failed and why, and whether the
published worldline is complete. A run that failed for one partition while succeeding
for others is reported as partial and is never presented as a finished
reconstruction.

**Why this priority**: A partial result published as final is worse than no result,
because downstream conclusions inherit a completeness claim that is false.

**Independent Test**: Force one partition to fail while others succeed, then verify
that coverage lists the failure with its reason, that the run status is partial, that
the worldline is marked incomplete, and that the previous valid publication remains
available.

**Acceptance Scenarios**

1. **AS-019 - Partial failure is visible and not final**: **Given** one partition fails
   while others succeed, **When** the run finishes, **Then** coverage lists the failed
   partition and its reason, the run is reported as partial, and no completed result
   is published as a final reconstruction.
2. **AS-020 - Last valid publication retained**: **Given** a previously published
   worldline and a subsequent failing run, **When** the analyst requests the
   worldline, **Then** the last valid publication is returned and is marked as not
   reflecting the newest evidence.
3. **AS-021 - Coverage query**: **Given** an entity with several runs, **When** coverage
   is requested, **Then** the response lists partitions and pages with their states,
   the remaining work, and the last progress timestamp.

---

### User Story 6 - Scale the Worldline to Large Histories (Priority: P3)

An analyst opens an entity with a long history, thousands of events across hundreds
of partitions, and the platform renders the timeline and its relations in bounded
time without a hard event ceiling, while remaining deterministic and correct for
small and large histories alike.

**Why this priority**: The current relation derivation is quadratic and refuses inputs
above a few hundred events. That makes the honest full-history capability of User
Story 1 unusable exactly where it matters most.

**Independent Test**: Build a history of at least ten thousand events with a
deterministic distribution of overlapping and disjoint intervals, then verify that
relations are derived without error, that the result matches the small-scale reference
implementation exactly, and that response time stays within the stated budget.

**Acceptance Scenarios**

1. **AS-022 - Large histories succeed**: **Given** an entity with at least ten thousand
   events, **When** the worldline and its relations are requested, **Then** the request
   completes successfully within the stated performance budget and without a
   size-related failure.
2. **AS-023 - Identical semantics at scale**: **Given** the same events supplied in
   small and large batches, **When** relations are derived, **Then** the derived
   relation set is identical to the small-batch result.
3. **AS-024 - Bounded, explained degradation**: **Given** a history exceeding the
   configured relation budget, **When** relations are derived, **Then** the system
   degrades in a documented and explicitly labelled way and reports what was not
   computed, rather than failing or silently truncating.

### Edge Cases

- An identity has no executable route at all: the run fails with an explicit
  no-executable-query reason instead of producing an empty worldline that looks like
  a negative finding.
- Two different routes resolve to the same byte range: one observation is stored and
  both route references are kept.
- The archive list changes between runs, with a new partition appearing or one
  withdrawn: already-exhausted partitions are not re-exhausted and the new partition
  is added to the frontier as open work.
- A partition's index shard is temporarily unavailable while the partition is
  advertised: this is a transient failure, not exhaustion.
- A WARC record is a revisit, is truncated, or fails its payload digest: the capture
  is marked untrustworthy and cannot by itself produce an admitted assertion.
- A capture yields only rejected claims: the observation is recorded, the worldline
  gains no event, and the run is not reported as a discovery failure.
- A capture yields more claims than the per-page admission budget: the remainder is
  deferred as explicit work rather than dropped.
- The process dies between persisting prepared work and appending it: the retry
  replays exactly the prepared work and does not re-fetch from the archive.
- The relay dies after claiming work but before starting the workflow: the claim lease
  expires and the work is reclaimed.
- A publication is attempted while another publication for the same entity is in
  flight: the second is serialized, not interleaved.
- The same entity identifier shape exists in two tenants: neither can read or
  reconstruct the other's frontier, evidence or worldline.
- Two concurrent runs for the same entity race on the stream sequence: sequence
  assignment is atomic and no record is lost or duplicated.
- The archive returns a page identical to a previously seen page because the offset is
  ignored: the run detects no forward progress and stops paging instead of looping.

## Requirements *(mandatory)*

### Source Query Planning

- **FR-001**: The system MUST derive an ordered, deduplicated set of source queries
  from every dimension of an entity's search surface, not from a single prioritized
  dimension.
- **FR-002**: The derived query set MUST be deterministic and independent of the
  ordering in which identity attributes were supplied.
- **FR-003**: Two identity attributes that normalize to the same executable query MUST
  produce one query carrying both provenance references.
- **FR-004**: Every identity dimension that cannot be executed by the currently
  available providers MUST be reported as unsupported with a reason and MUST NOT be
  silently discarded.
- **FR-005**: The system MUST preserve a documented, inspectable representation of the
  legacy single-plan behaviour for deployments that depend on it, while the default
  reconstruction path executes the full query set.
- **FR-006**: The system MUST record, for each run, which query routes were executed,
  which remain pending, and which are unsupported.

### Persistent Historical Frontier

- **FR-007**: The system MUST maintain a durable, tenant-scoped frontier of
  unexhausted work per entity, covering every archive partition and page that could
  yield evidence.
- **FR-008**: Per-run crawl, page, capture and query limits MUST be enforced only as a
  scheduler budget over that frontier and MUST NOT define, truncate or terminate the
  historical record.
- **FR-009**: A partition MUST be marked exhausted only on confirmed absence of further
  results from the provider, and never on an empty, transient or failed response.
- **FR-010**: A transient provider failure MUST leave the affected frontier entry open
  and retryable within a bounded retry budget.
- **FR-011**: The system MUST resume from the persisted frontier position after
  interruption without re-fetching work that is already durably recorded.
- **FR-012**: The system MUST detect absence of forward progress while paging and MUST
  stop that partition instead of looping indefinitely.
- **FR-013**: The frontier MUST be extended when newly advertised archive partitions
  appear, and MUST NOT re-open already exhausted partitions.
- **FR-014**: The system MUST report, per entity, the covered partitions and pages, the
  remaining work, and whether the reconstructed history is complete.

### Materialization Unit and Stream Separation

- **FR-015**: The system MUST represent the unit of materialization as a chain of
  independently identified stages - observation, mention or candidate, assertion,
  admission decision, temporal event, temporal relation, entity state transition -
  rather than a single capture record.
- **FR-016**: Each observation, assertion and temporal event MUST carry its own stable
  identity, tenant scope and provenance chain back to the raw source record.
- **FR-017**: Only assertions whose admission decision is in the accepted set MAY
  produce temporal events, temporal relations or entity state transitions.
- **FR-018**: Rejected, deferred and quarantined claims MUST be preserved and
  retrievable with their decision, reason codes and score vectors, and MUST NOT
  contribute to the accepted worldline.
- **FR-019**: An observation that yields no admitted assertion MUST still be recorded
  and retrievable, and the corresponding worldline interval MUST be represented as
  explicitly yielding no change.
- **FR-020**: Capture-level provenance, including source, retrieval locator, crawl
  partition, page, content hash and record identifiers, MUST remain available without
  being the sole carrier of interpretation results.
- **FR-021**: The system MUST distinguish an observation-level timeline from an
  assertion-level timeline and MUST label each explicitly.
- **FR-022**: The worldline MUST be rebuildable from accepted assertions alone, and
  MUST be byte-identical for identical assertion sets regardless of input ordering.

### Admission-Gated Publication

- **FR-023**: A work item that produced no admitted assertion MUST NOT be published as
  a completed reconstruction result.
- **FR-024**: Publication MUST record the accepted, rejected, deferred and quarantined
  counts of the work it covers.
- **FR-025**: The system MUST NOT report a run as complete while any frontier entry for
  that entity remains open, retryable or failed.

### Transactional Request and Reliable Dispatch

- **FR-026**: Entity creation MUST commit the entity and its pending reconstruction
  request in a single durable transaction.
- **FR-027**: A request claimed for dispatch MUST be bound to a lease, and a claim
  whose lease has expired MUST be reclaimable by another worker.
- **FR-028**: Claiming a request MUST respect its scheduled availability time so that
  backoff-delayed work is not claimed early.
- **FR-029**: A partial failure while dispatching a batch of requests MUST NOT be
  reported as a successful dispatch of the whole batch.
- **FR-030**: Dispatch MUST be idempotent: the same request MUST NOT start two
  concurrent reconstructions of the same entity.

### Concurrency and Consistency

- **FR-031**: Stream sequence assignment MUST be atomic under concurrent writers for
  the same entity, and MUST NOT drop or duplicate a record.
- **FR-032**: A crash between persisting prepared work and appending it MUST be
  recoverable by replaying exactly the prepared work.
- **FR-033**: Schema changes introduced by this feature MUST be delivered as new,
  forward-only migrations that apply cleanly both to a fresh installation and to an
  installation that already applied the earlier revision.

### Scale of Worldline Derivation

- **FR-034**: Temporal relation derivation MUST NOT use an algorithm whose cost grows
  quadratically with the number of events as its fundamental limit.
- **FR-035**: Relation derivation MUST use indexed interval and ordered adjacency
  structures, and MUST produce results identical to a reference pairwise
  implementation on the same inputs.
- **FR-036**: When a configured relation budget is exceeded, the system MUST degrade in
  a documented and explicitly labelled manner, MUST report what was not computed, and
  MUST NOT fail the request or silently truncate.
- **FR-037**: The system MUST support deterministic worldline construction for at least
  ten thousand events for one entity within the stated performance budget.

### Observability and Access

- **FR-038**: Operators MUST be able to query, per entity and per run, the frontier
  state, per-partition outcomes with failure reasons, dispatch state and last
  progress time.
- **FR-039**: All frontier, evidence, request and worldline reads and writes MUST be
  tenant-isolated.
- **FR-040**: The last valid published worldline MUST remain available when a newer run
  fails, and MUST be labelled as not reflecting the newest evidence.

### Key Entities

- **Source Query**: one executable acquisition intent derived from one identity
  dimension, with its route kind, normalized value, provider, execution status and
  provenance references.
- **Query Set**: the ordered, deduplicated collection of source queries for one
  entity, together with the unsupported routes and their reasons.
- **Frontier Entry**: the durable state of one unit of unexhausted acquisition work
  for one entity, including its partition, page, query, status, attempts, last error,
  progress marker and result reference.
- **Observation**: an immutable, content-addressed record of one retrieved source
  artefact, with its retrieval locator, content hash, capture time and source record
  identifiers.
- **Candidate**: a proposed identity or relation produced by extraction from an
  observation, carrying its own identity and the observation that produced it.
- **Assertion**: a normalized claim about a subject and object with a predicate,
  valid-time interval, precision and a provenance chain to its evidence.
- **Admission Decision**: the outcome of evaluating an assertion, with its reason
  codes, score vector, policy version and evidence references.
- **Temporal Event**: an accepted change in an entity's asserted state, with its
  interval, precision, participants, before and after state, evidence references and
  confidence.
- **Temporal Relation**: a derived or declared ordering or overlap between two
  temporal events, with its kind, lag and derivation basis.
- **Entity State Transition**: the resulting before and after asserted state of an
  entity at a point in time, derived only from accepted assertions.
- **Reconstruction Request**: the durable intent to reconstruct an entity's history,
  with its state, schedule, lease, attempt count and last error.
- **Coverage Report**: the per-entity summary of covered and remaining frontier work,
  per-partition outcomes, and the completeness verdict for the published worldline.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For an entity whose identity provides at least four distinct executable
  route types, 100% of supported routes appear in the executed query set and 0 routes
  are silently discarded.
- **SC-002**: Under a per-run budget smaller than the total available historical work,
  100% of frontier entries reach a terminal exhausted state after repeated runs, and 0
  partitions remain permanently unprocessed.
- **SC-003**: Across forced interruptions, 100% of completed work is recovered by
  resume, and 0 already-recorded observations are re-fetched or duplicated.
- **SC-004**: Across forced transient provider failures, 0 partitions are recorded as
  exhausted, and 0 runs are reported complete while any frontier entry remains open.
- **SC-005**: 100% of temporal events correspond to an accepted assertion, and 0
  rejected, deferred or quarantined claims produce a temporal event, a temporal
  relation or an entity state transition.
- **SC-006**: For identical accepted-assertion sets supplied in different orders, 100%
  of produced worldline documents, orderings, state transitions and fingerprints are
  identical.
- **SC-007**: A worldline containing at least ten thousand events is derived
  successfully with no size-related failure, and its relation set matches a reference
  pairwise implementation exactly.
- **SC-008**: 95% of worldline requests for a ten-thousand-event entity complete within
  3 seconds, and 95% of coverage queries complete within 1 second.
- **SC-009**: 100% of entity creations leave exactly one durable reconstruction request,
  verified by inspecting durable state with no worker running.
- **SC-010**: In a crash-and-reclaim test of the dispatch path, 100% of abandoned claims
  are reclaimed after lease expiry, and 0 entities are reconstructed twice
  concurrently.
- **SC-011**: Across concurrent writers for one entity, 0 stream records are lost or
  duplicated and 0 sequence collisions occur.
- **SC-012**: A fresh installation and an installation upgraded from the previous
  schema revision both reach the same schema state, verified by migration on both
  paths.
- **SC-013**: 100% of cross-tenant probes are denied, and 0 cross-tenant rows are
  returned by frontier, evidence, request or worldline reads.
- **SC-014**: When a run fails after a valid publication exists, 100% of worldline
  reads return the last valid publication with an explicit staleness label.

## Assumptions

- Feature 014 supplies the deterministic materialization, publication head and revision
  model; this feature changes the unit of materialization and the execution frontier
  rather than replacing the publication model.
- The real Common Crawl vertical slice that already exists - index discovery, byte-range
  retrieval, WARC parsing, deterministic extraction, admission, durable cursor, stream
  append, publication and worldline - is preserved and extended, not rebuilt, and no
  existing verified capability regresses.
- Deterministic extraction and the existing admission engine remain authoritative for
  whether a claim is accepted; this feature does not change their outcomes.
- The archive is treated as append-only over time: partitions already exhausted are never
  expected to yield new evidence, and newly advertised partitions extend coverage
  rather than invalidate it.
- Providers expose enough signal to distinguish "no more results" from "could not be
  determined"; where they do not, the system errs toward leaving work open.
- Per-run budgets remain configurable, because operational capacity is finite; the change
  is that exhausting a budget defers work instead of ending history.
- No generative or probabilistic model decides admission, event identity, temporal
  relations or completeness; all such outcomes remain deterministic and reproducible.
- Authentication, tenant resolution, role checks and audit plumbing already exist and are
  reused rather than redesigned.
- User interface changes are limited to exposing coverage, completeness, stream level and
  admission outcomes; a broader interface redesign is out of scope.
- Schema revision 014 is treated as already released; this feature ships new forward-only
  migrations rather than editing applied revisions.

## Out of Scope

- Replacing the archive provider itself, or adding providers beyond the existing Common
  Crawl integration.
- Changing extraction quality, adding new extractor families, or altering admission
  thresholds and scoring.
- Identity resolution semantics, candidate merging, and correlation policies.
- A general-purpose graph database, a new orchestration backbone, or a new universal
  knowledge store.
- Full historical reconstruction across non-Common-Crawl sources.
- A wholesale user interface redesign.

## Dependencies

- Feature 014 provides the publication head, revision identity and worldline contract
  that this feature preserves while changing the materialization unit.
- The existing Common Crawl client, byte-range transport and WARC parser provide the
  retrieval substrate that the frontier schedules.
- The existing extraction and admission modules provide the claims and decisions that this
  feature promotes into independently identified assertions and events.
- The existing durable outbox, cursor and stream repositories provide the persistence
  substrate extended by the lease, frontier and sequence guarantees.

## Risks

| Risk | Mitigation |
| --- | --- |
| Frontier growth makes exhaustive coverage unbounded in wall-clock time | Budgets defer rather than truncate, coverage is reported honestly, and operators choose budgets knowingly |
| Emitting one record per assertion multiplies write volume | Per-observation batching, single-transaction appends and idempotent fingerprints keep cost proportional to real evidence |
| Relation indexing changes existing worldline output | A reference pairwise implementation is retained as a test oracle and equivalence is asserted on shared inputs |
| Migrations on an already-deployed database | Forward-only migration verified on both a fresh install and an upgrade path from revision 014 |
| Event-level semantics change consumers of capture payloads | Capture provenance is preserved alongside the new levels and observation-level timelines remain available |

