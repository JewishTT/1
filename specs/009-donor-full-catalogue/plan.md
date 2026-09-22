# Implementation Plan: Donor Full Catalog Integration

**Spec**: `specs/009-donor-full-catalogue/spec.md` · **Created**: 2026-09-20 · **Status**: Active
**Input**: «Все доноры интегрируются; код копировать можно; критерий — успешная живая интеграция. Всё через speckit.»

## Summary

Программа интеграции **56 донорских единиц** (53 репозитория + 3 knowledge-файла) в платформу COGNITIVE. Каталог полной документации: `docs/architecture/donors/` (01–08 кластеры + 09 матрица). Каждый донор имеет: полное техописание + integration entry (слой, механизм, что даёт, как подключить, приоритет, лицензия, риск).

## Technical approach

- **Волновая стратегия**: Phase 0 конвенции → Phase 1 spec-ops core → Phase 2 OSINT core → Phase 3 science/TDA/sims → Phase 4 UI → Phase 5 экономика → Phase 6 верификация.
- **Механизмы интеграции** (FR-005 rev.2): permissive (MIT/BSD/Apache) → vendoring в `apps/*` + attribution-заголовок (repo + license + commit + guarding test); copyleft (GPL/AGPL) → изолированный сервис/бинарь; CC-BY-NC → knowledge-only; лицензия не заявлена → методы (не охраняются) переносим, код — clean-room/изоляция; решение владельца.
- **Атомарная сущность** (платформенный канон): человек/компания/организация/домен/канал/событие = динамический реляционный инвариант, закреплённый за пайплайном; интеграции доноров подают методы вычисления/трекинга инварианта (belief, behavior, trust, coordination, phase, attack-surface, econ-state).
- **Lab-дисциплина**: весь offensive-контент (кластеры 2, 3.6-sim, 4.10-sim) — только изолированный контур (docker lab-сети, allow-list, полное логирование, ROE-гейт из 3.6; паттерн PIDSF).
- **Правило модификаций**: донорские store не становятся source of truth; всё входит как observations/candidates/claims/artifacts; любая вендоренная единица проходит через attribution-аудит (Phase 6).

## Constitution check

- **Event-driven / evidence-first**: каждая интеграция производит immutable observations / proposals / claims; ничего не пишет мимо event-bus.
- **Rebuildable projections**: TDA/sim/ML-артефакты — производные от observations, пересобираемые (фиксация model id + version в claim).
- **Attribution/lineage**: обязательный заголовок + запись в `09-INTEGRATION-MATRIX.md` + видимость в webapp lineage.
- **Отдел спецопераций** — изолированный домен, не искажает OSINT-core; связь — через общий event-stream и science-claims.
- *(Сверить с `.specify/memory/constitution.md` при первом PR каждой фазы; ожидаемых конфликтов нет.)*

## Phases & deliverables

**Phase 0 — Конвенции (фундамент)**
Attribution-шаблон заголовка (repo/license/commit/test); scenario-DSL v2 (Diamond-поля 2.4 + atom-уровень 2.3); схема specops-событий (suggested topic `specops.telemetry`) + конвертеры (Caldera events); реестр UI-стилей `apps/webapp/src/styles/donors/`.

**Phase 1 — Spec-Ops core (P1)**
caldera service + профиль `spec-ops-lab`; парсер/импортёр ael + adversary_emulation_library → scenario registry + attack-atoms; PhantomStrike scoring-модуль; PhishSlayer service (SAT); PIDSF RoE-гейт-паттерн + domain-detection; sticks lab-fixture + STIX-sufficiency metric; Labyrinth deploy (deception); KB: Operation-Molasses (33 фазы + toolkit), AzureAD playbook, APT-SF схемы; SPEAR detectors baseline; TripleFantasy patterns-каталог.

**Phase 2 — OSINT core (P1)**
erlik-graph transforms-worker + MCP-паттерн; SYNINT: агенты (приоритетный список), chain-of-custody, identity-review → admission, checkpoint-паттерн; intellyweave GLiNER → interpretation; osia-framework: tier A/B/C + corroboration verdicts → admission/calibration, SITREP-report; argus: OCSF-нормализатор, IOC-NER, STIX-экспорт; PIDSF detection-модуль → acquisition brand-protection; io-coordinated-replies классификаторы; IO-detecting-and-anticipating motifs/link-prediction → projection/science; DIMA-OntoToolkit → interpretation; NarrativeDiffusion оператор; CognitiveAttack bias-KB + CI security-gate; Lying_with_Truth eval-набор.

**Phase 3 — Science / TDA / Sims (P1)**
*TDA-ядро*: BLF (стадии 0–2 → interpretation hook; 3–7 → batch-операторы; 8–10 → per-window jobs с artifact; 11 → forecasting-tool); persistence-agent worker (barcodes/features/facets); witness-topology (mapper graphs, bottleneck/Wasserstein); PHoDMSs (rank invariants, erosion distance); ABa-KiTo (χ/ISOKANN, kinetic pathways); HypergraphX (hypergraph-деривации projection); lau-network-science (native Rust метрики); Raphtory — пилот time-travel.
*Sims*: YuLan-OneSim (сервис, 100k-агентов); MicroWorld (сервис + PPR + inspectable-артефакты); posim (Social-BDI + Hawkes); silisocs (EASE-конфиг + probes); TwinMarket (BDI-рынок); social-oscillation (kernel-режим); Topology-of-Trust (OCEAN/edge_trust); DualMind (кризис-датасет).
*Фикстуры-эталоны*: ABM_polarisation (Schelling), Entropic-Dynamics (endogenous crisis). *Cognitive-science*: EvoCorps (интервенции), cognitive_phase_transitions (MPC/order), доп.txt модели (DeGroot/SIR-Hawkes/HK/Potts/ATE — локализация), hive-mind-gnca (P2 backlog).

**Phase 4 — UI (P1)**
CogniX-паттерны (SSE-прогресс, KPI-timeline, contribution-heatmap, presets, SLA-triage); ARGUS COP (globe/matrix/swimlane); Magma operation-matrix; MicroWorld run-inspector; OSIA briefing; LeakHunter single-panel; `donors/*.css` стили; Storybook/скриншот-тесты.

**Phase 5 — Экономика (P1)**
Science econ-контур: TwinMarket + слои votran + Entropic + ABa-KiTo-lens; disinfo-bridge (2.5) для манипуляционных сценариев; econ-facets у company-сущностей.

**Phase 6 — Верификация**
Attribution-audit (скрипт T001); matrix-sync (каждый PR обновляет 09); license-note рунбук (решения владельца по NO-LICENSE); UI a11y/screenshots; e2e story-tests US1–US5; GPU/perf-бюджеты (окна TDA, batch-лимиты LLM).

## Risks & mitigations

| Риск | Митигация |
|---|---|
| License-неопределённость (NO-LICENSE-FILE, personal-use) | методы переносим (не охраняются); код — изоляция/clean-room; решение владельца зафиксировано в 00-INDEX rev.2; обновляем матрицу при уточнении |
| GPU/LLM-бюджеты (BLF, YuLan, GLiNER, детекторы) | batch-контур off-path, лимиты на прогон, кэши моделей |
| Research-качество доноров | собственные тесты + фикстуры-эталоны (8.2, 4.8); заявки доноров (напр. «90%») не наследуются |
| Offensive-контент | строгий lab-контур: изолированные сети, allow-list, аудит запусков, ROE-гейт (3.6) |
| Объём программы | волны: P1 первым, P2/P3 backlog; калибровка по факту |

## Definition of done

SC-001…SC-005 закрыты (см. `09-INTEGRATION-MATRIX.md` §Верификация). Волна 1 закрыта, когда каждая P1-единица имеет **живого consumer'а** (сервис/модуль/джоб, продюсирующий события или артефакты в пайплайн), attribution-заголовок, guarding test и запись в матрице.

## Связь со спеками

`001` (платформа) · `002–008` (подсистемы) · `009` (настоящий каталог). Прогресс — в `tasks.md`.