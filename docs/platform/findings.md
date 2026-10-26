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

265 platform modules are not imported by any test. Sample:

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
| `apps/bulk-ingestion/historical/__init__.py` |
| `apps/control-plane/__init__.py` |
| `apps/control-plane/api/path_shim.py` |
| `apps/control-plane/api/routes/connectors.py` |
| `apps/control-plane/api/routes/discovery.py` |
| `apps/control-plane/api/routes/dossier.py` |

## Unresolved imports (by evidence)

0 platform imports have no resolved target (local/stale/guarded-local); 1 tracked guarded gaps; 0 undeclared (not platform/stdlib/installed/declared).

| From | Import | Kind |
|---|---|---|
| `apps/shared/tests/unit/test_relation_schema.py` | `domain.context_validation` | guarded-gap |
