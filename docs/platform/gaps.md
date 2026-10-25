# Gaps (machine-checked)

Every defect below is a claim tied to re-checkable evidence (a file and a regex). `platform_model/gaps.py` re-reads the tree and a contract test fails if any open gap's evidence no longer holds. This is the replacement for the old free-text `KNOWN_GAPS`.

**10** open gaps; **0** stale/resolved (must be zero — the test fails otherwise).

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
| `roe-in-memory-registry` | critical | OPEN | Rules-of-Engagement sign-off is written to an in-process registry, not durable storage. | `apps/control-plane/api/routes/specops_roe.py` |
| `alembic-head-is-not-a-base` | high | OPEN | The first Alembic revision has down_revision=None, so upgrade head builds no pre-014 table. | `apps/control-plane/db/migrations/versions/014_temporal_materialization.py` |
| `create-tables-in-production-path` | high | OPEN | Operational code creates schema with Base.metadata.create_all, not Alembic. | `apps/control-plane/services/temporal_materialization_dispatch.py` |
| `dlq-seeded-record` | high | OPEN | GET /api/v1/dlq reads an in-process store seeded with one fake record. | `apps/control-plane/api/routes/quarantine.py` |
| `metrics-hardcoded` | high | OPEN | GET /api/v1/metrics returns hard-coded numbers, never measured. | `apps/control-plane/api/routes/metrics.py` |
| `roe-approved-by-from-body` | high | OPEN | The RoE approver is taken from the request body, not a verified principal. | `apps/control-plane/api/routes/specops_roe.py` |
| `wheel-packages-omit-context-engine` | high | OPEN | The control-plane wheel omits context_engine/semantic_path, so an installed build differs from checkout. | `apps/control-plane/pyproject.toml` |
| `health-is-constant` | medium | OPEN | GET /health returns a constant and reflects no dependency availability. | `apps/control-plane/api/main.py` |

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
