# Implementation Plan: Context-Driven Continuous Intelligence Fabric

**Feature**: 024-context-driven-continuous-intelligence
**Spec**: `spec.md` (116 FR, 20 SC)
**Baseline**: `wave0-verified-state.md` — 33 claims audited, 15 false
**Decisions**: D1=a, D2=c, D3=b, D4=a, D5=b (owner-fixed)
**Date**: 2026-10-02

## Summary

Build a context-driven continuous intelligence fabric on top of real, live-proven primitives. The canonical event path is **greenfield composition**, not a refactor: Layer 0 is dead code already slated for deletion by spec 021 FR-172, and reviving it would convert a dormant Principle VI violation and a dormant SSRF vector into live ones.

Primary technical approach: compose the new event path around existing primitives (4 acquisition runtimes, 146-source catalogue, protobuf `EventEnvelope` with 116 types across 43 topics, `ObservationGate`, the Common Crawl chain, projection fabric, and the deterministic identity module). Build the Context Engine as five separated components beside the existing control-plane investigation domain. Persist context in PostgreSQL as authoritative; keep Neo4j as a rebuildable serving projection.

## Technical Context

**Language/runtime**: Python 3.12 (apps), TypeScript/React 18 (webapp), Rust (high-throughput)
**Infrastructure**: Redpanda (pinned by digest, D1=a), PostgreSQL 16, MinIO, Neo4j 5 (serving only), Temporal 1.25.2, OpenSearch, ClickHouse
**Serialization**: Protocol Buffers, 16-field `EventEnvelope`, 16 fields unchanged per D5=b
**Event surface**: 116 event types → 43 topics, DLQ at `events.dlq` / `events.quarantine`
**Target**: single-machine local operation, no external SaaS dependency for correctness

## Constitution Check

| Principle | Gate | Evidence plan |
|---|---|---|
| I Observation-Immutable Evidence Substrate | MUST PASS | Raw bytes content-addressed at `s3://knowledge/raw/{prefix}/{sha256}`; `artifact_sink.py` remains sole raw writer; `ObservationGate` untouched. FR-071, FR-072. |
| II Evidence-First | MUST PASS | Full chain preserved; `evidence_lineage` untouched; research lineage added as a third, distinct dimension (FR-079, FR-080). |
| III Projection-First | MUST PASS | No store gains authority over evidence; Neo4j demoted to rebuildable projection with observable divergence (FR-061…FR-066). |
| IV No Single Store / Graph / Score | MUST PASS | Resolves the existing PG/Neo4j duplication to exactly one authority + one projection; novelty signals kept distinct (FR-078). |
| V Plugability by Contract | MUST PASS | Routing stays `runtime_ref`-first, capabilities as check only — `runtime/__init__.py:10-14` invariant preserved (FR-067, FR-069). |
| VI Process-Centric | MUST PASS | Investigation stays the unit; no `apps/investigation` pseudo-app; lifecycle becomes genuinely executable in Temporal (FR-018…FR-022). |
| VII Security-First | MUST PASS | Layer 0's `follow_redirects=True` fetch pattern is NOT revived; SSRF/DNS-rebinding/egress policy enforced at the new transport boundary (FR-100, FR-013). |

**"No MVP/mini-architecture" constraint**: satisfied by fixing all final domain and event contracts up front (FR-011, FR-023…FR-042) while introducing them incrementally. Breaking a final contract later is forbidden.

**Complexity tracking**: the feature introduces a bounded set of justified deviations from the source ТЗ, each owner-decided: transport (D1), graph authority (D2), investigation boundary (D3), routing (D4), timestamps (D5). No unexplained deviation remains.

## Project Structure

```
specs/024-context-driven-continuous-intelligence/
  input.md                    # source convergence ТЗ (verbatim-fidelity digest)
  ui-upgrade.md               # UI 2.0 ТЗ
  wave0-verified-state.md     # verified baseline, 33-claim verdict table
  spec.md  plan.md  tasks.md  research.md  data-model.md  contracts.md
  quickstart.md               # operator path
  test-baseline.md            # FR-001 artifact

apps/shared/
  events/          # EventEnvelope unchanged; + payload timestamp convention (D5=b)
  domain/          # + investigation_context.py, obligation.py, frontier.py
  contracts/       # currently 0-line stub — filled with typed payload contracts
  storage/s3.py    # unchanged
apps/deploy/docker-compose.yml   # Redpanda pinned by digest, canonical profile
apps/control-plane/
  cp_domain/       # investigation.py extended
  workflows/       # worker.py registers InvestigationWorkflow (D3=b)
  context_engine/  # NEW, beside cp_domain — not a new app
  db/              # + context graph tables (authoritative, D2=c)
apps/science/      # store.py made durable + worldline-anchored
apps/webapp/src/   # 8 views completed, tokens, density, breakpoints
```

## Wave Architecture

The owner supplied the critical path. Waves are strictly ordered by the dependency DAG; independent items within a wave parallelize.

```
W0  TEST/INFRA BASELINE ─────────────────────────────────┐
W1  REDPANDA CANONICAL TRANSPORT ───────────────────────┤
W2  CANONICAL EVENT LOOP ───────────────────────────────┤
W3  INVESTIGATION + TEMPORAL REGISTRATION ──────────────┤
W4  CONTEXT ENGINE ─────────────────────────────────────┤
W5  OBLIGATION / FRONTIER ──────────────────────────────┤
W6  MULTI-SOURCE ACQUISITION ───────────────────────────┤
W7  INTERPRETATION / RESOLUTION / ADMISSION ────────────┤
W8  ENTITY STREAM ──────────────────────────────────────┤
W9  WORLDLINE ──────────────────────────────────────────┤
W10 PG AUTHORITATIVE GRAPH ─────────────────────────────┤
W11 NEO4J PROJECTION ───────────────────────────────────┤
W12 SCIENCE SUBSTRATE ──────────────────────────────────┤
W13 SCIENCE → CONTEXT FEEDBACK ─────────────────────────┤
                                                       ↺ loop closes
```

Each wave declares its entry gate, deliverables, FR coverage, exit criteria, and parallelism.

### W0 — Test/Infra Baseline

**Entry**: none (first wave)
**Deliverables**: `test-baseline.md` classifying all 121 failures and 24 collection errors by root cause; the three transport-critical modules collecting; a delta-check harness; honest CI reporting with no suppression.
**FR**: FR-001, FR-002
**Exit**: baseline published; unrelated change yields zero delta; no failure dismissed as flaky.
**Parallel**: module-diagnosis clusters run independently (24 collection errors, 5 top failure clusters, 4 layer0 tests).

### W1 — Redpanda Canonical Transport

**Entry**: W0 complete (FR-002 must run before transport changes are validated)
**Deliverables**: Redpanda image pinned by digest; Redpanda promoted to the canonical dev/live profile; `KafkaSettings` default repointed to the Redpanda profile; Constitution Technology Baseline and the 24 Kafka-assuming ADRs amended; timestamp convention documented per D5=b; `apps/shared/contracts/` filled with typed payload contracts carrying `observed_at`/`logical_time`.
**FR**: FR-003…FR-009
**Exit**: `redpandadata/redpanda:latest` has zero occurrences; broker reachable; emission tests pass.
**Parallel**: digest pinning ‖ ADR amendment ‖ contracts package ‖ timestamp convention doc.
**Note**: `apps/deploy/docker-compose.yml` currently pins MinIO, Kafka 7.7.0, Postgres, Redis, OpenSearch, ClickHouse, Neo4j, Temporal, Flink, SearXNG by tag — but `redpanda:latest`, `mc:latest`, `console:latest`, `nessie:latest`, `browsertrix-crawler:latest` are unpinned. D1 requires the transport pinned; others are recorded, not blocked on.

### W2 — Canonical Event Loop

**Entry**: W1 complete
**Deliverables**: new composition root wiring the canonical path around existing primitives; every cross-layer hop through the event bus; idempotent consumers keyed on event identity; DLQ/quarantine routing; backpressure that reduces acquisition rate rather than growing backlog; Common Crawl chain wired onto the path; Security-First fetch boundary (no Layer 0 pattern).
**FR**: FR-010…FR-017, FR-096, FR-100
**Exit**: one real observation completes the loop end-to-end producing durable downstream state (SC-004); duplicate delivery yields exactly one durable result; `rpk cluster info` healthy.
**Parallel**: composition root ‖ Common Crawl wiring ‖ DLQ/consumer idempotency ‖ security boundary.

### W3 — Investigation + Temporal Registration

**Entry**: W2 complete
**Deliverables**: `InvestigationWorkflow` and `RecrawlWorkflow` registered on task queue `cognitive-investigations`; lifecycle executed end-to-end rather than merely defined; investigation domain extended in `cp_domain/investigation.py`; no `apps/investigation` created.
**FR**: FR-018…FR-022, FR-021
**Exit**: a Temporal-driven investigation traverses its 10-state lifecycle with durable history.
**Wave 0 finding**: `workflows/worker.py:20-25` registers only `TemporalEntityMaterializationWorkflow` on its own queue. `workflows/investigation.py` defines `InvestigationWorkflow` (`@workflow.defn`, line 190) and `RecrawlWorkflow` (line 278) on `TASK_QUEUE = "cognitive-investigations"` (line 39) — **a queue with no worker registered on it.** Today these are dead code in Temporal terms, exactly like Layer 0. Wave 0 scored `InvestigationWorkflow` as "imported only by a test"; it is stronger than that — it is also unserved by any worker.

### W4 — Context Engine

**Entry**: W3 complete
**Deliverables**: `InvestigationContext` (`CXI-` identity, revision separate, append-only snapshots, durable, replay-reconstructible, provenance per revision, unknown-vs-empty distinction, explicit scope linkage); five separated components — obligation generator, satisfaction evaluator, action proposer, decision recorder, revision manager; incremental deterministic updates; explainability per update; adaptive layer optional and disable-able; deterministic replay mode vs adaptive mode recorded per decision; explicit missing/late/out-of-order policy; transport/UI/storage-independent core.
**FR**: FR-023…FR-032, FR-041…FR-051
**Exit**: context survives restart; replay reconstructs it; engine runs with adaptive layer disabled; `EvidenceContext` fields verifiably unchanged (FR-032) so every stored `context_id` still validates.
**Wave 0 finding**: overloading `EvidenceContext` is not merely bad style — adding any field invalidates every stored `context_id`, the `uq_evidence_context_fingerprint` index, every `context_ref`, and every frame-carrying event payload, making persisted frames unreadable. Template: `SemanticRegime`, a separate content-addressed object with a one-way `context_ref`.
**Parallel**: identity/revision model ‖ five components ‖ replay engine ‖ adaptive-layer isolation.

### W5 — Obligation / Frontier

**Entry**: W4 complete
**Deliverables**: `ResearchObligation` with the full attribute set; versioned inspectable generation rules; append-only lifecycle history; satisfaction as a pure versioned function; contradiction handling that never overwrites a claim; durable frontier; action memory; autonomous hypothesis/question proposal; saturation, coverage, marginal gain, budget, source exhaustion; honest termination and re-opening.
**FR**: FR-033…FR-040, FR-052…FR-060
**Exit**: system reports open/satisfied/contradicted obligations with reasons; an investigation closes with a formal termination report and re-opens on contradiction.
**Parallel**: obligation store ‖ satisfaction evaluator ‖ saturation model ‖ frontier ‖ autonomous proposal.

### W6 — Multi-Source Acquisition

**Entry**: W5 complete (needs obligations to route); W2 complete
**Deliverables**: catalogue-as-planner→dispatcher bridge; declarative capabilities from the 146 source definitions; `runtime_ref`-first routing with capabilities as compatibility check only; runtime contract unchanged; existing five runtimes reused; acquisition emits captures/records only; primary-processing contract preserved (raw always emitted unchanged beside any derived artifact).
**FR**: FR-067…FR-073
**Exit**: an obligation routes to a concrete runtime and executes; `runtime/__init__.py:10-14` invariant intact.
**Wave 0 finding**: `capabilities()` returns are hardcoded per class; the real capability-as-data layer is `sources/estorides/` (146 definitions, 20 categories) already exposed via `GET /api/v1/connectors` and `/api/v1/tools`. D4=a closes §4.7 through that catalogue, not by amending the runtime contract.

### W7 — Interpretation / Resolution / Admission

**Entry**: W2, W6 complete
**Deliverables**: interpretation, resolution, admission wired onto the canonical path; parser versioned and policy-recorded on every derived artifact; admission producing claims without acquisition ever creating one; DLQ routing for parser failure and policy uncertainty.
**FR**: FR-081…FR-084, FR-016
**Exit**: observation reaches an admitted claim with full provenance; every rejection replayable, none auto-deleted.

### W8 — Entity Stream

**Entry**: W7 complete
**Deliverables**: canonical entity stream and life-event materialization honoring `graph_invariant` guarantees — purity, determinism (`integrity_digest` order-independent), tz-aware, dedup, rejection of empty and mixed-identity input; novelty signals kept distinct.
**FR**: FR-074, FR-075, FR-078
**Exit**: entity stream rebuildable deterministically from the event log.

### W9 — Worldline

**Entry**: W8 complete
**Deliverables**: worldline materializer consuming only the entity stream; durable snapshots with method and dependency fingerprints; every worldline state records its producing events.
**FR**: FR-076, FR-077, FR-083
**Exit**: worldline snapshot durable and replayable; a snapshot at revision N answers "what did we believe at N, and why".

### W10 — PG Authoritative Graph

**Entry**: W3, W8 complete
**Deliverables**: Context Graph and operational/research graph state in PostgreSQL as authoritative (D2=c); resolution of the existing PG/Neo4j duplication to one authority + one projection; dedicated ADR recording the split; Graph Graph node/edge vocabulary replacing the source ТЗ's list, mapped onto real entities (`relation_claim`, `relation_candidate`, `evidence_context`, `investigations`).
**FR**: FR-061, FR-063, FR-064, FR-066
**Exit**: exactly one authoritative graph exists; ADR merged.
**Wave 0 finding**: the source ТЗ's 10 node types and 10 edge types do not exist. Real dictionaries are `TYPED_RELATIONS = {hasEvidence, depicts, inConversation}` and `HopKind`; `supersedes`/`contradicts` are fields on `RelationClaim`, not edge types. This wave designs the Context Graph vocabulary against verified entities, not against the ТЗ's list.

### W11 — Neo4j Projection

**Entry**: W10 complete
**Deliverables**: Neo4j as rebuildable serving projection behind existing `GraphProjection`/`GraphReader`/`GraphSnapshot`/`GraphTraversal`; observable divergence metric; no vendor-specific classes in domain logic; no third graph copy.
**FR**: FR-062, FR-065, FR-063
**Exit**: Neo4j rebuildable from PG alone; divergence detectable; authoritative reads never served from Neo4j.

### W12 — Science Substrate

**Entry**: W9, W11 complete
**Deliverables**: durable science state replacing the in-memory `science.*`-only store; worldline-anchored evaluations bound to snapshot identity; causal identification → estimation → refutation with recorded per-stage outcomes; TDA over real worldline windows; change-point; calibration `abs(drift) <= tolerance`; method/dependency fingerprints; statistical/causal/epistemic separation; TDA explicitly not a truth oracle.
**FR**: FR-085…FR-092
**Exit**: evaluation reproducible by replay against its snapshot; never reads post-snapshot state.
**Wave 0 finding**: `rg worldline apps/science/**` returns **zero hits** — Science is currently exactly the private toy state the ТЗ forbids. `store.py:1-12` self-describes as an in-memory `science.*`-only replay projection. The real layer is 14 domain subpackages over non-durable state; the ТЗ's builders/pipelines/`SKILL.md`/`tool_spec` layer is absent and is **not** being built here — those claims were false, and the ТЗ's normative requirement (§7.7 anchoring) is satisfied by anchoring the real layer instead.

### W13 — Science → Context Feedback

**Entry**: W4, W12 complete
**Deliverables**: science and worldline feed back into context — obligations, priorities, confidence, contradictions; continuous loop runs whenever unresolved obligations exist and stops only on saturation, closure, or suspension.
**FR**: FR-051…FR-060 (closure), FR-096
**Exit**: the loop closes and is demonstrable as continuous rather than a single scripted pass; headless demonstration works (input.md §34.3).

### Parallel UI Track

UI runs alongside from W0, independent of the backend critical path, tracked under `ui-upgrade.md`.

**U0** Baseline repair: restore the `canvas-{view}` test-id contract (9 failures, one cause); connect completed-but-unmounted `ops/`, `quality/`, `objects/` (2 327 lines, 0 tests); mock cytoscape canvas to kill the unhandled rejection.
**U1** Tokens: all 15 palette tokens to spec values, `COMPACT/STANDARD/COMFORTABLE` default `STANDARD`, `data-density`/`data-theme` written to DOM, width breakpoints at 1024/1280/1440/1920/2560, zero hardcoded hex in components.
**U2** State: nine-field `SelectionState` in the store; kill the four `useState`-resident fields; de-duplicate the shared payload query keys; URL encodes all required state.
**U3** Views: complete Objects, Acquisition, Findings, Analysis; remove the placeholder mechanism entirely.
**U4** Vertical slice + a11y + perf: critical slice with zero reloads, WCAG AA, route splitting, virtualization above 500 rows, non-blocking layout.

**FR**: FR-101…FR-116
**Exit**: SC-013…SC-018 green.

## Dependency DAG and Critical Path

```
W0 ──► W1 ──► W2 ──► W3 ──► W4 ──► W5 ──► W6 ──┬──► W7 ──► W8 ──► W9 ──┬──► W10 ──► W11 ──► W12 ──► W13
                          │                    │                          │
                          └────────────────────┘                          └──────────┘
                                    └──► W10 (needs W3 + W8)
```

**Critical path**: W0 → W1 → W2 → W3 → W4 → W5 → W6 → W7 → W8 → W9 → W10 → W11 → W12 → W13. Fully serial; **no wave on it has an internal shortcut.**

**Parallelizable within waves** (listed per wave above). **Parallelizable across waves**: W6 needs W5 + W2, so W7 may begin schema/consumer work during W6's tail; W10 needs W3 + W8, so its ADR may be drafted during W7/W8; the entire UI track runs independent of all of it.

## Complexity Tracking

| Deviation from source ТЗ | Reason | Status |
|---|---|---|
| Redpanda runtime, Kafka-compatible protocol | D1=a owner-fixed | decided |
| PG authoritative, Neo4j serving | D2=c owner-fixed; resolves pre-existing duplication | decided |
| No `apps/investigation` | D3=b owner-fixed; domain already exists in control-plane | decided |
| `runtime_ref` routing, catalogue capabilities | D4=a owner-fixed; preserves Principle V and 023 O-2 | decided |
| No protobuf field 17; timestamps in payloads | D5=b owner-fixed | decided |
| Layer 0 not revived, built around | Principle VI + VII; 021 FR-172 already ordered its deletion | decided |
| Context Graph vocabulary derived from verified entities, not the ТЗ's list | Wave 0 proved the ТЗ's node/edge types absent | decided |
| Science ТЗ-claimed modules not built | Wave 0 proved them absent; §7.7's normative anchoring met by anchoring the real layer | decided |
| Research lineage as third dimension | Complement to existing evidence + derivation | decided |
| UI track runs parallel | Independent of backend critical path | decided |

**Remaining complexity**: none unexplained. Any new conceptual contradiction halts that item per `AGENTS.md` §1.1.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| 24 collection errors mask transport bugs | High | W0 first; the three transport-critical modules repaired before W1 |
| 25 `test_acquisition_worker.py` failures sit under the acquisition stage | High | W0 triage; regression delta isolated by baseline |
| Temporal queue `cognitive-investigations` has never been served | Medium | W3 registers it; W3 exit proves lifecycle execution, not just definition |
| Science layer non-durable | Medium | W12 replaces in-memory store; W12 binds evaluations to snapshot identity |
| Two graphs already exist in production shape | Medium | W10 collapses to one authority + one projection with ADR |
| Context scope creep across investigations | Medium | FR-031 explicit linkage; silent absorption forbidden |
| Saturation misjudged as sufficiency | High | FR-053 forbids acquisition-count closure; coverage + saturation required |
| UI palette reverts to non-spec values | Medium | U1 token parity test; SC-016 measurable |
| Density/theme toggles remain inert | Medium | U1 writes attributes to DOM; SC-017 verifies pixel change |
| ACQ replay/failure-journal debt from 023 carried in | Low | Already proven live 29/29; journal work is a scoped addition, not a blocker |

## Generated Artifacts

| Artifact | Purpose |
|---|---|
| `data-model.md` | `CXI`/revision, obligation, frontier, saturation, snapshot entities; PG authoritative tables |
| `contracts.md` | Typed payload contracts with `observed_at`/`logical_time` convention (D5=b); new event types |
| `research.md` | Wave 0 method, verdict rationale, donor/platform-code reuse map |
| `test-baseline.md` | FR-001 artifact: 121 failures + 24 collection errors classified by root cause |
| `quickstart.md` | Operator path to a closed loop on one machine |
