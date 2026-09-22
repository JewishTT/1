# Cluster 3 — OSINT · CTI · Link Analysis

> Часть каталога `docs/architecture/donors/`. Governing spec: `specs/009-donor-full-catalogue/spec.md`.
>
> **Атомарная сущность** (человек/компания/домен/аккаунт) здесь получает **provenance-backed реляционное представление**: узел в link-analysis графе + рёбра-transform'ов + evidence-ссылки. Доноры кластера дают либо (a) трансформы обогащения, (b) движок реестров evidence/entity, (c) orchestration-паттерн multi-agent расследования, либо (d) telemetry/CTI-конвейер — всё закрепляется за общим пайплайном.

## Роль кластера в пайплайне

| Донор | Слой | Извлекаем | Механизм |
|---|---|---|---|
| erlik-graph | acquisition (enrichment), control-plane | entity/transform/graph core, 13 трансформов, FastAPI+MCP адаптеры, Neo4j | imported-module + mcp-pattern |
| SYNINT | acquisition, interpretation, admission | 46 collection-агентов, evidence/entity реестры, chain-of-custody, checkpoint/resume | imported-framework |
| intellyweave | interpretation, webapp | GLiNER entity-extraction, multi-agent debate, geo/network визуализация, hypothesis-режим | imported-module + UI-pattern |
| osia-framework | control-plane, science, webapp | desk-routing (Chief-of-Staff), RAG с boosts, Hermes corroboration (tier A/B/C), INTSUM/SITREP | service (isolated) |
| argus | acquisition (telemetry), projection, webapp | OCSF normalization, ML-ensemble anomaly, GNN lateral movement, SHAP, STIX 2.1 | imported-module + service |
| PIDSF | acquisition (brand-protection), spec-ops | domain-permutation + crt.sh + risk scoring + GoPhish (RoE-gate) + MITRE-маппинг | imported-service |

## 3.1 erlik-graph — OSINT link-analysis: one transform core, two front-ends

**Что это.** OSINT link-analysis граф: **Entities** (узлы) связываются **Transforms** (функции: сущность → связанные сущности) на интерактивном **Graph**. Ключевое — архитектура: transform-логика пишется **один раз** как Python-функции и выставляется через **два адаптера** поверх общего graph-store: (a) FastAPI + Cytoscape (визуальный, детерминированный, аудируемый), (b) MCP-сервер (LLM-агент вызывает те же трансформы автономно). Добавил трансформ — он появился в обоих.

**Фичи.** Entity/Transform/Graph модель с авто-дедупликацией узлов; 13 трансформов из коробки: DNS (A/MX/NS/TXT), reverse DNS, certificate-transparency субдомены (crt.sh), RDAP/WHOIS, Wayback Machine, IP-geolocation, HIBP breaches, Gravatar, Shodan services, username-enumeration по 10 платформам; визуальный граф (Cytoscape.js): клик по узлу → применимые трансформы → граф растёт; MCP-адаптер (каждый трансформ = tool: `domain_to_subdomains`, `username_to_profiles`, `get_graph`, …); pluggable storage: in-memory networkx или общий **Neo4j** (MCP и FastAPI читают/пишут один граф — агент обогащает, аналитик смотрит live в браузере).

**Hands-on.** `uvicorn erlik_graph.adapters.api_server:app --reload` (вариант A); `.mcp.json` → `python -m erlik_graph.adapters.mcp_server` (вариант B). Env: `SHODAN_API_KEY`, `HIBP_API_KEY`, Neo4j URI.

**Ограничения.** Ранняя версия (v0.1.0); трансформы синхронные; хранение — только граф узлов/рёбер (нет evidence-модели).

**Интеграция.**
- **Слой**: acquisition (pre-crawl enrichment), control-plane (MCP-поверхность), projection (link-analysis view).
- **Метод**: `imported-module` (трансформы как Python-пакет) + `mcp-server` (адаптер как паттерн).
- **Что даёт**: (1) детерминированные трансформы домен→субдомены/IP/сертификаты/упоминания — вход для Frontier: кандидатные URL ставятся один раз, с provenance (User Story 4); (2) паттерн «один core — два адаптера» — архитектурный шаблон нашей MCP-поверхности; (3) dedup-модель узлов — прототип дедупликации атомарных сущностей.
- **Как подключить**: (1) вынести `@transform`-функции в enrichment-worker (Python) позади acquisition; каждый результат → observation/candidate с source-транзитом; (2) FastAPI-адаптер → webapp «link analysis» панель (граф из projection, не из локального store); (3) MCP-адаптер → `control-plane` tool-gateway; (4) Neo4j-backend → опциональный shared-store между MCP и webapp в dev-режиме.
- **Приоритет**: **P1**. **Лицензия**: MIT → vendoring OK. **Риск**: лимиты внешних API (Shodan/HIBP) — квотирование на уровне acquisition.

## 3.2 SYNINT — local-first OSINT investigation framework (v5)

**Что это.** Локальный OSINT-фреймворк: staged-исполнение, pluggable collection-движки, централизованные **evidence и entity реестры**, resumable runs и structured forensic reporting. 46 default-агентов в каноническом порядке (`agents.AGENT_ORDER`) + опциональные (запускаются только по явному `--agents`).

**Фичи (v5).**
- **Archive collection**: bounded Common Crawl CDX lookup + single-record WARC range fetching; текст/сущности из архивов питают общий evidence pipeline.
- **Document intelligence**: read-only инспекция PDF/OOXML/OpenDocument/EPUB — хеши, embedded URLs, external relationships, document properties, provenance.
- **Relationship & timeline analysis**: provenance-backed co-occurrence edges (connected components, density, isolates, degree centrality); role-aware timestamps (source/collection/publication/archive/observation/creation/modification).
- **Identity review**: детерминированные identity-кандидаты с supporting evidence, contradictions, observation IDs и decision history; confirm/reject/reverse — только explicit human reviewer, без destructive merge.
- **Enhanced entity extraction** (opt-in): Bitcoin/Ethereum адреса, UUIDs, redacted SSN-like.
- **Experimental discovery**: камеры/ALPR/FLIR-метаданные через Shodan (bounded, private-address filtering, redirect denial, plate redaction).
- **Execution**: concurrent run-all (default) + staged pipeline `quick`/`standard`/`deep`.
- **Forensic hardening**: append-only **chain-of-custody ledger** (`chain_of_custody.jsonl`), per-agent checkpointing + resume (`synint_checkpoint.json`, `--resume-checkpoint`), strict normalized-result validation, SQLite store (`investigation.sqlite`).
- **Reporting**: `synint.log`, `synint_report.json`, `synint_report.html`, export bundle (`summary.json`, `report.md`), collection_artifacts/.
- **Runtime controls**: `--agent-timeout`, `--agent-retries`.

**Hands-on.** `python3 main.py https://target.tld`; `--list-agents`; `--agents WhoisAgent,DNSEnumAgent`; `--resume-checkpoint`.

**Ограничения.** Локальный single-host дизайн; агенты разнокачественные (фильтровать при импорте); лицензия в репо не заявлена.

**Интеграция.**
- **Слой**: acquisition (агенты-коллекторы), interpretation (co-occurrence/timeline), admission (identity review).
- **Метод**: `imported-framework` — агенты как worker-имплементации; orchestration-голова заменяется платформенным event-driven раннером.
- **Что даёт**: (1) 46 collection-агентов — бэклог acquisition (импорт поштучно, с дедупом против существующих); (2) **chain-of-custody ledger** — готовый паттерн append-only provenance → наша lineage-подсистема и webapp «lineage»; (3) identity-review workflow — модель admission/resolution человеческих решений; (4) checkpoint/resume — паттерн durable frontier/retry; (5) role-aware timestamps — обогащение временной модели Observation.
- **Как подключить**: (1) обернуть агенты в интерфейс платформенного worker'а (вход: seed-entity + budget; выход: normalized observations); (2) `synint_checkpoint.json` → платформенный checkpoint-store; (3) co-occurrence/timeline → `projection` (граф-деривации; centrality — facet атомарной сущности); (4) identity candidates → admission decision-очередь с audit trail.
- **Приоритет**: **P1**. **Лицензия**: NO-LICENSE-FILE → методы переносим; код — изоляция/clean-room до уточнения статуса; решение владельца. **Риск**: возраст зависимостей агентов — прогон на fixture-наборах перед включением.

## 3.3 intellyweave — AI-powered OSINT analysis platform (BSD-3)

**Что это.** OSINT-платформа: автоматически извлекает сущности из документов, визуализирует связи на картах и network-графах, применяет мультиагентные дебаты для well-reasoned ответов с цитатами. Слоган: «Upload documents. Ask questions. Get intelligence». Стек: Weaviate Elysia, **GLiNER** (zero-shot NER, 7 типов сущностей: persons, organizations, locations, dates, events, laws, cryptonyms; мультиязычно, без обучения), multi-provider LLM (OpenAI/Anthropic/Google/local).

**Фичи.** Entity extraction (примеры с 92% confidence + контекстный анализ); geospatial 3D-карты (интерактивные); network relationship analysis; archive discovery + hypothesis-driven investigation (Quartermaster + Case Officer роли); multi-agent reasoning для сложных вопросов; форматы PDF/DOCX/TXT/Markdown. Out of scope: real-time surveillance, автоматические решения без человека.

**Ограничения.** Beta; тяжёлый стек (Weaviate+LLM) — целиком в наш рантайм не тянем; часть функционала — поверх их платформы.

**Интеграция.**
- **Слой**: interpretation (NER/дебаты), webapp (geo/network UI-паттерны, hypothesis-workflow).
- **Метод**: `imported-module` (GLiNER-пайплайн) + `ui-component`/pattern (карты/граф/hypothesis-режим).
- **Что даёт**: (1) GLiNER как дополнительный NER-движок интерпретации (мультиязычный zero-shot — латает пробелы наших экстракторов); (2) «Quartermaster + Case Officer» — готовая UX-схема hypothesis-driven расследования для webapp (гипотеза → сбор → дебаты → вывод с цитатами); (3) multi-agent debate с citations — паттерн science «объясни вывод по evidence».
- **Как подключить**: (1) GLiNER в interpretation-экстрактор: вход — наши документы/тексты, выход — mentions с confidence и типом (маппинг 7 типов → наша онтология); (2) UI: geo-панель (наши geocoded entities), network-панель (projection-граф); (3) hypothesis-workflow → шаблон findings-страницы.
- **Приоритет**: **P1** (NER) / **P2** (UI-паттерны). **Лицензия**: BSD-3 → vendoring OK. **Риск**: деплой целиком тяжёл — брать модули; GLiNER-модели — кэшировать локально.

## 3.4 osia-framework — multi-agent intelligence agency

**Что это.** Event-driven multi-agent оркестрация OSINT: модель реального развед-агентства. **Chief of Staff** (Venice `venice-uncensored`) роутит запросы к специализированным AI-**Desks** (у каждого свой mandate, model, Qdrant collection): Geopolitical & Security, Cultural & Theological, Science & Technology, HUMINT, Finance & Economics, Cyber Intelligence & Warfare, Information & Psychological Warfare, Environment + **Watch Floor** (INTSUM-синтез).

**Ingress (3 канала).** Signal Gateway (оператив шлёт URL/query в Signal-группу → Redis `osia:task_queue`); RSS Ingress (поллер фидов: dedupe → clean → Gemini-суммари → **прямой upsert в Qdrant** `collection-directorate`, минуя оркестратор; сущности → `osia:research_queue`; дайджест в Redis `osia:rss:daily_digest` для 07:00 SITREP); Ingress API (authenticated HTTPS).

**Workers.** Research Worker (каждые 2 часа: multi-turn Venice-луп на тему → chunks/embeddings → в collection desk'а; payload: `entity_tags`, `reliability_tier: "B"`, `ingested_at_unix` для temporal decay; TTL-dedupe 72h). **Hermes Worker** (03:30 UTC daily: сканит points с tier ≠ "A"; two-phase corroboration на Hermes 4 70B (OpenRouter): Phase1 — поиск в KB + внешние источники (Tavily/OTX/ArXiv/Aleph), Phase2 — structured verdict после 3 раундов; verdicts **патчат payloads in-place** без re-embedding): `CORROBORATED` → upgrade (C/B→A); `CONTRADICTED` → downgrade + `contradiction_flag: true`; `UNVERIFIED` → stamp `corroboration_checked_at`, re-check через 14 дней.

**RAG.** Per-desk boosts (cyber: mitre-attack, cve-database, hackerone-reports, ttp-mappings, cti-reports; geo/humint: wikileaks-cables, epstein-files, collection-directorate, iran-israel-war-2026; watch floor: + osia_research_cache); query-expansion; real UTC timestamp в каждом сообщении.

**INTSUM/SITREP.** Watch Floor синтезирует INTSUM (структурированный брифинг: citations, reliability ratings, overall confidence) → записывает обратно в Qdrant (self-reinforcing KB) → PDF → Signal. Daily SITREP 07:00 UTC: Qdrant pre-seeding (4 standing queries: geopolitics/cyber/finance/tech) + 24h RSS digest → «ACCUMULATED OSIA INTELLIGENCE» блок.

**PHINT.** Медиа-перехват: social-видео → физический Android (Moto g06) через ADB записывает экран → Gemini Vision анализ; метаданные/комментарии — yt-dlp (ADB — fallback).

**Ограничения.** Требует внешних сервисов (Venice/OpenRouter/Qdrant/Redis/Signal/ADB); лицензия не заявлена; часть промптов — «uncensored»-модели.

**Интеграция.**
- **Слой**: `control-plane` (desk-routing), `science` (reliability tiers + corroboration = калибровка!), `acquisition` (RSS-коннектор), `webapp` (briefing).
- **Метод**: `service` (изолированный) + `imported-pattern` (desk-архитектура, verdict-механика).
- **Что даёт**: (1) **reliability-tiering + corroboration verdicts** — готовая механика evidence-калибровки (CORROBORATED/CONTRADICTED/UNVERIFIED как статусы наших claims); (2) INTSUM/SITREP — формат брифинг-документов; (3) desk-routing — паттерн доменной мульти-агентной оркестрации для control-plane.
- **Как подключить**: (1) tier/verdict-модель → admission/calibration (statuses + timestamps + contradiction_flag); (2) SITREP-сборка → report-генератор webapp; (3) RSS→Qdrant коннектор → паттерн для acquisition feeds; (4) абстрагировать LLM-провайдеров (не хардкодить Venice).
- **Приоритет**: **P1** (tier-механика) / P2 (сервис целиком). **Лицензия**: NO-LICENSE-FILE → модели/архитектуру переносим; код — сервис-изоляция. **Риск**: внешние зависимости — версионировать и оборачивать.

## 3.5 argus — open-source Cyber Threat Detection & Intelligence Platform (MIT)

**Что это.** Платформа детекции киберугроз и CTI: фьюзит мульти-источниковую телеметрию в единую онтологию, применяет реальные ML-модели (аномалии, lateral movement), визуализирует kill-chain в real-time Common Operating Picture. «Open-source альтернатива Palantir Gotham's cyber capabilities»: обученные модели, WebSocket-стриминг, graph-based attack path traversal на Neo4j.

**Фичи.**
- **Real-time detection**: гибридный пайплайн **LSTM-Autoencoder → Isolation Forest → XGBoost ensemble** (обучен на CICIDS2017 + UNSW-NB15 с cross-dataset валидацией); **GNN lateral movement** (LANL, PyTorch Geometric); **SHAP explainability** — каждый алерт с атрибуцией признаков (no black boxes).
- **NLP Threat Intel**: auto-IOC extraction (SecureBERT/DistilBERT: IPs, domains, hashes, CVE IDs, malware families); ATT&CK TTP mapping; **STIX 2.1** экспорт.
- **Command Center UI**: 3D threat globe (react-three-fiber, анимированные дуги), network topology (D3+Neo4j, multi-hop), ATT&CK matrix heatmap, kill-chain swimlane, dark HUD.
- **Data Fusion**: **OCSF**-нормализация сырой телеметрии; entity resolution (cross-source linking: «этот IP в netflow И endpoint-логах И фидах»); graph-correlation (indicators/assets/actors/campaigns).

**Ограничения.** Synthetic threat feed в комплекте; UI-слой к React-стеку.

**Интеграция.**
- **Слой**: acquisition (telemetry-нормализация), projection (граф), webapp (COP), spec-ops (defense validation).
- **Метод**: `imported-module` + `service`.
- **Что даёт**: (1) **OCSF-схема** — кандидат в стандарт нормализации нашей security-телеметрии; (2) SHAP-объяснения алертов — паттерн explainability-claims; (3) STIX 2.1 — канал обмена CTI; (4) entity resolution cross-source — метод слияния записей об одной сущности (наш admission); (5) UI-паттерны (см. 6.3).
- **Как подключить**: (1) OCSF-нормализатор → schema-слой; (2) ML-пайплайн → spec-ops detection-lab на фикстурах и наших lab-логах; (3) IOC/NER-модуль → interpretation (CTI-парсинг); (4) UI — задачи webapp.
- **Приоритет**: **P1** (OCSF+NLP+UI) / P2 (ML-сервис). **Лицензия**: MIT → vendoring OK. **Риск**: synthetic-фиды заменить реальными lab-данными.

## 3.6 PIDSF — Phishing Infrastructure Detection & Simulation Framework

**Что это.** Компактный санкционированный red-team-инструмент из связанных стадий с общим reporting-слоем: (1) **Detection** — dnstwist-style генерация доменных перестановок, кросс-референс с certificate-transparency (crt.sh), risk scoring; (2) **Simulation** — thin safety-gated wrapper над self-hosted **GoPhish** для одной авторизованной кампании; (3) **Reporting** — метрики, MITRE ATT&CK mapping, экспорт CSV / PDF / **ATT&CK Navigator layer**. Дополнительно: **Recon/OSINT** (subdomain attack-surface mapping via crt.sh) и **Monitoring** (re-runnable scan-and-diff — cron/systemd).

**Safety — в коде, не в UI.** `simulation.launch_campaign()` кидает `RoEError` и не вызывает GoPhish без `roe_confirmed` (только через явный sign-off endpoint); `create_landing_page()` хардкодит `capture_passwords=False` (пароли никогда не сохраняются; дефолтный `DEFAULT_DISCLOSURE_HTML` сразу раскрывает тест); `validate_target_roster()` принимает только явный supervisor-approved список; detection/recon — только публичные источники о своём тест-бренде.

**Hands-on.** `pip install -r requirements.txt` → `python run.py` → `http://127.0.0.1:5000` (сид демо-данных, ноль конфигурации, ноль внешних вызовов; live — чекбокс «Query live sources»); GoPhish — env `PIDSF_GOPHISH_URL` / `PIDSF_GOPHISH_API_KEY`. Layout: `app/{config,models,routes,modules/{detection,osint,simulation,reporting,monitoring}}`, Jinja2-шаблоны, SOC-console CSS, `tests/test_smoke.py`.

**Интеграция.**
- **Слой**: acquisition (brand-protection: lookalike-домены как кандидаты-сущности) + spec-ops (phishing с RoE-гейтом) + webapp (SOC-скоринг UI).
- **Метод**: `imported-service` (Flask) или перенос модулей detection/reporting.
- **Что даёт**: (1) **RoE-гейт как паттерн авторизации** — переносим в наши spec-ops: ни один боевой шаг без подтверждённого ROE; (2) domain-permutation+crt.sh scoring — модуль brand-protection для OSINT-core (находки → candidates/claims с evidence); (3) ATT&CK Navigator-экспорт — формат совместимости.
- **Как подключить**: (1) detection/reporting-модули → acquisition-обогащение и claims; (2) RoE-гейт → в campaign-схему spec-ops (обязательное поле + sign-off endpoint); (3) monitoring diff-pass → периодическая feedback-задача.
- **Приоритет**: **P1** (RoE-паттерн + domain-detection) / P2 (сервис). **Лицензия**: NO-LICENSE-FILE → методы переносим, код — изоляция. **Риск**: crt.sh rate limits; GoPhish — только авторизованные тренинги.

> **Кластер 3 завершён (6/6).** Интеграционная карта: `09-INTEGRATION-MATRIX.md`.
