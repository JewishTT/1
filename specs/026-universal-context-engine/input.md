# 026 — Universal Context Engine: verified platform audit

**Feature**: `026-universal-context-engine`
**Date**: 2026-10-08
**Status**: audit complete, plan ratified, F1 delivered
**Supersedes**: nothing. **Depends on**: `.specify/memory/constitution.md`, spec 024 §3, spec 025 §§32–36.

This document states what the platform **is**, verified against source. Where it contradicts a
spec or a docstring, the source wins and the discrepancy is named.

---

## 1. What exists

| Layer | Size | Verified state |
|---|---|---|
| `apps/shared` | 40 654 LOC | contracts, event catalog, storage, graph invariants, coverage, semantic fabric |
| `apps/control-plane` | 39 367 LOC | 14 routers, 26 route modules, 134 endpoints, investigations, frontier, Temporal workflows |
| `apps/interpretation` | 25 606 LOC | parsers, 5 deterministic extractors, relation extraction, 15-kind relation substrate |
| `apps/science` | 15 645 LOC | calibrated claims, hypotheses, inference, query compiler, coverage |
| `apps/acquisition` | 13 356 LOC | 145-source catalogue, dispatcher, worker runtimes, 8 Rust crates |
| `apps/projection` | 6 377 LOC | graph abstraction, GUDHI TDA, community metrics, temporal paths, ClickHouse client |
| `apps/admission` | 1 904 LOC | blocking/resolution ladder, source independence, temporal consistency |
| `apps/feedback` | 602 LOC | stopping policy, 3 branch types |
| tests | 62 565 LOC | `apps/shared` 16 109, `apps/interpretation` 13 171, `apps/control-plane` 12 041 |
| data model | 67 ORM tables, 10 migrations | `023_derivation_enforcement` is head |
| events | 100 catalogued types | 63 have code references, **37 are declaration-only** |

**Working, and worth building on — not rewriting:**

- `GraphInvariant` / `StaticObject` (`apps/shared/domain/graph_invariant.py:483,569`) — two
  object kinds, lifecycle `NASCENT/GROWING/STABLE/DECAYING/DORMANT`, epoch-aligned half-open
  windows, deterministic `integrity_digest`, `to_tda_input` / `to_multiplex` /
  `window_tda_input`.
- `apps/science/context/coverage.py` — ADR-0036 in full: `EvidenceDependencyGroup`,
  `IndependenceAssessment.n_eff` reported beside the raw count, `CoverageQualifiedAbsence`
  with the "unknown detection power ⇒ `INFORMATIONAL_ONLY`" rule enforced at line 311.
- GUDHI TDA — `SimplexTree`, `insert_batch`, `persistence`; features `bottleneck`,
  `wasserstein`, `landscapes`, `betti_curve`, `drift`, `persistence_entropy`, `amplitude`.
- Metrics — `label_propagation` + Newman–Girvan `modularity`, `reachable_from`, `journey`,
  temporal motifs, power-law α, Watts–Strogatz σ, hypergraph metrics.
- N-ary hypergraph without clique blowup — `HyperEdge`, `incidence_complex()`
  (`graph/abstraction.py:97-251`).
- `QueryIntent` (`apps/science/context/completeness.py`) — six objectives including
  `UNIVERSAL_NEGATIVE`, `TemporalMode` `CURRENT|AS_OF|INTERVAL`. **The query half of the
  engine exists.**
- `InterpretationBridge` — real bytes → mentions → referents → entities → candidates →
  `entity_stream`, tenant-scoped, provenance on every edge.

---

## 2. Gates, and what each one actually does

| Gate | Location | Blocks / admits | Wired? |
|---|---|---|---|
| Admission ladder | `apps/admission/engine/` | admit / defer / reject / quarantine | yes |
| Entity resolution | `apps/admission/resolution/`, `domain/entity_identity.py` | merges two references or refuses | yes |
| Evidence independence | `apps/science/context/coverage.py:48,116` | weights correlated evidence once | yes |
| Policy / budget | `apps/control-plane/cp_domain/policy.py` | whether work may start | **hardcodes `policies/default` / `budget/default` regardless of tenant** |
| Frontier lease | `services/frontier.py` | dequeues work | Postgres columns; **no Redis client exists** |
| Feedback | `apps/feedback/` | findings alter next acquisition | in-memory only |
| Projection rebuild | `apps/projection/graph/snapshot.py:68` | rebuild from offsets | `projection_id` generated and unused; `rebuild()` always from offset 0 |
| Scope limits | `apps/acquisition/dispatcher/scheduler.py:58` | resource limiting | `ScopeLimits.allows()` returns `(True, "")` — **a no-op** |

---

## 3. Missing links

### 3.1 Context Graph does not exist

`specs/024.../input.md` §3 requires a first-class, durable, independently writable graph with
10 node types (`Investigation`, `Question`, `Scope`, `Hypothesis`, `Task`, `EvidenceSet`,
`Claim`, `Contradiction`, `Unknown`, `Revision`) and 10 edge types (`asks`, `scopes`,
`supports`, `contradicts`, `refines`, `delegates`, `observes`, `revises`, `derived_from`,
`supersedes`).

Verified: `rg -il context_graph` over the repository returns **zero** matches outside the
spec that demands it. Wave 0 already recorded this as `FALSE — does not exist`.

This is the structural gap. Everything below it exists; this does not, and the constitution's
"the user creates an Investigation, not a graph" has nothing to materialise the Investigation
into.

### 3.2 No projection operator

Nothing turns a goal plus accumulated invariants into a question-specific subgraph. The two
nearest things are not it:

- `apps/science/context/semantic_graph.py` — a flat container of nodes and edges. No subgraph
  objects, no inference rules, no transitive closure, no recursive expansion.
- `apps/science/context/lattice.py` — closure over **co-occurrence**, not over predicates.

### 3.3 The graph→TDA bridge was absent

Four defects made the entire L3 topology stage inert. All four are now fixed (F1).

| Defect | Site | Effect |
|---|---|---|
| `lookup[source]` on index triples | `graph/adjacency.py:157` | `KeyError: 0`; 0 callers, 0 tests |
| nodes collected from edges only | `graph/adjacency.py:42` | an isolated vertex vanished |
| `filtration=float(b)` — vertex index, not time | `tda/pipeline.py:86` | filtration measured alphabet order |
| `persistence_dim_max=False` | gudhi default | erased H0 exactly for an edgeless filtration |

The unit test `test_pipeline_directed.py:66` copied `float(b)` verbatim, so the third defect
was structurally unfalsifiable.

### 3.4 Invariants are rebuilt, not enriched

- `workflows/temporal_materialization.py:133` — `revision=1`, hardcoded, built from the
  records of the **current run** (usually one capture), not from the accumulated stream.
- `GraphInvariant.with_links()` (`:630`) changes the digest but not the revision, and records
  no supersession.
- `docs/architecture/dynamic-entity-invariant.md:46` claims features are stored as time
  series in ClickHouse. No such consumer exists; the only implementation is
  `MemoryTemporalFeatureTable` (`projection/temporal_materialization/features.py:41`), used by
  tests only.

### 3.5 No bitemporality

`recorded_at` occurs **zero times** outside the table I added in migration 023. The platform
has valid-time only. "True since March" and "we learned it in September" are the same row,
so a fact learned late about an earlier period cannot be represented.

### 3.6 Temporal algebra is specification only

`temporal_algebra.py` does not exist. ADR-0035 (13 Allen relations, disjunctive value sets)
is 0% implemented; the code has five relations (`PRECEDES`, `FOLLOWS`, `OVERLAPS`, `CAUSES`,
`CO_OCCURS`). ADR-0022 (sweep line, soft event budget) is 0%; `derive_temporal_relations`
is still O(n²) and still `raise`s at `max_events`.

### 3.7 No ensemble

`rg -ni ensemble` over `apps/` and `docs/`: **zero**. Three isolated islands:

```
A  api/routes/network.py      live; TDA via a *different* engine (apps/science/scitda);
                              output is a JSON response, nothing persisted
B  projection/tda/*           GUDHI; correct; called only from projection/tests/**
C  domain/graph_invariant.py  to_tda_input / to_multiplex exist; 0 production callers
```

`topological_features` is a table that is never written (`TopologicalFeature(` appears once,
as an in-memory dataclass).

### 3.8 No cycle, no hierarchy

`CIRCULARITY` does not exist in any form — no cycle detection, and no way to distinguish a
load-bearing cycle (circular ownership) from noise (two mutual references).

`HIERARCHY` exists only over *types* (`domain/schema.py:descendants_of`). Transitive closure
over *predicates* does not exist, so an ownership chain never yields derived ownership.

### 3.9 Unknown evidence is lost

- `apps/interpretation/parsers/to_entities.py` routes anything whose `axis_for()` is not
  `"entity"` into values. `axis_for("unknown")` returns `"value"`, so the unknown branch in
  `_entity_for()` is unreachable.
- `ProjectionLayer` passes `getattr(definition, "source", "")` to `referent_id_for(... scope_id=...)`,
  making every referent id `""`-derived for that path.

The constitution requires "unknown relation type ≠ discard relation signal" (I-2, §0.2). At
present the platform discards it.

### 3.10 The loop is not closed

`run_fabric` (`apps/science/context/fabric.py`) generates `ResearchObligation`s. Nothing routes
those to acquisition and feeds the result back into the invariant reducer. `persist()` and
`append_stream()` in `InterpretationBridge` are separate transactions, so a failure between
them leaves an observation with no membership — counted as placed.

---

## 4. Unimplemented services

| Service | State | Evidence |
|---|---|---|
| MinIO / S3 | unreachable | port 9000/9001 closed; no `minio` package |
| Redpanda / Kafka | unreachable | 9092 closed; compose still ships Confluent under `legacy-kafka` |
| Temporal | unreachable | 7233 closed; workflows therefore untested end to end |
| SearXNG | unreachable | 8080 closed; `SRC-searxng` observations exist from an earlier session |
| Neo4j | unreachable | 7700 closed; and demoted to serving-only by ADR-0027 |
| OpenSearch | unreachable | search backends target Quickwit mappings; no Quickwit service in compose |
| ClickHouse | client + 3 DDL real, execution gated | `pow_run.py:529` returns `None` without `CLICKHOUSE_URL`; compose maps host **18123** while `.env.example` says **8123**; `settings.clickhouse_url` is never read |
| Redis | declared, no client | `services/frontier.py:3` |
| Rust crates | no `fn main`, no `[[bin]]` | produce rlibs only |

---

## 5. Closed vocabularies: the architectural contradiction

Spec 025 §32 requires `subject_class: wallet_control_cluster`, and the platform is meant to
handle "military-political games" and "asset tracing" through **one** engine. That is only
possible if the vocabulary is open.

What exists instead is a closed apparatus built over the catalogue:

- `EntityType` — 53 enumerated values.
- `ENTITY_TYPE_VALUES` — the same 53 copied into a SQL CHECK on `entities.entity_type`.
- 126 catalogue `parse:` blocks with closed `kind:` vocabularies.
- 14 relation predicates from `apps/interpretation/relations.py:_CUE_SPECS`, plus a global
  `RelationArityMode` with a single `_DIRECTIONAL_MODES` rule.

A closed vocabulary is why "family composition" produced a flat pile around one source: the
words that mattered (`owned_by`, `part_of`, `controls`) had nowhere to go except a 14-entry
cue list, and everything outside it was `UNKNOWN` and dropped.

**Decision**: types and predicates become *hints* for ranking and for the deterministic lane.
They stop being a whitelist. `unknown` is a value that is preserved, not a rejection.

---

## 6. The engine, stated once

```
NL  →  QueryAST  →  QueryIntent           (exists)
                    │
      Q             ▼            W  = accumulated GraphInvariants
    ┌───────────────────────────────┐
    │  π(Q, W)  — projection        │
    │  1 seed      terms → entries  │   IDENTITY, CO-OCCURRENCE
    │  2 poll      1-hop periphery  │   CO-OCCURRENCE
    │  3 fuse      shared context   │   CO-OCCURRENCE
    │  4 frame     articulation pts  │   CONNECTIVITY
    │  5 recurse   subgraph per node│   CONNECTIVITY, HIERARCHY
    │  6 back-link contains/belongs │   HIERARCHY
    │  7 close     transitive closure│   HIERARCHY, CONCENTRATION
    │  8 gaps      what is missing  │   COVERAGE
    └───────────────────────────────┘
              │                        │
       ContextGraph            Gap[]  →  Obligation  →  NL action
       (durable, 10/10)                    │
                                    acquisition
                                         │
                              observations → W'  →  π again
```

Ten domain-independent primitives. Any question is a composition of them; no domain is named
anywhere in the engine.

| Domain | Composition |
|---|---|
| family composition | HIERARCHY + ORDER + CO-OCCURRENCE |
| ownership map | HIERARCHY + INTERVAL + CIRCULARITY |
| vulnerability | CONNECTIVITY + ORDER + CO-OCCURRENCE |
| bottleneck | CONNECTIVITY (cut vertices, bridges) |
| collusion | CIRCULARITY + CONCENTRATION + CO-OCCURRENCE |

---

## 7. Acceptance

One production code path answers every domain above. Not five functions, not five adapters —
one `π(Q, W)` and one Context Graph, with the domain living only in `QueryIntent` and in the
evidence itself.

**UI criterion (sole success definition):** a run started from NL in the console produces a
Context Graph the analyst can navigate — question → hypothesis → task → evidence → claim →
contradiction → revision — with every derived edge carrying its derivation and every gap
carrying the obligation it raised. What the analyst sees must be reconstructable back to raw
observations; anything invented to look complete is a failure even if the screen is full.
