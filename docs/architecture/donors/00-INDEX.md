# COGNITIVE — Donor Architecture Catalogue (Full)

Master index of every project in `donors/`, grouped into 8 thematic clusters + zero-layer.
Each cluster file documents **every project** in maximal detail + gives a concrete **integration entry** (where, how, why, priority, license, risk).

> See `specs/009-donor-full-catalogue/spec.md` (clusters 1–8) and `specs/010-zero-layer-contact-harvesting/spec.md` (cluster 0) for the governing OpenSpec feature specs.
> **Статус: full catalogue complete** — кластеры `00–08` + `09-INTEGRATION-MATRIX.md` + `10-ZERO-LAYER.md` + `specs/009/plan.md` + `specs/009/tasks.md` + `specs/010/{spec,plan,tasks}.md`.
> Платформенная архитектура: `apps/acquisition → apps/interpretation → apps/admission → apps/projection → apps/science → apps/feedback → apps/webapp`, event-driven через Kafka, evidence-first (immutable Observation в S3, rebuildable projections). Zero-layer (`apps/zero/`) — фундамент под acquisition.

## Platform domain map (where clusters plug in)

```
┌─────────────────────────────────────────────────────────────────────┐
│  ZERO-LAYER (apps/zero/): любой вход → контакты (NO-AI)              │
│  type-detect → harvest(52 donors) → Fellegi-Sunter → spaCy+feedback  │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ observations
┌──────────────────────────▼──────────────────────────────────────────┐
│  DOMEN 1: OSINT CORE    (apps: acquisition→interpretation→admission→projection)  │
│  Domen 2: Отдел спецопераций (redteam/pentest/cognitive-redteam + isolated labs)  │
│  Domen 3: Экономика      (apps/science economic-dynamics)                        │
└──────────────────────────┬──────────────────────────────────────────────────────┘
                           │ event stream (Kafka)
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  apps/science  — probabilistic claims, causal/temporal/structure/TDA │
│  apps/feedback — utility scorer, acquisition stopping policy         │
│  apps/webapp   — React/TS SPA: 3 модуля (OSINT/Экономика/Spec-Ops)   │
└─────────────────────────────────────────────────────────────────────┘
```

## Cluster map

| File | Cluster | N projects | Donor role for platform |
|------|---------|-----------|------------------------|
| `00-INDEX.md` | (this file) | — | Master index + platform map |
| `10-ZERO-LAYER.md` | Zero-layer: любой вход → контакты (тип-детект → harvest → resolution → enrichment/feedback) | 52 клона + 6 synthesis | `apps/zero/` фундамент: harvest-модули, spaCy-обогащение, Fellegi-Sunter-резолюция, feedback-loop, frontend-компоненты |
| `01-COGNITIVE-WARFARE.md` | Cognitive warfare, narratives, influence, bias | 12 | Spec-ops cognitive-redteam, science belief-dynamics, interpretation bias-parsing |
| `02-SPEC-OPS-PENTEST.md` | Redteam / pentest / emulation / phishing | 14 | Отдел спецопераций TTP/phishing/CTF/defense |
| `03-OSINT-CTI.md` | OSINT / CTI / link analysis | 6 | OSINT-core recon, enrichment, threat-intel |
| `04-GRAPH-TDA.md` | Networks / graphs / hypergraphs / TDA / topology | 11 | science TDA/structure, projection graph features |
| `05-SOCIAL-SIMULATION.md` | Social simulations / ABM | 9 | science counterfactual/stress-test, spec-ops campaign forecasting |
| `06-UI-DASHBOARDS.md` | UI / dashboards / analytics | 4 компонента + 5 synthesis | webapp UI patterns, dashboard UX, risk scoring UI |
| `07-INFRA-STACK.md` | Infra data stack / theory | 1 blueprint (+2 cross-ref) | infra data backbone, science theory |
| `08-ECONOMICS.md` | Economic simulation | 2 полных + 3 cross-ref | science economic dynamics, spec-ops market manipulation |
| `09-INTEGRATION-MATRIX.md` | (cross-reference) | 56 единиц + synthesis | Project → layer → mechanism → priority → license → deliverable |

## Legend

- **(doc)** = documentation detail level (purpose, architecture, methods, data, features, usage, hands-on, limitations)
- **(int)** = integration entry (target app layer, method, what-delivers, how-to-wire, priority, license, risk)
- **Priority**: P1 (critical, extract/integrate code), P2 (strong reuse, service/MCP/data), P3 (pattern/UX inspiration only, no code copy), P4-skip (license-blocked or irrelevant)
- **Integration methods**: `imported-module` · `mcp-server` · `service` · `data-source` · `ml-model` · `ui-component` · `pattern-inspiration-only`

## Integration policy (rev.2 — код копировать можно)

Ключевой критерий — **успешная живая интеграция**, а не лицензионная чистота: копирование кода разрешено владельцем платформы. Лицензия определяет только **механизм** интеграции:

| License family | Механизм интеграции | Проекты (примеры) |
|---|---|---|
| MIT / BSD-3 / Apache-2.0 | ✅ Direct vendoring в `apps/*` c attribution-заголовком (repo + license + commit + guarding test) | caldera, adversary_emulation_library, ael, APT-SF, PhantomStrike-AI, SPEAR, erlik-graph, intellyweave, argus, HypergraphX, BLF, hive-mind-gnca, posim, silisocs, social-oscillation-model, EvoCorps, cognitive_phase_transitions, PHoDMSs, IO-detecting-and-anticipating, CognitiveAttack, lau-network-science, votranhabysscoremicro, YuLan-OneSim, DualMind, Operation-Molasses, DIMA-OntoToolkit, PIDSF |
| GPL / AGPL | ⚙️ Vendoring допустим; предпочтительно **изолированный сервис/бинарь** (process-граница сохраняет чистоту core; attribution обязателен) | fiercephish, PhishSlayer, Raphtory, Labyrinth, MicroWorld, TripleFantasy |
| CC-BY-NC | 📚 Knowledge-only: таксономии/методики в KB, без вендоринга кода | seithar-research |
| Лицензия не заявлена (NO-LICENSE-FILE) / custom | ⚠️ Методы (идеи не охраняются) переносим; код — изоляция сервиса или clean-room переписывание; решение владельца | SYNINT, osia-framework, sticks, topology, AzureAD-Attack-Defense (docs), Lying_with_Truth, NarrativeDiffusion, io-coordinated-replies, CogniX-Surface, LeakHunter, BluePhish, TwinMarket, Entropic-Dynamics, adversarygraph (personal-use), seithar, ABa-KiTo, ABM_polarisation, Social-Network-Simulation-Analysis, APT-SF (без файла) |

> P4-«skip» теперь применяется **только** при технической несовместимости с философией платформы (event-driven, evidence-first, immutable observations, rebuildable projections) → в этом случае `pattern-inspiration-only`.
> \* MITRE-проекты (ael: CT0005) — Apache-2.0 + notice «Approved for public release».
> \* adversarygraph — AdversaryGraph Personal Use License: внутреннее research-использование, изоляция сервиса.

## License quick-look (историческая версия, rev.1 — устарела)

| License family | Status for code extraction | Projects |
|---------------|------|----------|
| MIT / BSD / Apache-2.0 | ✅ Eligible | caldera(Apache), spe*, ael(Apache), APT-SF(MIT), PhantomStrike(MIT), BluePhish(MIT), SPEAR(MIT), Sticks(GPLv3→P4), TripleFantasy(MIT), erlik-graph(MIT), intellyweave(BSD-3), OSIA?, argus(MIT), PIDSF(MIT), HypergraphX(BSD-3), BeliefLandscapeFramework(MIT), persistence-agent(MIT), topology/witness-topology(MIT), ABa-KiTo?, Lau-network-science(MIT), CogniX-Surface(AGPL→P4), MicroWorld(AGPL→P4), posim(MIT), silisocs(MIT), social-oscillation-model(MIT), Social-Network-Simulation-Analysis(MIT?), EvoCorps(MIT), votranhabysscoremicro(Apache-2.0), YuLan-OneSim(Apache-2.0), TwinMarket(Apache-2.0), DualMind(Apache-2.0), f/доп(Apify/0-clause), Lying_with_truth(?), seithar-research(?), NarrativeDiffusion(?), io-coordinated-replies(?), IO-detecting(?), DIMA-OntoToolkit(??), cognitive_phase_transitions(MIT), ABM_polarisation(?), Raphtory(GPLv3→P4), SYNINT(?) |
| GPL / AGPL / CC-BY-NC | ⛔ No code copy (pattern only or P4-skip) | Sticks(GPLv3), TripleFantasy(MIT but Windows-only+offensive), CogniX-Surface(AGPL), MicroWorld(AGPL), Raphtory(GPLv3), reNgine(PANO ref→P3), PANO(CC BY-NC→P3), Labyrinth(AGPL) |
| Commercial / Unknown | ⛔ Skip or P4 | PhantomStrike-AI (research-only?), SEAL? |

> \* = speар, ael, и другие MITRE проекты используют MITRE License (персональное/правительственное использование).

## Reading order

1. `00-INDEX.md` → поймите карту платформы и кластеры
2. `09-INTEGRATION-MATRIX.md` → быстрый cross-reference для выбора донора
3. Любой кластерный файл (`01-...` ... `08-...`) → full документация + интеграция для каждого проекта