# Plan — Universal Context Engine (026)

**Spec**: [spec.md](spec.md) · **Audit**: [input.md](input.md)

---

## Architecture

```
NL ──► QueryAST ──► QueryIntent                    (exists)
                       │
                       │  Q                      W = accumulated GraphInvariants
                       ▼                              (exists, does not yet grow)
        ┌──────────────────────────────────┐
        │  π(Q, W)  projection operator      │   pure, deterministic, science layer
        │  seed · poll · fuse · frame       │
        │  recurse · back-link · close ·gap │
        └──────────────────────────────────┘
             │                          │
      ContextGraph                 Gap[]
      (durable, 10/10)                  │
             │                    ObligationGenerator ──► ActionProposer
             │                              │
             │                    NL → QueryAST → source request
             │                              │
             │                       acquisition
             │                              │
             │                     Observation → InvariantReducer → W'
             │                              │
             └──── SatisfactionEvaluator ◄───┘
                          │
                  RevisionManager → DecisionRecorder → ContextGraph revision
```

**Layer placement.** `π` and the ten primitives are pure functions in
`apps/science/context/` — no I/O, no clock, no randomness (spec 024 FR-043, FR-049).
`ContextGraph`, `InvariantReducer`, the obligation/action/decision/revision components and
all persistence live in `apps/control-plane/context_engine/`. Science never writes durable
state; control-plane never decides anything.

---

## Phases

Each phase ends in a **runnable vertical**, not a module in a box. F1 is done; F2 is next.

### F1 — Make the analytic substrate reachable — **DONE**

The GUDHI stage computed perfect barcodes that nothing could reach. Four defects, all fixed,
plus the missing converter:

| Fix | Site |
|---|---|
| index lookup `KeyError` | `graph/adjacency.py:149` |
| isolated nodes dropped | `graph/adjacency.py:42` |
| `filtration = vertex index` → real time | `tda/pipeline.py:64` |
| ignored `fan` → topology + structure hash | `tda/__init__.py:82` |
| `persistence_dim_max` erasing H0 | `tda/bridge.py:persistence_of` |
| **new** converter | `tda/bridge.py` |

Deliverable: `FiltrationInput` with a named scale, a digest per window, a multiplex
conversion, and a refusal to pool mixed units. Verified by
`apps/projection/tests/contract/test_tda_bridge_contract.py` (30 tests) and the pre-existing
projection suite (278 passed, 0 regressions).

**Why first:** everything analytic downstream is blocked on it, and it was reachable only from
tests.

### F2 — Invariants grow

`GraphInvariant` is the substrate; today it is a snapshot of one run wearing an invariant's
name.

1. `InvariantReducer` in control-plane: stream of `entity_stream` rows → new `TemporalSlice`
   values → `revision += 1` when the digest changes → `supersedes` the prior revision.
2. `with_links()` stops being the only mutation path; it records supersession.
3. Production materialisation reads the accumulated stream
   (`workflows/temporal_materialization.py:133` currently reads the current run).
4. Invariants persist. A restart resumes at the last revision.

**Gate:** 10 events over 3 runs ⇒ `revision == 10`, an unbroken `supersedes` chain, and a
restart that loses nothing.

### F3 — The two missing primitives

7 of the 10 primitives already work. These two do not exist in any form.

- **CIRCULARITY** — cycle detection over the claim graph, each cycle classified load-bearing
  or inert. The classification is the finding; the cycle is only its evidence.
- **HIERARCHY over predicates** — transitive closure over asymmetric predicates, with a
  derivation per derived edge. `domain/schema.py:descendants_of` does this for *types* and is
  the right shape; this does it for *claims*.

**Gate:** a chain `A owns B, B owns C` yields `A owns C` with a derivation; `A owns B, B owns A`
is classified, not dropped; a predicate that appears in neither any enum nor any cue list
still produces an edge.

### F4 — Context Graph and π — the core

1. Durable `ContextGraph` with all 10 node and 10 edge types, transactional, tenant-scoped.
2. `π(Q, W)` split into the five components of FR-011, starting with the linear projection
   (steps 1–4, 7–8) and no recursion.
3. Then recursion: a subgraph per node of each articulation centre, back-linked by
   `contains` / `belongs_to`.

**Gate:** five domains, one `π`, no domain branch. F4 is split 4a/4b because the recursive
part is the only genuinely unpredictable piece of the plan.

### F5 — Close the loop

`Gap` → `ObligationGenerator` → `ActionProposer` → NL → acquisition → observation →
`InvariantReducer` → new Context Graph revision. Saturation by `n_eff`.

Requires F2 (the reducer) and F4 (the graph) to exist; until then obligations are produced
and dropped.

Also in this phase: single-transaction observation persistence and membership (FR-062), which
today can leave an observation that coverage counts as placed.

### F6 — Temporality

1. `recorded_at` on every fact, alongside `valid_from`/`valid_until`.
2. Interval from birth/incorporation to death/liquidation.
3. ClickHouse live: fix the port mismatch (compose `18123` vs env `8123`), remove the silent
   env gate, add the missing series writer.
4. `AS_OF(t)` distinguishable from `CURRENT`.

### F7 — Ensemble and UI

One pass combining invariant topology + graph metrics + temporal paths + independence into a
persisted finding, and the console view of the Context Graph. This is where FR-080–083 are
met, and it is the last phase because it must render something real.

---

## Ordering rationale

F1 → F2 → F3 → F4 → F5 → F6 → F7.

- F1 blocks all analysis.
- F2 is the substrate; without it there is no `W` to project, only a pile of documents.
- F3 before F4: the projection needs both primitives to produce a hierarchy rather than a list.
- F5 before F6: the loop produces observable value first; temporal precision can be added
  afterwards without reworking the architecture. `AS_OF` is already public API and currently
  indistinguishable from `CURRENT` — a real debt, but a smaller one than an engine that runs
  once instead of iterating.
- F7 last: the console must render finished work.

## Risks

| Risk | Mitigation |
|---|---|
| F4b recursion exceeds its estimate | 4a is separately gated; the linear projection is already a working engine |
| Closing the predicate vocabulary breaks disambiguation | default + learn from data; never hard-fail on an unknown predicate |
| `derive_temporal_relations` O(n²) with a hard `raise` | ADR-0022 already specifies the sweep-line fix; scheduled in F6 |
| Open vocabularies flood the graph with noise | noise is handled by ranking and `DEPENDENCE`, not by a whitelist |

## Out of scope for this plan

Rust crate entry points, browser automation, Redis leases, OpenSearch-vs-Quickwit, Alembic
pre-014 history, the AGPL question on the donor catalogue. All are real and none is on the
critical path to a Context Graph an analyst can read.
