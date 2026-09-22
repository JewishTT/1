# Cluster 1 — Cognitive Warfare · Narratives · Influence · Bias

> Часть каталога `docs/architecture/donors/`. Governing spec: `specs/009-donor-full-catalogue/spec.md`.
>
> **Атомарная сущность** (платформенный канон): человек / компания / организация / канал / событие — **динамический реляционный инвариант, закреплённый за общим пайплайном** (`acquisition → interpretation → admission → projection → science → feedback`). Инвариант меняется во времени; моделируется методами от классической объектной репрезентации до science-network и TDA. Доноры кластера дают методы вычисления/трекинга инвариантов: belief-state, narrative-position, bias-profile, coordination-signature, phase-state.

## Роль кластера в пайплайне

| Донор | Слой | Извлекаем | Механизм |
|---|---|---|---|
| f.txt (paper) | spec-ops doctrine, science KPI | OODA-фрейм, измеримые атрибуты cognitive superiority, кейс | knowledge/spec |
| дополнительно.txt (MCP) | acquisition, science, spec-ops | SIR-Hawkes, DeGroot, Stackelberg, Potts, Hegselmann–Krause, greedy influence, double-robust ATE | mcp-server + reference-math |
| Cognitive-Weaponization-Matrix | interpretation, spec-ops KB | 5GW-таксономия техник и bias-каталог | knowledge-base |
| CognitiveAttack | spec-ops (cognitive redteam), interpretation | ансамбли из 154 bias → adversarial-промпты | ml-model / redteam tooling |
| seithar-research | KB, training | исследования influence / cognitive security | knowledge-only |
| NarrativeDiffusion | interpretation, science | P(adoption)=αW+βI+γA поверх causal-графа нарратива | imported-module |
| io-coordinated-replies | interpretation, admission | 2 supervised-классификатора reply-атак (AUC 0.88/0.97) | ml-model |
| IO-detecting-and-anticipating | projection, science | temporal signatures, GNN/TGNN link-prediction, static/temporal motifs | imported-module |
| DIMA-OntoToolkit | interpretation | arguments/agents/quotes → OWL/SPARQL bias-detection | imported-module |
| Lying_with_Truth | spec-ops, science | CoPHEME датасет + generative-montage attack plans | dataset + method |
| EvoCorps | spec-ops, science | multi-agent depolarization (Analyst/Strategist/Leader/Amplifier) | imported-framework |
| cognitive_phase_transitions | science | Kuramoto+Hebbian, order parameter/MPC, critical point | imported-module |

## 1.1 f.txt — Cognitive Warfare: Definition, Framework, and Case Study

**Что это.** Статья (Rushing, Hersch, Xu; arXiv:2603.05222v1, CC BY 4.0). Унифицированное определение cognitive warfare; интеракционный фрейм на базе OODA-петли Бойда; измеримые атрибуты cognitive superiority; показательный кейс (Norland: acute-фаза 72 часа + chronic-фаза недели–месяцы; attacker objectives AAO1–4 / ACO1–3: information saturation, attribution ambiguity, growth decision latency, institutional trust erosion, identity-frame polarization, credibility inversion).

**Методы.** Матрица attacker/defender objectives × OODA-фазы. Метрики: decision latency, decision error, misaligned action, trust calibration, belief receptivity. Потоки данных для assessment: time-stamped C2-логи (decision timestamps, meeting cadence), incident reports/after-action notes, соцмониторинг (volume/velocity), coarse public-sentiment polling. Attacker capabilities: access/delivery, narrative engineering, amplification, adaptation (AC1–…).

**Ограничения.** Только фрейм и кейс — кода нет; метрики преимущественно качественные; notional-сценарий требует адаптации под наши фикстуры.

**Интеграция.**
- **Слой**: spec-ops (доктрина) + science (KPI-модель).
- **Метод**: knowledge/spec — фрейм как **схема измерений** для spec-ops drills и science-claims.
- **Что даёт**: словарь метрик (decision latency/error, trust erosion, receptivity) → claims о cognitive-воздействии в `science`; измеримые атрибуты успеха — в отчётность spec-ops кампаний.
- **Как подключить**: (1) зафиксировать OODA-objectives (Observe/Orient/Decide/Act) как enum в spec-ops scenario-схеме; (2) маппинг «objective → measurable attribute → data source» в шаблон campaign-report; (3) кейс Norland — как готовый lab-сценарий в scenario registry (acute+chronic фазы).
- **Приоритет**: P2. **Лицензия**: CC BY 4.0 (attribution). **Риск**: нулевой (концепт).

## 1.2 дополнительно.txt — Cognitive Warfare & PsyOps MCP (Apify)

**Что это.** Внешний MCP-сервер для агентов (Claude/Cursor/Windsurf) с 8 инструментами анализа информационной войны, работающий на 16 источниках Apify, запрашиваемых параллельно. Инструменты: `detect_narrative_operations` (SIR-Hawkes), `model_belief_dynamics` (DeGroot), `optimize_counter_narrative` (Bayesian Stackelberg), `forecast_polarization_phase_transition` (Potts + Hegselmann–Krause), `map_influence_topology` (submodular greedy), `attribute_narrative_causation` (double-robust ATE + Rosenbaum gamma) и др. Классификация операций: усиление/подавление/искажение/фабрикация/поляризация; уровни угрозы low/medium/high/critical.

**Методы.** SIR+Hawkes self-excitation (сопряжённая эпидемическая модель); DeGroot social learning (eigenvector centrality, spectral gap = скорость конвергенции, polarization index, belief clusters); байесовская игра Штакельберга (контрнарратив); Potts (фазовые переходы: stable/polarized/fragmented); Hegselmann–Krause (cluster distribution позиций); submodular greedy (гарантия (1−1/e)≈0.632 в independent cascade); double-robust ATE (состоятельна при корректной propensity ИЛИ outcome-модели; указывать Rosenbaum gamma рядом с ATE).

**Источники (16).** Bluesky, Hacker News, Wikipedia, Federal Register, Interpol Red Notices, OpenSanctions (100+ программ), website change monitor, Wayback Machine, REST Countries, GDACS, Congress bills, NOAA weather, GitHub search, web→Markdown, DNS search, IP-geolocation.

**Ограничения.** Платный сервис (per-tool $0.045–0.055); нет X/Twitter и Telegram; выдаёт structured analysis, не дашборды; Apify-планировщик/webhooks — внешняя оркестрация.

**Интеграция.**
- **Слой**: acquisition (data-коннектор), science (методы), spec-ops (counter-narrative planning).
- **Метод**: `mcp-server` (внешний tool-провайдер control-plane) + **reference-math** (формулы локализуем в `apps/science`).
- **Что даёт**: (a) прообраз нашей MCP-поверхности OSINT-инструментов (tools/results-контракты); (b) 8 готовых мат-моделей — кандидаты в science-операторы: `polarization_phase_transition`, `belief_convergence` (spectral gap), `narrative_ate`, `influence_seed_selection` (greedy).
- **Как подключить**: (1) tool-gateway в control-plane с quota/учётом платности; (2) локализовать модели: DeGroot eigenvector+spectral gap; SIR-Hawkes co-occurrence; HK/Potts phase-classifier — как science-операторы с фикстурами; (3) webhooks Apify → acquisition-триггеры (threat level = CRITICAL, irreversibilityRisk > 0.70).
- **Приоритет**: P1 (модели) / P2 (коннектор). **Лицензия**: внешний сервис. **Риск**: платность; дублирование acquisition — использовать только недостающие источники.

## 1.3 Cognitive-Weaponization-Matrix — таксономия 5GW

**Что это.** Репозиторий-знание (Anadema): таксономия пятого поколения войны (5GW) «война информации и восприятия». Целит в pre-existing cognitive biases людей и организаций, а также создаёт новые. Отличия от конвенциональной войны: фокус на individual observer/decision-maker; трудность/невозможность атрибуции; скрытность природы атаки; отсутствие этики; стратегия subversion / infiltration / turn influencers. Внутри: Techniques, Key Concepts, quotes, Cognitive Bias Codex (John Manoogian III).

**Методы.** Качественная таксономия техник + bias-каталог; тезис «battlefield определяет форму боя»: масс-технологии и датасеты open/gray market — топливо для cognitive-weaponization.

**Ограничения.** Не код; публицистический тон; требует научной калибровки при переносе в KB.

**Интеграция.**
- **Слой**: interpretation (mapping риторики → техника), spec-ops KB (cognitive-redteam планирование).
- **Метод**: `knowledge-base` — структурированный KB-контент (yaml/json: technique id, name, description, observable markers, references).
- **Что даёт**: словарь attack-techniques для интерпретации текста (detected rhetoric → 5GW technique id); планка для spec-ops planning; стыковка с bias-ансамблем CognitiveAttack (1.4).
- **Как подключить**: (1) извлечь technique/bias списки в structured KB; (2) observable markers → детекторы в interpretation; (3) technique id → facet в UI spec-ops панели.
- **Приоритет**: P2. **Лицензия**: без файла → knowledge-использование (таксономии/факты; не вендоринг). **Риск**: нулевой.

## 1.4 CognitiveAttack — синергетические когнитивные биасы против LLM-safety (AAAI 2026)

**Что это.** Red-teaming фреймворк: адаптивно подбирает оптимальные **ансамбли из 154 когнитивных bias** (из социальной психологии) и инженерят их в adversarial-промпты, обходя safety-механизмы LLM. Результаты: systemic-уязвимости на 30 mainstream LLM (особенно open-source); ASR **60.1%** против SOTA PAP 31.6%; количественный анализ успешных джейлбрейков → паттерны уязвимостей. AAAI 2026 Oral.

**Архитектура.** Python; `main.py` — обучение red-team модели; `attack.py` — эвалюация против target LLM; `requirements.txt`; assets (Overview/CognitiveAttack схемы). MIT License, research use only.

**Методы.** Multi-bias synergy: ансамбли bias'ов, а не изолированные; обучение селектора комбинаций; измерение ASR/эффективности; выявление vulnerability patterns у safety-aligned моделей.

**Ограничения.** Генерация harmful-контента — только изолированное ответственное использование; открытая версия исследовательская.

**Интеграция.**
- **Слой**: spec-ops (cognitive redteam / LLM-security), interpretation (bias-детекторы).
- **Метод**: `imported-module` (MIT) + knowledge (154-bias каталог).
- **Что даёт**: (1) red-team движок для тестов **наших собственных LLM-агентов** (control-plane, MCP-инструменты) на устойчивость к bias-манипуляциям — внутренний safety-eval; (2) 154-bias каталог → онтология bias-маркеров для interpretation («сообщение эксплуатирует bias X»); (3) методология ASR-benchmark → наш внутренний leaderboard.
- **Как подключить**: (1) `attack.py` против staging-агентов в CI как security-gate (отдельный контур логирования); (2) выгрузить bias-каталог в KB (id/name/description/examples); (3) интерпретатор использует те же id в claims.
- **Приоритет**: **P1** (LLM-security контур). **Лицензия**: MIT (research-only оговорка → внутренний контур OK). **Риск**: harmful-контент — изоляция, отдельные логи.

## 1.5 seithar-research — research-портал cognitive warfare

**Что это.** Инструмент-портал для понимания cognitive warfare: influence operations, misinformation, social engineering; разделы SCT taxonomy, cognitive security, influence operation analysis; отчёты и кейсы; локальный запуск (Win/macOS/Linux, 4GB RAM, 500MB); экспорт отчётов.

**Методы.** Знание-ориентированный портал; таксономия SCT; без алгоритмов.

**Ограничения.** Не код-фреймворк; CC BY-NC 4.0 → non-commercial.

**Интеграция.**
- **Слой**: KB / обучение аналитиков.
- **Метод**: `knowledge-only` (термины, кейсы, таксономия SCT).
- **Что даёт**: SCT-таксономия и примеры influence-операций → KB-статьи с маппингом на 5GW (1.3) и bias-онтологию (1.4); учебные материалы для онбординга аналитиков.
- **Как подключить**: distilled-конспекты в KB (attribution, non-commercial); ссылки из cognitive-warfare раздела.
- **Приоритет**: P3. **Лицензия**: CC BY-NC 4.0 → код не вендорим. **Риск**: нулевой.

## 1.6 NarrativeDiffusion — graph-theoretical adoption model

**Что это.** Research-код (Syracuse University): математическая модель принятия (adoption) элемента нарратива, расширяющая Trabasso (память ↔ центральность в causal-сети): adoption-вероятность как комбинация позиции в нарративном causal-графе, социального влияния и личного alignment'а.

**Математика.** W(s_i)= (1/|S_t|)·Σ 1/(d(s_i,s_j)+1) — narrative influence (по расстояниям до уже принятых story items); I(s_i)=2/(1+e^{−ιn_i})−1 — social influence (логистика от числа соседей, принявших item); A(s_i)=(1+a_i)/2 — alignment (a_i ∈ [−1,1]); **P′(s_{i,t+1}|S_t,A) = αW(s_i)+βI(s_i)+γA(s_i)**, α+β+γ=1.

**Ограничения.** Только модель (README+формулы); требует калибровки α/β/γ на реальных каскадах; оценивает один агент-перспективу.

**Интеграция.**
- **Слой**: interpretation (оценка распространения), science (claims).
- **Метод**: `imported-module` — малая модель, форвардим формулы напрямую.
- **Что даёт**: оператор adoption-вероятности для трекинга **нарративного инварианта** сущности/нарратива: αW (структура истории) + βI (соцсеть) + γA (личный фильтр); центральность story item в causal-графе — facet.
- **Как подключить**: (1) строим causal-граф нарратива из наших claims/mentions (story items + причинные рёбра); (2) калибровка α/β/γ на фикстурах каскадов; (3) вывод — claim с uncertainty (какой сегмент аудитории примет item при данных W/I/A).
- **Приоритет**: **P2** (метод на готове). **Лицензия**: NO-LICENSE-FILE → методы переносим, код — clean-room (мал). **Риск**: калибровка.

## 1.7 io-coordinated-replies — детекция coordinated reply attacks (ICWSM 2025)

**Что это.** Репликационный код статьи «Coordinated Reply Attacks in Influence Operations: Characterization and Detection» (Pote, Elmas, Flammini, Menczer): характеризация и детекция тактики скоординированных ответов (поддержка/харассмент целей, влияние на них и их подписчиков). Ключевая находка: основные цели — влиятельные люди (журналисты, медиа, гософициальные лица, политики); атакуемые аккаунты работают как **сенсоры** для детекции influence-операций. Два supervised-классификатора: (1) classify tweets → targeted by reply attack (**AUC 0.88**); (2) classify accounts-репликаторов → участник coordinated attack (**AUC 0.97**).

**Архитектура.** Python: pandas, imbalanced-learn, scikit-learn, shifterator, stopwordsiso, wordcloud; helper-package; скрипты по RQ1/RQ2/RQ3; данные — Zenodo (doi 10.5281/zenodo.13896308).

**Ограничения.** Twitter-специфичные фичи; код исследовательский; лицензия не заявлена.

**Интеграция.**
- **Слой**: interpretation (reply-сигналы), admission (facets аккаунта).
- **Метод**: `ml-model` (supervised-классификаторы) — переносим фичи/пайплайн, обучаем на наших данных + их датасете.
- **Что даёт**: (1) детектор «сущность под reply-атакой» → claim + facets; (2) детектор «аккаунт — скоординированный репликатор» → coordination-facet; (3) паттерн «targets as sensors»: watchlist влиятельных сущностей как сенсорная сеть (связка с feedback-петлёй).
- **Как подключить**: (1) фичи (текст реплаев + метаданные) в наш feature-store; (2) обучение на платформенной разметке; (3) выходные скоры — в projection/science; (4) цели-«сенсоры» — приоритизация acquisition в feedback.
- **Приоритет**: **P1**. **Лицензия**: NO-LICENSE-FILE → методы переносим, код — clean-room. **Риск**: адаптация фич под наши источники (не только Twitter).

## 1.8 IO-detecting-and-anticipating — temporal signatures of coordination

**Что это.** Репликационный код «Temporal Signatures of Coordination: Detecting and Anticipating Influence Operations»: детекция **и антиципация** influence-операций по временным сигнатурам координации: interaction-сети, similarity-сети, static/temporal motifs, link-prediction (GNN, node2vec, TGNN), классификация IO vs organic.

**Пайплайны.** EDA (generate_interaction_network → analysis_over_time_hashtag/urls); static link prediction (construct_dataset → generate_similarity_network → merge_similarity_networks 0.3 → link_prediction_gnn × {all, interactions, similarities} → node2vec-варианты → link_prediction_similarity); temporal link prediction (GNN-temporal, node2vec-temporal, `link_prediction_tgnn_temporal`, `link_prediction_tgnn_similarity_temporal`); classification (classify_io с наборами фич: no_motif / twitter_interaction_types / static_motif / temporal_motif 60s / 3600s / all-combined; c/без temporal-агрегации).

**Методы.** Temporal motifs (окна 60s/3600s), GNN/TGNN на fusion (interaction+similarity) сетях, node2vec-эмбеддинги, статические мотивы; supervised IO-классификация поверх сетевых фич.

**Ограничения.** Twitter-центричность; GNN-пайплайн требует torch/GPU-контура.

**Интеграция.**
- **Слой**: `projection` (temporal-motif деривации, similarity-сети) + `science` (link-prediction = антиципация).
- **Метод**: `imported-module`.
- **Что даёт**: (1) temporal-motif counting → **coordination-signature** facet сущности/группы; (2) link-prediction → claims «вероятное установление связи» — не только ретроспекция, но **early-warning**; (3) fusion interaction+similarity сетей — метод сборки наших проекций.
- **Как подключить**: (1) motif/temporal-модули → projection-джобы (периодические, по окнам); (2) GNN-пайплайн — на фикстурах, выход вероятностей → science-claims с калибровкой; (3) features-наборы адаптировать к нашим типам взаимодействий.
- **Приоритет**: **P1**. **Лицензия**: MIT → vendoring OK. **Риск**: GPU для GNN; окна/пороги (60s/3600s) перекалибровать под наши источники.

## 1.9 DIMA-OntoToolkit — narrative bias extraction с OWL/SPARQL (Apache-2.0)

**Что это.** Python-пайплайн (сознательно **без black-box AI**): сканит тексты статей/публичных сообщений, раскладывает в логическую структуру, спроектированную экспертами (коммуникация, риторика, психология), детектит bias'ы и техники убеждения по фреймворку **DIMA**; каждое срабатывание полностью traceable (чёткое объяснение «где и как применяется влияние»), правила открыты.

**Фичи.** Parsing raw text/папки статей; headline detection (явный или GPT-inferred); **motif segmentation** (семантические мотивы ≈ параграфы); **argument extraction** (premises / developments / conclusions); **narrative agents** (NarratedState / NarratedPolitician / NarratedGeneralPublic / NarratedPerson); **quote extraction** (direct/paraphrased/interpretive, привязка к motif и argument-компоненте); генерация OWL по DIMA-онтологии; HermiT reasoner + SPARQL-запросы. Influence-Mini — лёгкая семантическая модель нарратива. Output: `output/articles_processed/article_processed_<id>.json` (article_id, headline, motifs[], narrative_agents[], quotes[]).

**Ограничения.** GPT-инференс для headline (можно локально заменить); OWL/SPARQL-слой — свой рантайм.

**Интеграция.**
- **Слой**: interpretation (bias/argument extraction), admission (цитируемые evidence-фрагменты).
- **Метод**: `imported-module` (Apache-2.0).
- **Что даёт**: (1) rule-based (не black-box) детектор bias/техник → объяснимые claims с location+explanation (эталон evidence-first интерпретации); (2) argument-модель (premises→developments→conclusions) — скелет обоснований наших claims; (3) narrative agents → маппинг на наши атомарные сущности; (4) quotes — evidence-fragments с привязкой к позициям.
- **Как подключить**: (1) пайплайн → interpretation-оператор (вход: тексты; выход: JSON → mentions/claims); (2) OWL/SPARQL — опциональный query-контур KB (или конвертация в наш граф); (3) HermiT — валидация непротиворечивости extracted-структур.
- **Приоритет**: **P1** (прямое попадание в interpretation; прозрачность). **Лицензия**: Apache-2.0 → vendoring OK. **Риск**: GPT-headline — заменить/opt-in.

## 1.10 Lying_with_Truth — collusion via Generative Montage (ACL 2026)

**Что это.** Демо-материалы исследования cognitive collusion-атак на LLM-агентов: координация агентов манипулирует убеждениями жертвы, используя **только правдивые evidence-фрагменты** (strategic narrative construction). Датасет **CoPHEME** (расширение PHEME): 6 rumor-событий (Charlie Hebdo, Sydney Siege, Ferguson, Ottawa Shooting, Germanwings, Putin Missing), evidence fragments (проверенные правдивые tweets с Local Truth LT=1), target fabrications. Pre-computed attack plans (GPT-4.1-mini): Writer-Editor-Director optimized narratives, validated montage (Director acceptance τ=7.0). Демо-метрики: ASR 81.7%, avg confidence 0.83, high-confidence ASR 67.4%.

**Интеграция.**
- **Слой**: spec-ops (cognitive redteam: collusion-сценарии против LLM-агентов, в т.ч. наших) + science (модели убеждений).
- **Метод**: dataset + `imported-module` (demo code).
- **Что даёт**: (1) корпус атак-планов — redteam-фикстуры: детектит ли наш пайплайн montage-collusion; (2) CoPHEME — eval-набор для детекторов манипуляций, собранных **из правды** (сложнейший класс: не ложь, а селекция); (3) концепт truth-based manipulation → новые фичи интерпретации (детект селективной подачи фактов).
- **Как подключить**: (1) фикстуры → spec-ops LLM-security (в паре с 1.4); (2) CoPHEME → eval-набор interpretation; (3) детектор «montage» — исследовательская задача интерпретации.
- **Приоритет**: **P1** (eval/redteam). **Лицензия**: NO-LICENSE-FILE → датасеты/методы переносим; код — clean-room. **Риск**: dual-use контент — изоляция.

## 1.11 EvoCorps — эволюционный мультиагентный фреймворк деполяризации (MIT)

**Что это.** Фреймворк **деполяризации** онлайн-мнений: не пост-фактум детекция, а моделирование интервенции как непрерывно эволюционирующего социального процесса — мониторинг и корректировка **в ходе распространения**: снижение эмоционального противостояния, подавление распространения крайних взглядов, рост рациональности дискуссии. Роли агентов: **Analyst → Strategist → Leader → Amplifier** (мониторинг → моделирование ситуации → планирование интервенции → факт-основанная генерация контента → мульти-ролевое распространение). Retrieval-augmented collective cognition: база аргументов (evidence KB) + action-result memory; **feedback-based evolutionary learning** (усиление сработавших стратегий, ослабление неэффективных).

**Валидация.** Прогоны на платформе **MOSAIC** (сценарии: распространение негативных новостей; злонамеренное усиление): превосходство над пост-фактум-интервенциями по эмоциональной поляризации, экстремизации мнений и рациональности аргументации (4 режима: обычная дискуссия / злонамеренное усиление без защиты / post-hoc модерация / real-time EvoCorps).

**Стек.** Python 3.9+; HF-датасеты; UI-превью; README на китайском (+ EN).

**Интеграция.**
- **Слой**: spec-ops (интервенционное планирование) + science (деполяризационные стратегии как claims).
- **Метод**: `imported-framework`.
- **Что даёт**: (1) ролевая схема кризис-команды — шаблон spec-ops «intervention cell»; (2) retrieval-augmented память действий-результатов — образец learning-loop (наш feedback); (3) метрики поляризации/рациональности — в science-каталог.
- **Как подключить**: (1) интервенционные прогоны как science-fixture (вход — смоделированное сообщество, выход — траектории метрик); (2) ролевая архитектура → дизайн агентов-помощников spec-ops; (3) UI-превью — в webapp (6.3).
- **Приоритет**: **P1** (cognitive-интервенции). **Лицензия**: MIT → vendoring OK. **Риск**: MOSAIC-зависимость (абстрагировать), язык доков.

## 1.12 cognitive_phase_transitions — фазовые переходы синхронизации (MIT)

**Что это.** Companion-code статьи «Cognitive Phase Transitions in Subjective Physics» (Khomyakov, 2025; Zenodo 10.5281/zenodo.17011035): вычислительные свидетельства критического перехода в адаптивной сети **N=40 когнитивных агентов**. Различаются глобальный order parameter |⟨ψ⟩| (Kuramoto mean-field amplitude) и **MPC** (Mean Pairwise Coherence — локальная синхронизация). Обнаружен немонотонный переход при r_c = **1.534** с резким скачком |ΔMPC| = 0.133 — структурная реорганизация синхронизированных кластеров; после транзиентного десинхрона (MPC min ≈ 0.42) система стабилизируется в high-coherence фазе (MPC = 0.992±0.007). Феноменология аналогична second-order фазовым переходам.

**Реализация.** `scripts/cognitive_phase_transitions.py`: адаптивная сеть фазовых осцилляторов — Kuramoto-like синхронизация + **Hebbian plasticity** + online covariance estimation (free-energy minimization); transition detection и consolidation. Python 3.9+; numpy/networkx/matplotlib/scipy. Фигуры: weight matrix, MPC change, network phase coloring, order parameter & control, phase transition curve, synchronization measure. Полностью воспроизводимый пакет.

**Интеграция.**
- **Слой**: `science` (модель синхронизации и порогов в сообществах).
- **Метод**: `imported-module` (мал).
- **Что даёт**: (1) order parameter + MPC — метрики фазового состояния сообщества (claims: «pre/post-transition фаза»); (2) Hebbian+Kuramoto+free-energy — механика адаптивных сетей (калибруется на наших графах взаимодействий); (3) методология детекта критического параметра — переносим на данные (аналог r_c: доля активности ядер, вызывающая каскадную реорганизацию).
- **Как подключить**: (1) science-оператор: вход — временные ряды активности сети → выход — order/MPC/transition-детект; (2) фигуры — science-панель; (3) калибровка N/связности под наши данные.
- **Приоритет**: **P1** (парная к 5.6 и 1.2). **Лицензия**: MIT → vendoring OK. **Риск**: малая N=40 — масштабировать осторожно.

> **Кластер 1 завершён (12/12).** Интеграционная карта: `09-INTEGRATION-MATRIX.md`.
