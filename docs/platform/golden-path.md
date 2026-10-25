# Golden path — person background analysis

Full person-background analysis: Layer 0 (broad, efficient collection over Kafka + lakehouse + sources) -> Layer 1 (extraction, merge, resolution, normalization of entity-artifacts and entity-invariants, plus relation extraction) -> Layer 2 (full context engine), grounded in the platform philosophy (event-driven, evidence-first, immutable observations, rebuildable projections, no fabrication).

Each capability is checked against the tree (`platform_model/golden_path.yaml`, a hybrid manifest: specs + the platform philosophy). Status is **reachability and maturity**, not correctness: `READY` means present, production-reachable and not a stub; `TEST_ONLY` means only tests reach it; `ORPHAN` means nothing imports it.

| Status | Capabilities |
|---|---|
| READY | 34 |
| PARTIAL | 0 |
| STUB | 0 |
| TEST_ONLY | 6 |
| ORPHAN | 4 |
| MISSING | 0 |

## Layer 0 — collection

| Capability | Status | Module | Reachability | Maturity |
|---|---|---|---|---|
| `source-catalogue` — Declarative source catalogue | READY | `apps/acquisition/sources/catalogue.py` | PRODUCTION | IMPLEMENTED |
| `source-executor` — Source executor | READY | `apps/acquisition/sources/executor.py` | PRODUCTION | IMPLEMENTED |
| `zero-harvesters` — Zero-layer contact harvesters | TEST_ONLY | `apps/zero/zero/harvesters/url.py` | TEST_ONLY | IMPLEMENTED |
| `acquisition-worker` — Acquisition worker (request -> fetch -> observation) | READY | `apps/acquisition/worker_acquisition.py` | PRODUCTION | IMPLEMENTED |
| `dispatcher-scheduler` — Two-stage dispatcher scheduler | READY | `apps/acquisition/dispatcher/scheduler.py` | PRODUCTION | IMPLEMENTED |
| `frontier` — Durable frontier | READY | `apps/control-plane/services/frontier.py` | PRODUCTION | IMPLEMENTED |
| `observation-gate` — Observation gate (content-addressed, immutable) | READY | `apps/shared/events/observation_gate.py` | PRODUCTION | IMPLEMENTED |
| `artifact-sink` — Artifact sink | READY | `apps/acquisition/artifact_sink.py` | PRODUCTION | IMPLEMENTED |
| `kafka-transport` — Kafka/Redpanda transport | READY | `apps/shared/events/kafka.py` | PRODUCTION | IMPLEMENTED |
| `bulk-ingestion` — Bulk historical ingestion (CC / Wayback / WARC) | TEST_ONLY | `apps/bulk-ingestion/backfill.py` | TEST_ONLY | IMPLEMENTED |
| `lakehouse` — Lakehouse (columnar / object layout) | ORPHAN | `apps/projection/lakehouse/__init__.py` | ORPHAN | PACKAGE_INIT |
| `region-backpressure` — Region backpressure | TEST_ONLY | `apps/acquisition/dispatcher/regional.py` | TEST_ONLY | IMPLEMENTED |

## Layer 1 — extraction, resolution, normalization

| Capability | Status | Module | Reachability | Maturity |
|---|---|---|---|---|
| `extraction-lane` — Deterministic extraction lane | READY | `apps/interpretation/extractors/lane.py` | PRODUCTION | IMPLEMENTED |
| `parsers` — Document parsers | READY | `apps/interpretation/parsers/documents.py` | PRODUCTION | IMPLEMENTED |
| `extractor-persons` — Person extraction | READY | `apps/interpretation/extractors/persons.py` | PRODUCTION | IMPLEMENTED |
| `extractor-orgs` — Organization extraction | READY | `apps/interpretation/extractors/orgs.py` | PRODUCTION | IMPLEMENTED |
| `extractor-places` — Place extraction | READY | `apps/interpretation/extractors/places.py` | PRODUCTION | IMPLEMENTED |
| `extractor-contacts` — Contact extraction | READY | `apps/interpretation/extractors/contacts.py` | PRODUCTION | IMPLEMENTED |
| `normalization` — Normalization post-pass | READY | `apps/interpretation/extractors/normalize.py` | PRODUCTION | IMPLEMENTED |
| `relation-extraction` — Relation extraction | READY | `apps/interpretation/extractors/relations.py` | PRODUCTION | IMPLEMENTED |
| `relation-signals` — Relation-signal producers | READY | `apps/interpretation/extractors/signals/protocol.py` | PRODUCTION | IMPLEMENTED |
| `signal-pipeline` — Relation-signal execution path | READY | `apps/control-plane/semantic_path/execution.py` | PRODUCTION | IMPLEMENTED |
| `entity-resolution` — Entity resolution | READY | `apps/admission/resolution/resolver.py` | PRODUCTION | IMPLEMENTED |
| `blocking` — Multi-strategy blocking | READY | `apps/admission/resolution/blocking.py` | PRODUCTION | IMPLEMENTED |
| `splink-adapter` — Splink linkage proposer | TEST_ONLY | `apps/admission/resolution/splink_adapter.py` | TEST_ONLY | IMPLEMENTED |
| `admission-engine` — Admission engine | READY | `apps/admission/engine/admission.py` | PRODUCTION | IMPLEMENTED |
| `independence` — Source independence | READY | `apps/admission/independence/independence.py` | PRODUCTION | IMPLEMENTED |
| `graph-invariant` — Graph invariant (entity-invariant) | READY | `apps/shared/domain/graph_invariant.py` | PRODUCTION | IMPLEMENTED |
| `relation-claim-store` — Relation-claim store | ORPHAN | `apps/control-plane/db/relation_claim_store.py` | ORPHAN | IMPLEMENTED |
| `semantic-fabric` — Semantic fabric | ORPHAN | `apps/shared/semantic/__init__.py` | ORPHAN | PACKAGE_INIT |

## Layer 2 — context engine

| Capability | Status | Module | Reachability | Maturity |
|---|---|---|---|---|
| `context-engine` — Context engine | READY | `apps/control-plane/context_engine/engine.py` | PRODUCTION | IMPLEMENTED |
| `context-store` — Postgres context store | READY | `apps/control-plane/context_engine/postgres_store.py` | PRODUCTION | IMPLEMENTED |
| `cognitive-loop` — Cognitive loop | READY | `apps/control-plane/context_engine/loop.py` | PRODUCTION | IMPLEMENTED |
| `obligations` — Obligations & saturation | READY | `apps/control-plane/context_engine/obligations.py` | PRODUCTION | IMPLEMENTED |
| `context-graph` — Context graph | TEST_ONLY | `apps/control-plane/context_engine/context_graph.py` | TEST_ONLY | IMPLEMENTED |
| `query-cycle` — Query cycle | READY | `apps/control-plane/context_engine/query_cycle.py` | PRODUCTION | IMPLEMENTED |
| `dossier` — Dossier assembly | READY | `apps/science/context/dossier.py` | PRODUCTION | IMPLEMENTED |
| `person-case-profile` — Person case profile pack | READY | `apps/control-plane/context_engine/person_case_profile.py` | PRODUCTION | IMPLEMENTED |
| `research-case-service` — Research case service | READY | `apps/control-plane/services/research_case_service.py` | PRODUCTION | IMPLEMENTED |
| `research-case-api` — Research case API | READY | `apps/control-plane/api/routes/research_cases.py` | PRODUCTION | IMPLEMENTED |
| `context-fabric` — Context fabric | READY | `apps/science/context/fabric.py` | PRODUCTION | IMPLEMENTED |

## Cross-cutting — projections & events

| Capability | Status | Module | Reachability | Maturity |
|---|---|---|---|---|
| `projection-search` — Search projection | TEST_ONLY | `apps/projection/search/indexer.py` | TEST_ONLY | IMPLEMENTED |
| `projection-graph` — Graph projection | ORPHAN | `apps/projection/graph/__init__.py` | ORPHAN | PACKAGE_INIT |
| `event-catalog` — Event catalog | READY | `apps/shared/events/topics.py` | PRODUCTION | IMPLEMENTED |

---

## Build plan (prioritized)

Non-READY capabilities, worst-first within each layer. `MISSING` before `ORPHAN` before `TEST_ONLY` before `STUB` before `PARTIAL`.

### Layer 0 — collection

| Capability | Status | Why it matters | Module |
|---|---|---|---|
| `lakehouse` | ORPHAN | Analytics-grade storage for the observation lake. | `apps/projection/lakehouse/__init__.py` |
| `bulk-ingestion` | TEST_ONLY | Backfill from archives is how a person's past is reached. | `apps/bulk-ingestion/backfill.py` |
| `region-backpressure` | TEST_ONLY | GO/THROTTLE/HALT gating per region. | `apps/acquisition/dispatcher/regional.py` |
| `zero-harvesters` | TEST_ONLY | The broadest, cheapest collection surface (emails, phones, domains, socials). | `apps/zero/zero/harvesters/url.py` |

### Layer 1 — extraction, resolution, normalization

| Capability | Status | Why it matters | Module |
|---|---|---|---|
| `relation-claim-store` | ORPHAN | Durable persistence of relation claims and their revision chain. | `apps/control-plane/db/relation_claim_store.py` |
| `semantic-fabric` | ORPHAN | Ontology-as-tool, regime, operators. | `apps/shared/semantic/__init__.py` |
| `splink-adapter` | TEST_ONLY | Probabilistic linkage behind the platform's resolution contract. | `apps/admission/resolution/splink_adapter.py` |

### Layer 2 — context engine

| Capability | Status | Why it matters | Module |
|---|---|---|---|
| `context-graph` | TEST_ONLY | The durable graph the analyst works in. | `apps/control-plane/context_engine/context_graph.py` |

### Cross-cutting — projections & events

| Capability | Status | Why it matters | Module |
|---|---|---|---|
| `projection-graph` | ORPHAN | Rebuildable relational serving projection. | `apps/projection/graph/__init__.py` |
| `projection-search` | TEST_ONLY | Rebuildable search over observations..findings. | `apps/projection/search/indexer.py` |
