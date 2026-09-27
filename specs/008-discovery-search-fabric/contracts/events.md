# Event Contracts: Discovery & Search Projection Fabric

**Feature**: `008-discovery-search-fabric` | **Date**: 2026-09-26

All four topics below are **already declared** in `apps/shared/events/topics.py`. The gap
this feature closes is that three of them have **no producer**.

| Topic | Partition domain | Declared | Producer today |
|---|---|---|---|
| `discovery.seed` | `discovery` | `topics.py:20` | **none** |
| `discovery.discovered` | `discovery` | `topics.py:21` | **none** |
| `graph.projected` | `projection` | `topics.py:47` | **none** |
| `search.projected` | `projection` | `topics.py:50` | **none** |

---

## 1. `discovery.seed`

**Producer**: control-plane, when an Investigation is created or re-scoped
(Constitution VI — the user creates an investigation, not a graph).

```json
{
  "tenant_id": "TEN-1",
  "investigation_id": "INV-1",
  "seed": "example.org",
  "seed_type": "domain",
  "sources": ["cc-index", "ct-log", "link-graph"],
  "requested_at": "2026-09-26T00:00:00Z"
}
```

| Field | Required | Notes |
|---|---|---|
| `seed` | yes | domain, or an entity name to be resolved |
| `seed_type` | yes | `domain` \| `entity` \| `url` |
| `sources` | no | explicit source allow-list; absent = all registered |

Consumption: `DiscoveryRegistry.discover(seed, sources=…, tenant_id=…, investigation_id=…)`.

**Ordering**: one seed must be processed to completion before its own re-emission.
`discovery.discovered` for a seed MUST be published before any acquisition task for that
candidate is dispatched, so the frontier row and the event never disagree.

## 2. `discovery.discovered`

**Producer**: `DiscoveryRegistry`, one envelope per coalesced candidate
(**NEW** — decision D2).

Payload = `Candidate.as_event_payload()` (`discovery/contracts.py:58-68`):

```json
{
  "uri": "https://example.org/a",
  "canonical_url": "https://example.org/a",
  "source": "cc-index",
  "method": "index-query",
  "confidence": 0.7,
  "query": "example.org",
  "provenance": {
    "sources": ["cc-index", "ct-log"],
    "seen_by": [{"source": "ct-log", "method": "ct-log"}]
  }
}
```

**Envelope requirements**

1. `tenant_id` and `investigation_id` travel in the **envelope**, never the payload. A
   producer must not be able to assert a tenant.
2. `event_id` MUST be deterministic given `(tenant_id, canonical_url, source-set)` so a
   replayed discovery pass does not create a second logical discovery (FR-006, Invariant 11).
3. `confidence` is a **source-declared prior, not truth** (Constitution IV). It must not be
   summed across sources — `coalesce` takes the max (`discovery/contracts.py:138`).
4. `provenance.seen_by` accumulates in encounter order and MUST be stable across replays.

**Delivery**: at-least-once. Consumers MUST be idempotent on `canonical_url`.

## 3. `search.projected`

**Producer**: `SearchProjectionPublisher` (**NEW** — decision D2). This is the ingestion
edge that makes FR-008's "Kafka-native" claim true; today the consumer side is fully
declarative (`mappings.py:134-157`) and the producer does not exist.

```json
{
  "tenant_id": "TEN-1",
  "kind": "entities",
  "doc_id": "ENT-abc",
  "text": "Example Org",
  "produced_at": "2026-09-26T00:00:00Z",
  "entity_id": "ENT-abc",
  "name": "Example Org"
}
```

**Hard requirements**

1. `tenant_id` and `kind` are **mandatory**. The index transform filter is
   `tenant_id == "<tenant>" && kind == "<kind>"` (`mappings.py:150-154`); a document missing
   either is excluded from **every** index — silent, invisible data loss. The publisher
   rejects such documents rather than emitting them.
2. `doc_id` is the idempotency key and MUST equal the `IndexedDoc.doc_id`.
3. `produced_at` MUST be present — it is the `timestamp_field` of every mapping
   (`mappings.py:102`).
4. Publication MUST NOT be able to fail the index write, and MUST NOT be on the rebuild
   critical path. The **event log is the rebuild source** (FR-010, FR-016) — a lost
   publication is repaired by replay, never by patching the index.

**Partitioning**: by `tenant_id`, so a tenant's documents are totally ordered and per-tenant
rebuild is a bounded scan.

**Retention**: the index generation declares `retention_period: 90 days`
(`mappings.py:133`). Retention applies to the **index**, not to the events — events are
retained per the event-schema ADR and are the rebuild source.

## 4. `graph.projected`

**Producer**: the graph projector. Declared at `topics.py:47`; **no producer exists**.

This feature does **not** build the graph publisher. The graph projection write path already
exists (`apps/projection/graph/neo4j.py`, `snapshot.py`, `relation_store.py`). What is
missing is only the event emission, which belongs to the projection that owns the write.
Recorded here so the gap is visible and owned, and so FR-004's link-graph source has a
documented upstream to read from once the graph projection emits.

**Rule**: link-graph discovery reads the **graph projection** (a rebuildable artifact), not
the `graph.projected` topic. Reading the projection keeps discovery synchronous with the
committed graph state and avoids a second consumer group for the same data.

---

## Event-name discipline

The four topics above follow the existing registry conventions: `discovery.*` for the
discovery plane, `<plane>.projected` for projection output. Two things deliberately do
**not** get topics:

- **Rebuild / backfill progress** — a rebuild is a local operation over the log, not a domain
  event. Emitting one per replayed document would flood the bus (rebuilds can be 10^6 events)
  and would make the log describe a projection's construction rather than the domain.
- **Candidate → frontier transitions** — the frontier row is the state (ADR-0015); an event
  duplicating it would create two sources of truth for frontier membership.
