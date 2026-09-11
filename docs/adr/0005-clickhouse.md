# ADR-0005: ClickHouse for analytics

Status: Accepted
Date: 2026-09-07

## Context

The platform produces high-volume analytic aggregates: observation counts,
throughput, useful-observation rates, discovery yield, duplicate ratios,
storage growth, per-type breakdowns, cost-per-million. These power the
operational dashboard (T068) and KPI panels (T073). Candidates: ClickHouse,
plain Postgres analytics, BigQuery, Druid.

## Decision

Use **ClickHouse** for columnar analytic/OLAP workloads.

## Rationale

- Columnar engine is ideal for high-cardinality aggregates over immutable
  observation streams.
- Cheap, fast group-by over billions of rows for the dashboard/KPI projections.
- Projections from Kafka (Flink on-ramp, ADR-0006) load analytic tables
  incrementally.
- Self-hosted, license-friendly, regionally deployable (FR-030).

## Consequences

- Analytics is another rebuildable projection (I-12); ClickHouse tables hold no
  source-of-truth data.
- Requires its own TTL/partitioning scheme tied to retention policy.
- Adds an operational component (ingestion, merges, replica).
