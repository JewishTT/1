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

`ObservationLake` now writes one immutable, content-addressed CSV object per
observation and reconstructs each partition by listing the tenant/month prefix.
This removes the shared manifest read-modify-write race. Legacy monthly manifests
remain readable and are promoted to immutable row objects before new appends.
Reconstruction verifies object hashes, row cardinality and tenant/month scope.

This is **not an Iceberg/Parquet table**: schema evolution, compaction, catalog
integration and end-to-end observation consumer wiring remain separate gates. The
immutable row writer is now concurrency-safe for distinct row identities, but that
does not mean the complete production lakehouse path is connected.


## Neo4j status: durable VALID-claim relay added; end-to-end path still gated

Migration 031 adds the durable `relation_claim.validation_record` JSONB home and
`relation_claim_projection_outbox`. The validation record and enqueue of a
`VALID` verdict commit in one Postgres transaction; the standalone
`cognitive-relation-projection-relay` claims rows with a lease and retries
after expiry. It reloads the claim under its tenant, rechecks the durable verdict,
then projects via the existing `GraphProjectionBridge`. A candidate row alone is
never graph input. A crash between Neo4j writes and the SQL completion commit
causes an at-least-once replay of deterministic IDs.

Neo4j writes now include tenant in node/edge identity and tenant-scoped traversal
requires an explicit tenant. Startup installs uniqueness constraints for projection
nodes and hyperedges. These changes address the adapter/outbox boundary; they do
**not** establish that every source reaches an explicit claim-admission call, nor
have they been demonstrated against a live Postgres + Neo4j deployment in this PR.
The full rebuild-from-canonical-claims proof remains required before calling the
whole graph projection path operationally complete.

## Remaining acceptance gate

- Persisted candidates survive redelivery with the same IDs and retain spans,
  source metadata, context and regime.
- No `relation_claim` can appear until an admission decision exists.
- Stream membership remains one row per observation/entity/extraction version.
- Immutable lake row appends are covered by concurrency and legacy-promotion tests; Iceberg/Parquet catalog and end-to-end consumer wiring remain separate acceptance gates.
- The VALID-only outbox relay is present; the explicit candidate-to-admission caller, live Postgres/Neo4j integration, and graph rebuild-from-canonical-claims proof remain open.
