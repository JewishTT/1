# Quickstart / Validation Guide: Donor Pattern Integration

**Phase 1 output** — runnable validation showing the donor patterns work end-to-end on top of feature 001. This is a run guide; implementation lives in `tasks.md` + code.

> Design details: [data-model.md](./data-model.md) · contract interfaces: [contracts/](./contracts/README.md) · donor rationale: [research.md](./research.md).

## Prerequisites

- Feature 001 platform running (compose topology + control plane, per `001-global-osint-platform/quickstart.md`).
- Python env (`uv`), Rust toolchain for `apps/acquisition`.
- Fixtures in `bench/fixtures/` (already present).

## Dev topology

No new services. The donor patterns reuse the existing Neon/Kafka/S3/Postgres/OpenSearch/graph/devices and the existing `apps/*` planes. Only new artifact types (Statement, CorrelationEdge, ReviewDecision, Connector, ReconPlan, OntologyPack, Claim/Storyline, ParserAdapter) are added to existing stores.

## Validation scenario (smoke)

### 1. Statement-level knowledge model (US1)

- Create an investigation with seeds over `bench/fixtures/*`.
- Assert every produced assertion has a Statement with `dataset_id`, `first_seen/last_seen`, `original_value`, `extraction_version` (FR-001/FR-003).
- Feed a reprint corpus: 1 original + N copies → `publication_count = N+1`, `independent_sources = 1` (FR-002).

### 2. Correlation without destruction (US2)

- Two candidates sharing weak signals → `CorrelationEdge(kind=possible_match, raw_pair_score, reasons)` exists; no auto-merge (FR-004).
- Insufficient evidence → admission returns DEFER (default), never destructive REJECT (FR-005).
- Analyst review ACCEPT/REJECT/UNCERTAIN → `ReviewDecision` persisted, replayable via Kafka (FR-006).

### 3. Investigation/evidence workspace (US3)

- Open the workbench for an investigation: evidence objects with grading appear in graph + timeline (+ map when geolocation exists).
- Walk lineage finding → feature → graph/assertion → evidence → observation → raw uri.

### 4. Connector ecosystem + parser interface (US4)

- Register a connector (fixture source); confirm `capabilities()/estimate()/acquire()` satisfy the AcquisitionWorker contract and produce a standard observation event.
- Run a recon plan: Investigation → Acquisition Plan → Tasks → Kafka → Collectors → Observations.
- Parse an artifact through `ParserAdapter.can_parse/parse` → deterministic findings (HTML/JSON/CSV/PDF/Email/Archive).

### 5. Evidence reasoning + stream provenance (US5)

- Corroboration fixture (independent sources agree) → claim verdict SUPPORTED + corroboration.
- Copy fixture (one original reprinted) → consolidates to one independent chain, verdict not inflated.
- Replay Kafka events → no duplicate rows, provenance intact (idempotency).

## Regressions

```bash
cd apps/control-plane && uv run pytest -m "contract or integration"
cd apps/admission && uv run pytest
cd apps/interpretation && uv run pytest
cd apps/webapp && pnpm vitest run
cd bench && uv run python -m bench.run --scenario smoke-val
```

Expected: all green; the donor-pattern contract tests (statement, correlation-no-merge, review, connector, parser determinism) pass and the existing smoke-val chain still passes.