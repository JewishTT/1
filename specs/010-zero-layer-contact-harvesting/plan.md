# Implementation Plan: Zero-Layer Contact Harvesting Pipeline

**Spec**: `specs/010-zero-layer-contact-harvesting/spec.md` · **Created**: 2026-09-21 · **Status**: Active
**Input**: «Zero-layer: любой вход → контакты. Никакого ИИ в нулевом слое. spaCy + 100+ harvester-модулей. Native spec-ops. Лучший в мире фронтенд.»

## Summary

Фундаментальный нулевой слой платформы: универсальный конвейер "любой вход → контакты" с автоопределением типа, harvest-модулями и обратной связью в аналитику. Все specops-инструменты интегрируются **нативно** (без MCP wrappers). spaCy и 50+ enrichers на слое 3. Zero-layer не содержит ИИ.

## Technical approach

- **4-layer architecture**: Type Detection (regex+heuristics, no AI) → Harvesting (deterministic modules) → Entity Resolution (Fellegi-Sunter + graph topology, no AI) → Enrichment + Feedback (spaCy, 50+ enrichers, new seeds → L1)
- **Zero-layer is NO-AI**: Только deterministic regex, heuristics, format-validators, probabilistic matching (Fellegi-Sunter), graph topology. Никаких LLM/embeddings.
- **Spec-ops native**: caldera → Rust binding через pyo3; ael/АEL-lib → scenario DSL parser; SPEAR/PhantomStrike → imported-module в detectors; PhishSlayer → lab fixture; Labyrinth → Rust deception nodes; Sticks → compose fixture; TripleFantasy → pattern catalog.
- **Feedback loop**: сплайн `zero_layer.feedback_seeds` → слой 3 обогащает → новые seeds → слой 1 авто-re-harvest.
- **Observaton-gate**: все результаты через `apps/acquisition/observation_gate/` → immutable S3 + Kafka.

## Phases & deliverables

**Phase 0 — Type Detection (Layer 1)**
T100: Regex+heuristic type detector для 8 input types → `apps/zero/type_detector/`
T101: SeedInput schema + confidence scoring → `apps/shared/contracts/`
T102: Parallel harvester spawner → `apps/zero/harvesters/manager/`

**Phase 1 — Harvest Modules (Layer 1-2)**
T110: Domain harvesters (email-permutation, subdomain-discovery, DNS, breach, social) → `apps/zero/harvesters/domain/`
T111: Email/username harvesters (Maigret, Sherlock, Holehe, GitHub email extraction, breach) → `apps/zero/harvesters/email_username/`
T112: Phone harvesters (carrier-lookup, breach-first, social enumeration, QR) → `apps/zero/harvesters/phone/`
T113: Image harvesters (QR, EXIF, OCR, face) → `apps/zero/harvesters/image/`
T114: URL harvesters (content scraping, link extraction, embedded contacts) → `apps/zero/harvesters/url/`
T115: Free-text name harvesters (permutation, social, public records) → `apps/zero/harvesters/name/`

**Phase 2 — Entity Resolution (Layer 2)**
T120: Fellegi-Sunter probabilistic matcher (Splink port) → `apps/zero/resolution/matcher/`
T121: Graph topology: Louvain, transitive closure, community detection → `apps/zero/resolution/graph/`
T122: EntityResolutionObservation → observation_gate

**Phase 3 — Enrichment + Feedback (Layer 3)**
T130: spaCy NER pipeline (8 entity types) → `apps/zero/enrichment/spacy/`
T131: 50+ harvester-enrichers (reverse email→username→GitHub→name, phone→address, etc.) → `apps/zero/enrichment/modules/`
T132: Feedback loop → Kafka `zero_layer.feedback_seeds` → type_detector авто-trigger
T133: EnrichmentObservation → observation_gate

**Phase 4 — Native Spec-Ops Integration**
T140: caldera Rust binding → `apps/specops/caldera/`
T141: ael/АEL-lib parser → scenario DSL → `apps/specops/scenarios/`
T142: SPEAR/PhantomStrike detectors → `apps/interpretation/detectors/`
T143: PhishSlayer lab fixture → `deploy/specops/sat/`
T144: Labyrinth Rust deception nodes → `apps/specops/deception/`
T145: Sticks compose fixture → `deploy/specops/lab/`
T146: TripleFantasy pattern catalog → `docs/kb/specops/patterns/`
T147: AzureAD playbook → `docs/kb/identity/`
T148: Operation-Molasses toolkit → `toolkit/`

**Phase 5 — Tactical Frontend**
T150: D3.js force-graph component → `apps/webapp/src/components/zero/LayerGraph.tsx`
T151: Entity inspector with confidence-страйпы → `apps/webapp/src/components/zero/EntityInspector.tsx`
T152: SSE status stream → `apps/webapp/src/components/zero/HarvestStream.tsx`
T153: Magma operation-matrix → `apps/webapp/src/components/specops/OperationMatrix.tsx`
T154: Dark tactical theme + styles → `apps/webapp/src/styles/zero/`

**Phase 6 — Verification**
T160: bench/run --scenario zero-layer-smoke (8 seed types → harvest → resolve → enrich → feedback)
T161: Attribution audit (T001 from spec 009) + guarding tests
T162: SC-001…SC-010 validation

## Constitution check
- **Event-driven / evidence-first**: zero-layer emits immutable observations via observation_gate.
- **No AI in zero-layer**: только deterministic regex + heuristics + Fellegi-Sunter + graph topology.
- **Rebuildable projections**: enrichment results → claims/assertions (rebuildable from observations).
- **Native specops**: direct code integration, no service abstraction. Lab-isolation только для контента, не для кода.
- **Feedback loop**: observations → feedback_seeds → re-harvest.

## Risks & mitigations
| Risk | Mitigation |
|---|---|
| Rate limiting на harvesters | adaptive pacing + proxy pool |
| Spec-ops legal risk | изолированный lab-contour + audit logging |
| spaCy model size | lazy load + GPU budget |
| D3.js perf на больших graph | WebGL fallback + canvas clustering |
| Zero-layer может дать не точные контакты | confidence scoring (deterministic) + human review flag |

## Definition of done
SC-001…SC-010 закрыты. Zero-layer принимает 8 input types, harvest + resolve + enrich + feedback работает end-to-end. Все specops нативно интегрированы. Frontend D3.js + Magma matrix работают с SSE. bench/run --scenario zero-layer-smoke проходит.