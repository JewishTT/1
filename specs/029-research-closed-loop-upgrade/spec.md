# Feature Specification: COGNITIVE Master Platform Upgrade — Auditable Closed Research Loop

**Feature Branch**: `029-research-closed-loop-upgrade`

**Created**: 2026-10-13

**Status**: Draft

**Input**: User description: "Master Engineering Prompt for Global Platform Upgrade — автономное архитектурное ревью, переосмысление, инженерная реализация и валидация глобального апгрейда COGNITIVE. Оптимизировать замкнутый вычислительный процесс исследования, а не коллекцию микросервисов."

---

## Verified Baseline (evidence, not claims)

Commit `608c3ad8f4743e4e729807c903b0364ed571b311`, branch `main`, working tree dirty (117 entries).
Measured on this machine on 2026-10-13.

| Command | Result |
|---|---|
| `pytest -q` at repo root **before** `testpaths` was set | **831 collection errors**, 6769 collected — every one a vendored third-party checkout under `donors/` or `tmp/` |
| `pytest apps -q --ignore=bench` | **22 failed, 4273 passed, 27 skipped** — 1097.95s |
| `pytest -q` at repo root **after** `testpaths` was set | **22 failed, 4288 passed, 27 skipped** — 1166.59s |
| `pytest --co -q` at repo root | **4336 collected, 0 collection errors** |
| `pytest -q` from `bench/` | **2 failed, 21 passed** |

This baseline is the contract for this feature. No acceptance claim may be made
against a run that did not execute.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — The investigation reaches a conclusion and states why (Priority: P1)

An analyst asks a question. The platform decomposes it into research obligations,
works the frontier, records observations, accumulates them into a versioned knowledge
state, and then **stops for a stated reason** — goal reached, qualified saturation,
explicit closure, or a recorded blocker.

*Verified state*: this was unreachable. The single production call into the loop passed
no saturation evidence, so the saturation verdict was permanently "not saturated", so
the satisfaction evaluator was permanently unsatisfied, so no obligation could ever
reach a terminal state. 104 unit tests were green over an inert loop.

**Why this priority**: without it every other capability is decoration on an infinite
loop.

**Independent Test**: start a question, deliver one observation, assert the obligation
transitions to a terminal state, the termination report names the reason, and the
proposed next action changed.

**Acceptance Scenarios**:
1. **Given** an investigation with one open obligation, **When** genuine independently-sourced evidence satisfies it, **Then** the obligation reaches a terminal state and the loop reports a machine-readable reason.
2. **Given** an obligation needing an unavailable capability, **When** the loop evaluates, **Then** it reports `blocked` naming the obligation and the missing capability, and does not spin.
3. **Given** two sources disagree, **When** the loop evaluates, **Then** the obligation stays open, the contradiction is surfaced, and no stop reason is emitted.

---

### User Story 2 — Every conclusion opens its source (Priority: P1)

An analyst clicks any conclusion and reaches the exact bytes: file, page, offset,
capture time, retrieval source.

*Verified state*: the chain exists but the span that grounds a mention is hashed into
its identifier and discarded. One positional field means byte offset in one parser,
segment index in another, and zero in a third — all summed into one number.

**Why this priority**: the platform's constitution makes evidence-first its first
principle. An ungroundable conclusion is not evidence.

**Independent Test**: a document with a table and a page-numbered PDF; a finding derived
from a table cell resolves to that cell's byte range in the stored raw bytes, and a
coordinate-bearing document keeps its page and box.

**Acceptance Scenarios**:
1. **Given** an extracted mention, **When** its chain is resolved, **Then** every hop resolves to a content address and a source span that still matches the stored bytes.
2. **Given** two producers disagree about what an offset means, **When** they are compared, **Then** the system refuses rather than conflating the two meanings.
3. **Given** a finding with no resolvable chain, **When** it is presented, **Then** it is marked unsupported or partial and is not presented as grounded.

---

### User Story 3 — Re-running changes nothing (Priority: P1)

The same event delivered twice, or a process restarted mid-run, leaves the platform in
an identical state.

*Verified state*: the default event identifier is a random value, so redelivery creates
a new logical event — and a contract test pins that behaviour. The knowledge-state
accumulator mints a new revision on every sweep whether or not anything changed. The
record of *why* a research step was chosen survives only in process memory.

**Why this priority**: reproducibility is the difference between an intelligence
platform and a log aggregator.

**Independent Test**: deliver an identical event twice and assert one logical
observation, no doubled independence count, no extra revision. Restart and assert the
accumulated state is identical by digest.

**Acceptance Scenarios**:
1. **Given** the same event delivered twice, **When** both are processed, **Then** exactly one logical observation exists and evidence-independence counts do not increase.
2. **Given** a recorded research decision, **When** the process restarts, **Then** grounds, inputs, alternatives, actor and outcome are still retrievable.
3. **Given** redelivery after restart, **When** processed, **Then** no new revision is created.

---

### User Story 4 — Evidence is stored before it is claimed (Priority: P1)

No observation exists unless the bytes behind it were stored first, and every
observation resolves to those bytes.

*Verified state*: three production producers publish observations that cannot be
resolved to bytes at all — one builds the event inline with no content reference and
performs no store write. Four different identity schemes disagree about what an
observation is, and one of them is a random UUID on the identity path.

**Why this priority**: an observation with no bytes is an assertion.

**Independent Test**: for every production producer, ingest a payload and assert the
published observation resolves to stored bytes; deliver the same event twice and assert
one logical observation.

**Acceptance Scenarios**:
1. **Given** a producer that has not stored bytes, **When** it attempts to publish an observation, **Then** publication is refused.
2. **Given** bytes stored but the observation write fails, **When** recovery runs, **Then** the orphan is harmless and the repair path is named.
3. **Given** a complete observation whose publication failed, **When** repair runs, **Then** it republishes idempotently without creating a second observation.

---

### User Story 5 — The investigation is a first-class object (Priority: P2)

Two analysts can run different questions over the same body of knowledge without their
state colliding. A question's definition is distinguishable from its running state.

*Verified state*: the definition/instance split exists in the architecture record and in
no code. A code search for it returns nothing. Only one identifier namespace exists.

**Independent Test**: create a definition, start two investigations under it, assert
neither reads the other's obligations, decisions or frontier.

**Acceptance Scenarios**:
1. **Given** one definition and two investigations, **When** each reads state, **Then** neither sees the other's obligations, decisions or frontier.
2. **Given** a new definition revision, **When** an investigation starts under it, **Then** it records which revision it began from.

---

### User Story 6 — Unknown is preserved, absence is distinguished (Priority: P2)

An unrecognised relation type survives intact and marked. "Not investigated", "searched,
nothing found", "source unavailable", "query unsupported", "covered and found nothing"
and "sources disagree" are six different things and none is reported as another.

*Verified state*: a closed catalogue sits in the ingestion path; the open-world promise
is not tested end to end. The epistemic layer models the distinction; the schema does not
carry it through to a finding.

**Independent Test**: push a relation whose type appears in no catalogue; assert it
survives persistence → API → projection flagged. Then construct an investigation with a
known-detecting source and a failing one and assert the resulting absence states differ.

**Acceptance Scenarios**:
1. **Given** an unknown predicate, **When** persisted and read back, **Then** it is present and flagged, not dropped.
2. **Given** a policy that forbids a predicate, **When** it is rejected, **Then** the rejection is recorded with its policy version and reason.
3. **Given** a source that was never queried, **When** the platform reports, **Then** it reports "not investigated" — not "no result".

---

### User Story 7 — Projections can be thrown away and rebuilt (Priority: P2)

Every derived index can be discarded and rebuilt from the durable record, reproducing
the same digest.

*Verified state*: several derived layers have no rebuild path. One advertised retrieval
mode is a parameter nothing reads. One entire class of analysis — spatial — does not
exist, while the interface offers a map view it can never populate.

**Independent Test**: delete each derived store, rebuild from the durable record, assert
the digest matches the pre-deletion digest.

**Acceptance Scenarios**:
1. **Given** a derived index destroyed, **When** rebuilt from the durable record, **Then** the digest matches.
2. **Given** a rebuild that fails, **When** it does, **Then** the underlying evidence is untouched and the failure is visible.
3. **Given** a retrieval request naming an unavailable mode, **When** served, **Then** the system refuses with a named reason — never accepting a mode it will ignore.

---

### User Story 8 — Identity is never merged on an uncalibrated threshold (Priority: P2)

Two similar records do not silently become one, and copied sources do not count as
independent confirmation.

*Verified state*: the live admission path auto-merges on a threshold of 0.8 against a
calibration profile whose own version string reads `UNCALIBRATED-v1`. The independence
model that exists is never called from production; the live path counts hostnames, so a
syndicated article republished on twenty domains scores as twenty independent sources.

**Independent Test**: many reprints of one source plus two independent sources; assert
raw count and effective count differ, and confidence does not rise from copies.

**Acceptance Scenarios**:
1. **Given** a merge candidate with no declared calibration, **When** admission runs, **Then** it routes to review and never to merge.
2. **Given** twenty copies of one article and two independent sources, **When** corroboration is computed, **Then** the effective count reflects the two, not twenty-two.
3. **Given** a merge or split, **When** it occurs, **Then** previously published conclusions that relied on the prior identity say how to read them.

---

### User Story 9 — Findings are inspectable, review is history (Priority: P3)

Each conclusion shows its uncertainty, the method and version that produced it, the
snapshot it was computed against, competing explanations and assumptions. Reviewer
actions are recorded as history and never overwrite the record.

**Independent Test**: render one conclusion with a deliberate conflict; confirm every
listed element is present and correct.

**Acceptance Scenarios**:
1. **Given** a conclusion with a competing explanation, **When** displayed, **Then** both appear with their supporting evidence.
2. **Given** a reviewer marking a conclusion irrelevant, **When** submitted, **Then** the mark is recorded as history and the original evidence is unchanged.
3. **Given** analyst feedback, **When** it is applied, **Then** the next proposed action changes.

---

### Edge Cases

- The event arrives twice in the same instant from two brokers.
- The process dies between storing bytes and recording the observation.
- The process dies between recording the observation and publishing the event.
- A document is larger than the configured limit, or is an archive bomb.
- A parser returns partial output and then fails.
- A model provider is unavailable mid-run.
- An observation arrives out of order — later knowledge about earlier history.
- Two analysts write to the same investigation simultaneously.
- The same bytes arrive from two different sources (a copy, not a confirmation).
- A relation involves more than two participants.
- A coordinate is known only to coarse precision.
- A query is repeated verbatim and returns the same results.
- A tenant identifier is empty or absent.

---

## Requirements *(mandatory)*

### Research loop and context state

- **FR-001**: The research loop MUST reach a terminal state from evidence, never from a task or worker merely finishing.
- **FR-002**: Every termination MUST record a machine-readable reason: goal reached, qualified saturation, explicitly closed, suspended, or blocked-with-named-capability.
- **FR-003**: An obligation MUST NOT be marked satisfied on an absence whose detecting capability was unknown or unavailable.
- **FR-004**: Evidence independence MUST be measured on dependency groups, never on a raw document count.
- **FR-005**: The record of a research decision — grounds, inputs, alternatives, actor, outcome — MUST survive process restart.
- **FR-006**: A question definition MUST be a distinct object with its own identity space from the investigation state running under it.
- **FR-007**: Two investigations under the same definition MUST NOT observe each other's obligations, decisions or frontier.
- **FR-008**: Each context revision MUST record why it changed: events consumed, rule and operator versions, parameters, predecessor revision, derived changes, unresolved warnings.
- **FR-009**: A published revision MUST NOT be rewritten; changes MUST produce a new revision that supersedes it.
- **FR-010**: State accumulated from the durable event record MUST be authoritative; a single run or capture MUST NOT be able to overwrite it.
- **FR-011**: An action that previously produced no gain MUST be suppressed until a stated change in conditions, version or time window.
- **FR-012**: Action ranking MUST expose its components — expected information gain, hypothesis discrimination, relevance, source reliability, novelty, independence, freshness, cost, success probability — with safety, budget, source admissibility and approval as hard constraints no score can offset.
- **FR-013**: Raw features, calibrated probabilities and the final policy decision MUST be stored separately.

### Evidence and provenance

- **FR-014**: A recorded observation MUST be immutable, content-addressed, and resolve to stored raw bytes.
- **FR-015**: Every production path producing an observation MUST pass through exactly one gate; a producer MUST NOT publish an observation it did not store.
- **FR-016**: Exactly one scheme MUST derive observation identity; shadow derivations MUST be deleted or made to delegate.
- **FR-017**: Exactly one scheme MUST derive event identity; a random default MUST NOT exist, and no test may pin it.
- **FR-018**: Every derived artefact MUST reference the exact source span — byte range, page, coordinate box, URL or time interval — resolvable against the stored bytes.
- **FR-019**: Where producers disagree about the meaning of a positional field, the system MUST refuse rather than conflate.
- **FR-020**: A finding MUST either resolve a complete chain to a raw object and source, or be explicitly marked unsupported or partial and MUST NOT be presented as grounded.
- **FR-021**: No downstream operator — parser, model, graph, topological analysis, matcher — MUST modify recorded raw evidence.
- **FR-022**: No operator output MUST change canonical identity or become committed truth without an explicit admission or resolution decision.
- **FR-023**: An unrecognised type or predicate MUST survive persistence, API and projection; discarding it MUST require a recorded, versioned policy decision.
- **FR-024**: A mention's position MUST survive to the finding rather than being consumed into an identifier.

### Operator and event contracts

- **FR-025**: Every analytical step — parser, extractor, matcher, ranker, graph analytics, topological analysis, spatial indexing, online detector, model call — MUST return one versioned envelope carrying: operator identity and version; upstream repository/release/commit; licence; image digest or model/provider version; input observation ids and content digests; parent derivations; typed output kind and schema version; evidence references; captured/processed/source-declared/valid-from/valid-until/recorded times without semantic conflation; method fingerprint; deterministic parameters or seed; calibration identity; uncertainty; missingness; warnings; cost; replay key; idempotency key; tenant and policy identity; and an explicit status of succeeded, partial, unsupported, blocked, failed or quarantined.
- **FR-026**: A succeeded status with an empty output for a non-nullable output kind MUST be a contract violation, so an absence cannot masquerade as an empty success.
- **FR-027**: Uncertainty MUST be stored as a vector; different uncertainty semantics MUST NOT be collapsed into one scalar without justification.
- **FR-028**: Schema evolution, compatibility, idempotency and replay policy MUST be defined for every event type.
- **FR-029**: Object-store and database/event writes MUST be reconciled: a raw blob MAY become a harmless orphan, but no observation, membership or context record may assert successful placement on an unsuccessful link. Distributed atomicity MUST NOT be claimed without a mechanism.
- **FR-030**: Each of the failure windows between byte storage and event publication MUST have a named repair path.

### Determinism and time

- **FR-031**: Restart MUST reproduce the accumulated state exactly.
- **FR-032**: Every timestamp field MUST carry a declared, distinct semantic — obtained, captured, observed, published, valid-from, valid-until, recorded, processed — and the semantics MUST NOT be interchanged.
- **FR-033**: Current, as-of and interval queries MUST give materially different answers on data where the distinction is meaningful.
- **FR-034**: Later knowledge about the past MUST NOT retroactively change what the system reported it knew at an earlier point.
- **FR-035**: An operator MUST declare whether it is deterministic; where not, it MUST persist seed or configuration, model and version, the source of non-determinism, and its own result.

### Retrieval, projections and analysis

- **FR-036**: Candidate generation, candidate scoring, policy ranking and action selection MUST be separate stages with separate measurements.
- **FR-037**: Every derived index MUST declare purpose, input event types, checkpoint, schema and operator fingerprint, incremental path, full rebuild path, and staleness signal — as enforced data, not prose.
- **FR-038**: Every derived index MUST be rebuildable from the durable record and the rebuild MUST reproduce the same digest.
- **FR-039**: Projection failure MUST NOT damage or remove evidence.
- **FR-040**: A requested capability that is unavailable MUST be refused with a named reason.
- **FR-041**: Analytical outputs — scores, centralities, topological features, spatial resolutions — MUST be recorded as structural signals with method, version, snapshot and window, and MUST NOT be presented as facts of truth.
- **FR-042**: Structural change, regime change, temporal boundary and causal explanation MUST remain separate result types; drift MUST NOT be presented as causation.
- **FR-043**: Original geometry and its uncertainty MUST remain primary; a spatial index resolution MUST NOT create false precision.

### Admission and identity

- **FR-044**: Identity merges MUST be a recorded decision with a feature breakdown, model fingerprint, calibration identity, and defer, reject and review paths.
- **FR-045**: An automatic merge MUST NOT occur against a threshold whose calibration state is undeclared or empty.
- **FR-046**: Corroboration MUST count independent sources, not distinct hosts or distinct documents.
- **FR-047**: A split or merge MUST state how previously published conclusions relying on the prior identity should be read.
- **FR-048**: Admission and identity resolution MUST remain separate stages; no implicit promotion on parser or model confidence.

### Security, tenancy and operations

- **FR-049**: Every query and write MUST be tenant-scoped, tested at storage, API and consumer level.
- **FR-050**: A cross-tenant read or write MUST be refused with a typed refusal, not answered with an empty result.
- **FR-051**: External input MUST be treated as untrusted: private-network and rebinding targets refused; payload, archive and file-count limits enforced; parser and model instructions treated as data.
- **FR-052**: Each operator MUST have a timeout, resource limit, isolation boundary, kill switch and stated degraded behaviour.
- **FR-053**: Retry budgets MUST exist per task, source, investigation and globally; exhausted work MUST reach a queue preserving cause and replay path.
- **FR-054**: Acquisition MUST slow down when downstream backlog grows.
- **FR-055**: Every new runtime dependency MUST be recorded with exact version, licence, transitive footprint, deployment boundary, and the capability or measurement justifying it.
- **FR-056**: Every licence, model and dataset MUST pass an explicit policy gate before production use; copyleft licences are permitted but require a documented deployment and compliance design.
- **FR-057**: Platform truth MUST be recoverable from the durable record alone; no single index, score, ontology or model may be the sole authority.
- **FR-058**: Silent failure MUST NOT exist in any acquisition or interpretation path; a dropped artefact, unstored observation or swallowed exception MUST be counted and surfaced.

### Governance and evidence of work

- **FR-059**: Every capability claimed as delivered MUST be classified by evidence — declared, implemented, unit-tested, contract-tested, wired into a live path, or proven end to end — with file references.
- **FR-060**: A status marker in a task list MUST NOT be accepted as proof without the corresponding call sites and tests.
- **FR-061**: Every architecture gate changed or retired MUST be recorded as an explicit decision with alternatives, cost, migration, failure modes and reversibility.
- **FR-062**: Every donor candidate MUST be classified as accepted, rejected, methodology-only, benchmark, or unverified/ambiguous, with an exact upstream, exact revision and licence — or an explicit statement that it could not be identified.
- **FR-063**: Documents that contradict the code MUST be reconciled, with correction history preserved.

### Key Entities

- **Research Obligation**: a checkable thing that must be learned — question, target knowledge type, status, satisfaction requirement, stopping rule, blocking capability.
- **Research Decision**: grounds, inputs, alternatives, actor, outcome, timestamp.
- **Question Definition**: the immutable analytical assignment — objective, scope, policy, time frame — under which investigations run.
- **Investigation Context**: the revisable operational state under a definition — obligations, hypotheses, evidence, conflicts, unknown, decisions, revisions.
- **Context Revision**: a published, immutable state version with a stated cause and predecessor.
- **Capture**: an immutable, content-addressed acquisition event with retrieval source and retrieval time.
- **Observation**: a statement that something was obtained from a source — not that it is true.
- **Evidence Reference**: an exact typed span, page, coordinate, URL or time interval inside a stored object.
- **Mention**: a surface form at an exact location — not an entity.
- **Candidate**: a proposed identity match or relation with supporting and opposing evidence.
- **Resolution Decision**: accept, reject, defer or reverse, with the calibration state that justified it.
- **Operator Result**: one analytical step's output with identity, version, inputs, method fingerprint, uncertainty, status and cost.
- **Finding**: a conclusion with its chain, uncertainty, alternatives, assumptions and limitations.
- **Absence Statement**: the explicit classification of what is not known, distinguishing six cases.
- **Derived Index**: any rebuildable projection with a declared fingerprint, checkpoint and rebuild path.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of conclusions accepted for publication either resolve a complete machine-checkable chain to a stored raw object and its source, or are explicitly marked unsupported or partial. A conclusion marked grounded with no resolvable chain is a defect.
- **SC-002**: An end-to-end test exists in which one new observation traverses the whole loop — gap → obligation → action → acquisition → observation → knowledge-state revision → changed obligation and changed next-action proposal — passing against the real stack profile, or naming precisely what infrastructure blocks it.
- **SC-003**: Delivering an identical event twice yields one logical observation, does not increase the independent-evidence count, and does not create an additional revision. Measured.
- **SC-004**: After restart, the accumulated knowledge state is identical to the state before restart, compared by digest. Measured.
- **SC-005**: A recorded research decision is retrievable after restart including grounds, inputs, alternatives and outcome, asserted against a real database.
- **SC-006**: Current, as-of and interval queries return three materially different answers on a fixed fixture. Asserted.
- **SC-007**: An unknown predicate submitted through the full path survives persistence, API and projection and is returned flagged. Asserted.
- **SC-008**: Every derived index claiming a rebuild path rebuilds to an identical digest after destruction. The count claiming one and failing is zero.
- **SC-009**: Cross-tenant read and write attempts are refused with a typed refusal at storage, API and consumer level, in tests.
- **SC-010**: Zero silent failures in acquisition and interpretation: dropped artefacts, unstored observations and swallowed exceptions are counted and surfaced. The count is zero.
- **SC-011**: A reproducible baseline exists for retrieval quality, identity-resolution false-merge rate, provenance completeness, effective independent evidence per finding, cost per grounded finding, loop convergence, replay divergence and rebuild determinism — with commands recorded and raw measurements kept.
- **SC-012**: Every donor and dependency is classified with an exact upstream, exact revision and licence, or an explicit statement that it could not be identified. Names that resolve to several projects are marked ambiguous.
- **SC-013**: No new test failures are introduced. The pre-existing failure set is either fixed or recorded with a reason. The command and its output are recorded in this feature directory.
- **SC-014**: A reviewer reaches from a conclusion to the exact source bytes, method version, time window, competing explanations and the decision that caused the next acquisition action in at most three steps.
- **SC-015**: The mandatory benchmark scenarios exist with fixtures: document intelligence; identity ambiguity; correlated evidence; temporal reversal; contradiction/unknown/qualified absence; closed loop; projection rebuild and restart; retrieval comparison; topological robustness; spatial uncertainty; operator failure; tenant and security.
- **SC-016**: Live integration tests are explicitly marked and never report a pass when the network or a service is unavailable.

---

## Assumptions

- The existing technology baseline (event transport, object storage, relational store, search and analytical stores, graph abstraction, topological analysis in Python) is retained unless measurement shows a concrete failure. This feature introduces no new datastore, broker, graph engine or model provider.
- The existing test harness is used. `live` tests remain opt-in and MUST NOT report a pass when a service is unavailable.
- Vendored third-party checkouts under `donors/` and `tmp/` are not platform code and MUST be excluded from the default test run.
- Scope is the research loop, its contracts and its evidence chain. Domain research packs and analyst interface work are in scope only where they expose or consume these contracts.
- The owner accepts that some capabilities previously recorded as delivered will be reclassified as not wired. That reclassification is the point, not a regression.

---

## Out of Scope

- New acquisition sources beyond what is needed to exercise the loop end to end.
- Replacing a technology in the recorded baseline without a measured failure attributable to it.
- Multi-region deployment, commercial licensing decisions, and anything requiring legal advice.
- Any mechanism that bypasses authentication, CAPTCHA, paywalls or other access controls of a source.