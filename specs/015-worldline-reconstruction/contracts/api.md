# API Contract: Worldline Reconstruction

**Feature**: [015-worldline-reconstruction](../spec.md) | **Date**: 2026-09-25
**Base path**: `/api/v1` | **Auth**: existing tenant resolution; every route is
tenant-scoped and cross-tenant identifiers return `404`, never another tenant's data
(FR-039, SC-013)

All responses carry `tenant_id` and `entity_id`. Endpoints returning derived history also
carry a `completeness` block, so a consumer can never mistake a partial reconstruction
for a finished one.

---

## `POST /api/v1/entities` (changed)

Creates an entity **and** its durable reconstruction request in one transaction.

Request is unchanged (`canonical_identity`, optional `label`, `aliases`,
`source_records`).

Response `202 Accepted`:

```json
{
  "entity_id": "ENT-2003",
  "tenant_id": "t-1",
  "request_id": "outbox-<hash>",
  "run_id": "run-<fingerprint>",
  "workflow_id": "materialization-ENT-2003-<fingerprint>",
  "status": "QUEUED",
  "request_state": "PENDING",
  "available_at": "2026-09-25T12:00:00+00:00"
}
```

Behavioural change: the route performs **no inline dispatch** and spawns no in-process
pipeline task. The durable request is the mechanism; the relay dispatches it. Creation
succeeds even when no worker or Temporal endpoint is reachable, because nothing about
creation depends on dispatch (FR-026, AS-015, AS-016, SC-009).

Errors: `422` for empty `canonical_identity` or a source record whose scope mismatches
the resolved tenant.

---

## `GET /api/v1/entities/{id}/coverage` (new)

The honest answer to "how far did reconstruction get".

Query: none required. Optional `run_id` to scope to one run.

```json
{
  "tenant_id": "t-1",
  "entity_id": "ENT-2003",
  "queries": {
    "total": 6, "executable": 4, "executed": 4, "unsupported": 2,
    "unsupported_reasons": [
      {"route_kind": "phone_derived", "reason": "no_provider_for_route"},
      {"route_kind": "username_derived", "reason": "no_provider_for_route"}
    ]
  },
  "partitions": {
    "total": 12, "exhausted": 9, "exhausted_no_progress": 0, "failed": 1, "open": 2
  },
  "pages": {"open": 5, "completed": 40},
  "remaining_work": 7,
  "failing_partitions": [
    {"partition": "CC-MAIN-2025-26", "status": "FAILED",
     "last_error": "HTTP 503 from index endpoint", "attempts": 5}
  ],
  "last_progress_at": "2026-09-25T12:41:07+00:00",
  "complete": false,
  "admission_counts": {"accepted": 486, "rejected": 12, "deferred": 3, "quarantined": 0},
  "publication_generation": 2,
  "stale": true
}
```

`complete` is `true` only when no frontier entry remains non-terminal and nothing failed.
It is never derived from "no exception was raised" (FR-014, FR-025, FR-038, AS-019,
AS-021).

Errors: `404` unknown entity, or entity in another tenant.

---

## `GET /api/v1/entities/{id}/queries` (new)

The executed query set, so multi-route execution is inspectable rather than asserted.

```json
{
  "tenant_id": "t-1",
  "entity_id": "ENT-2003",
  "identity_fingerprint": "<64 hex>",
  "complete": false,
  "queries": [
    {"query_id": "q-<hash>", "ordinal": 0, "route_kind": "exact_url",
     "query_value": "https://example.com/john", "match_type": "prefix",
     "provider": "common_crawl", "executable": true, "origin_refs": ["url"],
     "state": "EXHAUSTED"},
    {"query_id": "q-<hash>", "ordinal": 3, "route_kind": "phone_derived",
     "query_value": "+15550100", "provider": null, "executable": false,
     "unsupported_reason": "no_provider_for_route", "origin_refs": ["phone"],
     "state": "UNSUPPORTED"}
  ]
}
```

`state` is `PENDING`, `IN_PROGRESS`, `EXHAUSTED`, `RETRYABLE`, `FAILED` or
`UNSUPPORTED`. Unsupported routes are always present, never omitted (FR-001, FR-004,
FR-006, AS-006, AS-008, SC-001).

---

## `GET /api/v1/entities/{id}/observations` (new)

Observation level, independent of any assertion.

Query: `from`, `to`, `limit`, `offset`.

```json
{
  "tenant_id": "t-1", "entity_id": "ENT-2003", "total": 3,
  "observations": [
    {"observation_id": "OBS-CC-abc123", "level": "observation",
     "url": "https://example.com/john", "crawl": "CC-MAIN-2025-30", "page": 0,
     "locator": "crawl-data/...@1234,5678", "warc_record_id": "<urn:uuid:...>",
     "record_type": "response", "content_sha256": "<64 hex>", "byte_length": 8123,
     "observed_at": "2025-06-01T00:00:00+00:00", "digest_verified": true,
     "untrustworthy": false, "untrustworthy_reasons": [],
     "evidence_ref": "s3://knowledge/raw/cc/<sha256>",
     "admitted_assertions": 37, "rejected_assertions": 2}
  ]
}
```

An observation with zero admitted assertions is still returned, with
`admitted_assertions: 0` (FR-019, FR-020, AS-012, AS-014).

---

## `GET /api/v1/entities/{id}/assertions` (new)

Assertion level with its admission outcome. This is where a rejected claim is visible
without being part of the worldline.

Query: `decision` filter (`ACCEPT_NEW`, `ACCEPT_EXISTING`, `DEFER`, `REJECT`,
`QUARANTINE`), `from`, `to`, `limit`, `offset`.

```json
{
  "tenant_id": "t-1", "entity_id": "ENT-2003",
  "counts": {"ACCEPT_NEW": 470, "ACCEPT_EXISTING": 16, "DEFER": 3, "REJECT": 12},
  "assertions": [
    {"assertion_id": "ASR-<hash>", "level": "assertion",
     "subject": "example.com", "subject_kind": "organization",
     "predicate": "has_contact", "object": "john@example.com", "object_kind": "email",
     "valid_from": "2025-06-01T00:00:00+00:00", "valid_until": null,
     "precision": "day", "confidence": 0.87,
     "source_observation_id": "OBS-CC-abc123",
     "source_record_id": "<urn:uuid:...>",
     "admission": {"decision": "REJECT", "reason_codes": ["low_source_independence"],
                    "score_vector": {"novelty": 0.2, "support": 0.1},
                    "policy": "cc-capture-v1"},
     "produced_event": false}
  ]
}
```

`produced_event` is `false` for every non-accepted decision, which is the observable form
of admission gating (FR-017, FR-018, FR-023, SC-005).

---

## `GET /api/v1/entities/{id}/events` (new)

Temporal events derived from admitted assertions only.

Query: `from`, `to`, `limit`, `offset`.

```json
{
  "tenant_id": "t-1", "entity_id": "ENT-2003", "level": "assertion", "total": 486,
  "events": [
    {"event_id": "EVT-<hash>", "assertion_id": "ASR-<hash>",
     "subject": "example.com", "predicate": "has_contact", "object": "john@example.com",
     "interval": {"point": "2025-06-01T00:00:00+00:00", "start": null, "end": null},
     "precision": "day", "confidence": 0.87,
     "participants": [{"entity_id": "example.com", "role": "subject"}],
     "before_state": {"has_contact": null}, "after_state": {"has_contact": "john@example.com"},
     "evidence_refs": [{"observation_id": "OBS-CC-abc123", "source_id": "common_crawl"}],
     "admission": {"decision": "ACCEPT_NEW", "policy": "cc-capture-v1"},
     "projection_generation": 2}
  ]
}
```

Every event carries `assertion_id`, so an event is always traceable to the admitted claim
that produced it (FR-015, FR-016).


---

## `GET /api/v1/entities/{id}/worldline` (changed)

Existing endpoint, extended.

| Parameter | Values | Default | Meaning |
| --- | --- | --- | --- |
| `level` | `observation` \| `assertion` \| `both` | `assertion` | which timeline is returned, explicitly labelled in the response (FR-021) |
| `from`, `to` | ISO-8601 instants | none | interval filter on event time |
| `require_evidence` | bool | `true` | reject events lacking evidence references |
| `include_relations` | bool | `true` | include derived relations |
| `relation_budget` | int | server default | cap on derived relations, with labelled degradation |

Response additions to the existing worldline body:

```json
{
  "tenant_id": "t-1", "entity_id": "ENT-2003",
  "level": "assertion",
  "projection_generation": 2,
  "run_id": "run-<fingerprint>",
  "completeness": {
    "complete": false, "remaining_work": 7, "verdict": "partial",
    "failing_partitions": [{"partition": "CC-MAIN-2025-26", "status": "FAILED"}]
  },
  "stale": true,
  "stale_reason": "newer_run_incomplete",
  "degradation": null,
  "admission_counts": {"accepted": 486, "rejected": 12, "deferred": 3, "quarantined": 0},
  "events": [],
  "relations": []
}
```

- `verdict` is `complete`, `partial` or `exhausted`. `partial` whenever any frontier entry
  is non-terminal or failed (AS-002, AS-019, FR-025).
- `stale` is `true` when the returned generation is not the newest attempted one, and
  `stale_reason` names the cause. The last valid publication is still returned in that
  case (AS-020, FR-040, SC-014).
- `degradation` is non-null when a relation budget was exceeded, naming what was not
  computed rather than truncating silently (FR-036).
- With `level: "both"` the response carries `observations` and `events` as separate
  labelled collections, never interleaved (FR-021).

Errors: `404` unknown or cross-tenant entity; `422` for an unparseable instant or an
invalid `level`.

---

## `GET /api/v1/entities/{id}/materialization` (new)

Request and dispatch state for operators.

```json
{
  "tenant_id": "t-1", "entity_id": "ENT-2003",
  "request": {
    "request_id": "outbox-<hash>", "status": "DISPATCHING",
    "attempts": 2, "reclaim_count": 1, "last_outcome": "reclaimed",
    "lease_owner": "relay-1", "lease_expires_at": "2026-09-25T12:05:00+00:00",
    "available_at": "2026-09-25T12:00:00+00:00", "last_error": ""
  },
  "runs": [
    {"run_id": "run-<fingerprint>", "workflow_id": "materialization-...",
     "status": "partial", "complete": false, "generation": 2,
     "started_at": "2026-09-25T12:00:00+00:00", "finished_at": null}
  ]
}
```

Exposes lease state so a stranded dispatch is visible rather than silent (FR-027, FR-038).

---

## Endpoint summary

| Endpoint | Change | Requirements | Scenarios |
| --- | --- | --- | --- |
| `POST /entities` | changed: transactional request, no inline dispatch | FR-026, FR-030 | AS-015, AS-016, AS-017 |
| `GET /entities/{id}/coverage` | new | FR-014, FR-025, FR-038 | AS-002, AS-019, AS-021 |
| `GET /entities/{id}/queries` | new | FR-001, FR-004, FR-006 | AS-006, AS-007, AS-008, AS-009 |
| `GET /entities/{id}/observations` | new | FR-019, FR-020 | AS-012, AS-014 |
| `GET /entities/{id}/assertions` | new | FR-017, FR-018, FR-023 | AS-011 |
| `GET /entities/{id}/events` | new | FR-015, FR-021 | AS-010 |
| `GET /entities/{id}/worldline` | changed: level, completeness, staleness, degradation | FR-021, FR-025, FR-036, FR-040 | AS-002, AS-013, AS-020, AS-022, AS-024 |
| `GET /entities/{id}/materialization` | new | FR-027, FR-038 | AS-018, AS-021 |
| `GET /entities/{id}/admission` | unchanged | existing consumers | existing behaviour |

