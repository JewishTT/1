# COGNITIVE Documentation

Global OSINT Intelligence Platform — an evidence-backed, closed-loop intelligence
platform. Raw observations are immutable (S3), all analysis is traceable, and
findings always link back to raw evidence.

## Where to start

- [Architecture overview](architecture/overview.md)
- [Multi-region acquisition topology](architecture/multi-region.md)
- [Quickstart / validation guide](../specs/001-global-osint-platform/quickstart.md)
- Specification: `specs/001-global-osint-platform/` (plan.md, spec.md, research.md,
  data-model.md, contracts/)
- Donor-pattern integration: `specs/002-donor-pattern-integration/`
- Deterministic entity-extraction stack (spec 007): `specs/007-deterministic-entity-extraction-stack/`
  (extraction lane, parsers, offline dictionaries, contract tests)

## Design decisions (ADRs)

Architecture Decision Records capture the why behind every major choice:

- Foundations: `0001` Kafka, `0002` object storage, `0003` PostgreSQL role,
  `0004` OpenSearch, `0005` ClickHouse, `0006` Flink role, `0007` Temporal
- Knowledge layer: `0008` graph abstraction, `0009` graph backend,
  `0010` TDA architecture, `0011` event schema, `0012` provenance
- Reasoning: `0013` entity resolution, `0014` admission engine, `0015` frontier
  architecture, `0016` scheduling, `0017` recrawl strategy
- Operations: `0018` multi-region topology

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).