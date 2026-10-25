# Components

One row per deployable unit / package root.

## `acquisition`

Discovery, frontier, dispatcher, content router, HTTP/browser workers, ArtifactSink.

Python modules: **101** · TypeScript modules: **0**

<details><summary>module sample</summary>

```
apps.acquisition._measure_coverage
apps.acquisition._probe_catalogue
apps.acquisition._prove_airbyte
apps.acquisition._prove_backbone
apps.acquisition._prove_readback
apps.acquisition._prove_searxng
apps.acquisition._prove_tools
apps.acquisition.adapters
apps.acquisition.adapters._ingest
apps.acquisition.adapters.browsertrix
apps.acquisition.adapters.browsertrix.collect
apps.acquisition.adapters.common_crawl
apps.acquisition.adapters.commoncrawl
apps.acquisition.adapters.commoncrawl.index
apps.acquisition.adapters.discovery
apps.acquisition.adapters.discovery.commoncrawl_index
apps.acquisition.adapters.discovery.contracts
apps.acquisition.adapters.discovery.crtsh
apps.acquisition.adapters.discovery.linkgraph
apps.acquisition.adapters.discovery.registry
apps.acquisition.adapters.discovery.wayback_cdx
apps.acquisition.adapters.heritrix
apps.acquisition.adapters.heritrix.collect
apps.acquisition.adapters.nutch
apps.acquisition.adapters.nutch.collect
apps.acquisition.adapters.registry
apps.acquisition.adapters.scrapy
apps.acquisition.adapters.scrapy.spider
apps.acquisition.adapters.scrapy.stream
apps.acquisition.adapters.sec_edgar
apps.acquisition.adapters.stormcrawler
apps.acquisition.adapters.stormcrawler.collect
apps.acquisition.adapters.warc
apps.acquisition.adapters.warc.collect
apps.acquisition.artifact_sink
apps.acquisition.cc_extract
apps.acquisition.cc_plan
apps.acquisition.dispatcher
apps.acquisition.dispatcher.kafka_producer
apps.acquisition.dispatcher.plan_driver
```

</details>

## `admission`

Blocking/resolution, assertion extraction, source independence, calibrated admission.

Python modules: **30** · TypeScript modules: **0**

<details><summary>module sample</summary>

```
apps.admission.engine
apps.admission.engine.admission
apps.admission.engine.assertions
apps.admission.engine.calibration
apps.admission.engine.intake
apps.admission.engine.storyline
apps.admission.engine.temporal
apps.admission.independence
apps.admission.independence.independence
apps.admission.resolution
apps.admission.resolution.blocking
apps.admission.resolution.candidate
apps.admission.resolution.cluster
apps.admission.resolution.collective
apps.admission.resolution.decision_store
apps.admission.resolution.gate
apps.admission.resolution.resolver
apps.admission.resolution.span
apps.admission.resolution.splink_adapter
apps.admission.tests.contract.test_no_auto_merge
apps.admission.tests.contract.test_resolution_history
apps.admission.tests.test_admission
apps.admission.tests.test_candidate
apps.admission.tests.test_claims
apps.admission.tests.test_collective_export
apps.admission.tests.test_effective_independence
apps.admission.tests.test_intake
apps.admission.tests.test_statement_consumer
apps.admission.tests.unit.test_cluster_transitivity
apps.admission.tests.unit.test_splink_adapter
```

</details>

## `bench`

E2E smoke harness, micro-benchmarks, knowledge-quality harness.

Python modules: **16** · TypeScript modules: **0**

<details><summary>module sample</summary>

```
bench.bench
bench.bench.harness
bench.chaos
bench.chaos.bench_replay
bench.collection.bench_collection
bench.collection.bench_scale
bench.extraction.bench_extract
bench.fixtures.extraction._generate
bench.fixtures.global_upgrade.epistemic.build_corpus
bench.fixtures.global_upgrade.identity.build_corpus
bench.knowledge.quality
bench.run
bench.science.bench_structural
bench.tests.test_harness
bench.tests.test_knowledge
bench.tests.test_scale_scale
```

</details>

## `bulk-ingestion`

Common Crawl / Wayback / WARC / dataset backfill profiles.

Python modules: **6** · TypeScript modules: **0**

<details><summary>module sample</summary>

```
apps.bulk-ingestion.backfill
apps.bulk-ingestion.historical
apps.bulk-ingestion.historical.replay
apps.bulk-ingestion.tests.contract.test_archive_live_convergence
apps.bulk-ingestion.tests.unit.test_backfill
apps.bulk-ingestion.tests.unit.test_historical_replay
```

</details>

## `control-plane`

FastAPI control plane: investigations, context engine, frontier, review, query planner, HTTP API.

Python modules: **227** · TypeScript modules: **0**

<details><summary>module sample</summary>

```
apps.control-plane
apps.control-plane.api
apps.control-plane.api.auth
apps.control-plane.api.main
apps.control-plane.api.path_shim
apps.control-plane.api.routes
apps.control-plane.api.routes.connectors
apps.control-plane.api.routes.discovery
apps.control-plane.api.routes.dossier
apps.control-plane.api.routes.entities
apps.control-plane.api.routes.fabric
apps.control-plane.api.routes.findings
apps.control-plane.api.routes.investigation_context
apps.control-plane.api.routes.investigations
apps.control-plane.api.routes.manual_assertions
apps.control-plane.api.routes.metrics
apps.control-plane.api.routes.network
apps.control-plane.api.routes.platform
apps.control-plane.api.routes.quarantine
apps.control-plane.api.routes.research_cases
apps.control-plane.api.routes.resolutions
apps.control-plane.api.routes.science_causal
apps.control-plane.api.routes.science_claims
apps.control-plane.api.routes.science_hypotheses
apps.control-plane.api.routes.science_review
apps.control-plane.api.routes.science_robustness
apps.control-plane.api.routes.science_structure
apps.control-plane.api.routes.science_tda
apps.control-plane.api.routes.science_temporal
apps.control-plane.api.routes.search
apps.control-plane.api.routes.search_rebuild
apps.control-plane.api.routes.specops_counterintel
apps.control-plane.api.routes.specops_emulation
apps.control-plane.api.routes.specops_engagement
apps.control-plane.api.routes.specops_forensics
apps.control-plane.api.routes.specops_ghostline
apps.control-plane.api.routes.specops_phishing
apps.control-plane.api.routes.specops_roe
apps.control-plane.api.routes.specops_social
apps.control-plane.api.routes.temporal_materializations
```

</details>

## `feedback`

Recrawl/priority feedback, stopping policy.

Python modules: **11** · TypeScript modules: **0**

<details><summary>module sample</summary>

```
apps.feedback.feedback
apps.feedback.feedback.branch
apps.feedback.feedback.branch.entity
apps.feedback.feedback.branch.finding
apps.feedback.feedback.branch.source
apps.feedback.feedback.frontier
apps.feedback.feedback_engine
apps.feedback.stopping
apps.feedback.tests.test_branches
apps.feedback.tests.test_feedback
apps.feedback.tests.test_frontier_loop
```

</details>

## `interpretation`

Parsers, deterministic entity-extraction stack, NER/normalization, candidate aggregation.

Python modules: **112** · TypeScript modules: **0**

<details><summary>module sample</summary>

```
apps.interpretation
apps.interpretation._consume_searxng
apps.interpretation._prove_primproc
apps.interpretation.aggregation.candidates
apps.interpretation.dictionaries
apps.interpretation.dictionaries.build_mini
apps.interpretation.dictionaries.cities
apps.interpretation.dictionaries.companies
apps.interpretation.dictionaries.countries
apps.interpretation.dictionaries.data
apps.interpretation.dictionaries.first_names
apps.interpretation.dictionaries.sanctions
apps.interpretation.evidence
apps.interpretation.evidence.manifest
apps.interpretation.extract_demo
apps.interpretation.extractors
apps.interpretation.extractors.contacts
apps.interpretation.extractors.dictionary_entities
apps.interpretation.extractors.lane
apps.interpretation.extractors.language
apps.interpretation.extractors.matching
apps.interpretation.extractors.normalize
apps.interpretation.extractors.orgs
apps.interpretation.extractors.payload
apps.interpretation.extractors.payload.hypotheses
apps.interpretation.extractors.payload.keytable
apps.interpretation.extractors.payload.structure
apps.interpretation.extractors.persons
apps.interpretation.extractors.places
apps.interpretation.extractors.registry
apps.interpretation.extractors.relations
apps.interpretation.extractors.signals
apps.interpretation.extractors.signals.lexical
apps.interpretation.extractors.signals.links
apps.interpretation.extractors.signals.mentions
apps.interpretation.extractors.signals.metadata
apps.interpretation.extractors.signals.protocol
apps.interpretation.extractors.signals.signal
apps.interpretation.extractors.signals.syntactic
apps.interpretation.extractors.signals.tables
```

</details>

## `platform_model`

The generator that produces docs/platform from the tree.

Python modules: **13** · TypeScript modules: **0**

<details><summary>module sample</summary>

```
platform_model
platform_model.architecture
platform_model.build
platform_model.events
platform_model.evidence
platform_model.facts
platform_model.gaps
platform_model.golden_path
platform_model.maturity
platform_model.narrative
platform_model.reachability
platform_model.scanners
platform_model.semantic
```

</details>

## `projection`

Graph abstraction, search/analytics projectors, snapshots, TDA.

Python modules: **65** · TypeScript modules: **0**

<details><summary>module sample</summary>

```
apps.projection.analytics
apps.projection.analytics.clickhouse_client
apps.projection.analytics.projector
apps.projection.analytics.store
apps.projection.analytics.temporal_graph
apps.projection.graph
apps.projection.graph.abstraction
apps.projection.graph.adjacency
apps.projection.graph.neo4j
apps.projection.graph.relation_store
apps.projection.graph.snapshot
apps.projection.lakehouse
apps.projection.lakehouse.river.lake
apps.projection.metrics
apps.projection.metrics.community
apps.projection.metrics.hypergraph_metrics
apps.projection.metrics.network_measures
apps.projection.metrics.temporal_paths
apps.projection.path_shim
apps.projection.search
apps.projection.search.bm25s_backend
apps.projection.search.index
apps.projection.search.indexer
apps.projection.search.mappings
apps.projection.search.projector
apps.projection.search.publisher
apps.projection.search.quickwit
apps.projection.search.relevance
apps.projection.search.tantivy_backend
apps.projection.spatial.h3_index
apps.projection.streams
apps.projection.streams.jobs
apps.projection.tda
apps.projection.tda.bridge
apps.projection.tda.diagram
apps.projection.tda.features
apps.projection.tda.insight
apps.projection.tda.pipeline
apps.projection.tda.validated
apps.projection.temporal_materialization
```

</details>

## `root`

Repo-root wiring: pytest conftest and the import roots it installs.

Python modules: **1** · TypeScript modules: **0**

<details><summary>module sample</summary>

```
conftest
```

</details>

## `science`

Context operators, fabric, retrieval economics, abstraction ladder.

Python modules: **139** · TypeScript modules: **0**

<details><summary>module sample</summary>

```
apps.science._events
apps.science.anchoring
apps.science.beliefs
apps.science.beliefs.landscape
apps.science.causal
apps.science.causal.infer
apps.science.causal.model
apps.science.causal.scope
apps.science.claims
apps.science.claims.calibration
apps.science.claims.model
apps.science.claims.provenance
apps.science.claims.query
apps.science.claims.registry
apps.science.claims.status
apps.science.context
apps.science.context.argumentation
apps.science.context.bridge
apps.science.context.circularity
apps.science.context.completeness
apps.science.context.coverage
apps.science.context.dialectics
apps.science.context.dossier
apps.science.context.enrichment
apps.science.context.epistemic
apps.science.context.fabric
apps.science.context.growth
apps.science.context.hierarchy
apps.science.context.lattice
apps.science.context.locality
apps.science.context.natural_language
apps.science.context.operators
apps.science.context.operators.adapters
apps.science.context.operators.base
apps.science.context.operators.compatibility
apps.science.context.operators.contract_bridge
apps.science.context.operators.gluing
apps.science.context.operators.registry
apps.science.context.query_ast
apps.science.context.query_binding
```

</details>

## `shared`

Contracts, events, domain invariants, storage, security — the substrate every app imports.

Python modules: **194** · TypeScript modules: **0**

<details><summary>module sample</summary>

```
apps.shared.config
apps.shared.config.settings
apps.shared.conftest
apps.shared.contracts
apps.shared.contracts.canonical
apps.shared.contracts.error_codes
apps.shared.contracts.evidence_span
apps.shared.contracts.operator_result
apps.shared.contracts.projection_manifest
apps.shared.contracts.stage_outcome
apps.shared.datasets
apps.shared.datasets.build
apps.shared.domain
apps.shared.domain.access_mode
apps.shared.domain.acquisition_artifact
apps.shared.domain.capture
apps.shared.domain.co_mention
apps.shared.domain.derivation
apps.shared.domain.dynamics
apps.shared.domain.entity
apps.shared.domain.entity_identity
apps.shared.domain.evidence_context
apps.shared.domain.evidence_lineage
apps.shared.domain.fabric
apps.shared.domain.graph_invariant
apps.shared.domain.hypergraph
apps.shared.domain.investigation_context
apps.shared.domain.mention_occurrence_index
apps.shared.domain.observation_identity
apps.shared.domain.ontology
apps.shared.domain.predicate_hypothesis
apps.shared.domain.predicate_signature
apps.shared.domain.predicate_voice
apps.shared.domain.property
apps.shared.domain.relation_candidate
apps.shared.domain.relation_claim
apps.shared.domain.relation_claim_material
apps.shared.domain.relation_identity
apps.shared.domain.relation_participant
apps.shared.domain.relation_schema
```

</details>

## `specops`

Isolated spec-ops lab profile (never in the routine path).

Python modules: **30** · TypeScript modules: **0**

<details><summary>module sample</summary>

```
apps.specops
apps.specops.counterintel
apps.specops.emulation
apps.specops.engagement
apps.specops.engagement.config
apps.specops.engagement.fabric
apps.specops.engagement.funnel
apps.specops.engagement.taxonomy
apps.specops.forensics
apps.specops.ghostline
apps.specops.ghostline.catalog
apps.specops.ghostline.config
apps.specops.ghostline.engine
apps.specops.ghostline.ledger
apps.specops.ghostline.loader
apps.specops.ghostline.redaction
apps.specops.ghostline.runtime
apps.specops.ghostline.service
apps.specops.ghostline.telephony
apps.specops.ghostline.voices
apps.specops.phishing
apps.specops.roe
apps.specops.roe.gate
apps.specops.social
apps.specops.tests.conftest
apps.specops.tests.test_engagement
apps.specops.tests.test_ghostline
apps.specops.tests.test_roe_gate
apps.specops.tests.test_specops_ghostline_routers
apps.specops.tests.test_specops_routers
```

</details>

## `tools`

Generators, capability/owner/donor tools, probes.

Python modules: **10** · TypeScript modules: **0**

<details><summary>module sample</summary>

```
tools.append_zero_frontend_a
tools.append_zero_frontend_b
tools.append_zero_inventory
tools.append_zero_sources_a
tools.append_zero_sources_b
tools.fix_zero_layer_doc
tools.specs.build_capability_matrix
tools.specs.build_donor_registry
tools.specs.build_owner_map
tools.strip_zero_inventory
```

</details>

## `webapp`

React analyst surfaces: investigation, search, entity, finding, ops, lineage.

Python modules: **0** · TypeScript modules: **254**


## `zero`

Zero-layer contact harvesting from arbitrary seeds.

Python modules: **30** · TypeScript modules: **0**

<details><summary>module sample</summary>

```
apps.zero.tests.conftest
apps.zero.tests.test_cc_capture
apps.zero.tests.test_enrichment
apps.zero.tests.test_harvest_wave
apps.zero.tests.test_harvesters
apps.zero.tests.test_resolution
apps.zero.tests.test_type_detector
apps.zero.zero
apps.zero.zero.cc_capture
apps.zero.zero.enrichment
apps.zero.zero.enrichment.feedback
apps.zero.zero.enrichment.modules
apps.zero.zero.harvest_wave
apps.zero.zero.harvesters
apps.zero.zero.harvesters.contracts
apps.zero.zero.harvesters.domain
apps.zero.zero.harvesters.git
apps.zero.zero.harvesters.image
apps.zero.zero.harvesters.modules
apps.zero.zero.harvesters.phone
apps.zero.zero.harvesters.registry
apps.zero.zero.harvesters.transport
apps.zero.zero.harvesters.url
apps.zero.zero.harvesters.username
apps.zero.zero.observation_gate
apps.zero.zero.resolution
apps.zero.zero.resolution.fellegi_sunter
apps.zero.zero.resolution.graph
apps.zero.zero.resolution.similarity
apps.zero.zero.type_detector
```

</details>
