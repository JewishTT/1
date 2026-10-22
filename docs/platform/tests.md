# Tests

321 test files, 5177 test functions. 639 platform
modules are not imported by any test.

## Test files

| File | Tests | Targets |
|---|---|---|
| `apps/acquisition/tests/contract/test_plan_driver.py` | 20 | — |
| `apps/acquisition/tests/contract/test_scheduler.py` | 11 | — |
| `apps/acquisition/tests/integration/test_adapters_gate.py` | 5 | — |
| `apps/acquisition/tests/integration/test_backpressure.py` | 6 | — |
| `apps/acquisition/tests/integration/test_engine_adapters_gate.py` | 5 | — |
| `apps/acquisition/tests/integration/test_live_loop.py` | 4 | — |
| `apps/acquisition/tests/integration/test_loop_closed.py` | 2 | — |
| `apps/acquisition/tests/integration/test_worker.py` | 5 | — |
| `apps/acquisition/tests/test_connector_registry.py` | 13 | — |
| `apps/acquisition/tests/unit/test_acquisition_artifact_sink.py` | 39 | — |
| `apps/acquisition/tests/unit/test_acquisition_worker.py` | 31 | — |
| `apps/acquisition/tests/unit/test_adapter_onboarding.py` | 3 | — |
| `apps/acquisition/tests/unit/test_airbyte_runtime.py` | 28 | — |
| `apps/acquisition/tests/unit/test_archival_worker.py` | 8 | — |
| `apps/acquisition/tests/unit/test_bbot_process_boundary.py` | 15 | — |
| `apps/acquisition/tests/unit/test_bbot_runtime.py` | 25 | — |
| `apps/acquisition/tests/unit/test_browser_fabric.py` | 8 | — |
| `apps/acquisition/tests/unit/test_cc_extract.py` | 10 | — |
| `apps/acquisition/tests/unit/test_cc_index.py` | 3 | — |
| `apps/acquisition/tests/unit/test_cc_plan.py` | 12 | — |
| `apps/acquisition/tests/unit/test_engine_adapters.py` | 6 | — |
| `apps/acquisition/tests/unit/test_entity_search.py` | 4 | — |
| `apps/acquisition/tests/unit/test_primproc_runtime.py` | 32 | — |
| `apps/acquisition/tests/unit/test_region_backpressure.py` | 7 | — |
| `apps/acquisition/tests/unit/test_render_pipeline.py` | 6 | — |
| `apps/acquisition/tests/unit/test_replay_journal.py` | 5 | — |
| `apps/acquisition/tests/unit/test_source_catalogue_full.py` | 15 | — |
| `apps/acquisition/tests/unit/test_source_query_set.py` | 12 | — |
| `apps/acquisition/tests/unit/test_warc_adapter.py` | 3 | — |
| `apps/admission/tests/contract/test_no_auto_merge.py` | 25 | — |
| `apps/admission/tests/contract/test_resolution_history.py` | 35 | — |
| `apps/admission/tests/test_admission.py` | 22 | — |
| `apps/admission/tests/test_candidate.py` | 14 | — |
| `apps/admission/tests/test_claims.py` | 15 | — |
| `apps/admission/tests/test_collective_export.py` | 4 | — |
| `apps/admission/tests/test_effective_independence.py` | 11 | — |
| `apps/admission/tests/test_intake.py` | 38 | — |
| `apps/admission/tests/test_statement_consumer.py` | 5 | — |
| `apps/admission/tests/unit/test_cluster_transitivity.py` | 13 | — |
| `apps/admission/tests/unit/test_splink_adapter.py` | 20 | — |
| `apps/bulk-ingestion/tests/contract/test_archive_live_convergence.py` | 2 | — |
| `apps/bulk-ingestion/tests/unit/test_backfill.py` | 5 | — |
| `apps/bulk-ingestion/tests/unit/test_historical_replay.py` | 5 | — |
| `apps/control-plane/tests/contract/test_context_graph_contract.py` | 21 | — |
| `apps/control-plane/tests/integration/__init__.py` | 0 | — |
| `apps/control-plane/tests/integration/test_cc_temporality_api.py` | 3 | — |
| `apps/control-plane/tests/integration/test_closed_research_loop.py` | 13 | — |
| `apps/control-plane/tests/integration/test_donor_api.py` | 11 | — |
| `apps/control-plane/tests/integration/test_end_to_end_pipeline.py` | 2 | — |
| `apps/control-plane/tests/integration/test_entity_investigation_membership.py` | 9 | — |
| `apps/control-plane/tests/integration/test_epistemic_roundtrip.py` | 31 | — |
| `apps/control-plane/tests/integration/test_finding_evidence_chain.py` | 7 | — |
| `apps/control-plane/tests/integration/test_frontier_provenance.py` | 40 | — |
| `apps/control-plane/tests/integration/test_investigation_temporal.py` | 12 | — |
| `apps/control-plane/tests/integration/test_layer0_direct_pipeline.py` | 4 | — |
| `apps/control-plane/tests/integration/test_lineage_api.py` | 4 | — |
| `apps/control-plane/tests/integration/test_loop_closure.py` | 43 | — |
| `apps/control-plane/tests/integration/test_observation_changes_next_action.py` | 9 | — |
| `apps/control-plane/tests/integration/test_observation_immutability.py` | 5 | — |
| `apps/control-plane/tests/integration/test_orm_migration_parity.py` | 1 | — |
| `apps/control-plane/tests/integration/test_platform_assembly.py` | 31 | — |
| `apps/control-plane/tests/integration/test_quarantine.py` | 6 | — |
| `apps/control-plane/tests/integration/test_query_planner.py` | 5 | — |
| `apps/control-plane/tests/integration/test_resolution_api.py` | 4 | — |
| `apps/control-plane/tests/integration/test_science_api.py` | 4 | — |
| `apps/control-plane/tests/integration/test_seed_security.py` | 2 | — |
| `apps/control-plane/tests/integration/test_temporal_materialization_api.py` | 3 | — |
| `apps/control-plane/tests/integration/test_tenancy.py` | 6 | — |
| `apps/control-plane/tests/integration/test_tools_api.py` | 8 | — |
| `apps/control-plane/tests/unit/test_action_memory.py` | 19 | — |
| `apps/control-plane/tests/unit/test_approval_gate.py` | 7 | — |
| `apps/control-plane/tests/unit/test_assembly_structural_conflict.py` | 24 | — |
| `apps/control-plane/tests/unit/test_badges_facade.py` | 8 | — |
| `apps/control-plane/tests/unit/test_cc_temporality.py` | 7 | — |
| `apps/control-plane/tests/unit/test_cognitive_loop.py` | 18 | — |
| `apps/control-plane/tests/unit/test_context_engine.py` | 45 | — |
| `apps/control-plane/tests/unit/test_context_termination_and_catalogue.py` | 30 | — |
| `apps/control-plane/tests/unit/test_digest_gated_revision.py` | 16 | — |
| `apps/control-plane/tests/unit/test_dispatcher_backpressure.py` | 11 | — |
| `apps/control-plane/tests/unit/test_donor_patterns.py` | 9 | — |
| `apps/control-plane/tests/unit/test_dossier_store.py` | 9 | — |
| `apps/control-plane/tests/unit/test_enrichment_service.py` | 11 | — |
| `apps/control-plane/tests/unit/test_entity_stream_persistence.py` | 6 | — |
| `apps/control-plane/tests/unit/test_fabric_anchor_guard.py` | 7 | — |
| `apps/control-plane/tests/unit/test_fabric_endpoints.py` | 15 | — |
| `apps/control-plane/tests/unit/test_invariant_reducer.py` | 34 | — |
| `apps/control-plane/tests/unit/test_migration_016_forward_only.py` | 14 | — |
| `apps/control-plane/tests/unit/test_migration_017_forward_only.py` | 17 | — |
| `apps/control-plane/tests/unit/test_migration_020_universal_relation.py` | 16 | — |
| `apps/control-plane/tests/unit/test_migration_024_investigation_entity_membership.py` | 9 | — |
| `apps/control-plane/tests/unit/test_migration_forward_only.py` | 5 | — |
| `apps/control-plane/tests/unit/test_modifier_mismatch.py` | 9 | — |
| `apps/control-plane/tests/unit/test_monitor.py` | 11 | — |
| `apps/control-plane/tests/unit/test_network_analytics.py` | 10 | — |
| `apps/control-plane/tests/unit/test_ontology_registry.py` | 9 | — |
| `apps/control-plane/tests/unit/test_postgres_context_store.py` | 7 | — |
| `apps/control-plane/tests/unit/test_producer_binding_golden_path.py` | 4 | — |
| `apps/control-plane/tests/unit/test_query_degradation.py` | 17 | — |
| `apps/control-plane/tests/unit/test_query_fusion.py` | 11 | — |
| `apps/control-plane/tests/unit/test_rank_fusion_wiring.py` | 14 | — |
| `apps/control-plane/tests/unit/test_reobservation.py` | 9 | — |
| `apps/control-plane/tests/unit/test_science_tda.py` | 5 | — |
| `apps/control-plane/tests/unit/test_search_core_selection.py` | 4 | — |
| `apps/control-plane/tests/unit/test_search_fusion_api.py` | 5 | — |
| `apps/control-plane/tests/unit/test_series_lifecycle.py` | 10 | — |
| `apps/control-plane/tests/unit/test_source_query_store.py` | 7 | — |
| `apps/control-plane/tests/unit/test_sse_stream.py` | 8 | — |
| `apps/control-plane/tests/unit/test_temporal_materialization_persistence.py` | 9 | — |
| `apps/control-plane/tests/unit/test_temporal_port.py` | 7 | — |
| `apps/control-plane/tests/unit/test_tool_catalog.py` | 8 | — |
| `apps/control-plane/tests/unit/test_us1_core.py` | 15 | — |
| `apps/control-plane/tests/unit/test_us3_ops.py` | 7 | — |
| `apps/control-plane/tests/unit/test_workflows.py` | 16 | — |
| `apps/feedback/tests/test_branches.py` | 10 | — |
| `apps/feedback/tests/test_feedback.py` | 8 | — |
| `apps/feedback/tests/test_frontier_loop.py` | 2 | — |
| `apps/interpretation/tests/conftest.py` | 0 | — |
| `apps/interpretation/tests/contract/__init__.py` | 0 | — |
| `apps/interpretation/tests/contract/test_dictionary_entities.py` | 7 | — |
| `apps/interpretation/tests/contract/test_documents.py` | 6 | — |
| `apps/interpretation/tests/contract/test_lang_parity.py` | 9 | — |
| `apps/interpretation/tests/contract/test_normalize.py` | 11 | — |
| `apps/interpretation/tests/contract/test_parser_families.py` | 37 | — |
| `apps/interpretation/tests/contract/test_persons.py` | 6 | — |
| `apps/interpretation/tests/contract/test_span_semantics.py` | 16 | — |
| `apps/interpretation/tests/contract/test_to_entities_honesty.py` | 10 | — |
| `apps/interpretation/tests/integration/test_all_sources_parse.py` | 20 | — |
| `apps/interpretation/tests/test_deterministic_extraction.py` | 16 | — |
| `apps/interpretation/tests/test_evidence_manifest.py` | 14 | — |
| `apps/interpretation/tests/test_mention_binding_seam.py` | 16 | — |
| `apps/interpretation/tests/test_observation_consumer.py` | 20 | — |
| `apps/interpretation/tests/test_parser_adapter.py` | 17 | — |
| `apps/interpretation/tests/test_payload_binding.py` | 14 | — |
| `apps/interpretation/tests/test_payload_detection.py` | 15 | — |
| `apps/interpretation/tests/test_payload_hypotheses.py` | 35 | — |
| `apps/interpretation/tests/test_payload_parser_layer.py` | 28 | — |
| `apps/interpretation/tests/test_payload_routing.py` | 25 | — |
| `apps/interpretation/tests/test_payload_structure_producer.py` | 37 | — |
| `apps/interpretation/tests/test_pipeline.py` | 19 | — |
| `apps/interpretation/tests/test_primary_proc.py` | 93 | — |
| `apps/interpretation/tests/test_primary_proc_regex_mutant.py` | 10 | — |
| `apps/interpretation/tests/test_producer_migration.py` | 23 | — |
| `apps/interpretation/tests/test_relation_cue_coverage.py` | 7 | — |
| `apps/interpretation/tests/test_relations.py` | 25 | — |
| `apps/interpretation/tests/test_retriever_fusion.py` | 8 | — |
| `apps/interpretation/tests/test_search_retriever.py` | 7 | — |
| `apps/interpretation/tests/test_signal_kind_channels.py` | 11 | — |
| `apps/interpretation/tests/test_signal_nary_contract.py` | 32 | — |
| `apps/interpretation/tests/test_syntactic_producer.py` | 58 | — |
| `apps/interpretation/tests/test_warc_reader.py` | 44 | — |
| `apps/projection/tests/contract/test_search_projection_manifest.py` | 9 | — |
| `apps/projection/tests/contract/test_tda_bridge_contract.py` | 30 | — |
| `apps/projection/tests/test_bm25s_backend.py` | 9 | — |
| `apps/projection/tests/test_lakehouse.py` | 8 | — |
| `apps/projection/tests/test_metrics.py` | 21 | — |
| `apps/projection/tests/test_projection.py` | 17 | — |
| `apps/projection/tests/test_relevance.py` | 15 | — |
| `apps/projection/tests/test_streams.py` | 7 | — |
| `apps/projection/tests/test_tantivy_backend.py` | 7 | — |
| `apps/projection/tests/unit/test_diagram.py` | 6 | — |
| `apps/projection/tests/unit/test_features.py` | 21 | — |
| `apps/projection/tests/unit/test_graph_store_direction.py` | 28 | — |
| `apps/projection/tests/unit/test_h3_spatial.py` | 21 | — |
| `apps/projection/tests/unit/test_neo4j_relation_write.py` | 13 | — |
| `apps/projection/tests/unit/test_pipeline_directed.py` | 9 | — |
| `apps/projection/tests/unit/test_relation_store.py` | 18 | — |
| `apps/projection/tests/unit/test_takens.py` | 5 | — |
| `apps/projection/tests/unit/test_tda_insight.py` | 14 | — |
| `apps/projection/tests/unit/test_tda_pipeline_performance.py` | 16 | — |
| `apps/projection/tests/unit/test_temporal_features.py` | 3 | — |
| `apps/projection/tests/unit/test_temporal_graph.py` | 28 | — |
| `apps/projection/tests/unit/test_topological_invariant.py` | 4 | — |
| `apps/projection/tests/unit/test_validated.py` | 5 | — |
| `apps/science/context/tests/test_epistemic_algebra.py` | 69 | — |
| `apps/science/tests/contract/test_argumentation_contract.py` | 26 | — |
| `apps/science/tests/contract/test_causal_contract.py` | 5 | — |
| `apps/science/tests/contract/test_circularity_contract.py` | 46 | — |
| `apps/science/tests/contract/test_claim_contract.py` | 7 | — |
| `apps/science/tests/contract/test_completeness_contract.py` | 37 | — |
| `apps/science/tests/contract/test_coverage_independence_contract.py` | 44 | — |
| `apps/science/tests/contract/test_dialectics_contract.py` | 45 | — |
| `apps/science/tests/contract/test_discipline_adapters_contract.py` | 34 | — |
| `apps/science/tests/contract/test_dossier_contract.py` | 46 | — |
| `apps/science/tests/contract/test_enrichment_contract.py` | 34 | — |
| `apps/science/tests/contract/test_epistemic_contract.py` | 60 | — |
| `apps/science/tests/contract/test_event_emission_contract.py` | 7 | — |
| `apps/science/tests/contract/test_gluing_contract.py` | 34 | — |
| `apps/science/tests/contract/test_growth_contract.py` | 25 | — |
| `apps/science/tests/contract/test_hierarchy_contract.py` | 65 | — |
| `apps/science/tests/contract/test_hypothesis_contract.py` | 8 | — |
| `apps/science/tests/contract/test_locality_contract.py` | 43 | — |
| `apps/science/tests/contract/test_ontology_and_schema_stay_in_step.py` | 7 | — |
| `apps/science/tests/contract/test_operator_registry_contract.py` | 27 | — |
| `apps/science/tests/contract/test_operator_result_bridge.py` | 10 | — |
| `apps/science/tests/contract/test_query_compiler_contract.py` | 46 | — |
| `apps/science/tests/contract/test_review_contract.py` | 6 | — |
| `apps/science/tests/contract/test_robustness_contract.py` | 7 | — |
| `apps/science/tests/contract/test_science_seam_contract.py` | 29 | — |
| `apps/science/tests/contract/test_scope_lattice_contract.py` | 30 | — |
| `apps/science/tests/contract/test_structure_contract.py` | 6 | — |
| `apps/science/tests/contract/test_temporal_contract.py` | 4 | — |
| `apps/science/tests/contract/test_temporal_filter.py` | 13 | — |
| `apps/science/tests/contract/test_worldline_view_contract.py` | 21 | — |
| `apps/science/tests/integration/test_context_engine_chain.py` | 8 | — |
| `apps/science/tests/integration/test_live_asg_pipeline.py` | 13 | — |
| `apps/science/tests/integration/test_live_scope_lattice.py` | 10 | — |
| `apps/science/tests/test_anchoring.py` | 21 | — |
| `apps/science/tests/unit/__init__.py` | 0 | — |
| `apps/science/tests/unit/test_calibration.py` | 4 | — |
| `apps/science/tests/unit/test_changedetect.py` | 3 | — |
| `apps/science/tests/unit/test_econ.py` | 11 | — |
| `apps/science/tests/unit/test_gain.py` | 3 | — |
| `apps/science/tests/unit/test_gnca.py` | 7 | — |
| `apps/science/tests/unit/test_kinetics.py` | 10 | — |
| `apps/science/tests/unit/test_ladder.py` | 4 | — |
| `apps/science/tests/unit/test_landscape.py` | 7 | — |
| `apps/science/tests/unit/test_phase.py` | 19 | — |
| `apps/science/tests/unit/test_reproduction.py` | 9 | — |
| `apps/science/tests/unit/test_river_drift.py` | 25 | — |
| `apps/science/tests/unit/test_schelling.py` | 5 | — |
| `apps/science/tests/unit/test_scope.py` | 4 | — |
| `apps/science/tests/unit/test_series_embedding.py` | 7 | — |
| `apps/science/tests/unit/test_structure.py` | 7 | — |
| `apps/science/tests/unit/test_tda.py` | 19 | — |
| `apps/shared/tests/constitution/__init__.py` | 0 | — |
| `apps/shared/tests/constitution/test_constitution4_no_fabrication.py` | 16 | — |
| `apps/shared/tests/constitution/test_constitution_has_teeth.py` | 2 | — |
| `apps/shared/tests/constitution/test_i1_i3_immutability_and_preservation.py` | 9 | — |
| `apps/shared/tests/constitution/test_identity_subsystem_constitution.py` | 14 | — |
| `apps/shared/tests/constitution/test_iv_vi_tenancy_and_determinism.py` | 9 | — |
| `apps/shared/tests/contract/__init__.py` | 0 | — |
| `apps/shared/tests/contract/test_correlation.py` | 4 | — |
| `apps/shared/tests/contract/test_domain_invariants.py` | 12 | — |
| `apps/shared/tests/contract/test_donor_registry.py` | 27 | — |
| `apps/shared/tests/contract/test_entity_fabric.py` | 46 | — |
| `apps/shared/tests/contract/test_error_codes.py` | 54 | — |
| `apps/shared/tests/contract/test_event_envelope.py` | 11 | — |
| `apps/shared/tests/contract/test_evidence_span.py` | 52 | — |
| `apps/shared/tests/contract/test_evidence_span_roundtrip.py` | 8 | — |
| `apps/shared/tests/contract/test_metrics.py` | 6 | — |
| `apps/shared/tests/contract/test_ontology.py` | 4 | — |
| `apps/shared/tests/contract/test_operator_result.py` | 51 | — |
| `apps/shared/tests/contract/test_platform_model.py` | 15 | `platform_model` |
| `apps/shared/tests/contract/test_projection_manifest.py` | 24 | — |
| `apps/shared/tests/contract/test_review.py` | 4 | — |
| `apps/shared/tests/contract/test_single_publication_path.py` | 9 | — |
| `apps/shared/tests/contract/test_stage_outcome.py` | 52 | — |
| `apps/shared/tests/contract/test_statement.py` | 3 | — |
| `apps/shared/tests/contract/test_storage.py` | 6 | — |
| `apps/shared/tests/integration/__init__.py` | 0 | — |
| `apps/shared/tests/integration/test_idempotency.py` | 3 | — |
| `apps/shared/tests/integration/test_infra_connectivity.py` | 6 | — |
| `apps/shared/tests/integration/test_redpanda_emission.py` | 1 | — |
| `apps/shared/tests/unit/domain/test_domain_model.py` | 7 | — |
| `apps/shared/tests/unit/domain/test_graph_invariant.py` | 23 | — |
| `apps/shared/tests/unit/domain/test_temporal_materialization.py` | 9 | — |
| `apps/shared/tests/unit/domain/test_temporal_worldline.py` | 23 | — |
| `apps/shared/tests/unit/domain/test_temporal_worldline_store.py` | 11 | — |
| `apps/shared/tests/unit/donor/conftest.py` | 0 | — |
| `apps/shared/tests/unit/donor/test_correlation_graph.py` | 13 | — |
| `apps/shared/tests/unit/donor/test_evidence.py` | 7 | — |
| `apps/shared/tests/unit/donor/test_statement.py` | 14 | — |
| `apps/shared/tests/unit/donor/test_target.py` | 18 | — |
| `apps/shared/tests/unit/donor/test_temporal.py` | 14 | — |
| `apps/shared/tests/unit/events/test_temporal_materialization_events.py` | 1 | — |
| `apps/shared/tests/unit/scoring/test_adaptive_state.py` | 10 | — |
| `apps/shared/tests/unit/test_access_mode.py` | 15 | — |
| `apps/shared/tests/unit/test_acquisition_path.py` | 14 | — |
| `apps/shared/tests/unit/test_candidate_logical_identity.py` | 29 | — |
| `apps/shared/tests/unit/test_cc_session.py` | 4 | — |
| `apps/shared/tests/unit/test_cd6_unresolved_predicate.py` | 17 | — |
| `apps/shared/tests/unit/test_co_mention.py` | 4 | — |
| `apps/shared/tests/unit/test_commoncrawl.py` | 7 | — |
| `apps/shared/tests/unit/test_derivation_identity.py` | 32 | — |
| `apps/shared/tests/unit/test_dlq_durable.py` | 9 | — |
| `apps/shared/tests/unit/test_event_timestamps.py` | 11 | — |
| `apps/shared/tests/unit/test_evidence_context.py` | 27 | — |
| `apps/shared/tests/unit/test_evidence_lineage.py` | 16 | — |
| `apps/shared/tests/unit/test_evidence_store_guard.py` | 10 | — |
| `apps/shared/tests/unit/test_fusion.py` | 26 | — |
| `apps/shared/tests/unit/test_idempotent_consumer.py` | 8 | — |
| `apps/shared/tests/unit/test_ids.py` | 8 | — |
| `apps/shared/tests/unit/test_investigation_context.py` | 37 | — |
| `apps/shared/tests/unit/test_layer_boundaries.py` | 9 | — |
| `apps/shared/tests/unit/test_measured_values.py` | 19 | — |
| `apps/shared/tests/unit/test_mention_occurrence_index.py` | 20 | — |
| `apps/shared/tests/unit/test_observation_gate_identity.py` | 20 | — |
| `apps/shared/tests/unit/test_observation_identity.py` | 29 | — |
| `apps/shared/tests/unit/test_open_world_predicates.py` | 27 | — |
| `apps/shared/tests/unit/test_participant_end_kind.py` | 5 | — |
| `apps/shared/tests/unit/test_predicate_signature.py` | 77 | — |
| `apps/shared/tests/unit/test_range_pull.py` | 5 | — |
| `apps/shared/tests/unit/test_relation_claim.py` | 16 | — |
| `apps/shared/tests/unit/test_relation_identity.py` | 24 | — |
| `apps/shared/tests/unit/test_relation_schema.py` | 27 | — |
| `apps/shared/tests/unit/test_research_lineage.py` | 19 | — |
| `apps/shared/tests/unit/test_resolution_mention_span.py` | 13 | — |
| `apps/shared/tests/unit/test_schema_hierarchy.py` | 20 | — |
| `apps/shared/tests/unit/test_secure_fetch.py` | 16 | — |
| `apps/shared/tests/unit/test_security.py` | 19 | — |
| `apps/shared/tests/unit/test_temporal_metrics.py` | 9 | — |
| `apps/shared/tests/unit/websearch/test_websearch.py` | 23 | — |
| `apps/specops/tests/conftest.py` | 0 | — |
| `apps/specops/tests/test_engagement.py` | 26 | — |
| `apps/specops/tests/test_ghostline.py` | 36 | — |
| `apps/specops/tests/test_roe_gate.py` | 11 | — |
| `apps/specops/tests/test_specops_ghostline_routers.py` | 26 | — |
| `apps/specops/tests/test_specops_routers.py` | 10 | — |
| `apps/zero/tests/conftest.py` | 0 | — |
| `apps/zero/tests/test_cc_capture.py` | 14 | — |
| `apps/zero/tests/test_enrichment.py` | 24 | — |
| `apps/zero/tests/test_harvest_wave.py` | 15 | — |
| `apps/zero/tests/test_harvesters.py` | 25 | — |
| `apps/zero/tests/test_resolution.py` | 23 | — |
| `apps/zero/tests/test_type_detector.py` | 22 | — |
| `bench/tests/test_harness.py` | 10 | — |
| `bench/tests/test_knowledge.py` | 10 | — |
| `bench/tests/test_scale_scale.py` | 3 | — |
| `implementation/tests/test_contract_files.py` | 4 | — |
| `implementation/tests/test_person_case_lark.py` | 2 | — |
| `specs/021-entity-relation-extraction-finalization/repair/tools/test_reference_check.py` | 200 | — |

## Untested platform modules (sample)

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
| `apps/acquisition/adapters/browsertrix/__init__.py` |
| `apps/acquisition/adapters/browsertrix/collect.py` |
| `apps/acquisition/adapters/common_crawl.py` |
| `apps/acquisition/adapters/commoncrawl/__init__.py` |
| `apps/acquisition/adapters/commoncrawl/index.py` |
| `apps/acquisition/adapters/discovery/__init__.py` |
| `apps/acquisition/adapters/discovery/commoncrawl_index.py` |
| `apps/acquisition/adapters/discovery/contracts.py` |
| `apps/acquisition/adapters/discovery/crtsh.py` |
| `apps/acquisition/adapters/discovery/linkgraph.py` |
| `apps/acquisition/adapters/discovery/registry.py` |
| `apps/acquisition/adapters/discovery/wayback_cdx.py` |
| `apps/acquisition/adapters/heritrix/__init__.py` |
| `apps/acquisition/adapters/heritrix/collect.py` |
| `apps/acquisition/adapters/nutch/__init__.py` |
| `apps/acquisition/adapters/nutch/collect.py` |
| `apps/acquisition/adapters/registry.py` |
| `apps/acquisition/adapters/scrapy/__init__.py` |
| `apps/acquisition/adapters/scrapy/spider.py` |
| `apps/acquisition/adapters/scrapy/stream.py` |
| `apps/acquisition/adapters/sec_edgar.py` |
| `apps/acquisition/adapters/stormcrawler/__init__.py` |
| `apps/acquisition/adapters/stormcrawler/collect.py` |
| `apps/acquisition/adapters/warc/__init__.py` |
| `apps/acquisition/adapters/warc/collect.py` |
| `apps/acquisition/artifact_sink.py` |
| `apps/acquisition/cc_extract.py` |
| `apps/acquisition/cc_plan.py` |
| `apps/acquisition/dispatcher/__init__.py` |
| `apps/acquisition/dispatcher/kafka_producer.py` |
| `apps/acquisition/dispatcher/plan_driver.py` |
| `apps/acquisition/dispatcher/regional.py` |
| `apps/acquisition/dispatcher/scheduler.py` |
| `apps/acquisition/entity_search.py` |
| `apps/acquisition/observation_gate/__init__.py` |
| `apps/acquisition/observation_gate/replay.py` |
| `apps/acquisition/registry.py` |
| `apps/acquisition/runtime/__init__.py` |
| `apps/acquisition/runtime/airbyte.py` |
| `apps/acquisition/runtime/bbot.py` |
| `apps/acquisition/runtime/external_tool.py` |
| `apps/acquisition/runtime/primproc.py` |
| `apps/acquisition/runtime/record_stream.py` |
| `apps/acquisition/runtime/searxng.py` |
| `apps/acquisition/source_query_set.py` |
| `apps/acquisition/sources/__init__.py` |
| `apps/acquisition/sources/append_parse_blocks.py` |
| `apps/acquisition/sources/capabilities.py` |
| `apps/acquisition/sources/catalogue.py` |
| `apps/acquisition/sources/connector.py` |
| `apps/acquisition/sources/executor.py` |
