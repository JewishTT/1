# Cluster 5 — Social Simulations · ABM · LLM-Agents

> Часть каталога `docs/architecture/donors/`. Governing spec: `specs/009-donor-full-catalogue/spec.md`.
>
> **Атомарная сущность** здесь получает **counterfactual-лабораторию**: симулируемая популяция людей/агентов реплицирует реляционные инварианты реальных сущностей (связи, взгляды, эмоции, решения) и позволяет прогонять «что если»: как инвариант изменится при информационном вбросе, интервенции, шоке. Доноры дают движки разных классов: cognitive-BDI (posim, TwinMarket), dual-process (DualMind), EASE-конфигурация (silisocs), масштабные LLM-симуляторы (YuLan-OneSim, MicroWorld), физика фазовых переходов (social-oscillation), OCEAN+GCN-DQN (Topology of Trust), 31-слойная econ/political-модель (votranhabysscoremicro).

## Роль кластера в пайплайне

| Донор | Слой | Извлекаем | Механизм |
|---|---|---|---|
| YuLan-OneSim | science (counterfactual) | LLM-соцсимулятор: 100k агентов, code-free сценарии, 50+ доменов, AI-researcher | imported-framework |
| MicroWorld | science, webapp | multi-modal event → граф → агенты → симуляция; PPR-влияние; inspectable outputs | imported-framework |
| posim | science, spec-ops | Social-BDI (Perception→Belief→Desire→Intention→Action), Hawkes-тайминг, 3-tier валидация | imported-framework |
| silisocs | science | EASE-декомпозиция (Environment/Agents/Simulation/Evaluation), Hydra-YAML конфиги, evaluation probes | imported-framework |
| TwinMarket | science, экономика | BDI-агенты финрынка, соцсеть по схожести трейдов, stylized facts (fat tails, volatility clustering) | imported-framework |
| social-oscillation-model | science | kernel-агенты self-excitation, таnh-динамика, regime shift по доле ядер | imported-module |
| Social-Network-Simulation-Analysis | science | OCEAN+DQN+GCN: cooperation/defection, rewiring homophily, archetypes | imported-module |
| DualMind | science, spec-ops | dual-process эмоции/когниции, 15 реальных PR-кризисов, strategy rehearsal | imported-framework |
| votranhabysscoremicro | экономика, science | 31-слойная симуляция экономики + PoliticalCore (элиты/медиа/оппозиция) | imported-module |

## 5.1 YuLan-OneSim (玉兰-万象) — LLM-соцсимулятор (Apache-2.0)

**Что это.** Социальный симулятор на LLM-агентах (RUC-GSAI): code-free построение сценариев через естественно-языковой диалог; 50+ дефолтных сценариев в 8 доменах социальных наук; **evolvable simulation** (модели авто-улучшаются по внешней обратной связи); распределённая архитектура до **100 000 агентов**; **AI social researcher** — автономный цикл от постановки темы до генерации отчёта.

**Hands-on.** Docker (рекомендуется; образ на Docker Hub + Makefile) либо из исходников; конфиг `config/config.json` + `config/model_config.json` (API-ключи, модели); демо-видео.

**Ограничения.** LLM-зависимость (стоимость прогонов); часть контента на китайском; сложная распределённая инфраструктура.

**Интеграция.**
- **Слой**: `science` (counterfactual-лаборатория), spec-ops (forecast кампаний/реакций).
- **Метод**: `imported-framework` → изолированный сервис для крупных прогонов.
- **Что даёт**: (1) массовые «что если» симуляции (до 100k агентов) — стресс-тест гипотез science и планирования spec-ops; (2) образец автономного research-цикла (topic→experiments→report) для science-департамента; (3) 50+ готовых социальных сценариев — фикстуры.
- **Как подключить**: (1) сервис-контейнер с API для science-jobs; (2) science-job: сценарий+параметры → артефакты (траектории, отчёты) → claims; (3) code-free сценарии кастомизируем под наши fixture-схемы.
- **Приоритет**: **P1**. **Лицензия**: Apache-2.0 → vendoring OK. **Риск**: бюджеты LLM-вызовов — лимиты на прогон; язык контента — проверить локализацию.

## 5.2 MicroWorld — multi-modal event → graph → simulation (AGPL-3.0)

**Что это.** Лёгкая система (D2I CUHK): из сырых событийных материалов (документы, изображения, видео, graph-context) строит event-граф, выводит платформенные профили агентов, запускает topology-aware мультиагентную дискуссию; все промежуточные артефакты (**граф, промпты, simulation inputs, action traces, memory states, отчёт**) остаются привязаны к тому же прогону и доступны для инспекции.

**4 стадии.** (1) Ingestion & graph build: онтология, сущности, отношения; (2) Simulation prep: topic keywords, cluster topology, platform profiles; (3) Runtime: topology-aware симуляция с **PPR-guided directional influence** и lightweight memory; (4) Reporting & inspection: логи/трейсы/конфиги/отчёты из того же прогона.

**Фичи.** Multi-modal ingestion; два режима topology-clustering (threshold-based и LLM-keyword-driven); PPR-guided направленное влияние (активация и информационные потоки); lightweight memory (инкрементальная без full-replay); inspectable outputs.

**Ограничения.** AGPL-3.0 (для нас — изоляция сервиса); дизайн под кейсы «отчёта недостаточно».

**Интеграция.**
- **Слой**: `science` + `webapp` (inspectable-run UX).
- **Метод**: `service` (изолированный контейнер) + `pattern` (UX).
- **Что даёт**: (1) event→graph пайплайн — образец для связки interpretation→projection (событийные кластеры); (2) **PPR-влияние** — метод направленной активации в симуляциях; (3) **UX «все артефакты прогона рядом»** — паттерн для webapp science-прогон-инспектора (согласуется с evidence-first: воспроизводимость и трассируемость).
- **Как подключить**: (1) сервис-контейнер: вход — projection-экспорт (событие/граф), выход — симуляционный отчёт + артефакты; (2) ссылки на артефакты из claims в webapp; (3) PPR-модуль — кандидат на перенос в science native.
- **Приоритет**: **P1** (UX+PPR важнее самого движка). **Лицензия**: AGPL-3.0 → изолированный процесс, attribution. **Риск**: AGPL-граница — не смешивать код.

## 5.3 posim — Public Opinion Simulator: Social-BDI cognitive agents (MIT)

**Что это.** Мультиагентный sim-фреймворк эволюции общественного мнения и его управления: LLM-агенты в структурированной **Social-BDI**-архитектуре (Perception → Belief → Desire → Intention → Action) с emotional arousal и когнитивными bias'ами. Три когнитивные подсистемы — независимые LLM-вызовы; **полностью трассируемые decision chains** (belief→desire→intention→action).

**Механики.** **Hawkes process temporal engine**: self-exciting точечный процесс — unifying exogenous event shocks и endogenous user interactions с circadian rhythm-модуляцией; minute-level «outbreak–sustain–decay». Эмерджентные явления (не запрограммированы): жизненные циклы мнений, эмоциональная поляризация, каскадные power laws. **Three-tier progressive validation**: индивидуальная механизм-калибровка → коллективное emergence → статистическая согласованность. Decoupled модульная архитектура: Agents/Environment/Evaluation через стандартные интерфейсы (заменяемые cognitive architecture / temporal engine / metrics).

**Стек.** Python 3.8+, PyTorch 2.0+, OpenAI-совместимый LLM-эндпоинт; проектный сайт + prototype.

**Ограничения.** LLM-зависимость; калибровка под домен; review-статус публикации.

**Интеграция.**
- **Слой**: `science` (кернел opinion-dynamics) + spec-ops (counterfactual governance: прогон стратегий управления).
- **Метод**: `imported-framework`.
- **Что даёт**: (1) Social-BDI + трассируемые цепочки → claims могут ссылаться на decision-chain (объяснимость 2-го порядка); (2) **Hawkes-тайминг** — заимствуем для реалистичной time-модели (согласуется с SIR-Hawkes из 1.2); (3) three-tier-валидация — переносим как стандарт credibility-проверки sim-claims в science playbook.
- **Как подключить**: (1) модуль counterfactual-прогонов (сервис); (2) Hawkes-модуль — science native; (3) validation-методика — в science-гайд.
- **Приоритет**: **P1**. **Лицензия**: MIT → vendoring OK. **Риск**: LLM-бюджеты; домен-калибровка.

## 5.4 silisocs — configurable multi-agent sandbox (MIT)

**Что это.** Конфигурируемый расширяемый фреймворк мультиагентных социальных симуляций и экспериментов (Silicon Society Sandbox). Структура **EASE**: Environment, Agents, Simulation engine, Evaluation (вдохновлено Concordia); каждая ось — YAML-конфиг: среда, популяция агентов и их памяти, движок расписания, метрики эвалюации. Встроенные environment: соцплатформы (Twitter-like, Reddit-like, реальный **Mastodon**), resource market, virtual space — легко добавлять свои. Возможности: scenario-driven grounding, game-master-mediated environments, local/served backends, **evaluation probes**, runtime telemetry, tooling для экспериментов; optional **Concordia-bridge**. Extras: `hf` (persona sources), `mastodon`, `studio` (visual workspace), `analysis`, `hpc` (Submitit/Slurm).

**Hands-on.** `pip install silisocs`; `uv run silisocs`; smoke без API: `sim.llm.provider=scripted`; Hydra-override `num_agents=10 num_steps=5 sim.llm.name=gpt-4o`; bundled scenario `--config-path scenarios/election/conf`.

**Публикации.** ICML 2026 (position), EASE-конфигурация (arXiv), ранее NeurIPS workshop / IJCAI (Mastodon-версия).

**Ограничения.** Alpha-статус (ожидаются стабилизации); требует uv/Hydra-дисциплины.

**Интеграция.**
- **Слой**: `science` (экспериментальная инфраструктура) + spec-ops (полигон Mastodon).
- **Метод**: `imported-framework`.
- **Что даёт**: (1) конфиг-слой (YAML+Hydra) — эталон организации воспроизводимых sim-fixtures; (2) evaluation probes + runtime telemetry — шаблон science-метрик на лету; (3) Mastodon-интеграция — реальная соцсеть как полигон (red-vs-blue соц-инженерия в изолированном контуре).
- **Как подключить**: (1) перенять EASE-YAML-схему для наших science-сценариев; (2) probes → science metrics-модуль; (3) Mastodon-env — кандидат на sandbox-полигон spec-ops.
- **Приоритет**: **P1** (конфиг/полигон) / P2 (движок целиком). **Лицензия**: MIT → vendoring OK. **Риск**: alpha — pin версии, свои smoke-тесты.

## 5.5 TwinMarket — BDI-симуляция финансовых рынков

**Что это.** Мультиагентный фреймворк симуляции socio-economic систем с фокусом на финансовые рынки: индивидуальные инвесторы, социальные взаимодействия, эмерджентные явления. Микроуровень: **BDI** (Belief-Desire-Intention) + behavioral biases (overconfidence, loss aversion, herding). Макроуровень: соцсеть по **схожести трейдов** (time decay: недавние трейды влияют сильнее), информационная пропагация (aggregation, opinion leaders, echo chambers/polarization). Данные: реальные профили/трейды Xueqiu, CSMAR (SSE 50), новости Sina/10jqka/CNINFO; препроцессинг — joint distribution. Результаты: opinion leaders; поляризация при слухах (belief divergence, рост sell/buy, обвал рынка); **stylized facts** (fat tails, volatility clustering, leverage effect, volume-return); self-fulfilling prophecies и information cascades.

**Замечание.** Официальный репозиторий переехал (freedomintelligence/TwinMarket); лицензия в клоне не заявлена (в оригинале заявлялась Apache-2.0 — уточнить при вендоринге).

**Интеграция.**
- **Слой**: `science` (econ-симуляции, см. 8.3) + spec-ops (сценарии манипуляции рынком: rumour → crash).
- **Метод**: `imported-framework`.
- **Что даёт**: (1) готовая BDI-финансовая модель с эмерджентными bubbles/crashes — counterfactual-лаборатория экономического домена; (2) соцсеть по трейд-сходству — метод кластеризации сущностей по поведению (согласуется с behavioral-подписями 4.2); (3) stylized facts — метрики валидации рыночных claims.
- **Как подключить**: (1) сервис/модуль прогонов; (2) фикстуры rumor-shock; (3) валидация эмерджентных свойств против реальных паттернов (SSE 50).
- **Приоритет**: **P1** (ключевой донор экономического домена). **Лицензия**: NO-LICENSE-FILE в клоне → методы переносим; код — по уточнению статуса. **Риск**: LLM-бюджеты; домен данных (CN) — учесть.

## 5.6 social-oscillation-model — self-excitation & phase transitions (MIT)

**Что это.** Минимальная модель: как self-excitation и синхронизация возникают в текстово-опосредованных коммуникационных средах. Гипотеза: коллективная нестабильность определяется **не только** топологией/потоком информации, но и **распределением гетерогенных индивидуальных черт** популяции: подмножество — self-exciting «**kernel**»-агенты (высокий internalization gain I_i, низкий damping L_i, ниже порог насыщения), остальные — пассивные; с ростом доли ядер — **regime shift** из стабильного в синхронизированное/осциллирующее/нестабильное состояние. Поляризация/runaway = **phase-transition-like phenomenon**, движимый составом популяции, а не только внешними шоками.

**Динамика.** x_i(t+1) = tanh( α·x_i(t) + (1−α)·( I_i·f(neighbors_i) − L_i·x_i(t) + η_i(t) ) ); f — нелинейное соседское влияние с extreme amplification; α — inertia. Модель: random-сеть → доля kernel-агентов → эволюция → observables: mean activity (order parameter), system energy (variance) → sweep доли ядер (regime transitions).

**Интеграция.**
- **Слой**: `science` (кернел-модель нестабильности, early-warning).
- **Метод**: `imported-module` (мал).
- **Что даёт**: (1) метрика «доля ядер»: оценка доли self-exciting сущностей в сообществе → прогноз склонности к осцилляциям/поляризации (кандидат в early-warning claims; согласуется с 1.2, 1.5, 4.8); (2) минимальная фикстура (почти аналитически понятна) для тестов science-контура; (3) мост «индивидуальные черты → коллективная нестабильность» между behavioral facets и system-level claims.
- **Как подключить**: (1) science-оператор: вход — популяция с оценками I/L-профилей (из наших behavioral facets); выход — прогноз режима; (2) фикстуры/тесты.
- **Приоритет**: **P1** (малая, концептуально точная). **Лицензия**: MIT → vendoring OK. **Риск**: калибровка I/L по реальным данным.

## 5.7 Social-Network-Simulation-Analysis (Topology of Trust) — OCEAN + GCN + DQN

**Что это.** Симуляционный фреймворк эмерджентности кооперации/дефекции в социальных сетях: Graph Convolutional Networks + **OCEAN**-модель личности + co-evolutionary network dynamics. Каждый агент: shared **GCN** (3-hop агрегация соседства) + intrinsic OCEAN-профиль (Dirichlet-бюджет черт → естественные когнитивные tradeoff) + dynamic personality drift (черты эволюционируют от опыта: предательство/кооперация/новизна, с 15% регрессией к baseline). Среда: iterated **Prisoner's Dilemma** с динамическим `edge_trust`; rewire по personality homophily; обучение через **Deep Q-Learning**. Итог: self-organising echo chambers, trust clusters, defection cascades — без хардкод-правил.

**Механики черт.** Openness → per-agent Boltzmann-температура (широта exploration); Conscientiousness → эффективный discount factor; Extraversion → max degree и агрессивность rewiring; Agreeableness → порог rewiring и скорость восстановления доверия; Neuroticism → чувствительность к payoff-trend. State: 11-мерный вектор (strategy, payoff, reputation, trends, betrayal rate + OCEAN). Payoffs: масштабируются динамическим edge_trust, нормализуются по степени (анти-hub). Обучение: replay buffer + Smooth L1 (Huber).

**Стек.** NetworkX (Watts-Strogatz / Barabasi-Albert / Erdos-Renyi / Grid), PyTorch, Streamlit+Plotly дашборд (live demo), аналитика: Gini, strategy entropy, personality assortativity, archetype-классификация.

**Интеграция.**
- **Слой**: `science` (behavioral microstructure) + webapp (Streamlit-паттерн).
- **Метод**: `imported-module`.
- **Что даёт**: (1) OCEAN-механика с drift — эталон personality-facets сущности; (2) GCN 3-hop — метод neighborhood-агрегации поведенческих фич; (3) **edge_trust-динамика — модель доверия на рёбрах** (реляционный инвариант связи: mutual cooperation строит, defection разрушает) — кандидат в science-операторы доверия; (4) live-дашборд — UX (6.3).
- **Как подключить**: (1) механику доверия/rewire — в science-sims (поляризация, эхо-камеры); (2) state-вектор — шаблон наших behavioral features; (3) прогоны на фикстурах.
- **Приоритет**: **P1** (механики доверия/личности). **Лицензия**: NO-LICENSE-FILE → методы переносим, код — clean-room. **Риск**: масштаб (GCN на больших графах — семплирование).

## 5.8 DualMind — cognitive-affective cascades (WWW 2026, Apache-2.0)

**Что это.** LLM-driven мультиагентная платформа: моделирует interplay быстро меняющихся **эмоций** и медленной эволюции **когнитивных состояний** у гетерогенных персон (dual-component architecture). Валидация на **15 реальных PR-кризисах** после knowledge cutoff LLM (post-Aug 2024 — исключает data contamination): система воспроизводит реальные траектории мнений и исходы, существенно превосходя SOTA-базлайны.

**Стек/релиз.** Backend FastAPI + LangChain; frontend React + Ant Design; curated dataset 15 кризисов; roadmap: core completed → demo video → full system release. UI: Strategy Rehearsal Sandbox (интерактивные стратегические прогоны).

**Интеграция.**
- **Слой**: `science` (кризис-симуляции), spec-ops (PR-кризисные сценарии).
- **Метод**: `imported-framework`.
- **Что даёт**: (1) dual-process декомпозиция (эмоция↔когниция) — паттерн агент-моделей (пара к posim 5.3); (2) **кейс-датасет 15 кризисов — eval-фикстуры** для проверки предсказательной силы наших claims; (3) Strategy Rehearsal UI — UX удачного «репетиционного» полигона (6.3).
- **Как подключить**: (1) кризис-прогоны как science-fixtures; (2) сравнение траекторий с реальностью — калибровка; (3) UI-паттерны в webapp.
- **Приоритет**: **P1** (датасет+метод). **Лицензия**: Apache-2.0 → vendoring OK. **Риск**: частичный релиз — следить за обновлениями; LLM-бюджеты.

## 5.9 votranhabysscoremicro — кросс-ссылка

Полная документация — в **8.1** (кластер «Экономика»). В контексте кластера 5: 31-слойная симуляция + PoliticalCore даёт политико-поведенческих агентов (elites/public/media/opposition) и Q-learning политик — используем как прогон-лабораторию для сценариев «информационная операция → политическая/экономическая реакция» (связка с posim 5.3 и TwinMarket 5.5).

> **Кластер 5 завершён (9/9).** Интеграционная карта: `09-INTEGRATION-MATRIX.md`.
