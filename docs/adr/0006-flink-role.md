# ADR-0006: Flink's role — stateful, rebuildable projections only

Status: Accepted
Date: 2026-09-07

## Context

Some analytics/signals require genuine streaming state: temporal windows, stream
joins, live counters, change/pattern detection (T079, FR-021). We must apply
stream processing WITHOUT making it a transport or a source of truth.

## Decision

Use **Apache Flink** for stateful projections (temporal windows, joins, counters)
— never for transport, never as durable store (FR-021, I-5).

## Rationale

- Flink provides exactly-once-window/join/counter semantics with checkpointing.
- Genuine stateful jobs belong in the projection layer, rebuilt from Kafka
  event history (I-12).
- The engine stays pure/Flink-agnostic (see `apps/projection/streams/jobs.py`)
  so it runs in tests and on a real cluster behind a thin adapter.
- Stateful work is limited to FR-021 items only — everything else stays in the
  bulk/projection path.

## Consequences

- State lives in Flink (checkpointed) and is always re-derivable from Kafka.
- Adding a Flink runtime is optional (pure engine runs anywhere); a cluster
  adapter is a drop-in.
- Must guard against using Flink as a message bus — Kafka remains the transport.
