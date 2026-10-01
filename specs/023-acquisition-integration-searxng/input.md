# INPUT — Feature 021 / ACQUISITION INTEGRATION

Полномасштабное исполнительное ТЗ. Источник истины для spec/plan/tasks.
Разделы пронумерованы как в оригинале; нормативные MUST-формулировки сохранены.

**Статус:** IMPLEMENTATION DIRECTIVE
**База:** `main` репозитория `JewishTT/1`
**HEAD на момент выдачи:** `fe3eb4486fecf89574dfb78b13c3d28a51ffa04b`
**Назначение:** довести acquisition fabric от декларативного набора источников и тестовых seam-ов до фактического получения, долговременного сохранения и downstream-обработки потока наблюдений.

---

## 0. КРИТЕРИЙ ВЫПОЛНЕННОСТИ — ИСТИННЫЙ GATE

ТЗ **не считается выполненным**, если выполнено только одно или несколько из:
написаны адаптеры; зарегистрированы source definitions; проходят unit-тесты; проходят fixture-тесты; worker умеет запуститься; контейнер инструмента корректно вызывается; сообщение появилось в stdout; сообщение было отправлено в Kafka; `observation.created` существует в коде; Redpanda содержит какие-либо сообщения; downstream consumer существует, но реально ничего не обработал.

### 0.1 Единственный финальный критерий

Feature считается выполненной только после подтверждения полного runtime-path:

```
Investigation
    ↓
AcquisitionTask
    ↓
Scheduler / Dispatcher
    ↓
конкретный worker_ref + source/runtime definition
    ↓
реальный запуск внешнего источника
    ↓
реальный output source
    ↓
Capture / raw artifact
    ↓
ObjectStore
    ↓
Observation / ObservationRecord
    ↓
canonical EventEnvelope
    ↓
Redpanda
    ↓
реальный downstream consumer
    ↓
успешная обработка наблюдения
    ↓
идентифицируемый persisted result
```

Для **каждого** из пяти семейств должен существовать хотя бы один доказанный runtime trace. Минимально:

```
source start
  → task_id
  → worker_ref
  → capture_id
  → raw_ref
  → observation_id
  → event_id
  → topic
  → partition/offset
  → consumer group
  → downstream processing result
```

Все перечисленные идентификаторы должны быть доступны для forensic inspection.

---

## 1. СТРАТЕГИЯ РЕАЛИЗАЦИИ

Не создавать пять независимых acquisition systems. Нужна единая acquisition fabric с тремя runtime-семействами:

```
Investigation → AcquisitionTask → worker_ref + runtime_ref
    ├─ HttpRuntime (SearXNG)
    ├─ AirbyteRuntime (connectors)
    └─ ExternalToolRuntime (Maigret, BBOT, SpiderFoot)
                  ↓
        AcquisitionArtifact
                  ↓
        Capture → ObjectStore
                  ↓
        Observation Gate
                  ↓
             EventEnvelope
                  ↓
              Redpanda
                  ↓
     interpretation / discovery frontier
```

> **Donor projects дают runtime mechanics. Платформа сохраняет за собой semantic authority, provenance, identity, durability и admission boundaries.**

---

## 2. ЧТО ИМЕННО ИНТЕГРИРУЕТСЯ

**SearXNG** — HTTP search backend для discovery/acquisition. API поддерживает `/` и `/search`, GET/POST, `q`, `categories`, `language`, `pageno`, `time_range`, `safesearch` и output format вроде JSON; **JSON должен быть включён в конфигурации конкретного инстанса**, иначе запрос на неподдерживаемый формат может вернуть HTTP 403.

**Airbyte** — connector execution layer. Source-интерфейс: `spec()`, `check(config)`, `discover(config)`, `read(config, configured_catalog, state)`. При STDIO output идёт как поток отдельных JSONL `AirbyteMessage`. `read()` выдаёт `RECORD` и `STATE`, record messages могут быть multiplexed между несколькими streams. Docker boundary: `docker run --rm -i <image> spec|check|discover|read`.

**Maigret** — username/site discovery runtime. Async search API, `MaigretDatabase`, site filtering, `status`, `url_user`, `http_status`, `rank`, `ids_data`; `is_parsing_enabled=True` активирует профильное извлечение через `socid_extractor`.

**BBOT** — event-producing recon runtime. События имеют `type`, `id`, `uuid`, `data`/`data_json`, timestamps, parent/provenance-поля, выводятся в JSON. У BBOT есть output modules включая Kafka, но **нативный BBOT Kafka output не является каноническим EventEnvelope платформы** и не должен подключаться напрямую к canonical observation topic.

**SpiderFoot** — modular OSINT runtime. CLI: `-s TARGET -m modules -t event types -u use case -o json`; экспорт scan data в JSON поддерживается.

---

## 3. КЛЮЧЕВОЕ ТРЕБОВАНИЕ: НЕ СТРОИТЬ SEMANTIC SHORTCUTS

Ни один donor runtime не имеет права: `tool output → entity`; `tool output → relation → graph edge`; `tool output → "fact"`.

Правильный путь:
```
tool output → Capture → Observation → Interpretation
            → Mention / TypeSignal / RelationSignal / Candidate
            → Validation → Admission → Claim → Projection
```

Следовательно:
- **Maigret** `status=found` — это **наблюдение инструмента**, не Entity.
- **BBOT** `parent_chain` — это **donor provenance / derivation context**, не автоматически RelationClaim.
- **SpiderFoot** correlation event — **наблюдение / вывод самого SpiderFoot**, а не наше утверждение о мире.
- **Airbyte** `State` — control-plane checkpoint, не evidence.
- **SearXNG** search result — observation of search engine response, а не доказательство истинности содержимого target URL.

---

## 4. ТЕКУЩАЯ ТОЧКА РЕПОЗИТОРИЯ

Уже присутствуют: `apps/acquisition/stream.py`, `registry.py`, `sources/catalogue.py`, `sources/connector.py`, `sources/executor.py`; `apps/shared/domain/capture.py`, `apps/shared/events/observation_gate.py`, `kafka.py`, `topics.py`; `apps/deploy/docker-compose.yml`.

Уже существует: `Capture`; content-addressed raw storage; source catalogue; HTTP source executor; topic catalogue; protobuf `EventEnvelope`; Redpanda/Kafka path; donor catalogue integration; SpiderFoot-style connector abstractions.

**Однако runtime seam неполен.** `SourceConnector` формирует observation event как обычный Python dict, тогда как канонический backbone должен сходиться через `ObservationGate` и protobuf `EventEnvelope`. `ObservationGate` генерирует **случайный UUID-based `observation_id`**, что противоречит детерминированной реконструкции.

> Эти проблемы должны быть устранены **до того**, как пять источников будут объявлены интегрированными.

**Проверено на HEAD `fe3eb448`:** `apps/shared/events/observation_gate.py:74` содержит `observation_id = "OBS-" + uuid.uuid4().hex[:12]`; `ObservationGate`/`EventEnvelope` не вызываются из `sources/connector.py`; ни один из пяти рантаймов в `docker-compose.yml` не присутствует; каталог `apps/acquisition/runtime(s)` отсутствует; `apps/acquisition/acquisition_loop.py` отсутствует.

---

## 5. PRIMARY ACQUISITION CONTRACT

```python
@dataclass(frozen=True)
class AcquisitionArtifact:
    task_id: str
    source_id: str
    worker_ref: str

    target_uri: str
    locator: str

    body: bytes
    content_type: str | None

    fetched_at: datetime
    transport: str

    producer: str
    producer_version: str

    metadata: Mapping[str, Any]
```

Для потоковых runtime не требовать предварительного полного buffering всего запуска. Предпочтительный интерфейс:

```python
async for artifact in worker.run(task):
    await artifact_sink.accept(artifact)
```

---

## 6. CAPTURE VS OBSERVATION

```
Capture    = что физически было получено/создано runtime-ом
Observation= какой адресуемый объект/record извлечён из capture
```

| Runtime | Capture | Observation |
|---|---|---|
| SearXNG | whole JSON response for query page | `result[0]`, `result[1]`, … |
| Airbyte | connector run / ordered message stream | RECORD #0, #1, #2, … |
| Maigret | complete tool result artifact / stream | site=GitHub, site=Reddit, site=VK, … |
| BBOT | scan output | event #0, #1, #2, … |
| SpiderFoot | scan result export / event stream | event #0, #1, … |

---

## 7. RAW STORAGE

Raw bytes **никогда** не идут в Redpanda. Сохраняются в ObjectStore: `raw/{tenant}/{yyyy}/{mm}/{sha256}` или существующем эквиваленте.

Redpanda получает только: `capture_id`, `observation_id`, `raw_ref`, `locator`, `tenant_id`, `investigation_id`, `source_id`, `task_id` и прочие refs/metadata.

---

## 8. CAPTURE MODEL

Использовать существующий `Capture`. **Не создавать второй конкурентный capture model.**

Capture обязан сохранять: `tenant_id`, `source_id`, `source_family`, `target_uri`, `locator`, `content_digest`, `content_length`, `media_type`, `fetched_at`, `time_basis`, `transport`, `ingest_batch_id`, `ingest_attempt`, `recorded_by`. Capture должен быть зарегистрирован как first-class durable object.

---

## 9. НОВЫЙ RECORD-LEVEL SEAM

`ObservationGate.ingest(body=...)` достаточен для blob/capture-level ingestion, но недостаточен для record-oriented sources. Добавить второй явно выраженный путь.

**`ingest_capture`** принимает физический payload (`body`, `metadata`, `source`, `task`, `investigation`, `tenant`), создаёт `Capture`, `raw_ref` и родительский Observation/Capture record.

**`ingest_record`** не должен повторно сохранять весь blob. Принимает `capture_id`, `record_locator`, `record_digest`, `record_metadata`; создаёт адресуемый ObservationRecord.

---

## 10. RECORD LOCATOR

Locator детерминированный и воспроизводимый. Примеры:
- SearXNG: `json:results[0]`, `json:results[1]`
- Airbyte: `airbyte:message:17` или `airbyte:stream=<namespace>/<stream>:record:<sequence>`
- BBOT: `bbot:event:<message_index>`
- SpiderFoot: `spiderfoot:event:<sequence>`
- Maigret: `maigret:site:<canonical_site_name>`

Locator — provenance address, а не semantic identity.

---

## 11. DETERMINISTIC IDS

**Запрещено** использовать как основу observation identity: `uuid.uuid4()`, `datetime.now()` (как часть identity), `random`, process id, thread id, memory address.

```
OBS-{digest128(identity_schema | tenant_id | capture_id | locator | record_digest)}
```

Capture ID детерминирован согласно существующей `Capture` model. Event ID детерминирован относительно `event_type | event_version | observation_id | producer | producer_version | lifecycle`.

При replay одного и того же acquisition artifact: `capture_id == same`, `observation_id == same`, `event_id == same`, если semantic material не изменился.

---

## 12. REPLAY INVARIANT

Повторный запуск одного и того же source task на идентичном fixture/live response не должен породить логическую лавину дубликатов. Допустимы same observation ID / same content hash / same event ID при повторной delivery. Consumer обязан быть идемпотентен. **Нельзя надеяться на Kafka exactly-once.**

---

## 13. WORKER ROUTING

Capability matching недостаточно. Различать: `execution_class`, `required_capabilities`, `worker_ref`, `runtime_ref`.

```yaml
worker_ref: http
runtime_ref: searxng
```

Scheduler должен сначала разрешить **явный runtime**, а capability matching использовать как проверку совместимости.

**Запрещённая ситуация:** `BBOT task → capability=http → generic HttpWorker`. Airbyte task не должен попасть в HTTP worker.

---

## 14. SOURCE REGISTRATION MODEL

Расширить `SourceDefinition` минимально необходимыми полями: `source_id`, `name`, `enabled`, `worker_ref`, `runtime_ref`, `execution_class`, `capabilities`, `input_schema`, `output_schema`, `contact_class`, `parser / interpreter hint`, `resource_class`, `timeout`, `max_output_bytes`, `source_version`, `runtime_version`, `provenance`.

`source_id` остаётся content-addressed. `runtime_ref` определяет конкретную executable implementation.

---

## 15–23. HTTP RUNTIME — SEARXNG

### 15.1 Интеграция
`worker_ref = http`, `runtime_ref = searxng`, `execution_class = api/http`. При локальном SearXNG container: `http://searxng:8080/search`. Платформа не обращается напрямую к Google/Bing/Brave и т.п. — федерацию выполняет SearXNG.

### 16 Source definition
Минимальный request: `GET /search` с параметрами `q`, `format=json`, `pageno`, `language`, `categories`, `safesearch`, `time_range`. `q` обязателен, `pageno` начинается с `1`, JSON должен быть разрешён конфигурацией инстанса. **Не копировать YAML буквально без проверки текущего catalogue loader** — адаптировать под существующую source schema.

### 17 Health probe
До первого acquisition task доказать: `GET /config` или эквивалентный локальный probe. Подтвердить: SearXNG отвечает; JSON format enabled; `/search` доступен; хотя бы один engine включён. При отсутствии JSON → `SEARXNG_JSON_FORMAT_DISABLED`, источник не runtime-ready. Документация указывает: незадекларированный output format может давать HTTP 403.

### 18 Query contract
Task содержит `query`, `language`, `categories`, `page`, `max_pages`, `time_range`, `safesearch`. Минимум `query`. Например `site:github.com "event-driven"`. **Query — acquisition instruction, не semantic truth.**

### 19 Pagination
`HttpSourceExecutor` с фиксированным `max_pages` **не является** production implementation для SearXNG. Обеспечить `page 1, 2, 3, …` и stop condition, учитывающую **содержимое ответа**, а не просто непустой HTTP body.

Недопустимо: `HTTP 200 + body != empty → fetch next page`.
Правильно: `JSON parse → inspect result collection → continue while results remain → obey hard max_pages`.

Обязательны два предохранителя: `hard_max_pages` и `hard_runtime_budget`. Нельзя превращать неисправный pagination source в бесконечный task.

### 20 Capture semantics
Каждая HTTP response page становится durable capture. Parser/expander создаёт `OBS-001 → results[0]`, `OBS-002 → results[1]`, `OBS-003 → results[2]`. Каждая observation ссылается на `capture_id` и `locator`.

### 21 Result preservation
Не уничтожать оригинальный result object после выделения `title`, `url`, `content`, `engine`, `category`, `publishedDate`, `thumbnail`, `template`, `score` или других реально присутствующих полей. **Не invent-ить поля.** Отсутствующее поле `null` не семантическое утверждение. Unknown top-level fields остаются доступными в raw artifact.

### 22 Downstream processing
Обязателен реальный consumer: `observation.created → SearXNG observation decoder → structured observation → discovery / mention producer`. Минимально: `search result → URL candidate / document discovery candidate`, **оставаясь provenance-bound** к исходному capture (`source = SearXNG`, `observation_id`, `capture_id`, `result_locator`).

### 23 Acceptance test
Реальное `query → SearXNG → JSON → Redpanda → consumer`. Acceptance, все 15 шагов: task создан; task dispatched; searxng runtime invoked; HTTP 200; JSON parsed; ≥1 result emitted; capture stored; raw_ref exists; ≥1 observation persisted; `observation.created` в Redpanda; consumer receives; consumer fetches raw_ref; consumer resolves locator; downstream processing completes; processing record persisted.

---

## 24–38. AIRBYTE — ОСОБАЯ ВЕТКА

Airbyte **нельзя** интегрировать как «ещё один HTTP source». Airbyte — **connector execution protocol**. Нужен `AirbyteRuntime`, а не `HttpSourceExecutor + random connector URL`.

### 25 Runtime interface
```python
class AirbyteRuntime:
    async def spec(task) -> AirbyteArtifact: ...
    async def check(task) -> AirbyteArtifact: ...
    async def discover(task) -> AirbyteArtifact: ...
    async def read(task) -> AsyncIterator[AirbyteMessage]: ...
```
Работать через process/container boundary.

### 26 STDIO — первая фаза
Использовать **STDIO JSON protocol** даже при наличии socket mode: максимальная прозрачность `subprocess stdout → line parser → AirbyteMessage`, проще forensic debug. Socket mode — отдельный optimisation track, не blocker.

### 27 Process execution
Вызов соответствует `spec` / `check --config` / `discover --config` / `read --config --catalog --state`. **Запрещено** `subprocess.run(..., capture_output=True)` для потенциально большого `read()` stream. Нужен streaming stdout reader:
```python
proc = await asyncio.create_subprocess_exec(...)
async for line in proc.stdout:
    parse(line)
```

### 28 Control plane vs evidence
| Классификация | Семантика |
|---|---|
| `spec` | Control-plane metadata |
| `check` | Connectivity/credential diagnostic |
| `discover` | Catalog metadata |
| `read RECORD` | **Acquisition evidence** |
| `read STATE` | **Checkpoint / control-plane state** |
| `LOG` | Operational telemetry |
| `TRACE` | Connector runtime diagnostics |

Ни `STATE`, ни `LOG`, ни `TRACE` не должны автоматически становиться observations.

### 29 Catalog
Сохраняется отдельно как immutable run metadata: `connector_ref`, `image_digest`, `config_ref`, `catalog_ref`, `state_before_ref`, `state_after_ref`. **Не помещать секретный config в raw evidence** — secrets ссылаются на secret manager / secret refs.

### 30 Config security
**Никогда** не публиковать в `Redpanda`, `logs`, `EventEnvelope`, `Capture metadata`, `Git`: `access_token`, `api_key`, `password`, oauth refresh token, private credential material. Для provenance хранить `credential_ref`, `credential_version`, а не credential value.

### 31 Connector pinning
Не использовать бессрочно mutable tag как единственную provenance identity. Фиксировать `connector image`, `connector version`, `image digest`, `protocol version`, `runtime version` (например `airbyte/source-github:2.7.1` + `sha256:...`). Версия записывается в acquisition provenance.

### 32 Read stream
```
docker/process → stdout line → JSON decode → AirbyteMessage → switch(type)
```
Обязательно обработать `RECORD`, `STATE`, `LOG`, `TRACE` и **не падать на новых/неожиданных protocol message types**. Unknown type: `preserve raw line → quarantine / diagnostic lane → do not silently discard`.

### 33 Record normalization
Каждый `RECORD` сохраняется с `namespace`, `stream`, `data`, `emitted_at`, `sequence`, `message_index`. Записи нескольких streams могут идти вперемешку — **нельзя** делать `groupby(stream)` и предполагать сериализованный по streams input.

### 34 Identity
Observation identity строится на `capture_id | record_locator | record_digest`, а не только на содержимом record. Причина: `record A in stream X` и `record A in stream Y` могут иметь одинаковый JSON, но представлять разные observed occurrences.

### 35 State checkpointing
Порядок обязательный:
```
receive record → persist observation → acknowledge durable persistence → process state checkpoint
```
Нельзя считать `STATE` подтверждением факта, если preceding records не гарантированно durable. Иначе: `STATE persisted / records lost / next run starts after state` → **irreversible evidence gap**.

### 36 Backpressure
Stdout reader естественно flow-controlled. Нельзя `read entire stdout into RAM` и нельзя `unbounded asyncio.Queue`. Лимиты: `max buffered messages`, `max buffered bytes`, `max record bytes`, `max run bytes`, `max runtime`, `max records/run`. При превышении → `resource_limit_exceeded` с сохранением частичного run state и возможностью replay/retry.

### 37 Failure matrix
Минимум: `image_not_found`, `container_start_failed`, `spec_failed`, `check_failed`, `discover_failed`, `protocol_malformed`, `record_invalid`, `state_invalid`, `connector_runtime_failed`, `timeout`, `resource_limit_exceeded`, `network_denied`, `credential_unavailable`, `credential_rejected`. Каждое состояние должно быть наблюдаемым.

### 38 Real acceptance
`connector image resolved → spec succeeds → check succeeds → discover succeeds → catalog persisted → read starts → ≥ N real RECORD → RECORD → Capture/Observation → STATE processed correctly → observation.created into Redpanda → downstream consumer receives → consumer resolves record → processing succeeds`, где `N >= 10`. При connector, физически возвращающем меньше 10 записей, допускается `all available records >= 1`, **но причина должна быть recorded, а не замаскирована**.

### 39 Обязательный почти-базовый connector test
До произвольных enterprise connectors нужен один connector, который: запускается без ручного UI; работает в test environment; имеет deterministic source; отдаёт несколько streams или хотя бы один; выдаёт несколько RECORD; выдаёт STATE; позволяет проверить resume. Если реальный live connector требует external credentials — добавить **deterministic fixture connector как protocol-validation harness**, но затем всё равно выполнить хотя бы один настоящий connector run. Fixture доказывает correctness protocol bridge; live connector доказывает correctness integration.

---

## 40–46. GENERIC EXTERNAL TOOL RUNTIME / MAIGRET

### 40 ToolDefinition
Maigret, BBOT, SpiderFoot не должны получать по отдельному heavyweight worker stack. Нужен `ExternalToolRuntime` с декларативным `ToolDefinition`:
```yaml
tool_id: runtime: image: entrypoint: argv: input_mapping: output_mode:
record_parser: timeout: max_stdout_bytes: max_stderr_bytes: max_records:
network_policy: filesystem_policy: resource_class: version:
```

### 41 Runtime principle
`AcquisitionTask → ToolDefinition → argv/config construction → sandbox/container → stdout/event/artifact stream → parser → AcquisitionArtifact → Observation Gate`. **Donor-specific internals не протаскиваются в canonical domain.**

### 42 Maigret интеграция
Для первой production ветки использовать **isolated external-tool boundary**, даже если библиотека позволяет direct embedding. Причина: security, fault isolation, dependency isolation, version pinning, resource limits, replay. Direct Python embedding — только после успешного isolated runtime.

### 43 Input contract
Task: `username`, `id_type`, site selection/filter, `timeout`, `max sites`, `profile parsing mode`. Сохранять `canonical username` и `raw username`, но canonicalization **не должна уничтожать исходное значение**.

### 44 Output
Каждый site result: `site_name`, `status`, `url_user`, `http_status`, `rank`, `ids_data` + все дополнительные реально присутствующие поля. **Не превращать** `status.is_found()` в `entity_exists = true`.

### 45 Provenance
Observation metadata: `tool = maigret`, `tool_version`, `database_version`, `site_name`, `site_rank`, `request_username`. При proxy: `proxy_mode`, `proxy_ref` — **но не secret**. Результат с timeout/HTTP error → `observation status = failed/indeterminate`, а не `not_found`, если сам Maigret не даёт оснований для вывода `not_found`.

### 46 Live acceptance
`username → Maigret → несколько site checks → stdout/result → capture → observation(s) → Redpanda → consumer`. Acceptance: `≥1 observation`; `≥1 identifiable site result`; raw artifact exists; observation locator resolves; event visible in Redpanda; downstream parser completes. Для real external web results точность отдельных site checks не acceptance condition; acceptance condition — прохождение acquisition protocol.

---

## 47–50. BBOT

Использовать `JSON/NDJSON output`. **Не подключать** `BBOT Kafka module → canonical observation topic` напрямую: его event schema является BBOT schema, а не нашей `EventEnvelope`.

### 48 Event bridge
`BBOT event JSON → validate donor event → AcquisitionArtifact → Capture → Observation → EventEnvelope`. Минимально сохранять: `bbot event type`, `bbot event id`, `bbot uuid`, `bbot data/data_json`, `scope`, `parent`, `parent_uuid`, `timestamp`, `module`, `module_sequence`, `discovery_context`, `discovery_path`, `parent_chain` — **если присутствуют**. Не семантизировать при acquisition.

### 49 Parent chain
`parent_chain` сохраняется как donor provenance: `OBS-BBOT-EVENT-X → provenance.parent_chain → [...]`. Это не означает, что `A parent-of B` является автоматически platform RelationClaim.

### 50 Acceptance
`BBOT starts → scan completes / bounded stop → events received → at least one event persisted → raw run preserved → observation created → Redpanda event emitted → downstream consumer receives → donor event parser succeeds`. Использовать безопасный test target; scan с hard timeout.

---

## 51–55. SPIDERFOOT

### 51–52 Execution
CLI JSON boundary: `-s TARGET -o json -q ...`. Параметры задаются `ToolDefinition`, **не** hardcode-ятся в runtime. **Не использовать `shell=True`**; argv передаётся массивом `argv: list[str]`.

### 53 Output
SpiderFoot JSON **не** считать готовым platform observation. `scan / event / target / module / event type / data` → platform Observation.

### 54 Correlation
Correlation engine SpiderFoot **не должен** автоматически писать в platform graph. Правильно: `SpiderFoot correlation output → tool observation → interpretation`. Если корреляция интересна как inference artifact — сохранить как provenance-bound observation.

### 55 Acceptance
`target → SpiderFoot → JSON event stream/export → Capture → Observation(s) → Redpanda → consumer → downstream processing`. Минимум `≥1 event`, желательно `≥10` если target реально генерирует больше.

---

## 56–59. INVESTIGATION / DISPATCH / CATALOGUE

### 56 Investigation workflow
Все пять источников запускаются через единый production entrypoint `InvestigationWorkflow`, **а не** direct worker/connector/graph call. Live path обязан иметь `investigation_id`, `tenant_id`, `task_id`, `source_id`, `worker_ref`, `runtime_ref` на всём пути.

### 57 Dispatch
`AcquisitionTask → resolve worker_ref → resolve runtime_ref → validate capabilities → validate policy → execute`, а не `infer worker from capabilities` когда source уже явно определён.

### 58 Source catalogue
`apps/acquisition/sources/catalogue.py` остаётся registry/catalogue layer. YAML donor catalogue можно использовать как data source, но каждый source адаптируется к platform semantics. Нельзя разрешать donor YAML напрямую определять `Entity / Relation / Graph edge / Claim / Admission`.

### 59 Estorides catalogue
Использовать как **source corpus / donor mechanics**, не semantic authority. Запрещён перенос `HTTP → parser → relation → KG`. Source definitions полезны для source coverage, request mechanics, parser inventory, pagination patterns, tool discovery. Graph mutation из donor path запрещён.

---

## 60. DONOR REUSE RULE

**Разрешено и желательно** переиспользовать: CLI invocation, request construction, pagination, result parsing, site catalogues, event schemas, tool wrappers, retry mechanics, resource estimation.

**Нельзя переносить без адаптации**: entity semantics, claim semantics, graph mutation, identity decisions, evidence adjudication, ontology assumptions, automatic trust decisions.

---

## 61–71. ADDRESSING / UNKNOWN DATA / VERSIONS / SECURITY / REDPANDA

### 61 Content-addressing
Every persisted artifact has `sha256`. `record_digest = SHA256(canonical_json(record))`; canonical JSON с deterministic key ordering и normalized encoding.

### 62 Unknown data
Unknown/unmapped/unexpected/vendor-specific поля **не удалять**. Сохранять raw artifact, structured metadata, parser version, producer version. Если mapping unknown: `record → retained → not mapped`, а не `drop`.

### 63 Parser version
Каждый observation трассируем до `collector`, `collector_version`, `parser`, `parser_version`, `runtime_version`, `source_version`. При runtime upgrade: `same raw capture → reparse → different interpretation version` **не должно требовать повторной сетевой acquisition**.

### 64 Security boundary — HTTP
Allow/deny network policy, DNS resolution controls, SSRF protection, redirect policy, max bytes, timeout, connection limit. **Текущий legacy `acquisition_loop.py` не использовать** (проверено: отсутствует в репозитории).

### 65 Container security
Не предоставлять acquisition tool: Docker socket, host filesystem, host credentials, platform secrets, unbounded outbound network. Путь: `Acquisition Service → dedicated runner → isolated container`. **Не монтировать `/var/run/docker.sock` внутрь untrusted tool process.**

### 66 Resource governance
Каждый runtime получает `resource_class` (минимум `small`/`medium`/`large`) с `cpu`, `memory`, `runtime`, `max_output`, `max_records`, `concurrency`. Scheduler учитывает acquisition budget. **Нельзя расширять concurrency при росте backlog.** Backpressure работает в обратную сторону: `backlog ↑ → acquisition rate ↓`.

### 67 Redpanda topology
Использовать существующий canonical topic catalogue. Минимальный путь: `acquisition.request → acquisition worker → observation.created → interpretation / discovery consumer`. **Не создавать по topic на каждого donor tool** (`maigret-observations`, `bbot-observations`, `spiderfoot-observations` запрещены). Tool identity живёт в metadata/provenance.

### 68 Event envelope
Использовать существующий protobuf `EventEnvelope`. Обязательные routing fields: `event_id`, `event_type`, `event_version`, `producer`, `producer_version`, `produced_at`, `tenant_id`, `investigation_id`, `source_id`, `work_id`, `region_id`, `observation_id`. Payload: **refs only**.

### 69 Event payload
Не отправлять в payload: raw body, large JSON arrays, entire BBOT scan, entire Airbyte result stream, large SpiderFoot scan. Payload маленький и replayable: `{"capture_id": "CAP-...", "observation_id": "OBS-...", "raw_ref": "s3://...", "locator": "airbyte:message:17"}`.

### 70 Redpanda observability
Обязательно видеть: `topic`, `partition`, `offset`, `event_id`, `observation_id`, `task_id`, `consumer group`, `consumer lag`, `processing result`. Для каждого acceptance run сохранять diagnostic snapshot.

### 71 Live trace record
Каждый E2E run создаёт `integration_run_id` и trace manifest:
```json
{"integration_run_id": "...", "tenant_id": "...", "investigation_id": "...",
 "task_id": "...", "source_id": "...", "worker_ref": "...", "runtime_ref": "...",
 "runtime_version": "...", "capture_ids": [], "observation_ids": [], "event_ids": [],
 "topics": [], "consumer_group": "...", "offsets": [], "processing_results": []}
```
Trace manifest сам является operational artifact.

---

## 72–75. DEBUGGING LOOP

### 72 Обязательный iterative loop
При неуспешной интеграции работа **не прекращается** на «адаптер написан» / «тест падает из-за инфраструктуры» / «connector пока не отвечает» / «Redpanda что-то не приняла».
```
RUN → OBSERVE → CLASSIFY FAILURE → PATCH → RESTART AFFECTED COMPONENT
    → REPLAY TASK → VERIFY → RUN AGAIN
```
Loop выполняется до green acceptance либо до чётко зафиксированного инфраструктурного blocker, который действительно невозможно устранить из данного execution context.

### 73 Failure classification
Каждый failure классифицируется: `build`, `configuration`, `dependency`, `container`, `process`, `network`, `DNS`, `TLS`, `authentication`, `protocol`, `parsing`, `identity`, `storage`, `Kafka`, `schema`, `consumer`, `downstream`, `performance`, `security policy`, `determinism`. Generic «integration failed» без классификации запрещён.

### 74 Debugging evidence
На каждый failure сохранять: `task_id`, `integration_run_id`, `worker_ref`, `runtime_ref`, tool version, image digest, argv sans secrets, exit code, bounded stdout/stderr artifact, source response metadata, event IDs, Kafka topic/partition/offset, consumer error. **Secrets redact before storage.**

### 75 Redpanda-first debugging
Если worker утверждает `observation created` → проверить в Redpanda: `topic == observation`, `event_id exists`, `observation_id exists`. Event есть, downstream не обработал → `inspect consumer group / offset / lag / poison`. Event отсутствует → `inspect producer / topic routing / delivery callback / serialization`. Raw есть, event absent → `inspect ObservationGate → producer seam`. Raw отсутствует → `inspect artifact sink / ObjectStore`. Capture есть, observation нет → `inspect record expander`. Observation есть, downstream result нет → `inspect consumer / parser / downstream stage`.

---

## 76–79. NO FALSE GREEN / TEST CLASSES

### 76 No false green
Нельзя делать `xfail`, `skip`, `mock`, `monkeypatch`, fake Redpanda, fake source output **после появления реального acceptance requirement**. Допускаются unit/fixture tests, но они не заменяют live gate. Live test имеет отдельный marker `@pytest.mark.live_integration` и **не должен быть автоматически skipped** в release validation.

### 77 Offline vs live
**Offline**: deterministic, fast, fixture, no internet — для parser/protocol correctness. **Live**: real process, real container/tool, real Redpanda, real ObjectStore, real Kafka event, real consumer — для integration acceptance. Оба обязательны.

### 78 Five live scenarios
Создать `live_searxng_smoke`, `live_airbyte_smoke`, `live_maigret_smoke`, `live_bbot_smoke`, `live_spiderfoot_smoke`. Каждый запускается через standard InvestigationWorkflow.

### 79 Live scenario contract
Каждый scenario: `scenario id`, `target/query`, `source id`, `worker ref`, `runtime ref`, `expected minimum observations`, `expected topic`, `expected consumer`, `assertions`, `cleanup`.

---

## 80–84. SCENARIO DETAIL

- **80 SearXNG**: `investigation = int-searxng-smoke`, `query: "SearXNG GitHub"`, `source: searxng.search`, `worker: http`, `runtime: searxng`. Assertions: HTTP reachable; JSON response; ≥1 result; Capture; raw_ref; Observation; `observation.created`; consumer processed; discovery/result downstream.
- **81 Airbyte**: connector, гарантированно выдающий data. Assertions: spec=success; check=success; discover=success; read started; RECORD observed; STATE observed **или** explicit connector limitation recorded; Capture; Observation; Redpanda event; consumer succeeds.
- **82 Maigret**: controlled test username. Assertions: tool starts; sites checked; ≥1 result record; Capture; Observation; Redpanda; consumer. Точность site checks не acceptance condition.
- **83 BBOT**: safe bounded test target. Assertions: scan starts; event stream exists; ≥1 event; Capture; Observation; Redpanda; consumer. Hard timeout.
- **84 SpiderFoot**: bounded passive/investigative scenario. Assertions: process starts; JSON emitted; event parsed; Observation created; Redpanda event; downstream processing. Не требовать event count выше 1, если runtime/source variation делает его нестабильным.

---

## 85–86. DOWNSTREAM PROCESSING

"Observation пришла в Kafka" недостаточно. Должен существовать реальный consumer:
```
consume event → resolve observation → load raw_ref → resolve locator
→ validate observation payload → write processing result
```
(например `observation.processed` или durable processing journal).

Успешный processing оставляет machine-readable доказательство: `processing_run_id`, `observation_id`, `consumer`, `consumer_version`, `processed_at`, `status`, `derived_ref`. Допустимо `status = processed`, но обязательна ссылка на concrete result.

---

## 87–90. ROUTING / PROTOCOL / EXIT

### 87 Content router
Использовать существующий `ContentRouter`. Не создавать отдельный content classification mechanism для каждого donor. `application/json`, `text/json`, `application/x-ndjson`, `text/plain` должны иметь deterministic routing. **Не доверять одному только file extension.**

### 88 JSON / NDJSON parsers
Различать: JSON document, JSON array, NDJSON/JSONL, mixed stdout. Для Airbyte STDIO: `one JSON object = one line`. Каждая line — отдельное protocol message; официальный protocol требует именно line-delimited messages в STDIO mode.

### 89 STDERR
`stdout = data channel`, `stderr = logs/errors`. Airbyte protocol аналогично указывает, что STDERR предназначен для log messages. **Не смешивать stdout и stderr в одном parser.**

### 90 Process exit semantics
`exit_code == 0` **не гарантирует** наличие data. Success: `exit_code == 0 AND protocol valid AND expected stream/data observed`. И наоборот `exit_code != 0` **не означает**, что надо выбросить уже полученные observations. Partial data должна сохраняться.

---

## 91–100. PARTIAL RUNS / RETRY / CACHE / LIFECYCLE

- **91 Partial runs**: 100 records, crash на 101 — **не делать** `rollback all 100`. Сохраняются `partial capture`, `partial observations`, `failure marker`, `resume/replay capability`.
- **92 Retry semantics**: retry на уровне task/run, **не blind subprocess duplication**. Перед retry: `check idempotency`, `check previous partial observations`, `check connector state`, `check raw artifact`.
- **93 Airbyte resume**: `state_before` / `state_after` сохраняются, state не является observation. На retry `state_before = last durable checkpoint`, а не arbitrary current stdout tail.
- **94 SearXNG replay**: если raw response сохранён, `reparse without HTTP` должно работать — новый parser/extractor/normalization без повторного network request.
- **95 Tool versioning**: outputs provenance-bound (`producer: bbot`, `producer_version: 3.x`, `runtime_ref: bbot.default`, `parser_version: 1.x`). Изменение donor tool: `new version != old derivation`, raw evidence remains.
- **96 Determinism**: проверяется минимум на source task identity, capture identity, observation identity, record locator, canonical JSON hashing, event identity, pagination, tool result normalization. Live runs могут давать разный порядок; но **для persisted raw artifact повторный parse детерминирован**.
- **97 Sorting**: все persisted collections, являющиеся semantic projection одного raw payload, сортируются детерминированно. Нельзя полагаться на `dict insertion order from donor`, `set order`, `thread timing`, `async completion order`, если это влияет на IDs или canonical serialization.
- **98 Pagination bug class**: `pages 1..N fetched, only last page persisted` — **запрещено**. Каждая fetched page должна быть durable.
- **99 Cache correctness**: `cache key excludes params` — запрещённый donor issue. Query/params участвуют в request identity. Для SearXNG: `q`, `language`, `category`, `pageno`, `time_range`, `safesearch` входят в canonical request material. Нельзя `query A → cache hit → result of query B`.
- **100 Authenticated cache isolation**: cache key не должен позволять `tenant A credential → cached response → tenant B`. Минимум `tenant`, `source`, `credential context`, `request`.

---

## 101–111. LIFECYCLE / ERRORS / QUARANTINE / IMMUTABILITY / ISOLATION

- **101 Lifecycle**: `created`, `changed`, `unchanged`, `duplicate`, `failed` где применимо. Не путать `unchanged` с `not acquired`.
- **102 Error observations**: HTTP 4xx, connector error, tool timeout **не превращаются** в fabricated empty result. `HTTP 403` не `results=[]`, а `acquisition outcome: failed / access_denied` с сохранением evidence metadata.
- **103 SearXNG error semantics**: различать `HTTP 403 because JSON disabled`, `HTTP 429`, `HTTP 5xx`, `empty result set`, `successful search with zero results`.
- **104 Airbyte error semantics**: различать `check failed`, `read failed`, `no records`, `catalog empty`, `malformed protocol`, `connector crash`, `auth denied`, `network denied`. **`no records` не эквивалентно `connector failed`.**
- **105 Maigret error semantics**: различать `site unavailable`, `timeout`, `blocked`, `HTTP 404`, `not found`, `found`, `indeterminate`, `tool failure`. **Не collapse в binary** `found / not_found`.
- **106 BBOT/SpiderFoot error semantics**: отделять `tool process failure`, `module failure`, `target result`, `transport error`, `partial run`.
- **107 Quarantine**: malformed messages (invalid JSON, invalid AirbyteMessage, invalid BBOT event, invalid SpiderFoot record, invalid Maigret result) идут в `quarantine` с `reason`, `source`, `runtime`, `raw ref`, `line/message index`.
- **108 No auto-drop**: malformed/unknown output **не означает** `delete`. Raw artifact сохраняется для replay/debug.
- **109 Observation immutability**: после durable persistence `observation core fields` immutable. Allowed later updates: `processing status`, `derived metadata`, `review state`. **НЕ** `raw_ref`, `tenant_id`, `source_id`, `capture_id`, original locator.
- **110 Tenant isolation**: каждый `Capture`, `Observation`, `EventEnvelope`, ObjectStore key, task, run несёт tenant identity. Cross-tenant raw retrieval невозможен на основании угадываемого URI.
- **111 Investigation isolation**: `investigation_id` сохраняется во всех event envelopes. Нельзя использовать `default-tenant` / `default-investigation` в live production path для реального investigation. Fixture may use defaults only inside isolated tests.

---

## 112–121. ZERO LAYER / DISCOVERY / GRAPH / SCHEMA

- **112 Zero-layer**: пять семейств могут стать acquisition sources для zero layer, но acquisition integration **не должна повторно реализовывать** zero-layer semantic model. Правильно: `zero-layer request → acquisition task → source runtime → observation → zero-layer interpreter`, а не `source → ZeroLayerObservation directly`.
- **113 Discovery**: SearXNG естественно становится discovery source (`search result → URL candidate → frontier enqueue`), но frontier enqueue — downstream interpretation/discovery step. **SearXNG runtime сам не создаёт canonical frontier state.**
- **114 Airbyte discovery**: `discover() → catalog` является source metadata; может использоваться planner (`discover → available streams → configured catalog → read`). **Catalog не является observation of world.**
- **115 Donor events as observations**: для Maigret/BBOT/SpiderFoot `tool-produced event` — `observation of a tool's execution output`, а не raw world fact. Distinction выражается в provenance schema.
- **116 Provenance graph**: `Observation → Capture → Runtime → Source → Tool/version`; derivation `ProcessedObservation → Observation → Parser version`; evidence lineage `Claim → Evidence → Observation → Capture`. **Не смешивать evidence lineage и derivation lineage.**
- **117 Event causation**: `causation_id = input event_id`, `correlation_id = investigation/run correlation`. `observation.created(E1) → mention.created(causation_id=E1)`.
- **118 No graph write from acquisition**: acquisition code must not import/call `GraphWriter`, `GraphEdge`, `RelationClaim`, `EntityStore`, `KnowledgeGraph` для обычного acquisition path, даже если donor tool produces relationship-like output.
- **119 No direct entity resolution**: acquisition может produce `raw identifier`, `username`, `URL`, `IP`, `domain`, `email-like string`, `tool id`, но **не** `resolved Entity`. Resolution downstream.
- **120 Schema registry**: canonical event schemas registry-validated. Each new event version требует `event schema`, `version`, `producer`, `consumer compatibility` — не ad hoc JSON shape.
- **121 Backward compatibility**: если existing consumers expect v2 observation events, integration должен либо `preserve v2`, либо `add new version`, а не silently modify semantics under same version.

---

## 122–130. STORAGE / DB / IDEMPOTENCY / INFRA / TRACE

- **122 Storage schema**: если DB schema не имеет first-class capture persistence — добавить migration. Минимальные relational relationships `captures` / `observations`, где `observations.capture_id` и `observations.locator` — first-class fields. **Не засовывать всё только в generic JSONB**, если durable query/reconstruction требует structural columns.
- **123 Database idempotency**: unique constraint по deterministic identity: `capture_id unique`, `observation_id unique`, при record-level semantics дополнительно `(capture_id, locator, record_digest)`.
- **124 Objectstore idempotency**: same bytes → same sha256 → same raw object. **No overwrite.**
- **125 Redpanda idempotency**: producer delivery retry может дать duplicate delivery; consumer **обязан** deduplicate по deterministic event/observation key.
- **126 Live infrastructure**: integration environment запускается через существующий `apps/deploy/docker-compose.yml` и существующие profiles. **Не создавать вторую параллельную infrastructure stack** ради feature.
- **127 Services required**: `Postgres`, `Redis`, `ObjectStore`, `Redpanda`, `Schema/Event infrastructure`, `acquisition worker`, `ObservationGate`, `downstream consumer` + `SearXNG`, `Airbyte runtime`, `Maigret runtime`, `BBOT runtime`, `SpiderFoot runtime` для соответствующих scenarios.
- **128 Healthcheck**: перед live run `docker compose ps` и machine-readable health checks. Не начинать E2E до `Redpanda healthy` / `Postgres healthy` / `ObjectStore healthy`. Health = **capability to process, не только container status**.
- **129 Redpanda precheck**: `topic exists`, `producer can connect`, `consumer can subscribe`, `schema can serialize/deserialize`. Создать ephemeral integration consumer group для smoke tests.
- **130 Trace commands**: единая **executable** инструкция/команда для `run integration / dump task / dump capture / dump observation / inspect Kafka / inspect consumer / replay task` — не только README prose.

---

## 131–143. REPLAY / METRICS / LAG / RECONCILIATION

- **131 Task replay**: `replay(task_id)` без ручного переписывания acquisition config. Воспроизводит `worker_ref`, `runtime_ref`, `source_id`, `input`, `limits`, `tenant`, `investigation` с новым `integration_run_id`.
- **132 Raw replay**: `replay_observation(observation_id)` **не вызывает network acquisition**, читает `raw_ref` из ObjectStore.
- **133 Parser replay**: `raw capture → parser v1` и `raw capture → parser v2` без изменения source acquisition.
- **134 Metrics**: для каждого runtime — `tasks started`, `tasks completed`, `tasks failed`, `records emitted`, `observations created`, `duplicates`, `quarantine count`, `bytes fetched`, `bytes stored`, `runtime seconds`, `Kafka publish failures`, `consumer failures`.
- **135 Metrics by source**: labels `source_id`, `worker_ref`, `runtime_ref`, `producer_version`, `tenant_id`, но **не** labels с secret / raw user data.
- **136 Lag**: `consumer lag` должен быть доступен. **Acceptance run не считается green, пока event физически не обработан consumer'ом.**
- **137 Zero data loss check**: для bounded smoke известен `expected N`; проверять `source records >= N`, `observations durable >= N`, `Redpanda events >= N`, `downstream processed >= N`. Для nondeterministic live tools — `at least one` + reconciliation с explanation.
- **138 Airbyte reconciliation**: отдельно считать `TOTAL messages`, `RECORD`, `STATE`, `LOG/TRACE`. Expected `record_count > 0` и `observation_count == record_count` если ни один RECORD не отфильтрован policy layer. **STATE не входит в observation count.**
- **139 SearXNG reconciliation**: `pages fetched`, `results reported by parser`, `observations persisted`. Expected `pages >= 1`, `results >= 1`, `observations == retained result count`; duplicate policy объясняется отдельно.
- **140 Maigret reconciliation**: `sites scheduled`, `sites completed`, `results yielded`, `observations persisted`.
- **141 BBOT reconciliation**: `events seen`, `events parsed`, `events persisted`, `events published`, `events processed`.
- **142 SpiderFoot reconciliation**: `events exported`, `events parsed`, `events observed`, `events processed`.
- **143 Tool-specific resource limits**: не использовать одинаковые `all tools = 2 GB / 10m`. Maigret: `max_sites`, `max_connections`, `timeout`. Airbyte: `max records`, `max output`, `connector timeout`. BBOT: `scan timeout`, `max process/resources`. SpiderFoot: `max threads`, `runtime limit`, `output limit`. SearXNG: `max pages`, `request timeout`, `result count limit`.

---

## 144–149. NETWORK / TARGET / TIMEOUTS / PROCESSES

- **144 Network policy**: SearXNG — worker видит только internal SearXNG endpoint (federation делает SearXNG). Airbyte — network access по требованиям connector'а, но через controlled egress. Maigret/BBOT/SpiderFoot — outbound network policy **явный**; **не давать unrestricted egress «потому что tool — OSINT».**
- **145 Target policy**: tool runtimes проходят существующую policy layer. Task encodes `target`, `target_scope`, `contact level`. Acquisition layer **не должен silently bypass** operator policy.
- **146 Timeouts**: каждый runtime — `connect timeout`, `read timeout`, `overall task timeout`, `shutdown grace period`. После timeout: `SIGTERM → grace → SIGKILL` с записью результата.
- **147 Child process control**: особенно BBOT/SpiderFoot. Worker отслеживает child processes и **не оставляет orphan processes** после timeout.
- **148 stdout/stderr caps**: отдельно `max_stdout_bytes`, `max_stderr_bytes`. После превышения: `process killed` с `reason = output_limit_exceeded` либо controlled truncation если protocol безопасно это поддерживает. Raw partial output сохраняется.
- **149 Airbyte streaming parser**: stateful line reader `buffered line → UTF-8 decode → JSON decode → AirbyteMessage validation → dispatch`. Malformed line **не должен** poison весь process, если protocol позволяет продолжить read. Если connector terminally corrupt: `abort`, `quarantine`, `retain artifact`.

---

## 150–154. MANIFEST / LICENSE / MATRIX / LIVENESS

- **150 Donor version manifest**: для каждой integration runtime:
```yaml
tool: bbot
source_repository: ...
license: ...
version: ...
image: ...
digest: ...
integration_role: acquisition
adapted_components: [...]
non_transferred_semantics: [...]
known_patches: [...]
```
- **151 License/provenance**: donor code reuse must remain license-compliant, особенно для copyleft source projects. В manifest фиксировать `upstream repo`, `commit`, `license`, `copied code`, `adapted code`, `dynamic/external execution boundary`. **Без юридического «магического clean room».**
- **152 Test matrix**: для каждого из 5 runtimes — Unit, Fixture, Process, Redpanda, Live, Replay (все ✓).
- **153 Live test shall not be synthetic**: `producer.produce(fake_observation)` **не является** SearXNG acceptance. Нужны `actual HTTP request` / `actual SearXNG response`. Аналогично actual Airbyte/Maigret/BBOT/SpiderFoot process.
- **154 Required logging**: structured logs с `integration_run_id`, `task_id`, `source_id`, `worker_ref`, `runtime_ref`, `capture_id`, `observation_id`, `event_id`. Каждый log line принадлежит конкретному runtime execution.

---

## 155–159. CORRELATION / CAUSATION / TRACE EXAMPLE / ACCEPTANCE / REPORT

- **155 Correlation ID**: всё, что начинается от Investigation, несёт `correlation_id`; **не меняется** на переходе scheduler → worker → observation gate → Kafka → downstream.
- **156 Causation chain**: `investigation.started → acquisition.request → observation.created → discovery.discovered` с `E_investigation ↓ causation E_acquisition ↓ causation E_observation ↓ causation E_discovery`.
- **157 Final E2E trace example**: `INV-123 / TSK-123 / worker http / runtime searxng / GET ... / HTTP 200 sha256=... / CAP-abc / json:results[0] / OBS-def / EVT-ghi / topic observation / partition 3 / offset 812 / consumer interpretation-1 / processing processed / derived ref`.
- **158 Release acceptance command**: единый entrypoint `uv run python -m bench.run --scenario acquisition-integration` (или существующий эквивалент), который реально `prepare / healthcheck / run 5 sources / reconcile / inspect Kafka / inspect downstream / emit final report`.
- **159 Final report**: machine-readable. Success — `{"status": "PASS", "sources": {"searxng": {"tasks":1,"captures":1,"observations":12,"published":12,"processed":12}, "airbyte": {...}}}`. Failure — `{"status":"FAIL","failed_stage":"observation_gate.publish","task_id":"...","capture_id":"...","observation_id":"...","reason":"..."}`.

---

## 160. RELEASE BLOCKERS

Любое из ниже блокирует release:
```
observation_id random
event_id random for replay-sensitive events
raw artifact absent
observation without raw lineage
event without canonical EventEnvelope
tool bypasses policy
tenant information lost
investigation_id lost
consumer cannot replay
pagination loses pages
Airbyte STATE treated as evidence
donor event written directly to graph
secret appears in logs/events
live source never actually executed
Redpanda path not exercised
downstream consumer not exercised
```

---

## 161. FAILURE IS NOT A REASON TO LOWER THE ACCEPTANCE BAR

Если `SearXNG fails` — не `skip SearXNG`, а `inspect / patch / re-run`. Если `Airbyte connector fails` — не заменять fixture'ом в качестве финального решения. **Fixture остаётся protocol test. Live connector остаётся integration proof.**

---

## 162. REQUIRED ITERATIVE DEBUGGING PROCEDURE

Для каждого runtime буквально: `PHASE A Build` → `B Start infrastructure` → `C Healthcheck` → `D Start one task` → `E Inspect process` → `F Inspect raw output` → `G Inspect Capture` → `H Inspect Observation` → `I Inspect Redpanda event` → `J Inspect consumer` → `K Inspect persisted downstream result` → `L Replay` → `M Verify deterministic identity` → `N Increase workload` → `O Final acceptance`.

---

## 163–170. SCALE / GUARANTEES / REPLAY / TENANT / LIFECYCLE / VERSIONS / DETERMINISM / SORTING / PERF

- **163 Scale-up**: после первого зелёного smoke `1 task → N tasks` по resource budget. Проверить `concurrency`, `backpressure`, `ordering`, `dedup`, `Kafka lag`, `ObjectStore pressure`, `DB pressure`, `tool isolation`.
- **164 Multi-record guarantee**: первый successful run использует источник, реально выдающий несколько records, чтобы доказать отсутствие ошибки `first record only` / `last record only` / `one observation per process`. Для Airbyte `record_count > 1`; для SearXNG `results_count > 1` если engine их возвращает.
- **165 Cross-runtime replay**: `capture → record extraction → observation IDs` два раза. Ожидается same capture identity, same observation identities, same locator identities.
- **166 Cross-tenant replay**: два test tenants. Same raw bytes могут иметь same content digest, но access/control lineage остаётся tenant-scoped. **Не должно происходить `tenant A event → tenant B observation resolution`.**
- **167 Source disable/enable**: `enabled=false` без удаления definition. Scheduler не создаёт task для disabled source. Runtime ID остаётся stable.
- **168 Source version change**: изменение `runtime_version` **не должно** silently mutate old observations. Old records preserve original provenance.
- **169 Schema evolution**: при изменении tool output parser **must retain unknown data**, raw остаётся source of truth for replay.
- **170 Performance targets**: минимум `no unbounded memory`, `no runaway process`, `no Kafka backlog runaway`, `no raw-to-Kafka blob transfer`, `no O(N²) acquisition routing`.
- **171 Airbyte special performance**: `RSS remains bounded`, `stdout parser doesn't accumulate entire run`, `ObjectStore writes are streamed/bounded`, `STATE processing doesn't block indefinitely`, `Kafka publish doesn't block connector forever`.
- **172 SearXNG special performance**: `page limit`, `result count limit`, `HTTP timeout`, `parallel query limit`, `engine upstream variance`. Latency отдельных upstream engines может различаться; acquisition runtime **не должен считать variability ошибкой платформенного routing layer**.

---

## 173–189. PROCESSING CONTRACT / VERSIONING / DETERMINISM / SORTING / PAGINATION / CACHE / LIFECYCLE / ERRORS / QUARANTINE / IMMUTABILITY / ISOLATION / SCHEMA / STORAGE / IDEMPOTENCY

- **173 Observation processing contract**: consumer умеет `load observation → resolve capture → load raw → resolve locator → parse record`, а **не требует donor-specific HTTP calls**.
- **174 No refetch during interpretation**: observation consumer **не должен** говорить «URL есть, я заново схожу в интернет». Он использует **captured raw artifact**.
- **175 Discovery refetch**: если frontier решил `refetch URL` — это **новый acquisition task** и новая Capture, **не mutation старого Observation**.
- **176 Change detection**: SearXNG page changed → `new capture` + `new observation or lifecycle`, **без overwrite old capture**.
- **177 Airbyte incrementality**: `run 1 → observations → state checkpoint`, `run 2 → resumes`; проверить, что duplicate prevention не ломает legitimately new records.
- **178 Airbyte full refresh**: отдельно проверить full-refresh semantics. Expected `same source state → new acquisition observation occurrences`, а не semantic overwrite предыдущего evidence.
- **179 Maigret database version**: site database часть provenance; изменение базы фиксируется в run provenance.
- **180 BBOT module version**: event provenance сохраняет `BBOT version`, `preset/config identity`, `module identity`.
- **181 SpiderFoot module set**: сохранять `selected modules`, `use case`, `event filters`, `tool version` — иначе один и тот же CLI target не воспроизводим.
- **182 Config identity**: каждый tool run имеет deterministic `config_digest`, но secrets excluded/replaced by stable secret references.
- **183 Command identity**: `argv_normalized_digest` из normalized command **без секретов**.
- **184 No secret leakage in hashed configs**: не хэшировать plaintext secrets в manifests, если это credential fingerprint. Использовать `secret_ref`.
- **185 Acceptance report reproducible**: содержит `git commit`, `image digests`, `source version`, `runtime version`, `schema version`, `test scenario version`.
- **186 Git state**: перед live acceptance `git rev-parse HEAD`, `git status --porcelain`. «Working tree accidentally dirty» не принимается как неизвестное состояние.
- **187 Migration gate**: если необходима DB migration — `migration up → smoke → migration replay/clean environment`. **Integration green на уже мутированной локальной БД не принимается.**
- **188 Clean-stack acceptance**: финальный smoke на clean stack — `fresh DB`, `fresh Redis`, `fresh ObjectStore namespace`, `fresh Redpanda topics/consumer group`.
- **189 Replay acceptance**: после clean live run `stop downstream` → `replay Kafka events / observations` → same durable interpretation **без новой network acquisition**.

---

## 190–193. FAILURE DRILLS

- **190 Redpanda loss test**: `producer active / consumer temporarily stopped`; source emits; после запуска consumer `all observations eventually processed` без data loss.
- **191 Consumer crash test**: consumer crashes во время processing; после restart `event replayed`, `observation not duplicated semantically`.
- **192 Duplicate delivery test**: искусственно доставить один `EventEnvelope` дважды → `one semantic processing result` с idempotency evidence.
- **193 Partition/order test**: не предполагать global Kafka ordering. Ordering guarantees scoped to `key / partition`. Record identity **не должна** зависеть от incidental global ordering.

---

## 194. FINAL ACCEPTANCE MATRIX

| Runtime | Source reached | Raw captured | Observation | Redpanda | Consumer | Replay | Status |
|---|---|---|---|---|---|---|---|
| SearXNG | required | required | required | required | required | required | BLOCKED until all green |
| Airbyte | required | required | required | required | required | required | BLOCKED until all green |
| Maigret | required | required | required | required | required | required | BLOCKED until all green |
| BBOT | required | required | required | required | required | required | BLOCKED until all green |
| SpiderFoot | required | required | required | required | required | required | BLOCKED until all green |

---

## 195. WORK PACKAGES

| ID | Содержание |
|---|---|
| ACQ-01 | Canonical artifact seam: `AcquisitionArtifact` + потоковый artifact sink |
| ACQ-02 | Capture persistence: first-class `Capture` registration к реальному acquisition path |
| ACQ-03 | Observation Gate repair: random observation IDs → deterministic identity |
| ACQ-04 | EventEnvelope bridge: убрать raw event-dict publication из canonical live path |
| ACQ-05 | Record observation seam: `capture_id`, `locator`, `record_digest` |
| ACQ-06 | Worker routing: `worker_ref`, `runtime_ref` в task/dispatch/source registration path |
| ACQ-07 | SearXNG runtime: health, query, pagination, capture, record expansion |
| ACQ-08 | SearXNG JSON validation: live probe, explicit fail при отсутствии JSON support |
| ACQ-09 | Airbyte runtime: process/container runner `spec/check/discover/read` |
| ACQ-10 | Airbyte stream parser: streaming JSONL protocol bridge |
| ACQ-11 | Airbyte state checkpoint: сохранение state отдельно от evidence |
| ACQ-12 | ExternalToolRuntime: generic runtime boundary |
| ACQ-13 | Maigret definition: tool manifest + argv/input/output parser |
| ACQ-14 | BBOT definition: JSON event bridge + provenance mapping |
| ACQ-15 | SpiderFoot definition: CLI JSON bridge + event parser |
| ACQ-16 | Sandbox/resource controls: CPU/memory/runtime/stdout/stderr/network policies |
| ACQ-17 | Redpanda integration: canonical publish + event inspection |
| ACQ-18 | Downstream observation consumer: real `event → raw → locator → processing result` |
| ACQ-19 | E2E live scenarios: пять live smoke scenarios |
| ACQ-20 | Replay infrastructure: task replay + raw observation replay |
| ACQ-21 | Failure journal: machine-readable integration failure report |
| ACQ-22 | Clean-stack acceptance: run all five scenarios against fresh stack |

---

## 196. TASK EXECUTION ORDER

```
ACQ-01 → ACQ-02 → ACQ-03 → ACQ-04 → ACQ-05 → ACQ-06 → ACQ-17 → ACQ-18
ACQ-07 ─┐
ACQ-09 ─┼→ foundational runtimes
ACQ-12 ─┘
   ↓
ACQ-08, ACQ-10, ACQ-11, ACQ-13, ACQ-14, ACQ-15
   ↓
ACQ-16 → ACQ-19 → ACQ-20 → ACQ-21 → ACQ-22
```

> **Нельзя строить пять runtime integrations на неисправном Capture → ObservationGate → EventEnvelope seam.**

---

## 197. CODING AGENT BEHAVIOUR

Агент обязан: `inspect current implementation → patch smallest coherent seam → run focused tests → run process-level test → run Redpanda test → inspect real event → fix discovered failure → repeat`. **Не разрешается после первого compile green возвращаться к бумажной работе.**

---

## 198. WHAT COUNTS AS PROGRESS

`"event_id появилась в topic observation"` лучше `"adapter implemented"`, ещё лучше `"event_id E123 at partition 2 offset 847 consumed by group G123"`. **Главная единица прогресса — длина реально пройденного runtime path.**

---

## 199. FINAL PHILOSOPHY

Конечная цель интеграции не «подключить пять OSINT-инструментов», а **создать единый executable acquisition substrate, в который пять совершенно разных runtime paradigms могут выдавать реальные данные, не ломая единую модель Capture → Observation → Provenance → Replay → Interpretation.**

---

## 200. АБСОЛЮТНЫЙ DEFINITION OF DONE

Оператор может взять чистый stack и выполнить:
```
start stack → create investigation → launch SearXNG task
→ observe records in Redpanda → observe downstream processing
→ launch Airbyte task → observe RECORD stream → observe Redpanda → observe processing
→ launch Maigret task → observe site results → observe Redpanda → observe processing
→ launch BBOT task → observe event stream → observe Redpanda → observe processing
→ launch SpiderFoot task → observe JSON/event stream → observe Redpanda → observe processing
```
Затем: `kill consumer → resume → all pending observations processed`.
Затем: `replay raw observation → same observation identity → same deterministic parser result`.
Затем: `clean stack → repeat` и все пять runtime paths снова green.

**Именно эта повторяемая последовательность — окончательный критерий завершения.** Не количество классов, не число YAML definitions, не passing unit tests, не наличие контейнеров. **Факт существования реального, сохранённого, прошедшего через Redpanda и реально обработанного потока наблюдений.**

---

## 201. ОБЯЗАТЕЛЬНЫЙ ФИНАЛЬНЫЙ ARTIFACT

```
artifacts/acquisition-integration/
    run-manifest.json
    searxng.json
    airbyte.json
    maigret.json
    bbot.json
    spiderfoot.json
    redpanda-trace.json
    replay-report.json
```
`run-manifest.json` содержит: git sha, deployment identity, source versions, runtime versions, image digests, schema versions, integration run ids, task ids, capture ids, observation ids, event ids, Kafka topics, partitions, offsets, consumer groups, processing counts, replay counts.

---

## 202. ЗАПРЕТ НА ЗАВЕРШЕНИЕ ЧЕРЕЗ MOCK

Финальный `PASS` запрещён, если любой из пяти acceptance paths заменён: `mock source`, `fake subprocess`, `fake Kafka`, `fake observation`, `manual DB insert`, `manual topic publication`. Разрешены только для нижних уровней тестирования.

---

## 203. ЗАПРЕТ НА ИСКУССТВЕННЫЙ SUCCESS

Нельзя: `catch Exception → emit observation.created`; `tool failed → emit empty result`; `Kafka unavailable → mark processed`; `consumer failed → test green`. **Любая failure должна оставаться failure до её устранения.**

---

## 204. ФИНАЛЬНАЯ ФОРМУЛА

```
REAL SOURCE × REAL RUNTIME × REAL CAPTURE × REAL OBSERVATION
  × REAL REDPANDA EVENT × REAL CONSUMER × REAL DOWNSTREAM PROCESSING × REAL REPLAY
= INTEGRATION COMPLETE
```
Если хотя бы один множитель равен нулю — `FEATURE = NOT COMPLETE`.

И после появления первой реальной ошибки применяется **не пересмотр acceptance criteria**, а: `debug → patch → replay → verify → repeat`.
