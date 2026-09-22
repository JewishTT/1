# Cluster 7 — Infra Data Stack · Reference Blueprint

> Часть каталога `docs/architecture/donors/`. Governing spec: `specs/009-donor-full-catalogue/spec.md`.
>
> В `donors/` есть три файла-знания (не репозитории): `сбор данных.txt`, `f.txt`, `дополнительно.txt`. `f.txt` и `дополнительно.txt` задокументированы в кластере 1 (1.1 и 1.2) — здесь фиксируется **инфраструктурный блюпринт** `сбор данных.txt` (data-driven, stream-first стек петабайтного/экзабайтного масштаба).

## 7.1 сбор данных.txt — финальный стек сбора (Redpanda → Flink → Fluss → Iceberg)

**Что это.** Сводный блюпринт data-backbone: взаимосвязанная система слоёв, где каждый слой усиливает остальные.

**Слои (как зафиксировано в файле).**
1. **Полномасштабный сбор**: Common Crawl (единственный публичный аудируемый веб-масштабный краулер, 10+ ПБ с 2008), Heritrix (Internet Archive, 400 ТБ), Apache Nutch + Hadoop (петабайтный классический краулинг).
2. **Event Transport — Redpanda (не отказываемся)**: p99 latency 1–2ms против 5–20ms у Kafka; C++ thread-per-core, без JVM GC-пауз и ZooKeeper; на 60–87% меньше узлов при той же нагрузке (кейс Teads); Kafka API-совместимость → все клиенты/коннекторы работают. Почему не Kafka 4.0/KRaft — p99-спайки до 50–200ms под нагрузкой; почему не Pulsar — 3-уровневая эксплуатационная сложность.
3. **Stream Storage — Apache Fluss (дополнение, не замена)**: колоночное хранение (аналитические запросы до 91× быстрее log-based), плотная интеграция с LakeHouse (**Iceberg/Paimon**) без ETL, production (Alibaba: 3 ПБ при 40 ГБ/с). Паттерн: Redpanda → Flink → Fluss.
4. **Потоковая обработка — Apache Flink**: де-факто стандарт; Uber — петабайты, Alibaba — 4 ПБ/день при 1 млрд TPS; **Dynamic Iceberg Sink** (динамическое создание/эволюция схем без рестарта job'а); exactly-once.
5. **Data Integration — Apache Gobblin**: lifecycle-интеграция данных (LinkedIn/PayPal production) вместо Kafka Connect на петабайтах.
6. **Хранение и индексация**: **Iceberg** (table format); **Quickwit** (S3-native поиск по ПБ: субсекундно, 10× экономия); **DeltaCAT** (exabyte lakehouse); **TernFS** (exabyte filesystem). Плюс: **DataHub** (lineage LinkedIn-scale, column-level), **Dagster** (оркестрация ML/AI, asset-based pipelines).

**Интеграция.**
- **Слой**: инфраслой платформы (deploy) + `control-plane` (оркестрация) + `projection` (аналитический store).
- **Метод**: `reference-blueprint` (подтверждение и калибровка наших инфра-решений; кода нет).
- **Что даёт**: (1) обоснование нашей шины событий как **Redpanda-совместимой** (Kafka-API): latency-профиль и операционная простота; (2) аналитический контур Flink→Fluss→Iceberg для проекций/фичстора; (3) Quickwit как кандидат для полнотекста по петабайтам; (4) DataHub/Dagster для lineage и ML-оркестрации science-батчей.
- **Как подключить**: (1) сверить deploy-манифесты с паттерном Redpanda→Flink→Fluss→Iceberg (топики/схемы — наши конвенции, не менять); (2) lineage-эмиттеры (DataHub-совместимые) из пайплайнов; (3) Dagster-подобная оркестрация GPU-батчей (BLF 4.1, GLiNER 3.3, TDA 4.2–4.4); (4) Quickwit-индекс для admission/поиска, если объёмы оправдают.
- **Philosophy-check**: блюпринт полностью согласуется с event-driven/evidence-first (immutable log + rebuildable projections) — конфликтов не обнаружено.
- **Приоритет**: **P1** (reference для инфры). **Лицензия**: текстовый блюпринт (соответствие OSS-лицензиям компонентов). **Риск**: версии/операционные детали — сверять с актуальной документацией компонентов перед внедрением.

> **Кластер 7 завершён.** Кросс-ссылки: `f.txt` → 1.1, `дополнительно.txt` → 1.2. Интеграционная карта: `09-INTEGRATION-MATRIX.md`.
