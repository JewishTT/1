# Cluster 6 — UI · Dashboards · Analytics Patterns

> Часть каталога `docs/architecture/donors/`. Governing spec: `specs/009-donor-full-catalogue/spec.md`.
>
> Этот кластер — про `apps/webapp` (React/TS SPA): какие доноры дают **готовые UI-компоненты, паттерны и UX-фишки** для панелей платформы (evidence ladder, lineage, dashboards, spec-ops cockpit). UI-доноры подключаются двумя способами: (a) **component-vendoring** (код вендорится/адаптируется), (b) **pattern-inspiration** (перенос UX-паттерна без кода). Реестр стилей доноров уже существует: `apps/webapp/src/styles/donors/INDEX.md` — этот кластерный файл задаёт его смысловой контекст.

## Роль кластера в пайплайне

| Донор | UI-деливерабл | Цель в `apps/webapp` | Механизм |
|---|---|---|---|
| CogniX-Surface | live-пайплайн прогресс (SSE), KPI-timeline, presets фильтров, contribution-heatmap, SLA-очередь | панель cognitive-risk / triage | ui-component + service |
| LeakHunter | client-side risk-scoring UI (JS), pattern-breakdown, batch-экспорт CSV/TXT | панель credential-exposure / human-risk | ui-component (JS) |
| Social-Network-Simulation-Analysis | Streamlit live-sim контроль, сетевые визуализации, training-аналитика | counterfactual-консоль science | pattern |
| ARGUS (argus) | 3D threat globe, ATT&CK matrix heatmap, kill-chain swimlane, HUD-эстетика | spec-ops Common Operating Picture | pattern + ui-component |
| caldera/Magma | operation matrix, ability graph (VueJS) | spec-ops operation dashboard | pattern |
| Labyrinth | TUI live event log + web dashboard для deception-контура | deception/telemetry панель | pattern |
| MicroWorld | inspectable outputs UX: артефакты прогона (graph, prompts, traces, memory) на одном экране | прогон-инспектор science | pattern |
| osia-framework | INTSUM/SITREP briefing-вёрстка, Signal-доставка | briefing-документы | pattern |
| EvoCorps | intervention previews, sentiment-траектории, стратегические панели | интервенционный планировщик | pattern |
| hive-mind-gnca | «Civic Resonator»: ambient-фидбек когерентности (light/haptics) | эксперимент (не webapp) | pattern |

## 6.1 CogniX-Surface — cognitive risk analysis platform

**Что это.** Платформа анализа когнитивных атак в корпоративных коммуникациях (phishing, BEC, pretexting, CEO fraud): семантические эмбеддинги (`all-MiniLM-L6-v2`), feature-engineering по 11 психологическим измерениям (urgency, authority, trust, fear, social proof, reciprocity, commitment, liking + sentiment, длина текста), explainable scoring (настраиваемые веса, трансформация `1−exp(−x)`, per-feature contributions, dominant driver), FastAPI + Bootstrap + Vega-Lite дашборд, операционный triage (SLA, приоритетная очередь), SQLite WAL (4 таблицы), API-key auth (8 endpoints), rate limiting (slowapi 120/min; 3/min на пайплайн), 153 автотеста, Docker-compose.

**UI-фишки (goldmine для webapp).** 20 REST endpoints; 9 визуализаций (histogram, donut, driver bar, user scatter, contribution heatmap, correlation matrix, boxplot, weights, feature averages); продвинутые фильтры (risk range, bands, driver, users, text query, top-N); деталки с разбором вклада фичей; **filter presets** (сохранение, max 50, в SQLite); **SSE live-прогресс** (`/api/run/stream`: progress/done/fatal); **KPI Timeline** (snapshot history до 200 + delta между прогонами); run-history (IndexedDB + localStorage fallback); audit log (статусы, веса, webhooks).

**Ограничения.** Датасет демо-коммуникаций; веса — конфигурируемые, но калибровка под наш домен нужна; лицензия-файл в репо отсутствует.

**Интеграция.**
- **Слой**: interpretation (риск-скоринг сообщений) + webapp (паттерны triage/explainability).
- **Метод**: `imported-module` (скоринг-движок) + `ui-component` (паттерны дашборда).
- **Что даёт**: (1) explainable-скоринг «риск-сообщения» → claims cognitive-risk с per-feature вкладом — эталон explainability для evidence-first; (2) UX-паттерны: SSE-прогресс долгих прогонов, KPI-timeline со snapshot-дельтами, contribution-heatmap, presets — переносим в webapp; (3) SLA-triage очередь — паттерн для admission decision-очереди.
- **Как подключить**: (1) скоринг-модуль → interpretation-оператор (фичи из наших mention-текстов); (2) веса калибруем на фикстурах; (3) паттерны — задачи frontend (согласовать с `apps/webapp/src/styles/donors/INDEX.md`).
- **Приоритет**: **P1** (UI-паттерны) / P2 (скоринг — частично дублируется 1.3/1.4). **Лицензия**: NO-LICENSE-FILE → код не вендорим без уточнения; паттерны/идеи — свободно; при использовании — сервис-изоляция. **Риск**: license-unclear — держать как reference/сервис.

## 6.2 LeakHunter — password exposure analysis

**Что это.** Инструмент анализа парольной безопасности и exposure-рисков: risk-score по энтропии, словарным паттернам, клавиатурным последовательностям (qwerty/asdf), датам/годам, корпоративным паттернам, leetspeak, повторам символов, включению username; Shannon entropy + crack-time в сценариях (offline GPU, online, bcrypt, NTLM и др.); batch-анализ списков (по отделам) с экспортом CSV/TXT; контекстные рекомендации.

**Архитектура.** `LeakHunter.html` — полностью клиентское приложение (HTML+CSS+JS, без бэкенда); Java-модульный движок: `PasswordAnalysisEngine` + интерфейс `PasswordPatternChecker` + чекеры (Common/Keyboard/Date/Corporate/LeetSpeak), `Finding`, `AnalysisConfig`; CLI-демо (`java PasswordAnalysisEngine`); интеграция как библиотека/сервлет.

**Ограничения.** Java 8+ движок + отдельное client-side приложение; данные паролей — крайне чувствительны; лицензия-файл отсутствует.

**Интеграция.**
- **Слой**: webapp (human-risk/credential-exposure панель) + spec-ops (credential-hygiene в SAT-кампаниях).
- **Метод**: `ui-component` (client-side риск-вью) + `imported-module`/clean-room (скоринг-формулы в наш стек).
- **Что даёт**: (1) pattern-detection набор (dictionary/keyboard/date/corporate/leet) + crack-time модель → наш credential-exposure скоринг; (2) пример лёгкой одно-файловой SPA-панели (без бэкенда) для внутренних инструментов; (3) рекомендации/отчётность — для awareness-программ spec-ops.
- **Как подключить**: (1) формулы чекеров → модуль скоринга (backend или client-side); (2) Java-движок при нужде — изолированный CLI для batch-аудитов; (3) никакой обработки реальных паролей вне явного изолированного контура; только синтетика по умолчанию.
- **Приоритет**: P2. **Лицензия**: NO-LICENSE-FILE → код не вендорим; методы/формулы переносим. **Риск**: чувствительность данных — политики хранения; держать далеко от прод-данных.

## 6.3 UI-паттерны ARGUS / Magma / Labyrinth / MicroWorld / OSIA / EvoCorps (synthesis)

Паттерны, снятые с доноров-систем (не UI-кластер в чистом виде, но их UI — источник решений для `apps/webapp`):

- **ARGUS COP (argus)**: 3D threat globe (react-three-fiber, анимированные дуги атак), network topology (force-directed, multi-hop traversal через Neo4j), ATT&CK matrix heatmap (coverage по техникам), kill-chain swimlane timeline (фазы вторжения), dark «defense-grade» HUD-эстетика (панели, neon-акценты, terminal-типографика). → spec-ops Common Operating Picture: globe (источники/цели), matrix (coverage из наших specops-claims), swimlane (фазы операции из Caldera-events).
- **Magma (Caldera v5 UI, VueJS)**: operation matrix (abilities × hosts), ability graph, таблицы агентов. → live spec-ops operation dashboard.
- **Labyrinth**: TUI dashboard (overview + live event log) + web dashboard; метрики deception-контура. → паттерн «минимальный оперативный терминал» + live-лог (SSE/WS).
- **MicroWorld**: **inspectable run UX** — граф, промпты, inputs, traces, memory, отчёт одного прогона на одном экране. → science run-inspector (evidence-first: воспроизводимость).
- **OSIA**: INTSUM/SITREP briefing-вёрстка (citations, reliability ratings, confidence) + доставка (Signal → у нас in-app/PDF). → briefing-документ.
- **EvoCorps**: sentiment-траектории, intervention previews, стратегические панели. → интервенционный планировщик (science + spec-ops).
- **CogniX-Surface**: SSE-прогресс, KPI-timeline со snapshot-дельтами, filter presets, contribution-heatmap (см. 6.1).
- **LeakHunter**: single-file client-side панель — образец лёгких вью без бэкенда (см. 6.2).

**Общая интеграция**: слой `webapp`; метод `ui-pattern` (+ `ui-component` там, где лицензия позволяет: argus MIT, Magma MITRE Apache-2.0, CogniX/LeakHunter — только паттерны). **Приоритет**: P1 — ARGUS COP, CogniX-паттерны, MicroWorld-inspector, OSIA-briefing; P2 — остальное. **Риск**: лицензии исходников (Labyrinth AGPL → изоляция/паттерн), объём работ — разносить по фазам.

## 6.4 Как это встраивается в `apps/webapp`

- **Дизайн-токены и стили**: реестр `apps/webapp/src/styles/donors/INDEX.md` уже существует — расширяем: `donors/argus.css` (HUD-панели, matrix, swimlane), `donors/cognix.css` (dashboard-компоненты: KPI-карточки, heatmap, donut), `donors/leakhunter.css` (single-panel layout).
- **Компонентный план**: `<OperationMatrix/>` (Magma-паттерн), `<AttackGlobe/>` (ARGUS-паттерн), `<KpiTimeline/>` (CogniX), `<ContributionHeatmap/>` (CogniX), `<RunInspector/>` (MicroWorld), `<BriefingDoc/>` (OSIA), `<TriageQueue/>` (CogniX SLA).
- **Данные**: все панели читают projection/science API платформы (никаких локальных store) — консистентно evidence-first: каждая панель умеет «показать источник» (lineage).
- **Верификация**: скриншот-тесты/Storybook-фикстуры; a11y — не хуже текущего baseline.
- **Связь со специями**: UI-работы выполняются задачами в `tasks.md` (кластер 6) и опираются на тексты этой папки.

> **Кластер 6 завершён.** Паттерны согласованы с реестром `apps/webapp/src/styles/donors/INDEX.md`; интеграционная карта: `09-INTEGRATION-MATRIX.md`.
