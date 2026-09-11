# ADR-0001: Event transport — Kafka vs alternatives

Status: Accepted
Date: 2026-09-07

## Context

The platform must move high-volume observation/candidate/assertion events
between acquisition, interpretation, admission, and projection with replay
capability, at-least-once delivery, and per-tenant partitioning. Candidates:
Kafka, RabbitMQ, NATS, AWS SQS/SNS, zeroMQ.

## Decision

Use **Apache Kafka** as the primary event transport.

## Rationale

- Time-ordered, replayable, partitioned log with per-tenant partitioning (I-5
  says Kafka is never a durable store for raw bytes, only a transport — but the
  log retains event metadata for replay/projection rebuild).
- Consumer groups enable multiple independent downstream projections and
  per-region consumers (FR-030).
- Ecosystem fit: Flink (T079), stream joins, temporal windows, all read Kafka
  natively.
- At-least-once delivery matches our idempotent projection invariant (I-11).

## Consequences

- Kafka becomes a coordination point between producers/consumers; we must keep
  it a transport only and never store blobs on it (I-5).
- Requires Kafka-aware operator knowledge and per-tenant ACL/partition setup
  (T061).
