# Gaps (machine-checked)

Every defect below is a claim tied to re-checkable evidence (a file and a regex). `platform_model/gaps.py` re-reads the tree and a contract test fails if any open gap's evidence no longer holds. This is the replacement for the old free-text `KNOWN_GAPS`.

**5** open gaps; **1** stale/resolved (must be zero — the test fails otherwise).

## Layer 0 — collection

| ID | Severity | Status | Claim | Evidence |
|---|---|---|---|---|
| `layer0-pipeline-marked-stub` | medium | OPEN | services/layer0_pipeline.py carries stub markers and is test-only. | `apps/control-plane/services/layer0_pipeline.py` |

## Layer 1 — extraction/resolution

| ID | Severity | Status | Claim | Evidence |
|---|---|---|---|---|
| `search-tantivy-declared-not-implemented` | medium | OPEN | search/tantivy_backend.py declares a BM25 backend but defines no class. | `apps/projection/search/tantivy_backend.py`, `apps/projection/search/tantivy_backend.py` |

## cross-cutting

| ID | Severity | Status | Claim | Evidence |
|---|---|---|---|---|
| `dlq-tenant-store-not-wired` | critical | RESOLVED | The DLQ API fails closed because a durable tenant-scoped quarantine repository is not wired to the control plane. | `apps/control-plane/api/routes/quarantine.py` |
| `roe-in-memory-registry` | critical | OPEN | Rules-of-Engagement sign-off is written to an in-process registry, not durable storage. | `apps/control-plane/api/routes/specops_roe.py` |
| `alembic-head-is-not-a-base` | high | OPEN | The first Alembic revision has down_revision=None, so upgrade head builds no pre-014 table. | `apps/control-plane/db/migrations/versions/014_temporal_materialization.py` |
| `metrics-not-connected-to-telemetry` | high | OPEN | The metrics API explicitly reports unavailable because tenant-scoped telemetry and time-windowed aggregates are not connected. | `apps/control-plane/api/routes/metrics.py` |

## Resolved claims (regression guards)

Formerly-recorded gaps whose fix must stay in place; a regression flips the guard.

| ID | Status | Claim |
|---|---|---|
| `context-engine-was-in-memory-only` | GUARDED | CognitiveLoop ran entirely on InMemoryContextStore; the fix is a Postgres store. |
| `investigation-workflow-was-unregistered` | GUARDED | InvestigationWorkflow/RecrawlWorkflow were declared but never registered. |
| `all-downgrades-were-not-implemented` | GUARDED | Every migration downgrade raised NotImplementedError. |
| `ci-sync-installed-no-test-runner` | GUARDED | CI ran `uv sync --locked` and installed no test runner. |
| `auth-anonymous-admin` | GUARDED | Anonymous requests must not receive an administrator role. |
| `auth-unverified-token` | GUARDED | JWT claims must be signed and validated before they can establish identity or role. |
| `operational-schema-owned-by-alembic` | GUARDED | Operational service paths no longer create schema at runtime; a static AST contract guards Alembic ownership. |
| `roe-approver-from-authenticated-principal` | GUARDED | Rules-of-Engagement approver identity comes from the verified administrator principal, never request-body input. |
| `control-plane-wheel-includes-runtime-packages` | GUARDED | The installed control-plane wheel includes context_engine and semantic_path package roots. |
| `dlq-has-no-seeded-fictional-record` | GUARDED | The quarantine API no longer seeds a fictional rejection to make the dashboard look populated. |
| `dlq-re-evaluation-does-not-delete-payload` | GUARDED | The API no longer purges a quarantined payload as part of re-evaluation. |
| `metrics-have-no-fabricated-operational-values` | GUARDED | The metrics API never returns hard-coded demonstration counters as operational measurements. |
