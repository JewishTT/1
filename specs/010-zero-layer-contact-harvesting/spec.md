# Feature Specification: Zero-Layer Contact Harvesting Pipeline

**Feature Branch**: `010-zero-layer-contact-harvesting`
**Created**: 2026-09-21
**Status**: Draft
**Input**: «Zero-layer: любой вход → контакты. Никакого ИИ в нулевом слое. spaCy + 100+ harvester-модулей. Native spec-ops. Лучший в мире фронтенд. Feedback loop между слоем сбора (1) и аналитики (3).»

## User Scenarios & Testing

### User Story 1 - Universal Seed Ingestion (P0)
Аналитик вставляет любой seed (имя/email/username/домен/телефон/URL/изображение). Платформа автоопределяет тип через regex+heuristics, запускает harvest-модули, выдаёт enriched контакты с детерминированными confidence-оценками. **Никакого ИИ в zero-layer**.

**Acceptance**:
1. **Given** seed = `microsoft.com`, **When** "Harvest", **Then** Domain-тип → email-permutation + subdomain-discovery + DNS → 50+ контактов, confidence ≥0.7.
2. **Given** seed = `+12025550199`, **When** "Harvest", **Then** Phone-тип → carrier-lookup + breach-search + social-enumeration → связанные email/username/social.
3. **Given** seed = `https://github.com/octocat`, **When** "Harvest", **Then** Username/URL-тип → git-email-discovery + commit-extraction → verified email.
4. **Given** изображение с QR/EXIF, **When** загрузить, **Then** Image-тип → QR/EXIF extraction → embedded контакты.
### User Story 2 - Native Spec-Ops Integration (P0)
Все спецоперационные инструменты интегрируются **нативно** — direct code import/vendoring, без MCP wrappers, без service-abstraction. caldera → Rust binding; ael → scenario DSL; SPEAR/PhantomStrike → detectors; PhishSlayer → lab fixture; Labyrinth → native Rust deception; Sticks → compose fixture; TripleFantasy → pattern catalog; AzureAD → KB.

**Acceptance**:
1. **Given** AEL plan в KB, **When** "Launch Emulation", **Then** direct parser → caldera Operation через Rust binding → telemetry → event-bus → webapp dashboard (real-time SSE).
2. **Given** SPEAR модели, **When** тренировка, **Then** TextCNN/BERT/AI-скоринг импортированы прямо в `apps/interpretation/detectors/`.
3. **Given** Labyrinth deception, **When** сканер, **Then** deception-узлы как native Rust services в `apps/specops/deception/`.
4. **Given** Sticks fixture, **When** lab запуск, **Then** Docker-compose монтируется в `deploy/specops/lab/`.

### User Story 3 - Tactical Frontend (P0)
D3.js force-directed graph, real-time таймлайн, entity inspector с confidence-страйпами, SSE-поток статуса, dark tactical тема.

**Acceptance**:
1. **Given** graph построен, **When** клик на node, **Then** inspector: контакты, confidence-баллы, provenance chain, spec-ops operations.
2. **Given** specops operation, **When** events потокуются, **Then** Magma operation-matrix обновляется через SSE.
3. **Given** timeline скролл, **When** остановка на event, **Then** context window: source, enrichment chain, связанные entities.

## Requirements

### Functional Requirements
- **FR-001**: Accept любой input type: free-text имя, email, username, домен, телефон, URL, изображение (JPG/PNG/SVG/WebP), PDF, DOCX (embedded contacts).
- **FR-002**: Auto-detect input type без ИИ: regex + format-validators + heuristics. Confidence = deterministic score (0.0–1.0).
- **FR-003**: Spawn harvest-модули based on detected type. Each harvester emits `ObservationCandidate` с provenance: source_module, method, raw_fields, confidence.
- **FR-004**: Integrate ALL specops tools нативно: direct code import/vendoring, без MCP wrappers. caldera → Rust binding; ael/АEL-lib → scenario DSL; SPEAR/PhantomStrike → imported-module в detectors; PhishSlayer/BluePhish → lab fixture; Labyrinth → native Rust deception nodes; Sticks → lab-compose; TripleFantasy → pattern catalog; AzureAD → KB.
- **FR-005**: Feedback loop: entities discovered на слое 3 → обратно в слой 1 как новые seeds → auto re-harvest.
- **FR-006**: spaCy + 50+ enricher-модулей на слое 3: name, email, phone, address, org, ip, crypto wallet, social handle.
- **FR-007**: Frontend D3.js force-graph с node типизацией (domain/email/phone/username/url/image).
- **FR-008**: Frontend Magma-style operation-matrix с real-time SSE для spec-ops.
- **FR-009**: Emit observations через `apps/acquisition/observation_gate/` → immutable S3 + Kafka → interpretation.
- **FR-010**: Entity resolution на слое 3: Fellegi-Sunter + graph topology (Louvain, transitive closure), НЕ LLM.
- **FR-011**: Parallel harvest: multiple seeds → concurrent harvester workers → merged results.
- **FR-012**: Emit `harvest_cycle_complete` event после каждой wave: seeds_in, contacts_out, confidence_dist, new_seeds_discovered.
- **FR-013**: ALL mentioned zero-layer repos MUST be cloned into `donors/` and inventoried: 52 new repos (see §0.12 inventory) — sherlock-project/sherlock, kaifcodec/user-scanner, Greyjedix/Profil3r, martinvigo/email2phonenumber, codeGROOVE-dev/gh-mailto, grisuno/estorides, grisuno/lazyaddon + 46 others; unreachable URLs replaced or documented (mailhound/phone-number-search/intel-harvester/specter → 404-substitutions).
- **FR-014**: Zero-layer MUST ingest from any source class: web (thecrowler/CommonCrawl/Heritrix/Nutch/StormCrawler/Browsertrix/SpiderFoot/secureflow-intel), Tor/.onion (OnionSearch + Tor egress pool + paste/forge-паттерн), Telegram/WhatsApp/Instagram (TDLib adapter + tgstat/telemetr + DIGI-NETRA/ignorant/EmailExtractWithProxyApp), Git (gitsnitch/gh-mailto/gitrecon/GitFive), breach (mosint/user-scanner/HIBP/DeHashed), phone (phoneinfoga/phone-osint-framework/Phunter/SearchPhone), net (trident), keyless frameworks (osint-terminal/argus-cotcollective/seekr/phantomsignal/Aperture/osint-web-mcp/estorides/lazyaddon).
- **FR-015**: Frontend MUST be a single tactical workbench с тремя платформенными модулями (OSINT / Экономика / Spec-Ops), питающимися из OSINT-ядра: CommandBar с universal seed input, HarvestRail (SSE), ForceGraphCanvas (D3 v7 + WebGL fallback), EntityInspector (contacts/provenance/claims), TimelineScrubber, OperationMatrix (Magma-паттерн), DeceptionView (Labyrinth), PhishKPI, EconLens, ReportsPalette (OSIA INTSUM/SITREP).

### Key Entities
- **SeedInput**: any user-provided string/file. raw_value, detected_type, confidence, metadata.
- **HarvestModule**: deterministic enrichment worker. name, capability, required_input_type, method, license, attribution.
- **ContactEntity**: extracted contact. email, phone, username, domain, full_name, social_profiles, confidence, source_chain.
- **HarvestObservation**: immutable result. seed_input_id, module_id, raw_output, extracted_fields, confidence_score, provenance_chain.
- **SpecOpsOperation**: native caldera operation. operation_id, plan_id, adversary_profile, agents_active, event_stream_ref.
- **ZeroLayerSeed**: entity from layer 3 → layer 1. original_seed_id, derived_value, derived_type, confidence, reason.

## Context

Zero-layer — фундаментальный слой под acquisition layer. Предоставляет "любой вход → контакты".

```
INPUT → LAYER 1: TYPE DETECTION (regex+heuristics, no AI) → typed seed
  → LAYER 2: ENTITY RESOLUTION (Fellegi-Sunter + graph topology, no AI)
  → LAYER 3: ENRICHMENT + FEEDBACK (spaCy + 50+ enrichers → new seeds → L1)
  → OUTPUT: ContactEntities → ObservationGate → immutable S3 + Kafka
```

## Success Criteria
- **SC-001**: Accepts 8 input types, auto-detects 95%+ (deterministic confidence ≥0.85).
- **SC-002**: Spawns correct harvest-модули, producing ≥1 ContactEntity per seed.
- **SC-003**: 14 specops доноров integrated natively (no abstraction).
- **SC-004**: Entity resolution: Fellegi-Sunter + graph topology (не LLM), explainable confidence.
- **SC-005**: ≥15% новых seeds от слоя 3 → слой 1 для auto re-harvest.
- **SC-006**: D3.js force-graph с real-time SSE updates.
- **SC-007**: spaCy + 50+ enricher-модулей, extract ≥5 entity типов.
- **SC-008**: Observations → Immutable S3 + Kafka через observation_gate.
- **SC-009**: Magma operation-matrix для spec-ops с real-time SSE.
- **SC-010**: bench/run --scenario zero-layer-smoke проходит.
- **SC-011**: 100% mentioned repos в `donors/` — inventory §0.12 полон: 52/52 клонировано (проверено по рабочему дереву), недоступные URL задокументированы с заменами.
- **SC-012**: Frontend-дизайн §0.13 покрывает все 10 компонентов + дизайн-систему + три модуля над OSINT-ядром; каждый компонент имеет паттерн-донора и target-файл.
- **SC-013**: Zero-layer doc содержит §0.11 «Sources From Everywhere» (web/Tor/TG/social/git/breach/phone/net/keyless) и §0.12 inventory — используемо standalone.

## Assumptions
- Zero-layer строится поверх существующего `apps/acquisition/observation_gate/` и adapters.
- Spec-ops tools: direct vendoring в `apps/`, без service-обёрток. caldera → pyo3 или custom protocol.
- spaCy как основной NLP на слое 3. Всё extraction — deterministic, без LLM.
- Feedback loop через Kafka topic `zero_layer.feedback_seeds`.
- Frontend на React+TS с D3.js.
- Harvest-модули: только open-source tools. Никаких paid APIs в core.
- Zero-layer НЕ содержит ИИ. ИИ только в верхних слоях.
- Spec-ops content в изолированных lab-contour, но код нативно интегрирован.
- Legal advice подтверждено: direct vendoring specops tools допустим при isolation + audit logging.