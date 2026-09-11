# Research: Donor Pattern Integration

**Phase 0 output** — resolves all unknowns in Technical Context. Decision / Rationale / Alternatives format per `/speckit.plan`.

## R-1: FollowTheMoney statement model

- **Decision**: Model knowledge as **statements**, not bare triples. Every assertion carries `dataset_id`, `first_seen`, `last_seen`, `original_value`, `extraction_version`, `provenance`, and optional `valid_from`/`valid_until`. Dataset is a provenance boundary: reprints of one original collapse to one independent chain.
- **Rationale**: Spec FR-001/FR-002/FR-003; data-model §Assertion/§Observation already carries provenance; donor (FTM) validates statement-level provenance and dataset boundary as the data language of OSINT.
- **Alternatives considered**: bare subject→predicate→object triples (rejected: no provenance, no reprint detection), entity-centric only (rejected: loses statement granularity).

## R-2: OpenOSINT correlation-without-destruction

- **Decision**: Maintain a **correlation graph** over Candidates with `possible_match` edges (raw_pair_score + reasons) that never auto-merge into Entities. Identity comes only from admitted resolution (I-2/I-6). Extraction confidence stored separately from resolution score (I-7).
- **Rationale**: Spec FR-004/FR-005; existing `apps/admission/resolution/` blocking→pairwise→collective + `apps/admission/evidence/independence.py`; donor (OpenOSINT) proves correlation-before-merge preserves uncertainty and enables human review.
- **Alternatives considered**: auto-merge on score threshold (rejected: destructive, violates I-2), no correlation graph (rejected: loses possible_match semantics).

## R-3: Kipi investigation/evidence workspace

- **Decision**: The analyst works in **investigations** (targets, evidence objects, entities, relationships, timeline, sources, decisions), each evidence object carrying grading + provenance. UI surfaces investigation-first, not graph-first.
- **Rationale**: Spec FR-007; feature 001 `Investigation` model + webapp pages exist; donor (Kipi) validates investigation lifecycle + evidence grading as the analyst-facing model.
- **Alternatives considered**: graph-first UI (rejected: violates C-6 process-centric), no evidence grading (rejected: loses analyst decision provenance).

## R-4: SpiderFoot connector ecosystem

- **Decision**: All sources are **connectors** implementing the existing `AcquisitionWorker` contract (`capabilities()/estimate()/acquire()`), emitting standard Observation/Artifact/Mention/Candidate outputs. No bespoke per-source formats; a connector registry + per-source capabilities drive dispatcher choice.
- **Rationale**: Spec FR-008; contracts/acquisition-worker.md + Rust `worker-http`/`worker-browser` exist; donor (SpiderFoot) proves modular connector ecosystems scale.
- **Alternatives considered**: monolithic crawler (rejected: 50k-line mega_crawler anti-pattern), per-source bespoke outputs (rejected: breaks standard Observation chain).

## R-5: investigator evidence reasoning

- **Decision**: Extend `apps/admission/evidence/independence.py` with **corroboration vs copying** evaluation, **claim verdicts** (supported/contradicted/uncertain), triangulation, and **storyline** construction over consolidated evidence.
- **Rationale**: Spec FR-011; FR-002 requires publication_count ≠ independent_sources; donor (investigator) validates corroboration/claim-verdict reasoning for admission.
## R-6: reNgine recon orchestration

- **Decision**: Investigation launches become **recon plans** (Investigation → Acquisition Plan → Tasks → Kafka → Collectors → Observations) reusing the existing frontier/dispatcher/scheduler; a recon-plan is a typed investigation-scoped task group with monitoring.
- **Rationale**: Spec FR-009; feature 001 frontier/dispatcher/backpressure exist; donor (reNgine) validates scan-engine task orchestration patterns.
- **Alternatives considered**: import reNgine Django/Celery infra (rejected: vendor lock-in, violates C-5), no orchestration layer (rejected: no continuous recon).

## R-7: kafSIEM stream provenance + ontology packs

- **Decision**: Keep Kafka-native events with immutable provenance; add **OntologyPack** as a versioned, registry-validated schema pack (allowed entity types, properties, relations) consumed by extractors/admission. Events carry refs, never blobs (I-5).
- **Rationale**: Spec FR-012; EventEnvelope + Schema Registry exist; donor (kafSIEM) validates Kafka-native processing + ontology packs for entity graphs.
- **Alternatives considered**: JSON ad-hoc schemas (rejected: no evolution/validation), ontology in code (rejected: not versioned/registry-driven).

## R-8: PANO/Vitni analyst workbench

- **Decision**: Extend the React SPA with a **merged graph/timeline/map entity inspector** and **review controls** (ACCEPT/REJECT/UNCERTAIN persisted as immutable provenance). PANO is UX inspiration only (CC BY-NC; no code/assets).
- **Rationale**: Spec FR-006/FR-013; webapp GraphPanel/EntityViewPage exist; donors (PANO, Vitni) validate the graph/timeline/map workbench + review-as-provenance UX.
- **Alternatives considered**: copy PANO code (rejected: CC BY-NC license), no review UI (rejected: FR-006 unmet).

## R-9: NetForensicAI parser interface

- **Decision**: Add a **ParserAdapter** protocol (`can_parse(artifact) -> bool`, `parse(artifact) -> Findings`) to `apps/interpretation/parsers/registry.py`; deterministic findings for HTML/JSON/CSV/PDF/Email/Archive; heavy/unsafe parsers isolated behind the registry.
- **Rationale**: Spec FR-010; parser registry exists; donor (NetForensicAI) validates unified parser interface + evidence manifests.
- **Alternatives considered**: bespoke per-format parsing (rejected: no unified interface), inline unsafe parsers (rejected: violates C-7 isolation).

## R-10: Donor adoption governance

- **Decision**: Adopt **concepts/patterns only**; no donor code, no donor dependencies, no copied assets. License safety (PANO CC BY-NC = inspiration-only). Any future closer adoption requires an ADR.
- **Rationale**: Spec FR-014; Constitution C-5/C-7; avoids Frankenstein and vendor lock-in while capturing validated patterns.
- **Alternatives considered**: vendor-lock / wholesale import (rejected: violates constitution + licenses), ignore donors (rejected: loses proven patterns).