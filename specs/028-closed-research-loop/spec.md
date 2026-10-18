# Feature Specification: Closed Research Loop with Versioned Evidence Contracts

**Feature Branch**: `028-closed-research-loop`

**Created**: 2026-10-13

**Status**: Draft

**Input**: User description: "Master Engineering Prompt for Global Platform Upgrade — автономное архитектурное ревью, переосмысление, инженерная реализация и валидация глобального апгрейда COGNITIVE. Audit first, then agreed target architecture, then implementation as end-to-end verticals with tests. Optimize for new verifiable knowledge per unit of total research cost, not isolated throughput."

---

## Verified Baseline (WP0 — evidence, not claims)

Commit `608c3ad8f4743e4e729807c903b0364ed571b311`, branch `main`, working tree dirty (117 entries).
Real test run on this machine:

| Command | Result |
|---|---|
| `.venv\Scripts\python.exe -m pytest apps -q --ignore=bench` | **22 failed, 4273 passed, 27 skipped** in 1097.95s |
| `.venv\Scripts\python.exe -m pytest -q` (repo root) | **831 collection errors** — vendored `donors/` and `tmp/` trees are collected; no `testpaths` is configured |
| `bench/tests/test_harness.py` | **collection error** — `from bench import harness` resolves to `bench/__init__.py`, not `bench/bench/` |

This baseline is the contract. No acceptance claim in this feature may be made against a run that did not execute.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — The loop actually closes (Priority: P1)

An analyst asks a question. The platform decomposes it into research obligations, works the frontier, records observations, accumulates them into a versioned knowledge state, and then **stops for a stated reason** — goal reached, qualified saturation, explicit closure, or a recorded blocker. Today it does not stop for any reason: the single production call site into the research loop passes no saturation evidence, so the saturation verdict is always "not saturated", so no obligation can ever be satisfied, so the loop can only be terminated by a human killing the process.

**Why this priority**: Without this, every other capability is decoration on an infinite loop. All 4273 passing tests include unit coverage of the closure path — exercised only from tests.

**Independent Test**: Start a question, deliver one observation, and assert (a) the obligation transitions to a satisfied or explicitly-blocked state, (b) the termination report names the reason, (c) the proposed next action changed as a result.

**Acceptance Scenarios**:
1. **Given** an investigation with one open obligation, **When** a genuine, independently-sourced observation satisfies it, **Then** the obligation reaches a terminal state and the loop reports a machine-readable stop reason — not silence.
2. **Given** an investigation whose only remaining obligation needs a capability that is unavailable, **When** the loop evaluates, **Then** it reports `blocked` with the missing capability named, and does not spin.
3. **Given** an investigation where two sources disagree, **When** the loop evaluates, **Then** the obligation stays open, the contradiction is surfaced, and no stop reason is emitted.

---

### User Story 2 — Every conclusion traces to a primary source (Priority: P1)

An analyst clicks any conclusion and reaches the exact bytes it rests on: file, page, offset, capture time, retrieval source. Today a chain of claims is stored, but the span that grounds a mention is hashed into its identifier and discarded; one parser records a byte offset where another records a segment index, both into the same field; and the live resolution path loses the span entirely.

**Why this priority**: Without a groundable chain, no conclusion is checkable, and the platform's own constitution makes evidence-first the first principle.

**Independent Test**: Take a document with a table and a page-numbered PDF; assert that a finding derived from a cell in the table resolves to that cell's byte range in the original bytes, and that a coordinate-bearing document keeps its page and box.

**Acceptance Scenarios**:
1. **Given** an extracted mention, **When** its provenance chain is resolved, **Then** every hop resolves to a content address and a source span that still matches the stored raw bytes.
2. **Given** two producers reporting a span, **When** they disagree about what an offset means, **Then** the system refuses rather than silently conflating the two meanings.

---

### User Story 3 — Re-running changes nothing (Priority: P1)

The same event delivered twice, or a process restarted mid-run, leaves the platform in the identical state. Today the default event identifier is a random value, so redelivery is a new event; the knowledge-state accumulator mints a new revision on every sweep whether or not anything changed; and the record of *why* a research step was chosen survives only in process memory.

**Why this priority**: Reproducibility is the difference between an intelligence platform and a log aggregator.

**Independent Test**: Deliver an identical event twice and assert one logical observation, no doubled independence count, and no extra revision; restart and assert the accumulated state is byte-identical.

**Acceptance Scenarios**:
1. **Given** the same event delivered twice, **When** both are processed, **Then** exactly one logical observation exists and evidence-independence counts do not increase.
2. **Given** a recorded research decision, **When** the process restarts, **Then** the decision — grounds, inputs, alternatives, outcome — is still retrievable.
3. **Given** a redelivery after restart, **When** it is processed, **Then** no new revision is created.

---

### User Story 4 — The investigation is a first-class object (Priority: P2)

Two analysts can run different questions over the same body of knowledge without their state colliding, and a question's definition is distinguishable from its running state. Today the definition/instance split exists in the architecture record but not in code: only one identifier namespace exists, and the engine can be constructed twice for the same investigation.

**Why this priority**: It is the difference between a research workspace and a shared mutable scratchpad, and it is the precondition for branching.

**Independent Test**: Create a question definition, start two revisions under it, and assert the two revisions' states never read each other's obligations or decisions.

**Acceptance Scenarios**:
1. **Given** one question definition and two concurrent investigations, **When** each reads its state, **Then** neither sees the other's obligations, decisions or frontier.
2. **Given** a definition revision, **When** a new investigation starts under it, **Then** it records which revision it started from.

---

### User Story 5 — Unknown is preserved, not dropped (Priority: P2)

An unrecognised relation type or predicate survives the pipeline intact and marked, rather than being silently discarded by a fixed vocabulary. Today a closed catalogue sits in the ingestion path, and the open-world promise is not tested end to end.

**Why this priority**: Premature vocabulary closure is the classic way an evidence platform silently loses the finding it was built to find.

**Independent Test**: Push a relation whose type appears in no catalogue, assert it survives persistence → API → projection with its unknown-type marker.

**Acceptance Scenarios**:
1. **Given** an unknown predicate, **When** it is persisted and read back, **Then** it is present and flagged, not dropped.
2. **Given** a policy that forbids a predicate, **When** it is rejected, **Then** the rejection is recorded with its policy version and reason.

---

### User Story 6 — Absences are distinguishable (Priority: P2)

"Not investigated", "searched, nothing found", "the source could not answer", "the source could have answered but the search did not cover it", and "sources disagree" are five different things, and the platform must not report one as another.

**Why this priority**: Converting an unsearched gap into a negative finding is the most common way an intelligence system manufactures false certainty.

**Independent Test**: Construct an investigation with a known-detecting source and a failing one, and assert the resulting absence states differ.

**Acceptance Scenarios**:
1. **Given** a source that was never queried, **When** the platform reports on the question, **Then** it reports "not investigated".
2. **Given** a source that was queried and can answer, **When** nothing was returned, **Then** it reports "searched, no result" — distinguishable from (1).
3. **Given** two sources that disagree, **When** the platform reports, **Then** it reports an unresolved contradiction and keeps both.

---

### User Story 7 — Projections can be thrown away and rebuilt (Priority: P2)

Every derived index — knowledge graph, search, temporal, analytical, topological, spatial — can be discarded and rebuilt from the durable record, and the rebuild reproduces the same result. Today several derived layers have no rebuild path at all, one advertised retrieval mode is a parameter nothing reads, and one entire class of analysis (spatial) does not exist while the interface offers a map view it can never populate.

**Why this priority**: Projections are cheap; the durable record is not. A platform that cannot rebuild is a platform that cannot recover.

**Independent Test**: Delete each derived store, rebuild from the durable record, and assert the resulting digest matches the pre-deletion digest.

**Acceptance Scenarios**:
1. **Given** a derived index destroyed, **When** it is rebuilt from the durable record, **Then** the rebuilt digest matches the destroyed one.
2. **Given** a rebuild in progress, **When** it fails, **Then** the underlying evidence is untouched and the failure is visible.
3. **Given** a retrieval request naming a semantic mode, **When** it is served, **Then** the system either serves it or states plainly that the capability is unavailable — it never accepts the mode and ignores it.

---

### User Story 8 — Findings are inspectable objects (Priority: P3)

Each conclusion shows its uncertainty, the method and version that produced it, the snapshot it was computed against, the competing explanations, and what is assumed. Reviewer actions are recorded as history and never overwrite the record.

**Why this priority**: An uninspectable conclusion is a rumour with extra steps.

**Independent Test**: Render one conclusion with a deliberate conflict and confirm every listed element is present and correct.

**Acceptance Scenarios**:
1. **Given** a conclusion with a competing explanation, **When** it is displayed, **Then** both appear with their supporting evidence.
2. **Given** a reviewer marking a conclusion irrelevant, **When** they submit, **Then** the mark is recorded as history and the original evidence is unchanged.

---

### Edge Cases

- The event arrives twice in the same instant from two brokers.
- The process dies between storing raw bytes and recording the observation that references them.
- The process dies between recording the observation and publishing the event.
- A document is larger than the configured limit, or is an archive bomb.
- A parser returns partial output and then fails.
- A model provider is unavailable mid-run.
- An observation arrives out of order — later knowledge about earlier history.
- Two analysts write to the same investigation at the same time.
- The same bytes arrive from two different sources (copy, not confirmation).
- A relation involves more than two participants.
- A coordinate is known only to coarse precision.
- A query is repeated verbatim and returns the same results.
- A tenant identifier is empty or absent.

---

## Requirements *(mandatory)*

### Research loop and context state

- **FR-001**: The research loop MUST reach a terminal state from evidence, never from a task or worker merely finishing.
- **FR-002**: Every termination MUST record a machine-readable reason from the closed set: goal reached, qualified saturation, explicitly closed, suspended, blocked-with-named-capability.
- **FR-003**: An obligation MUST NOT be marked satisfied on an absence whose detecting capability was unknown or unavailable.
- **FR-004**: Evidence independence MUST be measured on dependency groups, never on a raw document count.
- **FR-005**: The record of a research decision — grounds, inputs, alternatives, actor, outcome — MUST survive process restart.
- **FR-006**: A question definition MUST be a distinct object with its own identity space from the investigation state that runs under it.
- **FR-007**: Two investigations under the same definition MUST NOT observe each other's obligations, decisions or frontier.
- **FR-008**: Each context revision MUST record why it changed: the events consumed, the rule and operator versions, the parameters, and the predecessor revision.
- **FR-009**: A published revision MUST NOT be rewritten; changes MUST produce a new revision that supersedes it.
- **FR-010**: The state accumulated from the durable event record MUST be the authoritative state; a single run or capture MUST NOT be able to overwrite it.
- **FR-011**: A repeated action that previously produced no gain MUST be suppressed until a stated change in conditions, version or time window.

### Evidence and provenance

- **FR-012**: A recorded observation MUST be immutable and content-addressed, and MUST resolve to stored raw bytes.
- **FR-013**: Every production path that produces an observation MUST pass through exactly one gate; a producer MUST NOT publish an observation it did not store.
- **FR-014**: Exactly one scheme MUST derive the observation identity; additional derivations MUST be removed or made to delegate to it.
- **FR-015**: Every derived artefact MUST reference the exact source span it came from — byte range, page, coordinate box, URL or time interval — and that span MUST be resolvable against the stored raw bytes.
- **FR-016**: Where two producers disagree about the meaning of a positional field, the system MUST refuse rather than conflate.
- **FR-017**: A finding MUST either resolve a complete chain to a raw object and source, or be explicitly marked unsupported or partial and MUST NOT be presented as grounded.
- **FR-018**: No downstream operator — parser, model, graph, topological analysis, matcher — MUST modify recorded raw evidence.
- **FR-019**: No operator output MUST change canonical identity or become committed truth without passing an explicit admission or resolution decision.
- **FR-020**: An unrecognised type or predicate MUST survive persistence, API and projection; discarding it MUST require an explicit, versioned policy decision that is recorded.

### Determinism, idempotency and time

- **FR-021**: An event identifier MUST be derived from the event's content; redelivery of an identical event MUST NOT create a new logical event.
- **FR-022**: An operator MUST declare whether it is deterministic; where it is not, it MUST persist its seed or configuration, the model and version used, the source of non-determinism, and its own result.
- **FR-023**: Restart MUST reproduce the accumulated state exactly.
- **FR-024**: Every timestamp field MUST carry a declared, distinct semantic: obtained, captured, observed, published, valid-from, valid-until, recorded, processed. The semantics MUST NOT be interchanged.
- **FR-025**: Current, as-of and interval queries MUST give materially different answers on data where the distinction is meaningful.
- **FR-026**: Later knowledge about the past MUST NOT retroactively change what the system reported it knew at an earlier point in time.
- **FR-027**: Storage of raw bytes and the record referencing them MUST be atomic, or the failure MUST be recorded honestly with a defined repair path. Distributed atomicity MUST NOT be claimed without a mechanism.

### Retrieval, projections and analysis

- **FR-028**: Candidate generation, candidate scoring, policy ranking and action selection MUST be separate stages with separate measurements.
- **FR-029**: Each derived index MUST declare its purpose, its inputs, its checkpoint, its schema and operator fingerprint, its incremental path, its full rebuild path and its staleness signal.
- **FR-030**: Every derived index MUST be rebuildable from the durable record, and the rebuild MUST reproduce the same digest.
- **FR-031**: Projection failure MUST NOT damage or remove evidence.
- **FR-032**: A requested capability that is unavailable MUST be refused with a named reason; the system MUST NOT accept a request it will silently not honour.
- **FR-033**: Analytical outputs — scores, centralities, topological features, spatial resolutions — MUST be recorded as structural signals with method, version, snapshot and window, and MUST NOT be presented as facts of truth.
- **FR-034**: Structural change, a change in regime, a temporal boundary and a causal explanation MUST remain separate result types.

### Admission and identity

- **FR-035**: Identity merges MUST be a recorded decision with a feature breakdown, a model fingerprint, a calibration identity and a defer, reject and review path.
- **FR-036**: An automatic merge MUST NOT be performed against a threshold whose calibration state is undeclared or empty.
- **FR-037**: Corroboration MUST count independent sources, not distinct hosts or distinct documents.
- **FR-038**: A split or merge MUST state how previously published conclusions that relied on the prior identity should be read.

### Security, tenancy and operations

- **FR-039**: Every query and write MUST be tenant-scoped, and the scoping MUST be tested at the storage, API and consumer levels.
- **FR-040**: A cross-tenant read or write MUST be refused with a typed refusal, not answered with an empty result.
- **FR-041**: External input MUST be treated as untrusted: private-network and rebinding targets refused, payload and archive limits enforced, parser and model instructions treated as data.
- **FR-042**: Each operator MUST have a timeout, a resource limit, an isolation boundary, a kill switch and a stated degraded behaviour.
- **FR-043**: Retry budgets MUST exist per task, source, investigation and globally; exhausted work MUST go to a queue whose cause and replay path are preserved.
- **FR-044**: Acquisition MUST slow down when downstream backlog grows.
- **FR-045**: Every new runtime dependency MUST be recorded with its exact version, licence, transitive footprint, deployment boundary and the capability or measurement that justifies it.
- **FR-046**: A licence, model or dataset MUST pass an explicit policy gate before production use.
- **FR-047**: Platform truth MUST be recoverable from the durable record alone; no single index, score, ontology or model may be the sole authority.

### Governance and evidence of work

- **FR-048**: Every capability claimed as delivered MUST be classified by evidence: declared, implemented, unit-tested, contract-tested, wired into a live path, or proven end to end — with file references for each claim.
- **FR-049**: A status marker in a task list MUST NOT be accepted as proof of implementation without the corresponding call sites and tests being present.
- **FR-050**: Where an architecture gate is changed or retired, the change MUST be recorded as an explicit decision with alternatives, cost, migration, failure modes and reversibility.

### Key Entities

- **Research Obligation**: a checkable thing that must be learned, with its question, target knowledge type, status, satisfaction requirement and stopping rule.
- **Research Decision**: why a step was chosen and what happened — grounds, inputs, alternatives, actor, outcome, timestamp.
- **Question Definition**: the immutable analytical assignment — objective, scope, policy, time frame — under which investigations run.
- **Investigation Context**: the revisable operational state under a definition — obligations, hypotheses, evidence, conflicts, unknown, decisions, revisions.
- **Context Revision**: a published, immutable version of that state with a stated cause and a stated predecessor.
- **Capture**: an immutable, content-addressed acquisition event with its retrieval source and retrieval time.
- **Observation**: a statement that something was obtained from a source; not a statement that it is true.
- **Evidence Reference**: an exact span, page, coordinate, URL or time interval inside a stored object.
- **Mention**: a surface form found at an exact location; not an entity.
- **Candidate**: a proposed identity match or relation, with its supporting and opposing evidence.
- **Resolution Decision**: accept, reject, defer or reverse, with the calibration state that justified it.
- **Operator Result**: the output of any analytical step, carrying its identity, version, inputs, method fingerprint, uncertainty, status and cost.
- **Finding**: a conclusion with its chain, uncertainty, alternatives, assumptions and limitations.
- **Absence Statement**: the explicit classification of what is not known, distinguishing the five cases.
- **Derived Index**: any rebuildable projection with a declared fingerprint, checkpoint and rebuild path.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of conclusions accepted for publication either resolve a complete, machine-checkable chain to a stored raw object and its source, or are explicitly marked unsupported or partial. A conclusion marked as grounded with no resolvable chain is a defect, not a warning.
- **SC-002**: An end-to-end test exists in which one new observation traverses the whole loop — gap → obligation → action → acquisition → observation → knowledge-state revision → changed obligation and changed next-action proposal — and passes against the real stack profile, or the test names precisely what infrastructure blocks it.
- **SC-003**: Delivering an identical event twice yields exactly one logical observation, does not increase the independent-evidence count, and does not create an additional revision. Measured, not asserted by construction.
- **SC-004**: After restart, the accumulated knowledge state is identical to the state before restart, compared by digest. Measured.
- **SC-005**: A recorded research decision is retrievable after restart, including grounds, inputs, alternatives and outcome. At least one test asserts this against a real database.
- **SC-006**: Current, as-of and interval queries return three materially different answers on a fixed fixture where the distinctions are meaningful. A test asserts all three differ.
- **SC-007**: An unknown predicate submitted through the full path survives persistence, API and projection and is returned flagged. A test asserts its presence.
- **SC-008**: Every derived index that claims a rebuild path rebuilds to an identical digest after destruction. Count of indices claiming a rebuild path without one passing this test is zero.
- **SC-009**: Cross-tenant read and write attempts are refused with a typed refusal at storage, API and consumer level, in tests, not only in documentation.
- **SC-010**: Zero silent failures in the acquisition and interpretation paths: a dropped artefact, an unstored observation or a swallowed exception is counted and surfaced. The count is zero.
- **SC-011**: A reproducible baseline exists for retrieval quality, identity-resolution false-merge rate, provenance completeness, effective independent evidence per finding, cost per grounded finding, loop convergence, replay divergence and rebuild determinism — with the commands recorded and the raw measurements kept.
- **SC-012**: Every donor and dependency under consideration is classified as accepted, rejected, methodology-only, benchmark, or unverified/ambiguous — with an exact upstream, an exact revision and a licence, or an explicit statement that it could not be identified.
- **SC-013**: The existing test suite has no new failures introduced by this work; the pre-existing 22 failures are either fixed or explicitly recorded as out of scope with a reason. The run command and its output are recorded in this feature directory.
- **SC-014**: A reviewer can navigate from a conclusion to the exact source bytes, the method version, the time window, the competing explanations and the decision that caused the next acquisition action, in at most three steps.

---

## Assumptions

- The platform's own constitution (`.specify/memory/constitution.md`, v1.2.0) remains the governing philosophy; where a recorded gate conflicts with a more fundamental principle, this feature changes the gate through an explicit decision record rather than silently.
- The existing technology baseline (event transport, object storage, relational store, search and analytical stores, a graph abstraction, topological analysis in Python) is retained unless measurement shows a concrete failure. This feature does not introduce a new datastore, message broker, graph engine or model provider.
- Test infrastructure already present (pytest with unit, contract, integration and live markers) is the harness. `live` tests remain opt-in and MUST NOT report a pass when the network or a service is unavailable.
- The vendored `donors/` and `tmp/` trees are third-party checkouts, not platform code, and MUST be excluded from the default test run. This is a configuration fix, not a deletion.
- Scope is the research loop, its contracts and its evidence chain. Domain research packs and analyst interface work are in scope only where they expose or consume these contracts.
- The owner accepts that some previously recorded capabilities will be reclassified from "delivered" to "not wired" as a result of this work. That reclassification is the point, not a regression.

---

## Out of Scope

- New acquisition sources beyond what is needed to exercise the loop end to end.
- Replacing a technology in the recorded baseline without a measured failure attributable to it.
- Multi-region deployment, commercial licensing decisions, and anything requiring legal advice.
- Any mechanism that bypasses authentication, CAPTCHA, paywalls or other access controls of a source.