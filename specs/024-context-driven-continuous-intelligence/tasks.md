# Tasks: Context-Driven Continuous Intelligence Fabric

**Feature**: 024-context-driven-continuous-intelligence
**Plan**: `plan.md` · **Spec**: `spec.md` (116 FR)
**Baseline**: `wave0-verified-state.md`

## Conventions

- `[P]` — parallelizable within its wave. `[S]` — sequential, on the critical path.
- Every task names the FRs it satisfies. A task with no FR is a defect.
- Donor/platform reuse is mandatory before new code (`AGENTS.md` §1). Every task that writes new code MUST state what it takes ready-made, what it takes from platform code, and what it writes itself.
- Conceptual contradiction → halt and ask (`AGENTS.md` §1.1).

## Phase 0 — Test/Infra Baseline

**Entry**: none. **Exit**: `test-baseline.md` published; unrelated change = zero delta.

- [ ] **T001** `[P]` Diagnose all 24 collection errors; record root cause per module. The three transport-critical ones (`test_idempotency.py`, `test_infra_connectivity.py`, `test_redpanda_emission.py`) get repaired, not waived. FR-001, FR-002
- [ ] **T002** `[P]` Classify the 121 failures by root cause into tracked categories; none dismissed as flaky. FR-001
- [ ] **T003** `[P]` Triage the 25 `test_acquisition_worker.py` failures — they sit under the stage the loop depends on. FR-001
- [ ] **T004** `[P]` Classify the 4 `test_layer0_direct_pipeline.py` failures as expected-dead-code, since 021 FR-172 orders that orchestrator deleted. FR-001
- [ ] **T005** `[S]` Write `test-baseline.md`: machine-readable, per-test, with root cause and disposition. FR-001
- [ ] **T006** `[S]` Build the delta harness: run suite, diff against baseline, fail only on new breakage. FR-001, SC-001
- [ ] **T007** `[S]` Make CI report failures honestly — no suppression, no auto-skip of unclassified failures. FR-001, SC-020

## Phase 1 — Redpanda Canonical Transport (D1=a)

**Entry**: T001–T007. **Exit**: digest pinned, `:latest` gone from transport, broker reachable, emission tests pass.

- [ ] **T008** `[P]` Resolve and pin the Redpanda image by digest; pin `redpanda-console` too. Zero `redpanda:latest` occurrences. FR-003, SC-003
- [ ] **T009** `[P]` Promote Redpanda from `streaming`-profile-only to the canonical dev/live profile; wire it into the default startup path. FR-003, FR-004
- [ ] **T010** `[P]` Repoint `KafkaSettings` (`apps/shared/config/settings.py:28-32`) defaults to the Redpanda profile; keep the Kafka-compatible protocol contract untouched. FR-004
- [ ] **T011** `[P]` Amend the Constitution Technology Baseline to state actual architecture: Kafka-compatible protocol, Redpanda runtime, pinned digest. FR-005
- [ ] **T012** `[P]` Audit and amend the 24 ADRs that assume Kafka as transport. FR-005
- [ ] **T013** `[P]` Document the timestamp convention (D5=b): envelope `produced_at` = transport production time; payload `observed_at` = evidence logical time; `logical_time` where an interval is meaningful. FR-007, FR-008
- [ ] **T014** `[P]` Fill the 0-line `apps/shared/contracts/` stub with typed payload contracts, each declaring whether it requires `observed_at`/`logical_time` per the convention. FR-006, FR-007
- [ ] **T015** `[S]` Verify broker health and run the repaired emission and idempotency tests green. FR-002, FR-009
- [ ] **T016** `[S]` Wire `NERVOUS_SYSTEM_EVENT_TYPES` (`topics.py:145-154`) into the hermetic bus for deterministic rebuild without a live broker. FR-009

## Phase 2 — Canonical Event Loop

**Entry**: Phase 1. **Exit**: one real observation completes the loop with durable downstream state; duplicate delivery yields one result.

- [ ] **T017** `[S]` Build the new composition root around existing primitives. Not a refactor of Layer 0 — Layer 0 stays dead (021 FR-172). Reuse its four hook `Protocol`s only (`layer0_pipeline.py:121,135,143,149`). FR-013, FR-014
- [ ] **T018** `[P]` Enforce single-hop communication: no layer writes into another layer's store. Contract-level guard, not convention. FR-010
- [ ] **T019** `[P]` Make every consumer idempotent on event identity, deduplicating on `event_id`/`task_id`/`observation_id`/projection offsets. FR-012
- [ ] **T020** `[P]` Route malformed data, parser failures, policy uncertainty, and resource abuse to `events.dlq`/`events.quarantine`; rejected candidates never auto-deleted, always replayable. FR-016
- [ ] **T021** `[P]` Implement backpressure that reduces acquisition rate instead of growing broker backlog (Constitution). FR-015
- [ ] **T022** `[P]` Wire the existing Common Crawl chain onto the canonical path: index client, byte-range pull, WARC capture/extract, temporality contour, 5 `cc_temporality` events. Existing code, not rewritten. FR-017
- [ ] **T023** `[P]` Enforce the Security-First fetch boundary: SSRF guard, DNS-rebinding protection, egress policy, resource limits. Do NOT reuse Layer 0's `follow_redirects=True` with no allowlist (`acquisition_loop.py:51-53`). FR-100
- [ ] **T024** `[S]` Verify event envelope conformance: identity, schema version, producer identity/version, production time, correlation, causation, tenant. FR-011
- [ ] **T025** `[S]` Prove one real observation end-to-end: source → capture → Redpanda → interpretation → resolution → admission → graph → worldline → durable projection. SC-004, FR-010
- [ ] **T026** `[S]` Prove lineage traversable in both directions per the existing `evidence_lineage` contract, raw bytes to claim unbroken. FR-083
- [ ] **T027** `[S]` Prove duplicate delivery produces exactly one durable result. FR-012

## Phase 3 — Investigation + Temporal Registration (D3=b)

**Entry**: Phase 2. **Exit**: a Temporal-driven investigation traverses its 10-state lifecycle with durable history.

- [ ] **T028** `[S]` Register `InvestigationWorkflow` (`workflows/investigation.py:190`) and `RecrawlWorkflow` (`:278`) on task queue `cognitive-investigations` (`:39`) in `worker.py`. Wave 0: this queue has **no worker registered on it** — both workflows are dead code in Temporal terms. FR-020
- [ ] **T029** `[P]` Implement the workflow activities `InvestigationWorkflow` requires but Temporal never supplied. FR-020
- [ ] **T030** `[P]` Preserve the 10-state lifecycle (`LifecycleState`, `investigation.py:57`) and `InvalidLifecycleTransition` (`:69`) semantics exactly; do not redefine states. FR-021
- [ ] **T031** `[P]` Extend investigation domain in `cp_domain/investigation.py` for context linkage. No `apps/investigation` pseudo-app. FR-019, FR-022, FR-018
- [ ] **T032** `[S]` Prove the lifecycle executes end-to-end in Temporal with durable history — not merely defined. FR-020, FR-021
- [ ] **T033** `[S]` Verify the Context Engine can sit adjacent to this domain without a new app boundary. FR-022

## Phase 4 — Context Engine

**Entry**: Phase 3. **Exit**: context survives restart, replay reconstructs it, adaptive layer disable-able, `EvidenceContext` verifiably unchanged.

- [ ] **T034** `[P]` Build `InvestigationContext` with `CXI-{digest128(canonical_context_material)}` identity over identifying fields only, independent of revision state. FR-024
- [ ] **T035** `[P]` Implement revision identity: `revision` monotonic, `parent_revision` linking, separate from `context_id`. FR-025
- [ ] **T036** `[P]` Implement append-only snapshots; a revision never mutates a prior snapshot. FR-026
- [ ] **T037** `[P]` Durable transactional persistence; survives process restart. FR-027
- [ ] **T038** `[P]` Replay reconstruction from context definition + decision history + event log. FR-028
- [ ] **T039** `[P]` Per-revision provenance: which events, decisions, operator actions caused it. FR-029
- [ ] **T040** `[P]` Model "not yet investigated" vs "investigated and found nothing" as distinct first-class states. Wave 0: platform expresses unknown as `None` (`TemporalSlice.burstiness`, `ContextTrustState.UNVERIFIED`) — inherit that discipline, do not add a third state. FR-030
- [ ] **T041** `[P]` Explicit scope linkage; an investigation never silently absorbs another's evidence. FR-031
- [ ] **T042** `[P]` Verify `EvidenceContext` fields unchanged and every stored `context_id`, `uq_evidence_context_fingerprint`, and `context_ref` still validates. Wave 0: adding a field invalidates all of them. FR-023, FR-032
- [ ] **T043** `[P]` Obligation generator component. FR-041
- [ ] **T044** `[P]` Satisfaction evaluator component. FR-041
- [ ] **T045** `[P]` Action proposer component. FR-041
- [ ] **T046** `[P]` Decision recorder component. FR-041
- [ ] **T047** `[P]` Revision manager component. FR-041, FR-047
- [ ] **T048** `[P]` Verify the five components are genuinely separate — no god object. FR-041
- [ ] **T049** `[P]` Incremental update: process only what changed, explain which change caused which update. FR-042, FR-044
- [ ] **T050** `[P]` Determinism: same event sequence + rules version + parameters = same state; no wall-clock or unseeded randomness except explicit `observed_at`. FR-043
- [ ] **T051** `[P]` Constitutional core vs adaptive layer separation; core fully functional with adaptive disabled. FR-045
- [ ] **T052** `[P]` Deterministic replay mode vs adaptive mode, recorded per decision. FR-046
- [ ] **T053** `[P]` Explicit policy for missing, late, out-of-order events; no context corruption. FR-048
- [ ] **T054** `[P]` Core logic independent of UI, transport, storage engine. FR-049
- [ ] **T055** `[S]` Query interface: current state, open/satisfied obligations, contradictions, decisions, revision history. FR-050
- [ ] **T056** `[S]` Prove the engine runs and tests independently of the rest of the platform. FR-051
- [ ] **T057** `[S]` Every context update explainable by input event + rule + prior state. FR-044, FR-096

## Phase 5 — Obligation / Frontier

**Entry**: Phase 4. **Exit**: obligations reported with reasons; formal termination and re-opening work.

- [ ] **T058** `[P]` `ResearchObligation` with full attribute set: identity, context, question, rationale, target knowledge type, priority, status, creator, satisfaction criteria, confidence, related hypotheses, blocking dependencies. FR-033
- [ ] **T059** `[P]` Versioned, inspectable generation rules; record triggering rule and input event. FR-034
- [ ] **T060** `[P]` `ResearchAction` proposal: expected information gain, estimated cost, capability requirements, approval state. FR-036
- [ ] **T061** `[P]` Realize actions as concrete tasks with recorded runtime routing; actions never executed directly. FR-036
- [ ] **T062** `[P]` Append-only obligation lifecycle history answering "why did we stop, and when". FR-039
- [ ] **T063** `[P]` Terminal-state enforcement: every obligation reaches `satisfied` or `abandoned` with reason, or the set reports non-closed. FR-035
- [ ] **T064** `[P]` Satisfaction as a pure versioned function of obligation + evidence index + saturation + contradiction; unit-testable in isolation. FR-037
- [ ] **T065** `[P]` Contradiction handling: new obligation or contradiction record, never silent claim overwrite. FR-038
- [ ] **T066** `[P]` Unsatisfiable capability → recorded as proposed capability requirement, never implicitly implemented. FR-040
- [ ] **T067** `[P]` Durable queryable frontier. FR-058
- [ ] **T068** `[P]` Action memory: which acquisition was attempted for which obligation. FR-059
- [ ] **T069** `[P]` Autonomous hypothesis and question proposal from contradictions, coverage gaps, low confidence, saturation shortfall. Wave 0: `science/hypotheses/` exists but is operator-triggered only — this makes it autonomous. FR-060
- [ ] **T070** `[P]` Saturation model: distinct sources, source diversity, marginal gain, stopping conditions. FR-052
- [ ] **T071** `[P]` Forbid acquisition-count closure; coverage + saturation are the sufficiency criteria. FR-053
- [ ] **T072** `[P]` Expected and realised information gain recorded per action. FR-054
- [ ] **T073** `[P]` Budget-bounded investigation with consumption reported against satisfaction. FR-055
- [ ] **T074** `[P]` Source exhaustion as explicit terminal condition, distinct from unvisited. FR-056
- [ ] **T075** `[S]` Honest termination: record why it stopped, what remains unknown, what would re-open. FR-057
- [ ] **T076** `[S]` Re-opening on contradicting evidence; terminal state never silently overwritten. SC-007
- [ ] **T077** `[S]` Report open/satisfied/contradicted obligations with reasons for any investigation. SC-006

## Phase 6 — Multi-Source Acquisition (D4=a)

**Entry**: Phases 5, 2. **Exit**: obligation routes to a concrete runtime and executes; `runtime/__init__.py:10-14` invariant intact.

- [ ] **T078** `[P]` Build the catalogue bridge: `sources/estorides/` (146 definitions, 20 categories) → Context Planner → Runtime Dispatcher, via existing `GET /api/v1/connectors` and `/api/v1/tools`. FR-068, FR-069
- [ ] **T079** `[P]` Declarative capability model over the catalogue, replacing the source ТЗ's demand that capabilities come from runtime method returns. FR-068
- [ ] **T080** `[S]` Routing stays `runtime_ref`-first; capabilities remain compatibility check only. Do NOT amend `runtime/__init__.py`. FR-067
- [ ] **T081** `[P]` Reuse all five live-proven runtimes unchanged: SearXNG, Airbyte, BBOT, Maigret, SpiderFoot. No replacement. FR-070
- [ ] **T082** `[S]` Verify acquisition emits captures and records only — no entity, claim, or membership. FR-071
- [ ] **T083** `[P]` Preserve the primary-processing contract (`runtime/primproc.py`): raw artifact always emitted unchanged alongside any derived cleaned artifact; derived provenance recorded; derived artifact carries no clock of its own. FR-072
- [ ] **T084** `[P]` At-least-once acquisition with idempotent identity derivation retained. FR-073
- [ ] **T085** `[S]` Prove an obligation routes to a concrete runtime, executes, and produces observations. FR-036, FR-061

## Phase 7 — Interpretation / Resolution / Admission

**Entry**: Phases 2, 6. **Exit**: observation reaches an admitted claim with full provenance; every rejection replayable.

- [ ] **T086** `[P]` Wire interpretation onto the canonical path, preserving the consumer boundary that writes no entity, no claim, no graph edge. FR-010
- [ ] **T087** `[P]` Resolution and admission wired; admission owns claim creation, acquisition never does. FR-071
- [ ] **T088** `[P]` Version parser and record policy on every derived artifact. FR-081
- [ ] **T089** `[P]` Maintain the artifact dependency graph; an input change traces to every affected output. FR-082
- [ ] **T090** `[P]` Verify existing evidence and derivation lineage behaviour unchanged. FR-084
- [ ] **T091** `[P]` Parser failure and policy uncertainty route to DLQ/quarantine; rejections replayable, never auto-deleted. FR-016
- [ ] **T092** `[S]` Prove observation → admitted claim with complete provenance, answerable back to raw evidence, parser version, rules version, decisions. FR-083, SC-008

## Phase 8 — Entity Stream

**Entry**: Phase 7. **Exit**: entity stream rebuildable deterministically from the event log.

- [ ] **T093** `[P]` Canonical entity stream and life-event materialization. FR-074, FR-075
- [ ] **T094** `[P]` Honor `graph_invariant.py` guarantees: purity (no IO, no projection imports), determinism (`integrity_digest` order-independent), tz-aware, dedup, rejection of empty and mixed-identity input. FR-075
- [ ] **T095** `[P]` Keep entity novelty, evidence novelty, and structural novelty distinct; no single score. FR-078
- [ ] **T096** `[S]` Prove deterministic rebuild from the event log alone. FR-075, SC-010

## Phase 9 — Worldline

**Entry**: Phase 8. **Exit**: durable replayable snapshot answering "what did we believe at N, and why".

- [ ] **T097** `[P]` Worldline materializer consuming only the entity stream — no private path. FR-074
- [ ] **T098** `[P]` Durable snapshots with method and dependency fingerprints. FR-076
- [ ] **T099** `[P]` Every worldline state records the events that produced it. FR-077
- [ ] **T100** `[S]` Prove a snapshot at revision N answers what was believed at N and why, replayable from immutable inputs. FR-028, FR-077

## Phase 10 — PG Authoritative Graph (D2=c)

**Entry**: Phases 3, 8. **Exit**: exactly one authoritative graph; ADR merged.

- [ ] **T101** `[P]` Design the Context Graph vocabulary against **verified** entities — `relation_claim`, `relation_candidate`, `evidence_context`, `investigations`. Wave 0: the source ТЗ's 10 node and 10 edge types do not exist; real dictionaries are `TYPED_RELATIONS` and `HopKind`. FR-061
- [ ] **T102** `[P]` PostgreSQL tables for Context Graph and operational/research graph state, as authoritative. FR-061
- [ ] **T103** `[P]` Dedicated ADR recording `PG = authority`, `Neo4j = rebuildable serving projection`. FR-064
- [ ] **T104** `[P]` Resolve the pre-existing duplication: 57 PG tables including a full relational graph, plus a second graph in Neo4j. Collapse to one authority + one projection. FR-066
- [ ] **T105** `[P]` Verify no third graph store or graph copy is introduced. FR-063
- [ ] **T106** `[S]` Prove exactly one authoritative graph exists. SC-009

## Phase 11 — Neo4j Projection

**Entry**: Phase 10. **Exit**: Neo4j rebuildable from PG alone; divergence detectable; authoritative reads never from Neo4j.

- [ ] **T107** `[P]` Neo4j as serving projection behind existing `GraphProjection`/`GraphReader`/`GraphSnapshot`/`GraphTraversal`. FR-062
- [ ] **T108** `[P]` Observable divergence metric between PG authority and Neo4j projection. FR-065
- [ ] **T109** `[P]` No vendor-specific classes in domain logic (Principle V). FR-062
- [ ] **T110** `[S]` Prove full Neo4j rebuild from PG alone. FR-062, SC-009

## Phase 12 — Science Substrate

**Entry**: Phases 9, 11. **Exit**: evaluation reproducible by replay against its snapshot; never reads post-snapshot state.

- [ ] **T111** `[P]` Durable science state replacing the in-memory `science.*`-only store (`science/store.py`). Wave 0: `rg worldline apps/science/**` returns zero hits — this is the §7.7 violation. FR-085
- [ ] **T112** `[P]` Anchor every evaluation to a worldline snapshot identity; never silently read newer state. FR-086
- [ ] **T113** `[P]` Causal identification → estimation → refutation, each with a recorded outcome, not one opaque verdict. FR-087
- [ ] **T114** `[P]` TDA over real worldline windows. FR-088
- [ ] **T115** `[P]` Change-point detection against real data. FR-089
- [ ] **T116** `[P]` Calibration `abs(drift) <= tolerance` against real data. FR-089
- [ ] **T117** `[P]` Durable method and dependency fingerprints making results replayable. FR-090
- [ ] **T118** `[P]` Statistical, causal, epistemic layers separable. FR-091
- [ ] **T119** `[P]` TDA explicitly not a truth oracle (Constitution invariant 6). FR-092
- [ ] **T120** `[S]` Prove evaluation reproducible by replay against its bound snapshot. SC-012
- [ ] **T121** `[S]` Prove an evaluation does not read worldline state past its snapshot. FR-086

## Phase 13 — Science → Context Feedback

**Entry**: Phases 4, 12. **Exit**: the loop closes and runs continuously, demonstrable headless.

- [ ] **T122** `[P]` Science and worldline feed back into context: obligations, priorities, confidence, contradictions. FR-041
- [ ] **T123** `[P]` Loop runs whenever unresolved obligations exist; stops only on saturation, closure, or suspension. FR-051
- [ ] **T124** `[P]` Operator supervision preserved: the system proposes, the operator accepts/rejects/modifies/prioritizes. FR-045, input.md §11.4
- [ ] **T125** `[S]` Demonstrate the loop as continuous over substantial operation, not a single scripted pass. SC-005
- [ ] **T126** `[S]` Demonstrate the loop headless, proving the UI is not load-bearing for correctness. input.md §34.3, FR-099
- [ ] **T127** `[S]` Prove local-only operation with no external SaaS dependency for correctness. FR-099, SC-019
- [ ] **T128** `[S]` Prove one person can run a real multi-day investigation on one machine. input.md §35.10

---

## Phase 14 — Lineage Completion & Cross-Cutting NFR Verification

Cross-cutting verification. Each task is executed **at the phase named in its description**, but tracked here so FR coverage is complete and auditable. Research lineage is the one genuinely missing subsystem: Wave 0 found `evidence_lineage.py` implements evidence and derivation only, with zero occurrences of "research".

- [ ] **T161** `[P]` **At Phase 7** — Implement research lineage `Context → Obligation → Action → Task → Result → ContextRevision` as the third, distinct lineage dimension. Wave 0: the word "research" does not appear in `evidence_lineage.py`; no obligation or action hop exists in `HopKind`. FR-079, FR-080
- [ ] **T162** `[P]` **At Phase 7** — Verify all three lineages coexist and remain distinct; evidence and derivation behaviour byte-identical to pre-024. FR-079, FR-084
- [ ] **T163** `[P]` **At Phase 5** — Determinism verification: same inputs, rules version, and parameters produce identical outputs across repeated runs. FR-093
- [ ] **T164** `[P]` **At Phase 9** — Replay verification: every derived artifact reconstructible **without network re-acquisition**, reading raw bytes by reference with the same parser version and policy. FR-094
- [ ] **T165** `[P]` **At Phase 4** — Durability-before-observability: no state transition is observable before its transaction commits. FR-095
- [ ] **T166** `[P]` **At Phase 5** — Honesty verification: contradiction, incompleteness, contested claims, low confidence, and unknown are all representable and reachable as first-class states, with none collapsing to absence of data. FR-097
- [ ] **T167** `[P]` **At Phase 5** — Resource observability: memory, storage, and computation per investigation are measurable and enforceable against a budget. FR-098
- [ ] **T168** `[P]` **At Phase 13** — Explainability verification: every decision attributable to context, obligation, evidence, and rule, with the attribution queryable rather than merely logged. FR-096

---

## Parallel UI Track

Runs independent of the backend critical path. Spec: `ui-upgrade.md`.

### U0 — Baseline Repair

- [ ] **T129** `[P]` Restore the `canvas-{view}` test-id contract so Stages 3–4 surfaces do not break the Stage-2 test contract. All 9 failures share one cause; 6 are pure testid drift, 3 reference the removed `placeholder-*` contract. FR-110
- [ ] **T130** `[P]` Connect the completed-but-unmounted `src/ops/` (3 462 lines, 54 tests) to the workspace; decide its status against the 8-view list. FR-109
- [ ] **T131** `[P]` Connect `src/quality/` (hook + harness, 35 tests) and remove its dead state. FR-109
- [ ] **T132** `[P]` Wire `src/objects/` models — 2 327 lines including virtualization for 500+ rows, currently 0 components, 0 tests, 0 imports. FR-109
- [ ] **T133** `[P]` Mock the cytoscape 2d canvas to kill the unhandled rejection in `IntelligenceContainer.test.tsx`. FR-113

### U1 — Tokens, Density, Breakpoints

- [ ] **T134** `[P]` Apply all 15 palette tokens at spec values. Wave 0: 0 of 15 match today; accent is `#46c07a` where the spec requires phosphor `#8FCB64`. FR-102
- [ ] **T135** `[P]` Eliminate hardcoded hex in components; `color.css` forbids it and `IntelligencePage.tsx:748` violates it. FR-102
- [ ] **T136** `[P]` Write `data-density` and `data-theme` to the DOM. Wave 0: 0 occurrences in any `.ts`/`.tsx` — today the toggles change zero pixels and light theme is unreachable. FR-103
- [ ] **T137** `[P]` Three density modes `COMPACT`/`STANDARD`/`COMFORTABLE`, default `STANDARD`. Wave 0: `STANDARD` does not exist; only compact (default) and comfortable. FR-103
- [ ] **T138** `[P]` Density tokens applied to graph and timeline. Wave 0: `graph.css`, `timeline.css`, `evidence.css` reference zero density tokens. FR-103
- [ ] **T139** `[P]` Width breakpoints at 1024/1280/1440/1920/2560. Wave 0: 0 width-based media queries in app CSS; panes are fixed px. FR-104
- [ ] **T140** `[P]` Uncapped-content handling at 2560. FR-104

### U2 — State

- [ ] **T141** `[P]` `SelectionState` with all nine fields. Wave 0: `evidenceIds`, `graphMode`, `lineageMode`, `focusedPath` are all absent. FR-105
- [ ] **T142** `[P]` Move the four `useState`-resident fields into the store: `graphMode` (`GraphCanvas.tsx:93`), `focusedPath` (`:96`), `expandedIds`/`temporalActive`/`filterDrawerOpen` (`:94,102,103`), graph facets (`useGraphFacets`). They are lost on view switch today, which breaks the guarantee the store tests assert. FR-105
- [ ] **T143** `[P]` De-duplicate the shared `entity-projection` payload currently fetched under four keys (`graph`/`evidence`/`timeline`/`objects`); divergent invalidation today. FR-106
- [ ] **T144** `[P]` Consolidate the three Investigation query keys into one. FR-106
- [ ] **T145** `[P]` Add `QueryClient` `defaultOptions` — no `staleTime` in production today. FR-106
- [ ] **T146** `[S]` URL encodes investigation, object selection, view, time range, filters, graph mode; full working state restores on reload. FR-107

### U3 — Views

- [ ] **T147** `[P]` Objects view: table, filters, multi-select, record detail with lineage, virtualization connected. FR-108, FR-109
- [ ] **T148** `[P]` Acquisition view: `src/acquisition/` does not exist — build from the runtime model and catalogue bridge. FR-108
- [ ] **T149** `[P]` Findings/Claims view: queue, why-detected, lineage walk. FR-108
- [ ] **T150** `[P]` Analysis view: derived measures, communities, diagram features. FR-108
- [ ] **T151** `[P]` Remove the `StagePlaceholder` mechanism entirely; no view may ship a placeholder. FR-108
- [ ] **T152** `[P]` Specific honest empty states naming the missing dependency; zero fabricated numbers in a production build. FR-116

### U4 — Vertical Slice, Accessibility, Performance

- [ ] **T153** `[P]` Critical vertical slice: investigation → graph → entity → inspector → evidence → timeline → lineage/pivot/acquisition → new observations → graph, with zero full page reloads and selection preserved throughout. FR-111
- [ ] **T154** `[P]` Streaming/invalidation updates the graph incrementally, never full refetch-and-replace. FR-111
- [ ] **T155** `[P]` WCAG AA, full keyboard operability, focus restoration on overlay close. Wave 0: aria coverage ~55–60%; `Tabs` declares `aria-controls` pointing at tabpanels absent from the DOM. FR-113
- [ ] **T156** `[P]` Route-level code splitting, virtualization above 500 rows, non-blocking graph layout. Wave 0: 0 of 4 techniques applied; `objects/virtualization.ts` written and imported by nothing. FR-114
- [ ] **T157** `[S]` `npm run build` green, `npm run lint` zero errors, `npm test` zero failures. SC-013
- [ ] **T158** `[S]` Visual regression at 1440×900, 1920×1080, 2560×1440. FR-104, SC-018
- [ ] **T159** `[S]` Every view renders against a fixture server with no backend running. FR-115
- [ ] **T160** `[S]` Audit for forbidden visual patterns: neon, purple/magenta, glassmorphism, Web3 chrome, emoji iconography, rainbow series palettes, decorative HUD. FR-112

---

## Coverage

| Phase | Tasks | FRs |
|---|---|---|
| 0 Test/Infra Baseline | T001–T007 (7) | FR-001, FR-002 |
| 1 Redpanda Transport | T008–T016 (9) | FR-003…FR-009 |
| 2 Canonical Event Loop | T017–T027 (11) | FR-010…FR-017, FR-083, FR-096, FR-100 |
| 3 Investigation + Temporal | T028–T033 (6) | FR-018…FR-022 |
| 4 Context Engine | T034–T057 (24) | FR-023…FR-032, FR-041…FR-051, FR-096 |
| 5 Obligation / Frontier | T058–T077 (20) | FR-033…FR-040, FR-052…FR-060 |
| 6 Multi-Source Acquisition | T078–T085 (8) | FR-067…FR-073 |
| 7 Interpretation / Admission | T086–T092 (7) | FR-010, FR-016, FR-071, FR-081…FR-084 |
| 8 Entity Stream | T093–T096 (4) | FR-074, FR-075, FR-078 |
| 9 Worldline | T097–T100 (4) | FR-076, FR-077, FR-083 |
| 10 PG Authoritative Graph | T101–T106 (6) | FR-061, FR-063, FR-064, FR-066 |
| 11 Neo4j Projection | T107–T110 (4) | FR-062, FR-063, FR-065 |
| 12 Science Substrate | T111–T121 (11) | FR-085…FR-092 |
| 13 Science → Context | T122–T128 (7) | FR-041, FR-045, FR-051, FR-099 |
| 14 Lineage + NFR Verification | T161–T168 (8) | FR-079, FR-080, FR-093…FR-098 |
| UI U0–U4 | T129–T160 (32) | FR-101…FR-116 |

**Total: 168 tasks. All 116 FR covered.**

**Critical path**: T001–T007 → T008–T016 → T017–T027 → T028–T033 → T034–T057 → T058–T077 → T078–T085 → T086–T092 → T093–T096 → T097–T100 → T101–T106 → T107–T110 → T111–T121 → T122–T128.

## Success Criteria mapping

| SC | Verified by |
|---|---|
| SC-001, SC-002 | T001–T007, T015 |
| SC-003 | T008 |
| SC-004 | T025 |
| SC-005 | T125 |
| SC-006 | T077 |
| SC-007 | T076 |
| SC-008 | T092 |
| SC-009 | T106, T110 |
| SC-010 | T038, T096 |
| SC-011 | T051, T052 |
| SC-012 | T120 |
| SC-013 | T157 |
| SC-014 | T153 |
| SC-015 | T151 |
| SC-016 | T134, T135 |
| SC-017 | T136, T137, T138 |
| SC-018 | T158 |
| SC-019 | T127 |
| SC-020 | T006, T007 |
