# COGNITIVE architecture and technology review

Review date: 2026-10-28. Scope: checked-in source tree, existing generated platform model and its explicit caveats. This is a static repository review, not a claim that all backing services were run in this environment.

## Architectural intent

The platform's differentiating idea is not "a large OSINT toolbox." It is an evidence-first, process-centric investigation fabric that continuously approximates a changing world from immutable observations. The intended chain is:

```
investigation + context + invariants
  -> obligations / policy-aware planning
  -> discovery + durable frontier
  -> acquisition + immutable, content-addressed observations
  -> parsing / extraction / normalization
  -> entity and relation resolution + evidence admission
  -> bitemporal context and claims
  -> rebuildable graph / search / analytics / TDA projections
  -> findings with lineage
  -> feedback into acquisition utility and stopping policy
```

That philosophy implies several non-negotiable technical properties:

- Facts must preserve provenance back to immutable evidence; interpretation and inference must not be confused with observation.
- Dynamic entities and relations require valid-time and transaction-time semantics, explicit revision/merge/split behaviour and deterministic replay.
- Event delivery and projection must be idempotent, replayable and recoverable after partial failure.
- Authoritative state must be explicit. Materialized graphs and search indices are rebuildable projections, not silent alternate authorities.
- Cross-layer data contracts and ownership need stable boundaries; all production services should use the same contracts as tests.
- An investigator must be able to see provenance, confidence, contradictory evidence, temporal changes and uncertainty—not only a visually convincing graph.
- AI-facing specs, source code, docs and tests must converge on the same acceptance criteria.

## Findings by priority

### P0 — Security/authority and durable operational state

**RoE approval is not grounded in a verified principal.** The current gap record identifies `apps/control-plane/api/routes/specops_roe.py` as taking an approver identity from the request body, with approval stored in an in-process registry. This conflicts with auditability and durable governance: an approval must be bound to the authenticated principal, tenant, policy version, timestamp and immutable decision record.

**Action:** use the authenticated principal from the validated auth dependency; persist approvals transactionally; emit an audit event/outbox record; add tests for forged approver identity, cross-tenant access, restart survival and replay.

### P1 — Operational truth vs. mock/constant endpoints

The generated known-gap ledger calls out:
- `apps/control-plane/api/routes/quarantine.py`: the DLQ endpoint reads an in-process store seeded with a fake record.
- `apps/control-plane/api/routes/metrics.py`: metrics are hard-coded, not measured.

**Health/readiness correction:** the generated ledger previously listed `GET /health` as a constant health endpoint. That is a **false positive when read as readiness**: the root `/health` route is a liveness probe, while `GET /api/v1/platform/health` resolves the assembled platform and returns `503` when the platform is not ready. The false-positive gap has been removed. Keep liveness and readiness semantically distinct and add a deployment probe contract that targets the latter for traffic admission.

The DLQ and metrics findings remain real: these endpoints can make the workbench report states that never existed. For an evidence-centric product, fake operational telemetry is worse than an explicit "unavailable" status.

**Action:** wire the API to durable DLQ/quarantine storage and real metric sources; retain separate liveness/readiness probes and make deployment readiness depend on required components; distinguish unknown, zero and unavailable in the UI. Keep any demo fixture behind an explicit development adapter and make its scope unmistakable.

### P1 — Schema migration and installed-package parity

The known-gap ledger identifies an Alembic base-chain problem in `apps/control-plane/db/migrations/versions/014_temporal_materialization.py`, runtime use of `Base.metadata.create_all` in `apps/control-plane/services/temporal_materialization_dispatch.py`, and a control-plane wheel that omits `context_engine` / `semantic_path` in `apps/control-plane/pyproject.toml`.

**Action:** reconstruct a valid migration chain from an empty database, make migrations the only production schema evolution path, add clean-install and upgrade tests, and install the built wheel into a clean environment to run API/context-engine contract tests. Checkout tests alone do not prove packaging parity.

### P1 — Evidence admission and temporal semantics

The project has explicit architecture decisions for Belnap epistemic algebra, Allen temporal algebra, evidence independence, deterministic replay, identity merge/split and retention/erasure. Those decisions are stronger than a generic entity graph. They need executable contract suites at boundaries:
- observed time vs. produced/ingested time;
- immutable raw observation vs. mutable interpretation and entity worldline;
- assertion support, contradiction and absence;
- source independence and copied-source correlation;
- deterministic replay across revision and projection rebuild;
- retention/erasure rules applied to raw evidence, derived claims and indexes.

**Action:** map each invariant to a named test and failure-mode fixture, then derive projection and API behaviour from those contract suites. Do not count broad module-level test totals as proof of invariant coverage.

### P1 — Incomplete capability/runtime evidence

The generated `docs/platform/audit.md` documents 146 test-only modules, 122 orphan modules, 29 event types with no references outside the catalog, and nine Rust crates without an executable entry point. The golden-path table marks several meaningful capabilities test-only or orphaned, including historical backfill, regional backpressure, zero-layer harvesters, relation-claim persistence, graph projection and parts of the context graph.

These counts are static, and an orphan may be a plugin-loaded component or intentionally future-facing. Still, each item requires an owner and one explicit disposition: production wiring, verified plugin discovery, deliberate quarantine/deprecation, or removal. Catalogued events with no producer/consumer require a contract owner and deployment status.

**Action:** build an executable capability matrix from entrypoints, dependency injection, app manifests, event producer/consumer registration and test assertions. Avoid name/substring heuristics as the final authority. For every claimed production capability, prove at least one production ingress path and one observable end-to-end effect.

### P2 — Documentation coverage is structural, not semantic

The existing model's Python module scanner uses the Python AST, but TypeScript/React exports and Rust items are mostly discovered with regular expressions. Route inventory is regex-based; test mapping relies largely on import statements; the spec traceability layer often recognises numbers cited in module docstrings. These are useful discovery heuristics, not proof that a requirement is implemented or tested.

**Action:** retain the fast generated model, add compiler/parser-backed source records, stable symbol IDs, source-evidenced import/call/doc/spec/event edges, broken-link checks and per-acceptance test links. Expose compact context packets for AI agents and keep static evidence separate from test/runtime evidence.

### P2 — UI structure and operator workflow

The web application already has a React workbench, graph/timeline panels, keyboard command palette, density/theme controls and Playwright screenshot infrastructure. The Counterintelligence subject board's endpoint was present but the UI unconditionally claimed it was not served. It now consumes the endpoint's actual `served` / `missing` / `scope` envelope and labels the registry as a shared seeded fixture, not investigation data; a unit contract guards against reintroducing the false "NOT SERVED" assertion. The cognitive operators themselves remain unconnected and are not claimed as implemented. However, the current top navigation expands module tabs and many section links across the shell's most width-constrained horizontal strip. This competes with the investigation name, selection and work-state controls and repeats information already shown by the page itself.

**Action:** make navigation a compact active-workspace trigger with a searchable/grouped module deck, preserve route semantics and deep links, and make the workspace canvas the visual centre. Use restrained industrial/cyberpunk visual language—graphite, measured phosphor-green activity, amber temporal/provenance markers, semantic red for failure, precise typography and hairline separators. The current design-system contract explicitly forbids gratuitous neon glows, magenta gradients, HUD decoration and fake telemetry; "cyberpunk" should mean a credible intelligence workstation, not a casino dashboard.

The CI browser workflow captures the design-system and SpecOps/GhostLine surfaces at six viewport widths, plus the navigation deck at desktop/tablet/phone sizes. Screenshot artifacts are visual evidence and must be inspected; geometry assertions catch overflow and overlap but do not replace human UX review.

## Verification strategy (ordered)

1. **Data integrity contracts:** immutability/content addressing, lineage continuity, identity merge/split, temporal algebra, source independence, tenant isolation, retention and deterministic replay.
2. **Durable failure recovery:** outbox/consumer idempotency, Kafka/Redpanda retry and DLQ, Postgres transaction failure, object-store timeout, process restart and projection rebuild.
3. **Production wiring and packaging:** clean database migration, built-wheel installation, router registration, deployed event producer/consumer and readiness dependency checks.
4. **Golden-path E2E:** create an investigation; add static and dynamic invariants; acquire known seeded evidence; resolve entity/relation hypotheses with provenance; introduce conflicting temporal evidence; rebuild projections; confirm finding lineage and feedback/stopping behaviour.
5. **AI intent conformance:** every acceptance criterion maps to at least one test that fails if the criterion is removed. Use independent spec-grounded review, not only implementation-aware review.
6. **UI visual + interaction regression:** screenshots at wide, desktop, tablet and phone widths; no clipping/overlap; working keyboard navigation; clear active module/scope; errors and unavailable values honestly represented.

## Boundary of this review

The findings above are either explicitly listed in the committed generated gap ledger or described as follow-up validation targets. The counts describe that committed model snapshot. No runtime dependency, live collection source, production database or browser session was started as part of the static review; claims requiring those checks remain unverified.

## Specification / documentation boundary

Normative specification files must not Markdown-link into `docs/` reader views. Feature-scoped accepted decisions live in the owning feature's `decisions.md`; a reader-facing ADR page may be generated from that source. The semantic graph resolves stable decision identifiers such as `ADR-0028` into traceability edges without injecting a documentation path into the spec. This prevents generated prose from becoming a dependency of product intent and avoids manually synchronizing two normative copies.
