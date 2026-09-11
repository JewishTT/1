---
description: "Specification for integrating real donor subsystems into the platform's core domain (knowledge model, resolution, parsers, connectors, investigation state)"
---

# Feature Specification: Donor Core Subsystems

**Feature Branch**: `005-donor-core-subsystems`

**Created**: 2026-09-08

**Status**: Draft

**Input**: User description: "Надо не адаптировать идеи, а вырезать конкретные куски кода из доноров и интегрировать их в платформу как рабочие подсистемы. Приоритеты: FollowTheMoney — единый knowledge model (Entity/Property/Statement/provenance/dataset/temporal/schema-ontology); OpenOSINT — resolution (кандидаты, человеческое ревью, недиструктивный dedup); Kipi — investigation/evidence workflow (клон пустой, только паттерны); PANO — референс UX (копировать нельзя); SpiderFoot — connector ecosystem (модули→observations→correlation); investigator — evidence reasoning (corroboration/claim/triangulation); reNgine — recon patterns (копировать нельзя); kafSIEM — Kafka/event model; Vitni — review/timeline; NetForensicAI — parser interface (can_parse/parse/registry) + evidence manifest + findings + timeline. Главное правило: берём конкретную подсистему, переписываем под event-driven архитектуру. НЕ Frankenstein: одна подсистема — один источник."

## User Scenarios & Testing

### User Story 1 - Unified knowledge model across the platform (Priority: P1)

Every pipeline stage (parsers, admission, resolution, projection, UI) exchanges
knowledge through one canonical model: named **Entities** carrying typed
**Properties** as first-class objects, grouped into **Statements** with explicit
**provenance** (source observation, dataset, confidence) and **temporal validity**
(valid_from / valid_until / referenced dates at day or year precision). Schema
knowledge lives in a **schema registry** (schema_name → Entity schema) that all
stages consult so the same concept (Person, Company, Account, ...) means the same
thing everywhere. Donor: FollowTheMoney (MIT) model layer
(`followthemoney/model.py`, `followthemoney/types/*`).

**Why this priority**: The user's brief names the knowledge model first. The auditors
showed the model is currently scattered (Engineers in `engine/assertions.py`,
EntityRecord in `services/catalog.py`, Statement in `db/schema.py`); without one
canonical model no downstream subsystem (resolution, evidence, connectors) can be a
real integration rather than a one-off port.

**Independent Test**: A single statement round-trips through the model — parse →
entity/property/statement → serialize → deserialize — with identical provenance,
dataset, and temporal fields; the schema registry resolves any registered
schema_name to its property set. This slice alone replaces the scattered
Entity/Statement types in shared domain.

**Acceptance Scenarios**:

1. **Given** a raw observation (e.g., a parsed news item naming a person and a company), **When** the shared model builds a Statement, **Then** it yields Entities and Properties with schema-backed names and a Statement carrying source observation id, dataset id, and optional confident/valid temporal bounds.
2. **Given** an Entity lacking a temporal bound, **When** serialized to the event envelope, **Then** no fabricated dates appear (temporal stays empty unless attested).
3. **Given** an unknown schema_name, **When** the registry is asked, **Then** a typed error is raised (or a project-defined extension schema), never a silent mis-typed Entity.

---

### User Story 2 - Resolution with human review and non-destructive merge (Priority: P1)

When the platform detects that two entities may be the same subject, it materializes
reviewable **candidate pairs** with scores and evidence links. An analyst reviews the
candidates; confirmed merges are **non-destructive** (original entities and their
evidence remain readable; the merge is recorded as resolution state that can be
re-opened and reversed). Resolution feeds the correlation graph so reviewers see
"these may be the same" inline. Donor: OpenOSINT (MIT) `openosint/graph` store and
resolution flow.

**Why this priority**: Second in the user's brief. Non-destructive, human-reviewed
resolution is the analytical core of the platform and directly matches the
Constitution's "Mention != Candidate != Entity" invariant.

**Independent Test**: Feeding two observations of the same subject produces a
candidate pair with a stable id; accepting it creates a merge record that preserves
both source entities; rejecting it leaves no merge; both actions emit resolution
events.

**Acceptance Scenarios**:

1. **Given** two Entities sharing indicative properties, **When** resolution runs, **Then** a Candidate with a deterministic pair key, a score vector, and linked evidence is created (never auto-merged).
2. **Given** an analyst accepting a candidate, **When** the merge is recorded, **Then** both original entities stay queryable and a resolution link (not deletion) is persisted.
3. **Given** a rejected candidate, **When** the decision is stored, **Then** the pair is not re-proposed at the same evidence level and the rejection is preserved with reasons.

---

### User Story 3 - Pluggable parser and evidence-manifest subsystem (Priority: P2)

Parsers are discovered through a **registry** that classifies raw content by
`can_parse(raw, hint)` and extracts via `parse(raw, meta)`, so new formats plug in
without touching pipeline wiring. Every extraction emits an **evidence manifest**
(finding → observation → raw object → source), aligning with the
Evidence-First Constitution rule. Each parser runs sandboxed with size/time limits.
Donor: NetForensicAI (MIT) `netforensicai/evidence` manager and parser interface
(evidence manifest, findings) and `apps/interpretation/parsers` wiring.

**Why this priority**: Parser plugability + evidence traces make every other
subsystem trustworthy. Directly requested in the brief (NetForensicAI parser
interface + manifest).

**Independent Test**: Registering a new parser is a one-line registry entry; a
registered format is classified and parsed; the produced finding carries a
manifest linking it to the raw object's sha256 and source id; hostile input is
quarantined, never parsed.

**Acceptance Scenarios**:

1. **Given** a content blob with an unknown format, **When** the registry probes parsers, **Then** `can_parse` returns false for all, there is no parse attempt, and the blob is quarantined with a reason.
2. **Given** a known format blob, **When** parsed, **Then** a Finding is returned that chains Finding → Evidence → Observation → Raw Object.
3. **Given** a parser hitting a size/time ceiling, **When** invoked, **Then** it is terminated, the failure recorded, and the event is safe to retry.

---

### User Story 4 - Connector ecosystem behind one plugin contract (Priority: P3)

Acquisition connectors register as capability-modules: each declares what it can
do, reports scan events, and obeys a shared module lifecycle (load / scan / stop)
with a bounded thread pool and event output channel. Observations from connectors
flow to the knowledge model through one normalization path. Donor: SpiderFoot (MIT,
logic layer) `spiderfoot/__init__.py` (sfEvent, sfModule lifecycle) and
`spiderfoot/target.py` already ported in prior work.

**Why this priority**: The Constitution's AcquisitionWorker contract is code-isolated;
a SpiderFoot-style module registry adds a pluggable connector ecosystem that fits
without violating the contract.

**Independent Test**: Two dummy connectors register, a scan produces events on a
shared channel, and stopping the module stops its scans; each event is
normalized to a single observation shape before entering the model.

**Acceptance Scenarios**:

1. **Given** a connector module declaring capabilities and an event output, **When** a scan starts, **Then** events are emitted on the task's channel and shutdown is prompt and clean on stop.
2. **Given** two connectors both reporting the same value, **When** events are emitted, **Then** they normalize to the same canonical target form (via the existing target layer) and map to the same Entity.
3. **Given** a connector raising while scanning, **When** the module faults, **Then** the failure is contained (task-level quarantine) and other connectors in the same run continue.

---

### User Story 5 - Investigation state and monitoring (Priority: P3)

Each investigation owns observable **state** (created / running / awaiting_review /
finding / closed) and **monitoring counters** (items examined, evidence ingested,
resolved candidates) surfaced in control-plane: analysts see progress without
digging into logs. Donor: investigator (MIT) `src/investigator.py` monitor/state
section and `Monitor`/`State` in the investigator CLI (`src/`, `lib/`).

**Why this priority**: Recommended by the Python-donor audit as a low-risk stdlib
port (≈940 LOC slice); completes the "investigation = first-class" Constitution
mandate with a concrete statemachine + telemetry.

**Independent Test**: Creating an investigation initializes state; emitting event
counters updates the monitor; closing locks the state and persists the final
summary. All visible through an API read-only endpoint.

**Acceptance Scenarios**:

1. **Given** a new investigation, **When** created, **Then** its state transitions to `running` and monitoring counters start at zero.
2. **Given** evidence and resolution events, **When** emitted, **Then** monitor counters advance atomically per investigation.
3. **Given** a closed investigation, **When** a late event arrives, **Then** it is parked (dead-letter) and the state is not mutated.

---

### User Story 6 - Review queue & timeline UI (Priority: P2)

Analysts review resolution candidates and assertions from the investigation UI:
a review queue with filters (review state, evidence strength, confidence, text),
stable sorting (unreviewed-first, newest, oldest, weakest-evidence) and derived
node status badges (`clear` / `needs_review` / `conflict`, evidence `supported` /
`gap`). Evidence timeline renders per-subject facts ordered by date, pulling from
the manifest chain. Donors: **vitni** (Apache-2.0) `app/renderer/src/features/review`
model is ported as pure logic into `apps/webapp/src/lib/donor/review.ts`;
**PANO** (CC BY-NC-4.0) contributes UX **patterns only** — timeline-first review,
grouping evidence by subject — documented in `contracts/ux-reference.md` (never copied).

**Why this priority**: The user's brief puts review/timeline interaction front and
center and explicitly asks for UI integration now (not a follow-up track). It also
gives the non-destructive resolution a human decision surface (US2) inside the product.

**Independent Test**: Pure review-model functions (build/filter/sort derived
assertions, node-status map, next-unreviewed) are vitest-covered; the UI renders a
review queue that filters/sorts and opens candidate decisions without crashing on
empty/unknown data.

**Acceptance Scenarios**:

1. **Given** reviewable assertions/candidates from the backend, **When** the review model derives them, **Then** each carries subject label, source title, supporting-source count, corroboration count, evidence status (`none|single|multiple`) and conflict status.
2. **Given** a filter set (state/evidence/confidence/query), **When** applied, **Then** the queue returns the sorted, filtered subset and `sort=weakest_evidence` / `unreviewed_first` order exactly as specified.
3. **Given** a subject with conflicting or evidence-gapped facts, **When** the status map is built, **Then** the node badge shows `conflict` / `needs_review` (or `gap`) and never crashes on unknown review states.

---

### Edge Cases

- What happens when extraction pulls in a heavy donor dependency (banal, rigour, netaddr, semhash)? The adapted module must be rewritten to stdlib / already-wired deps (FR-003).
- How are unknown schema names, missing temporal fields, or invalid candidate pair keys handled? Explicit errors / empty-safe types, never silent corruption (FR-004, FR-006).
- What about reNgine (GPLv3) and PANO (CC BY-NC-4.0)? Never copied — inspiration/pattern-only, documented per module (FR-005).
- What if a ported subsystem's domain class (e.g., Engineer/Assertion) already exists? The port becomes the canonical domain type and old handles are adapted, not duplicated (FR-007).
- How to make sure nothing is dead code? Every module is referenced by an executable consumer (service, API, or pipeline stage) and grep-checked (FR-008).

## Requirements

### Functional Requirements

- **FR-001**: Every adapted module MUST carry an attribution header: source repo, license, commit-ish, and a "what changed" note.
- **FR-002**: Adapted Python modules MUST use only stdlib + already-wired deps; heavy donor dependencies must be rewritten out. No new runtime dependencies.
- **FR-003**: Each adapted module MUST ship unit tests runnable in the existing suites (pytest / vitest) and the full regression MUST stay green.
- **FR-004**: Knowledge MUST flow through a single canonical model (Entity / Property / Statement + provenance + dataset + temporal + schema registry) in `apps/shared/domain`.
- **FR-005**: The license gate MUST be respected: reNgine (GPLv3), PANO (CC BY-NC-4.0), kipi (empty) are never copied; only pattern-level reuse for PANO/reNgine.
- **FR-006**: Resolution MUST be non-destructive: original entities/evidence never deleted; merges are persisted resolution links that can be reversed; rejections are preserved with reasons.
- **FR-007**: Existing domain handles (Engineers in `engine/assertions.py`, EntityRecord in `services/catalog.py`, Statement in `db/schema.py`) MUST be adapted to the canonical model, not duplicated alongside it.
- **FR-008**: Every extracted subsystem MUST be wired into a live consumer of an executable path (pipeline service, API, or UI component). Benchmark-harness-only integration is NOT sufficient.
- **FR-009**: Parsers MUST be registered via a `can_parse` / `parse` contract and be sandboxed (size / time / depth limits); extraction MUST emit an evidence manifest (Finding → Evidence → Observation → Raw Object).
- **FR-010**: Connector modules MUST declare capabilities and report events through a single observation normalization path into the knowledge model.
- **FR-011**: UI donor logic (vitni review model) MUST be ported pure into `apps/webapp/src/lib/donor/` (no framework/Tailwind/icon drag-in) and wired into a live webapp view.
- **FR-012**: PANO (CC BY-NC-4.0) MUST contribute UX patterns only — documented in `contracts/ux-reference.md`, never verbatim code.

### Key Entities

- **Entity**: named subject of an investigation with a schema-backed type (Person, Company, ...).
- **Property**: typed, schema-validated attribute of an Entity, first-class (not nested dicts).
- **Statement**: grouping of Entity + Properties with provenance (source observation id, dataset id, confidence) and temporal validity (valid_from / valid_until / precision).
- **Schema Registry**: maps schema_name → property definitions used by all stages.
- **Candidate (resolution)**: deterministic pair key + score vector + evidence links + review state (open / accepted / rejected / reversed).
- **Evidence Manifest / Finding**: chain Finding → Evidence → Observation → Raw Object (sha256), sandbox-produced by parsers/connectors.
- **Investigation State**: lifecycle state machine + monitoring counters per investigation.
- **Derived Review Assertion (UI)**: reviewable assertion enriched with subject label, source title, supporting-source/corroboration counts, evidence status, conflict status.
- **Node Review Status (UI)**: per-subject badge (`clear|needs_review|conflict`, evidence `supported|gap`).

## Success Criteria

### Measurable Outcomes

- **SC-001**: The canonical knowledge model replaces scattered Entity/Statement handling: 100% of new upstream flows (parsers, connectors) emit Statements through it, and existing handles are adapted (grep-verified, 0 remaining duplicated class definitions).
- **SC-002**: Resolution is fully non-destructive and human-reviewed: accepted/rejected/reversed decisions are persisted and replayable through the event log; original entities remain queryable after any merge.
- **SC-003**: ≥6 donor subsystems integrated as executable consumers (knowledge model, resolution, parser registry + manifest, connector registry, investigation state, review/timeline UI) with at least one independent passing test each.
- **SC-004**: Full regression stays green: shared ≥144, admission ≥41, bench ≥20, webapp ≥43; `ruff check` clean on touched Python; `tsc -b` and vitest clean on webapp.
- **SC-005**: Attribution + license compliance verified on every module (no copied GPL / CC BY-NC code; PANO/reNgine pattern-only contributions are documented).
- **SC-006**: Tasks T001–T0NN in `tasks.md` all closed `[x]` with the review gate passed.

## Assumptions

- Feature directory auto-numbered under `specs/` (sequential numbering: 005).
- No git branch hook exists (`.specify/extensions.yml` is absent), so no branch/hook steps run.
- User's brief priorities map to this track as: Knowledge model + resolution = P1, parsers/evidence + review/timeline UI = P2, connectors + investigation state = P3. The webapp is IN scope this track (vitni review-model port + PANO-pattern UX reference doc). The kafSIEM Go event-envelope backend is the only deferred slice (separate runtime, follow-up track).
- "One subsystem, one donor" (no Frankenstein): each adapted subsystem is sourced from a single donor listed in its attribution header; mixed-subsystem composition happens at the platform contract layer only.
- FollowTheMoney type-system helpers (banal, rigour) are inline-rewritten to stdlib, keeping the model dependency-free.
- Existing regression baselines (shared 144 / admission 41 / bench 20 / webapp 43) are the gate for acceptance; new tests add on top.