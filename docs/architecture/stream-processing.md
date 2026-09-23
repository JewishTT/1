# Stream Processing — the nervous system

Referenced by `apps/shared/events/bus.py` and `apps/shared/events/topics.py`.
Related: ADR-0001 (Kafka), ADR-0006 (Flink role), ADR-0005 (ClickHouse).

## The substrate

The control plane runs on one deterministic event bus (`EventBus` protocol,
`apps/shared/events/bus.py`). Phase 1 is the hermetic `MemoryEventBus` (tests and
local runs need no broker); phase 2 binds the same protocol to a Redpanda adapter —
a transport swap, never a semantic change.

Bus contract (enforced by the protocol and its tests):

- **append-only**: an assigned offset never changes;
- **deterministic offsets**: monotone per-topic counters in publish order;
- **deterministic replay**: `replay(topic)` yields records in offset order, so
  `topic + offset` rebuilds byte-identical projections (I-12);
- **refs-only** (I-5): raw blobs are rejected on publish (`MAX_INLINE_REFS`);
- **content-addressed ids**: `evt-<sha256(payload)>` when an envelope omits one —
  produce retries dedup on `event_id` (I-11).

## Topology

| Layer | Technology | Role | Where |
| --- | --- | --- | --- |
| Transport | Kafka (KRaft) / Redpanda | Topics, consumer groups, Schema Registry | compose profile `core` / `streaming` |
| Stateful operators | Flink | Temporal windows, joins, change/pattern detection, counters | `apps/projection/streams/jobs.py` (pure engines) |
| Series store | ClickHouse `ReplacingMergeTree` | `entity_series` (metric rows keyed `(tenant, entity, key, series_hash, ts)`) | `apps/control-plane/services/series_lifecycle.py` |
| Operational state | PostgreSQL 16 | investigations, frontier, decisions, entity_stream (append-only) | control-plane |
| Raw evidence | MinIO/S3 | content-addressed objects (`s3://knowledge/raw/...`) | storage layer |
| Graph / search | Neo4j, OpenSearch | current relational state; rebuildable search projection | `apps/projection` |

Flink engines are Flink-agnostic and hermetic (`TemporalWindow`, `StreamJoin`,
change detection — see `apps/projection/tests/test_streams.py`); a thin adapter
binds them to a cluster in the compose `streaming` profile (redpanda/flink/nessie).
**TDA is a time series, never a "TDA graph"**: per-window persistence features are
stored as rows (`tda.feature.series`), the adjacency stays rebuildable from events.

## Topic taxonomy (nervous-system events)

Catalog lives in `apps/shared/events/topics.py`; every type has a stable topic
(`topic_for(event_type)`). Nervous-system types (`NERVOUS_SYSTEM_EVENT_TYPES`):

| Event type | Topic | Meaning |
| --- | --- | --- |
| `cc.capture.series` | `cc_temporality` | CC capture timeline rebuilt as a series (I-12) |
| `replay.stream` | `stream` | consumer-group watermark / cursor checkpoint |
| `series.invariant` | `series` | deterministic-replay verification gate (I-12) |
| `tda.feature.series` | `tda` | TDA features emitted as time series |

Plus the entity life-stream (`entity.stream.appended`, `entity.state.projected`,
`entity.series.projected`, `hyperedge.*`) and the CC temporality lane
(`cc.plan_ready → cc.captures_pulled → cc.observations_extracted → cc.series_projected`).
Dead-letter and quarantine lanes: `events.dlq`, `events.quarantine`.

## Batch-first → stream-first

1. **Batch lane (live today)** — Common Crawl temporality v1 composes L1→L0→L1→L2
   synchronously: plan (`apps/acquisition/cc_plan.py`) → pull
   (`apps/shared/network/{cc_session,range_pull}.py` via `zero.cc_capture`) →
   normalize (`apps/acquisition/cc_extract.py`) → series
   (`services/series_lifecycle.py`); orchestrated by
   `services/cc_temporality.py` with an honest SSE event (`cc.temporality`).
   Every hop is content-addressed and idempotent; empty answers are documented
   notes, never fabricated series (I-3).
2. **Stream-first lane (next)** — the same shapes flow as events: entity life-stream
   appends and `temporality.series.updated` / `invariant.updated` payloads (refs
   only) feed Flink stateful operators, which emit `entity_series` rows and
   `tda.feature.series`; `series.invariant` gates replay equality.

## Layer 1 — the dual-direction first layer

The zero layer (`apps/zero`, spec 010) is the first layer and works in both
directions:

- **Input** (raw → parseable): harvesters/normalizers emit deterministic
  `ObservationCandidate`s (value, kind, confidence, provenance chain
  `source_module/method/raw_fields/evidence`) from already-collected data;
  enrichment adds deterministic transforms (breach/geo/tech signals) from injected
  context — offline-testable, no bare sockets, no ML.
- **Output** (data → search for the *unknown*): the `FeedbackLoop` re-classifies
  novel contacts into `ZeroLayerSeed`s (deduped, confidence-gated) emitted to
  `zero_layer.feedback_seeds` — the spout of the next harvest wave, closing
  Layer 1 ↔ discovery.

## Rebuildability rules (I-12)

- Projections (graph/search/analytics/TDA series) consume the event log and are
  rebuildable from `topic + offset`.
- `series.invariant` and content-addressed digests (`integrity_digest`,
  `series_hash`) are the verification gate: same replay ⇒ same hashes.
- Only features/derived rows are stored in ClickHouse; adjacency and raw content
  remain in Neo4j/object storage respectively.

## Status & gaps

- Hermetic bus + catalog: implemented and tested (`apps/shared/tests/`).
- CC batch lane: implemented (spec 011 phases 1–3 green); live CC gated behind
  fixture-built parquet (no binary fixtures in git).
- Flink engines: implemented, hermetic tests green; live cluster binding and
  Schema Registry registration of bus defaults (`registry.register_bus_defaults`)
  remain open.
