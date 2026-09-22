# Cluster 4 — Networks · Graphs · Hypergraphs · TDA · Topology

> Часть каталога `docs/architecture/donors/`. Governing spec: `specs/009-donor-full-catalogue/spec.md`.
>
> **Ключевой кластер определения атомарной сущности**: человек/компания/событие существует как **динамический реляционный инвариант** — граф/гиперграф/point cloud во времени. Доноры дают вычислительные ядра, которыми `science`/`projection` моделируют инвариант: persistent homology (стабильность/петли/пустоты), нейро-ODE поля убеждений, witness-комплексы, χ-функции кинетики, higher-order структуры, temporal graph DB.

## Роль кластера в пайплайне

| Донор | Слой | Извлекаем | Механизм |
|---|---|---|---|
| BeliefLandscapeFramework | science | beliefs → кластеры → VAE(8D) → neural ODE → аттракторы → прогноз | imported-framework |
| persistence-agent | science (TDA) | VR-комплекс → баркоды → features (stability/adaptability/depth) → archetype | imported-crate |
| topology/witness-topology | science (TDA) | witness complex, persistence, bottleneck/Wasserstein, mapper, stability bounds | imported-crate |
| PHoDMSs | science (TDA) | spatiotemporal Betti-0, rank invariants, erosion distance (динамические метрики) | imported-module |
| HypergraphX | projection, science | higher-order сети: конверсии, метрики, generative-модели, динамика | imported-module |
| hive-mind-gnca | science, spec-ops | GNCA Titans (fast/slow weights), simplicial CA, Λ>η диагностика коллапса | imported-module |
| ABa-KiTo | science | χ-function (ISOKANN), кластеризация состояний ABM, граф макросостояний | imported-module |
| ABM_polarisation | science | Schelling-сеть поляризации (Julia), функции анализа | imported-module |
| Raphtory | projection (storage) | in-memory temporal graph DB: time-travel, temporal motifs, risk detection | service / reference |
| lau-network-science | projection (metrics) | Rust network-science: генераторы, центральности, Louvain, SIR/SIS, percolation, power-law MLE | imported-crate |
| adversarygraph | spec-ops, projection, webapp | CTI→detection workbench: Threat Radar, hybrid RAG, Evidence-to-Detection Graph, MCP | service (isolated) |

## 4.1 BeliefLandscapeFramework (BLF) — от beliefs к аттракторам и прогнозу

**Что это.** End-to-end система (DARPA MAGICS): извлекает убеждения из соцмедиа-текста, обучает непрерывный **belief landscape** и прогнозирует коллективное поведение (выборы, мобилизации, полит-насилие). 11 стадий: 0 cleaner → 1 belief classifier → 2 LLM belief extractor → 3 embedding+dedup → 4 first-pass coherence clustering → 5 pair generation + LLM alignment → 6 alignment refinement → 7 streaming proposition stitching (лонгитюдный каталог) → 8 reconstruction VAE (8-мерный латент z на юзера) → 9 neural ODE field (векторное поле над z по окнам) → 10 geometric analysis (attractors, saddles, basins, region flow/density) → 11 forecasting toolkit (elections, event traces, anomaly scans).

**Архитектура.** `src/core` (cleaning, embeddings, HDBSCAN/fast_hdbscan shells, pair generator, GPU utils, LLM-клиенты vLLM/Anthropic/OpenAI), `src/clustering` (coherence/alignment, GPU-isolated subprocess runners), `src/proposition` (sliding-window matching), `src/streaming` (first_pass, pair_engine, proposition_tracker — window-to-window stitching), `src/trajectory_model` (VAE + ODE + walk-forward evaluation), `src/forecasting`.

**Методы/математика.** Sentence-transformer эмбеддинги → кластеризация (HDBSCAN / coherence shells) → LLM-alignment скоринг → пропозиции; VAE реконструкция траекторий пользователей в 8D; neural ODE как обучаемое векторное поле; топологический разбор поля (аттракторы/сёдла/бассейны/потоки); прогноз как эволюция поля + anomaly-scan.

**Ограничения.** Тяжёлый GPU-пайплайн; сырые корпуса и артефакты в приватном репо; публичный миррор — методологический код.

**Интеграция.**
- **Слой**: `science` (structural/causal/time-series контур).
- **Метод**: `imported-framework` — стадии как science-операторы; тяжёлое — batch-jobs (GPU), не inline.
- **Что даёт**: (1) **эталон вычисления belief-инварианта атомарной сущности**: z-траектория + положение в ландшафте; (2) нейро-ODE поле → claims класса structure («устойчивые режимы дискурса» = аттракторы/сёдла); (3) forecasting-слой → counterfactual-сценарии для spec-ops; (4) streaming proposition tracker → образец incremental projection.
- **Как подключить**: (1) стадии 0–2 — в interpretation (вход: mention/claim-потоки); (2) стадии 3–7 — science batch-операторы (вход: фикстура-корпус, выход: proposition catalog с evidence-линками); (3) стадии 8–10 — per-window jobs (артефакт `belief_landscape/{window}.bin`); (4) стадия 11 — forecasting toolkit как science-tool (claims привязаны к окну фикстуры); (5) всё GPU-тяжёлое — off-path batch, результаты — immutable artifacts.
- **Приоритет**: **P1** (science core: belief-инвариант). **Лицензия**: MIT → vendoring OK. **Риск**: GPU/данные; LLM-вызовы — бюджетировать.

## 4.2 persistence-agent — persistent homology для поведения агента (Rust)

**Что это.** «Persistent homology for agent behavior»: действия агента образуют point cloud в behavior-space; персистентная гомология отделяет сигнал от шума. Долгоживущие топологические фичи = реальная «личность» агента; короткоживущие = шум.

**Математика.** H₀ (connected components) = **стабильность** (сколько поведенческих кластеров устойчиво); H₁ (loops) = **адаптивность** (циклы поведенческого исследования); H₂ (voids) = **глубина** (сложные многомерные паттерны). Пайплайн: `ActionPoint` → `PointCloud` (distance matrix; `Metric::Cosine`) → `VRComplex` (simplices) → `BoundaryMatrix` + reduction → `Barcode` (birth, death; ∞ для essential features) → `AgentFeatures` → archetype (Steady, Explorer, Deep, Balanced, Volatile).

**Фичи.** Чистая Rust-имплементация без внешних math-зависимостей; модули point_cloud / barcode / features; barcode-инспекция с печатью интервалов.

**Ограничения.** VR-комплекс комбинаторно растёт с числом точек — окна надо ограничивать; для больших популяций — witness-подход (см. 4.3); дистанция по умолчанию cosine.

**Интеграция.**
- **Слой**: `science` (TDA-операторы поведенческих инвариантов).
- **Метод**: `imported-crate` (Rust workspace) — science-worker/service.
- **Что даёт**: поведенческий инвариант атомарной сущности: **barcode = динамическая топологическая подпись** действий (человек/аккаунт/агент); features → facets сущности в projection; archetype → понятные аналитику ярлыки (фильтры в webapp).
- **Как подключить**: (1) worker: вход — временной ряд action-векторов сущности (наши observation-фичи: post/comment/reply/network-метрики); выход — barcode + features + archetype как claim с evidence на окно наблюдений; (2) bottleneck-дистанция между баркодами = сравнение сущностей («насколько похожи поведенческие подписи»), drift-детекция между окнами; (3) archetype-ярлыки — facet для UI.
- **Приоритет**: **P1**. **Лицензия**: custom «Copyright (c) 2025-2026 SuperInstance Contributors» — permissive-стиль, уточнить terms при вендоринге. **Риск**: размер облаков — окна + даунсэмплинг; большие наборы — witness-topology.

## 4.3 topology/witness-topology — witness complexes для флотов агентов (Rust)

**Что это.** TDA-библиотека для верификации поведения агентов через **witness complexes**: разреженные топологические скелеты из landmark-агентов; persistent homology выявляет поведенческие режимы флота. Построена с нуля — без внешних math-зависимостей.

**Компоненты.** Landmark selection: `max_min_sampling` (farthest-point итерация), `random_selection` (seeded), `greedy_spacing`; `weak_witness_complex` (sparse approximation полной топологии); `compute_persistence` (диаграммы); diagram distances (bottleneck / Wasserstein); Mapper graphs (сводка высокоразмерных данных в интуитивный граф); stability guarantees (provable bounds: возмущение данных → ограниченное изменение топологических выводов).

**Hands-on.** `PointCloud::from_points(...)` → `max_min_sampling(&cloud, k)` → `weak_witness_complex(&cloud, &landmarks, 2, 3)` → `compute_persistence(&complex)` → `diagram.points` (birth, death, dim).

**Ограничения.** Разреженное приближение ≠ полная гомология (но есть stability bounds); API ранний.

**Интеграция.**
- **Слой**: `science` (масштабируемый TDA-движок для больших популяций сущностей).
- **Метод**: `imported-crate`.
- **Что даёт**: (1) witness complex как production-TDA там, где VR-комплекс (4.2) не тянет по размеру; (2) **mapper graphs → UI-ready сводки**: webapp «Mapper»-панель — кластеры сущностей/режимов и переходы между ними; (3) bottleneck/Wasserstein → сравнение «поведенческих подписей» между окнами (drift атомарной сущности); (4) stability bounds → claim с квантифицированной устойчивостью (evidence-first: выводы не артефакт шума).
- **Как подключить**: (1) science-worker: вход — облако фичей сущностей (окно), выход — persistence diagram + mapper-граф + distances; (2) mapper-граф → projection-артефакт, рендер в webapp; (3) пайплайн согласовать с 4.2 (общий формат ActionPoint/features).
- **Приоритет**: **P1** (пара с 4.2). **Лицензия**: NO-LICENSE-FILE в `donors/topology` → методы переносим; код — clean-room/изоляция; решение владельца. **Риск**: ранний API — зафиксировать свою обёртку-фасад.

## 4.4 PHoDMSs — spatiotemporal persistent homology & erosion distance

**Что это.** Research-код (Woojin Kim & Facundo Mémoli, Ohio State; DG 2020): (1) вычисление **spatiotemporal persistent Betti-0** и **rank invariant** для **dynamic metric spaces** (DMS — временной ряд distance-функций на фиксированном множестве: стаи птиц, соцсети); (2) квантификация различия двух DMS по их spatiotemporal-топологии через обобщение **erosion distance** (Amit Patel); (3) генератор DMS по **Boids-модели** (torus 500×250; separation/alignment/cohesion forces&radii; 100+ точек); (4) отдельный инструмент — erosion distance между 1-D persistence modules (rank invariants). Python + Dionysus 2.

**Hands-on.** `python boids_simulation.py [num_points] [separation_force] [alignment_force] [cohesion_force] [dmsfile]` (или полный набор радиусов); `betti_generator.py [dmsfile] [bettifile] 40 0 50 5`.

**Ограничения.** Вычислительно тяжёлые структуры; 100+ точек — уже «мощная инфраструктура»; кодовые конвенции — исследовательские.

**Интеграция.**
- **Слой**: `science` (TDA-контур: динамические метрики).
- **Метод**: `imported-module`.
- **Что даёт**: **метрика различия динамик** двух популяций/сетей — ядро трекинга реляционного инварианта во времени: rank invariant = «форма динамики»; erosion distance = «насколько динамика изменилась/отличается от эталона» → claims класса drift/similarity (кампания A vs B; до/после операции). Boids-генератор — синтетические фикстуры для тестов всего TDA-стека.
- **Как подключить**: (1) science-worker: вход — два DMS-окна (наши временные distance-матрицы по сущностям/сообществам); выход — rank invariants + erosion distance + Betti-0 кривые; (2) сценарии: сравнение динамики сообществ до/после информационной операции, детект смены режима; (3) Boids → фикстуры в тестах 4.2/4.3.
- **Приоритет**: **P1** (science/TDA). **Лицензия**: MIT → vendoring OK. **Риск**: Dionysus2-зависимость (зафиксировать версию); производительность — ограничивать окна.

## 4.5 HypergraphX (HGX) — библиотека higher-order сетей (BSD-3)

**Что это.** Python-библиотека (HGX-TEAM, Trento) для анализа систем с **групповыми взаимодействиями**: конструкция/визуализация/анализ гиперграфов — weighted, directed, temporal, multiplex. Единый источник инструментов для higher-order данных: конверсии между представлениями, метрики higher-order организации, фильтрация/разрежение (sparsification), генеративные модели, динамические процессы (contagion → synchronization). Docs, tutorials, PyPI.

**Ключевые API (иллюстрация).** `Hypergraph(edge_list=[(1,2,3),(2,4)])`; weighted + `node_metadata`/`edge_metadata`; конверсии представлений; генераторы; процессы на гиперграфах.

**Ограничения.** Активная молодая библиотека (API эволюционирует); часть алгоритмов — исследовательские.

**Интеграция.**
- **Слой**: `projection` (higher-order модель данных) + `science` (динамика).
- **Метод**: `imported-module`.
- **Что даёт**: (1) гиперграф как честная модель «атомарная сущность в групповых актах»: со-упоминания, со-участие в событиях, ко-комментинг — группы, а не только парные рёбра → higher-order деривации в projection (гипер-степени, гипер-кластеризация, центральности); (2) contagion/synchronization на гиперграфах → science-сценарии claims (вброс через группу vs пару); (3) конверсии (clique expansion, bipartite-проекции) — совместимость с нашими граф-сервисами (Raphtory/Neo4j-слой).
- **Как подключить**: (1) projection-джоб: построение гиперграфов из co-mention/co-event, вычисление HGX-метрик как facets сущностей; (2) экспорт вниз — в существующие граф-хранилища; (3) science: contagion-прогоны на гиперграфе как counterfactual-fixture.
- **Приоритет**: **P1**. **Лицензия**: BSD-3 → vendoring OK. **Риск**: фиксировать версию (pin) + smoke-тесты конверсий.

## 4.6 hive-mind-gnca — GNCA Titans & Civic Nervous System

**Что это.** Horizon 3 исследовательской программы Algoplexity: моделирование системного заражения, алгоритмической монокультуры и коллективного интеллекта через topological deep learning и cyber-physical интерфейсы. Гипотеза: коллективные феномены (финансовые крахи, паники, policy-gridlock) — **emergent computations** из синхронизации **nested optimization** процессов в сети.

**Три теоретических слоя.** Physics (AID — algorithmic information dynamics: определение «структуры»); Agent (UAI/QCEA: интеллект = поддержание когерентности против энтропии); Network (higher-order cybernetics: консенсус как **simplicial phase transition**). Диагностический порог (Williams, 2025): коллективный сбой = global coherence loss, когда endogenous drift превышает коллективную скорость обновления: **Λ_Hive > η_Hive ⇒ systemic collapse (Rule 60)**.

**Архитектурная троица.** (1) Engine — **Deep GNCA Titans** (Graph ViTCA + NL): self-modifying Titan-архитектура: **fast weights** = «рефлекс» (System 1: паника/стадность), **slow weights** = «стратегия» (System 2: культурные нормы) → сеть как distributed deep optimizer. (2) Topology — **SGCA** (Simplicial Graph Cellular Automata): апгрейд графа с рёбер на симплексы (треугольники/тетраэдры); «**simultaneity gate**» — нелинейный терм, срабатывающий только при одновременном взаимодействии соседей (математика «Room»-динамики: консенсус требует совместного подкрепления, а не просто связей). (3) Interface — **Civic Resonator** (CPS): мультимодальные сенсоры (audio/capacitive) → Edge-GNCA на ESP32 (локальная энтропия) → ambient haptics/light (группа «чувствует» собственную когерентность).

**Код.** `modules/gnca_titan.py`, `modules/simplicial_layer.py` (детект треугольников), `modules/diff_logic.py` (differentiable logic gates → извлечение правил); `hardware/` (firmware ESP32, CAD, schematics); notebooks (Scout Delta Topology; Continuous Herding; Nelson Wetlands); specs (Financial Boids; Civic Nervous System); results (Figure 6 entropy, Figure 8 simplicial bloom).

**Ограничения.** Research-grade код; hardware-часть — вне платформы; эмпирика частичная.

**Интеграция.**
- **Слой**: `science` (синхронизация/коллапс, simplicial contagion) + spec-ops (ранний детектор нестабильности).
- **Метод**: `imported-module` (PyTorch Geometric) + `spec` (документы/идеи).
- **Что даёт**: (1) fast/slow-weight GNCA — модель агентов с разделением «рефлекс/стратегия» → симуляции паник; (2) simultaneity gate — механика группового консенсуса (spec-ops: усиление в «комнатах»); (3) критерий Λ>η — кандидат в science-алерты (systemic-failure раннее предупреждение); (4) diff_logic — интерпретируемое извлечение правил из обученных CA → объяснимые claims.
- **Как подключить**: (1) science-оператор GNCA (вход — граф/симплициальный комплекс сущностей, выход — динамика состояний); (2) проверить Λ/η на фикстурах кризисов; (3) diff_logic → rules в claims.
- **Приоритет**: P2 (сильные идеи, research-зрелость). **Лицензия**: MIT → vendoring OK. **Риск**: research-качество — оборачивать своими тестами.

## 4.7 ABa-KiTo — Agent-Based Kinetics via Topology

**Что это.** Вычислительный фреймворк: извлекает топологические инсайты из симуляций agent-based моделей социально-экономических систем (расширение MoKiTo — Molecular Kinetics via Topology). 3 стадии: (1) exploration state space ABM-симуляции; (2) построение **χ-функции** через **ISOKANN** (Julia-пакет ISOKANN.jl); (3) кластеризация данных, отфильтрованных по χ (динамически близкие состояния — не только по χ-значениям, но и пространственно) + edge assignment → граф-представление системы. χ служит ordering parameter, подсвечивающим доминантные **kinetic pathways** между макросостояниями.

**Контекст.** Кейс статьи «Green Growth Meets Koopman: A Data-Driven Understanding of Economic Green Transitions in an Agent-Based Model»; полный датасет на Zenodo.

**Ограничения.** Julia-тулчейн (ISOKANN.jl); исследовательский код; работает поверх готовых ABM-траекторий.

**Интеграция.**
- **Слой**: `science` (кинетика переходов между макросостояниями).
- **Метод**: `imported-module`.
- **Что даёт**: (1) превращение сырых симуляций (наших 5.x sims и любых trajectory-данных) в **граф макросостояний с kinetic pathways**: «откуда/куда перетекает система, где узкие места» → structure-claims; (2) χ/ISOKANN — общий метод для любых временных рядов состояний; (3) edge assignment — техника построения графа переходов.
- **Как подключить**: (1) science-оператор после sim-прогонов (вход: trajectory data; выход: χ + кластеры + граф); (2) визуализация pathways — science-панель webapp; (3) применять к econ-симуляциям (8.1/8.2) и polarization-ABM (4.8).
- **Приоритет**: **P1** (метод универсален поверх наших sims). **Лицензия**: NO-LICENSE-FILE (ABa-KiTo) → методы переносим; ISOKANN.jl — своя лицензия (проверить при вендоринге). **Риск**: Julia-тулчейн в прод-контуре — обёртка через вызов из Python.

## 4.8 ABM_polarisation — Schelling-сеть поляризации (Julia)

**Что это.** Julia-комплект ABM: `99_functions.jl` (библиотека функций анализа), `schelling-network.jl` (Schelling-модель на сети), README-файлы (`README.txt`, `schelling-network_README.txt`). Моделирует поляризацию/сегрегацию через сетевые взаимодействия агентов распространения мнений.

**Интеграция.**
- **Слой**: `science` (базовая модель поляризации).
- **Метод**: `imported-module` (транскрипция в Python или Julia-сервис).
- **Что даёт**: (1) минимальная эталонная модель поляризации — фикстура валидации более сложных движков (posim 5.3, DualMind 5.7, EvoCorps): если сложная модель не воспроизводит простые Schelling-эффекты — сигнал ошибки; (2) `99_functions` — библиотека сетевых/поляризационных метрик для переиспользования.
- **Как подключить**: (1) фикстура «schelling polarisation»; (2) метрики — в science-каталог.
- **Приоритет**: P2. **Лицензия**: NO-LICENSE-FILE → методы переносим. **Риск**: Julia — обёртка вызова.

## 4.9 Raphtory — temporal graph DB (Rust + Python, GPLv3)

**Что это.** In-memory vectorised граф-БД на Rust с Python API (`pip install raphtory`): сотни миллионов рёбер на лаптопе; embedded или сервер (GraphQL); **time-travel**, full-text search, multilayer-моделирование; advanced analytics: automatic risk detection, dynamic scoring, **temporal motifs**; по подписке — on-disk (out-of-memory) масштабирование без потери производительности.

**Интеграция.**
- **Слой**: `projection` (temporal graph storage) — кандидат на движок временных проекций.
- **Метод**: `service`/`reference` (GPLv3 → изолированный сервис; паттерны перенимаем в любом случае).
- **Что даёт**: (1) **time-travel-хранилище** для нашей временной модели проекций: снапшоты графа на момент t — идеально для воспроизводимости evidence-first; (2) temporal-motifs API — для coordination-сигнатур (согласуется с 1.8); (3) multilayer — bridge к higher-order моделям (4.5); (4) dynamic scoring/risk detection — идеи для алертов.
- **Как подключить**: (1) пилот: сервис + наш temporal-экспорт → прогнать алерты; (2) сравнить с текущим граф-контуром по производительности/эргономике; (3) time-travel query-паттерн — перенять безусловно.
- **Приоритет**: P2 (пилот) / **P1** (паттерны). **Лицензия**: GPLv3 → изоляция, attribution. **Риск**: license-граница; интеграционный вес.

## 4.10 adversarygraph — CTI-to-detection workbench (self-hosted)

**Что это.** AI-assisted workbench: ATT&CK mapping, hypothesis-driven threat hunting, **Threat Radar** early warning, **Evidence-to-Detection Graph** reasoning, IOC enrichment, CVE Library correlation, malware-analysis triage, asset attack-surface review, Attack Simulation, SIEM validation. Превращает threat reports / IOC evidence / CVE-контекст / malware-leads / asset-инвентарь → reviewed ATT&CK/ATLAS mappings и detection-инженерные work items.

**Ключевые способности.** Ингест отчётов (text/PDF/DOCX/TXT) с AI-assist; **Threat Radar** (CVE/KEV/PoC/zero-day/supplier/package/hardware сигналы; product exposure scoring; case graphs; PSIRT/Hunt/IR/Detection workflows; saved-asset registry; passive OSINT + isolated MCP safe-Nmap + web posture checks + verified TLS/DNS posture + signed/rate-limited Nuclei templates + local CVE candidates + MCP tool trace + governed AI review); **Threat Hunting** (фальсифицируемые гипотезы, bounded scope, versioned query plans, preserved findings, reviewed dispositions); **Query Library** (Sigma/YARA-L, Git-backed фиды, deterministic IOC-to-query в 10 форматах); **Hybrid RAG** (PostgreSQL full-text + **pgvector**, citation-bound AI answers, expiring Navigator proposals); **bounded MCP server** (read-only/advisory, без авто-мутаций платформы); ATT&CK/ATLAS Navigator overlays; IOC Library + VirusTotal pivots; CVE Library (NVD + CISA KEV sync, CVSS/CWE/CPE, строгие APT-TTP-IOC-CVE корреляции); Asset Attack Surface mapping (`namespace:value` labels); Malware Analysis (изолированный MalwareGraph: static triage, strings, unpacking, AI summaries); **Attack Simulation** (TTP-first lab-сценарии, реальная телеметрия атакуемого сервера, SIEM forwarding, kill-chain drills); **Evidence-to-Detection Graph** (evidence → claims → behavior → ATT&CK → required telemetry → detection candidates → rules → validation → SIEM results → analyst decisions); observability dashboard (metrics/traces/redacted log tails). Релиз: v8.0.0-beta (report review gate, durable authority, transactional outbox + receipt fencing, Alembic-гейты); React Router 7.

**Ограничения.** Лицензия — **personal use only**; beta-статус; тяжёлый стек.

**Интеграция.**
- **Слой**: spec-ops (hunting/validation) + projection/science (hybrid RAG-паттерн) + webapp (Operational UI).
- **Метод**: `service` (изолированный) + `reference` (их архитектурные паттерны — ценнее кода).
- **Что даёт**: (1) **Evidence-to-Detection Graph** — прямой архитектурный референс нашей цепочки claim→evidence→detection (evidence-first!); (2) hybrid RAG (FTS+pgvector+one-hop allow-listed expansion) — паттерн retrieve для наших findings; (3) Threat Radar workflow — аналог нашего feedback/early-warning контура; (4) bounded MCP (read-only + advisory, без мутаций) — паттерн governance для нашей MCP-поверхности.
- **Как подключить**: (1) изучить граф-модель (таблицы/связи) при проектировании claims-графов; (2) hunting-гипотезы/query plans → science-модуль; (3) MCP-bounded→ дизайн control-plane.
- **Приоритет**: P2 (reference/service; не вендорим из-за personal-use). **Лицензия**: AdversaryGraph Personal Use License → изоляция/референс. **Риск**: license; объём стека.

## 4.11 lau-network-science — Rust network-science library (MIT)

**Что это.** Комплексная Rust-библиотека network science: построение графов, генеративные модели, центральности, community detection, эпидемические симуляции, degree-distribution анализ, agent-based соцсетевые модели. Стек: `nalgebra`, `rayon`, `serde` — чистый Rust, без C-bindings и внешних солверов.

**Возможности.** Построение графов (undirected/directed, adjacency-list, BFS, connected components, serde-сериализация); генераторы (Erdős–Rényi G(n,p)/G(n,M), **Barabási–Albert**, **Watts–Strogatz**); центральности (degree, **betweenness по Brandes**, closeness, eigenvector через power iteration, **PageRank** undirected+directed); communities (**Louvain**, label propagation, modularity, **NMI**); структура (small-world σ/γ/λ, clustering coefficient, transitivity, degree assortativity, mixing matrices, k_nn(k)); эпидемии (**SIR/SIS** на произвольных графах, epidemic threshold, multi-run final-size); resilience (random percolation узлов/рёбер, targeted degree-attacks, **Molloy–Reed** threshold); distributions (**power-law MLE** Clauset–Shalizi–Newman, CCDF, Gini, scale-free detection); **AgentNetwork** (именованные агенты с атрибутами, взвешенные взаимодействия, influence rankings, bridge agents, community memberships, summary stats).

**Интеграция.**
- **Слой**: `projection` (граф-метрики, native Rust) + `science` (симуляции).
- **Метод**: `imported-crate`.
- **Что даёт**: (1) единый toolbox метрик для facets атомарных сущностей (centrality-наборы, community, bridge-роли, PageRank); (2) эпидемические/resilience-симуляции для стресс-тестов графа (в паре с science); (3) power-law/Gini/scale-free — facet «тип сети».
- **Как подключить**: (1) dependency в projection-engine; (2) centrality/pagerank/communities — периодические projection-jobs; (3) AgentNetwork — модель наших сущностей с атрибутами и взвешенными взаимодействиями.
- **Приоритет**: **P1** (метрики) / P2 (sims — дублируют science-контур). **Лицензия**: MIT → vendoring OK. **Риск**: сверить метрики с networkx-эталонами (sanity-тесты).

> **Кластер 4 завершён (11/11).** Интеграционная карта: `09-INTEGRATION-MATRIX.md`.
