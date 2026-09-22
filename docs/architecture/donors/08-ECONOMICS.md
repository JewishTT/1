# Cluster 8 — Экономика · Economic Dynamics

> Часть каталога `docs/architecture/donors/`. Governing spec: `specs/009-donor-full-catalogue/spec.md`.
>
> **Третий домен платформы** (после OSINT-core и отдела спецопераций): экономика. **Атомарная сущность** здесь — компания / рынок / экономический агент; её реляционный инвариант — финансовое состояние, связи капитала и поставок, ожидания/настроения, политико-экономическая устойчивость. Доноры дают симуляционные движки и метрики для counterfactual-прогнозов и стресс-тестов.

## Роль кластера в пайплайне

| Донор | Слой | Извлекаем | Механизм |
|---|---|---|---|
| votranhabysscoremicro | science (econ), spec-ops | 31-слойная экономическая симуляция + PoliticalCore (элиты/медиа/оппозиция, Q-learning политик) | imported-module |
| Entropic-Dynamics-of-the-Universal-Equivalent | science (econ) | ABM эндогенного кризиса (3 класса агентов), готовые фигуры/статистика | imported-module |
| TwinMarket | science (econ) | BDI-агенты финрынка, соцсеть по трейдам, bubbles/crashes, stylized facts | cross-ref → 5.5 |
| ABa-KiTo | science (econ) | χ-кинетика макросостояний (green transition ABM) | cross-ref → 4.7 |
| Operation-Molasses | spec-ops (econ-вектор) | Short-and-Distort: disinfo-бот ↔ обвал цены | cross-ref → 2.5 |

## 8.1 votranhabysscoremicro — 31-слойная экономика + PoliticalCore

**Что это.** Симуляционный фреймворк `VoTranhAbyssCoreMicro` (экономика) + `PoliticalCore` (политика). Заявляемая валидация **90% accuracy** на макро-событиях нескольких экономик при корректном «специальном computational environment» (инструкции — от автора). Экономическая часть зависит от корректного прогона политической: события, движимые энтропией и системной динамикой.

**Экономика (31 слой — выборка механик).** Shadow economy; cultural inertia; propaganda (narrative-driven sentiment); policy multiverse; trust dynamics (GCN-пропагация); timewarp GDP; neocortex emulator (стресс/дефолт-риски); Ponzi daemon; shaman council (прогнозы, влияющие на агентов); system self-awareness (детект манипуляций); investment inertia (trust к институтам); mnemonic market (травмы → паника); expectation decay; nostalgia portfolio; illusion grid; echo chamber; agent possession (иррациональный all-in); parallel economy leak; entropy-bound forecast decay; archetype emergence (Hoarder/Gambler/Prophet/Bureaucrat); dream state shifts; infectious memes; quantum duality portfolio; narrative engine; economic necromancy; meme market mechanics; quantum volatility reflections; psychopolitical agent fusion; endogenous collapse seeds; reflexive necroeconomics; economic singularity (ECOGOL); systemic archetype amplifier. Агенты: **HyperAgent** (formal: wealth, innovation, fear/hope/greed) и **ShadowAgent** (informal: cash, gold, black-market).

**PoliticalCore.** PoliticalAgent (elites/public/media/opposition; influence, loyalty, adaptability, confidence, dissent, debt stress); PoliticalResonanceLayer (нейрослой с phase-shift модуляцией); PoliticalPredictor (LSTM+Transformer): stability, trust, tension, cohesion, unrest, currency substitution, debt-default probability; политики через Q-learning (propaganda/control/reform/repression/stabilize-currency/debt-restructuring); econ→political фидбеки (inflation/unemployment/GDP).

**Стек.** Python 3.8+; numpy, torch, networkx, pandas, scipy, sklearn, filterpy, cupy; GPU strongly recommended.

**Ограничения.** Заявка «90%» внешне неподтверждаема; монолитный research-код; «спец-среда» — внешняя инструкция.

**Интеграция.**
- **Слой**: `science` (econ-counterfactual), spec-ops (модели манипуляции рынком: propaganda → sentiment → price; связка с Short-and-Distort из 2.5).
- **Метод**: `imported-module` (Apache-2.0) — портируем **отдельные слои**, не монолит.
- **Что даёт**: (1) механики-операторы: trust-GCN, echo chamber, entropy-bound forecast decay, narrative engine; (2) political-features (tension/unrest/default-prob) — facet-наборы econ-сущностей; (3) policy-simulator (Q-learning) — counterfactual «какие меры стабилизируют».
- **Как подключить**: (1) слои — как science-операторы (вход/выход — наши схемы); (2) валидировать на фикстурах, заявку 90% не наследовать; (3) econ↔political feedback — связать с 8.2 и TwinMarket (5.5).
- **Приоритет**: P2 (монолит) / **P1** для слоёв (trust-GCN, narrative engine, predictors). **Лицензия**: Apache-2.0 → vendoring OK. **Риск**: неподтверждаемые заявления — маркировать; cupy/GPU — изолированное окружение.

## 8.2 Entropic-Dynamics-of-the-Universal-Equivalent — ABM эндогенного кризиса

**Что это.** Секция 6 исследования: agent-based numerical simulation **endogenous crisis formation** (Colab-stable версия). Три класса агентов: **Liquidity Providers**, **Leveraged Speculators**, **Crisis-Sensitive Reallocators**. Выходы: ABM time series (CSV), summary statistics (CSV), 7 manuscript-ready фигур.

**Методы.** Чистый ABM: кризис возникает **эндогенно** из взаимодействия трёх классов агентов — без экзогенного шока. Идеальный минимальный стресс-генератор для counterfactual-лаборатории.

**Ограничения.** Компактный исследовательский код; один базовый сценарий.

**Интеграция.**
- **Слой**: `science` (econ-симуляции, фикстуры кризисов).
- **Метод**: `imported-module` (малый).
- **Что даёт**: (1) воспроизводимый генератор **эндогенного кризиса** — базовая фикстура стресс-тестов econ-гипотез (согласуется с Λ>η-идеей из 4.6); (2) эталонная минимальная модель для sanity-check более сложных симуляций (8.1, 5.5): сложная модель обязана воспроизводить базовые кризис-паттерны.
- **Как подключить**: (1) перенести как science-фикстуру «endogenous crisis»; (2) расширить классами (ShadowAgent из 8.1) в форках; (3) выходные фигуры → science-панель/отчёты.
- **Приоритет**: **P1** (малая, полезная фикстура). **Лицензия**: NO-LICENSE-FILE → методы переносим; код — clean-room (мал). **Риск**: минимализм модели — не переоценивать.

## 8.3 Кросс-ссылки (полные доки — в других кластерах)

- **TwinMarket** (→ **5.5**): BDI-агенты финрынка (Xueqiu-профили/трейды, CSMAR SSE 50, Sina/10jqka/CNINFO), соцсеть по схожести трейдов с time decay, информационная пропагация (opinion leaders, echo chambers), эмерджентные явления (self-fulfilling prophecies, information cascades, bubbles/crashes), stylized facts (fat tails, volatility clustering, leverage effect, volume-return). Экономическая линза: рынок как многоагентная BDI-система; связка с 8.1 (econ↔political feedback) и science (market claims).
- **ABa-KiTo** (→ **4.7**): χ-функция/ISOKANN для kinetic pathways экономических переходов (green transition ABM) — применяется к траекториям наших econ-симуляций.
- **Operation-Molasses** (→ **2.5**): модуль `zencefil_disinfo_bot.py` (Short-and-Distort) — мост econ ↔ cognitive: манипуляция нарративом → обвал цены.

**Сводная интеграция экономического домена**: `apps/science` получает econ-контур: симуляционные движки (5.5 TwinMarket, 8.1 votran, 8.2 Entropic) + кинетика переходов (4.7) + манипуляционные сценарии (2.5); атомарные сущности — компании/рынки/агенты — трекаются через финансовые facets, политико-экономические предикторы и рыночные stylized facts; claims проходят ту же evidence-first цепочку платформы.

> **Кластер 8 завершён.** Экономический домен подключён к `apps/science`; интеграционная карта: `09-INTEGRATION-MATRIX.md`.
