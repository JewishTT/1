# Feature Specification: Context-Driven Continuous Intelligence Fabric

**Feature Branch**: `024-context-driven-continuous-intelligence`
**Created**: 2026-10-02
**Status**: Approved — architecture position fixed by owner decision
**Input**: `input.md` (platform convergence ТЗ), `ui-upgrade.md` (UI 2.0 ТЗ), `wave0-verified-state.md` (verified baseline)
**Owner decisions**: D1=a, D2=c, D3=b, D4=a, D5=b (see §14)

## Wave 0 correction notice

This specification is written against the **verified** baseline in `wave0-verified-state.md`, not against the source ТЗ. Of 33 audited claims, 15 were false, 6 partial, 4 unverifiable, 8 true. Six named subsystems in the source ТЗ (`apps/investigation`, `apps/shared/skills/`, Context Graph, research lineage, `AssemblyBatch`/`DefinitionLifecycle`, the described Science layer with builders/pipelines/`SKILL.md`/`tool_spec`) **do not exist at all**. This is greenfield work on real primitives, not completion of an existing architecture.

---

## User Scenarios & Testing

### User Story 1 — Baseline is trustworthy (P1)

As a maintainer, I need the test suite to distinguish *my regression* from *pre-existing debt*, so that every later wave is verifiable.

**Why this priority**: 2 491 pass / 121 fail / 24 collection errors, and the 24 non-importing modules include `test_idempotency.py`, `test_infra_connectivity.py`, `test_redpanda_emission.py` — the very tests that verify transport idempotency. Without a published, honest baseline, no later wave can prove it did not break anything.

**Independent Test**: Given the repository at the pre-024 commit, when the full suite runs, then a machine-readable baseline record exists listing every failure and collection error by cause, and a re-run of any unrelated change produces zero delta against that record.

**Acceptance Scenarios**:
1. **Given** the current suite state, **When** the baseline capture runs, **Then** every one of the 121 failures and 24 collection errors is classified by root cause into a tracked category, with none dismissed as "flaky".
2. **Given** a recorded baseline, **When** an unrelated change is applied, **Then** the delta is exactly zero, and any new failure is attributable to the change.
3. **Given** the three transport-critical test modules that do not collect, **When** their collection errors are diagnosed, **Then** the package-path or import defect is identified for each, and each is either repaired or formally waived with a named reason and a follow-up owner.

---

### User Story 2 — One real observation completes the canonical loop (P1)

As an investigator, I need a single real observation to travel the entire canonical path — source to capture to Redpanda to interpretation to resolution to admission to graph to worldline to durable projection — so that the platform demonstrates a working loop rather than a designed one.

**Why this priority**: input.md §18.2 and the primary metric. Everything else is unverifiable until one observation survives the whole path.

**Independent Test**: Given Redpanda running with a pinned image and the canonical topic set published, when one real source fetch produces one observation, then the observation is retrievable from the durable worldline projection with an unbroken lineage chain from raw bytes to claim.

**Acceptance Scenarios**:
1. **Given** a live Redpanda broker with pinned digest, **When** an acquisition worker emits an observation, **Then** the event is consumed, resolved, admitted, materialized to the entity stream, and reflected in the worldline, with no layer writing directly into another layer's store.
2. **Given** an observation at each stage, **When** lineage is queried, **Then** the full chain raw object → capture → observation → mention → candidate → claim → entity is traversable in both direction, per the existing `evidence_lineage` contract.
3. **Given** the same observation event delivered twice, **When** the consumer processes both, **Then** exactly one durable result exists, deduplicated by event identity.

---

### User Story 3 — The context drives what is investigated (P1)

As an investigator, I want the durable research context to decide what must be learned next and to generate obligations automatically, so that the platform investigates rather than waits to be told.

**Why this priority**: input.md §11.1, §36.1, §36.4. This is the feature's namesake. Without it the platform is a pipeline; with it, it is a continuous intelligence system.

**Independent Test**: Given a context with one open obligation and available capabilities, when the Context Engine ticks, then a research action is proposed, routed to a concrete runtime, executed as a task, and the resulting observations are fed back into the obligation's satisfaction evaluation.

**Acceptance Scenarios**:
1. **Given** a context revision and a coverage gap, **When** the obligation generator runs, **Then** a `ResearchObligation` is created with a recorded reason naming the triggering rule and input event.
2. **Given** an open obligation, **When** the action proposer runs, **Then** a `ResearchAction` is proposed with expected information gain, estimated cost, and the capability requirements drawn from the declarative Source/Tool Catalogue, not from runtime method returns.
3. **Given** proposed actions, **When** operator approval is required, **Then** the system waits and records the decision; it does not self-execute.
4. **Given** a satisfied obligation, **When** new evidence contradicts a supporting claim, **Then** a contradiction is recorded and a new obligation is created rather than the claim being overwritten.

---

### User Story 4 — Investigation termination is honest (P2)

As an investigator, I want the system to distinguish "saturated and satisfied" from "not looked hard enough", so that conclusions are defensible.

**Why this priority**: input.md §15.1–§15.11, §18.5–18.6. Premature closure is the primary failure mode of an autonomous investigator.

**Independent Test**: Given a context whose source space is saturated with marginal gain below threshold, when the satisfaction evaluator runs, then the obligation closes with a machine-readable reason citing coverage and marginal gain; given a context that merely stopped early, the obligation remains open.

**Acceptance Scenarios**:
1. **Given** coverage 0.92 and marginal gain 0.03 against a declared threshold, **When** evaluation runs, **Then** the obligation is marked satisfied with both figures recorded in the closure reason.
2. **Given** an obligation closed, **When** a contradicting observation arrives, **Then** the context re-opens with a recorded re-opening reason, and the terminal state is not silently overwritten.
3. **Given** a fully resolved obligation set, **When** the operator requests closure, **Then** a termination report is produced naming every obligation, its terminal state, and its reason, including any abandoned obligation.

---

### User Story 5 — Science evaluates the real worldline (P2)

As an investigator, I want scientific evaluation anchored to durable worldline snapshots, so that "the model is sound" means something checkable rather than a private in-memory state.

**Why this priority**: input.md §7.7 and §27. Wave 0 found `rg worldline apps/science/**` returns zero hits — Science is currently exactly the private toy state the ТЗ forbids.

**Independent Test**: Given a committed worldline snapshot with a method fingerprint, when a causal or calibration evaluation runs, then the result is durably recorded against that snapshot and is reproducible by replay.

**Acceptance Scenarios**:
1. **Given** a durable worldline snapshot, **When** calibration runs, **Then** `abs(drift) <= tolerance` is evaluated against real data from that snapshot and the verdict is persisted.
2. **Given** an evaluation, **When** the worldline has advanced past the snapshot, **Then** the evaluation remains bound to its snapshot identity and does not silently read newer state.
3. **Given** a causal model, **When** it is evaluated, **Then** identification, estimation, and refutation each produce an explicit recorded outcome rather than a single opaque verdict.

---

### User Story 6 — The operator sees the loop (P3)

As an operator, I want the Investigation Workspace to show the context, obligations, and frontier, and to let me direct acquisition from the graph, so that the continuous loop is governable rather than opaque.

**Why this priority**: ui-upgrade.md §7 critical vertical slice. The loop must be demonstrable headless (input.md §34.3), but an ungovernable loop is not the product.

**Independent Test**: Given an investigation with real observations, when the operator opens the workspace and selects an entity, then claim, evidence, and timeline all resolve with selection and time range preserved, and acquisition can be triggered at the frontier without a page reload.

**Acceptance Scenarios**:
1. **Given** a selected entity, **When** the operator navigates graph → timeline → evidence → back to graph, **Then** selection and time range survive every transition.
2. **Given** an unresolved frontier obligation, **When** the operator triggers acquisition from the workspace, **Then** the action is proposed with approval, and resulting observations appear in the graph without a full refetch-and-replace.
3. **Given** a reload of a shared URL, **When** the workspace mounts, **Then** the complete working state is restored.

---

### Edge Cases

- Observation arrives with a locator that collides across captures → identity material includes `capture_id`, so it remains a distinct observation; the gate reports `duplicate` only on true identity match.
- Redpanda restarts mid-run with unacknowledged offsets → replay from the last committed offset is idempotent; no double-writes.
- A source is exhausted and obligation remains open → recorded as `blocked` with the exhaustion reason, never as `satisfied`.
- Two workers claim the same frontier item → Temporal lease plus `event_id` idempotency; one winner, the loser records a no-op tick.
- An obligation is proposed for a capability that does not exist → recorded as a proposed capability requirement, not silently implemented (input.md §13.9).
- Context revision races with a contradicting observation → revision commits transactionally with its decision record; a contradiction arriving mid-revision replays onto the next revision.
- Neo4j projection lags PostgreSQL authority → the serving projection is stale, never authoritative; the divergence is observable and rebuildable.
- A donor source cannot be repaired within the transfer boundary → the defect is repaired on transfer, or the capability is not imported; donor defaults are never inherited silently (AGENTS.md §2).
- Suite contains a test that fails only in CI ordering → classified in the baseline as order-dependent, not dismissed as flaky.
- `observed_at` is needed by a new event type → goes in the typed payload per D5, with the convention declared; no field 17.

---

## Requirements

### Functional Requirements — Baseline & Transport

- **FR-001**: The system MUST publish a machine-readable test baseline recording every currently failing test and every collection error, each classified by root cause, before any functional wave begins.
- **FR-002**: The three transport-critical modules that currently fail to collect (`test_idempotency.py`, `test_infra_connectivity.py`, `test_redpanda_emission.py`) MUST be repaired or formally waived with a named reason and follow-up owner.
- **FR-003**: Redpanda MUST be the single dev/live transport runtime, with its image pinned by digest; the unpinned `:latest` tag MUST NOT appear in any compose or configuration file.
- **FR-004**: Transport settings MUST default to the Redpanda profile as the canonical runtime, and the Kafka-compatible protocol contract MUST remain unchanged.
- **FR-005**: The Constitution Technology Baseline and every ADR that names Kafka as transport MUST be amended to state the actual architecture: Kafka-compatible protocol, Redpanda runtime, pinned digest.
- **FR-006**: The system MUST retain the existing `EventEnvelope` protobuf contract at 16 fields for this feature.
- **FR-007**: Event types requiring a logical observation time MUST carry `observed_at` inside their typed payload, under a single mandatory convention.
- **FR-008**: The system MUST document and enforce the semantic distinction: envelope `produced_at` is transport event production time; payload `observed_at` is evidence/event logical time.
- **FR-009**: The system MUST emit and consume the hermetic `NERVOUS_SYSTEM_EVENT_TYPES` set so a deterministic rebuild is possible without a live broker.

### Functional Requirements — Canonical Event Path

- **FR-010**: Every cross-layer communication MUST traverse the canonical event path; a layer MUST NOT write directly into another layer's store.
- **FR-011**: Every event MUST carry a stable identity, schema version, producer identity and version, production time, trace correlation, causation reference, and tenant identity, matching the existing `EventEnvelope`.
- **FR-012**: Every consumer MUST be idempotent under at-least-once redelivery, deduplicating by event identity.
- **FR-013**: Layer 0 MUST NOT become the production orchestration path; it MUST NOT be revived or wired. Its four hook `Protocol`s MAY be reused.
- **FR-014**: The canonical path MUST be built as new composition around existing primitives, not as a refactor of Layer 0.
- **FR-015**: Backpressure MUST reduce the acquisition rate rather than expand broker backlog (Constitution).
- **FR-016**: Malformed data, parser failures, policy uncertainty, and resource abuse MUST route to the `events.dlq` / `events.quarantine` lanes; rejected candidates MUST NOT be auto-deleted and MUST remain replayable.
- **FR-017**: The existing Common Crawl chain (index client, byte-range pull, WARC capture/extract, temporality contour, 5 `cc_temporality` events) MUST be wired onto the canonical path, not rewritten.

### Functional Requirements — Investigation & Temporal

- **FR-018**: The system MUST NOT create an `apps/investigation` pseudo-application.
- **FR-019**: Investigation state MUST remain in `control-plane/cp_domain/investigation.py` and its persistence schema.
- **FR-020**: `InvestigationWorkflow` and its activities MUST be registered with the Temporal worker; the lifecycle MUST be executable, not merely defined.
- **FR-021**: The existing 10-state investigation lifecycle MUST be preserved and exercised end-to-end.
- **FR-022**: Context Engine components MUST be built adjacent to the existing investigation domain, not behind a new application boundary.

### Functional Requirements — InvestigationContext

- **FR-023**: The system MUST provide a new `InvestigationContext` distinct from `EvidenceContext`; it MUST NOT be an overload, rename, or extension of the latter.
- **FR-024**: `InvestigationContext` identity MUST be `CXI-{digest128(canonical_context_material)}` over identifying fields only, and MUST NOT depend on mutable revision state.
- **FR-025**: Context revision identity MUST be separate from context identity, carrying a monotonically increasing `revision` and a `parent_revision`.
- **FR-026**: Context snapshots MUST be append-only; a revision MUST NOT mutate a prior snapshot.
- **FR-027**: Context state MUST be durably persisted in a transactional store and MUST survive process restart.
- **FR-028**: Context state MUST be reconstructible by replay from the context definition, decision history, and event log.
- **FR-029**: Context MUST record provenance: every revision MUST record the events, decisions, and operator actions that caused it.
- **FR-030**: The system MUST distinguish "not yet investigated" from "investigated and found nothing" as first-class states.
- **FR-031**: Cross-investigation linkage MUST be explicit and recorded as a scope decision; an investigation MUST NOT silently absorb another's evidence.
- **FR-032**: `EvidenceContext` MUST remain unmodified in its fields, so that every existing stored `context_id`, the unique fingerprint index, and every `context_ref` continue to validate.

### Functional Requirements — Research Obligations

- **FR-033**: `ResearchObligation` MUST be a durable first-class object with identity, owning context, question, rationale, target knowledge type, priority, status, creator, satisfaction criteria, confidence, related hypotheses, and blocking dependencies.
- **FR-034**: Obligation generation MUST be rule-based, versioned, and inspectable; the triggering rule and input event MUST be recorded.
- **FR-035**: Obligations MUST NOT be silently dropped; every obligation MUST reach `satisfied` or `abandoned` with a recorded reason, or the set MUST be reported non-closed.
- **FR-036**: `ResearchAction` MUST be proposed, MUST NOT be executed directly, and MUST be realized as concrete tasks with recorded runtime routing.
- **FR-037**: Obligation satisfaction MUST be evaluated by a pure, versioned function of obligation, evidence index, saturation state, and contradiction state, and MUST be unit-testable in isolation.
- **FR-038**: Contradictory evidence MUST create a contradiction record and a new obligation, never a silent claim overwrite.
- **FR-039**: Obligation lifecycle MUST be an append-only durable history, answering "why did we stop investigating this, and when".
- **FR-040**: Actions that no existing capability can satisfy MUST be recorded as proposed capability requirements, never implicitly implemented.

### Functional Requirements — Context Engine

- **FR-041**: The Context Engine MUST be decomposed into an obligation generator, a satisfaction evaluator, an action proposer, a decision recorder, and a revision manager; it MUST NOT be a single module implementing all five.
- **FR-042**: The Context Engine MUST be incremental: an update MUST process only what changed and MUST be able to explain which change caused which update.
- **FR-043**: The Context Engine MUST be deterministic given the same event sequence, rules version, and parameters; wall-clock or unseeded randomness is forbidden in context state except where an explicit `observed_at` is recorded.
- **FR-044**: Every context update MUST be explainable: which input event, which rule, and which prior state produced the new state.
- **FR-045**: The constitutional core MUST be deterministic, versioned, and inspectable, and MUST remain fully functional with the adaptive layer disabled.
- **FR-046**: The Context Engine MUST support an explicit deterministic replay mode and an adaptive operating mode, recorded per decision.
- **FR-047**: Context revisions MUST commit transactionally with their decision records.
- **FR-048**: The Context Engine MUST define and apply an explicit policy for missing, late, and out-of-order events.
- **FR-049**: The Context Engine MUST NOT depend on a specific UI, transport, or storage engine for its core logic.
- **FR-050**: The Context Engine MUST expose queries for current state, open/satisfied obligations, contradictions, decisions, and revision history.
- **FR-051**: The Context Engine MUST be operable and testable independently of the rest of the platform.

### Functional Requirements — Saturation, Frontier, Feedback

- **FR-052**: Saturation MUST be a first-class computed state accounting for distinct sources consulted, source diversity, marginal information gain, and stopping conditions.
- **FR-053**: Acquisition count alone MUST NOT satisfy an obligation; coverage and saturation are the sufficiency criteria.
- **FR-054**: Expected and realised information gain MUST be recorded per action.
- **FR-055**: The system MUST support budget-bounded investigation and report budget consumption against obligation satisfaction.
- **FR-056**: Source exhaustion MUST be an explicit terminal condition distinct from "unvisited".
- **FR-057**: Termination MUST record why the system stopped, what remains unknown, and what would re-open the investigation.
- **FR-058**: The research frontier MUST be a durable, queryable object rather than operator memory.
- **FR-059**: Action memory MUST record which acquisition was already attempted for which obligation.
- **FR-060**: Hypothesis and question proposal MUST be autonomous from contradictions, coverage gaps, low-confidence claims, and saturation shortfalls.

### Functional Requirements — Storage Authority & Projection

- **FR-061**: PostgreSQL MUST be the authoritative store for the Context Graph and for operational/research graph state.
- **FR-062**: Neo4j MUST remain a rebuildable serving projection behind the existing `GraphProjection` / `GraphReader` / `GraphSnapshot` / `GraphTraversal` contracts.
- **FR-063**: No third graph store or graph copy MUST be introduced.
- **FR-064**: The authority/projection split MUST be recorded in a dedicated ADR.
- **FR-065**: Any Neo4j divergence from PostgreSQL MUST be observable and rebuildable; Neo4j MUST never be treated as authoritative.
- **FR-066**: The system MUST resolve the existing PG-graph / Neo4j-graph duplication so that exactly one authoritative and one serving copy remain.

### Functional Requirements — Acquisition Routing

- **FR-067**: `runtime_ref` MUST remain the routing identity for acquisition; capabilities MUST remain a compatibility check and MUST NOT select the runtime.
- **FR-068**: Declarative capability data MUST be sourced from the existing Source/Tool Catalogue (146 definitions, 20 categories) exposed via the existing API.
- **FR-069**: The catalogue MUST act as the bridge between the Context Planner and the Runtime Dispatcher.
- **FR-070**: Existing live-proven acquisition runtimes (SearXNG, Airbyte, BBOT, external tools: Maigret, SpiderFoot) MUST be reused, not replaced.
- **FR-071**: Acquisition MUST emit captures and records only; it MUST create no entity, claim, or membership.
- **FR-072**: The existing primary-processing contract MUST be preserved: raw artifact always emitted unchanged alongside any derived cleaned artifact, with derived provenance recorded and no clock of its own.
- **FR-073**: Acquisition MUST remain at-least-once with idempotent identity derivation.

### Functional Requirements — Worldline & Entity Stream

- **FR-074**: The worldline MUST be materialized from the canonical event path, not from a private path.
- **FR-075**: A canonical entity stream and life-event model MUST exist, honouring the existing `graph_invariant` guarantees (purity, determinism, tz-aware, dedup, mixed-input rejection).
- **FR-076**: Durable worldline snapshots MUST exist with a method and dependency fingerprint.
- **FR-077**: Every worldline state MUST record the events that produced it.
- **FR-078**: Entity novelty, evidence novelty, and structural novelty MUST remain distinct signals and MUST NOT be collapsed into one score (Constitution invariant 8).

### Functional Requirements — Lineage & Traceability

- **FR-079**: All three lineages MUST exist and remain distinct: evidence, derivation, and research.
- **FR-080**: Research lineage MUST be implemented as `Context → Obligation → Action → Task → Result → ContextRevision`, absent today.
- **FR-081**: Every derived artifact MUST declare its inputs by stable identity, dependency versions, parameters, and producing code version, and MUST be reconstructible from them.
- **FR-082**: The system MUST maintain a dependency graph over artifacts so an input change is traceable to every affected output.
- **FR-083**: Every conclusion MUST be answerable back to raw evidence, parser version, rules version, and decisions.
- **FR-084**: Existing evidence and derivation lineage behaviour MUST be preserved unchanged.

### Functional Requirements — Science Convergence

- **FR-085**: Science state MUST be durable and anchored to worldline snapshots; the current in-memory `science.*`-only store MUST NOT remain the sole state.
- **FR-086**: Every scientific evaluation MUST be bound to a snapshot identity and MUST NOT silently read newer worldline state.
- **FR-087**: Causal evaluation MUST implement explicit identification, estimation, and refutation stages, each with a recorded outcome.
- **FR-088**: Topological analysis MUST consume real worldline windows.
- **FR-089**: Change-point detection and calibration `abs(drift) <= tolerance` MUST be implemented against real data.
- **FR-090**: Method and dependency fingerprints MUST be durable so results are reproducible by replay.
- **FR-091**: Statistical, causal, and epistemic layers MUST remain separable.
- **FR-092**: TDA MUST NOT be treated as a truth oracle (Constitution invariant 6).

### Functional Requirements — Non-Functional

- **FR-093**: The same inputs, rules version, and parameters MUST produce the same outputs.
- **FR-094**: Every derived artifact MUST be reconstructible without network re-acquisition, reading raw bytes by reference with the same parser version and policy.
- **FR-095**: Every state transition MUST be durably committed before it is observable.
- **FR-096**: Every decision MUST be explainable by context, obligation, evidence, and rule.
- **FR-097**: Contradiction, incompleteness, contested claims, low confidence, and unknown MUST be first-class representable states.
- **FR-098**: Resource use MUST be observable and budgetable per investigation.
- **FR-099**: The platform MUST remain fully operable on one machine with local services, with no external SaaS dependency for correctness.
- **FR-100**: SSRF, DNS-rebinding, sandboxed parsing, egress policy, and resource limits MUST be enforced (Principle VII); the Layer 0 fetch pattern MUST NOT be revived.

### Functional Requirements — UI 2.0

- **FR-101**: The UI stack MUST remain React 18, Vite, Zustand, TanStack Query, Cytoscape, ECharts, CSS Modules with design tokens; no framework substitution.
- **FR-102**: All 15 palette tokens and their exact values MUST be applied; hardcoded hex values in components MUST be eliminated.
- **FR-103**: `data-density` and `data-theme` MUST be written to the DOM by the shell; three density modes (`COMPACT`, `STANDARD`, `COMFORTABLE`, default `STANDARD`) MUST apply globally including graph and timeline.
- **FR-104**: Width-based breakpoints at 1024/1280/1440/1920/2560 MUST be implemented; fixed-pixel-only layout MUST NOT persist.
- **FR-105**: The global `SelectionState` MUST contain all nine specified fields; `graphMode`, `lineageMode`, `focusedPath`, and `evidenceIds` MUST live in the store, not component state, so they survive view switches.
- **FR-106**: TanStack Query MUST own server state only; Zustand MUST own client state only; shared payloads MUST NOT be duplicated under per-view query keys in a way that allows divergent invalidation.
- **FR-107**: URL state MUST encode investigation, object selection, view, time range, filters, and graph mode, and MUST restore the full working state on reload.
- **FR-108**: All eight views MUST ship real content; the four currently rendering `StagePlaceholder` MUST be completed, and no placeholder mechanism may remain.
- **FR-109**: Completed-but-unmounted surfaces (`src/ops/`, `src/quality/`, `src/objects/` models with their virtualization) MUST be connected to the workspace.
- **FR-110**: The nine currently failing frontend tests MUST pass; the `canvas-{view}` test-id contract MUST be restored so Stages 3–4 surfaces do not break the Stage-2 test contract.
- **FR-111**: The critical vertical slice MUST work with zero full page reloads and preserved selection throughout.
- **FR-112**: No neon, purple/magenta, glassmorphism, Web3 chrome, emoji iconography, rainbow series palettes, or decorative HUD elements may appear.
- **FR-113**: Every interactive element MUST have an accessible name, keyboard path, visible focus, and tooltip when icon-only; zero WCAG AA violations.
- **FR-114**: Route-level code splitting, table virtualization above 500 rows, and non-blocking graph layout MUST be implemented.
- **FR-115**: Every view MUST render against a fixture server with no backend running.
- **FR-116**: Missing data MUST render a specific honest empty state naming the missing dependency; fabricated numbers are forbidden in a production build.

### Key Entities

- **InvestigationContext** (`CXI-`): durable research scope; identity independent of revision; append-only revisions; distinct from `EvidenceContext`.
- **ContextRevision**: a committed context state with `revision`, `parent_revision`, provenance to events/decisions/operator actions.
- **ResearchObligation**: a durable statement of what must be learned, why, and what would answer it; carries satisfaction criteria and terminal status.
- **ResearchAction**: a candidate means of satisfying an obligation, with expected information gain, estimated cost, capability requirements, and approval state; realized as tasks.
- **ContextFrontier**: durable queryable representation of open obligations and their readiness for action.
- **ContextDecision**: an append-only record of a Context Engine decision, naming input event, rule, and prior state.
- **SaturationState**: coverage, source diversity, marginal gain, and stopping condition for a source space against an obligation.
- **ActionMemory**: record of which acquisition was attempted for which obligation, preventing repeated work.
- **ResearchLineage**: `Context → Obligation → Action → Task → Result → ContextRevision`.
- **WorldlineSnapshot**: durable, fingerprinted projection state that scientific evaluations bind to.
- **MethodFingerprint**: dependency and code version identity making an evaluation reproducible.
- **TestBaselineRecord**: machine-readable classification of every pre-existing failure and collection error.

### Success Criteria

- **SC-001**: The published baseline accounts for all 121 failures and all 24 collection errors by root cause, and an unrelated change produces exactly zero delta against it.
- **SC-002**: All three transport-critical test modules collect and run.
- **SC-003**: Redpanda image is pinned by digest; zero occurrences of an unpinned `:latest` tag in transport configuration.
- **SC-004**: One real observation completes the full canonical loop and produces durable downstream state, with unbroken lineage from raw bytes to claim in both directions.
- **SC-005**: A context with unresolved obligations demonstrably generates actions, executes them, and folds the resulting observations back into obligation evaluation.
- **SC-006**: For any investigation, the system reports open, satisfied, and contradicted obligations with reasons.
- **SC-007**: An investigation can be closed with a formal termination report and re-opened on contradicting evidence.
- **SC-008**: Every conclusion is traceable to raw evidence, parser version, rules version, and decisions.
- **SC-009**: Exactly one authoritative graph (PostgreSQL) and one serving projection (Neo4j) exist; no third copy exists.
- **SC-010**: Context state survives process restart and is reconstructible by replay.
- **SC-011**: The Context Engine runs correctly with the adaptive layer fully disabled.
- **SC-012**: A scientific evaluation bound to a snapshot is reproducible by replay and does not read post-snapshot state.
- **SC-013**: `npm run build` succeeds, `npm run lint` reports zero errors, `npm test` reports zero failures.
- **SC-014**: The critical vertical slice completes with zero full page reloads and preserved selection throughout.
- **SC-015**: All eight views ship real content with no remaining placeholder mechanism.
- **SC-016**: All 15 palette tokens match their specified values with zero hardcoded hex in components.
- **SC-017**: Density and theme toggles produce measurable pixel changes; three density modes apply to graph and timeline.
- **SC-018**: Visual regression passes at 1440×900, 1920×1080, and 2560×1440.
- **SC-019**: The platform runs locally with no external SaaS dependency for correctness.
- **SC-020**: The full suite passes deterministically, or the residual delta against the published baseline is exactly zero.

---

## Architecture position (owner-fixed)

| Decision | Choice | Consequence binding on this spec |
|---|---|---|
| **D1** transport | **(a)** Redpanda is the single dev/live runtime; Kafka-compatible protocol retained; baseline and ADRs amended to actual architecture; digest pinned; settings default to Redpanda profile | FR-003…FR-005 |
| **D2** graph storage | **(c)** PostgreSQL authoritative for Context Graph and operational/research graph state; Neo4j a rebuildable serving projection via existing `GraphProjection`; no third copy; dedicated ADR | FR-061…FR-066 |
| **D3** investigation | **(b)** no `apps/investigation`; extend `control-plane/cp_domain/investigation.py`; drive lifecycle to a real `InvestigationWorkflow` and **actually register** workflow/activities in Temporal; Context Engine built adjacent | FR-018…FR-022 |
| **D4** routing | **(a)** `runtime_ref` stays routing identity, capabilities stay compatibility check; §4.7 closed via declarative capabilities of the existing Source/Tool Catalogue; catalogue is the planner→dispatcher bridge; runtime contract unchanged | FR-067…FR-069 |
| **D5** timestamps | **(b)** `EventEnvelope` not extended now; `observed_at` / `logical_time` in typed payload contracts under one mandatory convention; `produced_at` = transport production time, payload `observed_at` = evidence logical time; field 17 deferred | FR-006…FR-008 |

## Assumptions

- The existing acquisition runtimes, Source/Tool Catalogue, primary-processing package, deterministic identity, observation gate, object store, and Common Crawl chain are correct and reused as-is; Wave 0 found them working and load-bearing.
- `EvidenceContext` stays frozen in its fields; `InvestigationContext` follows the existing `SemanticRegime` pattern — a separate content-addressed object referencing `context_ref` one-way.
- Wave 0's verdict table remains the planning baseline. Any later discovery that contradicts it triggers a re-verification entry, not a silent plan change.
- Test debt is a **precondition, not an architecture blocker**: the baseline is recorded first so later waves are measurable, but no architecture decision waits on a green suite.
- No architectural question requiring owner judgement remains open. Any new conceptual contradiction discovered during implementation halts that item per `AGENTS.md` §1.1.
