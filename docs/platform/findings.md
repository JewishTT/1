# Findings

What the generated model says is broken or unproven. Every row is derived from the tree;
nothing here is a matter of opinion.

## Test-only capabilities (production never calls them)

| Capability | Module | Claim |
|---|---|---|
| `durable-dlq` | `apps/shared/events/dlq_durable.py` | quarantine + replay |
| `admission-decisions` | `apps/admission/resolution/decision_store.py` | the only committer of identity/claim decisions |
| `temporal-filter` | `apps/science/context/temporal_filter.py` | CURRENT / AS_OF / INTERVAL selection over dated facts |
| `donor-registry` | `donors/registry.yaml` | FR-113 supply-chain record |
| `layer-boundaries` | `apps/shared/tools/layer_boundaries.py` | cross-layer dependency guard |

## Missing capabilities

_None: every declared capability has a module in the tree._

## Competing writers (two writers of canonical state)

| Object | Table | Writer |
|---|---|---|
| `observation` | `observations` | `apps/control-plane/services/interpretation_bridge.py:240` — select(ObservationRow).where( |
| `observation` | `observations` | `apps/control-plane/services/pow_run.py:180` — from db.schema import Entity, EntityVersion, Observation, RelationClai |
| `observation` | `observations` | `apps/zero/zero/harvesters/url.py:135` — candidates: list[ObservationCandidate] = [] |
| `mention` | `mentions` | `apps/interpretation/aggregation/candidates.py:34` — def add(self, mention: CanonicalMention, source_id: str) -> None: |
| `mention` | `mentions` | `apps/interpretation/extractors/registry.py:145` — out: list[Mention] = [] |
| `candidate` | `candidates` | `apps/acquisition/adapters/discovery/contracts.py:94` — out: list[Candidate] = [] |
| `candidate` | `candidates` | `apps/admission/resolution/blocking.py:90` — def strategies(self, rec: CandidateRecord) -> dict[str, set[str]]: |
| `candidate` | `candidates` | `apps/feedback/feedback/branch/source.py:83` — candidates: list[FeedbackCandidate] = [] |
| `candidate` | `candidates` | `apps/feedback/feedback/frontier.py:64` — async def enqueue_candidate(self, candidate: FeedbackCandidate) -> boo |
| `candidate` | `candidates` | `apps/interpretation/aggregation/candidates.py:63` — def add(self, mention: CanonicalMention, source_id: str, offset: int = |
| `candidate` | `candidates` | `apps/zero/zero/harvesters/url.py:135` — candidates: list[ObservationCandidate] = [] |
| `entity` | `entities` | `apps/control-plane/api/routes/entities.py:144` — pg_insert(InvestigationEntityMembership) |
| `entity` | `entities` | `apps/control-plane/api/routes/manual_assertions.py:172` — existing = await session.get(Entity, entity_id) |
| `entity` | `entities` | `apps/control-plane/db/entity_stream.py:182` — EntityStreamRow.observation_id.in_(wanted), |
| `entity` | `entities` | `apps/control-plane/services/interpretation_bridge.py:281` — EntityRow.entity_id == entity_id, |
| `entity` | `entities` | `apps/control-plane/services/pow_run.py:180` — from db.schema import Entity, EntityVersion, Observation, RelationClai |
| `entity` | `entities` | `apps/science/context/lattice.py:435` — ``LegalEntity``. That is a ``DERIVED`` closure and the operator says s |
| `frontier item` | `frontier_items` | `apps/control-plane/services/frontier.py:233` — from db.schema import FrontierItem as Row |
| `frontier item` | `frontier_items` | `apps/feedback/feedback/frontier.py:65` — from db.schema import FrontierItem as Row |
| `investigation` | `investigations` | `apps/control-plane/api/routes/entities.py:144` — pg_insert(InvestigationEntityMembership) |
| `investigation` | `investigations` | `apps/control-plane/context_engine/engine.py:1254` — state = InvestigationState.ACTIVE if created else context.state |
| `investigation` | `investigations` | `apps/control-plane/context_engine/postgres_store.py:405` — async def put_context(self, context: InvestigationContext) -> None: |
| `investigation` | `investigations` | `apps/control-plane/db/investigation_store.py:133` — async def create(self, investigation: Investigation) -> Investigation: |

## Objects with no writer

| Object | Table | Note |
|---|---|---|
| `assertion` | `assertions` | — |
| `evidence link` | `evidence_links` | — |
| `admission decision` | `admission_decisions` | — |
| `calibration profile` | `calibration_profiles` | — |
| `finding` | `findings` | — |
| `audit log` | `audit_logs` | — |
| `acquisition task` | `acquisition_tasks` | — |
| `source` | `sources` | — |

## Untested modules

277 platform modules are not imported by any test. Sample:

| Module |
|---|
| `apps/acquisition/_measure_coverage.py` |
| `apps/acquisition/_probe_catalogue.py` |
| `apps/acquisition/_prove_airbyte.py` |
| `apps/acquisition/_prove_backbone.py` |
| `apps/acquisition/_prove_readback.py` |
| `apps/acquisition/_prove_searxng.py` |
| `apps/acquisition/_prove_tools.py` |
| `apps/acquisition/adapters/__init__.py` |
| `apps/acquisition/adapters/_ingest.py` |
| `apps/acquisition/adapters/common_crawl.py` |
| `apps/acquisition/adapters/discovery/commoncrawl_index.py` |
| `apps/acquisition/adapters/discovery/contracts.py` |
| `apps/acquisition/adapters/discovery/crtsh.py` |
| `apps/acquisition/adapters/discovery/linkgraph.py` |
| `apps/acquisition/adapters/discovery/wayback_cdx.py` |
| `apps/acquisition/adapters/scrapy/spider.py` |
| `apps/acquisition/adapters/sec_edgar.py` |
| `apps/acquisition/dispatcher/__init__.py` |
| `apps/acquisition/observation_gate/__init__.py` |
| `apps/acquisition/policies/__init__.py` |
| `apps/acquisition/runtime/external_tool.py` |
| `apps/acquisition/runtime/searxng.py` |
| `apps/acquisition/sources/__init__.py` |
| `apps/acquisition/sources/append_parse_blocks.py` |
| `apps/acquisition/sources/capabilities.py` |
| `apps/acquisition/stream.py` |
| `apps/acquisition/worker-dataset/__init__.py` |
| `apps/acquisition/worker-dataset/acquire.py` |
| `apps/acquisition/worker_browser/__init__.py` |
| `apps/acquisition/worker_http/__init__.py` |
| `apps/acquisition/worker_service.py` |
| `apps/admission/engine/__init__.py` |
| `apps/admission/independence/__init__.py` |
| `apps/admission/resolution/__init__.py` |
| `apps/bulk-ingestion/backfill.py` |
| `apps/bulk-ingestion/historical/__init__.py` |
| `apps/bulk-ingestion/historical/replay.py` |
| `apps/control-plane/__init__.py` |
| `apps/control-plane/api/path_shim.py` |
| `apps/control-plane/api/routes/connectors.py` |

## Unresolved imports (by evidence)

0 platform imports have no resolved target (local/stale/guarded-local); 1 tracked guarded gaps; 281 undeclared (not platform/stdlib/installed/declared).

| From | Import | Kind |
|---|---|---|
| `apps/acquisition/tests/contract/test_plan_driver.py` | `pytest` | unknown |
| `apps/acquisition/tests/contract/test_scheduler.py` | `pytest` | unknown |
| `apps/acquisition/tests/integration/test_adapters_gate.py` | `pytest` | unknown |
| `apps/acquisition/tests/integration/test_backpressure.py` | `pytest` | unknown |
| `apps/acquisition/tests/integration/test_engine_adapters_gate.py` | `pytest` | unknown |
| `apps/acquisition/tests/integration/test_live_loop.py` | `pytest` | unknown |
| `apps/acquisition/tests/integration/test_loop_closed.py` | `pytest` | unknown |
| `apps/acquisition/tests/integration/test_worker.py` | `pytest` | unknown |
| `apps/acquisition/tests/test_connector_registry.py` | `pytest` | unknown |
| `apps/acquisition/tests/unit/test_acquisition_artifact_sink.py` | `pytest` | unknown |
| `apps/acquisition/tests/unit/test_acquisition_worker.py` | `pytest` | unknown |
| `apps/acquisition/tests/unit/test_adapter_onboarding.py` | `pytest` | unknown |
| `apps/acquisition/tests/unit/test_airbyte_runtime.py` | `pytest` | unknown |
| `apps/acquisition/tests/unit/test_bbot_process_boundary.py` | `pytest` | unknown |
| `apps/acquisition/tests/unit/test_bbot_runtime.py` | `pytest` | unknown |
| `apps/acquisition/tests/unit/test_case_execution_guard.py` | `pytest` | unknown |
| `apps/acquisition/tests/unit/test_engine_adapters.py` | `pytest` | unknown |
| `apps/acquisition/tests/unit/test_evidence_writer.py` | `pytest` | unknown |
| `apps/acquisition/tests/unit/test_primproc_runtime.py` | `pytest` | unknown |
| `apps/acquisition/tests/unit/test_source_catalogue_full.py` | `pytest` | unknown |
| `apps/acquisition/tests/unit/test_source_executor_contracts.py` | `pytest` | unknown |
| `apps/acquisition/tests/unit/test_warc_adapter.py` | `pytest` | unknown |
| `apps/admission/tests/contract/test_no_auto_merge.py` | `pytest` | unknown |
| `apps/admission/tests/contract/test_resolution_history.py` | `pytest` | unknown |
| `apps/admission/tests/test_candidate.py` | `pytest` | unknown |
| `apps/admission/tests/test_claims.py` | `pytest` | unknown |
| `apps/admission/tests/test_effective_independence.py` | `pytest` | unknown |
| `apps/admission/tests/test_statement_consumer.py` | `pytest` | unknown |
| `apps/admission/tests/unit/test_cluster_transitivity.py` | `pytest` | unknown |
| `apps/admission/tests/unit/test_splink_adapter.py` | `pytest` | unknown |
| `apps/bulk-ingestion/tests/contract/test_archive_live_convergence.py` | `pytest` | unknown |
| `apps/bulk-ingestion/tests/unit/test_backfill.py` | `pytest` | unknown |
| `apps/bulk-ingestion/tests/unit/test_historical_replay.py` | `pytest` | unknown |
| `apps/control-plane/api/sse.py` | `starlette.responses` | unknown |
| `apps/control-plane/tests/contract/test_context_graph_contract.py` | `pytest` | unknown |
| `apps/control-plane/tests/integration/test_cc_temporality_api.py` | `pytest` | unknown |
| `apps/control-plane/tests/integration/test_closed_research_loop.py` | `pytest` | unknown |
| `apps/control-plane/tests/integration/test_donor_api.py` | `pytest` | unknown |
| `apps/control-plane/tests/integration/test_end_to_end_pipeline.py` | `pytest` | unknown |
| `apps/control-plane/tests/integration/test_entity_investigation_membership.py` | `pytest` | unknown |
| `apps/control-plane/tests/integration/test_epistemic_roundtrip.py` | `pytest` | unknown |
| `apps/control-plane/tests/integration/test_finding_evidence_chain.py` | `pytest` | unknown |
| `apps/control-plane/tests/integration/test_frontier_provenance.py` | `pytest` | unknown |
| `apps/control-plane/tests/integration/test_investigation_temporal.py` | `pytest` | unknown |
| `apps/control-plane/tests/integration/test_layer0_direct_pipeline.py` | `pytest` | unknown |
| `apps/control-plane/tests/integration/test_lineage_api.py` | `pytest` | unknown |
| `apps/control-plane/tests/integration/test_loop_closure.py` | `pytest` | unknown |
| `apps/control-plane/tests/integration/test_observation_immutability.py` | `pytest` | unknown |
| `apps/control-plane/tests/integration/test_orm_migration_parity.py` | `pytest` | unknown |
| `apps/control-plane/tests/integration/test_platform_assembly.py` | `pytest` | unknown |
| `apps/control-plane/tests/integration/test_quarantine.py` | `pytest` | unknown |
| `apps/control-plane/tests/integration/test_query_planner.py` | `pytest` | unknown |
| `apps/control-plane/tests/integration/test_resolution_api.py` | `pytest` | unknown |
| `apps/control-plane/tests/integration/test_science_api.py` | `pytest` | unknown |
| `apps/control-plane/tests/integration/test_seed_security.py` | `pytest` | unknown |
| `apps/control-plane/tests/integration/test_temporal_materialization_api.py` | `pytest` | unknown |
| `apps/control-plane/tests/integration/test_tenancy.py` | `pytest` | unknown |
| `apps/control-plane/tests/integration/test_tools_api.py` | `pytest` | unknown |
| `apps/control-plane/tests/test_auth_security.py` | `pytest` | unknown |
| `apps/control-plane/tests/test_auth_security.py` | `starlette.requests` | unknown |
| `apps/control-plane/tests/test_research_case_invariants.py` | `pytest` | unknown |
| `apps/control-plane/tests/test_research_case_projection.py` | `pytest` | unknown |
| `apps/control-plane/tests/test_research_case_reports.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_action_memory.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_approval_gate.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_assembly_structural_conflict.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_cc_temporality.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_cognitive_loop.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_context_engine.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_context_termination_and_catalogue.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_digest_gated_revision.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_dispatcher_backpressure.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_donor_patterns.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_entity_stream_persistence.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_fabric_anchor_guard.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_fabric_endpoints.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_invariant_reducer.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_migration_017_forward_only.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_migration_020_universal_relation.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_migration_024_investigation_entity_membership.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_monitor.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_network_analytics.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_ontology_registry.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_postgres_context_store.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_producer_binding_golden_path.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_query_degradation.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_query_fusion.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_rank_fusion_wiring.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_relation_candidate_storage_contract.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_relation_projection_outbox_contract.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_science_tda.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_search_core_selection.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_search_fusion_api.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_series_lifecycle.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_sse_stream.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_temporal_materialization_persistence.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_temporal_port.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_us1_core.py` | `pytest` | unknown |
| `apps/control-plane/tests/unit/test_workflows.py` | `pytest` | unknown |
| `apps/feedback/tests/test_branches.py` | `pytest` | unknown |
| `apps/feedback/tests/test_frontier_loop.py` | `pytest` | unknown |
| `apps/interpretation/parsers/documents.py` | `PIL` | unknown |
| `apps/interpretation/tests/conftest.py` | `pytest` | unknown |
| `apps/interpretation/tests/contract/test_parser_families.py` | `pytest` | unknown |
| `apps/interpretation/tests/contract/test_span_semantics.py` | `pytest` | unknown |
| `apps/interpretation/tests/integration/test_all_sources_parse.py` | `pytest` | unknown |
| `apps/interpretation/tests/test_deterministic_extraction.py` | `pytest` | unknown |
| `apps/interpretation/tests/test_evidence_manifest.py` | `pytest` | unknown |
| `apps/interpretation/tests/test_mention_binding_seam.py` | `pytest` | unknown |
| `apps/interpretation/tests/test_observation_consumer.py` | `pytest` | unknown |
| `apps/interpretation/tests/test_parser_adapter.py` | `pytest` | unknown |
| `apps/interpretation/tests/test_payload_binding.py` | `pytest` | unknown |
| `apps/interpretation/tests/test_payload_detection.py` | `pytest` | unknown |
| `apps/interpretation/tests/test_payload_hypotheses.py` | `pytest` | unknown |
| `apps/interpretation/tests/test_payload_parser_layer.py` | `pytest` | unknown |
| `apps/interpretation/tests/test_payload_routing.py` | `pytest` | unknown |
| `apps/interpretation/tests/test_payload_structure_producer.py` | `pytest` | unknown |
| `apps/interpretation/tests/test_primary_proc.py` | `pytest` | unknown |
| `apps/interpretation/tests/test_primary_proc_regex_mutant.py` | `pytest` | unknown |
| `apps/interpretation/tests/test_producer_migration.py` | `pytest` | unknown |
| `apps/interpretation/tests/test_relation_cue_coverage.py` | `pytest` | unknown |
| `apps/interpretation/tests/test_relations.py` | `pytest` | unknown |
| `apps/interpretation/tests/test_retriever_fusion.py` | `pytest` | unknown |
| `apps/interpretation/tests/test_signal_kind_channels.py` | `pytest` | unknown |
| `apps/interpretation/tests/test_signal_nary_contract.py` | `pytest` | unknown |
| `apps/interpretation/tests/test_syntactic_producer.py` | `pytest` | unknown |
| `apps/interpretation/tests/test_tenzir_live.py` | `pytest` | unknown |
| `apps/interpretation/tests/test_tenzir_normalization.py` | `pytest` | unknown |
| `apps/interpretation/tests/test_warc_reader.py` | `pytest` | unknown |
| `apps/projection/tests/contract/test_search_projection_manifest.py` | `pytest` | unknown |
| `apps/projection/tests/contract/test_tda_bridge_contract.py` | `pytest` | unknown |
| `apps/projection/tests/test_bm25s_backend.py` | `pytest` | unknown |
| `apps/projection/tests/test_tantivy_backend.py` | `pytest` | unknown |
| `apps/projection/tests/unit/test_claim_projection.py` | `pytest` | unknown |
| `apps/projection/tests/unit/test_diagram.py` | `pytest` | unknown |
| `apps/projection/tests/unit/test_features.py` | `pytest` | unknown |
| `apps/projection/tests/unit/test_graph_store_direction.py` | `pytest` | unknown |
| `apps/projection/tests/unit/test_h3_spatial.py` | `pytest` | unknown |
| `apps/projection/tests/unit/test_neo4j_relation_write.py` | `pytest` | unknown |
| `apps/projection/tests/unit/test_pipeline_directed.py` | `pytest` | unknown |
| `apps/projection/tests/unit/test_relation_store.py` | `pytest` | unknown |
| `apps/projection/tests/unit/test_takens.py` | `pytest` | unknown |
| `apps/projection/tests/unit/test_tda_insight.py` | `pytest` | unknown |
| `apps/projection/tests/unit/test_tda_pipeline_performance.py` | `pytest` | unknown |
| `apps/projection/tests/unit/test_temporal_graph.py` | `pytest` | unknown |
| `apps/projection/tests/unit/test_topological_invariant.py` | `pytest` | unknown |
| `apps/projection/tests/unit/test_validated.py` | `pytest` | unknown |
| `apps/science/context/tests/test_epistemic_algebra.py` | `pytest` | unknown |
| `apps/science/tests/contract/test_argumentation_contract.py` | `pytest` | unknown |
| `apps/science/tests/contract/test_causal_contract.py` | `pytest` | unknown |
| `apps/science/tests/contract/test_circularity_contract.py` | `pytest` | unknown |
| `apps/science/tests/contract/test_claim_contract.py` | `pytest` | unknown |
| `apps/science/tests/contract/test_completeness_contract.py` | `pytest` | unknown |
| `apps/science/tests/contract/test_coverage_independence_contract.py` | `pytest` | unknown |
| `apps/science/tests/contract/test_dialectics_contract.py` | `pytest` | unknown |
| `apps/science/tests/contract/test_discipline_adapters_contract.py` | `pytest` | unknown |
| `apps/science/tests/contract/test_dossier_contract.py` | `pytest` | unknown |
| `apps/science/tests/contract/test_enrichment_contract.py` | `pytest` | unknown |
| `apps/science/tests/contract/test_epistemic_contract.py` | `pytest` | unknown |
| `apps/science/tests/contract/test_event_emission_contract.py` | `pytest` | unknown |
| `apps/science/tests/contract/test_gluing_contract.py` | `pytest` | unknown |
| `apps/science/tests/contract/test_growth_contract.py` | `pytest` | unknown |
| `apps/science/tests/contract/test_hierarchy_contract.py` | `pytest` | unknown |
| `apps/science/tests/contract/test_hypothesis_contract.py` | `pytest` | unknown |
| `apps/science/tests/contract/test_locality_contract.py` | `pytest` | unknown |
| `apps/science/tests/contract/test_ontology_and_schema_stay_in_step.py` | `pytest` | unknown |
| `apps/science/tests/contract/test_operator_registry_contract.py` | `pytest` | unknown |
| `apps/science/tests/contract/test_operator_result_bridge.py` | `pytest` | unknown |
| `apps/science/tests/contract/test_query_compiler_contract.py` | `pytest` | unknown |
| `apps/science/tests/contract/test_robustness_contract.py` | `pytest` | unknown |
| `apps/science/tests/contract/test_science_seam_contract.py` | `pytest` | unknown |
| `apps/science/tests/contract/test_scope_lattice_contract.py` | `pytest` | unknown |
| `apps/science/tests/contract/test_structure_contract.py` | `pytest` | unknown |
| `apps/science/tests/contract/test_temporal_filter.py` | `pytest` | unknown |
| `apps/science/tests/contract/test_worldline_view_contract.py` | `pytest` | unknown |
| `apps/science/tests/integration/test_context_engine_chain.py` | `pytest` | unknown |
| `apps/science/tests/integration/test_live_asg_pipeline.py` | `pytest` | unknown |
| `apps/science/tests/integration/test_live_scope_lattice.py` | `pytest` | unknown |
| `apps/science/tests/test_anchoring.py` | `pytest` | unknown |
| `apps/science/tests/unit/test_econ.py` | `pytest` | unknown |
| `apps/science/tests/unit/test_kinetics.py` | `pytest` | unknown |
| `apps/science/tests/unit/test_landscape.py` | `pytest` | unknown |
| `apps/science/tests/unit/test_phase.py` | `pytest` | unknown |
| `apps/science/tests/unit/test_river_drift.py` | `pytest` | unknown |
| `apps/science/tests/unit/test_schelling.py` | `pytest` | unknown |
| `apps/science/tests/unit/test_scope.py` | `pytest` | unknown |
| `apps/science/tests/unit/test_series_embedding.py` | `pytest` | unknown |
| `apps/science/tests/unit/test_structure.py` | `pytest` | unknown |
| `apps/science/tests/unit/test_tda.py` | `pytest` | unknown |
| `apps/shared/events/dlq_durable.py` | `anyio` | unknown |
| `apps/shared/events/dlq_durable.py` | `anyio` | unknown |
| `apps/shared/events/dlq_durable.py` | `anyio` | unknown |
| `apps/shared/events/event_envelope_pb2.py` | `google.protobuf` | unknown |
| `apps/shared/events/event_envelope_pb2.py` | `google.protobuf` | unknown |
| `apps/shared/events/event_envelope_pb2.py` | `google.protobuf` | unknown |
| `apps/shared/events/event_envelope_pb2.py` | `google.protobuf` | unknown |
| `apps/shared/events/event_envelope_pb2.py` | `google.protobuf.internal` | unknown |
| `apps/shared/tests/constitution/test_constitution4_no_fabrication.py` | `pytest` | unknown |
| `apps/shared/tests/constitution/test_constitution_has_teeth.py` | `pytest` | unknown |
| `apps/shared/tests/constitution/test_i1_i3_immutability_and_preservation.py` | `pytest` | unknown |
| `apps/shared/tests/constitution/test_identity_subsystem_constitution.py` | `pytest` | unknown |
| `apps/shared/tests/constitution/test_iv_vi_tenancy_and_determinism.py` | `pytest` | unknown |
| `apps/shared/tests/contract/test_correlation.py` | `pytest` | unknown |
| `apps/shared/tests/contract/test_domain_invariants.py` | `pytest` | unknown |
| `apps/shared/tests/contract/test_donor_registry.py` | `pytest` | unknown |
| `apps/shared/tests/contract/test_donor_registry.py` | `packaging.requirements` | unknown |
| `apps/shared/tests/contract/test_donor_registry.py` | `packaging.version` | unknown |
| `apps/shared/tests/contract/test_entity_fabric.py` | `pytest` | unknown |
| `apps/shared/tests/contract/test_error_codes.py` | `pytest` | unknown |
| `apps/shared/tests/contract/test_event_envelope.py` | `pytest` | unknown |
| `apps/shared/tests/contract/test_evidence_span.py` | `pytest` | unknown |
| `apps/shared/tests/contract/test_evidence_span_roundtrip.py` | `pytest` | unknown |
| `apps/shared/tests/contract/test_metrics.py` | `pytest` | unknown |
| `apps/shared/tests/contract/test_ontology.py` | `pytest` | unknown |
| `apps/shared/tests/contract/test_operator_result.py` | `pytest` | unknown |
| `apps/shared/tests/contract/test_platform_gaps.py` | `pytest` | unknown |
| `apps/shared/tests/contract/test_platform_model.py` | `pytest` | unknown |
| `apps/shared/tests/contract/test_projection_manifest.py` | `pytest` | unknown |
| `apps/shared/tests/contract/test_review.py` | `pytest` | unknown |
| `apps/shared/tests/contract/test_single_publication_path.py` | `pytest` | unknown |
| `apps/shared/tests/contract/test_stage_outcome.py` | `pytest` | unknown |
| `apps/shared/tests/contract/test_statement.py` | `pytest` | unknown |
| `apps/shared/tests/contract/test_storage.py` | `pytest` | unknown |
| `apps/shared/tests/integration/test_idempotency.py` | `pytest` | unknown |
| `apps/shared/tests/integration/test_infra_connectivity.py` | `pytest` | unknown |
| `apps/shared/tests/integration/test_infra_connectivity.py` | `botocore` | unknown |
| `apps/shared/tests/integration/test_redpanda_emission.py` | `pytest` | unknown |
| `apps/shared/tests/unit/domain/test_domain_model.py` | `pytest` | unknown |
| `apps/shared/tests/unit/domain/test_graph_invariant.py` | `pytest` | unknown |
| `apps/shared/tests/unit/domain/test_temporal_materialization.py` | `pytest` | unknown |
| `apps/shared/tests/unit/domain/test_temporal_worldline.py` | `pytest` | unknown |
| `apps/shared/tests/unit/domain/test_temporal_worldline_store.py` | `pytest` | unknown |
| `apps/shared/tests/unit/donor/conftest.py` | `pytest` | unknown |
| `apps/shared/tests/unit/donor/test_evidence.py` | `pytest` | unknown |
| `apps/shared/tests/unit/donor/test_target.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_access_mode.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_acquisition_path.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_candidate_logical_identity.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_cc_session.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_cd6_unresolved_predicate.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_co_mention.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_commoncrawl.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_derivation_identity.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_dlq_durable.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_event_timestamps.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_evidence_context.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_evidence_lineage.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_evidence_store_guard.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_fusion.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_idempotent_consumer.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_investigation_context.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_layer_boundaries.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_measured_values.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_mention_occurrence_index.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_observation_gate_identity.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_observation_identity.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_open_world_predicates.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_participant_end_kind.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_predicate_signature.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_range_pull.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_relation_claim.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_relation_identity.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_relation_schema.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_relation_schema.py` | `domain.context_validation` | guarded-gap |
| `apps/shared/tests/unit/test_research_lineage.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_resolution_mention_span.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_schema_hierarchy.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_secure_fetch.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_security.py` | `pytest` | unknown |
| `apps/shared/tests/unit/test_temporal_metrics.py` | `pytest` | unknown |
| `apps/specops/tests/conftest.py` | `pytest` | unknown |
| `apps/specops/tests/test_engagement.py` | `pytest` | unknown |
| `apps/specops/tests/test_ghostline.py` | `pytest` | unknown |
| `apps/specops/tests/test_roe_gate.py` | `pytest` | unknown |
| `apps/specops/tests/test_specops_ghostline_routers.py` | `pytest` | unknown |
| `apps/zero/tests/conftest.py` | `pytest` | unknown |
| `apps/zero/tests/test_cc_capture.py` | `pytest` | unknown |
| `apps/zero/tests/test_harvest_wave.py` | `pytest` | unknown |
| `apps/zero/tests/test_harvesters.py` | `pytest` | unknown |
| `apps/zero/tests/test_resolution.py` | `pytest` | unknown |
| `apps/zero/tests/test_type_detector.py` | `pytest` | unknown |
| `bench/tests/test_scale_scale.py` | `pytest` | unknown |
