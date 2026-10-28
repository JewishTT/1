# Import graph

1009 Python modules, 2807 resolved local edges.

Imports are classified against the platform's own import roots, the standard library,
the packages installed in the interpreter that ran the generator, and the distributions
declared in the workspace manifests. A name in none of those is a defect, not a dependency.

## External dependencies (top 40)

| Package | Kind | Import sites |
|---|---|---|
| `__future__` | stdlib | 879 |
| `dataclasses` | stdlib | 390 |
| `typing` | stdlib | 367 |
| `pathlib` | stdlib | 317 |
| `sys` | stdlib | 256 |
| `collections` | stdlib | 240 |
| `json` | stdlib | 193 |
| `datetime` | stdlib | 190 |
| `sqlalchemy` | declared-not-installed | 158 |
| `hashlib` | stdlib | 127 |
| `enum` | stdlib | 118 |
| `re` | stdlib | 96 |
| `asyncio` | stdlib | 70 |
| `os` | stdlib | 69 |
| `fastapi` | declared-not-installed | 66 |
| `uuid` | stdlib | 48 |
| `urllib` | stdlib | 43 |
| `math` | stdlib | 41 |
| `pydantic` | declared-not-installed | 34 |
| `types` | stdlib | 33 |
| `importlib` | stdlib | 32 |
| `time` | stdlib | 29 |
| `ast` | stdlib | 27 |
| `io` | stdlib | 25 |
| `alembic` | declared-not-installed | 24 |
| `numpy` | declared-not-installed | 23 |
| `logging` | stdlib | 23 |
| `inspect` | stdlib | 21 |
| `httpx` | declared-not-installed | 20 |
| `argparse` | stdlib | 20 |
| `tempfile` | stdlib | 18 |
| `threading` | stdlib | 17 |
| `confluent_kafka` | declared-not-installed | 16 |
| `subprocess` | stdlib | 16 |
| `warcio` | declared-not-installed | 15 |
| `shutil` | stdlib | 14 |
| `temporalio` | declared-not-installed | 13 |
| `itertools` | stdlib | 11 |
| `yaml` | declared-not-installed | 10 |
| `base64` | stdlib | 9 |

## Optional capability probes

Imported inside a `try`/`except ImportError`. The platform is written to run without
them, so they are neither a dependency nor a defect — but each one is a capability
that is switched off in this environment.

| Package | Probe sites |
|---|---|
| `opentelemetry` | 5 |
| `packaging` | 2 |
| `rdflib` | 2 |
| `PIL` | 1 |
| `pyshacl` | 1 |
| `pyzbar` | 1 |
| `tantivy` | 1 |

## Import roots

Top-level name → the directory it resolves to, taken from the platform's own `sys.path` at generation time.

| Name | Directory |
|---|---|
| `_events` | `apps/science/_events.py` |
| `_prove_readback` | `apps/acquisition/_prove_readback.py` |
| `acquisition` | `apps/acquisition` |
| `adapters` | `apps/acquisition/adapters/__init__.py` |
| `admission` | `apps/admission` |
| `aggregation` | `apps/interpretation/aggregation` |
| `analytics` | `apps/projection/analytics/__init__.py` |
| `anchoring` | `apps/science/anchoring.py` |
| `api` | `apps/control-plane/api/__init__.py` |
| `application` | `apps/control-plane/application` |
| `artifact_sink` | `apps/acquisition/artifact_sink.py` |
| `badges` | `apps/control-plane/badges/__init__.py` |
| `beliefs` | `apps/science/beliefs/__init__.py` |
| `bench` | `bench/bench/__init__.py` |
| `bulk_ingestion` | `apps/bulk-ingestion` |
| `case_execution_guard` | `apps/acquisition/case_execution_guard.py` |
| `causal` | `apps/science/causal/__init__.py` |
| `cc_extract` | `apps/acquisition/cc_extract.py` |
| `cc_plan` | `apps/acquisition/cc_plan.py` |
| `claims` | `apps/science/claims/__init__.py` |
| `composition` | `apps/control-plane/composition.py` |
| `config` | `apps/shared/config/__init__.py` |
| `context` | `apps/science/context/__init__.py` |
| `context_engine` | `apps/control-plane/context_engine/__init__.py` |
| `contracts` | `apps/shared/contracts/__init__.py` |
| `cp_domain` | `apps/control-plane/cp_domain/__init__.py` |
| `datasets` | `apps/shared/datasets/__init__.py` |
| `db` | `apps/control-plane/db/__init__.py` |
| `dictionaries` | `apps/interpretation/dictionaries/__init__.py` |
| `dispatcher` | `apps/acquisition/dispatcher/__init__.py` |
| `domain` | `apps/shared/domain/__init__.py` |
| `donor` | `apps/shared/donor/__init__.py` |
| `econ` | `apps/science/econ/__init__.py` |
| `engine` | `apps/admission/engine/__init__.py` |
| `errors` | `apps/science/errors.py` |
| `events` | `apps/shared/events/__init__.py` |
| `evidence` | `apps/interpretation/evidence/__init__.py` |
| `evidence_writer` | `apps/acquisition/evidence_writer.py` |
| `experiments` | `apps/science/experiments/__init__.py` |
| `extractors` | `apps/interpretation/extractors/__init__.py` |
| `feedback` | `apps/feedback` |
| `fixtures` | `apps/science/fixtures/__init__.py` |
| `frontier` | `apps/acquisition/frontier` |
| `graph` | `apps/projection/graph/__init__.py` |
| `hypotheses` | `apps/science/hypotheses/__init__.py` |
| `ids` | `apps/shared/ids/__init__.py` |
| `independence` | `apps/admission/independence/__init__.py` |
| `interpretation` | `apps/interpretation/__init__.py` |
| `isolation` | `apps/shared/isolation.py` |
| `kinetics` | `apps/science/kinetics/__init__.py` |
| `knowledge` | `bench/knowledge` |
| `lakehouse` | `apps/projection/lakehouse/__init__.py` |
| `metrics` | `apps/projection/metrics/__init__.py` |
| `modifier` | `apps/control-plane/modifier/__init__.py` |
| `net` | `apps/shared/net` |
| `network` | `apps/shared/network/__init__.py` |
| `normalization` | `apps/interpretation/normalization` |
| `observability` | `apps/shared/observability/__init__.py` |
| `observation_consumer` | `apps/interpretation/observation_consumer/__init__.py` |
| `observation_gate` | `apps/acquisition/observation_gate/__init__.py` |
| `operators` | `apps/science/operators/__init__.py` |
| `parsers` | `apps/interpretation/parsers/__init__.py` |
| `path_shim` | `apps/projection/path_shim.py` |
| `pipeline` | `apps/interpretation/pipeline.py` |
| `projection` | `apps/projection` |
| `registry` | `apps/acquisition/registry.py` |
| `relations` | `apps/interpretation/relations.py` |
| `resolution` | `apps/admission/resolution/__init__.py` |
| `retrieval` | `apps/interpretation/retrieval/__init__.py` |
| `review` | `apps/science/review/__init__.py` |
| `robustness` | `apps/science/robustness/__init__.py` |
| `runtime` | `apps/acquisition/runtime/__init__.py` |
| `science` | `apps/science` |
| `scitda` | `apps/science/scitda/__init__.py` |
| `scoring` | `apps/shared/scoring/__init__.py` |
| `search` | `apps/projection/search/__init__.py` |
| `security` | `apps/shared/security.py` |
| `semantic` | `apps/shared/semantic/__init__.py` |
| `semantic_path` | `apps/control-plane/semantic_path/__init__.py` |
| `services` | `apps/control-plane/services/__init__.py` |
| `sims` | `apps/science/sims/__init__.py` |
| `sources` | `apps/acquisition/sources/__init__.py` |
| `spatial` | `apps/projection/spatial` |
| `specops` | `apps/specops/__init__.py` |
| `storage` | `apps/shared/storage/__init__.py` |
| `store` | `apps/science/store.py` |
| `stream` | `apps/acquisition/stream.py` |
| `streaming` | `apps/science/streaming` |
| `streams` | `apps/projection/streams/__init__.py` |
| `structure` | `apps/science/structure/__init__.py` |
| `tda` | `apps/projection/tda/__init__.py` |
| `temporal` | `apps/science/temporal/__init__.py` |
| `tools` | `apps/shared/tools` |
| `websearch` | `apps/shared/websearch/__init__.py` |
| `worker_acquisition` | `apps/acquisition/worker_acquisition.py` |
| `worker_browser` | `apps/acquisition/worker_browser/__init__.py` |
| `worker_http` | `apps/acquisition/worker_http/__init__.py` |
| `workflow` | `apps/shared/workflow/__init__.py` |
| `workflows` | `apps/control-plane/workflows/__init__.py` |
| `zero` | `apps/zero/zero/__init__.py` |

## Undeclared dependencies

The import names a third-party package that is neither installed nor declared in any
workspace manifest. It will fail at runtime on a clean environment.

| From | Import |
|---|---|
| `apps/acquisition/tests/contract/test_plan_driver.py` | `pytest` |
| `apps/acquisition/tests/contract/test_scheduler.py` | `pytest` |
| `apps/acquisition/tests/integration/test_adapters_gate.py` | `pytest` |
| `apps/acquisition/tests/integration/test_backpressure.py` | `pytest` |
| `apps/acquisition/tests/integration/test_engine_adapters_gate.py` | `pytest` |
| `apps/acquisition/tests/integration/test_live_loop.py` | `pytest` |
| `apps/acquisition/tests/integration/test_loop_closed.py` | `pytest` |
| `apps/acquisition/tests/integration/test_worker.py` | `pytest` |
| `apps/acquisition/tests/test_connector_registry.py` | `pytest` |
| `apps/acquisition/tests/unit/test_acquisition_artifact_sink.py` | `pytest` |
| `apps/acquisition/tests/unit/test_acquisition_worker.py` | `pytest` |
| `apps/acquisition/tests/unit/test_adapter_onboarding.py` | `pytest` |
| `apps/acquisition/tests/unit/test_airbyte_runtime.py` | `pytest` |
| `apps/acquisition/tests/unit/test_bbot_process_boundary.py` | `pytest` |
| `apps/acquisition/tests/unit/test_bbot_runtime.py` | `pytest` |
| `apps/acquisition/tests/unit/test_case_execution_guard.py` | `pytest` |
| `apps/acquisition/tests/unit/test_engine_adapters.py` | `pytest` |
| `apps/acquisition/tests/unit/test_evidence_writer.py` | `pytest` |
| `apps/acquisition/tests/unit/test_primproc_runtime.py` | `pytest` |
| `apps/acquisition/tests/unit/test_source_catalogue_full.py` | `pytest` |
| `apps/acquisition/tests/unit/test_source_executor_contracts.py` | `pytest` |
| `apps/acquisition/tests/unit/test_warc_adapter.py` | `pytest` |
| `apps/admission/tests/contract/test_no_auto_merge.py` | `pytest` |
| `apps/admission/tests/contract/test_resolution_history.py` | `pytest` |
| `apps/admission/tests/test_candidate.py` | `pytest` |
| `apps/admission/tests/test_claims.py` | `pytest` |
| `apps/admission/tests/test_effective_independence.py` | `pytest` |
| `apps/admission/tests/test_statement_consumer.py` | `pytest` |
| `apps/admission/tests/unit/test_cluster_transitivity.py` | `pytest` |
| `apps/admission/tests/unit/test_splink_adapter.py` | `pytest` |
| `apps/bulk-ingestion/tests/contract/test_archive_live_convergence.py` | `pytest` |
| `apps/bulk-ingestion/tests/unit/test_backfill.py` | `pytest` |
| `apps/bulk-ingestion/tests/unit/test_historical_replay.py` | `pytest` |
| `apps/control-plane/api/sse.py` | `starlette.responses` |
| `apps/control-plane/tests/contract/test_context_graph_contract.py` | `pytest` |
| `apps/control-plane/tests/integration/test_cc_temporality_api.py` | `pytest` |
| `apps/control-plane/tests/integration/test_closed_research_loop.py` | `pytest` |
| `apps/control-plane/tests/integration/test_donor_api.py` | `pytest` |
| `apps/control-plane/tests/integration/test_end_to_end_pipeline.py` | `pytest` |
| `apps/control-plane/tests/integration/test_entity_investigation_membership.py` | `pytest` |
| `apps/control-plane/tests/integration/test_epistemic_roundtrip.py` | `pytest` |
| `apps/control-plane/tests/integration/test_finding_evidence_chain.py` | `pytest` |
| `apps/control-plane/tests/integration/test_frontier_provenance.py` | `pytest` |
| `apps/control-plane/tests/integration/test_investigation_temporal.py` | `pytest` |
| `apps/control-plane/tests/integration/test_layer0_direct_pipeline.py` | `pytest` |
| `apps/control-plane/tests/integration/test_lineage_api.py` | `pytest` |
| `apps/control-plane/tests/integration/test_loop_closure.py` | `pytest` |
| `apps/control-plane/tests/integration/test_observation_immutability.py` | `pytest` |
| `apps/control-plane/tests/integration/test_orm_migration_parity.py` | `pytest` |
| `apps/control-plane/tests/integration/test_platform_assembly.py` | `pytest` |
| `apps/control-plane/tests/integration/test_quarantine.py` | `pytest` |
| `apps/control-plane/tests/integration/test_query_planner.py` | `pytest` |
| `apps/control-plane/tests/integration/test_resolution_api.py` | `pytest` |
| `apps/control-plane/tests/integration/test_science_api.py` | `pytest` |
| `apps/control-plane/tests/integration/test_seed_security.py` | `pytest` |
| `apps/control-plane/tests/integration/test_temporal_materialization_api.py` | `pytest` |
| `apps/control-plane/tests/integration/test_tenancy.py` | `pytest` |
| `apps/control-plane/tests/integration/test_tools_api.py` | `pytest` |
| `apps/control-plane/tests/test_auth_security.py` | `pytest` |
| `apps/control-plane/tests/test_auth_security.py` | `starlette.requests` |
| `apps/control-plane/tests/test_research_case_invariants.py` | `pytest` |
| `apps/control-plane/tests/test_research_case_projection.py` | `pytest` |
| `apps/control-plane/tests/test_research_case_reports.py` | `pytest` |
| `apps/control-plane/tests/unit/test_action_memory.py` | `pytest` |
| `apps/control-plane/tests/unit/test_approval_gate.py` | `pytest` |
| `apps/control-plane/tests/unit/test_assembly_structural_conflict.py` | `pytest` |
| `apps/control-plane/tests/unit/test_cc_temporality.py` | `pytest` |
| `apps/control-plane/tests/unit/test_cognitive_loop.py` | `pytest` |
| `apps/control-plane/tests/unit/test_context_engine.py` | `pytest` |
| `apps/control-plane/tests/unit/test_context_termination_and_catalogue.py` | `pytest` |
| `apps/control-plane/tests/unit/test_digest_gated_revision.py` | `pytest` |
| `apps/control-plane/tests/unit/test_dispatcher_backpressure.py` | `pytest` |
| `apps/control-plane/tests/unit/test_donor_patterns.py` | `pytest` |
| `apps/control-plane/tests/unit/test_entity_stream_persistence.py` | `pytest` |
| `apps/control-plane/tests/unit/test_fabric_anchor_guard.py` | `pytest` |
| `apps/control-plane/tests/unit/test_fabric_endpoints.py` | `pytest` |
| `apps/control-plane/tests/unit/test_invariant_reducer.py` | `pytest` |
| `apps/control-plane/tests/unit/test_migration_017_forward_only.py` | `pytest` |
| `apps/control-plane/tests/unit/test_migration_020_universal_relation.py` | `pytest` |
| `apps/control-plane/tests/unit/test_migration_024_investigation_entity_membership.py` | `pytest` |
| `apps/control-plane/tests/unit/test_monitor.py` | `pytest` |
| `apps/control-plane/tests/unit/test_network_analytics.py` | `pytest` |
| `apps/control-plane/tests/unit/test_ontology_registry.py` | `pytest` |
| `apps/control-plane/tests/unit/test_postgres_context_store.py` | `pytest` |
| `apps/control-plane/tests/unit/test_producer_binding_golden_path.py` | `pytest` |
| `apps/control-plane/tests/unit/test_query_degradation.py` | `pytest` |
| `apps/control-plane/tests/unit/test_query_fusion.py` | `pytest` |
| `apps/control-plane/tests/unit/test_rank_fusion_wiring.py` | `pytest` |
| `apps/control-plane/tests/unit/test_relation_candidate_storage_contract.py` | `pytest` |
| `apps/control-plane/tests/unit/test_relation_projection_outbox_contract.py` | `pytest` |
| `apps/control-plane/tests/unit/test_science_tda.py` | `pytest` |
| `apps/control-plane/tests/unit/test_search_core_selection.py` | `pytest` |
| `apps/control-plane/tests/unit/test_search_fusion_api.py` | `pytest` |
| `apps/control-plane/tests/unit/test_series_lifecycle.py` | `pytest` |
| `apps/control-plane/tests/unit/test_sse_stream.py` | `pytest` |
| `apps/control-plane/tests/unit/test_temporal_materialization_persistence.py` | `pytest` |
| `apps/control-plane/tests/unit/test_temporal_port.py` | `pytest` |
| `apps/control-plane/tests/unit/test_us1_core.py` | `pytest` |
| `apps/control-plane/tests/unit/test_workflows.py` | `pytest` |
| `apps/feedback/tests/test_branches.py` | `pytest` |
| `apps/feedback/tests/test_frontier_loop.py` | `pytest` |
| `apps/interpretation/parsers/documents.py` | `PIL` |
| `apps/interpretation/tests/conftest.py` | `pytest` |
| `apps/interpretation/tests/contract/test_parser_families.py` | `pytest` |
| `apps/interpretation/tests/contract/test_span_semantics.py` | `pytest` |
| `apps/interpretation/tests/integration/test_all_sources_parse.py` | `pytest` |
| `apps/interpretation/tests/test_deterministic_extraction.py` | `pytest` |
| `apps/interpretation/tests/test_evidence_manifest.py` | `pytest` |
| `apps/interpretation/tests/test_mention_binding_seam.py` | `pytest` |
| `apps/interpretation/tests/test_observation_consumer.py` | `pytest` |
| `apps/interpretation/tests/test_parser_adapter.py` | `pytest` |
| `apps/interpretation/tests/test_payload_binding.py` | `pytest` |
| `apps/interpretation/tests/test_payload_detection.py` | `pytest` |
| `apps/interpretation/tests/test_payload_hypotheses.py` | `pytest` |
| `apps/interpretation/tests/test_payload_parser_layer.py` | `pytest` |
| `apps/interpretation/tests/test_payload_routing.py` | `pytest` |
| `apps/interpretation/tests/test_payload_structure_producer.py` | `pytest` |
| `apps/interpretation/tests/test_primary_proc.py` | `pytest` |
| `apps/interpretation/tests/test_primary_proc_regex_mutant.py` | `pytest` |
| `apps/interpretation/tests/test_producer_migration.py` | `pytest` |
| `apps/interpretation/tests/test_relation_cue_coverage.py` | `pytest` |
| `apps/interpretation/tests/test_relations.py` | `pytest` |
| `apps/interpretation/tests/test_retriever_fusion.py` | `pytest` |
| `apps/interpretation/tests/test_signal_kind_channels.py` | `pytest` |
| `apps/interpretation/tests/test_signal_nary_contract.py` | `pytest` |
| `apps/interpretation/tests/test_syntactic_producer.py` | `pytest` |
| `apps/interpretation/tests/test_tenzir_live.py` | `pytest` |
| `apps/interpretation/tests/test_tenzir_normalization.py` | `pytest` |
| `apps/interpretation/tests/test_warc_reader.py` | `pytest` |
| `apps/projection/tests/contract/test_search_projection_manifest.py` | `pytest` |
| `apps/projection/tests/contract/test_tda_bridge_contract.py` | `pytest` |
| `apps/projection/tests/test_bm25s_backend.py` | `pytest` |
| `apps/projection/tests/test_tantivy_backend.py` | `pytest` |
| `apps/projection/tests/unit/test_claim_projection.py` | `pytest` |
| `apps/projection/tests/unit/test_diagram.py` | `pytest` |
| `apps/projection/tests/unit/test_features.py` | `pytest` |
| `apps/projection/tests/unit/test_graph_store_direction.py` | `pytest` |
| `apps/projection/tests/unit/test_h3_spatial.py` | `pytest` |
| `apps/projection/tests/unit/test_neo4j_relation_write.py` | `pytest` |
| `apps/projection/tests/unit/test_pipeline_directed.py` | `pytest` |
| `apps/projection/tests/unit/test_relation_store.py` | `pytest` |
| `apps/projection/tests/unit/test_takens.py` | `pytest` |
| `apps/projection/tests/unit/test_tda_insight.py` | `pytest` |
| `apps/projection/tests/unit/test_tda_pipeline_performance.py` | `pytest` |
| `apps/projection/tests/unit/test_temporal_graph.py` | `pytest` |
| `apps/projection/tests/unit/test_topological_invariant.py` | `pytest` |
| `apps/projection/tests/unit/test_validated.py` | `pytest` |
| `apps/science/context/tests/test_epistemic_algebra.py` | `pytest` |
| `apps/science/tests/contract/test_argumentation_contract.py` | `pytest` |
| `apps/science/tests/contract/test_causal_contract.py` | `pytest` |
| `apps/science/tests/contract/test_circularity_contract.py` | `pytest` |
| `apps/science/tests/contract/test_claim_contract.py` | `pytest` |
| `apps/science/tests/contract/test_completeness_contract.py` | `pytest` |
| `apps/science/tests/contract/test_coverage_independence_contract.py` | `pytest` |
| `apps/science/tests/contract/test_dialectics_contract.py` | `pytest` |
| `apps/science/tests/contract/test_discipline_adapters_contract.py` | `pytest` |
| `apps/science/tests/contract/test_dossier_contract.py` | `pytest` |
| `apps/science/tests/contract/test_enrichment_contract.py` | `pytest` |
| `apps/science/tests/contract/test_epistemic_contract.py` | `pytest` |
| `apps/science/tests/contract/test_event_emission_contract.py` | `pytest` |
| `apps/science/tests/contract/test_gluing_contract.py` | `pytest` |
| `apps/science/tests/contract/test_growth_contract.py` | `pytest` |
| `apps/science/tests/contract/test_hierarchy_contract.py` | `pytest` |
| `apps/science/tests/contract/test_hypothesis_contract.py` | `pytest` |
| `apps/science/tests/contract/test_locality_contract.py` | `pytest` |
| `apps/science/tests/contract/test_ontology_and_schema_stay_in_step.py` | `pytest` |
| `apps/science/tests/contract/test_operator_registry_contract.py` | `pytest` |
| `apps/science/tests/contract/test_operator_result_bridge.py` | `pytest` |
| `apps/science/tests/contract/test_query_compiler_contract.py` | `pytest` |
| `apps/science/tests/contract/test_robustness_contract.py` | `pytest` |
| `apps/science/tests/contract/test_science_seam_contract.py` | `pytest` |
| `apps/science/tests/contract/test_scope_lattice_contract.py` | `pytest` |
| `apps/science/tests/contract/test_structure_contract.py` | `pytest` |
| `apps/science/tests/contract/test_temporal_filter.py` | `pytest` |
| `apps/science/tests/contract/test_worldline_view_contract.py` | `pytest` |
| `apps/science/tests/integration/test_context_engine_chain.py` | `pytest` |
| `apps/science/tests/integration/test_live_asg_pipeline.py` | `pytest` |
| `apps/science/tests/integration/test_live_scope_lattice.py` | `pytest` |
| `apps/science/tests/test_anchoring.py` | `pytest` |
| `apps/science/tests/unit/test_econ.py` | `pytest` |
| `apps/science/tests/unit/test_kinetics.py` | `pytest` |
| `apps/science/tests/unit/test_landscape.py` | `pytest` |
| `apps/science/tests/unit/test_phase.py` | `pytest` |
| `apps/science/tests/unit/test_river_drift.py` | `pytest` |
| `apps/science/tests/unit/test_schelling.py` | `pytest` |
| `apps/science/tests/unit/test_scope.py` | `pytest` |
| `apps/science/tests/unit/test_series_embedding.py` | `pytest` |
| `apps/science/tests/unit/test_structure.py` | `pytest` |
| `apps/science/tests/unit/test_tda.py` | `pytest` |
| `apps/shared/events/dlq_durable.py` | `anyio` |
| `apps/shared/events/dlq_durable.py` | `anyio` |
| `apps/shared/events/dlq_durable.py` | `anyio` |
| `apps/shared/events/event_envelope_pb2.py` | `google.protobuf` |
| `apps/shared/events/event_envelope_pb2.py` | `google.protobuf` |
| `apps/shared/events/event_envelope_pb2.py` | `google.protobuf` |
| `apps/shared/events/event_envelope_pb2.py` | `google.protobuf` |
| `apps/shared/events/event_envelope_pb2.py` | `google.protobuf.internal` |
| `apps/shared/tests/constitution/test_constitution4_no_fabrication.py` | `pytest` |
| `apps/shared/tests/constitution/test_constitution_has_teeth.py` | `pytest` |
| `apps/shared/tests/constitution/test_i1_i3_immutability_and_preservation.py` | `pytest` |
| `apps/shared/tests/constitution/test_identity_subsystem_constitution.py` | `pytest` |
| `apps/shared/tests/constitution/test_iv_vi_tenancy_and_determinism.py` | `pytest` |
| `apps/shared/tests/contract/test_correlation.py` | `pytest` |
| `apps/shared/tests/contract/test_domain_invariants.py` | `pytest` |
| `apps/shared/tests/contract/test_donor_registry.py` | `pytest` |
| `apps/shared/tests/contract/test_donor_registry.py` | `packaging.requirements` |
| `apps/shared/tests/contract/test_donor_registry.py` | `packaging.version` |
| `apps/shared/tests/contract/test_entity_fabric.py` | `pytest` |
| `apps/shared/tests/contract/test_error_codes.py` | `pytest` |
| `apps/shared/tests/contract/test_event_envelope.py` | `pytest` |
| `apps/shared/tests/contract/test_evidence_span.py` | `pytest` |
| `apps/shared/tests/contract/test_evidence_span_roundtrip.py` | `pytest` |
| `apps/shared/tests/contract/test_metrics.py` | `pytest` |
| `apps/shared/tests/contract/test_ontology.py` | `pytest` |
| `apps/shared/tests/contract/test_operator_result.py` | `pytest` |
| `apps/shared/tests/contract/test_platform_gaps.py` | `pytest` |
| `apps/shared/tests/contract/test_platform_model.py` | `pytest` |
| `apps/shared/tests/contract/test_projection_manifest.py` | `pytest` |
| `apps/shared/tests/contract/test_review.py` | `pytest` |
| `apps/shared/tests/contract/test_single_publication_path.py` | `pytest` |
| `apps/shared/tests/contract/test_stage_outcome.py` | `pytest` |
| `apps/shared/tests/contract/test_statement.py` | `pytest` |
| `apps/shared/tests/contract/test_storage.py` | `pytest` |
| `apps/shared/tests/integration/test_idempotency.py` | `pytest` |
| `apps/shared/tests/integration/test_infra_connectivity.py` | `pytest` |
| `apps/shared/tests/integration/test_infra_connectivity.py` | `botocore` |
| `apps/shared/tests/integration/test_redpanda_emission.py` | `pytest` |
| `apps/shared/tests/unit/domain/test_domain_model.py` | `pytest` |
| `apps/shared/tests/unit/domain/test_graph_invariant.py` | `pytest` |
| `apps/shared/tests/unit/domain/test_temporal_materialization.py` | `pytest` |
| `apps/shared/tests/unit/domain/test_temporal_worldline.py` | `pytest` |
| `apps/shared/tests/unit/domain/test_temporal_worldline_store.py` | `pytest` |
| `apps/shared/tests/unit/donor/conftest.py` | `pytest` |
| `apps/shared/tests/unit/donor/test_evidence.py` | `pytest` |
| `apps/shared/tests/unit/donor/test_target.py` | `pytest` |
| `apps/shared/tests/unit/test_access_mode.py` | `pytest` |
| `apps/shared/tests/unit/test_acquisition_path.py` | `pytest` |
| `apps/shared/tests/unit/test_candidate_logical_identity.py` | `pytest` |
| `apps/shared/tests/unit/test_cc_session.py` | `pytest` |
| `apps/shared/tests/unit/test_cd6_unresolved_predicate.py` | `pytest` |
| `apps/shared/tests/unit/test_co_mention.py` | `pytest` |
| `apps/shared/tests/unit/test_commoncrawl.py` | `pytest` |
| `apps/shared/tests/unit/test_derivation_identity.py` | `pytest` |
| `apps/shared/tests/unit/test_dlq_durable.py` | `pytest` |
| `apps/shared/tests/unit/test_event_timestamps.py` | `pytest` |
| `apps/shared/tests/unit/test_evidence_context.py` | `pytest` |
| `apps/shared/tests/unit/test_evidence_lineage.py` | `pytest` |
| `apps/shared/tests/unit/test_evidence_store_guard.py` | `pytest` |
| `apps/shared/tests/unit/test_fusion.py` | `pytest` |
| `apps/shared/tests/unit/test_idempotent_consumer.py` | `pytest` |
| `apps/shared/tests/unit/test_investigation_context.py` | `pytest` |
| `apps/shared/tests/unit/test_layer_boundaries.py` | `pytest` |
| `apps/shared/tests/unit/test_measured_values.py` | `pytest` |
| `apps/shared/tests/unit/test_mention_occurrence_index.py` | `pytest` |
| `apps/shared/tests/unit/test_observation_gate_identity.py` | `pytest` |
| `apps/shared/tests/unit/test_observation_identity.py` | `pytest` |
| `apps/shared/tests/unit/test_open_world_predicates.py` | `pytest` |
| `apps/shared/tests/unit/test_participant_end_kind.py` | `pytest` |
| `apps/shared/tests/unit/test_predicate_signature.py` | `pytest` |
| `apps/shared/tests/unit/test_range_pull.py` | `pytest` |
| `apps/shared/tests/unit/test_relation_claim.py` | `pytest` |
| `apps/shared/tests/unit/test_relation_identity.py` | `pytest` |
| `apps/shared/tests/unit/test_relation_schema.py` | `pytest` |
| `apps/shared/tests/unit/test_research_lineage.py` | `pytest` |
| `apps/shared/tests/unit/test_resolution_mention_span.py` | `pytest` |
| `apps/shared/tests/unit/test_schema_hierarchy.py` | `pytest` |
| `apps/shared/tests/unit/test_secure_fetch.py` | `pytest` |
| `apps/shared/tests/unit/test_security.py` | `pytest` |
| `apps/shared/tests/unit/test_temporal_metrics.py` | `pytest` |
| `apps/specops/tests/conftest.py` | `pytest` |
| `apps/specops/tests/test_engagement.py` | `pytest` |
| `apps/specops/tests/test_ghostline.py` | `pytest` |
| `apps/specops/tests/test_roe_gate.py` | `pytest` |
| `apps/specops/tests/test_specops_ghostline_routers.py` | `pytest` |
| `apps/zero/tests/conftest.py` | `pytest` |
| `apps/zero/tests/test_cc_capture.py` | `pytest` |
| `apps/zero/tests/test_harvest_wave.py` | `pytest` |
| `apps/zero/tests/test_harvesters.py` | `pytest` |
| `apps/zero/tests/test_resolution.py` | `pytest` |
| `apps/zero/tests/test_type_detector.py` | `pytest` |
| `bench/tests/test_scale_scale.py` | `pytest` |

## Guarded gaps (tracked missing features)

The platform imports the module inside a guard and skips the dependent tests. These
are tracked gaps, not defects — but each one is a feature that is not implemented.

| From | Import |
|---|---|
| `apps/shared/tests/unit/test_relation_schema.py` | `domain.context_validation` |
