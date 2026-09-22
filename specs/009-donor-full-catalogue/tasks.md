# Tasks: Donor Full Catalog Integration

**Spec**: `specs/009-donor-full-catalogue/spec.md` · **Plan**: `plan.md` · **Matrix**: `docs/architecture/donors/09-INTEGRATION-MATRIX.md`
Формат: `- [ ] TNNN — действие — донор (ref) — target`.

## Phase 0 — Конвенции (фундамент)

- [ ] T001 — Attribution-заголовок шаблон (repo + license + commit + oracle-test) + чек-скрипт аудита — все доноры (00-INDEX) — `apps/*/src/**`
- [ ] T002 — scenario-DSL v2: Diamond-поля, atom-уровень, expected-telemetry, ROE-поле — 2.3/2.4/2.10 — `apps/science/scenarios/`
- [ ] T003 — Схема specops-событий + конвертер Caldera events → event-bus — 2.1 — `apps/specops/stream/` (предлагаемый контур)
- [ ] T004 — Реестр UI-стилей donors расширить (argus/cognix/leakhunter) — 6.3/6.4 — `apps/webapp/src/styles/donors/`

## Phase 1 — Spec-Ops core

- [ ] T010 — Развернуть caldera как изолированный сервис (профиль `spec-ops-lab`) — 2.1 — `deploy/specops/`
- [ ] T011 — Парсер/импортёр ael → scenario registry (fixture bundles) — 2.2 — `apps/science/scenarios/importers/`
- [ ] T012 — Импортёр adversary_emulation_library + attack-atoms registry (micro-plans) — 2.3 — `apps/science/scenarios/atoms/`
- [ ] T013 — PhantomStrike: вынести AI-scoring формулу в severity-модуль — 2.6 — `apps/science/findings/severity/`
- [ ] T014 — PhishSlayer: поднять сервис в lab + KPI-схема (CTR/TTR/report-rate) — 2.7 — `deploy/specops/sat/`
- [ ] T015 — PIDSF: RoE-гейт-паттерн (обязательный sign-off) в campaign-схему spec-ops — 3.6 — `apps/science/scenarios/roe/`
- [ ] T016 — PIDSF: detection-модуль (permutation+crt.sh scoring) → acquisition brand-protection — 3.6 — `apps/acquisition/enrichment/lookalike/`
- [ ] T017 — sticks: lab-fixture (Caldera+Kali+nginx+DB) + STIX-sufficiency метрика — 2.10 — `deploy/specops/lab/`
- [ ] T018 — Labyrinth: deploy deception-контура на периметре lab — 2.13 — `deploy/specops/deception/`
- [ ] T019 — Operation-Molasses: KB-структура 33 фаз + toolkit-каталог (lab-only runner) — 2.5 — `docs/kb/specops/` + `toolkit/`
- [ ] T020 — SPEAR: baseline детекторов + LIME red-team чек в CI детекторов — 2.14 — `apps/interpretation/detectors/`
- [ ] T021 — TripleFantasy: patterns-каталог (beacon/OPSEC/anti-analysis) в KB — 2.11 — `docs/kb/specops/patterns/`
- [ ] T022 — AzureAD playbook → KB-статьи с ATT&CK-тэгами + detection-меры — 2.12 — `docs/kb/identity/`

## Phase 2 — OSINT core

- [ ] T030 — erlik-graph: transforms-worker (13 трансформов) → candidate/observation c provenance — 3.1 — `apps/acquisition/enrichment/`
- [ ] T031 — erlik-graph: MCP-паттерн «один core — два адаптера» → дизайн control-plane MCP — 3.1 — `apps/control-plane/mcp/`
- [ ] T032 — SYNINT: обёртка агентов (приоритетный список) в worker-интерфейс — 3.2 — `apps/acquisition/agents/`
- [ ] T033 — SYNINT: chain-of-custody ledger → lineage-подсистема — 3.2 — `apps/admission/lineage/`
- [ ] T034 — SYNINT: identity-review (confirm/reject/reverse) → admission decision-очередь — 3.2 — `apps/admission/identity/`
- [ ] T035 — intellyweave: GLiNER-экстрактор (7 типов) → interpretation mentions — 3.3 — `apps/interpretation/extractors/gliner/`
- [ ] T036 — osia-framework: reliability-tiering (A/B/C) + verdicts (CORROBORATED/CONTRADICTED/UNVERIFIED) → calibration — 3.4 — `apps/admission/calibration/`
- [ ] T037 — osia-framework: INTSUM/SITREP report-генератор — 3.4 — `apps/webapp/reports/` + `apps/science/briefing/`
- [ ] T038 — argus: OCSF-нормализатор (schema-слой телеметрии) — 3.5 — `apps/acquisition/telemetry/ocsf/`
- [ ] T039 — argus: IOC-NER (SecureBERT/DistilBERT) → interpretation CTI-парсер + STIX-экспорт — 3.5 — `apps/interpretation/cti/`
- [ ] T040 — io-coordinated-replies: фичи+модели → interpretation (reply-attack detection) — 1.7 — `apps/interpretation/models/replies/`
- [ ] T041 — IO-detecting-and-anticipating: temporal-motif джобы + link-prediction → projection/science — 1.8 — `apps/projection/motifs/`
- [ ] T042 — DIMA-OntoToolkit: пайплайн → interpretation (arguments/agents/quotes → bias-claims) — 1.9 — `apps/interpretation/dima/`
- [ ] T043 — NarrativeDiffusion: adoption-оператор (αW+βI+γA) в science — 1.6 — `apps/science/operators/adoption/`
- [ ] T044 — CognitiveAttack: bias-KB (154) → онтология; attack.py → CI LLM-security gate — 1.4 — `docs/kb/bias/` + `ci/security/`
- [ ] T045 — Lying_with_Truth: CoPHEME eval-набор + montage-детектор (research) — 1.10 — `apps/interpretation/eval/`

## Phase 3 — Science / TDA / Sims

- [ ] T050 — BLF: стадии 0–2 (clean→classify→extract) → interpretation hook — 4.1 — `apps/interpretation/beliefs/`
- [ ] T051 — BLF: стадии 3–7 (кластеры→alignment→stitching) → batch-оператор — 4.1 — `apps/science/beliefs/batch/`
- [ ] T052 — BLF: стадии 8–10 (VAE/neural ODE/geometry) → per-window job + artifact `belief_landscape.bin` — 4.1 — `apps/science/beliefs/landscape/`
- [x] T053 — BLF: forecasting toolkit → science-tool (claims с окном) — 4.1 — факт. `apps/science/beliefs/landscape.py` (отклонение таргета: `forecast/` → `beliefs/`, операторы flow/attractors/forecast)
- [x] T054 — persistence-agent: worker (barcode/features/archetype) + facets — 4.2 — `apps/science/tda/persistence.py`
- [ ] T055 — witness-topology: worker (mapper/distances) + данные для webapp Mapper-панели — 4.3 — `apps/science/tda/witness/`
- [x] T056 — PHoDMSs: worker (rank invariants/erosion distance) — 4.4 — `apps/science/tda/phodms.py`
- [x] T057 — ABa-KiTo: runner (χ/ISOKANN обёртка) — 4.7 — `apps/science/kinetics/pathways.py` (clean-room, методы; без ISOKANN/ML-зависимостей)
- [x] T058 — HypergraphX: hypergraph-джобы (co-mention/co-event) → projection-деривации — 4.5 — факт. `apps/projection/metrics/hypergraph_metrics.py` (отклонение таргета: `hypergraph/` → `metrics/`)
- [x] T059 — lau-network-science: crate в projection-engine (centrality/louvain/pagerank jobs) — 4.11 — `apps/projection/metrics/network_measures.py` + `community.py`
- [x] T060 — Raphtory: пилот time-travel сервиса + решение по стеку — 4.9 — `apps/projection/metrics/temporal_paths.py` (решение: без GPLv3; собственная реализация; отклонение таргета `deploy/pilots/raphtory/`)
- [ ] T061 — YuLan-OneSim: сервис + фикстурные сценарии — 5.1 — `deploy/science/yulan/`
- [ ] T062 — MicroWorld: сервис (PPR) + inspectable-артефакты — 5.2 — `deploy/science/microworld/`
- [ ] T063 — posim: Social-BDI прогоны + Hawkes-модуль в science — 5.3 — `apps/science/sims/posim/`
- [ ] T064 — silisocs: EASE-конфиг + probes → science metrics — 5.4 — `apps/science/sims/silisocs/`
- [ ] T065 — TwinMarket: econ-прогоны + rumor-shock фикстуры — 5.5 — `apps/science/sims/twinmarket/`
- [ ] T066 — social-oscillation-model: оператор (I/L-профили → режим) — 5.6 — `apps/science/operators/kernel_regime/`
- [ ] T067 — Topology-of-Trust: edge_trust/OCEAN-механики → science — 5.7 — `apps/science/sims/trust/`
- [ ] T068 — DualMind: dataset-фикстуры + dual-process паттерн — 5.8 — `apps/science/sims/dualmind/`
- [x] T069 — ABM_polarisation: фикстура + 99_functions-метрики — 4.8 — `apps/science/fixtures/schelling.py` (clean-room, методы)
- [x] T070 — Entropic-Dynamics: фикстура endogenous-crisis — 8.2 — факт. `apps/science/econ/crisis_abm.py` (clean-room; консолидировано в econ-контур через T090)
- [x] T071 — cognitive_phase_transitions: оператор (order/MPC/transition) — 1.12 — `apps/science/operators/phase.py`
- [x] T072 — hive-mind-gnca: GNCA/Λη (P2 backlog) — 4.6 — `apps/science/sims/gnca.py` (отклонение таргета: `backlog/gnca/` → `sims/`)
- [ ] T073 — EvoCorps: интервенционные прогоны (science-fixture) — 1.11 — `apps/science/sims/evocorps/`
- [ ] T074 — доп.txt: локализовать DeGroot/SIR-Hawkes/HK/Potts/ATE как science-операторы — 1.2 — `apps/science/operators/narrative/`

## Phase 4 — UI

- [ ] T080 — CogniX-паттерны: SSE-прогресс, KPI-timeline, contribution-heatmap, presets, SLA-triage — 6.1 — `apps/webapp/components/dashboard/`
- [ ] T081 — ARGUS COP: globe/matrix/swimlane — 6.3 — `apps/webapp/components/specops/`
- [ ] T082 — Magma: operation-matrix — 6.3 — `apps/webapp/components/specops/matrix/`
- [ ] T083 — MicroWorld: run-inspector — 6.3 — `apps/webapp/components/science/inspector/`
- [ ] T084 — OSIA: briefing-doc (INTSUM/SITREP) — 6.3 — `apps/webapp/components/briefing/`
- [ ] T085 — LeakHunter: single-panel (synthetic-only) — 6.2 — `apps/webapp/components/humanrisk/`
- [ ] T086 — styles `donors/*.css` + Storybook/скриншоты — 6.4 — `apps/webapp/src/styles/donors/`

## Phase 5 — Экономика

- [x] T090 — econ-контур в science (wiring TwinMarket/votran/Entropic/ABa-KiTo) — 8.1–8.3 — `apps/science/econ/operators.py` (votran) + `crisis_abm.py` (Entropic); ABa-KiTo-часть → `kinetics/pathways.py`
- [ ] T091 — disinfo-bridge: сценарии «нарратив → рынок» — 2.5+8.3 — `apps/science/scenarios/disinfo_market/`
- [ ] T092 — econ-facets у company-сущностей — 8.x — `apps/projection/facets/econ/`

## Phase 6 — Верификация

- [ ] T100 — attribution-audit (скрипт T001) + отчёт — все — `tools/audit/`
- [ ] T101 — license-note рунбук (NO-LICENSE/personal-use решения) — 00-INDEX rev.2 — `docs/architecture/donors/`
- [ ] T102 — matrix-sync чек в CI (новый вендор → запись в 09) — все — `ci/docs/`
- [ ] T103 — e2e story-tests US1–US5 (линедж, spec-ops прогон, science TDA-claim, discovery-enrichment, bias-парсинг) — spec 009 — `tests/e2e/`
- [ ] T104 — UI a11y/screenshots — 6.x — `apps/webapp/tests/`
- [ ] T105 — GPU/perf-бюджеты (TDA-окна, batch-лимиты LLM) — 4.x/5.x — `deploy/budgets/`
- [ ] T106 — финальный обзор каталога (00-INDEX sync, перекрёстные ссылки) — все — `docs/architecture/donors/`

---

**Трекинг**: отмечать `[x]` по мере закрытия; каждая задача при закрытии добавляет запись в `09-INTEGRATION-MATRIX.md` (механизм + статус) и passing guarding test.