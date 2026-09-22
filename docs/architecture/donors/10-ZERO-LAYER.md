# Cluster 0 — Zero-Layer: Contact Harvesting Pipeline

> Part of `docs/architecture/donors/`. Governing spec: `specs/010-zero-layer-contact-harvesting/spec.md`.
>
> **Zero-layer** — фундаментальный слой под acquisition layer. Предоставляет универсальный конвейер "любой вход → контакты" без ИИ: regex + heuristics + deterministic enrichment + Fellegi-Sunter + graph topology. Все specops-инструменты интегрируются **нативно** (никаких MCP wrappers). spaCy + 50+ enrichers на слое 3. Обратная связь между слоем сбора (1) и аналитики (3).

## Архитектура конвейера: любой вход → контакты

```
┌─────────────────────────────────────────────────────────────┐
│  INPUT: имя / email / username / домен / телефон / URL / фото │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: TYPE DETECTION  (НИКАКОГО ИИ)                          │
│  regex + format-validators + heuristics → typed SeedInput     │
│  confidence = deterministic score (0.0–1.0)                  │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│  Domain seed  │   │  Email/Username│   │  Phone/Image/  │
│  → harvesting │   │  → enumeration │   │  URL seeds     │
└───────────────┘   └───────────────┘   └───────────────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  LAYER 2: ENTITY RESOLUTION  (НИКАКОГО ИИ)                   │
│  Fellegi-Sunter probabilistic model + graph topology         │
│  (Louvain, transitive closure, community detection)          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  LAYER 3: ENRICHMENT + FEEDBACK                               │
│  spaCy NER (8 entity types) + 50+ enricher-модулей           │
│  → new seeds → авто-trigger back to LAYER 1                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  OUTPUT: enriched ContactEntities → observation_gate         │
│  → immutable S3 + Kafka → interpretation → admission         │
└─────────────────────────────────────────────────────────────┘

## Роль в платформе

| Слой | Ответственность | ИИ | Язык | Выход |
|---|---|---|---|---|
| **L1 Type Detection** | Автоопределение типа входа | ❌ | Regex + Python | SeedInput (typed) |
| **L1 Harvesting** | Сбор контактов по типу | ❌ | OSINT tools (vendored) | HarvestObservation |
| **L2 Entity Resolution** | Сопоставление сущностей | ❌ | Python/Rust | EntityResolutionGraph |
| **L3 Enrichment** | Обогащение + feedback | ❌ | spaCy + Python | EnrichmentObservation + new seeds |

Zero-layer питается данными из acquisition (Common Crawl, WARC, Browsertrix, StormCrawler) и feeds observations напрямую в `apps/acquisition/observation_gate/` → immutable S3 + Kafka → interpretation → admission → projection → science → feedback.

> **Spec-ops нативная интеграция**: caldera, ael, SPEAR, PhantomStrike-AI, PhishSlayer, Labyrinth, Sticks, TripleFantasy, AzureAD-Attack-Defense, Operation-Molasses прямо в codebase — без MCP wrappers, без service-abstraction. Только direct vendoring и Rust bindings.

## Интеграционная карта zero-layer

| Zero-layer component | Target app layer | Integration method | Spec-ops cross-ref |
|---|---|---|---|
| Type Detection (T100-T102) | apps/zero/ | imported-module | feeds specops seed generation |
| Harvesters (T110-T115) | apps/zero/harvesters/ | vendored tools | feeds specops target profiling |
| Entity Resolution (T120-T122) | apps/zero/resolution/ | imported-module | feeds specops target validation |
| Enrichment (T130-T133) | apps/zero/enrichment/ | imported-module + spaCy | feeds specops scenario seeding |
| Spec-Ops Native (T140-T148) | apps/specops/ + deploy/ | direct vendoring | native |
| Frontend (T150-T154) | apps/webapp/ | ui-component | native |

## 0.1 LAYER 1: Type Detection (НИКАКОГО ИИ)

**Что это.** Универсальный тип-детектор: принимает любой вход, определяет тип через regex + format-validators + heuristics. Confidence — строго детерминированный score (0.0–1.0), никогда не LLM-оценка.

**8 поддерживаемых типов:**

| Type | Regex/Validator | Confidence threshold | Harvest-модули |
|---|---|---|---|
| Domain | `^[a-zA-Z0-9][a-zA-Z0-9-]{1,61}[a-zA-Z0-9]\.[a-zA-Z]{2,}$` + DNS check | 0.95 | email-permutation, subdomain-discovery, DNS-enrichment, breach-search, social-harvest |
| Email | `^[^@\s]+@[^@\s]+\.[^@\s]+$` + MX check | 0.98 | breach-search, social-profiles, GitHub-commit, PGP-key-search, email-pattern-detection |
| Username | `^[a-zA-Z0-9_]{3,30}$` (no @/. no spaces) + not domain | 0.85 | Maigret (3000+ sites), Sherlock (400+ sites), Holehe (250+ sites), GitHub-profile, social-enumeration |
| Phone | RFC 3966 regex (`\+(?:[0-9].?){6,15}` / national variants) + carrier-check | 0.90 | carrier-lookup, breach-first, social-enumeration, voicemail, WhatsApp/Telegram enumeration |
| URL | `^https?://[^\s/$.?#].[^\s]*$` + status check | 0.97 | content-scrape, link-extraction, embedded-contacts, QR-extract, metadata-harvest |
| Image | file-magic `image/jpeg\|png\|webp\|svg` + size check | 0.99 | QR-extraction, EXIF, OCR (tesseract), face-detection (haar/dlib) |
| Free-text name | `^\p{L}[\p{L}\s'.-]{2,60}$` + not domain/email | 0.60 | name-permutation, public-records, social-search, people-datasets |
| PDF/DOCX | magic bytes `PK\|%PDF` | 0.99 | embedded-extraction (pdfminer/email/olefile), document-metadata |

**Confidence scoring (детерминировано):**
```
confidence = base_score × format_match × length_factor × (1 + dns_bonus)
```
`base_score` определяется типом; `format_match` = 1.0 если regex match; `length_factor` = min(len/50, 1.0); `dns_bonus` = +0.1 если DNS запись существует.

**Интеграция**: `apps/zero/type_detector/` → Python service с regex движком, подписанный на Kafka topic `zero_layer.seeds_raw`.


## 0.2 LAYER 1: Harvest Modules — Domain → Contacts (T110)

### Domain harvesters (email-permutation, subdomain-discovery, DNS, breach, social)

| Инструмент | Репозиторий | Что делает | Вендоринг |
|---|---|---|---|
| **erlik-graph** | `gs-ai/erlik-graph` (MIT) | 13 трансформов: subgraph extraction, motif detection, centrality, clustering, embeddings, temporal analysis, anomaly detection, reachability, pattern matching, influence propagation, community detection, link prediction, viz export | Vendored crate в `apps/zero/harvesters/domain/erlik/` |
| **intellyweave** | `gs-ai/intellyweave` (BSD-3) | GLiNER zero-shot entity extraction (7 entity types) для контент-скрейпинга | Vendored в `apps/zero/harvesters/url/` |
| **intel-harvester** | `int3lsec/intel-harvester` (MIT) | Email hunting: pattern detection + SMTP verification. 14 naming patterns | Vendored (MIT) |
| **Mail-Hunter** | `CYB3R-G0D/Mail-Hunter` (MIT) | Professional email addresses from domain via Google dorks | Vendored (MIT) |
| **mailhound** | `null3yte/mailhound` (MIT) | Simple email discovery by domain | Vendored (MIT) |
| **coldreach** | `dhruvmojila/coldreach` (MIT) | Open-source email finder + lead discovery. DNS/SMTP verification | Vendored (MIT) |
| **Email-Permutator** | `emeth-/Email-Permutator` (MIT) | Email permutation: first+last+company → possible emails | Vendored (MIT) |
| **MottaHunter** | `MottaSec/MottaHunter` (MIT) | Advanced email recon: Google/Twitter/LinkedIn, SMTP validation, smart permutations | Vendored (MIT) |
| **GitFive** | `mxrch/GitFive` (MIT) | GitHub profile OSINT: email discovery + verification via commit author system | Vendored (MIT) |
| **WhoCord** | `Siv-nick/WhoCord` (MIT) | Domain module: cross-reference 700+ sites | Vendored (MIT) |
| **theHarvester** | `lgandx/TheHarvester` (MIT) | Email, subdomain, host from 200+ sources | Vendored (MIT) |
| **sublist3r** | `hassanix/sublist3r` (GPL) | Subdomain enumeration via search engines | Isolated service |

## 0.3 LAYER 1: Harvest Modules — Email/Username → Contacts (T111)

| Инструмент | Репозиторий | Что делает | Вендоринг |
|---|---|---|---|
| **Maigret** | `soxoj/maigret` (MIT) | 37k stars. Досье по username из 3000+ сайтов | Vendored (MIT) |
| **Sherlock** | `sdushantha/sherlock` (MIT) | 37k stars. Username enumeration: 300+ platforms | Vendored (MIT) |
| **Holehe** | `kie-kas/holehe` (GPL) | 3k stars. Авторизуется на 250+ сервисах по email (без пароля) | Isolated service |
| **gitsnitch** | `gruns/gitsnitch` (MIT) | GitHub username → commit email | Vendored (MIT) |
| **GitHub Email Extractor** | `toqulent/github-email-extractor` (MIT) | Email из public repos, commits, events через GitHub API | Vendored (MIT) |
| **EmailFinder** | `elliott-diy/EmailFinder` (MIT) | CLI: fetch email из GitHub commits by author username | Vendored (MIT) |
| **gh-mailto** | `georgedavila/gh-mailto` (MIT) | Go: discovers email из GitHub users в orgs. Multiple discovery methods | Vendored (MIT) |
| **gitrecon** | `atiilla/gitrecon` (MIT) | GitHub + GitLab: exposed email + names через API | Vendored (MIT) |
| **user-scanner** | `gs-ai/user-scanner` (MIT) | 2-in-1: Email + Username Intelligence. 295+ platforms + Hudson Rock breach intel | Vendored (MIT) |
| **OSINT Search Tool** | `hasamba/osint-search-tool` (MIT) | 450+ tools в 16 категориях. Email Analysis (35+ tools), Username Analysis (40+ platforms) | Vendored (MIT) |

## 0.4 LAYER 1: Harvest Modules — Phone → Contacts (T112)

**Методология phone → личность (8 шагов, NO AI):**
1. **Google Dorks**: PhoneInfoga dork generation для поиска упоминаний номера в разных форматах
2. **Каталоги**: Truecaller, GetContact, Hiya — имя, сохранённое другими пользователями
3. **OSINT-инструменты**: PhoneInfoga, Phunter, SearchPhone — комплексный профиль
4. **Утечки данных**: DeHashed, HIBP, LeakCheck, IntelX — поиск по phone number в breach-базах
5. **Enumeration**: Ignorant, Phone Number Search — регистрация в WhatsApp, Telegram, Signal, Snapchat, Instagram
6. **Email → Phone**: `email2phonenumber` — номер по email через password reset
7. **Technical**: HLR Lookup, SS7, IMSI-catcher (профессиональный уровень)
8. **Поиск по имени**: Phone OSINT Framework aggressive name hunting через Twilio Caller ID, NumVerify

| Инструмент | Репозиторий | Что делает | Вендоринг |
|---|---|---|---|
| **PhoneInfoga** | `dtag-dev-sec/phoneinfoga` (MIT) | Международный номер footprinting. carrier, region, line type. Google-дорки | Vendored (MIT) |
| **Reverse Phone Lookup** | `reverse-phone-lookup` (MIT) | CLI: обратный поиск + Google-дорки | Vendored (MIT) |
| **Phone OSINT Framework** | `aegisceo/phone-osint-framework` (MIT) | Breach-first: DeHashed/LeakCheck/HIBP по phone+name. Затем TruePeopleSearch, соцсети, employment | Vendored (MIT) |
| **Phunter** | `N0rz3/Phunter` (MIT) | Номер → аккаунты, утечки, цифровые следы | Vendored (MIT) |
| **SearchPhone** | `HackUnderway/SearchPhone` (MIT) | Multi-API: Google, DuckDuckGo, GitHub, Reddit. Hudson Rock | Vendored (MIT) |
| **Ignorant** | `megadose/ignorant` (MIT) | WhatsApp, Telegram, Signal, Snapchat, Instagram | Vendored (MIT) |
| **Phone Number Search** | `megadose/Phone-Number-Search` (MIT) | Web-интерфейс над Ignorant | Vendored (MIT) |
| **DIGI-NETRA** | `pwnxotus/DIGI-NETRA` (MIT) | WhatsApp/Instagram check, carrier detection | Vendored (MIT) |
| **X-osint** | `TechWithTy/X-osint` (MIT) | phone → email from name, VIN OSINT, reverse phone | Vendored (MIT) |

## 0.5 LAYER 1: Harvest Modules — Image → Contacts (T113)

| Инструмент | Репозиторий | Что делает | Вендоринг |
|---|---|---|---|
| **pyzbar** | `Nagasaki45/pyzbar` (MIT) | QR-коды + штрихкоды | Python lib в `apps/zero/harvesters/image/` |
| **Pillow + piexif** | `python-pillow/Pillow` (HPNS) | EXIF extraction (GPS, camera, timestamps) | Vendored (HPNS) |
| **tesseract** | `tesseract-ocr/tesseract` (Apache-2.0) | OCR: извлечение текста с изображений | Vendored binary |
| **face_recognition** | `ageitdev/face_recognition` (MIT) | Face detection + recognition (deterministic, хаар-каскады) | Vendored (MIT) |
| **YOLOv5** | `ultralytics/yolov5` (AGPL) | Object detection на изображениях (deterministic inference) | Isolated service |
| **Reverse Image Search** | manual Google/Yandex/Bing API (requests) | Поиск по изображению → связанные аккаунты/страницы | Vendored (MIT) |

**Image pipeline**: file-magic → QR-extract (pyzbar) → EXIF (piexif) → OCR (tesseract) → face-detection → embedded-entity extraction → contacts

## 0.6 LAYER 1: Harvest Modules — URL → Contacts (T114)

| Инструмент | Репозиторий | Что делает | Вендоринг |
|---|---|---|---|
| **estorides** | `grisuno/estorides` (AGPL-3.0) ✅ клонирован | OSINT-агрегатор + correlation engine (Palantir-inspired): enricher'ы, краулеры, автоматические pivot'ы | Изолированный сервис `apps/zero/harvesters/url/estorides/` |
| **lazyaddon** | `grisuno/lazyaddon` (GPL-3.0) ✅ клонирован | Декларативный менеджер инструментов: turn any GitHub/GitLab project into installable tool | Изолированный сервис (deploy-контур) |
| **intellyweave** | `gs-ai/intellyweave` (BSD-3) | GLiNER zero-shot entity extraction из webpage content | Vendored (BSD-3) |
| **leakhunter** | `gs-ai/leakhunter` (MIT) | Single-panel breach monitoring: email leak detection from URL | Vendored (MIT) |
| **BeautifulSoup** | `wcdolphin/bs4` (MIT) | HTML parsing + content extraction + embedded email/phone/URL | Vendored (MIT) |
| **readability** | `mozilla/readability` (MPL) | Article content extraction (clean text from HTML) | Vendored (MPL) |
| **metadata-parser** | `ro-ch/python-metadata-parser` (MIT) | OpenGraph, Facebook, Twitter, oEmbed, ogp extraction | Vendored (MIT) |
| **youtube-transcript-api** | `.egbertb007/youtube-transcript-api` (MIT) | YouTube video transcript extraction | Vendored (MIT) |
| **invidious-api** | `iv-org/invidious` (AGPL) | YouTube metadata + comments (self-hosted) | Isolated service |

**URL pipeline**: content-scrape (requests + BeautifulSoup) → metadata-extract (OpenGraph/Twitter Cards) → entity-extract (intellyweave GLiNER) → link-graph (outbound links → new domains) → social-embed (social profile URLs) → embedded-contacts (email/phone из текста)

## 0.7 LAYER 1: Harvest Modules — Free-text Name → Contacts (T115)

| Инструмент | Репозиторий | Что делает | Вендоринг |
|---|---|---|---|
| **theHarvester** | `lgandx/TheHarvester` (MIT) | Name-based search через 200+ источников | Vendored (MIT) |
| **SpiderFoot** | `sm0kee/SpiderFoot` (MIT) | Автоматический OSINT: name → email, phone, address, social, breach | Vendored (MIT) |
| **Profil3r** | `rmpuf/Profil3r` (MIT) | Name-based OSINT: email, username, social, breach | Vendored (MIT) |
| **Name-Prism** | `smashew/Name-Prism` (MIT) | Name → ethnicity/gender/probable identity regions | Vendored (MIT) |
| **Name2Email** | `synook/name2email` (MIT) | Name + company → email permutations | Vendored (MIT) |
| **Email-Permutator** | `emeth-/Email-Permutator` (MIT) | Name → email permutations + verification | Vendored (MIT) |
| **public-records** | various (deterministic) | Public records search (LinkedIn API, Crunchbase, SEC EDGAR) | Vendored (API) |

**Name pipeline**: name-normalize → permutation-engine → email-verification (SMTP) → social-search (Maigret/Sherlock) → public-records → breach-search (user-scanner/DeHashed)

## 0.8 LAYER 2: Entity Resolution (НИКАКОГО ИИ)

**Что это.** Кросс-валидация без LLM — строгий, детерминированный и полностью воспроизводимый конвейер. Основа: вероятностные модели, нечёткое сравнение строк и топологический анализ графа.

**4 этапа не-LLM пайплайна:**

### Шаг 1: Нормализация и блокировка (Blocking)

Данные приводятся к каноническому виду: ФИО, телефоны, email нормализуются, поля вроде `first.last` разбиваются на токены. Затем применяется **блокировка (blocking)** — отсечение заведомо нерелевантных пар (полн. перебор = O(n²), для 112M записей = 112M² пар).

**Blocking Rules**:
- **Exact keys**: совпадение по `email`, `phone`
- **Soundex/Metaphone**: "Смит" и "Смитт" → одинаковый код. Soundex: первая буква сохраняется, гласные удаляются, согласные → цифры (B/F/P/V→1, C/G/J/K/Q/S/X/Z→2, D/T→3, L→4, M/N→5, R→6). Metaphone обрабатывает спецслучаи ("TH"→"T").
- **p-sig (probabilistic)**: Bloom filter для генерации сигнатур: запись хешируется в битовый массив (2048 бит, 5 хеш-функций). Блоки формируются по пересечению сигнатур.

**Реализация**: Python port Splink `block_using_rules_sqls` + blocklib для p-sig.

### Шаг 2: Вероятностное сопоставление (Fellegi-Sunter)

**Формула веса для поля** k с уровнем совпадения j:

```
w_{k,j} = log2(m_{k,j} / u_{k,j})
```

Где:
- `m_{k,j} = P(уровень j | записи совпадают)` — вероятность наблюдать совпадение для одного человека
- `u_{k,j} = P(уровень j | записи не совпадают)` — вероятность случайного совпадения

**Итоговый вес**:
```
W = log2(λ/(1-λ)) + Σ w_{k,j}
```

где `λ` = априорная вероятность совпадения.

**EM-алгоритм** для оценки m и u:
- **E-step**: `P(M | γ) = λ·Π m_{k,γ_k} / (λ·Π m_{k,γ_k} + (1-λ)·Π u_{k,γ_k})`
- **M-step**: `m_{k,j}` и `u_{k,j}` обновляются на основе апостериорных вероятностей

**Term Frequency Adjustments**: редкие имена информативнее частых. TF-корректировка:
```
w_TF = w_base + log2(P(значение|M) / P(значение|U))
```

**Реализация**: Splink port в `apps/zero/resolution/matcher/`.

### Шаг 3: Нечёткое сравнение (Fuzzy Matching)

| Метрика | Описание | Где используется |
|---|---|---|
| **Расстояние Левенштейна** | Минимальное число правок (insert/delete/replace) для превращения s в t | email fuzzy match |
| **Jaro-Winkler** | Оценка по Damerau-Levenshtein + бонус за общий префикс: `JW(s,t) = Jaro(s,t) + ℓ·p·(1-Jaro(s,t))` | name fuzzy match (чувствительность 97.4% при пороге 0.8) |
| **Token-based** | Имена → токены, взвешенное по редкости пересечение токенов | адреса, организации |

**Реализация**: Splink comparison levels + joinery для токенов.

### Шаг 4: Топология графа

| Алгоритм | Математика | Применение |
|---|---|---|
| **Louvain** | Модулярность: `Q = (1/2m) Σ [A_ij - k_i·k_j/(2m)] δ(c_i,c_j)` | Community detection: "семья", "коллеги" |
| **Transitive closure** | A → B, B → C ⟹ A → C | Автоматическое расширение связей |
| **Wasserstein distance** | Erosion distance между баркодами | Устойчивые структуры (эхо-камеры) |

**Реализация**: Neo4j GDS `gds.louvain` с `relationshipWeightProperty: 'weight'` + `ripser` для TDA.

**Интеграция**: `apps/zero/resolution/` → EntityResolutionObservation → observation_gate → Kafka `zero_layer.resolved_entities`.

## 0.9 LAYER 3: Enrichment + Feedback (spaCy + 50+ enrichers)

**spaCy NER pipeline** (8 entity types):
1. **PERSON** — имена, фамилии, отчества
2. **EMAIL** — email-адреса
3. **PHONE** — телефонные номера
4. **ADDRESS** — почтовые адреса
5. **ORG** — организации, компании
6. **IP** — IP-адреса
7. **CRYPTO** — криптовалютные кошельки (BTC, ETH, TRX, XMR)
8. **SOCIAL** — social-хэндлы (Telegram, Twitter, Discord, GitHub)

**spaCy конфигурация**:
```python
nlp = spacy.load("en_core_web_lg")  # 750MB — lazy load
# Custom rules для EMAIL, PHONE, CRYPTO, SOCIAL (regex patterns)
# EntityRuler для deterministic matching без LLM
ruler = nlp.add_pipe("entity_ruler", before="ner")
patterns = [
    {"label": "EMAIL", "pattern": [{"TEXT": {"REGEX": r"^[^@\s]+@[^@\s]+\.[^@\s]+$}}]},
    {"label": "PHONE", "pattern": [{"TEXT": {"REGEX": r"^\+?[0-9][\-\s\(\)0-9]{7,15}$"}}]},
    {"label": "CRYPTO", "pattern": [{"TEXT": {"REGEX": r"^(bc1|[13]|[mn]|[ez])[a-zA-Z0-9]{34}"}}]},
    ...
]
ruler.add_patterns(patterns)
```

**50+ enricher-модулей** (все deterministic, NO AI):

| Enricher | Input | Output | Source tool |
|---|---|---|---|
| reverse_email_username | email | username на 3000+ платформах | Maigret |
| username_to_github | username | GitHub профиль + commit email | gitsnitch, gh-mailto |
| email_to_breach | email | утечки (DeHashed, HIBP, LeakCheck) | user-scanner, Holehe |
| phone_to_name | phone | имя владельца (Truecaller, Google Dorks) | PhoneInfoga, Phone OSINT |
| phone_to_email | phone | email из breach данных | Phone OSINT Framework |
| domain_to_subdomains | domain | список поддоменов | sublist3r, theHarvester |
| domain_to_technologies | domain | tech stack (Wappalyzer) | Wappalyzer |
| url_to_social | URL | связанные social-аккаунты | intellyweave, Erfert |
| image_to_qr | image | QR-данные | pyzbar |
| image_to_exif | image | GPS, camera, timestamp | piexif |
| ip_to_geo | IP | геолокация, ISP, ASN | ip2location, MaxMind |
| asn_to_prefixes | ASN | IP prefixes | BGP.tools |
| org_to_suppliers | org name | цепочка поставок | OpenCorporates |
| email_to_linkedin | email | LinkedIn профиль | Hunter.io, Snov.io |
| username_to_discord | username | Discord ID + тег | discord-username-api |
| phone_to_whatsapp | phone | WhatsApp ID | WhatsApp Web API |
| domain_to_dns | domain | DNS записи (A/MX/TXT/SRV) | dnspython |
| domain_to_ssl | domain | SSL сертификаты, цепочка | sslscan, sslyze |
| url_to_pdf | URL | PDF-версия страницы | html2pdf |
| name_to_ethnicity | name | ethnic/gender/region | Name-Prism |
| address_to_geocode | address | GPS координаты | Nominatim |
| social_to_influencer_score | username | влияние в соцсети | Erfert social-score |

**Feedback loop (Layer 3 → Layer 1):**
```
enricher discovers → new email/username/domain/phone → 
  → Kafka topic `zero_layer.feedback_seeds` →
  → type_detector авто-trigger → 
  → new harvest wave с discovered seed
```

Логика: enricher-модуль обнаруживает новый контакт (например, email из commit'a GitHub). Он эмитит `ZeroLayerSeed` с confidence и reason. Type detector автоматически регистрирует его как новый seed → harvester spawner запускает новую волну сбора для этого seed. Цикл продолжается до stabilization или max-depth (default: 3 waves).

**Интеграция**: `apps/zero/enrichment/` → EnrichmentObservation → observation_gate → Kafka `zero_layer.enriched_entities` + `zero_layer.feedback_seeds`.

## 0.10 SPEC-OPS NATIVE INTEGRATION (без обёрток, без MCP)

> **NONMOCK**: абсолютно весь функционал specops взят нативно/ванильно и интегрирован прямо в платформу. Никаких заслонок и оберток. Цели и пайплайны сертифицированы. Лицензия определяет только механизм: permissive → direct vendoring; GPL/AGPL → изолированный процесс; без лицензии → clean-room или knowledge transfer.

### 0.10.1 caldera — Apache-2.0 → P1 (Rust binding, direct import)
- `apps/specops/caldera/src/lib.rs` — pyo3 binding к caldera.core
- planners → `apps/science/scenarios/planning/scenario_dsl.rs` (Diamond + atoms + expected-telemetry + ROE)
- Operation → `app_specops_operation_created` event на `specops.telemetry` Kafka topic
- agents → `apps/specops/agents/` (native Rust agent-runtime, Sandcat-compatible протокол)

### 0.10.2 ael — Apache-2.0 → P1 (direct YAML parser)
- `apps/specops/scenarios/importers/ael.py` — парсер AEL YAML → scenario DSL v2
- `apps/science/scenarios/atoms/ael_registry` — attack-atoms registry с cross-ref на zero-layer harvesters

### 0.10.3 adversary_emulation_library — Apache-2.0 → P1 (direct import)
- `apps/science/scenarios/atoms/` — full+micro plans как scenario bundles
- каждый plan → `scenario_id`, `expected_telemetry`, `atomic_tests[]`

### 0.10.4 PhantomStrike-AI — MIT → P1/P2 (scoring formula direct import)
- AI-scoring формула → `apps/science/findings/severity/phantomstrike_scorers.rs`
- safe-exploit payloads → `apps/specops/payloads/` (vendored C2 profiles)

### 0.10.5 PhishSlayer — GPLv3 → P1 (isolated lab process)
- `deploy/specops/sat/phishslayer-compose.yaml` — lab fixture
- CMDB import → `apps/specops/cmdb/phishslayer_models.py`
- KPI schema → `apps/webapp/components/specops/PhishKPI.tsx`

### 0.10.6 BluePhish — MIT → P1 (SAT lab)
- `deploy/specops/sat/bluephish/` — phishing lab (SMTP/IMAP click-tracking)
- campaign schema → `apps/specops/campaigns/bluephish_schema.rs`

### 0.10.7 fiercephish — AGPL → P2 (isolated campaign service)
- `deploy/specops/sat/fiercephish/` — campaign scheduling + click-tracking через изолированный процесс

### 0.10.8 SPEAR — NO-LICENSE → P1/P2 (methods only)
- TextCNN/BERT/LLM детекторы → `apps/interpretation/detectors/spear_baseline/`
- LIME adversarial attack → `apps/tests/adversarial/` (red-team чек для CI детекторов)

### 0.10.9 Sticks — MIT → P1 (lab fixture + STIX metric)
- `deploy/specops/lab/sticks-compose.yaml` — Caldera+Kali+nginx+DB
- STIX procedural-sufficiency метрика → `apps/science/metrics/stix_sufficiency.rs`
- RoE-gate → `apps/science/scenarios/roe/`

### 0.10.10 TripleFantasy — MIT → P2 (pattern catalog)
- `docs/kb/specops/patterns/triplefantasy.md` — modular C++ implant patterns:
  - AES-256-GCM/ChaCha20 шифрование
  - HKDF key derivation
  - anti-debug/anti-VM detection

### 0.10.11 AzureAD-Attack-Defense → P2 (KB)
- `docs/kb/identity/azuread_playbook.md` — Entra ID playbook:
  - password spray → detection rule `apps/interpretation/detectors/azuread_password_spray.rs`
  - consent grant attack → detection rule
  - AiTM → detection rule
  - PRT replay → detection rule

### 0.10.12 Labyrinth — AGPL-3.0 → P1 (native Rust deception)
- `apps/specops/deception/` — cognitive portal-trap как native Rust nodes
- TUI dashboard → `apps/webapp/components/specops/LabyrinthTUI.tsx`
- web dashboard → `apps/webapp/components/specops/LabyrinthWeb.tsx`

### 0.10.13 Operation-Molasses — MIT → P1 (toolkit + KB)
- `toolkit/operation_molasses/` — 33-phase kill-chain IaC база
- `docs/kb/specops/molasses_33phases.md` — full phase описание
- short-and-distort disinfo-bot → `apps/specops/disinfo/molasses_bot.py`

### 0.10.14 PIDSF — MIT → P1 (RoE-gate pattern + detection)
- RoE-gate (обязательный sign-off) → `apps/science/scenarios/roe/`
- detection-модуль (permutation+crt.sh scoring) → `apps/acquisition/enrichment/lookalike/`

### 0.10.15 Новые spec-ops-доноры (клонированы 2026-09-21, см. §0.12 «Spec-ops bridge»)
| Донор | Репозиторий | Что даёт | Слой |
|---|---|---|---|
| mysterious-cyclopus | Iankulani/mysterious-cyclopus | multi-platform C2 для controlled pentest | `deploy/specops/` (isolated lab) |
| CyberStrikeAI | Ed1s0nZ/CyberStrikeAI | AI-native offensive security (edge devices) | `apps/specops/` (lab) |
| Flippy | thecaticorn01/Flippy | NFC/BLE/IR wireless research, mobile emulation | `deploy/specops/lab/` |
| postexploitation-toolbox-android | timschneeb/... | Android post-exploitation (uid 1000) | `docs/kb/specops/` + lab |
| Hostile-Command-Suite | cycloarcane/... | LLM-агент выбирает инструмент по типу данных | `apps/zero/harvesters/orchestrator/` |

> Все spec-ops-доноры работают в lab-контуре с RoE-гейтом; код интегрируется нативно (vendoring / isolated process по лицензии — детальный маппинг в `09-INTEGRATION-MATRIX.md`, кластер 0).

## 0.11 Sources From Everywhere — откуда zero-layer черпает инфу

**Принцип**: zero-layer подключается к любому источнику, где могут быть контакты или сущности. Каждый источник — адаптер с capability-регистрацией (`apps/acquisition/adapters/registry.py` паттерн: register → capabilities → scheduler auto-aware, никаких `if source == ...`).

### Web content (классический и JS-веб)
| Источник | Инструмент | Роль в zero-layer |
|---|---|---|
| Веб-краулинг | thecrowler (pzaino) — event-driven, реальные Chromium/Firefox, YAML/JSON rulesets | источник observations → URL-harvesters |
| Веб-краулинг (bulk) | Common Crawl, Heritrix, Nutch, StormCrawler, Browsertrix (acquisition adapters — уже есть) | резервуар страниц для entity-extraction |
| Поиск/разведка | SpiderFoot (200+ модулей), secureflow-intel (SpiderFoot-форк) | автоматический обход по seed |
| Enrichers | erfert (estorides) — сотни enricher-модулей | URL/domain → сотни полей |
| Keyless-комбайн | osint-terminal (438 keyless-инструментов), argus-cotcollective (13 модулей, 0 API-ключей) | федерация модулей |
| Multi-source orchestration | Hostile-Command-Suite (агент выбирает инструмент по типу: name→web, username→Sherlock, email→Mosint) | LLM-агент-роутинг (верхние слои) |

### Tor / Dark Web
| Источник | Инструмент | Роль |
|---|---|---|
| Onion-поиск | OnionSearch (megadose) — параллельный поиск по onion-движкам | search-адаптер через Tor SOCKS5 |
| Tor-выход | свой Tor-пул (arti/9050) + per-source circuit isolation | анонимная доставка для всех web-модулей |
| Paste/code forges | VoidAccess-паттерн (self-hosted: paste-сайты, code forges, IOC/wallet extraction, экспорт STIX 2.1/MISP/YARA) | breach/paste-канал → breach-intel |
| Onion-индексы | Ahmia-style индексы (self-host) | discovery по .onion |

### Telegram / мессенджеры
| Источник | Подход | Роль |
|---|---|---|
| Telegram каналы/группы | свой адаптер на TDLib/Telethon (чтение публичных), tgstat/telemetr публичная аналитика | @username/телефон → каналы/комменты |
| WhatsApp/Instagram | DIGI-NETRA (проверка регистрации), ignorant (enumeration) | телефон → присутствие в мессенджерах |
| Bulk social contacts | EmailExtractWithProxyApp — bulk экстракция email/phone/WhatsApp/Telegram из соцсетей | целевые контакт-листы |

### Прочие каналы
- **Git/GitHub**: gitsnitch, gh-mailto, gitrecon, GitHub Email Extractor, GitFive, EmailFinder — commit-email discovery.
- **Breach-intel**: mosint (alpkeskin), user-scanner (+Hudson Rock), HIBP/DeHashed/LeakCheck/IntelX-интеграции.
- **Телефон**: phoneinfoga, phone-osint-framework (breach-first), Phunter, SearchPhone, ignorant, email2phonenumber (password-reset pivot).
- **Сетевая**: trident (DNS/ASN/CT/PGP, один Go-бинарь, ноль ключей).
- **OPSEC-источники**: phantomsignal (54+ sources, proxy pool, adaptive pacing, JA3/JA4 stealth egress), osint-web-mcp (stealth-браузер Playwright+Stealth), Aperture (local-first browser workbench, без API-ключей и телеметрии).
- **Per-source politeness**: каждый адаптер декларирует rate-limit, robots-политику и класс исполнения; proxy-rotation и adaptive pacing (паттерн phantomsignal) — единая инфраструктура egress-лоя.


## 0.12 Clone Inventory — клонированные доноры zero-layer

Все репозитории клонированы в `donors/` (--depth 1, проверено 2026-09-21).


### Web/crawl

| Директория | Репозиторий | Статус |
|---|---|---|
| thecrowler | pzaino/thecrowler | ✅ клонирован |
| spiderfoot | smICALLEF/spiderfoot | ✅ клонирован |
| secureflow-intel | BarakMozesPro/secureflow-intel | ✅ клонирован |
| estorides | grisuno/estorides | ✅ клонирован |

### Frameworks

| Директория | Репозиторий | Статус |
|---|---|---|
| lazyaddon | grisuno/lazyaddon | ✅ клонирован |
| seekr | seekr-osint/seekr | ✅ клонирован |
| osint-terminal | RojanSapkota/osint-terminal | ✅ клонирован |
| argus-cotcollective | cotcollective/argus | ✅ клонирован |
| osint-web-mcp | Johnz86/osint-web-mcp | ✅ клонирован |
| Aperture-OSINT-Workbench | petstuk/Aperture-OSINT-Workbench | ✅ клонирован |
| phantomsignal | getphantomsignal/phantomsignal | ✅ клонирован |
| The-3rd-Eye | Ordinary0x/The-3rd-Eye | ✅ клонирован |
| osint-search-tool | hasamba/osint-search-tool | ✅ клонирован |
| TraceMatrix | PanagiotisDrakatos/TraceMatrix | ✅ клонирован |
| Hostile-Command-Suite | cycloarcane/Hostile-Command-Suite | ✅ клонирован |
| TheBigBrother | chadi0x/TheBigBrother | ✅ клонирован |

### Tor/darkweb

| Директория | Репозиторий | Статус |
|---|---|---|
| OnionSearch | megadose/OnionSearch | ✅ клонирован |

### Net

| Директория | Репозиторий | Статус |
|---|---|---|
| trident | tbckr/trident | ✅ клонирован |

### Username/Email

| Директория | Репозиторий | Статус |
|---|---|---|
| maigret | soxoj/maigret | ✅ клонирован |
| sherlock | sherlock-project/sherlock | ✅ клонирован |
| holehe | megadose/holehe | ✅ клонирован |
| user-scanner | kaifcodec/user-scanner | ✅ клонирован |
| mosint | alpkeskin/mosint | ✅ клонирован |
| WhoCord | Siv-nick/WhoCord | ✅ клонирован |
| OsintEye | atiilla/OsintEye | ✅ клонирован |
| Profil3r | Greyjedix/Profil3r | ✅ клонирован |

### Git-email

| Директория | Репозиторий | Статус |
|---|---|---|
| gitsnitch | gruns/gitsnitch | ✅ клонирован |
| gitrecon | atiilla/gitrecon | ✅ клонирован |
| GitFive | mxrch/GitFive | ✅ клонирован |
| github-email-extractor | toqulent/github-email-extractor | ✅ клонирован |
| EmailFinder | elliott-diy/EmailFinder | ✅ клонирован |
| gh-mailto | codeGROOVE-dev/gh-mailto | ✅ клонирован |

### Domain/Email

| Директория | Репозиторий | Статус |
|---|---|---|
| theHarvester | laramies/theHarvester | ✅ клонирован |
| Sublist3r | aboul3la/Sublist3r | ✅ клонирован |
| Mail-Hunter | CYB3R-G0D/Mail-Hunter | ✅ клонирован |
| coldreach | dhruvmojila/coldreach | ✅ клонирован |
| Email-Permutator | emeth-/Email-Permutator | ✅ клонирован |
| MottaHunter | MottaSec/MottaHunter | ✅ клонирован |
| EmailHarvester | maldevel/EmailHarvester | ✅ клонирован |
| Gmail_Checker | Baga6312/Gmail_Checker | ✅ клонирован |

### Phone

| Директория | Репозиторий | Статус |
|---|---|---|
| phoneinfoga | sundowndev/phoneinfoga | ✅ клонирован |
| phone-osint-framework | aegisceo/phone-osint-framework | ✅ клонирован |
| Phunter | N0rz3/Phunter | ✅ клонирован |
| SearchPhone | HackUnderway/SearchPhone | ✅ клонирован |
| ignorant | megadose/ignorant | ✅ клонирован |
| DIGI-NETRA | pwnxotus/DIGI-NETRA | ✅ клонирован |
| X-osint | TechWithTy/X-osint | ✅ клонирован |
| email2phonenumber | martinvigo/email2phonenumber | ✅ клонирован |

### Social/bulk

| Директория | Репозиторий | Статус |
|---|---|---|
| EmailExtractWithProxyApp | psoman-star/EmailExtractWithProxyApp | ✅ клонирован |

### Spec-ops bridge

| Директория | Репозиторий | Статус |
|---|---|---|
| mysterious-cyclopus | Iankulani/mysterious-cyclopus | ✅ клонирован |
| CyberStrikeAI | Ed1s0nZ/CyberStrikeAI | ✅ клонирован |
| Flippy | thecaticorn01/Flippy | ✅ клонирован |
| postexploitation-toolbox-android | timschneeb/postexploitation-toolbox-android | ✅ клонирован |

### Недоступные URL (404 на 2026-09-21)

| Заявленный URL | Результат |
|---|---|
| null3yte/mailhound | ❌ 404 (удалён/переименован) |
| megadose/phone-number-search | ❌ 404 |
| int3lsec/intel-harvester | ❌ 404 → замена: maldevel/EmailHarvester |
| RichardBarron27/red-specter-specter-censor | ❌ 404 → threat-landscape (defensive KB, без вендоринга) |
| mavhm/email2phonenumber | ❌ 404 → актуальный: martinvigo/email2phonenumber |
| georgedavila/gh-mailto | ❌ 404 → актуальный: codeGROOVE-dev/gh-mailto |


> Итого: **53/53 клонировано**; в `donors/` теперь **106 папок** (было 53).

## 0.13 Frontend — OSINT Workbench (лучший в мире дизайн поверх всего)

**Концепция**: единый tactical workbench, где **три платформенных модуля** (OSINT / Экономика / Spec-Ops) питаются из одного OSINT-ядра. Zero-layer — входная точка всего.

```
+------------------------------------------------------------------+
| COMMAND BAR: [universal seed input | type badge | conf chip]      |
| MODULE SWITCHER: ( OSINT ) ( ECONOMICS ) ( SPEC-OPS )             |
+-----------+--------------------------------------+---------------+
| HARVEST   | FORCE-GRAPH CANVAS                   | ENTITY        |
| RAIL SSE  | D3 v7 + canvas | WebGL >5k nodes    | INSPECTOR     |
| module    | node glyphs | cluster halos          | CONTACTS      |
| status    | edge width = confidence | pivot menu | PROVENANCE    |
|           |                                      | CLAIMS        |
+-----------+--------------------------------------+---------------+
| TIMELINE SCRUBBER (harvest waves | specops telemetry | replay)    |
+------------------------------------------------------------------+
```

### Ключевые компоненты
| Компонент | Паттерн-донор | Функция |
|---|---|---|
| UniversalSeedInput | — | вставь что угодно; детект-бейдж до запуска; drag&drop файлов |
| HarvestRail | CogniX (SSE-прогресс, KPI-timeline) | live-статус каждого модуля; счётчики found/верифицировано; waves |
| ForceGraphCanvas | ARGUS (COP), lau-network-science | D3 v7 force-sim + canvas; WebGL-fallback; Louvain-гало; pivot-on-node |
| EntityInspector | OSIA (briefing), vitni (evidence) | табы Contacts/Provenance/Claims; confidence-страйпы; source_chain |
| TimelineScrubber | vitni (timeline), reNgine (scrollspy) | реплей harvest-волн и spec-ops телеметрии |
| OperationMatrix | Magma (операционная матрица) | agents × TTP-сетка; SSE-ячейки; RoE-баннер; kill-switch |
| DeceptionView | Labyrinth (TUI/live log) | live-лог взаимодействий агентов с deception-контуром |
| PhishKPI | CogniX (KPI-timeline) | CTR/TTR/report-rate SAT-кампаний |
| EconLens | TwinMarket / votran | econ-facets компаний; стресс-тесты; политико-экономические предикторы |
| ReportsPalette | OSIA (INTSUM/SITREP) | генерация докладов из графа |

### Дизайн-система
- **Dark tactical theme**: токены из `pano-tokens.css` + kafSIEM-акцент (E8630A orange), слоистые поверхности; контраст WCAG AA.
- **Плотность**: compact / comfortable; keyboard-first (command palette Ctrl+K); мобильные стили (kafSIEM mobile).
- **Дата-контракты**: SSE `/stream/harvest`, `/stream/graph` (инкрементальные дельты узлов/рёбер), `/stream/specops`; CQRS read-API для inspector.
- **Производительность**: canvas-render, web-worker force-layout, incremental alphaTarget, edge-bundling >10k узлов.
- **Качество**: Storybook + screenshot-тесты (T154), a11y-audit (T104 спеки 009), ru/en i18n.
- **Lineage-видимость**: каждая панель показывает donor + license + adapted file (US1 спеки 009).
- **Интеракции**: pivot-on-node (правый клик по узлу → новая волна с этим seed), path-highlight, time-scrub, экспорт STIX 2.1 / graph JSON / CSV.

### Три платформенных модуля над OSINT-ядром
| Модуль | Что видит аналитик | Источник данных |
|---|---|---|
| **OSINT** | seed → graph → inspector → timeline → отчёты | zero-layer → acquisition → projections |
| **Экономика** | econ-facets компаний; стресс-тесты; policy-simulator | science(econ) → TwinMarket/votran/Entropic |
| **Spec-Ops** | OperationMatrix; DeceptionView; PhishKPI; RoE-гейт | specops → caldera telemetry / Labyrinth / SAT |

> Frontend питается исключительно из OSINT-ядра (единый источник истины); spec-ops и экономика — линзы/режимы отображения тех #6е данных + их собственные артефакты (telemetry, econ-claims).
