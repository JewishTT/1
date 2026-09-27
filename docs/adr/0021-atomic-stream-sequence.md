# ADR-0021: Atomic entity-stream sequence allocation

Status: Accepted
Date: 2026-09-25
Feature: 015-worldline-reconstruction (T091-T094, D8)

## Context

`cc_cursor_materialization` currently computes
`sequence = max(existing.sequence) + len(records) + 1` in Python after a full
`replay()` read, and the `StreamAppendRejected` recovery path recomputes it again from a
second read. This is a read-then-write race: two concurrent runs for the same entity can
read the same maximum and attempt the same sequence.

`entity_stream` enforces `(tenant_id, entity_id, sequence)` as its primary key, so the
collision surfaces as an exception and is then "recovered" by recomputing — which is the
same race again, just later.

## Decision

Introduce `entity_stream_sequence (tenant_id, entity_id, next_sequence)` and allocate a
contiguous range with a single statement executed **inside the same transaction as the
append**:

```sql
INSERT INTO entity_stream_sequence (tenant_id, entity_id, next_sequence)
VALUES (:tenant_id, :entity_id, :count)
ON CONFLICT (tenant_id, entity_id)
DO UPDATE SET next_sequence = entity_stream_sequence.next_sequence + :count
RETURNING next_sequence;
```

The returned value is the first sequence of the batch; the batch occupies
`[first, first + count)`. The client never computes a sequence. The existing primary key
stays as the final enforcement layer.

## Rationale

- `UPDATE ... RETURNING` on one counter row serializes allocation per entity with no
  table lock and no client-side read. It is the standard Postgres idiom and requires no
  extension.
- Co-locating allocation and append in one transaction means a rollback returns the range
  to the pool, preserving contiguity.
- A dedicated counter makes the invariant explicit instead of emergent from a max-scan.

## Consequences

- A concurrent same-entity append test must prove zero lost records, zero duplicates and
  zero sequence collisions; the primary key remains the backstop if counter and table ever
  diverge, so a divergence is a loud failure, not silent corruption.
- The `StreamAppendRejected` path stops recomputing sequences; it becomes a genuine
  integrity signal rather than a retry mechanism.
- One extra row per entity is written, which is negligible next to the stream itself.
