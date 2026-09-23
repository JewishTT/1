# API Contract: Temporal Materialization

**Feature**: `014-temporal-materialization`  
**API version**: `/api/v1`  
**Status**: Design artifact; endpoints are not implemented

## Conventions

- Base prefix: `/api/v1`.
- Authentication: existing bearer-token resolver, with production identity integration replacing the current stub.
- Tenant: derived only from authenticated `TenantContext`; callers cannot select a tenant through body, path, or query parameters.
- Time: UTC RFC 3339 with explicit offsets.
- Identifiers: opaque strings; clients must not infer tenant/database ordering.
- Idempotency: mutating operations require `Idempotency-Key`.
- Errors: RFC 9457-style problem details with stable `type`, `title`, `status`, `code`, `detail`, `request_id`, and optional safe `meta`.
- Cross-tenant resource access returns the same `404` response and timing envelope as a resource that does not exist.
- Raw evidence, arbitrary source payloads, secrets, and quarantine payload bytes are never returned by default.

## Roles and capabilities

| Capability | Viewer | Analyst | Admin |
| --- | ---: | ---: | ---: |
| Read current/history/window/features/health | yes | yes | yes |
| Request rebuild | no | yes | yes |
| Review quarantine metadata | no | yes | yes |
| Replay/re-evaluate quarantine | no | governed analyst/admin | yes |
| Read audit history | no | no | yes |
| Change materialization policy/activation | no | no | yes |

Authorization is tenant-, investigation-, and resource-scoped. Entity read access still requires the caller's existing investigation/entity access.

## Endpoints

| Method and path | Purpose | Success |
| --- | --- | --- |
| `GET /api/v1/entities/{entity_id}/temporal-history` | List effective history windows | `200` |
| `GET /api/v1/entities/{entity_id}/temporal-history/at` | Resolve one event-time point in an exact source cut/revision | `200` |
| `GET /api/v1/entities/{entity_id}/temporal-history/current` | Read latest valid publication and current processing health | `200` |
| `GET /api/v1/entities/{entity_id}/temporal-history/windows/{window_start}` | Read one exact effective window | `200` |
| `GET /api/v1/entities/{entity_id}/temporal-features` | Read aligned window feature series | `200` |
| `POST /api/v1/entities/{entity_id}/temporal-materializations` | Request bounded rebuild/replay | `202` |
| `GET /api/v1/temporal-materializations/{run_id}` | Read tenant-scoped run status/safe point | `200` |
| `GET /api/v1/temporal-materializations/health` | List/aggregate tenant-scoped materialization health | `200` |
| `GET /api/v1/temporal-materializations/{run_id}/audit` | Read immutable run/publication audit | `200` |
| `GET /api/v1/temporal-materializations/quarantine` | List retained quarantine metadata | `200` |
| `GET /api/v1/temporal-materializations/quarantine/{quarantine_id}` | Read one sanitized quarantine record | `200` |
| `POST /api/v1/temporal-materializations/quarantine/{quarantine_id}/replay` | Request governed replay/re-evaluation | `202` |

An investigation-scoped alias may be added, but it must verify membership and call the same tenant/entity service. It must not create a second history implementation.

## History selection

`GET /api/v1/entities/{entity_id}/temporal-history` accepts exactly one selector mode:

| Selector | Query | Semantics |
| --- | --- | --- |
| Latest valid | omitted | Active head's last valid publication. |
| Source cut | `source_cut_id=<id>` | Exact published history for that sealed cut. |
| Publication revision | `revision=<positive integer>` | Exact immutable publication in this entity history. |
| Event-time point | `at=<RFC3339>` and either `source_cut_id` or `revision` | Window containing `at`; point cannot float to a newer cut. |

`source_cut_id` and `revision` are mutually exclusive. `at` without an exact cut/revision is rejected because a wall-clock event time alone cannot define what was known.

## History response

`GET .../temporal-history` returns:

```json
{
  "tenant_id": "tenant-a",
  "entity_id": "entity-123",
  "selector": {
    "mode": "source_cut",
    "source_cut_id": "src-...",
    "at": null
  },
  "publication_id": "pub-...",
  "history_revision": 12,
  "source_cut": {
    "source_cut_id": "src-...",
    "last_stream_sequence": 1042,
    "stream_head": "sha256:...",
    "coverage_start": "2026-01-01T00:00:00Z",
    "coverage_end": "2026-02-01T00:00:00Z",
    "source_schema_version": "entity-stream/v2"
  },
  "status": "current",
  "is_latest_valid": true,
  "completeness": "complete",
  "status_reason": null,
  "verification_fingerprint": "sha256:...",
  "windows": [],
  "next_cursor": "opaque-or-null"
}
```

A paginated empty `windows` page is valid only when a policy explicitly covers an empty range. Otherwise the endpoint returns the explicit completeness/reason fields.

## Window response

Each `windows` item contains:

```json
{
  "window_revision_id": "winrev-...",
  "revision": 3,
  "window_start": "2026-01-08T00:00:00Z",
  "window_end": "2026-01-15T00:00:00Z",
  "lifecycle": {
    "state": "growing",
    "event_count": 14,
    "events_per_period": 2.0,
    "burstiness": {
      "available": true,
      "value": 0.21,
      "reason": null
    }
  },
  "activity": [],
  "relationship_summary": {
    "neighbor_count": 3,
    "typed_summary_ref": "derived-ref-...",
    "identity_decision": null
  },
  "evidence_references": [
    {
      "type": "observation",
      "id": "obs-...",
      "content_sha256": "sha256:..."
    }
  ],
  "completeness": "complete",
  "completeness_reason": null,
  "provenance": {
    "source_record_ids": ["source-..."],
    "source_record_hashes": ["sha256:..."],
    "source_cut_id": "src-...",
    "policy_version": "temporal-policy/v1",
    "schema_version": "temporal-window/v1",
    "window_fingerprint": "sha256:..."
  }
}
```

Dormant windows remain explicit with `event_count=0`, `state=dormant`, and no fabricated relationship or feature measurement.

## Point-in-time response

`GET .../temporal-history/at` returns:

- the selected `window` object;
- the exact `publication_id` and `source_cut`;
- `is_latest_valid`;
- processing health separate from publication completeness;
- the aligned feature records for that exact window revision;
- the resolved history/window verification fingerprints.

It never returns windows admitted after the selected cut.

## Current response

`GET .../temporal-history/current` returns the same aggregate shape plus:

```json
{
  "status": "rebuilding",
  "status_reason": "rebuild run run-123 is reconciling",
  "is_latest_valid": true,
  "latest_source_cut_id": "src-newer",
  "active_publication_source_cut_id": "src-active",
  "active_run_id": "run-123",
  "age_seconds": 41,
  "last_updated_at": "2026-09-24T12:00:00Z"
}
```

The active publication remains readable while status is `rebuilding`, `delayed`, `degraded`, `quarantined`, or `incomplete`.

## Feature series response

`GET /api/v1/entities/{entity_id}/temporal-features` supports the same selectors and chronological window pagination.

Each record contains:

```json
{
  "feature_record_id": "feat-...",
  "window_revision_id": "winrev-...",
  "window_start": "2026-01-08T00:00:00Z",
  "window_end": "2026-01-15T00:00:00Z",
  "feature_name": "persistence_entropy",
  "feature_kind": "structural",
  "available": false,
  "value": null,
  "unavailable_reason": "insufficient_data",
  "sample_count": 1,
  "minimum_samples": 3,
  "structural_only": true,
  "provider": "topological-invariant/1",
  "input_fingerprint": "sha256:...",
  "source_cut_id": "src-...",
  "policy_version": "temporal-policy/v1",
  "schema_version": "temporal-feature/v1"
}
```

Every required feature key has one record per covered window. A measured zero uses `available=true` and `value=0`.

## Rebuild request

`POST /api/v1/entities/{entity_id}/temporal-materializations`

Headers:

- authenticated principal/tenant;
- `Idempotency-Key` required;
- optional existing `If-Match` policy/version selector.

Request fields:

| Field | Required | Rules |
| --- | --- | --- |
| `mode` | yes | `rebuild` or `replay`. |
| `source_cut_id` | no | Omit only to seal the latest permitted cut at admission time. |
| `policy_id` / `policy_version` | no | Omit to use the current governed policy. |
| `reason` | yes | Operator-supplied auditable reason. |
| `max_records` / `max_windows` | no | Positive values cannot exceed governed limits. |
| `investigation_id` | no | Must be accessible and relevant to the entity. |

Response `202`:

```json
{
  "run_id": "run-...",
  "status": "queued",
  "entity_id": "entity-123",
  "source_cut_id": "src-...",
  "policy_version": "temporal-policy/v1",
  "idempotency_key": "client-key",
  "created_at": "2026-09-24T12:00:00Z",
  "status_url": "/api/v1/temporal-materializations/run-..."
}
```

Repeating the same request/key returns the original run. Reusing a key with different normalized content returns `409`.

## Run response

`GET /api/v1/temporal-materializations/{run_id}` returns:

- mode/trigger, entity/investigation, actor, source cut, policy/schema versions;
- status/reason and timestamps/heartbeat;
- bounded progress and safe point;
- expected/actual window counts;
- reconciliation outcome/differences summary;
- retry-budget usage;
- active publication ID, if promotion completed;
- next permitted action/capability for the caller.

Safe points expose source/window cursors, not raw source payloads.

## Health response

`GET /api/v1/temporal-materializations/health` returns tenant-scoped aggregates and optional entity filters:

- `current`, `delayed`, `rebuilding`, `degraded`, `quarantined`, `incomplete` counts;
- latest accepted source age/lag;
- number of entities with no valid publication;
- active runs and oldest run age;
- reconciliation/fingerprint mismatch counts;
- duplicate suppression and quarantine counts;
- current/PIT query percentile summaries where available.

It must not expose another tenant's values, counts, timing, existence, or raw tenant labels.

## Quarantine response

List/get responses contain:

- quarantine/source/run IDs and tenant/entity context;
- reason code/detail, status, attempts, first/last seen;
- source identity/hash and immutable payload reference;
- append-only decision history;
- permitted replay/review action.

Raw/base64 payload bytes are never returned. Authorized review may request a separately governed object-store access flow.

## Audit response

`GET /api/v1/temporal-materializations/{run_id}/audit` returns append-only records for:

- run request/admission;
- candidate stage/reconcile;
- publication/revision/promotion;
- rejection/quarantine/replay/resolution;
- policy/access decisions.

Each record includes actor, action, reason, timestamp, tenant, entity, run, publication/revision, source cut, policy/schema versions, request ID, and safe detail. Audit access is admin-only and audited itself.

## Pagination and limits

- History windows and audit records use opaque cursor pagination with deterministic chronological/sequence order.
- Default history page size: 100 windows; maximum: 500.
- Default audit page size: 100; maximum: 500.
- Feature responses may page by window, preserving one-to-one records.
- Rebuild `max_records`, `max_windows`, input bytes, and duration are bounded before admission.
- `429` includes `Retry-After` and a stable backpressure code when run admission capacity is exhausted.

## Error responses

| HTTP | Stable code | Meaning |
| --- | --- | --- |
| `400` | `invalid_selector` | Conflicting/missing point-in-time selector. |
| `401` | `authentication_required` | Missing/invalid authentication. |
| `403` | `capability_denied` | Authenticated principal lacks required capability. |
| `404` | `history_not_found` | Entity/publication/window absent or foreign; indistinguishable. |
| `409` | `state_conflict` | Idempotency conflict, stale run, or illegal transition. |
| `422` | `validation_error` | Invalid policy/schema, timestamp, bounds, or source identity. |
| `429` | `materialization_backpressure` | Admission/processing capacity is bounded and currently exhausted. |
| `503` | `materialization_degraded` | Required projection dependency is unavailable; last valid view remains available where possible. |
| `410` | `retention_expired` | Requested historical revision/cut is no longer retained. |
| `507` | `reconciliation_incomplete` | Candidate/build storage is insufficient to prove completeness. |

Problem details must not include SQL, Kafka offsets, CH merge state, cross-tenant identifiers, secrets, or raw quarantine payloads.

## Compatibility

- Additive response fields are allowed within `v1`.
- New enum values require clients to preserve/display unknown values safely; semantic breaking changes require a new API version.
- Historical revisions are returned using their pinned schema/policy metadata even after newer readers deploy.
- The API never silently converts `source_cut`, revision, or provider unavailability into a current value.
