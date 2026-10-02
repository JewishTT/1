# ADR-0026 — Redpanda is the transport runtime; Kafka is the protocol

- **Status**: Accepted
- **Date**: 2026-10-02
- **Feature**: 024-context-driven-continuous-intelligence (D1=a)
- **Supersedes**: nothing. **Closes**: the question deferred by Feature 023 as `ADR-0026, O-1` (`specs/023-acquisition-integration-searxng/plan.md:478`, `spec.md:594`).

## Context

The Constitution Technology Baseline names **Apache Kafka (KRaft)** as the event backbone. The platform's producer/consumer code (`apps/shared/events/kafka.py`) targets `KAFKA_BOOTSTRAP_SERVERS`, defaulting to `localhost:9092` — the Confluent Kafka service in the compose `core` profile.

Feature 023's directive spoke only of Redpanda, naming it in nine places, while the code had no broker-brand branch. Because Redpanda is wire-compatible, 023 satisfied its gate with a single environment variable and **explicitly deferred the permanent choice to this ADR**, recording that moving the canonical backbone to Redpanda "would contradict the Technology Baseline without a Governance decision."

Feature 024 owner decision **D1=a** makes that Governance decision: Redpanda becomes the single dev/live transport runtime; the Kafka-compatible protocol contract is retained; the baseline and every ADR that names Kafka as transport are amended to the actual architecture.

## Decision

1. **Runtime**: Redpanda is the only broker in the `core` profile. Confluent Kafka is demoted to a `legacy-kafka` profile, retained for comparison and for the duration of the ADR amendment sweep.
2. **Protocol**: unchanged. `EventEnvelope` remains 16 fields of Protocol Buffers. Nothing in this ADR alters the event contract.
3. **Pinning**: the Redpanda image is pinned by digest. An unpinned `:latest` tag in transport configuration is a defect. (Resolves the pre-existing `redpandadata/redpanda:latest`.)
4. **Baseline**: the Constitution Technology Baseline is amended from "Apache Kafka (KRaft)" to "Kafka-compatible protocol; Redpanda runtime (pinned by digest)".
5. **Semantics**: "Kafka" in this platform now names a **wire protocol**, never a specific product. Product names in code refer to the runtime; protocol names refer to the contract.

## Consequences

**Positive**
- One broker in `core`. The previous split — Kafka on `:9092` in `core`, Redpanda on `:19092` in `streaming` — meant acceptance ran against a different broker than the default configuration, and no single setting made the tests meaningful.
- Digest pinning makes transport runs reproducible, which the platform's replayability and determinism requirements need at the transport layer, not only above it.
- The wire protocol is unchanged, so no producer or consumer was rewritten.

**Costs, accepted**
- The 24 ADRs naming Kafka as transport are now imprecise. An amendment sweep is required; each ADR is reviewed individually rather than bulk-edited.
- `test_infra_connectivity.py` previously asserted against two listeners (`test_kafka_list_topics`, `test_redpanda_list_topics`). Under one broker these become two names for one listener. Both names are retained deliberately so the pre-024 test baseline stays comparable; the file documents that they are not two brokers.
- Redpanda's schema registry is served at `:18081` rather than Confluent's `:8081`. Default configuration changed; any external tooling pinned to `:8081` must be updated.

**Not changed**
- No event schema change. D5=b keeps `EventEnvelope` at 16 fields; `observed_at` and `logical_time` travel inside typed payloads under a single mandatory convention (see `contracts.md`).
- No acquisition behaviour. Runtimes are untouched.

## Alternatives rejected

**(b) Keep Kafka as the declared transport, Redpanda as a dev substitute.** Rejected: it preserves the exact split that made the pre-024 baseline ambiguous — the default configuration and the acceptance run target different brokers, and neither is the declared one.

**(c) Support both with an explicit profile matrix.** Rejected: it keeps two brokers in the codebase permanently and leaves every future test ambiguous about which one it proves. A matrix is a permanent tax for a temporary migration need.

## Verification

- `docker compose --profile core config --services` lists `redpanda` and **not** `kafka`.
- No `:latest` tag on the transport in `apps/deploy/docker-compose.yml`.
- `KafkaSettings.bootstrap_servers` defaults to `localhost:19092`.
- `test_idempotency.py`, `test_infra_connectivity.py`, and `test_redpanda_emission.py` collect and run — they did not collect before Feature 024 Phase 0.
