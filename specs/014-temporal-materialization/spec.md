# Feature Specification: Temporal Entity Materialization

**Feature Branch**: `014-temporal-materialization`

**Created**: 2026-09-23

**Status**: Draft

**Input**: Materialize each dynamic entity invariant as a deterministic, queryable history of event-time windows and point-in-time views. Analysts and knowledge consumers must be able to determine what was known at a selected time, observe lifecycle and topology changes, incorporate late evidence without silent mutation, and rebuild any view from immutable source records. The feature preserves tenant isolation and complete provenance but does not resolve identity, alter evidence, or create a new source of truth.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Inspect an Entity's Timeline (Priority: P1)

An analyst opens an entity and views its complete event-time history, including active and dormant windows, lifecycle state, activity measures, relationship changes, evidence references, and the exact source cut represented by each view. The analyst can move between the latest valid view and a selected point in time.

**Why this priority**: A trustworthy historical view is the core user value. Without it, lifecycle signals and temporal analyses cannot be interpreted consistently.

**Independent Test**: Materialize a known event history containing multiple active windows and a dormant gap, then verify the timeline, latest view, and a selected historical view are correct and mutually consistent.

**Acceptance Scenarios**:

1. **AS-001 — Complete timeline**: **Given** an entity has events in several event-time windows, **When** the analyst requests its history, **Then** every covered window is shown in chronological order with its explicit lifecycle state, activity measures, relationship summary, evidence references, source cut, and completeness status.
2. **AS-002 — Honest gaps**: **Given** an entity has no events during one or more covered windows, **When** its history is requested, **Then** each gap is represented explicitly as dormant with no fabricated activity, relationship, or feature values.
3. **AS-003 — Point-in-time consistency**: **Given** views exist at several revisions, **When** the analyst selects a time or revision, **Then** the returned view represents exactly the records admitted through the selected source cut and does not expose later information.
4. **AS-004 — Reproducible history**: **Given** the same source records and materialization policy, **When** the entity is materialized more than once, **Then** every deterministic value and the view's verification fingerprint are identical.

---

### User Story 2 - Incorporate Late Information Safely (Priority: P1)

An analyst or data steward receives a late source record that belongs to an earlier event-time window. The system assigns it to the correct historical window, creates a visible revision where affected views depend on that record, and preserves the prior revision for audit and replay without changing the original evidence.

**Why this priority**: Real investigations contain delayed and out-of-order information. Incorrectly appending it or silently rewriting history would make temporal conclusions untrustworthy.

**Independent Test**: Materialize an ordered history, then supply an exact duplicate and a late event for an earlier window and verify idempotency, correct reassignment, dependency-aware revision, and preserved provenance.

**Acceptance Scenarios**:

1. **AS-005 — Late event**: **Given** later windows have already been materialized, **When** a valid event for an earlier window arrives, **Then** it is assigned by event time, all dependent views are revised, unaffected views remain unchanged, and the revision reason is visible.
2. **AS-006 — Exact duplicate**: **Given** a source record has already been incorporated, **When** the same record is received again, **Then** the materialized history and its revision count remain unchanged.
3. **AS-007 — Contradictory reuse**: **Given** the same source-record identity is presented with different content, **When** the record is processed, **Then** the conflicting representation is quarantined with a reason and retained for review rather than overwriting accepted history.
4. **AS-008 — Interrupted rebuild**: **Given** a rebuild stops partway through, **When** processing resumes, **Then** it completes without manual cleanup and produces the same result as an uninterrupted rebuild from the same source cut.

---

### User Story 3 - Consume an Aligned Temporal Feature Series (Priority: P2)

A scientific or analytical consumer receives lifecycle, activity, relationship, and structural feature series for an entity. Every feature value aligns to exactly one temporal window, carries provenance, and distinguishes unavailable values from measured zero-valued results.

**Why this priority**: Temporal analytics and topology features are valuable only when they are aligned to, and traceable through, the entity's materialized history.

**Independent Test**: Consume the materialized series for a fixture with active, insufficient-data, and dormant windows and verify one-to-one window alignment, explicit unknowns, structural-only labeling, and source traceability.

**Acceptance Scenarios**:

1. **AS-009 — Aligned series**: **Given** a materialized entity history, **When** a consumer requests its temporal feature series, **Then** lifecycle and eligible feature records align one-to-one with the history's windows in chronological order.
2. **AS-010 — Insufficient data**: **Given** a window lacks the minimum information required for a feature, **When** the series is produced, **Then** the feature is explicitly unavailable and is not replaced with zero, an estimate, or an inferred identity claim.
3. **AS-011 — Traceable analysis**: **Given** a structural feature value is presented, **When** its provenance is inspected, **Then** the consumer can identify the source records, source cut, policy version, window revision, and verification fingerprint used to produce it.

---

### User Story 4 - Operate and Audit Materialization (Priority: P2)

An operator monitors whether entity histories are fresh, complete, delayed, rebuilding, or degraded. A reviewer can determine who or what initiated a materialization change, which source cut it used, what was quarantined, and whether a rebuild reconciled with the expected result.

**Why this priority**: Silent staleness or partial publication would make otherwise deterministic views misleading to analysts.

**Independent Test**: Simulate normal processing, delayed processing, a failed run, and a quarantined record; verify status visibility, bounded retries, audit history, and complete isolation between tenants.

**Acceptance Scenarios**:

1. **AS-012 — Visible health**: **Given** processing is current, delayed, rebuilding, or degraded, **When** an operator checks materialization health, **Then** the status identifies the condition, latest source cut, completeness, age, and reason without presenting an incomplete view as current.
2. **AS-013 — Audited change**: **Given** a view is created, revised, quarantined, rejected, or promoted after rebuild, **When** the audit history is inspected, **Then** the action, reason, time, tenant, entity, revision, and source cut are recoverable.
3. **AS-014 — Tenant isolation**: **Given** two tenants have unrelated investigations, **When** either tenant requests or operates on entity histories, **Then** no data, status, count, timing, or existence information from the other tenant is disclosed.
4. **AS-015 — Load protection**: **Given** downstream demand exceeds available processing capacity, **When** work is admitted, **Then** processing slows at the appropriate boundary, retries remain bounded, and the system does not create an unbounded backlog or repeatedly amplify a failing input.

### Edge Cases

- An entity has one event, no events after its first event, or an event at a window boundary; each timestamp belongs to exactly one half-open window.
- A dormant gap is longer than one configured window; every covered dormant window remains explicit and no values are interpolated.
- Events arrive before their recorded occurrence time, far out of order, or after a historical view has already been used by another consumer.
- A late event affects an earlier window, a derived feature, and one or more later cumulative views; all affected revisions are identified consistently.
- Exact duplicates occur across retries, restarts, and rebuilds; they do not change counts, revisions, or source cuts.
- A malformed record, missing tenant, mixed-tenant history, ambiguous timestamp, or contradictory record reuse is quarantined without partially changing the accepted view.
- A source record refers to missing or inaccessible evidence; the relationship remains explicit as unavailable rather than being discarded or represented as negative evidence.
- A rebuild finds missing, extra, or divergent windows relative to the expected source range; reconciliation detects the difference and prevents promotion of the candidate view.
- Two operators request revisions or rebuilds concurrently; the latest valid cut is deterministic, conflicting candidates are not silently merged, and prior valid views remain available.
- A large burst affects many adjacent windows; materialization remains bounded, observable, and resumable without losing already accepted work.
- A structural analysis produces a significant signal; it remains labeled as structural evidence and never becomes an identity or truth decision.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST materialize only dynamic entity invariants into temporal histories; static objects and other evidence leaves MUST remain immutable references and MUST NOT acquire independent entity histories.
- **FR-002**: Each materialized history MUST preserve one stable tenant identity and one stable dynamic-entity identity; mixed-tenant or mixed-entity input MUST NOT be published.
- **FR-003**: Each window MUST use the event occurrence time and a clearly defined half-open interval; a source event MUST belong to exactly one window.
- **FR-004**: Covered windows without qualifying events MUST remain explicit as dormant, and missing measurements MUST remain unavailable rather than being interpolated or fabricated.
- **FR-005**: The system MUST distinguish the latest valid view from point-in-time views selected by event time, source cut, or revision.
- **FR-006**: A materialized view MUST expose its completeness state, latest accepted source cut, revision, and reason when it is delayed, rebuilding, quarantined, or otherwise incomplete.
- **FR-007**: Lifecycle state MUST be deterministic for every covered window and MUST use the existing lifecycle states: nascent, growing, stable, decaying, and dormant.
- **FR-008**: Activity measures MUST be calculated from admitted events in the applicable window and MUST identify when the available sample is insufficient for a valid measure.
- **FR-009**: Relationship and topology summaries MUST be window-specific, deterministic, and distinct from identity resolution; they MUST preserve typed evidence references without embedding evidence content.
- **FR-010**: Temporal feature records MUST align one-to-one with materialized windows, including dormant and insufficient-data windows, and MUST carry an explicit value or unavailable state.
- **FR-011**: All topology-derived and persistence-derived outputs MUST be labeled structural signals, MUST retain provenance, and MUST NOT assert identity, truth, or source independence.
- **FR-012**: Raw evidence and accepted source events MUST remain immutable; temporal materialization MUST store or expose only approved references and derived values.
- **FR-013**: Every published view MUST include a provenance record identifying its tenant, entity, window or requested point, accepted source-record range, source cut, materialization policy version, schema version, revision history, and verification fingerprint.
- **FR-014**: The same accepted source set, policy version, and schema version MUST produce logically identical windows, feature values, ordering, and verification fingerprints.
- **FR-015**: A materialization change MUST create a new identifiable revision; prior valid revisions MUST remain available for audit and replay until governed retention permits their removal.
- **FR-016**: Exact duplicate source records and repeated processing requests MUST be idempotent and MUST NOT change counts, lifecycle values, features, or revision numbers.
- **FR-017**: A valid late event MUST be assigned to its event-time window and MUST cause every dependent view to be revised consistently; unaffected views MUST remain unchanged.
- **FR-018**: Contradictory reuse of a source-record identity, malformed input, ambiguous timestamps, tenant mismatch, and policy-uncertain input MUST be quarantined with a reason and MUST NOT silently replace accepted history.
- **FR-019**: Quarantined or rejected records MUST be retained with their decision, reasons, source references, and processing time so they can be reviewed and replayed.
- **FR-020**: Any published temporal history MUST be rebuildable from immutable source events and evidence references without modifying those sources.
- **FR-021**: A rebuild candidate MUST NOT replace the active valid view until all expected windows are present and reconciliation finds no unexplained missing, extra, or divergent content.
- **FR-022**: Interrupted processing MUST be resumable from a recorded safe point and MUST converge to the same result as an uninterrupted rebuild.
- **FR-023**: Processing MUST use bounded task, source, investigation, and global retry budgets; exhausted or repeatedly failing work MUST be quarantined rather than retried indefinitely.
- **FR-024**: Processing MUST apply backpressure when downstream demand exceeds capacity and MUST bound work in memory, duration, and input size.
- **FR-025**: Tenant isolation MUST apply to reads, writes, revisions, rebuilds, status, counts, errors, and audit access.
- **FR-026**: Access MUST be limited by role to the minimum permitted actions, including viewing histories, requesting rebuilds, reviewing quarantined records, and accessing audit history.
- **FR-027**: The system MUST audit every publication, revision, promotion, rejection, quarantine, rebuild decision, and access-policy decision relevant to a materialization history.
- **FR-028**: Materialization MUST never become a source of truth, override admission or identity decisions, equate structural significance with truth, or delete evidence because a derived view failed.
- **FR-029**: A downstream failure MUST leave the last valid published view available and MUST prevent incomplete work from being presented as complete.
- **FR-030**: Materialization status MUST become observable within 60 seconds of a material delay, failure, quarantine decision, or completed reconciliation.

### Requirement Acceptance Matrix

| Requirements | Verified By |
| --- | --- |
| FR-001–FR-012 | AS-001 through AS-004 and AS-009 through AS-011 |
| FR-013–FR-019 | AS-003 through AS-008 and AS-011 |
| FR-020–FR-024 | AS-005, AS-008, and AS-015 |
| FR-025–FR-030 | AS-012 through AS-015 and cross-tenant isolation tests |

### Key Entities

- **Dynamic Entity Invariant**: The stable center of analysis for a person, company, domain, channel, or event; the subject of the materialized history but not the owner of identity decisions.
- **Temporal Window**: A half-open event-time interval with one explicit lifecycle state, source coverage, completeness, and revision history.
- **Materialized View**: A queryable current or point-in-time representation containing lifecycle, activity, relationship, evidence-reference, and eligible feature summaries for an entity.
- **Window Revision**: An immutable version of one window created by an initial materialization, late-data correction, policy change, or rebuild.
- **Source Cut**: The last accepted source position represented by a view, used to distinguish versions and support deterministic replay.
- **Temporal Feature Record**: A lifecycle, activity, relationship, or structural signal aligned to exactly one window with an explicit value or unavailable state.
- **Materialization Run**: An auditable attempt to create or rebuild histories, including status, source range, retries, reconciliation outcome, and publication decision.
- **Quarantine Record**: A malformed, ambiguous, policy-uncertain, contradictory, or repeatedly failing input retained with its decision and reasons.
- **Provenance Manifest**: The trace from a published window or feature back to its source records, source cut, policy, schema, revision, and verification fingerprint.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of completed temporal views can answer a point-in-time request and identify the exact accepted source cut represented by the answer.
- **SC-002**: Across repeated materialization of the same accepted inputs, 100% of deterministic values, orderings, and verification fingerprints match.
- **SC-003**: Across late-event scenarios, 100% of affected windows are revised, 0 unaffected windows change unexpectedly, and 0 source observations or events are modified.
- **SC-004**: Exact duplicate delivery across at least 1,000 repeated deliveries produces 0 additional accepted events, 0 phantom windows, and 0 unnecessary revisions.
- **SC-005**: In representative investigations, 95% of current-view requests complete within 2 seconds and 95% of point-in-time requests complete within 3 seconds after the corresponding view is available.
- **SC-006**: A test investigation containing 100,000 entity histories and 10 million source events materializes every eligible window with 100% cross-tenant isolation and no evidence loss.
- **SC-007**: At least 99% of interrupted materializations resume without manual cleanup and converge to the same verification fingerprint as uninterrupted processing within 15 minutes after processing capacity is restored.
- **SC-008**: 100% of malformed, ambiguous, contradictory, tenant-mismatched, and policy-uncertain test records are quarantined with actionable reasons; 0 are silently dropped or allowed to overwrite accepted history.
- **SC-009**: 100% of temporal feature records align one-to-one with materialized windows, and 100% of insufficient or dormant measurements are represented as unavailable or explicit dormancy rather than fabricated values.
- **SC-010**: 100% of structural signals are labeled structural-only, and structural materialization produces 0 identity or truth assertions.
- **SC-011**: 100% of publication, revision, rebuild, rejection, quarantine, and policy decisions produce an audit record traceable to tenant, entity, source cut, and time.
- **SC-012**: In a moderated usability study, at least 90% of analysts can identify when an entity was active, what evidence was known at a selected time, and whether a view is complete in under 3 minutes without assistance.

## Assumptions

- Feature 011 supplies deterministic lifecycle activity measures, temporal metrics, persistence outputs, and provenance conventions; this feature materializes and versions their temporal results rather than redefining their scientific meaning.
- Feature 012 supplies the two-kind dynamic-invariant/static-object boundary, stable identity anchors, event-time window rules, lifecycle states, dormant-window behavior, and window-aligned structural inputs.
- Dynamic entity events already carry a tenant, stable entity identity, unambiguous occurrence time, and stable source-record identity by the time they become eligible for materialization.
- The default materialization window remains seven days and may be changed by governed policy; changing it creates new revisions and does not reinterpret retained evidence.
- Covered-window history is retained according to existing evidence-retention policy, while every revision required for audit, dispute review, or reproducibility remains available for that period.
- Existing admission, entity-resolution, evidence, access-control, and investigation-policy decisions remain authoritative; this feature consumes their outcomes and cannot reverse them.
- The last valid view remains available when newer processing is delayed or failed, and consumers can distinguish that view from a fully current one.
- Acquisition scheduling, recrawl policy, source-quality policy, identity resolution, evidence interpretation, scientific truth adjudication, and user-interface redesign are outside this feature.
- No language model or other generative decision mechanism is used to create lifecycle states, features, provenance, or materialization outcomes.
- This feature is limited to the existing investigation, projection, and operational planes; it does not introduce a new orchestration backbone or universal knowledge store.
