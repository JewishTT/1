# Feature 043 — Redpanda-only event backbone and stream-path efficiency

**Intent:** Complete the already-approved Redpanda runtime decision across every supported environment. Kafka remains only the wire/client protocol name where technically accurate; Apache Kafka broker services and legacy compatibility paths are not supported runtime choices.

## Invariants (non-negotiable)
- Exactly one broker product: Redpanda, with a reviewed immutable image digest.
- One canonical bootstrap configuration shared by control plane, acquisition, interpretation, projection, CI, compose and deployment manifests.
- Existing protobuf envelope, topic catalog, partition/key contract, consumer-group semantics, schema compatibility, at-least-once delivery, durable inbox/outbox, DLQ/quarantine, replay offsets and idempotent side effects remain unchanged unless a separately versioned migration proves equivalence.
- No raw evidence bodies, credentials, or unbounded payloads in events; object storage remains the raw evidence authority.
- No acceptance test may report success unless it reads the persisted event and downstream durable projection back from the same Redpanda deployment.

## Migration work

### Runtime and configuration
- [x] Remove the Confluent Kafka broker and Confluent Schema Registry services/profile from Compose.
- [x] Remove legacy broker volume and profile references from canonical topology documentation.
- [x] Make Redpanda's built-in Kafka API and Schema Registry the sole local/CI runtime.
- [x] Remove the retired COGNITIVE_KAFKA_BROKERS compatibility environment alias.
- [ ] Sweep Helm/Kubernetes, Terraform, container entrypoints, testcontainers, fixtures, CI services, scripts and developer docs for alternate Kafka service endpoints and stale :9092/:8081 defaults.
- [ ] Add a topology contract that enumerates every supported profile and fails if a Kafka broker or second Schema Registry is present.
- [ ] Confirm all deployed environments point to managed/self-hosted Redpanda endpoints with TLS/SASL, ACLs, tenant-aware topic policy and secrets sourced from the approved secret manager.

### Client and event path
- [ ] Audit all producers/consumers for explicit delivery callbacks, bounded queues, poll/flush behavior, cancellation and graceful shutdown.
- [ ] Establish shared producer defaults: compression, batching, linger, queue bounds, idempotent producer, delivery timeout and in-flight safety; tune from measured workloads rather than guessed values.
- [ ] Establish consumer defaults: bounded poll batches, explicit offset commit only after durable effect, cooperative rebalance, heartbeat/max-poll alignment, retry budget and pause/resume backpressure.
- [ ] Centralize topic creation/partition/retention/cleanup policies and key selection; document ordering guarantees per aggregate.
- [ ] Validate schema compatibility and registration in CI against Redpanda's built-in registry; add schema evolution and rollback fixtures.
- [ ] Verify transactional outbox → broker → consumer inbox path, duplicate delivery, poison record quarantine, DLQ replay, broker restart and consumer rebalance.

### Reliability, security and optimization
- [ ] Add workload profiles and reproducible benchmark baselines for throughput, p50/p95/p99 latency, CPU, RSS, disk, backlog/lag, retry rate and end-to-end observation latency.
- [ ] Profile before optimizing: serialize once, avoid redundant protobuf/JSON conversions, reuse clients/connections, reduce avoidable database round trips, use bounded async concurrency and eliminate duplicate projection work.
- [ ] Tune partitions, replication, segment retention, compaction, batching and compression based on measured topic cardinality and replay requirements; preserve full replay and provenance.
- [ ] Add lag-aware backpressure tied to existing policy/budget controls; do not silently drop, sample or cap evidence/events.
- [ ] Add dashboards/alerts for broker health, partition skew, consumer lag, under-replicated partitions, outbox age, DLQ/quarantine volume and end-to-end freshness.
- [ ] Run load, soak, broker-failure, disk-pressure, rebalance and replay acceptance against the same Redpanda version/digest used by deployment.
- [ ] Record before/after benchmark artifacts and explain every optimization's correctness proof; no performance claim without evidence.

### Acceptance and rollout
- [ ] Run empty-database and upgrade migrations, all focused event contracts, complete Python/Rust/UI suites and full-stack source-to-report acceptance.
- [ ] Prove deterministic rebuild: event topic/partition/offset and stable event IDs reproduce the same canonical projection digest.
- [ ] Prove tenant isolation, authorization, event lineage and budget accounting remain intact under parallel load and replay.
- [ ] Update the generated platform model and ADRs; remove remaining claims that Apache Kafka is a broker/runtime.
- [ ] Production rollout: canary, dual-read verification only (never dual-write to competing brokers), monitored cutover, rollback plan and documented retirement of old broker data/credentials.

## Optimization policy
Optimize the whole critical path, not just broker throughput. Preserve source coverage, record completeness, evidence lineage, durable state transitions, replayability and security. A smaller/cheaper run that drops functionality or changes epistemic semantics is a regression, not an optimization.
