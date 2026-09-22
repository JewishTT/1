# Global Collection Fabric — Data-plane, Topics, Feedback, Phasing (T135)

The collection fabric (spec 001, phases B–E) extends the closed loop from the
Topology Overview. This doc records the implemented data-plane pieces, topic
taxonomy deltas, feedback-loop wiring, and the phased deployment model.

## 1. Data plane

Collection never writes blobs to the event bus (I-5). Raw bytes are
content-addressed in the object store; Kafka carries refs only.

| Piece | Implementation | Contract |
| --- | --- | --- |
| Content-addressed gate | `ObservationGate.ingest` — sha256 → `s3://…/raw/{tenant}/{ym}/{sha}` with dedup (`put_raw_dedup`) | R-08 `created`/`changed`/`unchanged`/`duplicate`; I-1 immutable after gate |
| Re-observation path | `reobservation.etag_equal` (weak/strong ETag) short-circuits a same-URI fetch; three-way split on `304`/hash-only/no-change | T101 |
| WARC archival | `build_warc`/`lint_warc`/`validate_warc` + browser-leftover capture → archival-eligible HTTP responses | T106/T107 |
| WARC range adapter | `adapt_warc` resolves `s3://…?offset=&length=` byte ranges → inner payload through the gate | T093 (CC offset/length contract) |
| Bulk historical | CC index replay (`DiscoveryReplay`, warc:// candidates) + Wayback CDX backfill, merged deterministically | T108/T121/T122 |
| Frontier | Postgres `frontier_items` — authoritative (R-02), partition-aware, ETag/digest checkpoints | R-02, T113/T119 |

A URL+payload that arrives once through a live worker and once through the
archive replay converges on **one** raw object and one observation URI — the
second path classifies `duplicate` (verified by the contract suite in
`apps/bulk-ingestion/tests/contract/test_archive_live_convergence.py`).

## 2. Topic taxonomy

Canonical event types map one-to-one to topics (`events/topics.py`): every
`observation.lifecycle` maps to `observation.{created,changed,unchanged,duplicate}`;
acquisition emits `acquisition.{assigned,request,outcome,completed,failed}`;
feedback closes the loop via `feedback.{generated,source,entity,system}`.
Consumers are idempotent on `event_id`/`observation_id`/`task_id`; DLQ and
quarantine topics are reserved (`events.dlq`, `events.quarantine`).

## 3. Feedback loops

1. **Recrawl loop**: post-TDA findings produce `feedback.generated` which seeds
   new frontier items/priorities; the scheduler's verdict mix (dispatch/defer/
   reject) throttles unbounded growth.
2. **Re-observation loop**: ETag/`previous_digest` at the gate prevents
   re-parse of unchanged content (SC-006).
3. **Region loop**: `RegionBackpressure` (GO/THROTTLE/HALT) gates the dispatcher
   per region using capacity + lag ceilings; frontier partitions are selected by
   `partition_of`/`host_partition` so a region owns its rows (T113/T119).

## 4. Phased deployment

Compose profiles (`apps/deploy/docker-compose.yml`, T136) gate the stack by
phase so the smallest runnable plane is `core`:

| Profile | Services | Phase purpose |
| --- | --- | --- |
| `core` | minio, minio-init, kafka, schema-registry, postgres, redis, temporal | data plane must-have |
| `streaming` | redpanda(+console), flink (jm/tm), nessie | durable streaming + lakehouse (phase C/D) |
| `collectors` | browsertrix | browser/engine collectors (T098) |
| `analytics` | opensearch, clickhouse, neo4j | projections/search/AI-analytics |

```bash
docker compose -f apps/deploy/docker-compose.yml \
  --profile core --profile analytics up -d
```

Multi-region rollout/storage-topology details stay in
[multi-region.md](./multi-region.md).