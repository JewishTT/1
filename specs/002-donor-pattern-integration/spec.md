# Feature Specification: Donor Pattern Integration

**Feature Branch**: `002-donor-pattern-integration`

**Created**: 2026-09-07

**Status**: Draft

**Input**: User description: "Integrate external OSINT donor patterns into the COGNITIVE platform: FollowTheMoney-style data model (statement provenance, schema/ontology, temporal semantics), OpenOSINT-style correlation/resolution without destroying uncertainty, Kipi-style investigation/evidence workflow, SpiderFoot-style modular connector ecosystem, investigator-style evidence fusion/reasoning, reNgine-style recon task orchestration, kafSIEM-style Kafka-native provenance, PANO/Vitni-style graph/timeline/map analyst workbench with human review, NetForensicAI-style unified parser interface."

## Context

COGNITIVE (feature `001-global-osint-platform`) already defines the platform skeleton: immutable Observations in S3, events over Kafka, the Mention→Candidate→Entity→Assertion chain, admission with ACCEPT/DEFER/REJECT/QUARANTINE, rebuildable projections, and a benchmark harness. This feature **does not import any donor codebase wholesale** (no Frankenstein, no vendor lock-in). It distills the *conceptual subsystems and patterns* validated by ten open-source OSINT projects and encodes them as first-class contracts, data-model elements, and tasks in COGNITIVE.

The governing idea is compact:

> **FollowTheMoney gives us the data language → OpenOSINT gives us the resolution mechanism → SpiderFoot gives us the source-connector model → Kipi gives us the investigation model → investigator gives us evidence reasoning → our event-driven architecture binds everything into one machine.**

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Statement-Level Knowledge Model (Priority: P1)

An analyst investigating a person sees, for every relationship (e.g. `Ivan → works_at → ACME`), the full statement record behind it: **value, dataset, first_seen, last_seen, original_value, extraction_version, provenance**. The analyst can distinguish "20 sites merely reprinted one original document" from "20 genuinely independent sources", can see temporal validity windows (`valid_from`/`valid_until`), and every assertion traces to its raw observation byte-for-byte.

**Why this priority**: Statement-level provenance is the *data language* of the entire platform (per donor analysis, FollowTheMoney). Without it, correlation counts reprints as corroboration, resolution is ungrounded, and auditability is impossible. It is the foundation the other stories build on.

**Independent Test**: Ingest a fixture corpus where one document is copied verbatim by multiple "sites" plus one independent source; verify the model reports `publication_count = N` but `independent_sources = 2`, every assertion carries `first_seen/last_seen/original_value/extraction_version`, and a lineage walk from finding to raw object succeeds.

**Acceptance Scenarios**:

1. **Given** a parsed observation, **When** interpretation produces an assertion, **Then** the assertion carries dataset id, first_seen/last_seen timestamps, original_value, and extraction_version (FR-011/FR-015).
2. **Given** 20 sites reprinting one document, **When** the evidence-independence engine evaluates support, **Then** they collapse to one independent chain, not 20.
3. **Given** a temporal assertion, **When** the analyst inspects it, **Then** `valid_from`/`valid_until` and the applicable temporal policy are shown, and retraction/superseding keeps the original (FR-016).

---

### User Story 2 - Correlation Without Destruction (Priority: P1)

The analyst can hold a **correlation graph** where `Candidate A --possible_match--> Candidate B` exists *without* implying identity. System and analyst can attach a human verdict (ACCEPT/REJECT/UNCERTAIN — become part of provenance), the system never destructively merges, and extraction confidence is stored separately from resolution score.

**Why this priority**: OpenOSINT's core lesson — never conflate "may be related" with "is the same entity" — is what keeps the knowledge base non-destructively deduplicable and reviewable. This is the *resolution mechanism* of the platform.

**Independent Test**: Feed a fixture with two entities sharing weak signals; assert the correlation graph creates `possible_match` edges without auto-merge, a human review can change the decision, and the review event is replayed as provenance.

**Acceptance Scenarios**:

1. **Given** two candidates with overlapping normalizations, **When** resolution runs, **Then** a `possible_match` edge is created with raw_pair_score + reasons; no entity merge occurs without an admitted assertion.
2. **Given** a candidate pair with insufficient evidence, **When** admission evaluates, **Then** the decision is DEFER (default), never destructive REJECT.
3. **Given** an analyst review ACCEPT/REJECT/UNCERTAIN, **When** recorded, **Then** the review becomes immutable provenance and is replayable.

---

### User Story 3 - Investigation & Evidence Workspace (Priority: P2)

The analyst drives an **investigation** — not a graph — with targets, evidence objects, entities, relationships, timeline, sources, and analyst decisions. Every element carries provenance and grading; the workbench presents a merged **graph + timeline + map** surface (investigation-first UX).

**Why this priority**: Kipi shows investigation UX is the analyst-facing product; PANO/Vitni show the graph/timeline/map canvas and review semantics. This is the *workflow model* and *analyst workbench*; it depends on stories 1-2 being present.

**Independent Test**: Create an investigation, attach fixture evidence, walk the full lineage from finding to raw object in the UI, issue ACCEPT/REJECT opinions, and verify a timeline renders from assertions' temporal fields.

**Acceptance Scenarios**:

1. **Given** an investigation, **When** evidence is added, **Then** evidence objects carry grading + provenance and appear in the investigation timeline.
2. **Given** the analyst workbench, **When** an entity is opened, **Then** graph neighborhood, timeline, map (if geolocation), and evidence panel render together.
3. **Given** a review decision, **When** persisted, **Then** it is visible in the review/timeline and searchable.

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome]
2. **Given** [initial state], **When** [action], **Then** [expected outcome]

---

### User Story 4 - Connector Ecosystem & Recon Orchestration (Priority: P2)

New data sources are added as **connectors** (web/search/dns/certificates/social/documents/code/public-records/archives/…), each producing standardized `Observation → Artifact → Mention → Candidate` outputs through one `AcquisitionWorker` contract. Investigation launches become reNgine-style **recon plans**: Investigation → Acquisition Plan → Tasks → Kafka → Collectors → Observations.

**Why this priority**: SpiderFoot proves that a huge connector ecosystem must be modular; reNgine proves recon task orchestration scales. This story makes the platform *connectable* and is independently testable, though it benefits from US1's statement model.

**Independent Test**: Define a connector adapter against a fixture source, run it through the dispatcher as a recon plan, and assert standard observation/candidate outputs against the AcquisitionWorker contract — no bespoke output formats.

**Acceptance Scenarios**:

1. **Given** a new source connector, **When** registered, **Then** `capabilities()/estimate()/acquire()` satisfy the AcquisitionWorker contract and produce standard observation events.
2. **Given** an investigation recon plan, **When** orchestrated, **Then** tasks flow through Kafka to collectors and back as observations without custom plumbing.
3. **Given** any connector output, **When** parsed, **Then** the parser interface (`can_parse`/`parse`) handles HTML/JSON/CSV/PDF/Email/Archive deterministically and safely.

---

### User Story 5 - Evidence Reasoning & Stream Provenance (Priority: P3)

The platform reasons about whether multiple sources **corroborate** (independent) or merely **copy** one original, assigns claim verdicts, and builds storylines. The event layer stays Kafka-native with immutable provenance and ontology packs.

**Why this priority**: investigator/kafSIEM patterns supply the *reasoning* and the *stream semantics*. These matter for decision quality and scale but are layered on stories 1-4.

**Independent Test**: Feed a contradiction fixture (source A says X, source B says ¬X) and a reprint fixture; assert corroboration/claim verdicts differ and that provenance survives stream replay.

**Acceptance Scenarios**:

1. **Given** corroborating independent sources, **When** evidence fusion runs, **Then** corroboration strengthens the claim verdict.
2. **Given** copied/derived sources, **When** evidence fusion runs, **Then** they consolidate to one chain and do not inflate support.
3. **Given** a replayed Kafka event stream, **When** consumers process, **Then** provenance fields survive and no duplicate rows are produced (idempotency).

---

### Edge Cases

- What happens when two "independent" sources actually derive from one upstream press release? — The evidence-independence engine detects reprint/copy edges and collapses them; `publication_count` stays distinct from `independent_sources` (FR-015).
- What happens when a candidate pair is ambiguous? — Default is DEFER; the correlation graph keeps a `possible_match` edge with reasons, and the analyst can review it without auto-merge.
- What happens when an analyst review contradicts the automatic admission decision? — The review is recorded as immutable provenance; downstream projections are rebuildable and reflect the review via events.
- What happens when a connector produces an unsupported format? — The parser registry falls back to plain text; dangerous/archive-heavy inputs are isolated per worker class and go to dead-letter/quarantine on repeated failure (FR-028).
- What happens on stream replay? — Consumers are idempotent on event_id/observation_id; no duplicate rows, provenance intact.
- What happens when temporal validity expires? — The assertion transitions to EXPIRED per its temporal policy; the original stays (FR-016).
- What if a donor license restricts use? — Only concepts/patterns are adopted, never code or assets; PANO's CC BY-NC is treated as inspiration-only.

### Edge Cases

- What happens when two "independent" sources actually derive from one upstream press release? — The evidence-independence engine detects reprint/copy edges and collapses them; `publication_count` stays distinct from `independent_sources` (FR-015 in feature 001).
- What happens when a candidate pair is ambiguous? — Default is DEFER; the correlation graph keeps a `possible_match` edge with reasons, and the analyst can review it without auto-merge.
- What happens when an analyst review contradicts the automatic admission decision? — The review is recorded as immutable provenance; downstream projections are rebuildable and reflect the review via events.
- What happens when a connector produces an unsupported format? — The parser registry falls back to plain text; dangerous/archive-heavy inputs are isolated per worker class and go to dead-letter/quarantine on repeated failure (FR-028 in feature 001).
- What happens on stream replay? — Consumers are idempotent on event_id/observation_id; no duplicate rows, provenance intact.
- What happens when temporal validity expires? — The assertion transitions to EXPIRED per its temporal policy; the original stays (FR-016 in feature 001).
- What if a donor license restricts use? — Only concepts/patterns are adopted, never code or assets; PANO's CC BY-NC is treated as inspiration-only.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST model every assertion as a statement record carrying `dataset_id`, `first_seen`, `last_seen`, `original_value`, `extraction_version`, and full provenance (FollowTheMoney → knowledge data language).
- **FR-002**: System MUST keep `publication_count` strictly separate from `independent_sources` / `independent_evidence_chains` (never equal — reprint-safe corroboration).
- **FR-003**: System MUST support temporal validity windows (`valid_from`/`valid_until`) per relationship and enforce the applicable temporal policy (FR-016), retaining originals on retraction/supersession.
- **FR-004**: System MUST maintain a correlation graph where `possible_match` candidate edges exist independently from entity identity, with raw_pair_score + reasons, and MUST NOT auto-merge without an admitted assertion (OpenOSINT).
- **FR-005**: System MUST preserve imperfect/uncertain candidates — default DEFER; never destructive REJECT; all decisions replayable (FR-013/FR-014).
- **FR-006**: System MUST record analyst review ACCEPT/REJECT/UNCERTAIN as immutable, replayable provenance linked to the reviewed candidate/assertion (Vitni).
- **FR-007**: System MUST expose the investigation+evidence workspace: targets, evidence objects, entities, relationships, timeline, sources, analyst decisions, each with provenance and evidence grading (Kipi).
- **FR-008**: System MUST provide a connector ecosystem where each source implements `capabilities()/estimate()/acquire()` and emits standard Observation/Artifact/Mention/Candidate outputs (SpiderFoot + AcquisitionWorker contract).

- **FR-009**: System MUST orchestrate investigation launches as recon plans (Investigation → Acquisition Plan → Tasks → Kafka → Collectors → Observations) with task orchestration and continuous monitoring (reNgine).
- **FR-010**: System MUST expose a unified parser interface (`can_parse`/`parse`) with deterministic findings for HTML/JSON/CSV/PDF/Email/Archive and other types (NetForensicAI).
- **FR-011**: System MUST evaluate corroboration vs copying (claim verdict, triangulation) and build storylines from consolidated evidence (investigator).
- **FR-012**: System MUST keep the event layer Kafka-native with immutable provenance, ontology packs, and idempotent consumers (kafSIEM).
- **FR-013**: System MUST present a merged graph/timeline/map entity inspector in the analyst workbench (PANO).
- **FR-014**: System MUST adopt only concepts/patterns from donors, never wholesale codebases or licensed assets (no Frankenstein; license safety).

### Key Entities *(include if feature involves data)*

- **Statement**: the unit of knowledge — subject/predicate/value, dataset id, first_seen/last_seen, original_value, extraction version, temporal validity, provenance (FTM).
- **CorrelationEdge**: `possible_match` (and similarity/derivation edges) between candidates, carrying raw_pair_score + reasons, existing without identity (OpenOSINT).
- **IndependenceChain**: citation/derivation cluster collapsing reprints into one independent evidence chain (investigator/FTM dataset boundary).
- **Investigation / Evidence**: targets, evidence objects with grading, timeline, analyst decisions (Kipi).
- **Connector**: a source adapter implementing the AcquisitionWorker contract with capabilities, estimate, acquire (SpiderFoot).
- **ReviewDecision**: ACCEPT/REJECT/UNCERTAIN recorded as immutable provenance (Vitni).
- **Claim / Storyline**: corroboration outcome and consolidated narrative over evidence (investigator).
- **ParserAdapter**: `can_parse`/`parse` interface for deterministic artifact parsing (NetForensicAI).
- **Ontology/SchemaPack**: declared entity/property types and admissible relations (FTM schema/ontology).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of assertions persist statement-level provenance (dataset, first/last seen, original_value, extraction_version); verified by contract tests on interpretation output.
- **SC-002**: Reprint corpus (N copies + 1 original) yields `publication_count = N+1` and `independent_sources = 1`; assertion tests prove no inflation.
- **SC-003**: Correlation graph creates `possible_match` edges without any auto-merge; resolution/admission contract tests show zero forced merges.
- **SC-004**: Every uncertain candidate is DEFER/QUARANTINE-replayable; a rejected rare evidence can be recovered and re-evaluated (mirrors SC-012 of feature 001).
- **SC-005**: Analyst review decisions are persisted and replayable as provenance; a review changes projections only via events (rebuildability holds).
- **SC-006**: A new connector can be registered and run end-to-end producing standard observations without bespoke formats; verified by a connector contract test.
- **SC-007**: Recon plan orchestration runs Investigation → Tasks → Kafka → Collectors → Observations with no custom plumbing; tested against fixtures.
- **SC-008**: Corroboration-vs-copy fixtures yield distinct claim verdicts; independent chains are counted correctly (see SC-002).
- **SC-009**: Stream replay produces no duplicate rows and preserves provenance (idempotency contract test).
- **SC-010**: The analyst workbench renders merged graph/timeline/map views with evidence panels and review controls; frontend tests cover each surface.

## Assumptions

- External donors are studied for patterns only; no donor dependency is added to the codebase (license safety, no vendor lock-in).
- Feature 001 (`001-global-osint-platform`) already supplies: Observation immutability, Kafka event envelope, admission engine, projections, TDA, bench harness; this feature integrates on top of them.
- The analyst workbench extends the existing React SPA (PANO/Vitni/Kipi = UX references, not dependencies).
- Connectors target public sources through public interfaces only; no bypass of authentication/access controls (Constitution VII).
- Statement/assertion schemas reuse feature 001 entity structures; this feature adds/strengthens provenance, temporal, correlation, and review fields.
- Bench/unittest run times stay modest; no new runtime services are required beyond the existing compose topology.
