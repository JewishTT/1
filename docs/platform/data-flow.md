# Data flow

The canonical pipeline, mapped to the modules that implement each stage. This is the
shape the specs describe; the gaps page records where the shape is not yet executable.

## Context & obligation creation

| Module | Docstring |
|---|---|
| `apps/admission/resolution/decision_store.py` | ``ResolutionDecision`` — append-only, supersession-based, with a surviving trail (T082, T083). |
| `apps/control-plane/api/routes/investigation_context.py` | The door: investigation context over HTTP. |
| `apps/control-plane/context_engine/__init__.py` | Context Engine: durable research context as a first-class object (Feature 024 Phase 4/5). |
| `apps/control-plane/context_engine/catalogue_bridge.py` | Catalogue bridge: Context Planner to Runtime Dispatcher (Feature 024 D4=a, Phase 6). |
| `apps/control-plane/context_engine/context_graph.py` | The Context Graph — first-class, durable, and the thing the user actually works in. |
| `apps/control-plane/context_engine/context_graph_store.py` | The Context Graph on PostgreSQL — durable, transactional, replayable (§3.6). |
| `apps/control-plane/context_engine/dossier_store.py` | Making a sweep survive the process, and survive being asked about again afterwards. |
| `apps/control-plane/context_engine/engine.py` | The five Context Engine components (FR-041) and the engine that composes them. |
| `apps/control-plane/context_engine/enrichment_service.py` | The vertical slice the platform was missing: subject -> sources -> invariant -> dossier. |
| `apps/control-plane/context_engine/fabric_bridge.py` | Control-plane bridge: fabric findings into the engine's own signal vocabulary. |
| `apps/control-plane/context_engine/fabric_runner.py` | The runner: one fabric pass, persisted, translated into engine signals. |
| `apps/control-plane/context_engine/fabric_store.py` | Durable persistence for the context fabric. |
| `apps/control-plane/context_engine/invariant_reducer.py` | Incremental growth of a ``GraphInvariant`` — one revision per real change. |
| `apps/control-plane/context_engine/loop.py` | The cognitive loop: context drives work, results feed back into context (Feature 024 Phase 13). |
| `apps/control-plane/context_engine/obligations.py` | Research obligations, actions, saturation, and the frontier (Feature 024 Phase 4/5). |
| `apps/control-plane/context_engine/person_case_profile.py` | Person case profile pack (Feature 034). |
| `apps/control-plane/context_engine/postgres_store.py` | PostgreSQL-backed :class:`~context_engine.store.ContextStore`. |
| `apps/control-plane/context_engine/query_cycle.py` | The AST cycle in one place: context in, search requests out, results back in. |
| `apps/control-plane/context_engine/return_path.py` | The return path: acquired observations back into the context (the reverse direction). |
| `apps/control-plane/context_engine/science_bridge.py` | The seam: consume ``science.*`` results and feed them back into a context. |
| `apps/control-plane/context_engine/store.py` | Context store: the contract, and a hermetic reference implementation (T037). |
| `apps/control-plane/context_engine/worldline.py` | Control-plane side of the worldline anchor: load revisions, build the view. |
| `apps/control-plane/db/correlation_store.py` | Durable persistence for possible_match correlation edges (FR-004, I-2). |
| `apps/control-plane/db/investigation_store.py` | Durable persistence for investigations. |
| `apps/control-plane/db/relation_claim_store.py` | Durable SQL persistence for relation claims and their revision chain (016, US2, T030). |

## Policy-first capability planning

| Module | Docstring |
|---|---|
| `apps/acquisition/dispatcher/scheduler.py` | Collection Fabric dispatcher — two-stage scheduler (Feature 034 production). |
| `apps/acquisition/tests/contract/test_scheduler.py` | Dispatcher scheduler contract tests (T110/T132/T133, US1, Constitution gates). |
| `apps/control-plane/context_engine/catalogue_bridge.py` | Catalogue bridge: Context Planner to Runtime Dispatcher (Feature 024 D4=a, Phase 6). |
| `apps/control-plane/services/discovery_frontier.py` | Production bindings between Layer A discovery and the durable frontier (008). |
| `apps/control-plane/services/frontier.py` | Frontier operational state (T026, FR-003, R-4). |
| `apps/control-plane/services/investigation_scheduler.py` | Starting investigations on Temporal, and scheduling their recrawls. |
| `apps/control-plane/services/tool_catalog.py` | Maltego-style entity→tool catalog for the SpecOps frontend (hermetic). |
| `apps/control-plane/tests/integration/test_frontier_provenance.py` | FR-007 survives the bridge from Layer A discovery to the durable frontier. |
| `apps/control-plane/tests/unit/test_tool_catalog.py` | Tool catalog (SpecOps entity→tool): determinism, coverage, type inference. |
| `apps/feedback/feedback/frontier.py` | Feedback loop closing: frontier sinks + shared forms (T116-T118). |
| `apps/feedback/tests/test_frontier_loop.py` | Integration: feedback loop closes into the authoritative Postgres frontier. |

## Acquisition (raw-first)

| Module | Docstring |
|---|---|
| `apps/acquisition/artifact_sink.py` | The sink: ``AcquisitionArtifact`` -> ``Capture`` + ``Observation`` + event. |
| `apps/acquisition/cc_plan.py` | CC query planner (L1, CC-TEMPORALITY v1): entity identity -> CC index plan. |
| `apps/acquisition/dispatcher/__init__.py` | Collection Fabric dispatcher (T110, T132, T133, R-03, R-09). |
| `apps/acquisition/dispatcher/kafka_producer.py` | Kafka producer for the acquisition stream plane. |
| `apps/acquisition/dispatcher/plan_driver.py` | Drive the real Dispatcher with a `plan()` result (W1). |
| `apps/acquisition/dispatcher/regional.py` | Region-level backpressure (T113). |
| `apps/acquisition/dispatcher/scheduler.py` | Collection Fabric dispatcher — two-stage scheduler (Feature 034 production). |
| `apps/acquisition/entity_search.py` | Deterministic entity search planning surface. |
| `apps/acquisition/sources/__init__.py` | Package marker for the acquisition source catalogue. |
| `apps/acquisition/sources/append_parse_blocks.py` | Append a ``parse:`` block to catalogue definitions that lack one. |
| `apps/acquisition/sources/capabilities.py` | Capability offers derived from the live source catalogue (spec 026 FR-097, FR-098). |
| `apps/acquisition/sources/catalogue.py` | Source catalogue: declarative OSINT source definitions. |
| `apps/acquisition/sources/connector.py` | Turn a source definition into scheduled tasks and, when executed, into observations. |
| `apps/acquisition/sources/executor.py` | Execute a source definition and emit one observation per page. |
| `apps/acquisition/tests/unit/test_acquisition_artifact_sink.py` | The artifact seam and the sink: §5, §6, §9, §11, §12, §61, §69, §124. |
| `apps/acquisition/tests/unit/test_cc_plan.py` | CC query planner unit tests (CC-TEMPORALITY v1, task_0006). |
| `apps/acquisition/tests/unit/test_entity_search.py` | Deterministic entity search surface unit tests. |
| `apps/control-plane/services/dispatcher.py` | Dispatcher/scheduler loop (T029, FR-003/FR-027/FR-028, R-11). |
| `apps/control-plane/tests/unit/test_dispatcher_backpressure.py` | Feature 024 T021 -- backpressure must actually reduce the acquisition rate. |
| `apps/interpretation/tests/integration/test_all_sources_parse.py` | Every source in the catalogue parses, and every failure has a name (spec 025 §33). |
| `tools/append_zero_sources_a.py` | Append section 0.11 (sources from everywhere) — part A. |
| `tools/append_zero_sources_b.py` | Append section 0.11 part B (telegram + misc channels). |

## Observation gate & outbox

| Module | Docstring |
|---|---|
| `apps/acquisition/dispatcher/kafka_producer.py` | Kafka producer for the acquisition stream plane. |
| `apps/acquisition/observation_gate/__init__.py` | Observation Gate resilience: collector replay / resume journal (T120, T127b). |
| `apps/acquisition/observation_gate/replay.py` | Collector replay / resume journal (T120, T127b). |
| `apps/control-plane/api/routes/science_robustness.py` | Science robustness + experiments API (T132, US6; contracts/science-api.md). |
| `apps/control-plane/services/event_bus.py` | Control-plane facade over the shared deterministic EventBus (nervous-system). |
| `apps/science/robustness/__init__.py` |  |
| `apps/science/robustness/perturb.py` | Perturbation grid for robustness analysis (T128, US6, FR-011). |
| `apps/science/robustness/report.py` | Flip rates, sensitivity and noise regions (T129, US6, FR-011). |
| `apps/science/tests/contract/test_robustness_contract.py` | Contract tests: robustness + experiment registry (T126, US6). |
| `apps/shared/events/bus.py` | Hermetic EventBus protocol + MemoryEventBus (feature: nervous-system). |
| `apps/shared/events/evidence_store_guard.py` | Evidence-storage enforcement for observation publication. |
| `apps/shared/events/kafka.py` | Idempotent Kafka producer/consumer base (T010, R-7, I-11). |
| `apps/shared/events/observation_gate.py` | Observation gate (T031, FR-002, I-1/I-5). |
| `apps/shared/tests/unit/test_evidence_store_guard.py` | WP-C T040/T045: an observation may not be published without resolvable evidence. |
| `apps/shared/tests/unit/test_observation_gate_identity.py` | The gate itself: §160's ``observation_id random`` blocker, pinned behaviourally. |
| `apps/zero/zero/observation_gate.py` | Zero-layer observation gate (spec/010 FR-009, FR-012) — immutable output. |

## Parsing & extraction

| Module | Docstring |
|---|---|
| `apps/interpretation/aggregation/candidates.py` | Candidate aggregation (T034, FR-011). |
| `apps/interpretation/extractors/__init__.py` | Extractor package (spec 007): deterministic, no-ML entity extraction. |
| `apps/interpretation/extractors/contacts.py` | Deterministic contact/identifier extraction (spec 007, US1, R-5). |
| `apps/interpretation/extractors/dictionary_entities.py` | Dictionary-entity extraction: OpenSanctions-derived matcher (spec 007, T015/T018). |
| `apps/interpretation/extractors/lane.py` | Deterministic extraction lane (spec 007, T032, US1/US4). |
| `apps/interpretation/extractors/language.py` | Charset + language tiers (spec 007, T026/T027, US5, FR-7). |
| `apps/interpretation/extractors/matching.py` | Deterministic gazetteer matching primitives (spec 007, US2). |
| `apps/interpretation/extractors/normalize.py` | Normalization post-pass: canonical forms + identity evidence (spec 007, T020/T021, US3). |
| `apps/interpretation/extractors/orgs.py` | Deterministic organization extraction (spec 007, org extractor). |
| `apps/interpretation/extractors/payload/__init__.py` | The stage between parsed payload records and typed, related mentions. |
| `apps/interpretation/extractors/payload/hypotheses.py` | S1: a type hypothesis with a **cited basis**, and no free-floating number. |
| `apps/interpretation/extractors/payload/keytable.py` | The type-hypothesis table: **a declared, versioned, inspectable list, and no fuzzy fallback**. |
| `apps/interpretation/extractors/payload/structure.py` | S3–S5: relation signals from structure, resolved mentions, and truncation that propagates. |
| `apps/interpretation/extractors/persons.py` | Deterministic person extraction, invariant across ML (spec 007, T014/T016). |
| `apps/interpretation/extractors/places.py` | Deterministic place extraction via the GeoNames automaton (spec 007, T015/T017). |
| `apps/interpretation/extractors/registry.py` | Extractor registry (T033, FR-011). |
| `apps/interpretation/extractors/relations.py` | Relation-aware extraction: the cue is the reading (spec 018, T021-T023, FR-017..FR-019). |
| `apps/interpretation/extractors/signals/__init__.py` | Relation signals: what producers saw, before anyone decided what it means. |
| `apps/interpretation/extractors/signals/lexical.py` | The lexical producer: cue phrases in running text, as signals. |
| `apps/interpretation/extractors/signals/links.py` | The link producer: what a hyperlink says, and nothing it does not. |
| `apps/interpretation/extractors/signals/mentions.py` | The **only** place a producer below the mention layer addresses a participant. |
| `apps/interpretation/extractors/signals/metadata.py` | The metadata producer: what a document says about itself. |
| `apps/interpretation/extractors/signals/protocol.py` | The one extraction contract every relation producer implements. |
| `apps/interpretation/extractors/signals/signal.py` | The relation signal: what a producer saw, before anyone decided what it means. |
| `apps/interpretation/extractors/signals/syntactic.py` | The syntactic producer: a parsed clause, as a relation signal. |

## Identity resolution & admission

| Module | Docstring |
|---|---|
| `apps/admission/resolution/__init__.py` |  |
| `apps/admission/resolution/blocking.py` | Multi-strategy blocking (T082, FR-013) + Feature 034 person-case blocking policy. |
| `apps/admission/resolution/candidate.py` | Resolution candidates with human review and non-destructive merge (feature 005, US2). |
| `apps/admission/resolution/cluster.py` | Cluster membership is a decision, not a consequence of two agreements (T078, FR-084). |
| `apps/admission/resolution/collective.py` | Collective/graph-aware resolution (T083, FR-013). |
| `apps/admission/resolution/decision_store.py` | ``ResolutionDecision`` — append-only, supersession-based, with a surviving trail (T082, T083). |
| `apps/admission/resolution/gate.py` | The admission gate for identity: the only path from a proposal to a MERGE (T081, FR-081). |
| `apps/admission/resolution/resolver.py` | Pairwise resolver (T035, FR-013). |
| `apps/admission/resolution/span.py` | Evidence spans on identity candidates (spec 030 contract 02, R4/R5/R6/R8). |
| `apps/admission/resolution/splink_adapter.py` | Splink 5.0.0 as a linkage *proposer*, behind the platform's resolution contract. |
| `apps/admission/tests/contract/test_resolution_history.py` | Split supersedes, never erases; corroboration counts roots (spec 030 T079, T080). |
| `apps/admission/tests/unit/test_splink_adapter.py` | Splink proposes; it does not decide (spec 030 CE-001 §15.5, DON-ER-003, T105). |
| `apps/control-plane/api/routes/resolutions.py` | Resolution review API (feature 005 US2): pair_candidates queue + decision endpoints. |
| `apps/control-plane/tests/integration/test_resolution_api.py` | API integration test: resolution review endpoints (feature 005 US2). |
| `apps/shared/semantic/blocking.py` | Type-hypothesis and relation-affordance candidate blocking (FR-016, T017, SC-10). |
| `apps/shared/semantic/resolution.py` | Mention -> entity resolution: the machine, in the order the architect named it. |
| `apps/shared/tests/unit/test_resolution_mention_span.py` | ResolutionMention span survival (spec 030 T059/T060, contract 02 R5/R7). |
| `apps/zero/tests/test_resolution.py` | Unit tests for Layer 2 entity resolution (spec/010 §0.8) — pure math, no AI. |
| `apps/zero/zero/resolution/__init__.py` | Resolution layer (spec/010 §0.8): pure matching mathematics, NO AI. |
| `apps/zero/zero/resolution/fellegi_sunter.py` | Fellegi-Sunter probabilistic matcher (spec/010 §0.8 step 2) — vs Splink. |
| `apps/zero/zero/resolution/graph.py` | Resolution graph topology (spec/010 §0.8 step 4) — NO AI. |
| `apps/zero/zero/resolution/similarity.py` | Fuzzy string similarity (spec/010 §0.8 step 3) — pure stdlib. |

## Claims, conflicts, independence

| Module | Docstring |
|---|---|
| `apps/acquisition/tests/unit/test_browser_fabric.py` | Browser work-cluster fabric (T105): assignment, overlay, visibility. |
| `apps/acquisition/worker_browser/fabric.py` | Browser work-cluster fabric (T105): cluster topology + coverage overlay. |
| `apps/admission/independence/__init__.py` |  |
| `apps/admission/independence/independence.py` | Source Independence Engine (T087, FR-015). |
| `apps/admission/tests/test_effective_independence.py` | WP-E T071: corroboration counts *origins*, not hostnames. |
| `apps/control-plane/api/routes/fabric.py` | Zero-layer (Collection Fabric) control surface API. |
| `apps/control-plane/context_engine/fabric_bridge.py` | Control-plane bridge: fabric findings into the engine's own signal vocabulary. |
| `apps/control-plane/context_engine/fabric_runner.py` | The runner: one fabric pass, persisted, translated into engine signals. |
| `apps/control-plane/context_engine/fabric_store.py` | Durable persistence for the context fabric. |
| `apps/control-plane/db/migrations/versions/018_semantic_fabric.py` | Alembic migration for semantic fabric persistence (feature 017). |
| `apps/control-plane/db/migrations/versions/022_context_fabric.py` | Context fabric persistence (spec 025 §7, §13, §15.3, §33). |
| `apps/control-plane/services/capture_interpretation.py` | Turn a WARC range pull into provenance-bearing interpretation/admission data. |
| `apps/control-plane/tests/unit/test_fabric_anchor_guard.py` | Unanchored science findings must not become research obligations (spec 030 FR-066, T139). |
| `apps/control-plane/tests/unit/test_fabric_endpoints.py` | Zero-layer (Collection Fabric) control-surface API tests. |
| `apps/science/context/fabric.py` | The context fabric: every layer of spec 025 composed into one pass. |
| `apps/science/tests/contract/test_coverage_independence_contract.py` | Contract: evidence independence, coverage-qualified absence, saturation. |
| `apps/shared/domain/fabric.py` | Atomic entity fabric — integration facade (feature 009, block A). |
| `apps/shared/events/fabric_events.py` | Kafka wiring for the atomic entity fabric (feature 009, block A). |
| `apps/shared/scoring/__init__.py` |  |
| `apps/shared/scoring/claim.py` | Claim verdict + corroboration signals (T004, FR-011, investigator pattern). |
| `apps/shared/scoring/fusion.py` | Rank fusion over heterogeneous ranked lists. |
| `apps/shared/scoring/metrics.py` | Collection metrics for the Global Collection Fabric (T114, US1, R-11). |
| `apps/shared/scoring/scorer.py` | UtilityScorer + AdaptiveState impl (T027, `contracts/utility-scorer.md`, FR-027). |
| `apps/shared/tests/constitution/test_constitution4_no_fabrication.py` | Constitution 4 and CD-7: the platform never fabricates, and losing semantics must not |
| `apps/shared/tests/contract/test_entity_fabric.py` | Feature-009 contract tests: atomic entity fabric (stream-first). |

## Rebuildable projections

| Module | Docstring |
|---|---|
| `apps/acquisition/adapters/discovery/linkgraph.py` | Link-graph discovery source (FR-004, US3). |
| `apps/acquisition/entity_search.py` | Deterministic entity search planning surface. |
| `apps/acquisition/tests/unit/test_entity_search.py` | Deterministic entity search surface unit tests. |
| `apps/control-plane/api/routes/research_cases.py` | Person Research Case API routes (Feature 034). |
| `apps/control-plane/api/routes/science_tda.py` | Topological invariant API (011, FR-008/FR-009; the "TDA in the corner"). |
| `apps/control-plane/api/routes/search.py` | Search plane endpoints (T026/T051, US2). |
| `apps/control-plane/api/routes/search_rebuild.py` | Admin-only search projection rebuild (T029, SC-009). |
| `apps/control-plane/api/routes/temporal_materializations.py` |  |
| `apps/control-plane/context_engine/context_graph.py` | The Context Graph — first-class, durable, and the thing the user actually works in. |
| `apps/control-plane/context_engine/context_graph_store.py` | The Context Graph on PostgreSQL — durable, transactional, replayable (§3.6). |
| `apps/control-plane/db/migrations/versions/014_temporal_materialization.py` | Alembic migration for temporal materialization persistence (feature 014). |
| `apps/control-plane/db/migrations/versions/016_relation_evidence_graph.py` | Alembic migration for relation & evidence graph fabric persistence (feature 016). |
| `apps/control-plane/db/migrations/versions/025_context_graph.py` | Context graph persistence: nodes, edges, decisions (025). |
| `apps/control-plane/db/migrations/versions/026_person_research_case_runtime.py` | Durable reservation ledger for Feature 034 (revision 026). |
| `apps/control-plane/db/temporal_materialization.py` | SQLAlchemy persistence adapter for temporal materialization projections. |
| `apps/control-plane/services/research_case_policy.py` | Person case policy gate (Feature 034). |
| `apps/control-plane/services/research_case_runtime.py` | Durable Feature 034 budget reservations and the existing Layer-0 dispatcher adapter. |
| `apps/control-plane/services/research_case_service.py` | Person case application service (Feature 034). |
| `apps/control-plane/services/search_backends.py` | Real query backends for the search plane (T026, US2). |
| `apps/control-plane/services/temporal_materialization_dispatch.py` | Temporal launch seam for entity-created temporal materialization. |
| `apps/control-plane/services/temporal_materialization_service.py` | Control-plane service facade for deterministic temporal materialization. |
| `apps/control-plane/tests/contract/test_context_graph_contract.py` | What the Context Graph is required to refuse, and what it must never confuse. |
| `apps/control-plane/tests/integration/test_closed_research_loop.py` | WP-A: the research loop must be able to close, and say why. |
| `apps/control-plane/tests/integration/test_temporal_materialization_api.py` | API integration tests for temporal materialization. |
| `apps/control-plane/tests/test_research_case_invariants.py` | Regression tests for the formerly broken Feature 034 case lifecycle. |

## Closed loop / frontier

| Module | Docstring |
|---|---|
| `apps/control-plane/services/discovery_frontier.py` | Production bindings between Layer A discovery and the durable frontier (008). |
| `apps/control-plane/services/frontier.py` | Frontier operational state (T026, FR-003, R-4). |
| `apps/control-plane/tests/integration/test_frontier_provenance.py` | FR-007 survives the bridge from Layer A discovery to the durable frontier. |
| `apps/feedback/feedback/__init__.py` | Feedback plane: adaptive loop closing (T116-T118). |
| `apps/feedback/feedback/branch/__init__.py` | Feedback plane branches (T116-T118): import to register them. |
| `apps/feedback/feedback/branch/entity.py` | T117: entity-resolution -> acquisition-hypothesis feedback branch. |
| `apps/feedback/feedback/branch/finding.py` | T118: finding -> new-work feedback branch. |
| `apps/feedback/feedback/branch/source.py` | T116: source-independence feedback branch. |
| `apps/feedback/feedback/frontier.py` | Feedback loop closing: frontier sinks + shared forms (T116-T118). |
| `apps/feedback/feedback_engine.py` | Feedback engine (T044). |
| `apps/feedback/stopping.py` | Stopping policy (T045). |
| `apps/feedback/tests/test_branches.py` | Feedback branches unit tests (T116/T117/T118): hermetic, no live stack. |
| `apps/feedback/tests/test_feedback.py` | Unit tests for feedback engine + stopping policy (T044-T045). |
| `apps/feedback/tests/test_frontier_loop.py` | Integration: feedback loop closes into the authoritative Postgres frontier. |
| `apps/science/hypotheses/gain.py` | Information-gain collection planner (T104, US2; interface-contracts §4). |
| `apps/science/tests/unit/test_gain.py` | Unit tests: information-gain planner (T100, US2). |
| `apps/zero/zero/enrichment/feedback.py` | Feedback loop (spec/010 §0.9, FR-005) — Layer 3 → Layer 1. |

## Report & completion

| Module | Docstring |
|---|---|
| `apps/control-plane/api/routes/dossier.py` | Dossier API — the surface an analyst actually reads. |
| `apps/control-plane/api/routes/findings.py` | Finding overview API (T053, US2, FR-032). |
| `apps/control-plane/context_engine/dossier_store.py` | Making a sweep survive the process, and survive being asked about again afterwards. |
| `apps/control-plane/tests/unit/test_dossier_store.py` | The round trip that decides whether a dossier survives its process. |
| `apps/science/context/dossier.py` | Dossier assembly: the one artefact an analyst actually reads. |
| `apps/science/robustness/report.py` | Flip rates, sensitivity and noise regions (T129, US6, FR-011). |
| `apps/science/tests/contract/test_dossier_contract.py` | Contract: the dossier is the honest end of the pipeline (spec 026). |

## Golden paths

**None are proven end-to-end.** The pipeline above is the intended shape; a golden path
requires a live stack (Postgres/MinIO/Kafka/OpenSearch/ClickHouse/Temporal) and a
request→report run. See [findings.md](findings.md).
