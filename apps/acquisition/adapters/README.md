# Collection Fabric — Adapters

External collection engines attach to Cognitive through this directory. Each
adapter wraps one external engine as a separate process/service behind the
`CollectionAdapter` contract (see `../contracts/`) and the Python capability
registry in `registry.py`.

## Rules (Constitution gates)

1. **Observation boundary**: adapters emit bytes + metadata only. They MUST NOT
   write to Postgres / Neo4j / OpenSearch / ClickHouse / Iceberg or emit events
   directly. One Observation Gate owns storage semantics.
2. **Capability-based selection**: register a source → declare execution class +
   capabilities → scheduler adopts it automatically. No `if source == ...`.
3. **No core edits for new engines**: onboarding is registration, not code
   changes in dispatcher/frontier.

## Proposed adapter packages

```
adapters/
├── registry.py      # capability registry + selection (T090)
├── http/            # RSS, sitemap, generic HTTP sources
├── api/             # API/feed pollers
├── commoncrawl/     # Common Crawl index (discovery reservoir) (T092)
├── warc/            # WARC/archive retrieval (T093)
├── heritrix/        # archival WARC-first collection (T097)
├── browsertrix/     # browser/JS worker pool (T098)
├── stormcrawler/    # distributed streaming crawl engine (T099)
├── nutch/           # bulk crawl backend (T100)
└── dataset/         # parquet/bulk/range-read datasets
```

Planned in phases B (T092–T096, fabric) and B2 (T097–T100, external engines).