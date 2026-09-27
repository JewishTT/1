# Operations: Discovery & Search Projection Fabric

**Feature**: `008-discovery-search-fabric` | **Date**: 2026-09-26

---

## 1. Migration

One forward-only migration.

| # | Change | Table | Reversible |
|---|---|---|---|
| 1 | `provenance JSONB NOT NULL DEFAULT '{}'` | `frontier_items` | yes (drop column) |

**Rationale.** FR-007 requires provenance to survive to the frontier. `frontier_items` has no
column for it (`apps/control-plane/db/schema.py`), so the Layer A → frontier bridge would
discard it. See `data-model.md`.

**Rules**

1. **Forward-only.** The previous revision is immutable, matching
   `migrations/versions/014_temporal_materialization.py`, `015_worldline_reconstruction.py`,
   `016_relation_evidence_graph.py`.
2. MUST be proven on **both** paths — upgrade from the current head, and fresh create —
   following the precedent in
   `apps/control-plane/tests/unit/test_migration_016_forward_only.py`.
3. `DEFAULT '{}'` makes it safe against existing rows; no backfill is required because no
   historical provenance exists to backfill.
4. MUST NOT touch `uq_frontier_schedule (tenant_id, uri)`. Discovery idempotency (FR-006)
   depends on that index and a migration that rebuilds it under load is a self-inflicted
   outage.
5. `provenance` is **not** indexed. It is read for audit, never queried. If a query need
   appears, it gets its own migration and a justification.

## 2. Index generation lifecycle

```text
  declarative config                apply                    serve
  mappings.index_config()  ──►  create physical index  ──►  alias swap
   (in-repo, versioned)           {kind}-v{n}-{tenant}      {kind}-{tenant}
                                          │
                                          ▼
                                  Kafka source attached
                                  (topic search.projected,
                                   enable_backfill_mode)
                                          │
                                          ▼
                              objects on s3://<bucket>/{index_id}
```

**Rules**

1. `INDEX_VERSION` is part of the **physical** name (`mappings.py:81`). A mapping change ⇒ a
   new physical index ⇒ the old generation stays readable until the alias swaps. There is no
   in-place reindex of a live projection.
2. The alias (`{kind}-{tenant}`) is what queries resolve. Swapping the alias is the atomic
   cutover.
3. `retention_period: 90 days` (`mappings.py:133`) applies to the **index**, never to the
   events. Events are the rebuild source (FR-010) and their retention is set by the
   event-schema ADR.
4. A generation is disposable. If it cannot be rebuilt from the log, it is not a projection —
   escalate; do not patch it in place.

## 3. Rebuild procedure

```text
1. record target position P from the log
2. drop / detach the target generation        (or build into a new version)
3. replay log from P → SearchProjector.project() per event
4. publish to search.projected               (idempotent on doc_id)
5. compare document id set + digest to the previous generation
6. swap the alias
```

**Rules**

1. Step 5 must **compare and report**, not assume. `duplicates` is reported (API contract §4).
2. A rebuild MUST NOT read the previous generation (US2 scenario 6). If a rebuild needs the
   old index to complete, the projection has acquired hidden state — that is a defect.
3. Rebuild is safe with producers live: writes are idempotent on `doc_id`.
4. If a projection offset is lost or the log is compacted, rebuild from the **earliest
   retained position**. Never partially patch (spec edge case).

## 4. Observability

| Signal | Type | Why it matters |
|---|---|---|
| `discovery.pass.duration` | histogram | per-pass cost; a slow pass stalls acquisition |
| `discovery.candidates.found` | counter | discovery yield per source |
| `discovery.candidates.enqueued` | counter | yield **after** dedup — the drop between the two is the dedup rate |
| `discovery.source.failed` | counter, labelled by source | a source failing is otherwise invisible (it just returns nothing) |
| `discovery.source.empty` | counter, labelled by source | distinct from failure; a permanently empty source is a silent loss of coverage |
| `search.projected.publish.failures` | counter | publication is downstream of the write; a leak here means the index silently drifts from the log |
| `search.projected.publish.skipped_no_tenant` | counter | **must be 0** — these documents are excluded from every index |
| `search.rebuild.documents` / `.duplicates` | counter | duplicates ≠ 0 is a defect signal |
| `search.query.degraded_backends` | counter, labelled by backend | FR-015/SC-006 evidence |
| `search.query.total_failure` | counter | must raise 503, not return empty |
| `adjacency.read.duration` / `.nodes` | histogram + gauge | feeds the analytical plane |

**Rule**: metrics are labelled by `source` / `backend` / `tenant` but **never** by URL. A URL
label is unbounded cardinality and a straightforward denial-of-service vector against the
metrics store (Constitution VII).

**Audit**: every discovery pass and every degraded query is written to the audit log
(`apps/control-plane/services/audit.py`) with the report/exception attached. Rejected
candidates are preserved, never auto-deleted.

## 5. Security controls

| Control | Implementation | Gate |
|---|---|---|
| No access-control bypass | A source requiring auth/CAPTCHA/paywall is refused **at registration** | FR-018, SC-008, Constitution VII |
| Tenant isolation | Tenant-scoped physical index + alias; `_prepare` rejects a doc without `tenant_id`; `TenantIsolationError` on cross-scope read | FR-011, SC-004 |
| Fail closed | A permission error raises; it is never converted to an empty result set | FR-011 |
| SSRF / DNS rebinding | Discovery sources issue **index queries**, not arbitrary fetches; a source that would fetch a discovered URL is the acquisition plane's job and inherits its egress policy | Constitution VII |
| Untrusted input | A malformed/oversized payload from any source is quarantined with a reason, never silently dropped | SC-009 |
| Resource limits | Per-pass candidate cap, per-source timeout, per-host frontier budget (deferred, not dropped) | Constitution VII |

**Note on the caps**: the API cap (§3 of `api.md`) and the per-pass cap are **reporting
limits**, not safety limits. Truncation must always be visible in the report, or the report
becomes a lie an operator trusts.

## 6. Operational runbook

### Discovery returns nothing for a seed that should have results

1. `discovery.source.empty{source=…}` — is the source empty, or failing?
   `discovery.source.failed` distinguishes them. Check the source's index freshness first: a
   stale index legitimately returns nothing.
2. `discovery.candidates.found` vs `enqueued` — a large gap is dedup, not failure.
3. Confirm the seed reached `DiscoveryRegistry` at all (`discovery.seed` has no producer
   outside the API route — if the API route is not being used, nothing is running).

### The index is missing documents

1. `search.projected.publish.skipped_no_tenant` — if non-zero, the publisher's guard is
   rejecting documents; that is a **producer** bug, and those docs are in no index.
2. `search.projected.publish.failures` — publication is downstream of the write, so the
   documents may be in a *local* index but absent from the Kafka-fed one. Rebuild from the
   log repairs it; do not patch the index.
3. Check the Quickwit transform filter (`tenant_id == … && kind == …`,
   `mappings.py:150-154`) against the document. A mismatched `kind` string is filtered out
   silently.
4. Only then investigate the index itself.

### A query returns 503

Expected when **every** backend failed — this is by design (Invariant 9). `degraded_backends`
in the 503 body names the cause. A 503 with an empty `degraded_backends` is a bug.

### A query returns 200 but with `degraded_backends` non-empty

Expected and correct (FR-015). The remaining backends answered. Investigate the named backend
independently; do not retry the whole query, which will fail the same way.

### Link-graph discovery returns no candidates

1. Is the graph projection populated? Link-graph discovery reads the **projection**, not the
   topic (`events.md` §4). An empty graph means no candidates — correctly, not a bug.
2. `adjacency.read.duration` — a provider timeout is recorded as a source failure, so also
   check `discovery.source.failed{source="link-graph"}`.
3. Edges without provenance are not returned (contract §8). If edges exist but are
   provenance-less, they are inadmissible (Constitution II) — fix the producer, do not relax
   the reader.
