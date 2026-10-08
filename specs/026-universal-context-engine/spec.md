# Specification — Universal Context Engine (026)

**Feature**: `026-universal-context-engine`
**Input**: [input.md](input.md)
**Constitution**: `.specify/memory/constitution.md` (supersedes all other practice)
**Parent specs**: 024 §3 (Context Graph), 025 §§32–36 (query, obligations, completeness, replay)

---

## Problem

The platform has 145 sources, 67 tables, 100 event types, 134 endpoints, working entity
resolution, working independence accounting, working TDA primitives and a working query
compiler. It has no Context Graph, no projection operator, and no closed investigation loop.
It answers "what was found" and cannot answer "what does this question touch, what follows
from it, and what have we not looked for".

Because the engine does not exist, the vocabulary was closed to compensate: 53 enumerated
entity types, a SQL CHECK enforcing them, and a 14-predicate cue list. An open-world problem
with a closed apparatus degrades into a flat pile of documents around one source.

## Non-goals

- Not a new source catalogue, not a new extractor, not a new search backend.
- Not a domain-specific detector family. One engine, N domains.
- Not an MVP. Contracts land complete; components may arrive incrementally, but nothing may
  break the final domain/event contracts (constitution, "No MVP/mini-architecture").

---

## Requirements

### A. Context Graph (spec 024 §3)

- **FR-001** The Context Graph MUST exist as a first-class, durable object with the 10 node
  types of spec 024 §3.2: `Investigation`, `Question`, `Scope`, `Hypothesis`, `Task`,
  `EvidenceSet`, `Claim`, `Contradiction`, `Unknown`, `Revision`.
- **FR-002** It MUST carry the 10 edge types of §3.3: `asks`, `scopes`, `supports`,
  `contradicts`, `refines`, `delegates`, `observes`, `revises`, `derived_from`, `supersedes`.
- **FR-003** It MUST be writable only by the context layer and MUST be transactionally
  updated with its decision records (spec 024 FR-047).
- **FR-004** It MUST distinguish *unknown* from *empty*. "Not investigated" is a node, not an
  absence (§3.8).
- **FR-005** It MUST be queryable independently: current state, open obligations, satisfied
  obligations, contradictions, decisions, revision history (spec 024 FR-050).

### B. Projection operator

- **FR-010** `π(Q, W)` MUST map a `QueryIntent` and a set of accumulated `GraphInvariant`s to a
  Context Graph plus a list of gaps, deterministically.
- **FR-011** The operator MUST be decomposed into the five components of spec 024 FR-041:
  obligation generator, satisfaction evaluator, action proposer, decision recorder, revision
  manager. It MUST NOT be one module implementing all five.
- **FR-012** Every context update MUST be explainable: which input event, which rule, which
  prior state produced the new state (FR-044).
- **FR-013** Replay MUST be exact: same events + same rule versions + same parameters ⇒
  byte-identical artifacts at every declared boundary (spec 025 §36, constitution I-12).
- **FR-014** An edgeless, contradiction-free, fully-covered Context MUST converge. The loop
  terminates on saturation, never on exhaustion.

### C. Domain-independent core

- **FR-020** Ten primitives, named, each independently testable: `IDENTITY`,
  `CO_OCCURRENCE`, `ORDER`, `INTERVAL`, `CONNECTIVITY`, `CIRCULARITY`, `HIERARCHY`,
  `CONCENTRATION`, `DEPENDENCE`, `COVERAGE`.
- **FR-021** No primitive may reference a domain. There is no `family`, `ownership`, `cve` or
  `malware` inside the engine.
- **FR-022** `CIRCULARITY` MUST classify a cycle as load-bearing or inert. A 2-cycle between
  mutual references is not the same finding as circular ownership.
- **FR-023** `HIERARCHY` MUST compute transitive closure over asymmetric predicates with the
  derivation recorded per edge.
- **FR-024** `CONNECTIVITY` MUST expose articulation points and bridges. They are the
  bottleneck primitive and nothing else computes them.

### D. Open vocabulary

- **FR-030** An entity type or predicate outside every enumeration MUST be accepted and
  preserved. It MUST NOT be discarded and MUST NOT be promoted to a known type.
- **FR-031** The SQL CHECK on `entities.entity_type` MUST be relaxed. Enumerated types become
  hints for ranking and for the deterministic lane, not an admission gate.
- **FR-032** Extraction cue vocabularies MAY be extended at runtime. A predicate not in the
  list MUST still yield an edge, marked `cue_unknown`, with its span and document id.
- **FR-033** Type disagreement between two sources MUST fall back to `UNKNOWN` and be recorded
  as a conflict, never resolved by last-write-wins.

### E. Invariants grow

- **FR-040** `GraphInvariant` MUST be an append-only reducer over the entity's life-stream.
  A new event produces a delta, not a full rebuild.
- **FR-041** Every materialisation that changes the invariant MUST increment `revision` and
  record `supersedes`.
- **FR-042** A restart MUST NOT lose accumulated invariant history.
- **FR-043** Production materialisation MUST read the accumulated stream, not the records of
  one run.

### F. Temporality

- **FR-050** Every fact MUST carry `valid_from`, `valid_until` **and** `recorded_at`. "When it
  was true" and "when we learned it" are different axes.
- **FR-051** A birth date or incorporation date opens an interval; a death or liquidation
  closes it.
- **FR-052** `TemporalMode.CURRENT`, `AS_OF(t)` and `INTERVAL(a,b)` MUST be distinguishable
  against the same data. Today they are not, because transaction time does not exist.
- **FR-053** ClickHouse holds historical and materialised series; PostgreSQL holds hot
  operational state. The temporal projection MUST be reconstructable from both.

### G. Closed loop

- **FR-060** A `Gap` MUST produce a `ResearchObligation` recording trigger event, trigger
  rule, reason, parent hypothesis/contradiction, required evidence, candidate capabilities and
  priority components (spec 025 §34.1).
- **FR-061** An obligation MUST be actionable as an arbitrary NL request through the existing
  compiler, and its result MUST re-enter the invariant reducer.
- **FR-062** Observation persistence and membership MUST commit in one transaction. A failure
  between them may not leave an observation that coverage counts as placed.
- **FR-063** Saturation MUST be judged by `n_eff` (ADR-0036), not by a raw count.
- **FR-064** The loop MUST report qualified absence: what was expected, what was searched, and
  why nothing was found. Unknown detection power always yields `INFORMATIONAL_ONLY`.

### H. Ensemble

- **FR-070** One analysis pass MUST combine invariant topology, graph metrics, temporal paths
  and evidence independence into a single finding with provenance.
- **FR-071** Topology results MUST be persisted. `topological_features` may not remain a table
  nothing writes.
- **FR-072** Every analytic input MUST be reachable from `GraphInvariant`, so the ensemble reads
  the same structure the UI reads.

### I. UI criterion

- **FR-080** A console run started from NL MUST produce a navigable Context Graph: question →
  hypothesis → task → evidence → claim → contradiction → revision.
- **FR-081** Every derived edge MUST display its derivation. Every gap MUST display the
  obligation it raised.
- **FR-082** Every displayed statement MUST resolve back to raw observations. Content invented
  to look complete is a failure, not a presentational choice.
- **FR-083** No screen may display a number that no code path measured.

---

### J. Entity enrichment is the exit condition

The platform's obligation for an entity inside a context is not to answer once. It is to
drive the entity to exhaustion — everything the applicable sources can say about it — and to
be exact about the difference between *we asked and there was nothing*, *we could not ask*,
and *we did not think to ask*. Collapsing those three is how an engine reports itself
finished while holding nothing.

- **FR-090** Every entity in a context MUST have an addressable profile: per attribute, the
  values, the contributing sources, and a coverage state.
- **FR-091** Coverage MUST distinguish `ACQUIRED`, `EMPTY` (a source ran and reported no such
  attribute), `REFUSED` (the capability exists but cannot run here), `CONFLICT` (sources
  disagree) and `UNKNOWN` (nobody tried). Only `UNKNOWN` generates work.
- **FR-092** Enrichment MUST continue until no attribute remains `UNKNOWN`. Stopping earlier
  is a defect even when every question in view is answerable.
- **FR-093** Saturation MUST be measured over the **expected surface** — what we know plus
  what the available capabilities declare we could know. Measured over held attributes
  alone, an entity the platform knows nothing about scores zero unknown and declares itself
  saturated, halting the loop before the first fetch.
- **FR-094** A capability that cannot run MUST be reported as a blocked source on the gap and
  MUST NOT be rescheduled. A capability gap is visible; an infinite retry is not.
- **FR-095** Corroboration MUST count independence groups, not distinct sources. Two outlets
  running one wire story are one source of evidence however many URLs carry it (ADR-0036).
- **FR-096** Source disagreement MUST be recorded as `CONFLICT` with all values retained and
  MUST NOT be resolved by arrival order.
- **FR-097** Capabilities MUST be declared as data discoverable at runtime (spec 024 §4.7). An
  attribute no enumeration has heard of MUST still be planned for when some source offers it.
- **FR-098** The planner MUST NOT invent attributes. Everything it plans is named by some
  capability offer.

---

## Success criteria

1. `rg -il context_graph` matches real modules, tables and routes.
2. One `π(Q, W)` implementation answers five domains: ownership chain, bottleneck, collusion,
   family, vulnerability — with no domain branch inside it.
3. A restart loses no invariant revision and no Context Graph node.
4. `AS_OF(t)` differs from `CURRENT` on data that changed.
5. A gap in the graph reaches a real source request and the answer returns to the graph.
6. An entity entered into a context is driven to saturation: nothing readable remains
   `UNKNOWN`, and every blocked capability is visible as such.
7. The analyst confirms the screen. Nothing else counts.
