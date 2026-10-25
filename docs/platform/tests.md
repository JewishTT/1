# Tests

322 test files, 5181 test functions. 268 platform modules are not targeted by any test.

`Targets` is resolved through the platform's own import roots, so a test that imports a package by its bare name resolves to the module it exercises. A target is reachability, not behavioural coverage.

## Test files

| File | Tests | Targets |
|---|---|---|
| `apps/acquisition/tests/contract/test_plan_driver.py` | 20 | `apps/acquisition/adapters/registry.py`, `apps/acquisition/dispatcher/plan_driver.py`, `apps/acquisition/dispatcher/scheduler.py`, `apps/acquisition/sources/connector.py` |
| `apps/acquisition/tests/contract/test_scheduler.py` | 11 | `apps/acquisition/adapters/registry.py`, `apps/acquisition/dispatcher/scheduler.py` |
| `apps/acquisition/tests/integration/test_adapters_gate.py` | 5 | `apps/acquisition/adapters/commoncrawl/index.py`, `apps/acquisition/adapters/scrapy/stream.py`, `apps/acquisition/adapters/warc/collect.py`, `apps/shared/events/content_router.py` |
| `apps/acquisition/tests/integration/test_backpressure.py` | 6 | `apps/control-plane/services/throttle.py` |
| `apps/acquisition/tests/integration/test_engine_adapters_gate.py` | 5 | `apps/acquisition/adapters/browsertrix/collect.py`, `apps/acquisition/adapters/heritrix/collect.py`, `apps/acquisition/adapters/nutch/collect.py`, `apps/acquisition/adapters/stormcrawler/collect.py` |
| `apps/acquisition/tests/integration/test_live_loop.py` | 4 | `apps/acquisition/adapters/registry.py`, `apps/acquisition/dispatcher/kafka_producer.py`, `apps/acquisition/dispatcher/plan_driver.py`, `apps/acquisition/dispatcher/scheduler.py` |
| `apps/acquisition/tests/integration/test_loop_closed.py` | 2 | `apps/acquisition/adapters/registry.py`, `apps/acquisition/dispatcher/plan_driver.py`, `apps/acquisition/dispatcher/scheduler.py`, `apps/acquisition/sources/catalogue.py` |
| `apps/acquisition/tests/integration/test_worker.py` | 5 | `apps/control-plane/services/source_registry.py` |
| `apps/acquisition/tests/test_connector_registry.py` | 13 | `apps/acquisition/registry.py` |
| `apps/acquisition/tests/unit/test_acquisition_artifact_sink.py` | 39 | `apps/acquisition/artifact_sink.py`, `apps/shared/domain/acquisition_artifact.py`, `apps/shared/domain/capture.py`, `apps/shared/domain/observation_identity.py` |
| `apps/acquisition/tests/unit/test_acquisition_worker.py` | 31 | `apps/acquisition/sources/catalogue.py`, `apps/acquisition/sources/connector.py`, `apps/acquisition/sources/executor.py`, `apps/acquisition/worker_acquisition.py` |
| `apps/acquisition/tests/unit/test_adapter_onboarding.py` | 3 | `apps/acquisition/adapters/commoncrawl/__init__.py`, `apps/acquisition/adapters/commoncrawl/index.py`, `apps/acquisition/adapters/registry.py`, `apps/acquisition/adapters/scrapy/__init__.py` |
| `apps/acquisition/tests/unit/test_airbyte_runtime.py` | 28 | `apps/acquisition/runtime/__init__.py`, `apps/acquisition/runtime/airbyte.py`, `apps/shared/domain/acquisition_artifact.py` |
| `apps/acquisition/tests/unit/test_archival_worker.py` | 8 | `apps/acquisition/worker_http/archival.py` |
| `apps/acquisition/tests/unit/test_bbot_process_boundary.py` | 15 | `apps/acquisition/runtime/bbot.py` |
| `apps/acquisition/tests/unit/test_bbot_runtime.py` | 25 | `apps/acquisition/runtime/__init__.py`, `apps/acquisition/runtime/bbot.py`, `apps/acquisition/runtime/record_stream.py` |
| `apps/acquisition/tests/unit/test_browser_fabric.py` | 8 | `apps/acquisition/worker_browser/fabric.py` |
| `apps/acquisition/tests/unit/test_cc_extract.py` | 10 | `apps/acquisition/cc_extract.py` |
| `apps/acquisition/tests/unit/test_cc_index.py` | 3 | `apps/acquisition/adapters/commoncrawl/index.py` |
| `apps/acquisition/tests/unit/test_cc_plan.py` | 12 | `apps/acquisition/cc_plan.py` |
| `apps/acquisition/tests/unit/test_engine_adapters.py` | 6 | `apps/acquisition/adapters/browsertrix/__init__.py`, `apps/acquisition/adapters/browsertrix/collect.py`, `apps/acquisition/adapters/heritrix/__init__.py`, `apps/acquisition/adapters/heritrix/collect.py` |
| `apps/acquisition/tests/unit/test_entity_search.py` | 4 | `apps/acquisition/entity_search.py` |
| `apps/acquisition/tests/unit/test_primproc_runtime.py` | 32 | `apps/acquisition/runtime/__init__.py`, `apps/acquisition/runtime/primproc.py`, `apps/shared/domain/acquisition_artifact.py` |
| `apps/acquisition/tests/unit/test_region_backpressure.py` | 7 | `apps/acquisition/dispatcher/regional.py` |
| `apps/acquisition/tests/unit/test_render_pipeline.py` | 6 | `apps/acquisition/worker_browser/renderer.py` |
| `apps/acquisition/tests/unit/test_replay_journal.py` | 5 | `apps/acquisition/observation_gate/replay.py` |
| `apps/acquisition/tests/unit/test_source_catalogue_full.py` | 15 | `apps/acquisition/sources/catalogue.py`, `apps/acquisition/sources/executor.py` |
| `apps/acquisition/tests/unit/test_source_query_set.py` | 12 | `apps/acquisition/cc_plan.py`, `apps/acquisition/entity_search.py`, `apps/acquisition/source_query_set.py` |
| `apps/acquisition/tests/unit/test_warc_adapter.py` | 3 | `apps/acquisition/adapters/warc/collect.py` |
| `apps/admission/tests/contract/test_no_auto_merge.py` | 25 | `apps/admission/engine/admission.py`, `apps/admission/engine/calibration.py`, `apps/admission/resolution/blocking.py`, `apps/admission/resolution/candidate.py` |
| `apps/admission/tests/contract/test_resolution_history.py` | 35 | `apps/admission/engine/calibration.py`, `apps/admission/engine/intake.py`, `apps/admission/resolution/decision_store.py`, `apps/admission/resolution/gate.py` |
| `apps/admission/tests/test_admission.py` | 22 | `apps/admission/engine/admission.py`, `apps/admission/engine/assertions.py`, `apps/admission/engine/calibration.py`, `apps/admission/engine/temporal.py` |
| `apps/admission/tests/test_candidate.py` | 14 | `apps/admission/resolution/candidate.py`, `apps/admission/resolution/collective.py` |
| `apps/admission/tests/test_claims.py` | 15 | `apps/admission/engine/assertions.py`, `apps/admission/engine/storyline.py`, `apps/admission/independence/independence.py`, `apps/admission/resolution/collective.py` |
| `apps/admission/tests/test_collective_export.py` | 4 | `apps/admission/resolution/collective.py`, `apps/admission/resolution/resolver.py` |
| `apps/admission/tests/test_effective_independence.py` | 11 | `apps/admission/engine/admission.py`, `apps/admission/engine/calibration.py`, `apps/admission/engine/intake.py` |
| `apps/admission/tests/test_intake.py` | 38 | `apps/admission/engine/admission.py`, `apps/admission/engine/assertions.py`, `apps/admission/engine/calibration.py`, `apps/admission/engine/intake.py` |
| `apps/admission/tests/test_statement_consumer.py` | 5 | `apps/admission/engine/assertions.py`, `apps/shared/domain/__init__.py`, `apps/shared/domain/statement.py` |
| `apps/admission/tests/unit/test_cluster_transitivity.py` | 13 | `apps/admission/resolution/cluster.py`, `apps/admission/resolution/decision_store.py`, `apps/admission/resolution/gate.py`, `apps/admission/resolution/span.py` |
| `apps/admission/tests/unit/test_splink_adapter.py` | 20 | `apps/admission/resolution/candidate.py`, `apps/admission/resolution/splink_adapter.py` |
| `apps/bulk-ingestion/tests/contract/test_archive_live_convergence.py` | 2 | `apps/acquisition/adapters/scrapy/stream.py`, `apps/acquisition/adapters/warc/collect.py`, `apps/shared/events/content_router.py`, `apps/shared/events/observation_gate.py` |
| `apps/bulk-ingestion/tests/unit/test_backfill.py` | 5 | `apps/shared/network/commoncrawl.py` |
| `apps/bulk-ingestion/tests/unit/test_historical_replay.py` | 5 | `apps/shared/network/commoncrawl.py` |
| `apps/control-plane/tests/contract/test_context_graph_contract.py` | 21 | `apps/control-plane/context_engine/context_graph.py` |
| `apps/control-plane/tests/integration/__init__.py` | 0 | — |
| `apps/control-plane/tests/integration/test_cc_temporality_api.py` | 3 | `apps/control-plane/api/main.py`, `apps/control-plane/services/cc_temporality.py`, `apps/zero/zero/cc_capture.py` |
| `apps/control-plane/tests/integration/test_closed_research_loop.py` | 13 | `apps/control-plane/context_engine/engine.py`, `apps/control-plane/context_engine/loop.py`, `apps/control-plane/context_engine/obligations.py`, `apps/control-plane/context_engine/store.py` |
| `apps/control-plane/tests/integration/test_donor_api.py` | 11 | `apps/control-plane/api/main.py` |
| `apps/control-plane/tests/integration/test_end_to_end_pipeline.py` | 2 | `apps/control-plane/db/session.py`, `apps/control-plane/services/acquisition_loop.py`, `apps/control-plane/services/frontier.py`, `apps/shared/events/content_router.py` |
| `apps/control-plane/tests/integration/test_entity_investigation_membership.py` | 9 | `apps/control-plane/api/main.py`, `apps/control-plane/api/routes/__init__.py`, `apps/control-plane/db/schema.py`, `apps/control-plane/db/session.py` |
| `apps/control-plane/tests/integration/test_epistemic_roundtrip.py` | 31 | `apps/science/context/completeness.py`, `apps/science/context/coverage.py`, `apps/science/context/epistemic.py`, `apps/shared/contracts/error_codes.py` |
| `apps/control-plane/tests/integration/test_finding_evidence_chain.py` | 7 | `apps/control-plane/api/main.py`, `apps/control-plane/api/routes/findings.py`, `apps/control-plane/services/catalog.py` |
| `apps/control-plane/tests/integration/test_frontier_provenance.py` | 40 | `apps/acquisition/adapters/discovery/__init__.py`, `apps/acquisition/adapters/discovery/registry.py`, `apps/control-plane/db/schema.py`, `apps/control-plane/services/discovery_frontier.py` |
| `apps/control-plane/tests/integration/test_investigation_temporal.py` | 12 | `apps/control-plane/workflows/__init__.py`, `apps/control-plane/workflows/investigation.py`, `apps/control-plane/workflows/investigation_activities.py`, `apps/control-plane/workflows/temporal_materialization.py` |
| `apps/control-plane/tests/integration/test_layer0_direct_pipeline.py` | 4 | `apps/control-plane/services/acquisition_loop.py`, `apps/control-plane/services/frontier.py`, `apps/control-plane/services/layer0_pipeline.py`, `apps/interpretation/pipeline.py` |
| `apps/control-plane/tests/integration/test_lineage_api.py` | 4 | `apps/control-plane/services/catalog.py` |
| `apps/control-plane/tests/integration/test_loop_closure.py` | 43 | `apps/control-plane/context_engine/engine.py`, `apps/control-plane/context_engine/loop.py`, `apps/control-plane/context_engine/obligations.py`, `apps/control-plane/context_engine/store.py` |
| `apps/control-plane/tests/integration/test_observation_changes_next_action.py` | 9 | `apps/control-plane/context_engine/engine.py`, `apps/control-plane/context_engine/invariant_reducer.py`, `apps/control-plane/context_engine/loop.py`, `apps/control-plane/context_engine/obligations.py` |
| `apps/control-plane/tests/integration/test_observation_immutability.py` | 5 | — |
| `apps/control-plane/tests/integration/test_orm_migration_parity.py` | 1 | `apps/control-plane/db/schema.py`, `apps/shared/config/settings.py` |
| `apps/control-plane/tests/integration/test_platform_assembly.py` | 31 | `apps/control-plane/composition.py`, `apps/control-plane/services/cycle_service.py`, `apps/science/context/query_ast.py` |
| `apps/control-plane/tests/integration/test_quarantine.py` | 6 | `apps/shared/events/dlq.py` |
| `apps/control-plane/tests/integration/test_query_planner.py` | 5 | `apps/control-plane/services/query_planner.py` |
| `apps/control-plane/tests/integration/test_resolution_api.py` | 4 | `apps/control-plane/api/main.py` |
| `apps/control-plane/tests/integration/test_science_api.py` | 4 | `apps/control-plane/api/main.py`, `apps/science/claims/registry.py` |
| `apps/control-plane/tests/integration/test_seed_security.py` | 2 | `apps/control-plane/api/main.py` |
| `apps/control-plane/tests/integration/test_temporal_materialization_api.py` | 3 | `apps/control-plane/api/routes/entities.py`, `apps/control-plane/api/routes/temporal_materializations.py` |
| `apps/control-plane/tests/integration/test_tenancy.py` | 6 | `apps/shared/isolation.py` |
| `apps/control-plane/tests/integration/test_tools_api.py` | 8 | `apps/control-plane/api/main.py` |
| `apps/control-plane/tests/unit/test_action_memory.py` | 19 | `apps/control-plane/context_engine/engine.py`, `apps/control-plane/context_engine/obligations.py`, `apps/control-plane/context_engine/store.py`, `apps/shared/contracts/stage_outcome.py` |
| `apps/control-plane/tests/unit/test_approval_gate.py` | 7 | `apps/control-plane/context_engine/engine.py`, `apps/control-plane/context_engine/loop.py`, `apps/control-plane/context_engine/store.py`, `apps/shared/domain/investigation_context.py` |
| `apps/control-plane/tests/unit/test_assembly_structural_conflict.py` | 24 | `apps/control-plane/semantic_path/__init__.py`, `apps/control-plane/semantic_path/assembly.py`, `apps/interpretation/extractors/signals/__init__.py`, `apps/interpretation/extractors/signals/protocol.py` |
| `apps/control-plane/tests/unit/test_badges_facade.py` | 8 | `apps/control-plane/badges/__init__.py` |
| `apps/control-plane/tests/unit/test_cc_temporality.py` | 7 | `apps/control-plane/api/sse.py`, `apps/control-plane/services/cc_temporality.py`, `apps/shared/network/cc_session.py` |
| `apps/control-plane/tests/unit/test_cognitive_loop.py` | 18 | `apps/control-plane/context_engine/engine.py`, `apps/control-plane/context_engine/loop.py`, `apps/control-plane/context_engine/obligations.py`, `apps/control-plane/context_engine/store.py` |
| `apps/control-plane/tests/unit/test_context_engine.py` | 45 | `apps/control-plane/context_engine/engine.py`, `apps/control-plane/context_engine/obligations.py`, `apps/control-plane/context_engine/store.py`, `apps/shared/domain/investigation_context.py` |
| `apps/control-plane/tests/unit/test_context_termination_and_catalogue.py` | 30 | `apps/control-plane/context_engine/catalogue_bridge.py`, `apps/control-plane/context_engine/engine.py`, `apps/control-plane/context_engine/obligations.py`, `apps/control-plane/context_engine/store.py` |
| `apps/control-plane/tests/unit/test_digest_gated_revision.py` | 16 | `apps/control-plane/context_engine/invariant_reducer.py`, `apps/shared/domain/dynamics.py` |
| `apps/control-plane/tests/unit/test_dispatcher_backpressure.py` | 11 | `apps/control-plane/services/dispatcher.py` |
| `apps/control-plane/tests/unit/test_donor_patterns.py` | 9 | `apps/control-plane/services/dispatcher.py`, `apps/control-plane/services/frontier.py`, `apps/control-plane/services/policy_service.py`, `apps/control-plane/services/review.py` |
| `apps/control-plane/tests/unit/test_dossier_store.py` | 9 | `apps/control-plane/context_engine/dossier_store.py`, `apps/science/context/enrichment.py` |
| `apps/control-plane/tests/unit/test_enrichment_service.py` | 11 | `apps/acquisition/sources/catalogue.py`, `apps/control-plane/context_engine/enrichment_service.py`, `apps/interpretation/parsers/families.py` |
| `apps/control-plane/tests/unit/test_entity_stream_persistence.py` | 6 | `apps/control-plane/db/entity_stream.py`, `apps/control-plane/db/schema.py`, `apps/shared/domain/dynamics.py` |
| `apps/control-plane/tests/unit/test_fabric_anchor_guard.py` | 7 | `apps/control-plane/context_engine/__init__.py`, `apps/control-plane/context_engine/fabric_bridge.py`, `apps/science/context/fabric.py` |
| `apps/control-plane/tests/unit/test_fabric_endpoints.py` | 15 | `apps/control-plane/api/__init__.py`, `apps/control-plane/api/main.py` |
| `apps/control-plane/tests/unit/test_invariant_reducer.py` | 34 | `apps/control-plane/context_engine/invariant_reducer.py`, `apps/science/context/worldline.py`, `apps/shared/domain/dynamics.py`, `apps/shared/domain/graph_invariant.py` |
| `apps/control-plane/tests/unit/test_migration_016_forward_only.py` | 14 | `apps/control-plane/db/schema.py` |
| `apps/control-plane/tests/unit/test_migration_017_forward_only.py` | 17 | `apps/control-plane/db/schema.py`, `apps/shared/config/settings.py` |
| `apps/control-plane/tests/unit/test_migration_020_universal_relation.py` | 16 | `apps/control-plane/db/schema.py`, `apps/shared/domain/relation_candidate.py` |
| `apps/control-plane/tests/unit/test_migration_024_investigation_entity_membership.py` | 9 | `apps/control-plane/api/routes/entities.py`, `apps/control-plane/db/schema.py`, `apps/control-plane/db/session.py`, `apps/shared/config/settings.py` |
| `apps/control-plane/tests/unit/test_migration_forward_only.py` | 5 | — |
| `apps/control-plane/tests/unit/test_modifier_mismatch.py` | 9 | `apps/control-plane/modifier/__init__.py` |
| `apps/control-plane/tests/unit/test_monitor.py` | 11 | `apps/control-plane/cp_domain/investigation.py` |
| `apps/control-plane/tests/unit/test_network_analytics.py` | 10 | `apps/control-plane/api/main.py` |
| `apps/control-plane/tests/unit/test_ontology_registry.py` | 9 | `apps/shared/domain/ontology.py` |
| `apps/control-plane/tests/unit/test_postgres_context_store.py` | 7 | `apps/control-plane/context_engine/obligations.py`, `apps/control-plane/context_engine/postgres_store.py`, `apps/control-plane/context_engine/store.py`, `apps/shared/domain/investigation_context.py` |
| `apps/control-plane/tests/unit/test_producer_binding_golden_path.py` | 4 | `apps/control-plane/semantic_path/execution.py`, `apps/interpretation/extractors/signals/lexical.py`, `apps/interpretation/extractors/signals/metadata.py`, `apps/shared/domain/capture.py` |
| `apps/control-plane/tests/unit/test_query_degradation.py` | 17 | `apps/control-plane/services/query_planner.py` |
| `apps/control-plane/tests/unit/test_query_fusion.py` | 11 | `apps/control-plane/services/query_planner.py` |
| `apps/control-plane/tests/unit/test_rank_fusion_wiring.py` | 14 | `apps/control-plane/services/query_planner.py`, `apps/shared/scoring/fusion.py` |
| `apps/control-plane/tests/unit/test_reobservation.py` | 9 | `apps/control-plane/services/reobservation.py` |
| `apps/control-plane/tests/unit/test_science_tda.py` | 5 | `apps/control-plane/api/main.py` |
| `apps/control-plane/tests/unit/test_search_core_selection.py` | 4 | `apps/control-plane/services/search_backends.py` |
| `apps/control-plane/tests/unit/test_search_fusion_api.py` | 5 | `apps/control-plane/api/main.py`, `apps/control-plane/api/routes/__init__.py`, `apps/control-plane/services/query_planner.py` |
| `apps/control-plane/tests/unit/test_series_lifecycle.py` | 10 | `apps/control-plane/services/series_lifecycle.py` |
| `apps/control-plane/tests/unit/test_source_query_store.py` | 7 | `apps/acquisition/entity_search.py`, `apps/acquisition/source_query_set.py`, `apps/control-plane/db/schema.py`, `apps/control-plane/db/source_query_store.py` |
| `apps/control-plane/tests/unit/test_sse_stream.py` | 8 | `apps/control-plane/api/main.py`, `apps/control-plane/api/sse.py` |
| `apps/control-plane/tests/unit/test_temporal_materialization_persistence.py` | 9 | `apps/control-plane/db/materialization_cursor.py`, `apps/control-plane/db/schema.py`, `apps/control-plane/db/temporal_materialization.py`, `apps/shared/domain/dynamics.py` |
| `apps/control-plane/tests/unit/test_temporal_port.py` | 7 | `apps/control-plane/services/temporal_port.py` |
| `apps/control-plane/tests/unit/test_tool_catalog.py` | 8 | `apps/control-plane/services/tool_catalog.py` |
| `apps/control-plane/tests/unit/test_us1_core.py` | 15 | `apps/control-plane/cp_domain/investigation.py`, `apps/control-plane/cp_domain/policy.py`, `apps/control-plane/services/policy_service.py`, `apps/control-plane/services/source_registry.py` |
| `apps/control-plane/tests/unit/test_us3_ops.py` | 7 | `apps/control-plane/services/audit.py`, `apps/control-plane/services/worker_pools.py` |
| `apps/control-plane/tests/unit/test_workflows.py` | 16 | `apps/control-plane/services/__init__.py`, `apps/control-plane/workflows/__init__.py`, `apps/control-plane/workflows/investigation.py`, `apps/control-plane/workflows/temporal_materialization.py` |
| `apps/feedback/tests/test_branches.py` | 10 | `apps/shared/scoring/scorer.py` |
| `apps/feedback/tests/test_feedback.py` | 8 | — |
| `apps/feedback/tests/test_frontier_loop.py` | 2 | `apps/control-plane/db/schema.py`, `apps/control-plane/db/session.py`, `apps/control-plane/services/frontier.py`, `apps/shared/scoring/scorer.py` |
| `apps/interpretation/tests/conftest.py` | 0 | `apps/interpretation/dictionaries/build_mini.py` |
| `apps/interpretation/tests/contract/__init__.py` | 0 | — |
| `apps/interpretation/tests/contract/test_dictionary_entities.py` | 7 | `apps/interpretation/dictionaries/__init__.py`, `apps/interpretation/extractors/dictionary_entities.py`, `apps/interpretation/extractors/orgs.py`, `apps/interpretation/extractors/places.py` |
| `apps/interpretation/tests/contract/test_documents.py` | 6 | `apps/interpretation/extractors/lane.py` |
| `apps/interpretation/tests/contract/test_lang_parity.py` | 9 | `apps/interpretation/extractors/lane.py`, `apps/interpretation/extractors/language.py`, `apps/interpretation/extractors/translit.py` |
| `apps/interpretation/tests/contract/test_normalize.py` | 11 | `apps/interpretation/extractors/normalize.py`, `apps/interpretation/extractors/types.py` |
| `apps/interpretation/tests/contract/test_parser_families.py` | 37 | `apps/interpretation/parsers/families.py`, `apps/interpretation/parsers/paths.py` |
| `apps/interpretation/tests/contract/test_persons.py` | 6 | `apps/interpretation/extractors/persons.py`, `apps/interpretation/extractors/types.py` |
| `apps/interpretation/tests/contract/test_span_semantics.py` | 16 | `apps/interpretation/extractors/lane.py`, `apps/interpretation/extractors/types.py`, `apps/interpretation/parsers/html_full.py`, `apps/interpretation/parsers/registry.py` |
| `apps/interpretation/tests/contract/test_to_entities_honesty.py` | 10 | `apps/interpretation/parsers/families.py`, `apps/interpretation/parsers/to_entities.py` |
| `apps/interpretation/tests/integration/test_all_sources_parse.py` | 20 | `apps/acquisition/sources/catalogue.py`, `apps/acquisition/sources/connector.py`, `apps/interpretation/parsers/families.py`, `apps/shared/domain/ontology.py` |
| `apps/interpretation/tests/test_deterministic_extraction.py` | 16 | `apps/interpretation/dictionaries/__init__.py`, `apps/interpretation/dictionaries/build_mini.py`, `apps/interpretation/extractors/lane.py`, `apps/interpretation/extractors/language.py` |
| `apps/interpretation/tests/test_evidence_manifest.py` | 14 | `apps/interpretation/evidence/manifest.py` |
| `apps/interpretation/tests/test_mention_binding_seam.py` | 16 | `apps/interpretation/extractors/signals/__init__.py`, `apps/interpretation/extractors/signals/lexical.py`, `apps/interpretation/extractors/signals/links.py`, `apps/interpretation/extractors/signals/mentions.py` |
| `apps/interpretation/tests/test_observation_consumer.py` | 20 | `apps/interpretation/observation_consumer/__init__.py`, `apps/shared/events/__init__.py` |
| `apps/interpretation/tests/test_parser_adapter.py` | 17 | `apps/interpretation/parsers/registry.py` |
| `apps/interpretation/tests/test_payload_binding.py` | 14 | `apps/interpretation/parsers/payload/__init__.py`, `apps/shared/domain/mention_occurrence_index.py`, `apps/shared/domain/relation_participant.py` |
| `apps/interpretation/tests/test_payload_detection.py` | 15 | `apps/interpretation/parsers/payload/__init__.py` |
| `apps/interpretation/tests/test_payload_hypotheses.py` | 35 | `apps/interpretation/extractors/payload/hypotheses.py`, `apps/interpretation/extractors/payload/keytable.py`, `apps/interpretation/parsers/payload/__init__.py`, `apps/shared/semantic/blocking.py` |
| `apps/interpretation/tests/test_payload_parser_layer.py` | 28 | `apps/interpretation/parsers/payload/__init__.py`, `apps/interpretation/parsers/payload/records.py`, `apps/shared/domain/relation_identity.py` |
| `apps/interpretation/tests/test_payload_routing.py` | 25 | `apps/acquisition/sources/catalogue.py`, `apps/interpretation/parsers/payload/__init__.py`, `apps/interpretation/parsers/payload/records.py` |
| `apps/interpretation/tests/test_payload_structure_producer.py` | 37 | `apps/interpretation/extractors/payload/structure.py`, `apps/interpretation/extractors/signals/mentions.py`, `apps/interpretation/extractors/signals/protocol.py`, `apps/interpretation/extractors/signals/signal.py` |
| `apps/interpretation/tests/test_pipeline.py` | 19 | `apps/interpretation/aggregation/candidates.py`, `apps/interpretation/extractors/registry.py`, `apps/interpretation/normalization/canonical.py`, `apps/interpretation/parsers/registry.py` |
| `apps/interpretation/tests/test_primary_proc.py` | 93 | `apps/interpretation/parsers/primproc/__init__.py`, `apps/interpretation/parsers/primproc/decode.py`, `apps/interpretation/parsers/primproc/markup.py`, `apps/interpretation/parsers/primproc/processor.py` |
| `apps/interpretation/tests/test_primary_proc_regex_mutant.py` | 10 | `apps/interpretation/parsers/primproc/__init__.py` |
| `apps/interpretation/tests/test_producer_migration.py` | 23 | `apps/interpretation/extractors/signals/__init__.py`, `apps/interpretation/extractors/signals/lexical.py`, `apps/interpretation/extractors/signals/links.py`, `apps/interpretation/extractors/signals/mentions.py` |
| `apps/interpretation/tests/test_relation_cue_coverage.py` | 7 | `apps/interpretation/extractors/relations.py` |
| `apps/interpretation/tests/test_relations.py` | 25 | `apps/interpretation/extractors/registry.py`, `apps/interpretation/relations.py` |
| `apps/interpretation/tests/test_retriever_fusion.py` | 8 | `apps/interpretation/retrieval/retriever.py`, `apps/shared/scoring/fusion.py` |
| `apps/interpretation/tests/test_search_retriever.py` | 7 | `apps/interpretation/retrieval/__init__.py` |
| `apps/interpretation/tests/test_signal_kind_channels.py` | 11 | `apps/interpretation/extractors/signals/links.py`, `apps/interpretation/extractors/signals/protocol.py`, `apps/interpretation/extractors/signals/signal.py`, `apps/interpretation/extractors/signals/syntactic.py` |
| `apps/interpretation/tests/test_signal_nary_contract.py` | 32 | `apps/interpretation/extractors/signals/signal.py`, `apps/shared/domain/mention_occurrence_index.py`, `apps/shared/domain/predicate_hypothesis.py`, `apps/shared/domain/predicate_signature.py` |
| `apps/interpretation/tests/test_syntactic_producer.py` | 58 | `apps/interpretation/extractors/signals/mentions.py`, `apps/interpretation/extractors/signals/protocol.py`, `apps/interpretation/extractors/signals/signal.py`, `apps/interpretation/extractors/signals/syntactic.py` |
| `apps/interpretation/tests/test_warc_reader.py` | 44 | `apps/interpretation/parsers/warc.py` |
| `apps/projection/tests/contract/test_search_projection_manifest.py` | 9 | `apps/projection/search/index.py`, `apps/projection/search/projector.py`, `apps/shared/contracts/projection_manifest.py` |
| `apps/projection/tests/contract/test_tda_bridge_contract.py` | 30 | `apps/projection/graph/adjacency.py`, `apps/projection/tda/__init__.py`, `apps/projection/tda/bridge.py`, `apps/projection/tda/pipeline.py` |
| `apps/projection/tests/test_bm25s_backend.py` | 9 | `apps/projection/search/bm25s_backend.py`, `apps/projection/search/indexer.py`, `apps/shared/domain/__init__.py` |
| `apps/projection/tests/test_lakehouse.py` | 8 | `apps/projection/lakehouse/river/lake.py`, `apps/shared/storage/memory.py` |
| `apps/projection/tests/test_metrics.py` | 21 | `apps/projection/graph/adjacency.py`, `apps/projection/metrics/community.py`, `apps/projection/metrics/hypergraph_metrics.py`, `apps/projection/metrics/network_measures.py` |
| `apps/projection/tests/test_projection.py` | 17 | `apps/projection/analytics/projector.py`, `apps/projection/graph/abstraction.py`, `apps/projection/graph/neo4j.py`, `apps/projection/graph/snapshot.py` |
| `apps/projection/tests/test_relevance.py` | 15 | `apps/projection/search/indexer.py`, `apps/projection/search/relevance.py`, `apps/shared/domain/__init__.py` |
| `apps/projection/tests/test_streams.py` | 7 | `apps/projection/streams/jobs.py` |
| `apps/projection/tests/test_tantivy_backend.py` | 7 | `apps/projection/search/index.py`, `apps/projection/search/quickwit.py`, `apps/projection/search/tantivy_backend.py`, `apps/shared/domain/__init__.py` |
| `apps/projection/tests/unit/test_diagram.py` | 6 | `apps/projection/tda/diagram.py` |
| `apps/projection/tests/unit/test_features.py` | 21 | `apps/projection/tda/features.py` |
| `apps/projection/tests/unit/test_graph_store_direction.py` | 28 | `apps/projection/graph/abstraction.py`, `apps/projection/graph/adjacency.py`, `apps/shared/domain/__init__.py` |
| `apps/projection/tests/unit/test_h3_spatial.py` | 21 | `apps/projection/spatial/h3_index.py` |
| `apps/projection/tests/unit/test_neo4j_relation_write.py` | 13 | `apps/projection/graph/abstraction.py`, `apps/projection/graph/neo4j.py`, `apps/shared/domain/__init__.py` |
| `apps/projection/tests/unit/test_pipeline_directed.py` | 9 | `apps/projection/tda/pipeline.py` |
| `apps/projection/tests/unit/test_relation_store.py` | 18 | `apps/projection/graph/relation_store.py`, `apps/projection/path_shim.py`, `apps/shared/domain/__init__.py`, `apps/shared/domain/relation_claim.py` |
| `apps/projection/tests/unit/test_takens.py` | 5 | `apps/projection/tda/pipeline.py` |
| `apps/projection/tests/unit/test_tda_insight.py` | 14 | `apps/projection/tda/insight.py`, `apps/projection/tda/pipeline.py` |
| `apps/projection/tests/unit/test_tda_pipeline_performance.py` | 16 | `apps/projection/tda/pipeline.py` |
| `apps/projection/tests/unit/test_temporal_features.py` | 3 | `apps/projection/temporal_materialization/features.py`, `apps/projection/temporal_materialization/operations.py`, `apps/shared/domain/dynamics.py`, `apps/shared/domain/temporal_materialization.py` |
| `apps/projection/tests/unit/test_temporal_graph.py` | 28 | `apps/projection/analytics/clickhouse_client.py`, `apps/projection/analytics/temporal_graph.py` |
| `apps/projection/tests/unit/test_topological_invariant.py` | 4 | `apps/projection/tda/__init__.py` |
| `apps/projection/tests/unit/test_validated.py` | 5 | `apps/projection/tda/validated.py` |
| `apps/science/context/tests/test_epistemic_algebra.py` | 69 | `apps/science/context/epistemic.py` |
| `apps/science/tests/contract/test_argumentation_contract.py` | 26 | `apps/science/context/argumentation.py` |
| `apps/science/tests/contract/test_causal_contract.py` | 5 | `apps/science/causal/infer.py`, `apps/science/causal/model.py`, `apps/science/claims/model.py`, `apps/science/errors.py` |
| `apps/science/tests/contract/test_circularity_contract.py` | 46 | `apps/science/context/circularity.py` |
| `apps/science/tests/contract/test_claim_contract.py` | 7 | `apps/science/claims/calibration.py`, `apps/science/claims/model.py`, `apps/science/claims/registry.py`, `apps/science/errors.py` |
| `apps/science/tests/contract/test_completeness_contract.py` | 37 | `apps/science/context/completeness.py`, `apps/science/context/coverage.py` |
| `apps/science/tests/contract/test_coverage_independence_contract.py` | 44 | `apps/science/context/coverage.py`, `apps/science/context/epistemic.py` |
| `apps/science/tests/contract/test_dialectics_contract.py` | 45 | `apps/science/context/dialectics.py` |
| `apps/science/tests/contract/test_discipline_adapters_contract.py` | 34 | `apps/science/claims/model.py`, `apps/science/context/argumentation.py`, `apps/science/context/dialectics.py`, `apps/science/context/locality.py` |
| `apps/science/tests/contract/test_dossier_contract.py` | 46 | `apps/science/context/dossier.py`, `apps/science/context/enrichment.py`, `apps/shared/domain/graph_invariant.py` |
| `apps/science/tests/contract/test_enrichment_contract.py` | 34 | `apps/science/context/enrichment.py` |
| `apps/science/tests/contract/test_epistemic_contract.py` | 60 | `apps/science/context/epistemic.py` |
| `apps/science/tests/contract/test_event_emission_contract.py` | 7 | `apps/science/claims/model.py`, `apps/science/robustness/perturb.py`, `apps/science/robustness/report.py`, `apps/science/store.py` |
| `apps/science/tests/contract/test_gluing_contract.py` | 34 | `apps/science/context/locality.py`, `apps/science/context/operators/compatibility.py`, `apps/science/context/operators/gluing.py` |
| `apps/science/tests/contract/test_growth_contract.py` | 25 | `apps/science/context/growth.py`, `apps/science/context/locality.py` |
| `apps/science/tests/contract/test_hierarchy_contract.py` | 65 | `apps/science/context/hierarchy.py`, `apps/shared/domain/derivation.py` |
| `apps/science/tests/contract/test_hypothesis_contract.py` | 8 | `apps/science/claims/model.py`, `apps/science/errors.py`, `apps/science/hypotheses/coverage.py`, `apps/science/hypotheses/decide.py` |
| `apps/science/tests/contract/test_locality_contract.py` | 43 | `apps/science/context/locality.py` |
| `apps/science/tests/contract/test_ontology_and_schema_stay_in_step.py` | 7 | `apps/control-plane/db/schema.py`, `apps/shared/domain/ontology.py` |
| `apps/science/tests/contract/test_operator_registry_contract.py` | 27 | `apps/science/context/operators/base.py`, `apps/science/context/operators/registry.py` |
| `apps/science/tests/contract/test_operator_result_bridge.py` | 10 | `apps/science/context/operators/base.py`, `apps/science/context/operators/contract_bridge.py`, `apps/shared/contracts/operator_result.py`, `apps/shared/contracts/stage_outcome.py` |
| `apps/science/tests/contract/test_query_compiler_contract.py` | 46 | `apps/science/context/completeness.py`, `apps/science/context/query_ast.py`, `apps/science/context/query_binding.py`, `apps/science/context/query_grammar.py` |
| `apps/science/tests/contract/test_review_contract.py` | 6 | `apps/science/claims/model.py`, `apps/science/review/events.py`, `apps/science/review/ladder.py` |
| `apps/science/tests/contract/test_robustness_contract.py` | 7 | `apps/science/claims/model.py`, `apps/science/errors.py`, `apps/science/experiments/registry.py`, `apps/science/experiments/reproduction.py` |
| `apps/science/tests/contract/test_science_seam_contract.py` | 29 | `apps/control-plane/context_engine/loop.py`, `apps/control-plane/context_engine/science_bridge.py`, `apps/science/anchoring.py`, `apps/science/context/bridge.py` |
| `apps/science/tests/contract/test_scope_lattice_contract.py` | 30 | `apps/science/context/lattice.py` |
| `apps/science/tests/contract/test_structure_contract.py` | 6 | `apps/science/errors.py`, `apps/science/structure/graph.py` |
| `apps/science/tests/contract/test_temporal_contract.py` | 4 | `apps/science/store.py`, `apps/science/temporal/changedetect.py`, `apps/science/temporal/scenario.py`, `apps/science/temporal/timeseries.py` |
| `apps/science/tests/contract/test_temporal_filter.py` | 13 | `apps/science/context/completeness.py`, `apps/science/context/query_ast.py`, `apps/science/context/temporal_filter.py` |
| `apps/science/tests/contract/test_worldline_view_contract.py` | 21 | `apps/science/anchoring.py`, `apps/science/context/worldline.py` |
| `apps/science/tests/integration/test_context_engine_chain.py` | 8 | `apps/science/context/argumentation.py`, `apps/science/context/completeness.py`, `apps/science/context/coverage.py`, `apps/science/context/dialectics.py` |
| `apps/science/tests/integration/test_live_asg_pipeline.py` | 13 | `apps/acquisition/sources/catalogue.py`, `apps/acquisition/sources/connector.py`, `apps/control-plane/db/session.py`, `apps/interpretation/parsers/families.py` |
| `apps/science/tests/integration/test_live_scope_lattice.py` | 10 | `apps/science/context/lattice.py`, `apps/shared/domain/derivation.py`, `apps/shared/domain/ontology.py` |
| `apps/science/tests/test_anchoring.py` | 21 | `apps/science/anchoring.py` |
| `apps/science/tests/unit/__init__.py` | 0 | — |
| `apps/science/tests/unit/test_calibration.py` | 4 | `apps/science/claims/calibration.py`, `apps/science/claims/model.py` |
| `apps/science/tests/unit/test_changedetect.py` | 3 | `apps/science/temporal/changedetect.py`, `apps/science/temporal/timeseries.py` |
| `apps/science/tests/unit/test_econ.py` | 11 | `apps/science/econ/crisis_abm.py`, `apps/science/econ/operators.py` |
| `apps/science/tests/unit/test_gain.py` | 3 | `apps/science/claims/model.py`, `apps/science/hypotheses/decide.py`, `apps/science/hypotheses/evidence.py`, `apps/science/hypotheses/gain.py` |
| `apps/science/tests/unit/test_gnca.py` | 7 | `apps/science/sims/gnca.py` |
| `apps/science/tests/unit/test_kinetics.py` | 10 | `apps/science/kinetics/pathways.py` |
| `apps/science/tests/unit/test_ladder.py` | 4 | `apps/science/claims/model.py`, `apps/science/review/ladder.py` |
| `apps/science/tests/unit/test_landscape.py` | 7 | `apps/science/beliefs/landscape.py` |
| `apps/science/tests/unit/test_phase.py` | 19 | `apps/science/operators/phase.py` |
| `apps/science/tests/unit/test_reproduction.py` | 9 | `apps/science/claims/model.py`, `apps/science/experiments/registry.py`, `apps/science/experiments/reproduction.py`, `apps/science/robustness/perturb.py` |
| `apps/science/tests/unit/test_river_drift.py` | 25 | `apps/science/streaming/river_operator.py` |
| `apps/science/tests/unit/test_schelling.py` | 5 | `apps/science/fixtures/schelling.py` |
| `apps/science/tests/unit/test_scope.py` | 4 | `apps/science/causal/model.py`, `apps/science/causal/scope.py`, `apps/science/errors.py` |
| `apps/science/tests/unit/test_series_embedding.py` | 7 | `apps/science/scitda/series.py` |
| `apps/science/tests/unit/test_structure.py` | 7 | `apps/science/structure/graph.py`, `apps/science/structure/model.py`, `apps/science/structure/motif.py`, `apps/science/structure/spectral.py` |
| `apps/science/tests/unit/test_tda.py` | 19 | `apps/science/scitda/persistence.py`, `apps/science/scitda/phodms.py` |
| `apps/shared/tests/constitution/__init__.py` | 0 | — |
| `apps/shared/tests/constitution/test_constitution4_no_fabrication.py` | 16 | `apps/interpretation/extractors/signals/__init__.py`, `apps/interpretation/extractors/signals/metadata.py`, `apps/interpretation/extractors/signals/protocol.py`, `apps/interpretation/extractors/signals/tables.py` |
| `apps/shared/tests/constitution/test_constitution_has_teeth.py` | 2 | — |
| `apps/shared/tests/constitution/test_i1_i3_immutability_and_preservation.py` | 9 | `apps/interpretation/extractors/signals/__init__.py`, `apps/shared/domain/capture.py`, `apps/shared/domain/predicate_hypothesis.py`, `apps/shared/domain/relation_candidate.py` |
| `apps/shared/tests/constitution/test_identity_subsystem_constitution.py` | 14 | `apps/shared/domain/predicate_signature.py`, `apps/shared/domain/relation_claim.py`, `apps/shared/domain/relation_identity.py`, `apps/shared/semantic/contracts.py` |
| `apps/shared/tests/constitution/test_iv_vi_tenancy_and_determinism.py` | 9 | `apps/control-plane/semantic_path/assembly.py`, `apps/interpretation/extractors/signals/__init__.py`, `apps/interpretation/extractors/signals/protocol.py`, `apps/shared/domain/capture.py` |
| `apps/shared/tests/contract/__init__.py` | 0 | — |
| `apps/shared/tests/contract/test_correlation.py` | 4 | `apps/shared/domain/__init__.py` |
| `apps/shared/tests/contract/test_domain_invariants.py` | 12 | `apps/shared/domain/__init__.py` |
| `apps/shared/tests/contract/test_donor_registry.py` | 27 | — |
| `apps/shared/tests/contract/test_entity_fabric.py` | 46 | `apps/shared/domain/dynamics.py`, `apps/shared/domain/fabric.py`, `apps/shared/domain/hypergraph.py` |
| `apps/shared/tests/contract/test_error_codes.py` | 54 | `apps/shared/contracts/canonical.py`, `apps/shared/contracts/error_codes.py` |
| `apps/shared/tests/contract/test_event_envelope.py` | 11 | `apps/shared/events/event_envelope_pb2.py`, `apps/shared/events/kafka.py` |
| `apps/shared/tests/contract/test_evidence_span.py` | 52 | `apps/shared/contracts/evidence_span.py` |
| `apps/shared/tests/contract/test_evidence_span_roundtrip.py` | 8 | `apps/shared/contracts/evidence_span.py` |
| `apps/shared/tests/contract/test_metrics.py` | 6 | `apps/shared/scoring/__init__.py` |
| `apps/shared/tests/contract/test_ontology.py` | 4 | `apps/shared/events/ontology_pack.py` |
| `apps/shared/tests/contract/test_operator_result.py` | 51 | `apps/shared/contracts/canonical.py`, `apps/shared/contracts/error_codes.py`, `apps/shared/contracts/evidence_span.py`, `apps/shared/contracts/operator_result.py` |
| `apps/shared/tests/contract/test_platform_gaps.py` | 3 | `platform_model/__init__.py` |
| `apps/shared/tests/contract/test_platform_model.py` | 16 | `platform_model/__init__.py` |
| `apps/shared/tests/contract/test_projection_manifest.py` | 24 | `apps/shared/contracts/projection_manifest.py` |
| `apps/shared/tests/contract/test_review.py` | 4 | `apps/shared/domain/__init__.py` |
| `apps/shared/tests/contract/test_single_publication_path.py` | 9 | — |
| `apps/shared/tests/contract/test_stage_outcome.py` | 52 | `apps/shared/contracts/error_codes.py`, `apps/shared/contracts/stage_outcome.py` |
| `apps/shared/tests/contract/test_statement.py` | 3 | `apps/shared/domain/__init__.py` |
| `apps/shared/tests/contract/test_storage.py` | 6 | `apps/shared/storage/s3.py` |
| `apps/shared/tests/integration/__init__.py` | 0 | — |
| `apps/shared/tests/integration/test_idempotency.py` | 3 | — |
| `apps/shared/tests/integration/test_infra_connectivity.py` | 6 | — |
| `apps/shared/tests/integration/test_redpanda_emission.py` | 1 | `apps/shared/events/event_envelope_pb2.py`, `apps/shared/events/kafka.py` |
| `apps/shared/tests/unit/domain/test_domain_model.py` | 7 | `apps/shared/domain/__init__.py`, `apps/shared/domain/entity.py`, `apps/shared/domain/property.py`, `apps/shared/domain/schema.py` |
| `apps/shared/tests/unit/domain/test_graph_invariant.py` | 23 | `apps/shared/domain/graph_invariant.py` |
| `apps/shared/tests/unit/domain/test_temporal_materialization.py` | 9 | `apps/shared/domain/dynamics.py`, `apps/shared/domain/temporal_materialization.py`, `apps/shared/domain/temporal_materialization_store.py` |
| `apps/shared/tests/unit/domain/test_temporal_worldline.py` | 23 | `apps/shared/domain/dynamics.py`, `apps/shared/domain/temporal_worldline.py` |
| `apps/shared/tests/unit/domain/test_temporal_worldline_store.py` | 11 | `apps/shared/domain/dynamics.py`, `apps/shared/domain/temporal_worldline.py`, `apps/shared/domain/temporal_worldline_store.py` |
| `apps/shared/tests/unit/donor/conftest.py` | 0 | `apps/shared/donor/correlation_graph.py` |
| `apps/shared/tests/unit/donor/test_correlation_graph.py` | 13 | `apps/shared/donor/correlation_graph.py` |
| `apps/shared/tests/unit/donor/test_evidence.py` | 7 | `apps/shared/donor/evidence.py` |
| `apps/shared/tests/unit/donor/test_statement.py` | 14 | `apps/shared/donor/statement.py` |
| `apps/shared/tests/unit/donor/test_target.py` | 18 | `apps/shared/donor/target.py` |
| `apps/shared/tests/unit/donor/test_temporal.py` | 14 | `apps/shared/donor/temporal.py` |
| `apps/shared/tests/unit/events/test_temporal_materialization_events.py` | 1 | `apps/shared/domain/dynamics.py`, `apps/shared/domain/stream_events.py`, `apps/shared/domain/temporal_materialization.py`, `apps/shared/events/topics.py` |
| `apps/shared/tests/unit/scoring/test_adaptive_state.py` | 10 | `apps/shared/scoring/scorer.py` |
| `apps/shared/tests/unit/test_access_mode.py` | 15 | `apps/shared/domain/access_mode.py` |
| `apps/shared/tests/unit/test_acquisition_path.py` | 14 | `apps/shared/domain/__init__.py`, `apps/shared/events/content_router.py`, `apps/shared/events/observation_gate.py`, `apps/shared/scoring/scorer.py` |
| `apps/shared/tests/unit/test_candidate_logical_identity.py` | 29 | `apps/shared/domain/predicate_signature.py`, `apps/shared/domain/relation_candidate.py`, `apps/shared/domain/relation_identity.py`, `apps/shared/semantic/contracts.py` |
| `apps/shared/tests/unit/test_cc_session.py` | 4 | `apps/shared/network/cc_session.py` |
| `apps/shared/tests/unit/test_cd6_unresolved_predicate.py` | 17 | `apps/shared/domain/predicate_hypothesis.py`, `apps/shared/domain/relation_candidate.py`, `apps/shared/domain/relation_claim_material.py`, `apps/shared/semantic/contracts.py` |
| `apps/shared/tests/unit/test_co_mention.py` | 4 | `apps/shared/domain/co_mention.py`, `apps/shared/domain/hypergraph.py` |
| `apps/shared/tests/unit/test_commoncrawl.py` | 7 | `apps/shared/network/commoncrawl.py` |
| `apps/shared/tests/unit/test_derivation_identity.py` | 32 | `apps/shared/domain/derivation.py` |
| `apps/shared/tests/unit/test_dlq_durable.py` | 9 | `apps/shared/events/dlq.py`, `apps/shared/events/dlq_durable.py` |
| `apps/shared/tests/unit/test_event_timestamps.py` | 11 | `apps/shared/events/timestamps.py` |
| `apps/shared/tests/unit/test_evidence_context.py` | 27 | `apps/shared/domain/evidence_context.py` |
| `apps/shared/tests/unit/test_evidence_lineage.py` | 16 | `apps/shared/domain/evidence_lineage.py`, `apps/shared/domain/relation_claim.py`, `apps/shared/domain/relation_identity.py` |
| `apps/shared/tests/unit/test_evidence_store_guard.py` | 10 | `apps/shared/events/evidence_store_guard.py` |
| `apps/shared/tests/unit/test_fusion.py` | 26 | `apps/shared/scoring/fusion.py` |
| `apps/shared/tests/unit/test_idempotent_consumer.py` | 8 | `apps/shared/events/__init__.py`, `apps/shared/events/dlq.py`, `apps/shared/events/kafka.py` |
| `apps/shared/tests/unit/test_ids.py` | 8 | `apps/shared/ids/__init__.py` |
| `apps/shared/tests/unit/test_investigation_context.py` | 37 | `apps/shared/domain/investigation_context.py` |
| `apps/shared/tests/unit/test_layer_boundaries.py` | 9 | `apps/shared/tools/layer_boundaries.py` |
| `apps/shared/tests/unit/test_measured_values.py` | 19 | `apps/shared/observability/measured.py` |
| `apps/shared/tests/unit/test_mention_occurrence_index.py` | 20 | `apps/shared/domain/mention_occurrence_index.py`, `apps/shared/domain/predicate_signature.py`, `apps/shared/domain/relation_identity.py` |
| `apps/shared/tests/unit/test_observation_gate_identity.py` | 20 | `apps/shared/domain/observation_identity.py`, `apps/shared/events/observation_gate.py` |
| `apps/shared/tests/unit/test_observation_identity.py` | 29 | `apps/shared/domain/observation_identity.py`, `apps/shared/domain/relation_identity.py` |
| `apps/shared/tests/unit/test_open_world_predicates.py` | 27 | `apps/shared/domain/predicate_hypothesis.py`, `apps/shared/domain/relation_candidate.py`, `apps/shared/semantic/contracts.py` |
| `apps/shared/tests/unit/test_participant_end_kind.py` | 5 | `apps/shared/domain/mention_occurrence_index.py`, `apps/shared/domain/predicate_signature.py`, `apps/shared/domain/relation_participant.py` |
| `apps/shared/tests/unit/test_predicate_signature.py` | 77 | `apps/shared/domain/__init__.py`, `apps/shared/domain/predicate_signature.py`, `apps/shared/domain/predicate_voice.py`, `apps/shared/domain/relation_identity.py` |
| `apps/shared/tests/unit/test_range_pull.py` | 5 | `apps/shared/network/range_pull.py` |
| `apps/shared/tests/unit/test_relation_claim.py` | 16 | `apps/shared/domain/relation_claim.py`, `apps/shared/domain/relation_identity.py` |
| `apps/shared/tests/unit/test_relation_identity.py` | 24 | `apps/shared/domain/relation_claim.py`, `apps/shared/domain/relation_identity.py` |
| `apps/shared/tests/unit/test_relation_schema.py` | 27 | `apps/shared/domain/evidence_context.py`, `apps/shared/domain/relation_claim.py`, `apps/shared/domain/relation_identity.py`, `apps/shared/domain/relation_schema.py` |
| `apps/shared/tests/unit/test_research_lineage.py` | 19 | `apps/shared/domain/research_lineage.py` |
| `apps/shared/tests/unit/test_resolution_mention_span.py` | 13 | `apps/shared/domain/mention_occurrence_index.py`, `apps/shared/semantic/contracts.py`, `apps/shared/semantic/resolution.py` |
| `apps/shared/tests/unit/test_schema_hierarchy.py` | 20 | `apps/shared/domain/schema.py` |
| `apps/shared/tests/unit/test_secure_fetch.py` | 16 | `apps/shared/net/secure_fetch.py`, `apps/shared/security.py` |
| `apps/shared/tests/unit/test_security.py` | 19 | `apps/shared/security.py` |
| `apps/shared/tests/unit/test_temporal_metrics.py` | 9 | `apps/shared/domain/temporal_metrics.py` |
| `apps/shared/tests/unit/websearch/test_websearch.py` | 23 | `apps/shared/websearch/__init__.py`, `apps/shared/websearch/contracts.py`, `apps/shared/websearch/discovery.py`, `apps/shared/websearch/providers.py` |
| `apps/specops/tests/conftest.py` | 0 | `apps/specops/ghostline/config.py`, `apps/specops/ghostline/runtime.py` |
| `apps/specops/tests/test_engagement.py` | 26 | `apps/specops/engagement/__init__.py`, `apps/specops/engagement/config.py`, `apps/specops/engagement/fabric.py` |
| `apps/specops/tests/test_ghostline.py` | 36 | `apps/specops/ghostline/catalog.py`, `apps/specops/ghostline/config.py`, `apps/specops/ghostline/engine.py`, `apps/specops/ghostline/ledger.py` |
| `apps/specops/tests/test_roe_gate.py` | 11 | `apps/specops/roe/gate.py` |
| `apps/specops/tests/test_specops_ghostline_routers.py` | 26 | `apps/control-plane/api/main.py` |
| `apps/specops/tests/test_specops_routers.py` | 10 | `apps/control-plane/api/main.py` |
| `apps/zero/tests/conftest.py` | 0 | `apps/zero/zero/type_detector.py` |
| `apps/zero/tests/test_cc_capture.py` | 14 | `apps/shared/network/cc_session.py`, `apps/zero/zero/cc_capture.py` |
| `apps/zero/tests/test_enrichment.py` | 24 | `apps/zero/zero/enrichment/feedback.py`, `apps/zero/zero/enrichment/modules.py`, `apps/zero/zero/harvesters/contracts.py`, `apps/zero/zero/type_detector.py` |
| `apps/zero/tests/test_harvest_wave.py` | 15 | `apps/zero/zero/harvest_wave.py`, `apps/zero/zero/harvesters/contracts.py`, `apps/zero/zero/harvesters/domain.py`, `apps/zero/zero/harvesters/registry.py` |
| `apps/zero/tests/test_harvesters.py` | 25 | `apps/zero/zero/harvesters/contracts.py`, `apps/zero/zero/harvesters/domain.py`, `apps/zero/zero/harvesters/git.py`, `apps/zero/zero/harvesters/image.py` |
| `apps/zero/tests/test_resolution.py` | 23 | `apps/zero/zero/harvesters/contracts.py`, `apps/zero/zero/resolution/fellegi_sunter.py`, `apps/zero/zero/resolution/graph.py`, `apps/zero/zero/resolution/similarity.py` |
| `apps/zero/tests/test_type_detector.py` | 22 | `apps/zero/zero/type_detector.py` |
| `bench/tests/test_harness.py` | 10 | `bench/bench/__init__.py` |
| `bench/tests/test_knowledge.py` | 10 | — |
| `bench/tests/test_scale_scale.py` | 3 | — |
| `implementation/tests/test_contract_files.py` | 4 | — |
| `implementation/tests/test_person_case_lark.py` | 2 | — |
| `specs/021-entity-relation-extraction-finalization/repair/tools/test_reference_check.py` | 200 | — |

## Platform modules not targeted by any test (sample)

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
| `apps/admission/engine/__init__.py` |
| `apps/admission/independence/__init__.py` |
| `apps/admission/resolution/__init__.py` |
| `apps/bulk-ingestion/backfill.py` |
| `apps/bulk-ingestion/historical/__init__.py` |
| `apps/bulk-ingestion/historical/replay.py` |
| `apps/control-plane/__init__.py` |
| `apps/control-plane/api/auth.py` |
| `apps/control-plane/api/path_shim.py` |
| `apps/control-plane/api/routes/connectors.py` |
| `apps/control-plane/api/routes/discovery.py` |
| `apps/control-plane/api/routes/dossier.py` |
| `apps/control-plane/api/routes/fabric.py` |
| `apps/control-plane/api/routes/investigation_context.py` |
| `apps/control-plane/api/routes/investigations.py` |
| `apps/control-plane/api/routes/manual_assertions.py` |
| `apps/control-plane/api/routes/metrics.py` |
| `apps/control-plane/api/routes/network.py` |
| `apps/control-plane/api/routes/platform.py` |
| `apps/control-plane/api/routes/quarantine.py` |
| `apps/control-plane/api/routes/research_cases.py` |
| `apps/control-plane/api/routes/resolutions.py` |
| `apps/control-plane/api/routes/science_causal.py` |
| `apps/control-plane/api/routes/science_claims.py` |
| `apps/control-plane/api/routes/science_hypotheses.py` |
| `apps/control-plane/api/routes/science_review.py` |
| `apps/control-plane/api/routes/science_robustness.py` |
| `apps/control-plane/api/routes/science_structure.py` |
| `apps/control-plane/api/routes/science_tda.py` |
| `apps/control-plane/api/routes/science_temporal.py` |
| `apps/control-plane/api/routes/search.py` |
