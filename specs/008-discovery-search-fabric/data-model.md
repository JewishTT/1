# Phase 1 Data Model: Discovery & Rebuildable Search Projection Fabric

**Feature**: `008-discovery-search-fabric` | **Date**: 2026-09-26

Entities marked **EXISTS** are already in the tree and are described here as the contract
this feature binds to. Entities marked **NEW** are introduced by this feature.

---

## Gap discovered while modelling

`frontier_items` (`apps/control-plane/db/schema.py`) has **no provenance column**:

```text
frontier_id, tenant_id, investigation_id, source_id, uri, host_key,
priority(Float), state, retries, lease_until, last_digest, last_etag,
partition, next_schedule_at, created_at
```

FR-007 requires every discovered candidate to carry provenance (originating source, query or
seed, and for link-graph the originating observation). The unique index
`uq_frontier_schedule (tenant_id, uri)` is the right dedup key and needs no change, but
without a provenance column the adapter would have to **discard** the provenance it is
required to carry — Layer A would satisfy FR-007 in memory and lose it at the boundary.

**Resolution:** one forward-only migration adding `provenance JSONB NOT NULL DEFAULT '{}'`
(see *Migration plan*). This is additive, nullable-safe, and does not touch the unique index
or any existing column.

---

## Entity: Candidate — **EXISTS**

`apps/acquisition/adapters/discovery/contracts.py:46-68`. A candidate for acquisition,
**never** an observation (Constitution Invariant 2: Mention ≠ Candidate ≠ Entity).

| Field | Type | Derivation / rule |
|---|---|---|
| `url` | `str` | Raw URL as reported by the source. Preserved verbatim for audit. |
| `canonical_url` | `str` | `canonicalize(url)`; the dedup key. Non-http(s) → source drops the row. |
| `source` | `str` | Registered discovery-source name. First source wins on coalesce. |
| `method` | `str` | How this source found it (`index-query`, `cdx`, `ct-log`, `link-graph`, …). |
| `confidence` | `float` | Source-declared prior in `[0, 1]`. Default `0.5`. **Not** truth. |
| `query` | `str` | The seed/query that produced it. Empty for link-graph. |
| `provenance` | `dict` | Free-form; `coalesce` accumulates `seen_by[]` and `sources[]`. |

**Canonicalisation rules** (`contracts.py:20-43`, deliberately conservative):

| Rule | Behaviour | Rationale |
|---|---|---|
| Scheme | lowercased; only `http`/`https` survive | Non-http(s) is not acquisition (edge case: `mailto:`, `javascript:`) |
| Host | lowercased, trailing `.` stripped | DNS case-insensitivity |
| Port | dropped when default for scheme (`:80`, `:443`) | `https://a/` ≡ `https://a:443/` |
| Fragment | always dropped | never sent to a server |
| **Trailing slash** | **preserved** | `Significant — /a and /a/ are different resources` |
| Query string | **preserved** | may carry identity |

`canonicalize` is pure and deterministic: same input → same output, always. This is what
makes FR-006 (idempotent enqueue by canonical URL) testable without a database.

**Coalescing rule** (`contracts.py:114-142`): group by `canonical_url`; first occurrence wins
for scalars; `confidence` takes the **max**; `provenance.seen_by` accumulates in encounter
order; output is emitted in **sorted key order**. Encounter-order accumulation plus sorted
emission is what makes a replayed discovery pass produce byte-identical output.

---

## Entity: DiscoveryReport — **EXISTS**

`registry.py:66-85`. The auditable outcome of one pass. Exists specifically so that "a
source returned nothing" (US1 scenario 3) is a recorded outcome rather than a hang.

| Field | Type | Meaning |
|---|---|---|
| `query` | `str` | The seed. |
| `sources_run` | `list[str]` | Sources selected for this pass. |
| `sources_failed` | `list[dict]` | `{source, error}` per source; a raising source never aborts the pass. |
| `candidates_found` | `int` | Count **after** coalescing. |
| `enqueued` | `int` | Frontier rows actually created. |
| `empty_sources` | `list[str]` | Sources that returned zero — distinct from failure. |

`sources_failed` and `empty_sources` are deliberately separate fields: "this source is
broken" and "this source genuinely had nothing" are different operational facts and
collapsing them is how a dead source goes unnoticed for months.

---

## Entity: FrontierItem — **EXISTS**, extended

`apps/control-plane/db/schema.py`. The durable acquisition frontier (ADR-0015). Uniqueness is
`(tenant_id, uri)`; `enqueue` prefers higher priority and returns whether a row was created.

**Mapping from the Layer A sink call:**

| `FrontierSink.enqueue` kwarg | `frontier_items` column | Note |
|---|---|---|
| `uri` | `uri` | fed the **canonical** URL, so dedup is by canonical URL |
| `tenant_id` | `tenant_id` | part of the unique key |
| `investigation_id` | `investigation_id` | Constitution VI: process-centric |
| `source` | `source_id` | source *name*; the column is nullable, discovery always sets it |
| `priority` (`int`) | `priority` (`float`) | widened, never truncated — `int` is a valid `float` |
| `provenance` | `provenance` **(NEW)** | `method`, `query`, `confidence`, `seen_by[]`, `sources[]` |
| — | `host_key` | derived from the canonical host, for per-host budget policy |
| — | `state` | `READY` — frontier policy owns state transitions (ADR-0016) |

The adapter MUST NOT set `state` itself. Deferral, budget exhaustion and recrawl cadence are
the frontier's policy (ADR-0016/0017) and are explicitly out of scope for this feature.

---

## Entity: LinkEdge — **EXISTS**

Input to both discovery expansion (FR-004) and TDA adjacency (FR-013).

| Attribute | Meaning |
|---|---|
| source node | originating page / observation node |
| target node | linked page, or the co-mentioned entity |
| type | `link` (hyperlink) or `co-mention` (co-occurrence in one observation) |
| provenance | originating observation id — **mandatory**, not optional |

A link edge with no provenance is not admitted: it cannot satisfy Constitution II
(Evidence-First), because there is no path from the edge back to a raw object.

---

## Entity: AdjacencyView — **EXISTS**

`apps/projection/graph/adjacency.py:29-176`. The (nodes, edges) contract TDA consumes.

| Member | Signature | Use |
|---|---|---|
| `index_of` | `(node_id: str) -> int` | stable position for matrix construction |
| `to_tda_input` | `() -> (list[str], list[(int, int, float)])` | **the** TDA entry point: node labels + weighted index triples |
| `degree_centrality` | `() -> dict[str, int]` | descriptive statistics |
| `subgraph` | `(node_ids) -> AdjacencyView` | scope reduction without a second traversal |
| `to_distance_matrix` | `(view) -> (nodes, matrix)` | filtration input |
| `co_mention_adjacency` | `(...)` | entity co-occurrence projection |
| `adjacency_from_store` | `(store, ...) -> AdjacencyView` | production reader over the graph projection |

`to_tda_input` returning **integer index triples** is deliberate: it means TDA consumes the
projection directly and never re-derives an identity, which is what FR-014 requires.

---

## Entity: SearchDocument — **EXISTS**, seven kinds

`mappings.DOC_KINDS` (`mappings.py:15-23`) is the **single source of truth**
(decision D8). `SearchProjector.INDEX_ALIASES` derives from it.

| # | Kind | Alias | Distinguishing fields |
|---|---|---|---|
| 1 | `observations` | `observations` | `observation_id`, `raw_ref`, `content_hash`, `status` |
| 2 | `documents` | `documents` | `observation_id`, `uri`, `content_type` |
| 3 | `mentions` | `mentions` | `mention_id`, `observation_id`, `mention_kind`, `value` |
| 4 | `candidates` | `candidates` | `candidate_id`, `observation_id`, `value` |
| 5 | `entities` | `entities` | `entity_id`, `name`, `aliases` |
| 6 | `assertions` | `assertions` | `assertion_id`, `entity_id`, `predicate`, `object_value` |
| 7 | `findings` | `findings` | `finding_id`, `entity_id` |

Every kind additionally carries the common fields `doc_id`, `tenant_id`, `kind`, `text`,
`produced_at` (`mappings.py:26-32`).

**Identity.** `doc_id` is the idempotency key (Constitution Invariant 11): the projector
short-circuits on an existing `doc_id` (`index.py:45-46`), which is what makes replay
produce an identical index.

**Provenance.** Every document carries `{event_id, observation_id}`
(`projector.py:50-53`) and is rejected without it by
`enforce_projection_provenance` (`index.py:44`). Provenance is a precondition of write, not
a field that may be omitted.

**Naming.** `physical_index_name = {kind}-{INDEX_VERSION}-{tenant}`;
`alias_name = {kind}-{tenant}`. Both raise on an empty tenant (`mappings.py:79-80, 88-89`).
Because the version is in the *physical* name, a mapping change produces a new physical index
and the previous generation stays intact — which is the correct behaviour for a projection
and is what makes FR-012's reproducibility claim true rather than aspirational.

---

## Entity: DegradedBackend — **NEW**

`FusedResult` gains a field recording which backends failed and why (decision D7).

| Field | Type | Meaning |
|---|---|---|
| `backend` | `str` | backend name |
| `error` | `str` | `type: message`, truncated — never a raw traceback |
| `recoverable` | `bool` | `True` for per-backend failure; the query still answered |

**Invariant:** `degraded_backends` is non-empty **iff** at least one selected backend failed.
A query where *every* backend failed raises instead of returning `[]` — an empty result set
means "no matches", and conflating it with "everything is down" violates Constitution
Invariant 9.

---

## Fusion scoring — corrected derivation

Current: `EVIDENCE_BASE * max + (1 - EVIDENCE_BASE) * max` ≡ `max` (query_planner.py:100,
decision D6). Corrected:

```text
relevance   = max(score for hits of doc_id)          # best single backend
support     = len({hit.source_id for hit in hits})   # independent sources, not backends
composite   = relevance * (1 + EVIDENCE_BASE * (support - 1))
```

Both `relevance` and `support` are retained on `FusedResult` so any reader can re-derive or
dispute `composite`. `support` counts distinct **sources**, never backends — Constitution
Governance is explicit that publication count is not independent-source count, and two
backends reading the same source are one piece of evidence, not two.

---

## Event: `discovery.discovered` — payload

Declared at `topics.py:21`; **no producer exists** (decision D2). Payload is
`Candidate.as_event_payload()` (`contracts.py:58-68`):

```json
{
  "uri": "https://example.org/a",
  "canonical_url": "https://example.org/a",
  "source": "cc-index",
  "method": "index-query",
  "confidence": 0.7,
  "query": "example.org",
  "provenance": { "seen_by": [{"source": "ct-log", "method": "ct-log"}],
                  "sources": ["cc-index", "ct-log"] }
}
```

`tenant_id` and `investigation_id` travel in the envelope, not the payload — they are
envelope-level and must not be forgeable by a producer.

## Event: `search.projected` — payload

Declared at `topics.py:50`; consumer side fully declarative
(`mappings.py:134-157`), **no producer** (decision D2).

```json
{ "tenant_id": "...", "kind": "entities", "doc_id": "...", "text": "...",
  "produced_at": "...", "entity_id": "...", "name": "..." }
```

`tenant_id` and `kind` are **mandatory**: the Quickwit transform filter
(`mappings.py:150-154`) is `tenant_id == "<tenant>" && kind == "<kind>"`. A document missing
either is silently filtered out of every index — invisible data loss, which is why the
publisher must reject such a document rather than emit it.

---

## Migration plan

| # | Change | Type | Reversible |
|---|---|---|---|
| 1 | `frontier_items.provenance JSONB NOT NULL DEFAULT '{}'` | additive column | yes (drop column) |

Forward-only, consistent with `migrations/versions/014_*`, `015_*`, `016_*`. The previous
revision is immutable. The migration must be proven on **both** paths (upgrade from `015`/`016`
and fresh create), following the existing precedent in
`apps/control-plane/tests/unit/test_migration_016_forward_only.py`.

No other table changes. The search index, the graph projection and the discovery layer hold
**no** relational state of their own — that is the point of the feature (FR-016, Constitution
III).
