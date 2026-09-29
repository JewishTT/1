# Input: 022 — estorides donor mining

> **Verbatim user prompt.** Reproduced without reduction. This file is the source of truth for
> this feature; `spec.md` is the engineering reading of it and yields to this document wherever
> the two appear to differ.

---

Да. И вот **это уже меняет картину реализации 021 очень сильно**.

Я посмотрел `grisuno/estorides` не как пользователь, а как донор архитектурных и программных примитивов. Там действительно огромный пласт уже написанного: около **179 source-файлов в каталоге sources**, **50+ специализированных parsers**, асинхронный HTTP transport, retry/backoff, circuit breaker, SQLite cache, structured extraction, entity resolution с blocking и cross-script matching, relation inferers, persistent fusion store, case store, NetworkX/Kuzu graph, pagination, system-tool adapters и bounded pivot engine. Сам проект позиционируется именно как OSINT aggregator/correlation engine с async fanout и knowledge graph. ([Medium][1])

То есть я бы теперь вообще не мыслил так:

> «Нам надо реализовать 021».

Я бы мыслил так:

> **«021 — конституционный каркас, estorides — массив готовых implementation primitives, которые мы переплавляем в наши контракты».**

Это гораздо мощнее.

## Самое главное: где именно лежит готовая работа

| Наш слой          | Донор                                                             | Что забираем                                                                       | Степень адаптации |
| ----------------- | ----------------------------------------------------------------- | ---------------------------------------------------------------------------------- | ----------------- |
| Acquisition       | `async_client.py`                                                 | async HTTP, retry, backoff, concurrency, circuit breaker, cache, proxy, SSRF guard | средняя           |
| Source registry   | `source_loader.py` + `sources/`                                   | декларативный каталог источников, routing, metadata, pagination                    | средняя           |
| Parsing           | `parsers.py`                                                      | десятки готовых source-specific parsers                                            | низкая/средняя    |
| Pagination        | `pagination.py`                                                   | page/cursor/offset machinery                                                       | низкая            |
| System tools      | `system_app_sources.py` + `tool_runner.py`                        | Kali/system-app execution + parsing + bounds                                       | средняя           |
| Mentions          | `entity_extraction.py`                                            | regex extraction, structured extraction, normalization, context                    | **средняя**       |
| Entity resolution | `entity_resolution.py` + `entity_store.py` + `transliteration.py` | blocking, Jaro-Winkler, cross-script, aliases, SAME_AS candidates                  | **высокая**       |
| Relation signals  | `relationship_inference.py`                                       | готовые DNS/WHOIS/Shodan/OTX/NVD/etc. extractors                                   | **средняя**       |
| Hypotheses        | `hypothesis_engine.py`                                            | deterministic hypothesis aggregation, evidence weighting, bounded evidence         | высокая           |
| Persistence       | `cases.py`, `fusion_store.py`                                     | persistence patterns, provenance aggregation, cross-run fusion                     | высокая           |
| Graph projection  | `knowledge_graph.py`, `graph_kuzu.py`                             | projection/export/indexing mechanics                                               | высокая           |
| Temporal          | `change_detection.py`, `feeds.py`                                 | snapshot diff, change events, spatiotemporal records                               | средняя           |
| Workflow          | `pivot_engine.py` + orchestration parts                           | bounded recursion, frontier, event sink                                            | высокая           |

И вот тут начинается самое вкусное.

# 1. `parsers.py` — это практически подарок

В `estorides_core/parsers.py` примерно **1300 строк** и огромная библиотека parser-ов для конкретных источников: DNS, RDAP, crt.sh, IP intelligence, Shodan, GreyNoise, URLScan, Wayback, ThreatFox, URLHaus, MalwareBazaar, OTX, HIBP, Wikidata, GitHub, Reddit, Mastodon, blockchain и так далее.

Это именно тот кусок, который **нам совершенно незачем писать заново**.

Но важно понимать границу:

```text
estorides parser
        ↓
normalized source payload
        ↓
Observation / ObservationContext
        ↓
наш interpretation layer
```

А не:

```text
estorides parser
        ↓
Entity
        ↓
GraphEdge
```

То есть parser остаётся parser-ом.

Это может уничтожить **огромную долю механической работы acquisition/parser части**.

# 2. `entity_extraction.py` очень хорошо превращается в наш Mention machinery

Вот где донора уже есть:

```python
extract_from_text(...)
extract_from_json(...)
extract_structured(...)
merge(...)
```

И это не игрушечный regex-only extractor.

Он уже умеет:

* IP;
* domains;
* email;
* hashes;
* CVE;
* ASN;
* crypto;
* MAC;
* phone;
* handles;
* structured extraction по полям;
* bounded scanning;
* context windows;
* deduplication;
* нормализацию query;
* detection query type.

Но у них:

```python
Entity(
    type=...,
    value=...,
    source=...,
    confidence=...
)
```

уже **схлопывает несколько эпистемических уровней**.

У нас это должно распасться:

```text
raw observation
      ↓
mention occurrence
      ↓
type signal
      ↓
type hypothesis
      ↓
type assertion
      ↓
entity resolution
```

То есть мы не переписываем extractor.

Мы делаем примерно:

```python
estorides.extract_from_json(...)
        ↓
MentionOccurrenceIndex
        +
TypeSignal
```

и сохраняем:

* surface;
* span/path;
* context;
* observation_ref;
* producer_ref;
* producer_version;
* source field;
* normalization trace.

Это очень хороший донор именно потому, что вся грязная работа по **нахождению потенциально значащих фрагментов** уже сделана.

# 3. Самый жирный кусок — `relationship_inference.py`

Вот здесь, на мой взгляд, estorides может сэкономить **массу работы по T133–T147**.

Там уже есть source-specific relation inference для:

```text
DNS
crt.sh
Shodan
GreyNoise
AbuseIPDB
WHOIS
URLScan
Phonebook
IP-API
OTX
NVD
```

Например:

```text
domain -> resolves_to -> ipv4
domain -> has_subdomain -> domain
ipv4 -> has_cve -> cve
ipv4 -> exposes_port -> port
ipv4 -> located_in -> country
domain -> registered_with_email -> email
domain -> uses_technology -> technology
indicator -> linked_to_threat_actor -> threat_actor
indicator -> mapped_to_technique -> mitre_technique
```

Но у них это сейчас:

```python
kg.add_relationship(...)
```

То есть:

> observation → сразу graph edge.

**Вот это мы не переносим.**

Мы буквально делаем adapter:

```text
EstoridesInferer
      ↓
RelationSignalProducer
      ↓
RelationSignal
      ↓
PredicateHypothesis
      ↓
RelationCandidate
      ↓
Validation
      ↓
Admission
      ↓
RelationClaim
      ↓
GraphEdge / HyperEdge
```

И старую функцию:

```python
_infer_dns(...)
```

превращаем концептуально в:

```python
produce_dns_relation_signals(...)
```

Она больше **ничего не утверждает**.

Она только говорит:

> «В этой Observation обнаружен сигнал, который наблюдательно совместим с relation `resolves_to`, вот участники, вот их роли, вот observation ref».

Это почти идеально ложится на нашу философию.

# 4. `entity_resolution.py` — это ещё один огромный подарок

Тут вообще интересный случай.

Донор уже реализовал довольно приличную механику:

### deterministic types

```text
ipv4
ipv6
hash
CVE
ASN
crypto
MAC
```

→ exact normalization.

### fuzzy types

```text
person
org
username
keyword
```

→ blocking + similarity.

Плюс:

* Jaro;
* Jaro-Winkler;
* transliteration;
* consonant skeleton;
* aliases;
* SAME_AS candidates;
* distinction between mergeable and non-mergeable types;
* persistent cross-run identity store.

Это **не нужно выбрасывать**.

Но нельзя принимать модель:

```text
Entity → CanonicalEntity
```

как истину нашего substrate.

Нам гораздо правильнее:

```text
Mention / TypeAssertion
        ↓
ResolutionCandidate
        ↓
matching signals
        ↓
resolution hypothesis
        ↓
adjudication
        ↓
resolved entity assertion
```

То есть алгоритм matching-а можно практически забрать.

А **эпистемическую оболочку** накладывает 021.

И вот это очень важное различие.

# 5. `hypothesis_engine.py` — неожиданно полезен для нашей внутренней механики

Там уже есть очень правильная идея:

```text
observation
   ↓
evidence
   ↓
hypothesis
   ↓
score/confidence
```

Причём они делают это:

* deterministic;
* pure;
* content-addressed;
* bounded;
* с explicit supporting / contradicting evidence.

Например:

```python
Hypothesis(
    id=...,
    type=...,
    supporting=[...],
    contradicting=[...],
)
```

Для нас готовая модель недостаточна, но **сам pattern очень правильный**.

Особенно:

```text
pure transformation
same input → same output
content hash
bounded evidence
explicit support / contradiction
```

Это можно использовать как реализационный шаблон для наших:

```text
PredicateHypothesis
TypeHypothesis
RelationCandidate
```

# 6. `async_client.py` — практически готовый acquisition engine

Это уже вполне серьёзный production-oriented primitive:

```text
async HTTP
per-host concurrency
retry
exponential backoff
circuit breaker
SQLite cache
proxy
SOCKS/Tor
SSRF protection
automatic auth substitution
timeouts
```

То есть вместо написания нового:

```text
HTTP transport v2
HTTP transport v3
HTTP transport v4
```

можно взять основу и встроить её под наш acquisition contract.

Но обязательно убрать из неё предположение:

> «результат HTTP-запроса = окончательная observation».

У нас acquisition обязан фиксировать:

```text
request intent
request
response
capture metadata
source
parser
raw bytes / raw representation
content digest
retrieval timestamp
adapter version
```

и только после этого отдавать объект interpretation pipeline.

# 7. `source_loader.py` + 179 source definitions — это вообще отдельный клад

Вот это, наверное, **самый недооценённый актив**.

В `sources/` у estorides огромный декларативный каталог:

```text
DNS
IP infra
Web
Social
Threat
Breach
Geolocation
Knowledge
Wireless
Blockchain
Paste/Leaks
Visual
Reputation
Tech
Cloud
People
Code
Supply
PDNS
System tools
```

То есть у нас может появиться примерно такая архитектура:

```text
DONOR SOURCE PACK
       ↓
SourceAdapterRegistry
       ↓
AcquisitionAdapter
       ↓
Observation
```

Вместо того чтобы самим руками описывать десятки/сотни источников.

И здесь особенно хороша их идея:

```yaml
name:
kind:
parser:
applies_to:
requires_key:
key_env:
pagination:
contact:
tool:
```

Эту модель можно очень хорошо преобразовать в нашу декларативную acquisition registry.

# 8. `pagination.py` тоже не писать

Там уже выделены стратегии:

```text
page
cursor
offset
limit
response path
max pages
```

Наш acquisition слой может просто использовать этот механизм.

Это мелочь по сравнению с relation extraction, но такие мелочи в сумме съедают дни и недели.

# 9. `system_app_sources.py` — ещё один готовый адаптерный слой

Особенно если мы хотим реально видеть интернет через разные внешние инструменты.

У них уже есть схема:

```text
YAML source
   ↓
tool binary
   ↓
sandbox
   ↓
bounded stdout
   ↓
tool parser
   ↓
normal observation
```

Причём там уже есть десятки parser-ов для:

```text
amass
maigret
phoneinfoga
sherlock
holehe
wafw00f
sublist3r
dnsrecon
dnsenum
fierce
dmitry
urlcrazy
metagoofil
whatweb
theHarvester
mailfy
phonefy
searchfy
...
```

Нам не нужен новый велосипед.

# 10. `pivot_engine.py` — это почти прототип будущего investigation expansion engine

Вот это особенно интересно концептуально.

У них уже есть:

```text
frontier
max depth
max steps
max entities
deadline
priority queue
event sink
EntityRunner
```

То есть:

```text
seed
 ↓
run
 ↓
extract leads
 ↓
score
 ↓
frontier
 ↓
next hop
 ↓
...
```

Это очень близко к тому, что нам потом понадобится для:

```text
InvestigationWorkflow
```

Но опять же:

**не переносить старую семантику целиком.**

Использовать как scheduler / bounded traversal primitive.

# 11. `cases.py` и `fusion_store.py`

Здесь я бы не переносил код буквально.

Но их storage ideas очень полезны.

У них уже разделены:

```text
case
observation
entity
entity_sources
properties
relationships
```

и есть cross-run fusion.

Для нас это превращается в гораздо более строгую схему:

```text
Investigation
Observation
Mention
Signal
Hypothesis
Candidate
ValidationReport
AdmissionDecision
RelationClaim
TypeAssertion
Projection
```

То есть donor storage = **прототип физической persistence organization**, а 021 определяет epistemic semantics.

# 12. `knowledge_graph.py` → только projection

Это прямо идеальный случай.

В estorides:

```python
KnowledgeGraph.add_relationship(...)
```

является фактическим write path.

У нас должно быть:

```text
RelationClaim
      ↓
ProjectionBuilder
      ↓
GraphEdge / HyperEdge
```

И только.

Тогда NetworkX/Kùzu становятся:

```text
query acceleration
visualization
traversal
analytics
```

а не источником истины.

# 13. `change_detection.py` — это уже следующий слой над substrate

Там уже есть:

```text
Snapshot
Diff
Change
ChangeReport
```

с обнаружением:

```text
new entity
disappeared entity
property changed
source added
edge added/removed
```

Это буквально кирпич для будущего temporal/worldline слоя.

Причём у них уже хороший паттерн:

```text
immutable snapshots
pure transformation
content-addressed change IDs
```

Это очень хорошо сочетается с нашей моделью worldline.

Не сейчас. Но **не выбрасывать**.

# 14. Есть ещё одна совершенно неожиданная ценность: boundedness

В estorides очень много механик, которые мы сейчас всё равно собираемся реализовывать:

```text
max pages
max entities
max steps
deadline
max scan chars
max evidence
per-host concurrency
cache TTL
circuit cooldown
output caps
```

Это не просто удобства.

Для нашего проекта это можно использовать как **implementation material для constitutional boundedness**.

# Но есть ОДНА фундаментальная вещь, которую нельзя делать

Не надо:

```text
git merge estorides
```

и потом пытаться превратить получившийся монолит в нашу систему.

Это будет катастрофой.

Потому что у estorides философия примерно:

```text
source
 → parser
 → Entity
 → inferer
 → graph
 → resolver
```

А у нас:

```text
Observation
 → Context
 → Mention
 → Signal
 → Hypothesis
 → Candidate
 → Validation
 → Admission
 → Claim
 → Projection
```

То есть **мы используем estorides снизу вверх**, а не тащим его архитектуру сверху вниз.

# Правильная стратегия: Donor Mining

Я бы сделал буквально такой режим разработки:

```text
                  ESTORIDES
                     │
       ┌─────────────┼───────────────┐
       ↓             ↓               ↓
   acquisition    extraction     relation
       │             │               │
       ↓             ↓               ↓
    adapters       mentions       signals
       └─────────────┼───────────────┘
                     ↓
               OUR SUBSTRATE
                     │
          ┌──────────┴───────────┐
          ↓                      ↓
      resolution             claims
          ↓                      ↓
          └──────────┬───────────┘
                     ↓
                 projection
                     ↓
                 Graph/Kuzu
```

То есть:

> **estorides supplies mechanisms; 021 supplies ontology-free semantics, epistemology, identity, lifecycle and provenance.**

Это как раз тот случай, когда внешний проект **не конкурирует с нашей архитектурой**, а становится мясом для её реализации.

# Что это означает для T101–T194

И вот здесь появляется очень приятный эффект.

Я бы **не переписывал 021** ради этого.

В существующие задачи просто добавляется принцип:

> **каждое task implementation-first анализирует donor code и переиспользует существующий implementation, если он удовлетворяет контракту 021 после адаптации.**

Особенно:

### P1 / Acquisition

Можно практически брать:

```text
async_client
source_loader
sources/*
pagination
system_app_sources
tool_runner
ssrf_guard
```

### P2/P3 / Mention + Type

Основной донор:

```text
entity_extraction
observation_models
structured extraction tests
```

### P4A/B/C / Relation Signals

Самый жирный:

```text
relationship_inference
parsers
structured parser outputs
```

Это может резко сократить объём нового кода.

### P5 / Candidate

```text
hypothesis_engine
entity_resolution matching primitives
```

Но поверх нашей модели.

### P6 / Lifecycle

Здесь донор уже вторичен — **наша архитектура должна победить**.

### P8 / Persistence + Projection

Берём идеи и низкоуровневые паттерны из:

```text
cases
fusion_store
knowledge_graph
graph_kuzu
sqlite_store
```

но авторитетом остаётся наш substrate.

### P9 / Replay / benchmarks

Берём:

```text
pure modules
stable ids
bounded transforms
change detection
pivot budget patterns
```

# А теперь важный вывод

Я бы даже сказал сильнее:

**Feature 021 сейчас выглядит не как "нам предстоит реализовать 94 задачи", а как "нам предстоит адаптировать уже существующий массив OSS-кода к строгому substrate contract".**

Разница колоссальная.

В частности, самая дорогая механическая работа уже присутствует:

```text
HTTP transport
source catalogue
pagination
50+ parsers
structured extraction
entity normalization
entity resolution
transliteration
relation extraction logic
persistent stores
graph projection
tool adapters
bounded traversal
```

А **наша реально новая работа** концентрируется там, где estorides принципиально проще:

```text
Observation as durable fact
Mention as first-class artifact
Signal as observation
Hypothesis as epistemic possibility
Candidate as structural assembly
PredicateSignature
exact logical candidate identity
validation/admission split
RelationClaim
TypeAssertion
uncertainty preservation
claim/projection separation
evidence vs derivation lineage
tenant-scoped deterministic substrate
replay
```

И это, кстати, очень хорошая новость: мы не зря потратили столько времени на 021. **Теперь у нас есть каркас, в который можно засунуть уже существующее "мясо" вместо того, чтобы заново изобретать каждую мышцу.**
