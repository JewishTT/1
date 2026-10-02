# Contracts — Event Timestamp Convention

**Feature**: 024 · **Tasks**: T013, T014 · **Decision**: D5=b

## Why this document exists

Feature 024 `spec.md` FR-007 and FR-008 require a logical observation time on every event that needs one, and require the distinction between transport production time and evidence logical time to be recorded.

Feature 024 D5=b resolved the route: **`EventEnvelope` is not extended.** It stays at 16 fields. `observed_at` and `logical_time` travel inside typed payloads under one mandatory convention. Adding protobuf field 17 would touch every producer and consumer while the suite carries a 106-failure baseline; the requirement is met inside payloads instead, and the envelope stays evolvable.

## The distinction

| Name | Where | Means |
|---|---|---|
| `produced_at` | `EventEnvelope` field 9 | **Transport** time: when this envelope was emitted onto the bus. Always present. Never evidence. |
| `observed_at` | typed payload, mandatory where required | **Evidence/event logical time**: when the thing the event describes actually happened or was observed. Nullable only when the event genuinely has no logical time (e.g. a transport-level signal). |
| `logical_time` | typed payload, mandatory where required | An **interval** — `{"from": ..., "to": ...}` — for events describing a span rather than an instant (validity windows, coverage periods, calibration windows). |

The rule that makes this enforceable: **`produced_at` may never be copied into a payload's `observed_at`.** Envelope time answers "when did the platform learn this"; payload time answers "when did this happen". Conflating them silently fabricates evidence, which Principle I and input.md §36.5 both forbid.

## Mandatory convention

For every event type in `apps/shared/events/topics.py`:

1. If the event describes something that occurred at a time, its payload MUST carry `observed_at` as an RFC 3339 UTC string.
2. If the event describes a span, its payload MUST carry `logical_time` with `from` and `to`.
3. If the event has no logical time, the payload MUST omit both, and the event type MUST be listed in `NO_LOGICAL_TIME` below with a reason.
4. Payload schemas MUST be registered in the Schema Registry with `observed_at` declared, so an undeclared field is a schema violation rather than a runtime surprise.
5. Timezone-naive timestamps are a defect. `datetime` values crossing this boundary MUST be tz-aware.

## Validation

`EventTimestamps.validate_payload(event_type, payload)` enforces 1–3 and raises on a `produced_at` copied into `observed_at`. It is pure, importable without a broker, and unit-tested — so the convention is checkable without standing up infrastructure.

## No-logical-time event types

Empty by default. Anything added here needs a reason in its docstring. A transport-level health signal legitimately has no evidence time; an observation-bearing event never does.

## Relationship to determinism

Context Engine state must be deterministic given the same event sequence (FR-043). `observed_at` is the **one** permitted source of wall-clock dependence, because it is recorded evidence about the world, not about the platform. Context revisions that read it must carry it through as data and never as a control-flow input.
