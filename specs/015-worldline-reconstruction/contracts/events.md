# Event Contracts: Worldline Reconstruction

**Feature**: [015-worldline-reconstruction](../spec.md) | **Date**: 2026-09-25

Events follow the conventions already used by the repository's event hub and Kafka topic
layer. Every envelope carries `event_id`, `tenant_id`, `occurred_at`, `producer` and
`schema_version`.

**Refs only** (constitution I-5): no event carries raw WARC bytes, document text, or any
other evidence blob. Payloads carry identifiers and hashes; content is resolved through
the content-addressed object store.

## Envelope

```json
{
  "event_id": "<uuid or deterministic hash>",
  "event_type": "entity.assertion.admitted",
  "schema_version": 1,
  "tenant_id": "t-1",
  "entity_id": "ENT-2003",
  "occurred_at": "2026-09-25T12:00:03+00:00",
  "producer": "cc-cursor-materialization",
  "idempotency_key": "<deterministic, see per event>",
  "payload": {}
}
```

## Idempotency and ordering

| Concern | Rule |
| --- | --- |
| Idempotency key | Every event carries a deterministic key derived from stable identities, never from a clock or a random value. Re-delivery is a no-op. |
| Ordering | Consumers must not assume global ordering. Per-entity ordering is recoverable from the publication generation, which is monotonic. |
| Duplicates | A consumer that receives the same `idempotency_key` twice must treat the second as a no-op. |
| Failure | A consumer that cannot process an event must dead-letter it with the reason preserved; it must not silently drop it. |
| Tenant isolation | A consumer must reject any event whose `tenant_id` does not match its own scope. |

## `entity.reconstruction.requested`

Emitted in the same transaction as entity creation, so the request and the intent cannot
diverge.

```json
{
  "request_id": "outbox-<hash>",
  "run_id": "run-<fingerprint>",
  "workflow_id": "materialization-ENT-2003-<fingerprint>",
  "identity_fingerprint": "<64 hex>",
  "query_count": 6,
  "executable_query_count": 4
}
```

`idempotency_key`: `<tenant>/<entity>/<identity_fingerprint>`.
**Satisfies**: FR-026, FR-030. **Scenarios**: AS-015, AS-016, AS-017.

## `entity.observation.recorded`

Emitted once per retrieved capture, including captures that yield no admitted claim.

```json
{
  "observation_id": "OBS-CC-abc123",
  "source": "common_crawl",
  "crawl": "CC-MAIN-2025-30",
  "page": 0,
  "locator": "crawl-data/...@1234,5678",
  "warc_record_id": "<urn:uuid:...>",
  "record_type": "response",
  "content_sha256": "<64 hex>",
  "byte_length": 8123,
  "observed_at": "2025-06-01T00:00:00+00:00",
  "untrustworthy": false,
  "untrustworthy_reasons": [],
  "evidence_ref": "s3://knowledge/raw/cc/<sha256>",
  "query_ids": ["q-<hash>"]
}
```

`idempotency_key`: `<tenant>/<entity>/observation/<observation_id>`.
**Satisfies**: FR-016, FR-019, FR-020. **Scenarios**: AS-012, AS-014.

## `entity.assertion.admitted`

Emitted only for assertions whose admission decision is accepted.

```json
{
  "assertion_id": "ASR-<hash>",
  "candidate_id": "CAN-<hash>",
  "subject": "example.com",
  "predicate": "has_contact",
  "object": "john@example.com",
  "valid_from": "2025-06-01T00:00:00+00:00",
  "precision": "day",
  "confidence": 0.87,
  "decision": "ACCEPT_NEW",
  "policy": "cc-capture-v1",
  "source_observation_id": "OBS-CC-abc123"
}
```

`idempotency_key`: `<tenant>/<entity>/assertion/<assertion_id>`.
**Satisfies**: FR-017, FR-023. **Scenarios**: AS-010, AS-011.

## `entity.assertion.rejected`

Emitted for every non-accepted decision, including `DEFER` and `QUARANTINE`, with the
decision preserved in full so rejection is replayable and auditable.

```json
{
  "assertion_id": "ASR-<hash>",
  "candidate_id": "CAN-<hash>",
  "subject": "example.com",
  "predicate": "has_contact",
  "object": "john@example.com",
  "decision": "REJECT",
  "reason_codes": ["low_source_independence"],
  "score_vector": {"novelty": 0.2, "support": 0.1},
  "policy": "cc-capture-v1",
  "source_observation_id": "OBS-CC-abc123",
  "quarantined": false
}
```

`idempotency_key`: `<tenant>/<entity>/assertion/<assertion_id>`.
**Satisfies**: FR-018, FR-024. **Scenarios**: AS-011.
Rejected assertions never produce an `entity.event.emitted`.

## `entity.event.emitted`

One per admitted assertion, carrying the state transition it implies.

```json
{
  "event_id": "EVT-<hash>",
  "assertion_id": "ASR-<hash>",
  "subject": "example.com",
  "predicate": "has_contact",
  "object": "john@example.com",
  "interval": {"point": "2025-06-01T00:00:00+00:00", "start": null, "end": null},
  "precision": "day",
  "confidence": 0.87,
  "before_state": {"has_contact": null},
  "after_state": {"has_contact": "john@example.com"},
  "evidence_refs": [{"observation_id": "OBS-CC-abc123", "source_id": "common_crawl"}],
  "projection_generation": 3
}
```

`idempotency_key`: `<tenant>/<entity>/event/<event_id>`.
**Satisfies**: FR-015, FR-016, FR-022. **Scenarios**: AS-010, AS-013.

## `entity.worldline.published`

```json
{
  "run_id": "run-<fingerprint>",
  "projection_generation": 3,
  "fingerprint": "<64 hex>",
  "event_count": 486,
  "relation_count": 612,
  "admission_counts": {"accepted": 486, "rejected": 12, "deferred": 3, "quarantined": 0},
  "complete": true,
  "partitions_total": 12,
  "partitions_exhausted": 12
}
```

`idempotency_key`: `<tenant>/<entity>/publication/<generation>`.
Emitted only after the head has advanced in its transaction, so a consumer never sees a
publication that was not committed (FR-024, FR-025).

## `entity.reconstruction.partial`

```json
{
  "run_id": "run-<fingerprint>",
  "complete": false,
  "remaining_work": 7,
  "verdict": "partial",
  "budget_hit": "max_partitions",
  "failing_partitions": [
    {"partition": "CC-MAIN-2025-26", "status": "FAILED", "last_error": "HTTP 503", "attempts": 5}
  ],
  "retained_generation": 2
}
```

`idempotency_key`: `<tenant>/<entity>/partial/<run_id>`.
`budget_hit` names which budget was reached, distinguishing deliberate deferral from
failure. **Satisfies**: FR-008, FR-014, FR-025, FR-038. **Scenarios**: AS-002, AS-019.

## `entity.frontier.exhausted`

```json
{
  "query_id": "q-<hash>",
  "route_kind": "domain",
  "partition": "CC-MAIN-2025-30",
  "reason": "confirmed_empty",
  "pages_scanned": 4,
  "captures_observed": 3
}
```

`reason` is `confirmed_empty` or `no_forward_progress`; the two are never conflated
(FR-009, FR-012). `idempotency_key`: `<tenant>/<entity>/exhausted/<query_id>/<partition>`.

## Requirement coverage

| Event | Requirements |
| --- | --- |
| `entity.reconstruction.requested` | FR-026, FR-030 |
| `entity.observation.recorded` | FR-016, FR-019, FR-020 |
| `entity.assertion.admitted` | FR-017, FR-023 |
| `entity.assertion.rejected` | FR-018, FR-024 |
| `entity.event.emitted` | FR-015, FR-016, FR-022 |
| `entity.worldline.published` | FR-024, FR-025 |
| `entity.reconstruction.partial` | FR-008, FR-014, FR-025, FR-038 |
| `entity.frontier.exhausted` | FR-009, FR-012, FR-013 |

