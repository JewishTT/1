# Feature Specification: Donor Full Catalog Integration
**Feature Branch**: `009-donor-full-catalogue`
**Created**: 2026-09-20
**Status**: Draft
**Input**: User description: "Иди в папку donors, и через затем пиши максимально подробное описание/документацию для каждого проекта. Учитывай что в платформе помимо осинта планируется отдел спецопераций включающий в себя различный redteam, функционал, т.е. и пентест, и все остальное — какие-то проекты оттуда помогут в анализе конкретных атомарных сущностей, какие-то имеют неплохой дизайн UI/интересные UI-фишки, другие обладают комплексными TDA-методами, третьи используют социологический анализ. Пиши доку по каждому проекту, максимально детально, затем пиши как где и зачем его интегрировать в нашу платформу, всё через speckit."

## Context

`donors/` содержит **55+ публичных репозитория**, клонированных как потенциальные "доноры" кода и идей для платформы COGNITIVE — распределённой, event-driven, evidence-first OSINT-платформы (`apps/`: `acquisition → interpretation → admission → projection → science → feedback → webapp → control-plane`).

Платформа состоит из двух крупных доменов:
1. **OSINT core** (Discovery → Frontier → Acquisition → Observation → Interpretation → Admission/Resolution → Projections → TDA → Findings → Feedback)
2. **Отдел спецопераций** (planning department — redteam, пентест, функционал, cognitive red-teaming) — отдельный security-research подраздел, использующий те же данные, но с offense/simulation/attack-surface подходами.

Эта спецификация фиксирует **полный каталог всех доноров** — максимально подробное техническое описание каждого проекта и **карту интеграции** — куда/как/зачем каждый проект вписывается в архитектуру платформы.

## Goal

Интегрировать **все** доноры. Форма интеграции — по обстоятельствам: где-то вырезаем атомарные сущности (модуль/алгоритм/UI-паттерн), где-то вендорим сервис целиком — **критерий успеха один: живая интеграция в пайплайн**. Копирование кода разрешено владельцем; лицензия влияет только на механизм (vendoring / изолированный сервис / clean-room). Документация живёт в `docs/architecture/donors/`, карта интеграции — в `09-INTEGRATION-MATRIX.md`.

## Cluster taxonomy (57 доноров → 7 кластеров + инфраструктурный слой)

| # | Кластер | Проекты | Роль для платформы |
|---|---------|---------|--------------------|
| 1 | **Когнитивная война, нарративы, influence** | f/доп (MCP), доп.txt, Cognitive-Weaponization-Matrix, CognitiveAttack, seithar-research, NarrativeDiffusion, io-coordinated-replies, IO-detecting-and-anticipating, DIMA-OntoToolkit, Lying_with_Truth, EvoCorps, cognitive_phase_transitions | Спецоперации (cognitive redteam), science (belief dynamics), interpretation (bias parsing) |
| 2 | **Spec-ops / Redteam / Pentest / Emulation** | caldera, adversary_emulation_library, ael, APT-SF, Operation-Molasses, PhantomStrike-AI, PhishSlayer, BluePhish, fiercephish, SPEAR, Sticks, TripleFantasy, AzureAD-Attack-Defense | Отдел спецопераций (adversary emulation, attack validation, phishing, CTF) |
| 3 | **OSINT / CTI / Link Analysis** | erlik-graph, SYNINT, intellyweave, OSIA-framework, argus, PIDSF | OSINT-core (recon, entity enrichment, CTI-to-graph, threat intel) |
| 4 | **Сети, графы, гиперграфы, TDA, топология** | adversarygraph, HypergraphX, BeliefLandscapeFramework, hive-mind-gnca, persistence-agent, topology/witness-topology, PHoDMSs, ABa-KiTo, ABM_polarisation, raphtory, Lau-network-science | science (TDA/structure), interpretation/projection (graph features) |
| 5 | **Социальные симуляции** | YuLan-OneSim, MicroWorld, posim, silisocs, TwinMarket, social-oscillation-model, Social-Network-Simulation-Analysis, votranhabysscoremicro, DualMind | science (counterfactual, stress-test), спецоперации (campaign forecasting) |
| 6 | **UI / Dashboard / Analytics** | CogniX-Surface, LeakHunter, Social-Network-Simulation-Analysis(dashboard) | webapp (UI patterns, dashboard UX, risk scoring UI) |
| 7 | **Инфраструктурный стек данных** | сбор данных.txt (Redpanda→Flink→Fluss→Iceberg/Gobblin/DeltaCAT), f.txt (ArXiv CW-paper) | infra / science (data backbone, theory) |
| 8 | **Экономика** | TwinMarket, votranhabysscoremicro, Entropic-Dynamics | science (economic dynamics), спецоперации (market manipulation) |

## User Scenarios & Testing

### User Story 1 - Analyst traces any donor insight to origin (Priority: P1)
An analyst using any platform feature can open "lineage" and see: donor project, commit-ish, license, adapted module path, guarding test.

**Why**: Без атрибуции нельзя license-комплаенс и отлаживать "где паттерн взят".

**Independent Test**: Every adapted module carries attribution header; `07-INTEGRATION-MATRIX.md` cross-references every adapted module.

**Acceptance Scenarios**:
1. **Given** an adapted module, **When** audited, **Then** header has source repo + license + commit + test.
2. **Given** a UI panel using donor logic, **When** analyst inspects lineage, **Then** panel shows source donor + license + adapted file.

### User Story 2 - Spec-ops reuses donor attack/sim capabilities (Priority: P1)
Spec-ops (redteam/pentest/cognitive-redteam) spins up scenarios from donor TTP libraries (Caldera, AEL, APT-SF, Sticks), phishing (PhishSlayer/BluePhish/SPEAR/PIDSF), deception (Labyrinth) in isolated lab fixtures, wired to Kafka so telemetry lands in `science`/`admission`.

**Independent Test**: A micro-emulation plan from AEL runs end-to-end in `<10 min` isolated lab, produces ATT&CK-mapped events to Kafka with lineage to donor source.

### User Story 3 - Science layer consumes donor TDA/sim methods (Priority: P1)
`apps/science` and `apps/projection` reuse donor TDA (BLF, persistence-agent, topology, HypergraphX, PHoDMSs, ABa-KiTo) and sim engines (YuLan-OneSim, posim, silisocs, TwinMarket, MicroWorld, DualMind, EvoCorps, social-oscillation) as algorithmic building blocks — producing claim distributions, null models, counterfactual scenarios.

**Independent Test**: A structure claim in `science` is built from a donor TDA method (e.g. persistence-agent barcode) on a fixture projection; the claim's declared model id points to donor; tests assert the barcode matches donor output.

### User Story 4 - Discovery enriches frontier with donor link-analysis (Priority: P2)
Discovery pre-crawl enrichment uses donor link-analysis transforms (erlik-graph: DNS/WHOIS/crt.sh/Shodan/CT) and recon patterns (SYNINT agents, PIDSF subdomain enum) to feed the durable frontier with provenance — zero manual search.

**Independent Test**: Seeding a registered domain produces deterministic candidate URLs enqueued once each into frontier; each carries source+transform provenance.

### User Story 5 - Interpretation parses donor-style cognitive biases (Priority: P2)
Interpretation uses DIMA-OntoToolkit (bias/argument/quote extraction → OWL/SPARQL), NarrativeDiffusion (causal-narrative graph influence), and CognitiveAttack (154-bias ensemble) to produce cognitive-risk claims.

**Independent Test**: A fixture article with known cognitive bias triggers a claim from the DIMA model; the claim cites evidence links to the parsed mention.

---

## Requirements

### Functional Requirements
- **FR-001**: Each donor documented in `docs/architecture/donors/` with: purpose, architecture, methodology, math, data sources, key features, usage, hands-on, limitations.
- **FR-002**: Each donor has an integration entry: target `app/`-layer, method, what-delivers, how-to-wire, priority, license, risk.
- **FR-003**: `09-INTEGRATION-MATRIX.md` cross-references every donor with priority + license + integration mechanism.
- **FR-004**: Adapted donor modules carry attribution header + unit test in `apps/*/tests/`.
- **FR-005 (rev.2 — код копировать можно)**: **все доноры интегрируются**; приоритет — успешная живая интеграция, не лицензионная чистота. Лицензия определяет **механизм**: (a) permissive (MIT/BSD-3/Apache-2.0) → direct vendoring в `apps/*` с attribution-заголовком (repo + license + commit + test); (b) copyleft (GPL/AGPL) → vendoring допустим, предпочтительно как **изолированный процесс/сервис** (process-граница сохраняет чистоту core); (c) CC-BY-NC → knowledge-only (таксономии/методики в KB, без вендоринга кода); (d) лицензия не заявлена → методы (идеи не охраняются) переносим, код — изоляция/clean-room, решение владельца. P4-«skip» применяется **только** при технической несовместимости с философией платформы (event-driven, evidence-first, immutable observations, rebuildable projections) → `pattern-inspiration-only`.
- **FR-006**: This spec references existing `001...008` specs for architectural context.

### Key Entities
- **Donor Project**: one repo in `donors/` (dir name); license, language, category, methods, integration method, priority.
- **Cluster**: thematic grouping (1-8).
- **Integration Target**: `apps/{acquisition|interpretation|admission|projection|science|feedback|webapp|control-plane|deploy}`.
- **Integration Method**: `imported-module` / `mcp-server` / `service` / `data-source` / `ml-model` / `ui-component` / `pattern-inspiration-only`.

## Success Criteria
- **SC-001**: 100% of donors documented in `docs/architecture/donors/*.md`.
- **SC-002**: 100% of donors have an integration entry.
- **SC-003**: `07-INTEGRATION-MATRIX.md` cross-references every donor with priority + license.
- **SC-004**: Every donor with integration value has ≥1 concrete integration task in `tasks.md` (vendoring / service / module / UI-pattern / knowledge), либо явно переведён в `pattern-inspiration-only` с обоснованием технической несовместимости.
- **SC-005**: Catalog usable standalone by analyst to understand coverage gaps.

## Assumptions
- `apps/` layers: acquisition=Rust workers+frontier; interpretation=parsers→mentions→candidates; admission=admission+resolution+calibration; projection=graph/search/analytics/TDA; science=probabilistic claims+hypothesis+c causal/temporal/structural; feedback=utility scorer+stopping; webapp=React/TS SPA.
- **Отдел спецопераций** = security-research подраздел (redteam/pentest/cognitive-redteam/attack-validation), не часть OSINT core, но использует те же данные + event-stream; интегрируется как `apps/science` scenarios + isolated lab fixtures + `apps/admission`/projection для телеметрии.
- **Экономика** = третья domain — отдельный подпроект для economic-dynamics доноров.
- **Атомарные сущности** = человек / компания / организация / домен / канал / событие и т.п. — **базовая составная единица OSINT-анализа абсолютно любой сети**. Онтологически это **реляционный инвариант, закреплённый за общим пайплайном/потоком данных платформы** (acquisition → interpretation → admission → projection → science → feedback); инвариант **динамически меняется** во времени и в пространстве связей. Моделируется разнообразными методами — от классических методов представления объектов (entity/attribute/edge-схемы, графовые деривации) до отделов science/network-science и TDA. Доноры дают конкретные методы, которые вычисляют / представляют / трекают эти реляционные инварианты в их динамике.
- **UI-фишки** = паттерны из CogniX, LeakHunter, vitni/kafSIEM/PANO, DualMind, EvoCorps — UX-референсы для `apps/webapp`.
- **TDA-методы** = BLF (VAE+ODE+attractor/saddle), persistence-agent (VR→barcode→personality), topology/witness-topology (witness complex→bottleneck), HypergraphX (higher-order), PHoDMSs (erosion distance), ABa-KiTo (χ-function/ISOKANN).
- **Социологический анализ** = DIMA-OntoToolkit (bias), CognitiveAttack (154 biases), social-oscillation-model (phase transitions), Social-Network-Simulation-Analysis (OCEAN+GCN+DQN), EvoCorps (depolarization multi-agent).