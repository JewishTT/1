# API Contracts: Discovery & Search Projection Fabric

**Feature**: `008-discovery-search-fabric` | **Date**: 2026-09-26

The read surface is **thin and already present**. This feature does not invent a new API
style; it binds the existing routes to the real projections and adds one discovery route.

---

## 1. `GET /search` and `POST /search` — **[BIND]** (exists, fixture-bound)

`apps/control-plane/api/routes/search.py:52-86`

**Current state**: both handlers use a module-level `_planner` built from `_FIXTURE_DOCS`
(`search.py:33-39`) — a `MemoryBackend` over two hard-coded observations. The route works and
returns well-formed `FusedResult`s, but it **never touches the search projection or the graph
projection**. FR-015 is therefore unproven in production: there is one backend, so there is
nothing to fuse and nothing to degrade.

**Contract after this feature**

| Aspect | Requirement |
|---|---|
| Backends | `QueryPlanner` MUST be constructed with a **search** client and a **graph** client over the real projections. `MemoryBackend` remains for tests only. |
| Tenant | `ctx.tenant_id` MUST scope **both** backends. The current fixture backend ignores the tenant entirely; the real clients must not. |
| Evidence | Every result carries `evidence[]` whose `observation` resolves to an immutable observation (`query_planner.py:111-125`). Unresolvable `observation_id` → the result is dropped, not returned with a null observation. |
| Degradation | `degraded_backends` MUST be present in the response whenever a selected backend failed. HTTP **200** with the remaining backends' results. |
| Total failure | If every backend fails → HTTP **503**, never `200` with `results: []` (Invariant 9). |
| Cross-tenant | A query addressed to another tenant's index scope MUST fail closed (FR-011). |

**Response shape** (additive; existing fields unchanged)

```json
{
  "query": "example org",
  "mode": "hybrid",
  "tenant_id": "TEN-1",
  "results": [
    {
      "doc_id": "ENT-abc",
      "score": 0.83,
      "relevance": 0.7,
      "support": 2,
      "backends": ["graph", "search"],
      "observation_ids": ["OBS-1001"],
      "evidence": [{"backend": "search", "kind": "entity", "observation_id": "OBS-1001"}],
      "degraded_backends": []
    }
  ],
  "degraded_backends": []
}
```

`relevance` and `support` are returned **alongside** `score` so a client can re-derive or
dispute the composite (D6, Constitution IV). `score` alone would be exactly the "single
score equates to truth" the constitution forbids.

## 2. `GET /adjacency` (TDA entry) — **[BIND]**

Reuses the existing `graph/adjacency.py` reader. The contract this feature fixes:

- Returns `{nodes: [...], edges: [{source, target, weight, provenance}]}` where node ids are
  the **same identifiers** the search projection uses (FR-014).
- Accepts `tenant_id`, `investigation_id`, and an optional node subset.
- Refuses a cross-tenant subset (fail closed).
- Every edge carries provenance; an edge without an originating observation is not returned.

`to_tda_input()` is the in-process equivalent and is what the contract tests exercise.

## 3. `POST /discovery/run` — **[NEW]**

The one new route. Layer A is currently unreachable from the API: `DiscoveryRegistry` has no
caller outside tests.

```http
POST /discovery/run
{ "seed": "example.org", "seed_type": "domain",
  "investigation_id": "INV-1",
  "sources": ["cc-index", "ct-log"] }
```

```json
{
  "seed": "example.org",
  "tenant_id": "TEN-1",
  "investigation_id": "INV-1",
  "report": {
    "query": "example.org",
    "sources_run": ["cc-index", "ct-log"],
    "sources_failed": [],
    "candidates_found": 42,
    "enqueued": 40,
    "empty_sources": ["ct-log"]
  },
  "candidates": [
    {"canonical_url": "https://example.org/a", "source": "cc-index",
     "method": "index-query", "confidence": 0.7}
  ]
}
```

**Contract**

1. `seed` required, `min_length 1`. `seed_type` ∈ `{domain, entity, url}`, default `domain`.
2. Response is the `DiscoveryReport` verbatim (US1 scenario 3: an empty or failed pass is an
   **audited outcome**, never a hang and never a silent `200 []`).
3. `candidates` is capped (default 100, max 1000) with `candidates_found` reporting the true
   total. A cap that silently truncated would make the report lie.
4. `sources_failed` entries are `{source, error}` with the error **truncated**; no tracebacks,
   no internal paths.
5. Requires the same auth/tenant resolution as every other route.
6. HTTP **207-style partial success is not used** — a pass with some sources failed is still
   `200` with the failures in the body. Only a request that cannot be parsed or is
   unauthorised is a non-2xx.
7. Emits `discovery.discovered` per candidate and enqueues into the frontier (FR-005).

## 4. `POST /search/rebuild` — **[NEW]**, admin

Triggers a projection rebuild from a log position.

```http
POST /search/rebuild   { "from_position": 0, "kinds": ["entities"] }
```

```json
{ "kinds": ["entities"], "from_position": 0,
  "documents_replayed": 1284, "duplicates": 0, "duration_ms": 913 }
```

**Contract**

1. Rebuilds from the **event log only**. It MUST NOT read the previous generation
   (US2 scenario 6, SC-010) — that is what proves the index is a projection.
2. `duplicates` MUST be reported, not asserted. A non-zero value is a defect signal, not a
   success.
3. `kinds` omitted → all seven `DOC_KINDS`.
4. Admin-only; tenant-scoped; rate-limited. A rebuild is expensive and must not be
   triggerable per-keystroke by a normal user.
5. MUST be safe to run while producers are live (replay is idempotent).

## 5. What this feature deliberately does not add

| Not added | Why |
|---|---|
| A bulk document-ingest endpoint | Ingestion is Kafka-native (FR-008). An HTTP bulk path would be a second ingestion route with different guarantees. |
| A per-document CRUD API for index contents | The index is a projection; its contents are derived. Editing them is meaningless — the next rebuild overwrites the edit. |
| A raw "run this Cypher" graph endpoint | Unbounded query surface over the projection, and an invitation to treat a projection as a source of truth (Invariant 4). |
| An index-mutation API | Same reason: `rebuild` exists; mutation does not. |
