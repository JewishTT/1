# Cluster 9 — Integration Matrix (все доноры × слои × механизмы)

> Часть каталога `docs/architecture/donors/`. Governing specs: `specs/009-donor-full-catalogue/spec.md` (кластеры 1–8) + `specs/010-zero-layer-contact-harvesting/spec.md` (кластер 0).
>
> Сквозная карта: каждый донор → кластер → язык → лицензия → приоритет → механизм интеграции → целевой слой → ключевой деливерабл.
> **Приоритеты**: P1 — интегрируем в первую волну (код/сервис/модель в живом consumer); P2 — вторая волна (методы/паттерны/сервисы); P3 — pattern/reference, без вендоринга.
> **Механизмы** (rev.2, код копировать можно): `imported-module` · `imported-crate` · `imported-framework` · `imported-service` · `service` (изолированный) · `mcp-server` · `data-source` · `ml-model` · `dataset` · `knowledge-base` · `ui-component` · `pattern` · `reference` · `lab-fixture` · `toolkit` · `vendored-binary`.
> Платформенные слои: `zero` (type-detect→harvest→resolution→enrichment/feedback) → `acquisition` → `interpretation` → `admission` → `projection` → `science` → `feedback` → `webapp` → `control-plane` (+ spec-ops lab-контур, + экономический домен в `science`).

## Кластер 0 — Zero-Layer (52 новых донора; любой вход → контакты, NO-AI)

| Донор | Lang | Лицензия | Pri | Механизм | Слой | Деливерабл |
|---|---|---|---|---|---|---|
| thecrowler | Go | Apache-2.0 | P1 | service | zero-L1 (web) | event-driven краулер, real browsers, YAML rulesets |
| spiderfoot | Python | MIT | P1 | vendored-module | zero-L1 | 200+ модулей обогащения от seed |
| secureflow-intel | Python | MIT | P2 | reference | zero-L1 | SpiderFoot-форк: расширенные фиды |
| estorides | Python | AGPL-3.0 | P1 | isolated-service | zero-L1/L3 | OSINT-агрегатор: enricher'ы/краулеры (Palantir-inspired) |
| lazyaddon | Python | GPL-3.0 | P2 | isolated-service | deploy | декларативный менеджер инструментов |
| OnionSearch | Python | GPL-3.0 | P1 | isolated-service | zero-L1 (Tor) | параллельный onion-поиск через Tor SOCKS5 |
| trident | Go | GPL-3.0 | P1 | vendored-binary | zero-L1 (net) | DNS/ASN/CT/PGP, один бинарь, 0 ключей |
| seekr | Go | GPL-3.0 | P2 | isolated-service | zero-L1 | BadgerDB-воркстейшн, плагины, web UI |
| osint-terminal | Python | MIT | P1 | vendored-module | zero-L1 | 438 keyless-инструментов (stdlib+requests) |
| argus-cotcollective | Python | MIT | P1 | vendored-module | zero-L1 | 13 модулей, 0 API-ключей, локальный Ollama |
| osint-web-mcp | TS | MIT | P1 | vendored-module | control-plane | stealth-браузер (Playwright+Stealth) MCP-сервер |
| Aperture-OSINT-Workbench | JS | MIT | P2 | reference | zero-L1 | local-first browser workbench, без телеметрии |
| phantomsignal | Python | NOASSERTION | P1 | methods+pattern | zero-L1 egress | stealth egress (proxy pool, JA3/JA4), 54+ sources |
| The-3rd-Eye | Python | MIT | P1 | vendored-module | zero-L1/L3 | LangGraph OSINT: email pattern detection, SMTP-верификация |
| osint-search-tool | JS | NO-LICENSE | P2 | ui-pattern | zero-L1 UI | 450+ инструментов в 16 категориях (Populate-All UX) |
| TraceMatrix | Python | NO-LICENSE | P2 | methods | zero-L2 | orchestrate endpoint + entity extraction/enrichment |
| Hostile-Command-Suite | Python | NOASSERTION | P2 | pattern | zero-L1 | LLM-агент выбирает инструмент по типу данных |
| TheBigBrother | Python | MIT | P2 | methods | zero-L1 | 473+ платформ, quad-vector viz, dorking |
| maigret | Python | MIT | P1 | vendored-module | zero-L1 | досье из 3000+ сайтов по username |
| sherlock | Python | MIT | P1 | vendored-module | zero-L1 | enumeration 400+ платформ |
| holehe | Python | GPL-3.0 | P1 | isolated-service | zero-L1 | авторизация-чек 250+ сервисов по email |
| user-scanner | Python | MIT | P1 | vendored-module | zero-L1 breach | Email+Username intel + Hudson Rock |
| mosint | Go | MIT | P1 | vendored-binary | zero-L1 breach | email breach/social/domains |
| WhoCord | Python | NO-LICENSE | P1 | methods | zero-L1 | auto-detect (8 модулей) — референс type-detector |
| OsintEye | Python | MIT | P2 | vendored-module | zero-L1 | GitHub/social/subdomain/email |
| Profil3r | Python | MIT | P2 | vendored-module | zero-L1 | name-based OSINT |

### 0.B Git-email / Domain / Phone / Social / Spec-ops-bridge

| Донор | Lang | Лицензия | Pri | Механизм | Слой | Деливерабл |
|---|---|---|---|---|---|---|
| gitsnitch | Python | MIT | P1 | vendored-module | zero-L1 | username → commit email |
| gitrecon | Python | NOASSERTION | P2 | methods | zero-L1 | GitHub+GitLab exposed email/names |
| GitFive | Python | MPL-2.0 | P1 | vendored-module | zero-L1 | email→GitHub account, Metamon-верификация |
| github-email-extractor | Python | MIT | P1 | vendored-module | zero-L1 | email из repos/commits/events |
| EmailFinder | Python | MIT | P2 | vendored-module | zero-L1 | commit-email по author |
| gh-mailto | Go | Apache-2.0 | P1 | vendored-binary | zero-L1 | org-users → email discovery |
| theHarvester | Python | GPL-2.0 | P1 | isolated-service | zero-L1 | email/subdomain/host из 200+ источников |
| Sublist3r | Python | GPL-2.0 | P2 | isolated-service | zero-L1 | subdomain enumeration |
| Mail-Hunter | Python | MIT | P1 | vendored-module | zero-L1 | professional email по домену |
| coldreach | Python | MIT | P1 | vendored-module | zero-L1 | email finder + DNS/SMTP верификация |
| Email-Permutator | Python | GPL-3.0 | P1 | isolated-service | zero-L1 | name→email перестановки + верификация |
| MottaHunter | Python | NOASSERTION | P2 | methods | zero-L1 | smart permutations, catch-all detection |
| EmailHarvester | Python | GPL-3.0 | P2 | isolated-service | zero-L1 | email-харвест из поисковиков |
| Gmail_Checker | Python | NO-LICENSE | P2 | methods | zero-L1 | Gmail-перестановки + SMTP-чек |
| phoneinfoga | Go | GPL-3.0 | P1 | isolated-service | zero-L1 | номер→carrier/region + OSINT-дорки |
| phone-osint-framework | Python | NOASSERTION | P1 | methods | zero-L1 | breach-first архитектура (DeHashed→LeakCheck→HIBP→social) |
| Phunter | Python | GPL-3.0 | P2 | isolated-service | zero-L1 | номер→аккаунты/утечки/следы |
| SearchPhone | Python | MIT | P1 | vendored-module | zero-L1 | multi-API search + Hudson Rock |
| ignorant | Python | GPL-3.0 | P1 | isolated-service | zero-L1 | WhatsApp/TG/Signal/Snapchat/IG enumeration |
| DIGI-NETRA | Python | NO-LICENSE | P2 | methods | zero-L1 | телефон/username/IP/email check |
| X-osint | Python | GPL-3.0 | P2 | isolated-service | zero-L1 | phone→email, VIN, reverse, subdomains |
| email2phonenumber | Python | MIT | P1 | vendored-module | zero-L1 (RoE-gate!) | email→phone через password-reset |
| EmailExtractWithProxyApp | Python | NO-LICENSE | P2 | methods | zero-L1 | bulk email/phone/WA/TG из соцсетей |
| mysterious-cyclopus | Python | NO-LICENSE | P2 | isolated-service | spec-ops lab | multi-platform C2 (controlled pentest) |
| CyberStrikeAI | Python | Apache-2.0 | P1 | vendored-module | spec-ops lab | AI-native offensive security |
| Flippy | Python | GPL-3.0 | P2 | isolated-service | spec-ops lab | NFC/BLE/IR research, mobile emulation |
| postexploitation-toolbox-android | Java | GPL-3.0 | P2 | knowledge+lab | spec-ops KB | Android post-exploitation (uid 1000) |

### 0.C Синтез zero-layer (методы, не репо)
| Компонент | База | Pri | Механизм | Слой | Деливерабл |
|---|---|---|---|---|---|
| Type-Detector | regex+validators+heuristics (WhoCord-референс) | P0 | imported-module | zero-L1 | 8 типов, deterministic confidence |
| Resolution | Fellegi-Sunter/Splink + Louvain/Neo4j GDS + Soundex/Metaphone/p-sig | P0 | imported-module | zero-L2 | match_weight, community_id, баркоды |
| Enrichment | spaCy NER (8 типов) + 50+ enricher'ов | P0 | imported-module | zero-L3 | enrichers + extraction |
| Feedback | Kafka `zero_layer.feedback_seeds` → L1 re-harvest | P0 | service | L3→L1 | auto re-harvest waves |
| Frontend | §0.13 workbench (10 компонентов, 3 модуля) | P0 | ui-component | webapp | D3-граф, inspector, matrix, KPI |



## Кластер 1 — Cognitive Warfare (12)

| Донор | Lang | Лицензия | Pri | Механизм | Слой | Деливерабл |
|---|---|---|---|---|---|---|
| f.txt | doc | CC BY 4.0 | P2 | knowledge | spec-ops/science | OODA-фрейм, метрики superiority, кейс Norland |
| дополнительно.txt | doc | внешний сервис | P1/P2 | mcp-server + reference-math | acquisition/science/spec-ops | 8 моделей: SIR-Hawkes, DeGroot, Stackelberg, Potts, HK, greedy, ATE |
| Cognitive-Weaponization-Matrix | doc | без файла | P2 | knowledge-base | interpretation/spec-ops | 5GW-таксономия техник + bias-каталог |
| CognitiveAttack | Python | MIT | P1 | imported-module | spec-ops/interpretation | 154-bias redteam-движок, ASR-методология |
| seithar-research | doc/app | CC BY-NC | P3 | knowledge-only | KB | SCT-таксономия, кейсы, обучение |
| NarrativeDiffusion | Python | без файла | P2 | imported-module | interpretation/science | adoption-модель αW+βI+γA |
| io-coordinated-replies | Python | без файла | P1 | ml-model | interpretation/admission | детекторы reply-атак (AUC 0.88/0.97) |
| IO-detecting-and-anticipating | Python | MIT | P1 | imported-module | projection/science | temporal motifs, GNN/TGNN link-prediction |
| DIMA-OntoToolkit | Python | Apache-2.0 | P1 | imported-module | interpretation | arguments/agents/quotes → OWL/SPARQL bias-detection |
| Lying_with_Truth | Python | без файла | P1 | dataset + imported-module | spec-ops/science | CoPHEME + montage attack plans (ASR 81.7%) |
| EvoCorps | Python | MIT | P1 | imported-framework | spec-ops/science | деполяризация: роли Analyst→Amplifier, evolution-loop |
| cognitive_phase_transitions | Python | MIT | P1 | imported-module | science | Kuramoto+Hebbian, MPC/order parameter, r_c=1.534 |

## Кластер 2 — Spec-Ops / Pentest / Emulation (14)

| Донор | Lang | Лицензия | Pri | Механизм | Слой | Деливерабл |
|---|---|---|---|---|---|---|
| caldera | Python | Apache-2.0 | P1 | service (lab) | spec-ops core | C2 + planners + agents + REST/UI, ATT&CK-оркестрация |
| ael | md/YAML | Apache-2.0 (CT0005) | P1 | data-source | spec-ops scenarios | ATT&CK Evaluations emulation plans → scenario DSL |
| adversary_emulation_library | md/YAML | Apache-2.0 | P1 | data-source + module | spec-ops | full+micro plans → attack-atoms registry |
| APT-SF | docs | без файла | P2 | imported-pattern | spec-ops planning | Diamond/TIBER-EU/UKC, ASM, output-схема отчётов |
| Operation-Molasses | md+scripts | MIT | P1/P2 | knowledge + toolkit | spec-ops KB/tools | 33 фазы, IaC, recon/weaponizer/sender |
| PhantomStrike-AI | Python | MIT | P1/P2 | imported-service | spec-ops pentest | 6-фазный скан, AI-scoring, safe-exploits, PDF |
| PhishSlayer | TS/Node | GPLv3 | P1 | service | spec-ops SAT | CMDB+MCP+LLM phishing sim, HITL, KPI |
| BluePhish | Python | без файла | P2 | imported-service | spec-ops SAT | локальная лаборатория, privacy-by-design, метрики |
| fiercephish | Python | GPLv3 | P3 | reference | spec-ops phishing | campaign data-model, sending-практики |
| SPEAR | Python | без файла | P1/P2 | imported-module | spec-ops email + detection | LIME-adversarial детекторы, email-модели |
| sticks | Python/Docker | без файла | P1 | module + lab-fixture | spec-ops | STIX sufficiency metric + Caldera-lab |
| TripleFantasy | C++ | GPLv3 | P3 | pattern-only | spec-ops research | beacon/OPSEC-паттерны, anti-analysis каталог |
| AzureAD-Attack-Defense | docs | без файла | P2 | knowledge → rules | spec-ops identity | Entra playbook: spray/AiTM/PRT/EIDSCA |
| Labyrinth | Go | AGPL-3.0 | P1/P2 | service + pattern | spec-ops deception | portal-trap против offensive AI-агентов; TUI |

## Кластер 3 — OSINT / CTI / Link Analysis (6)

| Донор | Lang | Лицензия | Pri | Механизм | Слой | Деливерабл |
|---|---|---|---|---|---|---|
| erlik-graph | Python | MIT | P1 | imported-module + mcp-pattern | acquisition/control-plane | 13 трансформов (DNS/crt.sh/RDAP/Wayback/Shodan/HIBP/…), 2 адаптера на одном core |
| SYNINT | Python | без файла | P1 | imported-framework | acquisition/interpretation/admission | 46 агентов, chain-of-custody ledger, identity-review, checkpoint/resume |
| intellyweave | Python/TS | BSD-3 | P1/P2 | imported-module + ui-component | interpretation/webapp | GLiNER NER (7 типов), geo/network UI, hypothesis-workflow |
| osia-framework | Python | без файла | P1/P2 | service + imported-pattern | control-plane/science/acquisition | reliability-tiering A/B/C + Hermes-corroboration, INTSUM/SITREP, desk-routing |
| argus | Python/React | MIT | P1/P2 | imported-module + service | acquisition/projection/webapp | OCSF, LSTM-AE+IF+XGBoost, SHAP-алерты, STIX 2.1, COP UI |
| PIDSF | Python | без файла | P1/P2 | imported-service | acquisition/spec-ops/webapp | lookalike-домены + crt.sh scoring, RoE-гейт, Navigator-экспорт |

## Кластер 4 — Networks / TDA (11)

| Донор | Lang | Лицензия | Pri | Механизм | Слой | Деливерабл |
|---|---|---|---|---|---|---|
| BeliefLandscapeFramework | Python | MIT | P1 | imported-framework | science | 11 стадий: beliefs→VAE(8D)→neural ODE→attractors/saddles→forecast |
| persistence-agent | Rust | custom permissive | P1 | imported-crate | science | VR→barcodes→features (stability/adaptability/depth)→archetype |
| witness-topology | Rust | без файла | P1 | imported-crate | science | witness complexes, mapper graphs, bottleneck/Wasserstein, stability bounds |
| PHoDMSs | Python | MIT | P1 | imported-module | science | spatiotemporal Betti-0, rank invariants, erosion distance |
| HypergraphX | Python | BSD-3 | P1 | imported-module | projection/science | hypergraph-модель групповых взаимодействий, contagion/sync |
| hive-mind-gnca | Python | MIT | P2 | imported-module | science/spec-ops | GNCA fast/slow weights, SGCA, Λ>η collapse-порог |
| ABa-KiTo | Python/Julia | без файла | P1 | imported-module | science | χ-function (ISOKANN), кластеры состояний, граф kinetic pathways |
| ABM_polarisation | Julia | без файла | P2 | imported-module | science | Schelling-поляризация: фикстура + метрики (99_functions.jl) |
| Raphtory | Rust | GPLv3 | P1/P2 | service/reference | projection | time-travel граф, temporal motifs, multilayer, dynamic scoring |
| lau-network-science | Rust | MIT | P1/P2 | imported-crate | projection/science | центральности/Louvain/SIR/перколяция/power-law/AgentNetwork |
| adversarygraph | Python/TS | personal-use | P2 | service + reference | spec-ops/projection/webapp | Evidence-to-Detection Graph, hybrid RAG (pgvector), Threat Radar |

## Кластер 5 — Social Simulations (9)

| Донор | Lang | Лицензия | Pri | Механизм | Слой | Деливерабл |
|---|---|---|---|---|---|---|
| YuLan-OneSim | Python | Apache-2.0 | P1 | imported-framework | science | 100k-агентов LLM-симулятор, code-free сценарии, AI-researcher цикл |
| MicroWorld | Python | AGPL-3.0 | P1 | service + pattern | science/webapp | event→graph→sim, PPR-влияние, inspectable-run UX |
| posim | Python | MIT | P1 | imported-framework | science/spec-ops | Social-BDI, Hawkes-тайминг, three-tier валидация |
| silisocs | Python | MIT | P1/P2 | imported-framework | science/spec-ops | EASE-YAML конфиги, evaluation probes, Mastodon-полигон |
| TwinMarket | Python | без файла (orig. Apache-2.0) | P1 | imported-framework | science (эконом.) | BDI-финрынок, соцсеть по трейдам, bubbles/crashes, stylized facts |
| social-oscillation-model | Python | MIT | P1 | imported-module | science | kernel-агенты, regime shift, order parameter/энергия |
| SNS-Analysis (Topology of Trust) | Python | без файла | P1 | imported-module | science/webapp | OCEAN-drift, edge_trust, GCN-DQN, эхо-камеры/defection cascades |
| DualMind | Python | Apache-2.0 | P1 | imported-framework | science/spec-ops | emotion↔cognition каскады, dataset 15 PR-кризисов, rehearsal UI |
| votranhabysscoremicro | Python | Apache-2.0 | P1/P2 | imported-module | science (эконом.)/spec-ops | 31 слой + PoliticalCore, trust-GCN, Q-learning политик |

## Кластер 6 — UI / Dashboards (компоненты + synthesis)

| Донор | Lang | Лицензия | Pri | Механизм | Слой | Деливерабл |
|---|---|---|---|---|---|---|
| CogniX-Surface | Python/JS | без файла | P1/P2 | ui-component + service | webapp/interpretation | SSE-прогресс, KPI-timeline, presets, explainable-скоринг |
| LeakHunter | HTML/Java | без файла | P2 | ui-component + clean-room | webapp/spec-ops | pattern-detection паролей, crack-time, single-panel |
| SNS-Analysis dashboard | Python | без файла | P2 | pattern | webapp (science) | Streamlit live-sim control, network-viz |
| ARGUS COP UI | React | MIT | P1 | pattern + ui-component | webapp (spec-ops) | 3D globe, ATT&CK heatmap, kill-chain swimlane |
| Magma (Caldera UI) | Vue | Apache-2.0 | P1 | pattern | webapp (spec-ops) | operation matrix, ability graph |
| Labyrinth UI | Go/TUI+web | AGPL-3.0 | P2 | pattern | webapp | TUI live-log, deception dashboard |
| MicroWorld UX | Python | AGPL-3.0 | P1 | pattern | webapp (science) | inspectable run-inspector |
| OSIA briefing UX | Python | без файла | P1 | pattern | webapp | INTSUM/SITREP briefing |
| EvoCorps UI | Python | MIT | P2 | pattern | webapp | intervention previews, sentiment-траектории |

## Кластер 7 — Infra Data Stack

| Донор | Lang | Лицензия | Pri | Механизм | Слой | Деливерабл |
|---|---|---|---|---|---|---|
| сбор данных.txt | doc | n/a | P1 | reference-blueprint | deploy/projection | Redpanda→Flink→Fluss→Iceberg; Quickwit; DataHub; Dagster |
| f.txt | doc | CC BY 4.0 | — | cross-ref → 1.1 | spec-ops/science | OODA-фрейм |
| дополнительно.txt | doc | внешний сервис | — | cross-ref → 1.2 | acquisition/science | 8 мат-моделей |

## Кластер 8 — Экономика

| Донор | Lang | Лицензия | Pri | Механизм | Слой | Деливерабл |
|---|---|---|---|---|---|---|
| votranhabysscoremicro | Python | Apache-2.0 | P1/P2 | imported-module | science(econ)/spec-ops | 31 слой + PoliticalCore, trust-GCN, Q-policies |
| Entropic-Dynamics | Python | без файла | P1 | imported-module | science(econ) | ABM эндогенного кризиса (3 класса агентов) |
| TwinMarket (econ-lens) | — | → 5.5 | P1 | imported-framework | science(econ) | BDI-рынок, stylized facts |
| ABa-KiTo (econ-lens) | — | → 4.7 | P1 | imported-module | science(econ) | kinetic pathways переходов |
| Operation-Molasses (disinfo) | — | → 2.5 | P1 | toolkit | spec-ops | Short-and-Distort модель |

## Сводка «волна 1» (P1-единицы по доменам)

| Домен | P1-единицы |
|---|---|
| Spec-ops | caldera, ael, adversary_emulation_library, Operation-Molasses, PhishSlayer, SPEAR (detection-side), sticks, Labyrinth, PhantomStrike-AI (scoring) |
| OSINT-core | erlik-graph, SYNINT, intellyweave, osia-framework, argus, PIDSF |
| Cognitive | CognitiveAttack, io-coordinated-replies, IO-detecting-and-anticipating, DIMA-OntoToolkit, Lying_with_Truth, EvoCorps, cognitive_phase_transitions, доп.txt-модели |
| TDA / Graph | BeliefLandscapeFramework, persistence-agent, witness-topology, PHoDMSs, HypergraphX, ABa-KiTo, lau-network-science, Raphtory (паттерны) |
| Sims | YuLan-OneSim, MicroWorld, posim, silisocs, TwinMarket, social-oscillation-model, Topology-of-Trust, DualMind |
| UI | CogniX-паттерны, ARGUS COP, Magma, MicroWorld-inspector, OSIA-briefing, styles-реестр |
| Infra / Econ | сбор данных.txt (blueprint), Entropic-Dynamics, votranhabysscoremicro (слои), ABa-KiTo (econ-lens) |

## Сводка механизмов (rev.2)

| Механизм | Доноры (категории) |
|---|---|
| vendoring (MIT/BSD/Apache-2.0) | caldera, ael, AEL-lib, PhantomStrike, PhishSlayer*, SPEAR*, erlik, intellyweave, argus, HGX, BLF, persistence*, lau, YuLan, silisocs, posim, TwinMarket**, DualMind, votran, social-oscillation, EvoCorps, phase_transitions, PHoDMSs, IO-detecting, CognitiveAttack, DIMA, Operation-Molasses, hive-mind |
| изолированный сервис (GPL/AGPL/personal-use) | fiercephish, PhishSlayer, Raphtory, Labyrinth, MicroWorld, TripleFantasy, adversarygraph, osia**, SYNINT** |
| clean-room методов (нет лицензии) | SYNINT, PIDSF, sticks, topology, Lying_with_Truth, NarrativeDiffusion, io-coordinated, CogniX, LeakHunter, BluePhish, APT-SF, ABa-KiTo, ABM_polarisation, Topology-of-Trust, Entropic, SNS-Analysis, SPEAR |
| knowledge / dataset / reference | f.txt, доп.txt, CWM, seithar, AzureAD, APT-SF (схемы), сбор данных.txt, KB-контуры |

> \* SPEAR/PhishSlayer — публичная часть/сервис; \*\* уточнение лицензии при вендоринге (см. кластерные файлы).

## Выполнено — первый волн интеграции доноров (T053–T072, T090)

> Запись на 2026-09-22. Проверка: `python -m pytest apps/science -q` (157 passed), `python -m pytest apps/projection -q` (53 passed). Лицензии: `lau` MIT, `persistence-agent` MIT/Apache-2.0, `BLF` MIT, `hypergraphx` BSD-3, `PHoDMSs` MIT, `hive-mind-gnca` MIT, `cognitive_phase_transitions` MIT, `votran` Apache-2.0; Raphtory GPLv3 и ABa-KiTo/ABM_polarisation/Entropic без лицензии → только методы (clean-room), помечено в докстрингах.

| Задача | Донор | Механизм | Модуль | Guarding-тест |
|---|---|---|---|---|
| T054 | persistence-agent | clean-room (MIT/Apache-2.0) | `apps/science/tda/persistence.py` | `apps/science/tests/unit/test_tda.py` |
| T056 | PHoDMSs | imported-module (MIT) | `apps/science/tda/phodms.py` | `apps/science/tests/unit/test_tda.py` |
| T053 | BLF forecast | methods (MIT) | `apps/science/beliefs/landscape.py` | `apps/science/tests/unit/test_landscape.py` |
| T057 | ABa-KiTo | clean-room (без лицензии) | `apps/science/kinetics/pathways.py` | `apps/science/tests/unit/test_kinetics.py` |
| T059 | lau-network-science | methods (MIT) | `apps/projection/metrics/network_measures.py`, `community.py` | `apps/projection/tests/test_metrics.py` |
| T058 | hypergraphx | methods (BSD-3) | `apps/projection/metrics/hypergraph_metrics.py` | `apps/projection/tests/test_metrics.py` |
| T060 | Raphtory | own-module (GPLv3 → решение: без вендоринга) | `apps/projection/metrics/temporal_paths.py` | `apps/projection/tests/test_metrics.py` |
| T070 | Entropic-Dynamics | clean-room (без лицензии) | `apps/science/econ/crisis_abm.py` | `apps/science/tests/unit/test_econ.py` |
| T090 | votran | imported-module (Apache-2.0) | `apps/science/econ/operators.py` | `apps/science/tests/unit/test_econ.py` |
| T069 | ABM_polarisation | clean-room (без лицензии) | `apps/science/fixtures/schelling.py` | `apps/science/tests/unit/test_schelling.py` |
| T072 | hive-mind-gnca | imported-module (MIT) | `apps/science/sims/gnca.py` | `apps/science/tests/unit/test_gnca.py` |
| T071 | cognitive_phase_transitions | imported-module (MIT) | `apps/science/operators/phase.py` | `apps/science/tests/unit/test_phase.py` |

**Отклонения таргетов** (задокументированы в `tasks.md`): T053 `forecast/` → `beliefs/landscape.py`; T058 `projection/hypergraph/` → `projection/metrics/hypergraph_metrics.py`; T060 `deploy/pilots/raphtory/` → `temporal_paths.py` (GPL-гейт); T069 `fixtures/schelling/` → `fixtures/schelling.py`; T070 `fixtures/econ_crisis/` → `econ/crisis_abm.py` (консолидация через T090); T072 `backlog/gnca/` → `sims/gnca.py`.

**Новые пакеты** добавлены в hatch-wheel: `apps/science/pyproject.toml` (+ `tda`, `kinetics`, `beliefs`, `econ`, `fixtures`, `sims`, `operators`), `apps/projection/pyproject.toml` (+ `metrics`).

## Верификация

- **SC-001/SC-002** (доки + integration entry на каждого донора) — ✅ кластеры `01–08` (12+14+6+11+9+4+1+2 полных + cross-refs и synthesis) **+ кластер 0** (52 клонированных донора zero-layer, §0.12 inventory в `10-ZERO-LAYER.md`).
- **SC-003** (матрица: priority + license + mechanism) — ✅ этот файл (кластеры 0–8).
- **SC-004** (≥1 задача на донора) — ✅ `specs/009-donor-full-catalogue/tasks.md` (T001–T106) + `specs/010-zero-layer-contact-harvesting/tasks.md` (T100–T175).
- **SC-005** (standalone readability) — ✅ `00-INDEX.md` → кластеры → матрица → tasks.
- **SC-011** (spec 010): 52/52 клонировано в `donors/` (106 папок всего) — ✅ проверено по рабочему дереву 2026-09-21; 404-URL задокументированы с заменами (sherlock→sherlock-project, user-scanner→kaifcodec, Profil3r→Greyjedix, email2phonenumber→martinvigo, gh-mailto→codeGROOVE-dev, erfert→grisuno/estorides+lazyaddon).
- **SC-012/SC-013** (spec 010): §0.11 Sources-From-Everywhere + §0.13 Frontend-дизайн — ✅ в `10-ZERO-LAYER.md`.
- **Guarding tests**: каждый вендоренный модуль получает тест в `apps/*/tests/` с фикстурой из донора и attribution-заголовком (T001, T100, T161).
- **Lineage**: webapp-панели, использующие донорскую логику, показывают donor + license + adapted file (US1).

> Программа выполнения: `specs/009-donor-full-catalogue/plan.md` + `tasks.md`; zero-layer: `specs/010-zero-layer-contact-harvesting/{plan,tasks}.md`. Настоящий каталог — источник истины по «что/куда/зачем» для каждой единицы.