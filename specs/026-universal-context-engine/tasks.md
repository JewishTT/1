# Tasks — Universal Context Engine (026)

**Plan**: [plan.md](plan.md) · **Spec**: [spec.md](spec.md) · **Audit**: [input.md](input.md)

Statuses: `[x]` delivered · `[ ]` open · `[~]` partial · `[!]` blocked, reason stated.

---

## F1 — Analytic substrate reachable — DONE

| # | Task | Status | Evidence |
|---|---|---|---|
| 026-F1-01 | `to_distance_matrix` index bug (`KeyError: 0`) | [x] | `graph/adjacency.py:149` |
| 026-F1-02 | `to_tda_input` drops isolated nodes | [x] | `graph/adjacency.py:42` |
| 026-F1-03 | `DirectionalFlagProvider` filtration = vertex index | [x] | `tda/pipeline.py:64`, real `times` |
| 026-F1-04 | `TopologicalInvariant.run` ignored `fan` | [x] | `tda/__init__.py:82`, `generator v2` |
| 026-F1-05 | gudhi erases H0 on an edgeless filtration | [x] | `tda/bridge.py:persistence_of` |
| 026-F1-06 | Converter `(nodes, triples) → Filtration` | [x] | `tda/bridge.py` (new) |
| 026-F1-07 | Mixed-scale filtration refused | [x] | `ScaleKind.MIXED` guard |
| 026-F1-08 | Clique-vs-path distinguishable | [x] | `fan_digest` alongside `fan_features` |
| 026-F1-09 | Multiplex: one filtration per window, bounds in provenance | [x] | `multiplex_filtrations` |
| 026-F1-10 | Contract suite | [x] | `tests/contract/test_tda_bridge_contract.py`, 30 tests |
| 026-F1-11 | Projection suite green | [x] | 278 passed, 2 skipped, 0 regressions |

---

## F2 — Invariants grow

| # | Task | Status | Notes |
|---|---|---|---|
| 026-F2-01 | `InvariantReducer`: stream → delta | [x] | `context_engine/invariant_reducer.py`: `reduce`/`restore`/`history`, unit contract |
| 026-F2-02 | `revision` increments when the digest changes | [ ] | `workflows/temporal_materialization.py:133` hardcodes `revision=1` |
| 026-F2-03 | `supersedes` recorded on invariants | [ ] | field exists on claims (`relation_claim.py:215`), absent on invariants |
| 026-F2-04 | `with_links()` records supersession | [ ] | `graph_invariant.py:630` |
| 026-F2-05 | Production reads the accumulated stream | [ ] | reads current-run records today |
| 026-F2-06 | Invariant persistence + restart resume | [ ] | |
| 026-F2-07 | Gate: 3 runs ⇒ 10 revisions, no restart loss | [ ] | |

---

## F3 — Missing primitives

| # | Task | Status | Notes |
|---|---|---|---|
| 026-F3-01 | CIRCULARITY: cycle detection over claims | [x] | `context/circularity.py`, Johnson SCC, no domain hardcoding |
| 026-F3-02 | CIRCULARITY: load-bearing vs inert | [x] | `LOAD_BEARING`/`INERT`/`SUSPECT` with stated reasons |
| 026-F3-03 | HIERARCHY: transitive closure over predicates | [x] | `context/hierarchy.py`, transitivity declared as data |
| 026-F3-04 | HIERARCHY: derivation per derived edge | [x] | `DerivedEdge` carries the derivation |
| 026-F3-05 | Unknown predicate still yields an edge | [x] | laws default empty, no name whitelist |
| 026-F3-06 | Gate: chain ⇒ derived edge; cycle classified | [~] | 59 + 65 contract tests pass; neither is called from production π yet (F4-10) |

---

## F4 — Context Graph and π

| # | Task | Status | Notes |
|---|---|---|---|
| 026-F4-01 | Durable `ContextGraph`, 10 node types | [x] | `context_engine/context_graph.py`: 10 node types, content-derived ids, durable store protocol |
| 026-F4-02 | 10 edge types | [x] | 10 edge types + `EDGE_ENDPOINTS` shape table; invalid shape refused at write time |
| 026-F4-03 | Transactional with decision records | [x] | `PostgresContextGraphStore.apply` is one transaction; rollback verified on a real database |
| 026-F4-04 | `Unknown` node distinct from absence | [x] | `Unknown` is a node type; `state_of` returns empty/unknown/known, `open_unknowns()` enumerates the open ones |
| 026-F4-05 | ObligationGenerator | [ ] | FR-011 component 1 |
| 026-F4-06 | SatisfactionEvaluator | [ ] | component 2 |
| 026-F4-07 | ActionProposer | [ ] | component 3 |
| 026-F4-08 | DecisionRecorder | [ ] | component 4 |
| 026-F4-09 | RevisionManager | [ ] | component 5 |
| 026-F4-10 | π linear: seed · poll · fuse · frame · close · gap | [ ] | F4a |
| 026-F4-11 | π recursive: subgraph per articulation node, back-linked | [ ] | F4b |
| 026-F4-12 | Gate: 5 domains, one π, no domain branch | [ ] | the acceptance criterion |
| 026-F4-13 | Audit trail per write (FR-003) | [x] | `DecisionRecord` with actor + rationale + what changed; `audit_trail()` |
| 026-F4-14 | Replay converges | [x] | content-derived ids + endpoint unique constraint; 21 contract tests |
| 026-F4-15 | Tenant isolation verified | [x] | another tenant reads empty; every statement filtered by `tenant_id` |
| 026-F4-16 | `question` written with its scope atomically | [x] | a question visible without its scope cannot be answered correctly |

---

## F5 — Close the loop

| # | Task | Status | Notes |
|---|---|---|---|
| 026-F5-01 | `Gap` → obligation with full provenance | [ ] | spec 025 §34.1 |
| 026-F5-02 | Obligation → arbitrary NL request | [ ] | compiler exists |
| 026-F5-03 | Result → `InvariantReducer` → W′ → π | [ ] | the loop |
| 026-F5-04 | Single-transaction persist + membership | [ ] | `InterpretationBridge` splits them today |
| 026-F5-05 | Saturation by `n_eff` | [ ] | `coverage.py` provides it |
| 026-F5-06 | Qualified absence surfaced | [ ] | FR-064 |

---

## F6 — Temporality

| # | Task | Status | Notes |
|---|---|---|---|
| 026-F6-01 | `recorded_at` on every fact | [ ] | 0 occurrences outside migration 023 |
| 026-F6-02 | Interval from birth/incorporation to death/liquidation | [ ] | FR-051 |
| 026-F6-03 | ClickHouse reachable (port + env gate) | [!] | compose `18123` vs env `8123`; no service |
| 026-F6-04 | Series writer for `entity_series` | [ ] | DDL exists, no adapter |
| 026-F6-05 | `AS_OF(t)` ≠ `CURRENT` | [ ] | FR-052 |
| 026-F6-06 | `derive_temporal_relations` sweep line, soft budget | [ ] | ADR-0022, 0% |
| 026-F6-07 | Interval algebra (13 Allen) | [ ] | ADR-0035, 0% |

---

## F7 — Ensemble and UI

| # | Task | Status | Notes |
|---|---|---|---|
| 026-F7-01 | One pass: topology + metrics + paths + independence | [ ] | FR-070 |
| 026-F7-02 | `topological_features` actually written | [ ] | table exists, 0 INSERTs |
| 026-F7-03 | Console: question → … → revision navigation | [ ] | FR-080 |
| 026-F7-04 | Every derived edge shows its derivation | [ ] | FR-081 |
| 026-F7-05 | Every gap shows the obligation it raised | [ ] | FR-081 |
| 026-F7-06 | Every statement traces to raw observations | [ ] | FR-082 |
| 026-F7-07 | No unmeasured number on any screen | [ ] | FR-083; `api/routes/metrics.py:37` returns hard-coded throughput |

---

## F2b — Enrichment core

| # | Task | Status | Notes |
|---|---|---|---|
| 026-F2b-01 | `Coverage`: 5 states, only UNKNOWN generates work | [x] | `context/enrichment.py` |
| 026-F2b-02 | `CapabilityOffer` as data, open kinds and attributes | [x] | spec 024 §4.7 |
| 026-F2b-03 | `EntityProfile` with per-attribute provenance | [x] | |
| 026-F2b-04 | Order-independent conflict merge | [x] | arrival order cannot decide |
| 026-F2b-05 | `plan_enrichment` → gaps + blocked sources | [x] | |
| 026-F2b-06 | Saturation over the **expected surface** | [x] | empty-profile defect found and fixed |
| 026-F2b-07 | Corroboration by independence group | [x] | ADR-0036 |
| 026-F2b-08 | Contract suite | [x] | `tests/contract/test_enrichment_contract.py`, 33 tests |
| 026-F2b-09 | Offers loaded from the live source catalogue | [x] | `sources/capabilities.py`: 145 offers, 206 distinct attributes |
| 026-F2b-10 | Profile built from `GraphInvariant` + claims | [~] | live profile + invariant + dossier build together via `enrichment_service.py`; claims-store side absent |
| 026-F2b-11 | Gaps become obligations in the loop | [ ] | needs F4/F5 |
| 026-F2b-12 | `EnrichmentService`: subject -> sources -> invariant -> dossier | [x] | live run on `example.com`: 30 sources, 26 events, invariant folded, dossier `2/2` traced facts |
| 026-F2b-13 | A dead source cannot close a gap | [x] | up to 3 candidates per gap; verified against a live 401/429/503 mix |
| 026-F2b-14 | Echo, shape and attribution refusals | [x] | `ip=example.com` and `organization=Wikipedia` refused; 10 tests in `test_to_entities_honesty.py` |
| 026-F2b-15 | `Dossier` core: timeline, links, contacts, gaps, conflicts | [x] | `context/dossier.py`, 49 contract tests |
| 026-F2b-16 | Timeline never claims coverage it did not have | [x] | a 1995 event produced 1627 weekly windows; unswept ones counted, not rendered |
| 026-F2b-17 | Dossier reader, API route, UI surface | [x] | `api/routes/dossier.py` + `/dossier` in the webapp; 5 views (coverage/timeline/links/sources/gaps), gaps resolved to source names at the API boundary |
| 026-F2b-18 | `applies_to` mismatch: `person` gets 0 offers | [x] | not a vocabulary gap: offers declare *input shapes*. Service selects by the shape of the value; person 0 -> 57 sources / 117 attrs |
| 026-F2b-19 | Sweep survives its process | [x] | `PostgresEnrichmentSink` -> `entity_stream`, sequence continues from stream max |
| 026-F2b-20 | Dossier rebuilt from persisted rows | [x] | `DossierReader`; re-folds the invariant rather than reading a second copy of state |
| 026-F2b-21 | Values keep their source through the round trip | [x] | facts travel in `entity_stream.payload`; `entity_facts` has no source column |
| 026-F2b-22 | An unswept subject is not a complete one | [x] | `Saturation.ratio`/`is_saturated` returned 1.0/True on an empty surface |
| 026-F2b-23 | `offers_for_query_kinds` | [x] | union by declared input shape, deduped by source; no kind-to-kind mapping invented |
| 026-F2b-24 | Re-sweep appends instead of colliding | [x] | `record_hash` now includes event time; found by running against a real database |
| 026-F2b-25 | Dossier API: sweep, read, list | [x] | `POST /dossier/enrich`, `GET /dossier/{ref}`, `GET /dossier`; 404 for an unswept subject, never a blank dossier |
| 026-F2b-26 | Dossier UI surface | [x] | `DossierPage`/`DossierContainer` on the design-system primitives; refusal, coverage and dormant-window honesty asserted in 10 tests |
| 026-F2b-27 | Sweep result survives to the next process | [x] | sequence continues from the stream max; re-sweep appends rather than colliding |

---

## Cross-cutting

| # | Task | Status | Notes |
|---|---|---|---|
| 026-X-01 | Relax `entities.entity_type` CHECK | [ ] | FR-031; 53-value whitelist blocks open vocabulary |
| 026-X-02 | Unknown kinds preserved, not dropped | [x] | `axis != 'entity'` demoted them; only `axis == 'value'` does now. `unclassified` was unreachable |
| 026-X-03 | ProjectionLayer referent ids use `source_id` | [ ] | `scope_id` receives `""` today |
| 026-X-04 | Predicate vocabulary extendable at runtime | [ ] | FR-032 |
| 026-X-05 | Type conflict → `UNKNOWN` + recorded conflict | [ ] | FR-033 |
| 026-X-06 | Migration 023 `NOT VALID` claim matches DDL | [x] | raw `ALTER TABLE ... NOT VALID` via `_add_check`; also fixed `sa.JSONB`, which does not exist |

---

## Blocking dependencies outside this plan

Recorded so they are not re-discovered: Rust crates without entry points, `worker-browser`
without a renderer, no consumer of `acquisition.request`, Alembic history starting at 014,
Redis declared without a client, `tantivy_backend` a 22-line stub, 37 declaration-only events,
auth stub granting `ADMIN` on a missing token, and the unresolved AGPL reading of the donor
catalogue.
