# Observation-to-candidate production boundary

This note records the scope of the observation-path hardening and, just as
importantly, the systems it does **not** claim to have connected.

## Connected by this change

1. Acquisition producers, the acquisition worker and the observation consumer
   resolve their broker list through the same setting: `KAFKA_BOOTSTRAP_SERVERS`.
   `COGNITIVE_KAFKA_BROKERS` remains a compatibility fallback only.
2. The observation consumer reads immutable captured bytes, then the deterministic
   extractor and resolver run over those bytes. Tenzir remains an additive
   normalization sidecar; it does not author entity identity or relation claims.
3. `InterpretationBridge` persists relation extraction as `relation_candidate`,
   along with its content-addressed `evidence_context` and `semantic_regime`.
   Candidate extraction no longer inserts rows into `relation_claim`. The latter
   remains reserved for the separate validation/admission path.
4. The full candidate object and source reading are persisted. When the current
   extractor cannot derive a structural `PredicateSignature`, the logical ID
   remains empty and the candidate's revision ID remains addressable. A fabricated
   predicate signature is not a recovery strategy.
5. New entity-stream rows receive a deterministic `source_event_id` from
   tenant/entity/observation/extractor-version/kind. A partial unique key covers
   only nonempty event IDs, so legacy rows—including historical duplicate deliveries—
   remain intact and do not make the migration fail. Before appending, the writer
   checks for any matching historical/current row with `LIMIT 1`; a per-entity lock
   serializes sequence allocation. A redelivery of the same observation is a no-op,
   and unsuccessful canonical persistence cannot create stream membership rows.

## Lakehouse status: deliberately not represented as wired

`ObservationLake` currently writes CSV row snapshots and a shared monthly JSON
manifest. It is not an Iceberg/Parquet table and its manifest update is a
read-modify-write without compare-and-swap or a database transaction. Running it
from a multi-partition consumer would allow concurrent writers to overwrite one
another's manifest changes. The production observation path must not call it until
the catalog/manifest has an atomic concurrency contract, a replay key and a rebuild
verification test. Raw capture bytes remain in the object store and are not duplicated
into a projection as if that were the lakehouse.

## Neo4j status: projection only, still not a production writer

`Neo4jGraphStore` is a driver-injected adapter; the adapter and its settings do
not constitute a complete worker. There is no durable claim-projection checkpoint or
transactional admission outbox in this path. Candidate hypotheses must not be written
as graph facts. The next Neo4j integration needs to consume **admitted** claim
revisions, project through the existing `GraphProjectionBridge`, checkpoint progress
durably, and prove that the graph can be rebuilt from canonical records after losing
the database. Idempotent node/edge upserts alone are not a replay protocol.

## Remaining acceptance gate

- Persisted candidates survive redelivery with the same IDs and retain spans,
  source metadata, context and regime.
- No `relation_claim` can appear until an admission decision exists.
- Stream membership remains one row per observation/entity/extraction version.
- Lakehouse manifest concurrency is resolved before the lake is enabled in production.
- Neo4j has a durable admitted-claim projection path and full rebuild test before
  it is described as connected.
