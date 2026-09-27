# Phase 1 Data Model: Worldline Reconstruction

**Feature**: [015-worldline-reconstruction](./spec.md) | **Date**: 2026-09-25
**Related**: [research.md](./research.md) (decisions D1-D14) | [plan.md](./plan.md)

All types follow the existing conventions in `apps/control-plane/db/schema.py`:
`String(n)` for bounded identifiers, `Text` for free text, `JSONB` for structured
payloads, `DateTime(timezone=True)` for instants, `Integer` for counters, `Boolean` for
flags. Every tenant-scoped table carries `tenant_id` and participates in tenant
isolation (FR-039).

## 1. Logical model

```text
EntitySearchSurface
   -> SourceQuerySet (1..n)                [derived, deterministic, no I/O]
        -> SourceQuery (executable | unsupported)
             -> ReconstructionFrontierEntry (1..n, run-independent)
                  -> MaterializationCursor (0..1 per run, run-scoped prepared output)
                       -> Observation           (1..1 per capture)
                            -> Assertion        (0..n)
                                 -> AdmissionDecision (1..1)
                                 -> TemporalEvent  (only if accepted)
                                      -> EventRelation (n..n)
                                      -> EntityStateTransition

ReconstructionRequest (1 active per entity + identity fingerprint)
   -> MaterializationRun -> publication generation
   -> CoverageReport (derived view over frontier + request + publication)
```

The frontier is the durable statement of *what work exists for this entity*. The
cursor is the durable statement of *what one run already computed*. They have different
lifetimes and are not merged (research D3).

## 2. `source_query_set` (persisted planning artifact)

The query set is deterministic and derived, but it is persisted so that a run can
report which routes it executed and so that frontier entries can reference a stable
query identity across runs.

| Column | Type | Notes |
| --- | --- | --- |
| `query_set_id` | `String(96)` PK | `qs-` + sha256(tenant, entity, canonical set)[:56] |
| `tenant_id` | `String(36)` | isolation key |
| `entity_id` | `String(64)` | owning entity |
| `identity_fingerprint` | `String(64)` | sha256 of canonical identity; ties to request uniqueness |
| `surface_digest` | `String(64)` | sha256 of the serialized `EntitySearchSurface` |
| `query_count` | `Integer` | number of queries in the set |
| `executable_count` | `Integer` | number with `executable = true` |
| `unsupported_count` | `Integer` | number declared unsupported |
| `created_at` | `DateTime(timezone=True)` | server default now() |

```sql
CREATE UNIQUE INDEX uq_source_query_set_scope
  ON source_query_set (tenant_id, entity_id, identity_fingerprint);
CREATE INDEX ix_source_query_set_tenant ON source_query_set (tenant_id);
```

## 3. `source_query`

| Column | Type | Notes |
| --- | --- | --- |
| `query_id` | `String(96)` PK | `q-` + sha256(query_set_id, route_kind, query_value)[:56] |
| `query_set_id` | `String(96)` | FK to `source_query_set` |
| `tenant_id` | `String(36)` | isolation key |
| `entity_id` | `String(64)` | owning entity |
| `ordinal` | `Integer` | deterministic order within the set |
| `route_kind` | `String(32)` | `exact_url`, `url_prefix`, `domain`, `name`, `alias`, `historical_name`, `username_derived`, `email_derived`, `phone_derived` |
| `query_value` | `String(512)` | normalized execution value |
| `match_type` | `String(16)` | `domain`, `prefix`, `exact` |
| `surt_prefix` | `String(255)` nullable | SURT normalization for domain routes |
| `provider` | `String(32)` | e.g. `common_crawl` |
| `executable` | `Boolean` | false when no registered provider serves the route |
| `unsupported_reason` | `String(64)` | `no_provider_for_route`, `normalization_failed`, `value_too_short` |
| `origin_refs` | `JSONB` | list of originating identity attribute keys, deduplicated |
| `created_at` | `DateTime(timezone=True)` | server default now() |

```sql
CREATE UNIQUE INDEX uq_source_query_identity
  ON source_query (query_set_id, route_kind, query_value);
CREATE INDEX ix_source_query_entity ON source_query (tenant_id, entity_id);
CREATE INDEX ix_source_query_executable ON source_query (tenant_id, entity_id, executable);
```

`origin_refs` is what makes FR-003 verifiable: two identity attributes normalizing to
the same route produce one row whose `origin_refs` lists both.

**Satisfies**: FR-001, FR-002, FR-003, FR-004, FR-006

## 4. `reconstruction_frontier` (the durable historical frontier)

The central new table. Unlike `materialization_cursors`, it has **no `run_id`**: it is
keyed per entity, so unexhausted work survives across runs and is the authority for the
completeness verdict (FR-007, FR-011, FR-014).

| Column | Type | Notes |
| --- | --- | --- |
| `frontier_entry_id` | `String(96)` PK | `fe-` + sha256(tenant, entity, query, partition, page)[:56] |
| `tenant_id` | `String(36)` | isolation key |
| `entity_id` | `String(64)` | owning entity |
| `query_id` | `String(96)` | FK to `source_query`; work is per route |
| `partition` | `String(64)` | archive partition, e.g. `CC-MAIN-2025-30` |
| `page` | `Integer` | page ordinal within the partition |
| `status` | `String(24)` | see state machine below |
| `attempts` | `Integer` | bounded retry counter |
| `lease_owner` | `String(128)` nullable | worker currently holding the entry |
| `lease_expires_at` | `DateTime(timezone=True)` nullable | claim lease |
| `last_page_digest` | `String(64)` | digest of the last processed page, for the no-forward-progress guard |
| `last_hit_count` | `Integer` | hits observed on the last processed page |
| `result_ref` | `String(96)` nullable | cursor id whose prepared output covers this entry |
| `last_error` | `Text` | truncated error text |
| `created_at` | `DateTime(timezone=True)` | server default now() |
| `updated_at` | `DateTime(timezone=True)` | server default now(), onupdate now() |
| `exhausted_at` | `DateTime(timezone=True)` nullable | set when a terminal exhausted state is reached |
| `completed_at` | `DateTime(timezone=True)` nullable | set on terminal completion of the entry |

```sql
CREATE UNIQUE INDEX uq_reconstruction_frontier_unit
  ON reconstruction_frontier (tenant_id, entity_id, query_id, partition, page);
CREATE INDEX ix_reconstruction_frontier_ready
  ON reconstruction_frontier (tenant_id, entity_id, status, partition, page);
CREATE INDEX ix_reconstruction_frontier_lease
  ON reconstruction_frontier (status, lease_expires_at);
CREATE INDEX ix_reconstruction_frontier_coverage
  ON reconstruction_frontier (tenant_id, entity_id, partition, status);
```

### State machine

```text
PENDING в”Ђв”Ђclaimв”Ђв”Ђ> IN_PROGRESS в”Ђв”Ђresultsв”Ђв”Ђ> PENDING (next page enqueued)
                        в”‚  в”‚
                        в”‚  в”њв”Ђв”Ђconfirmed emptyв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ> EXHAUSTED
                        в”‚  в”њв”Ђв”Ђno forward progressв”Ђв”Ђв”Ђв”Ђ> EXHAUSTED_NO_PROGRESS
                        в”‚  в””в”Ђв”Ђtransient error, attempts < maxв”Ђв”Ђ> RETRYABLE
                        в”‚  в””в”Ђв”Ђattempts exhaustedв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ> FAILED
                        в””в”Ђв”Ђlease expiryв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ> PENDING
```

Terminal states for scheduling purposes: `EXHAUSTED`, `EXHAUSTED_NO_PROGRESS`, `FAILED`.
`EXHAUSTED` is the only one that asserts the partition was proven empty, and coverage
reporting must distinguish it from the other two (research D5, FR-009).

`EXHAUSTED_NO_PROGRESS` exists because a provider that ignores the page parameter would
otherwise loop forever; it is terminal but it is not proof of absence (FR-012).

**Satisfies**: FR-007, FR-008, FR-009, FR-010, FR-011, FR-012, FR-013, FR-014

## 5. `materialization_outbox` changes (reconstruction request)

Existing columns are retained. Added:

| Column | Type | Notes |
| --- | --- | --- |
| `identity_fingerprint` | `String(64)` | sha256 of canonical identity; part of the uniqueness rule |
| `lease_owner` | `String(128)` nullable | relay instance holding the claim |
| `lease_expires_at` | `DateTime(timezone=True)` nullable | claim lease; expired leases are reclaimable |
| `reclaim_count` | `Integer` | how many times an expired claim was reclaimed |
| `last_outcome` | `String(32)` | `dispatched`, `failed`, `reclaimed` |

New indexes:

```sql
CREATE UNIQUE INDEX uq_materialization_outbox_active
  ON materialization_outbox (tenant_id, entity_id, identity_fingerprint)
  WHERE status IN ('PENDING', 'DISPATCHING', 'FAILED');
CREATE INDEX ix_materialization_outbox_lease
  ON materialization_outbox (status, lease_expires_at);
```

The partial unique index is what guarantees FR-017 (one active request per entity and
identity fingerprint) at the database level rather than by a check-then-insert in
application code, which would race. `claim_ready` gains the predicates
`available_at <= now()` and `(status = 'DISPATCHING' AND lease_expires_at < now())`,
both index-supported (FR-027, FR-028).

**Satisfies**: FR-026, FR-027, FR-028, FR-030

## 6. `entity_stream_sequence` (atomic sequence allocation)

| Column | Type | Notes |
| --- | --- | --- |
| `tenant_id` | `String(36)` | part of PK |
| `entity_id` | `String(64)` | part of PK |
| `next_sequence` | `Integer` | next value to hand out |
| `updated_at` | `DateTime(timezone=True)` | server default now(), onupdate now() |

Allocation is one statement, executed inside the same transaction as the append:

```sql
INSERT INTO entity_stream_sequence (tenant_id, entity_id, next_sequence)
VALUES (:tenant_id, :entity_id, :count)
ON CONFLICT (tenant_id, entity_id)
DO UPDATE SET next_sequence = entity_stream_sequence.next_sequence + :count
RETURNING next_sequence;
```

The returned value is the first sequence of the batch; the batch occupies
`[first, first + count)`. A rollback returns the range because the counter update is part
of the same transaction. This removes the client-side `max(sequence) + 1` read that is
racy under concurrent runs (research D8).

**Satisfies**: FR-031, FR-032

## 7. Stream record kinds

The existing `entity_stream` table is reused unchanged; only the `kind` values and
payload shapes are added. All payloads carry **refs only** (constitution I-5): raw WARC
bytes stay in the content-addressed object store and are reachable via `observation_id`.

### 7.1 `cc.capture` (retained, compatibility)

Written as before with the full capture payload nested under `interpretation`. Existing
consumers keep working. No longer the unit the worldline folds over.

### 7.2 `cc.observation` (new)

One row per retrieved capture, written **always**, including when no claim is admitted.

```json
{
  "level": "observation",
  "observation_id": "OBS-CC-<24 hex>",
  "source": "common_crawl",
  "url": "https://example.com/page",
  "locator": "crawl-data/.../warc/...@offset,length",
  "crawl": "CC-MAIN-2025-30",
  "page": 0,
  "warc_record_id": "<urn:uuid:...>",
  "record_type": "response",
  "content_sha256": "<64 hex>",
  "byte_length": 12345,
  "observed_at": "2025-06-01T00:00:00+00:00",
  "digest_verified": true,
  "untrustworthy": false,
  "untrustworthy_reasons": [],
  "query_ids": ["q-<hash>"],
  "evidence_ref": "s3://knowledge/raw/cc/<sha256>"
}
```

Identity: `OBS-` + a deterministic suffix derived from the WARC record id, falling back
to the content hash when the record has none.

### 7.3 `entity.assertion` (new)

One row per extracted claim. Written for every claim regardless of decision.

```json
{
  "level": "assertion",
  "assertion_id": "ASR-<hash>",
  "subject": "example.com",
  "subject_kind": "organization",
  "predicate": "has_contact",
  "object": "john@example.com",
  "object_kind": "email",
  "valid_from": "2025-06-01T00:00:00+00:00",
  "valid_until": null,
  "precision": "day",
  "confidence": 0.87,
  "candidate_id": "CAN-<hash>",
  "source_observation_id": "OBS-CC-<24 hex>",
  "source_record_id": "<warc record id>",
  "admission": {
    "decision": "ACCEPT_NEW",
    "reason_codes": [],
    "score_vector": {},
    "policy": "cc-capture-v1"
  }
}
```

`assertion_id` is a hash over canonicalized `(subject, predicate, object, valid_from,
source_observation_id)`, so the same claim from the same observation is idempotent while
the same claim observed twice remains two distinct assertions (FR-016, FR-018).

### 7.4 `entity.event` (new)

One row per **admitted** assertion only.

```json
{
  "level": "event",
  "event_id": "EVT-<hash>",
  "assertion_id": "ASR-<hash>",
  "subject": "example.com",
  "predicate": "has_contact",
  "object": "john@example.com",
  "interval": {"point": "2025-06-01T00:00:00+00:00", "start": null, "end": null},
  "precision": "day",
  "confidence": 0.87,
  "participants": [{"entity_id": "example.com", "role": "subject"}],
  "before_state": {"has_contact": null},
  "after_state": {"has_contact": "john@example.com"},
  "evidence_refs": [{"observation_id": "OBS-CC-<24 hex>", "source_id": "common_crawl"}],
  "admission": {"decision": "ACCEPT_NEW", "policy": "cc-capture-v1"},
  "projection_generation": 3
}
```

`event_id` hashes `(assertion_id, interval, projection_generation)` so a rebuild under a
new generation produces new ids while a replay under the same generation is a no-op.

**Satisfies**: FR-015, FR-016, FR-017, FR-018, FR-019, FR-020, FR-021, FR-022, FR-023, FR-024

## 8. Relation derivation structures

Relations are a **rebuildable projection** (constitution III), not authoritative state.
They are derived per request from the accepted event set, so the interval index and
ordered adjacency are built in memory per request rather than persisted. What is
persisted is the derivation basis needed to reproduce them: each event's canonical order
key, interval bounds and precision, all of which live in the `entity.event` payload.

In-memory structures built per request:

| Structure | Purpose | Replaces |
| --- | --- | --- |
| `events_sorted` | single sort by canonical order key; walking it yields `precedes`/`follows` | nested pair loop over all events |
| `sweep_active` | active interval set closed on interval end; yields `overlaps` | pair loop over all event pairs |
| `cause_index` | map of record id **and** event id to event, for declared causes | repeated linear scans |

The retained pairwise implementation stays in the module as a reference oracle for
equivalence testing and is not removed (research D11, FR-035).

**Satisfies**: FR-034, FR-035, FR-036, FR-037

## 9. Coverage report

Not a table: a derived read model assembled from `reconstruction_frontier`,
`materialization_outbox` and the current publication. Assembled per request so it can
never disagree with its sources.

| Field | Source | Meaning |
| --- | --- | --- |
| `entity_id`, `tenant_id` | request scope | isolation |
| `queries_total` / `queries_executed` / `queries_unsupported` | `source_query` | FR-006 |
| `partitions_total` | distinct `partition` in `reconstruction_frontier` | FR-014 |
| `partitions_exhausted` | count where `status = 'EXHAUSTED'` | proven empty |
| `partitions_exhausted_no_progress` | count where `status = 'EXHAUSTED_NO_PROGRESS'` | terminal, not proven |
| `partitions_failed` | count where `status = 'FAILED'` | needs attention |
| `partitions_open` | count where status is not terminal | remaining work |
| `pages_open` | count of non-terminal entries | remaining work |
| `failing_partitions` | partition + `last_error` for each non-exhausted terminal | FR-038 |
| `remaining_work` | total non-terminal entries | FR-008, FR-014 |
| `last_progress_at` | max `updated_at` over entries | FR-038 |
| `complete` | true only when no non-terminal entries remain and nothing failed | FR-025 |
| `admission_counts` | accepted / rejected / deferred / quarantined over covered work | FR-024 |
| `publication_generation` | current head | FR-040 |
| `stale` | true when `complete = false` or a newer run failed | FR-040, AS-020 |

`complete` is deliberately derived from frontier state and never from "no exception was
raised", which is the current behaviour and the source of the masked-failure defect
(research D13).

**Satisfies**: FR-014, FR-024, FR-025, FR-038, FR-040

## 10. Migration plan (forward-only)

Revision `014_temporal_materialization` is treated as already applied and is **not
modified** (research D12, FR-033). A new revision `015_worldline_reconstruction` creates:

| Object | Action |
| --- | --- |
| `source_query_set` | create table |
| `source_query` | create table |
| `reconstruction_frontier` | create table |
| `entity_stream_sequence` | create table |
| `materialization_outbox.identity_fingerprint` | add column, nullable, backfilled from stored identity |
| `materialization_outbox.lease_owner` | add column, nullable |
| `materialization_outbox.lease_expires_at` | add column, nullable |
| `materialization_outbox.reclaim_count` | add column, not null, server default 0 |
| `materialization_outbox.last_outcome` | add column, nullable |
| `uq_materialization_outbox_active` | create partial unique index |
| `ix_materialization_outbox_lease` | create index |
| `ix_reconstruction_frontier_*` | create indexes |

Ordering inside the revision: create tables, add columns, backfill, then create indexes,
so no index is built before its columns exist. `identity_fingerprint` is backfilled from
the existing `identity` JSONB so that pre-existing rows satisfy the new partial unique
index rather than colliding inside it.

### Verification of both paths

| Path | Procedure | Proves |
| --- | --- | --- |
| Fresh install | create an empty database, apply all revisions in order | SC-012 |
| Upgrade | create a database, apply revisions through `014` only, then apply `015` | SC-012 |
| Equivalence | compare the resulting schema of both paths programmatically (tables, columns, types, indexes) | SC-012 |

A test asserts that the two schema states are identical; visual inspection is not
accepted as evidence.

## 11. Data model to key entity mapping

| Key Entity (spec) | Physical representation |
| --- | --- |
| Source Query | `source_query` row |
| Query Set | `source_query_set` + its ordered `source_query` rows |
| Frontier Entry | `reconstruction_frontier` row |
| Observation | `entity_stream` row with `kind = 'cc.observation'` |
| Candidate | `candidate_id` carried in the assertion payload |
| Assertion | `entity_stream` row with `kind = 'entity.assertion'` |
| Admission Decision | `admission` object inside the assertion payload |
| Temporal Event | `entity_stream` row with `kind = 'entity.event'` |
| Temporal Relation | derived per request from events; not persisted |
| Entity State Transition | `before_state` / `after_state` on the event |
| Reconstruction Request | `materialization_outbox` row |
| Coverage Report | derived read model over frontier + request + publication |

## 12. Requirement coverage by the data model

| Requirement group | Where satisfied |
| --- | --- |
| FR-001 - FR-006 (query planning) | sections 2, 3 |
| FR-007 - FR-014 (frontier) | section 4, coverage report in 9 |
| FR-015 - FR-022 (materialization unit) | section 7 |
| FR-023 - FR-025 (admission-gated publication) | sections 7, 9 |
| FR-026 - FR-030 (transactional request) | section 5 |
| FR-031 - FR-032 (concurrency) | section 6 |
| FR-033 (forward-only migration) | section 10 |
| FR-034 - FR-037 (relation scale) | section 8 |
| FR-038 - FR-040 (observability) | sections 4, 9 |

