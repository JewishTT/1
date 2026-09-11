# Quickstart / Validation Guide: Global OSINT Intelligence Platform

**Phase 1 output** — runnable validation showing the feature works end-to-end: a fixture-driven investigation that walks the full intelligence chain (Spec FR-033 / §84 acceptance chain) with traceability at every hop.

> Design details: see [data-model.md](./data-model.md); contract interfaces: see [contracts/](./contracts/README.md). This file is a run guide — implementation lives in `tasks.md` + code.

## Prerequisites

- Docker + Docker Compose (dev topology: `deploy/docker-compose.yml`).
- `uv` (Python toolchains) and Rust toolchain for `apps/acquisition/worker-http`.
- Node 20+ / pnpm for `apps/webapp`.
- Speckit CLI for workflow commands (already installed: `specify`).

## Dev topology (single-node, self-hosted)

MinIO (raw evidence), Kafka KRaft (1 broker), Schema Registry, PostgreSQL 16 (operational state), Redis (frontier leases), OpenSearch (search), ClickHouse (analytics), Neo4j (graph dev backend), Temporal (workflow + UI), control-plane API, dispatcher + worker-http, interpretation/admission/projection/feedback services.

Start:

```bash
docker compose -f deploy/docker-compose.yml up -d
```

## Validation scenario

Proof the closed loop works with controlled fixtures (no live external crawling). Fixtures live in `bench/fixtures/` — served objects + sitemap + rss + a mirrored page graph.

### 1. Create Investigation

```bash
curl -s -X POST localhost:8000/investigations \
  -d '{
    "name": "smoke-val",
    "objective": {"type": "osint", "description": "validate closed loop"},
    "seeds": ["http://fixtures.local/sitemap.xml"],
    "scope": {"source_classes": ["HTTP", "RSS"], "time_range": {}},
    "policy_id": "policies/default"
  }'
# expect: status RUNNING, investigation_id = INV-...
```

### 2. Seeds → discovery → frontier

Poll `.specify` convention: check `specs/001-global-osint-platform/` state independent of UI. Assert frontier contains items from sitemap + rss with host_key `fixtures.local`, state READY, non-deterministic but positive priorities.

### 3. Acquisition → Observation (immutable raw)

Wait for acquisition.completed. Assert:
- `observation.created` event in topic `observation.created` with correct envelope (event_id/correlation_id/provenance).
- Raw object present at `s3://knowledge/raw/{tenant}/{yyyymm}/{sha256}` — content matches fixture bit-for-bit (sha256 verifiable).
- Postgres `observations` row immutable: sending a PUT-style update is rejected by model.

### 4. Interpretation

Run interpretation job for the observation. Assert `mention.created`, `candidate.created`, `assertion.created` events; mentions on the page's fixture text (e.g., "ACME Corp" → PERSON/ORG hypothesis), candidates aggregate mentions, assertions link subject/object entities with evidence_refs.

### 5. Admission + Entity resolution

Run admission. Assert decision rows for each candidate (ACCEPT_NEW/…/REJECT) with score_vector and reasons; non-empty `independent_sources` counting (copied pages contribute 1, not N). Entities materialized as versions (version 1 at least).

### 6. Projections

Trigger projection run. Assert:
- OpenSearch index `entities`, `observations`, `findings` searchable; query `acme` returns the admitted entity.
- ClickHouse has `observation_metrics` rows (count/bytes per source).
- Neo4j (via GraphReader) exposes the assertion edge with independent_support = 1.
- `GraphSnapshot` row created with node/edge counts and checksum.
- 2nd run rebuild: `rebuild(projection_id)` reproduces identical node/edge counts — rebuildability proven (SC-002).

### 7. TDA + Findings + Feedback

Build the adaptive subgraph from the fixture graph, run budgeted persistence (H0/H1/H2). Assert `tda.completed`, TopologicalFeature rows with birth/death/persistence and supporting nodes/edges; at least one `finding.created` (e.g., dense cluster or persistence signal) with full lineage (finding → feature → graph → assertion → evidence → observation → raw uri).

### 8. Feedback closure

After findings, assert `feedback.generated` and that a NEW frontier item / recrawl priority was produced from the finding (loop closed). Run the loop again → asserted to converge (marginal yield drop → SLEEP/STOP) without unbounded frontier growth.

## Regression / contract checks

```bash
# backend contract + integration + unit
cd apps/control-plane && uv run pytest -m "contract or integration"
cd apps/acquisition && cargo test
# frontend
cd apps/webapp && pnpm vitest run
# full acceptance chain, from plan root
cd bench && uv run python -m bench.run --scenario smoke-val
```

`bench.run --scenario smoke-val` re-runs steps 1–8 against a clean compose stack and prints the traceability chain for every finding.

## Expected outcomes

- SC-001: every finding links to a raw object that exists in MinIO.
- SC-002: `rebuild` reproduces projections.
- SC-003: full §84 chain runs with zero manual DB pokes.
- SC-006: unchanged fixture re-fetch → `observation.unchanged`, no re-parse (dedup + conditional acquisition).
- Idempotency: replaying `observation.created` events yields no duplicate rows.
- Security smoke: external egress blocked for workers except allow-listed fixtures host (FR-029 check).