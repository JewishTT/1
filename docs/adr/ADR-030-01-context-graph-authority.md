# ADR-030-01 — ContextGraph is authoritative durable state for research-process relationships only

- **Status**: Accepted
- **Date**: 2026-10-17
- **Feature**: `030-global-platform-upgrade`
- **Implements**: T016
- **Cites**: FR-030, Constitution P8, P9, Principle III, ADR-0027, ADR-0028
- **Supersedes nothing**; narrows ADR-0027 §1 from "all operational and research graph state" to the
  research-process subset named below

## Context

ADR-0027 already settled the store question: PostgreSQL is authoritative, Neo4j is a rebuildable
serving projection, and no third graph copy may be introduced. What it did **not** settle is the
question FR-030 actually asks, which is narrower and sharper: *which* state is authoritative, and
*for what*.

The distinction matters because "the graph is authoritative" is true of two different things that
this repository keeps separately.

**[MEASURED]** The Context Graph exists and is durable. `PostgresContextGraphStore` is declared at
`apps/control-plane/context_engine/context_graph_store.py:74`, and its `apply()` method
(`:80`) carries the signature
`async def apply(self, tenant_id: str, transaction: Transaction) -> DecisionRecord`. Two properties
follow from that signature and both are load-bearing: the caller supplies the transaction, so the
graph mutation is not independently committed; and the method returns the `DecisionRecord` it wrote,
so the revision advance and its justification are one indivisible unit. This is the storage-layer
form of CE-001 §13.5. It already holds. Migration `025_context_graph.py` exists in
`apps/control-plane/db/migrations/versions/`, so the tables are on the schema history, not only in
code.

**[MEASURED]** The thing this ADR must *not* claim authority over is the real-world entity relation
stream. That lives in a different place with different semantics: `EntityFact` is declared at
`apps/control-plane/db/schema.py:2768`, and migration `023_derivation_enforcement.py` adds
`recorded_at` alongside `valid_from` with the distinction written into the migration itself
(`:128`) — *"`recorded_at` is when we learned it; `valid_from` is when it was true."* A relation
asserted about the world is evidence-bearing and revisable. A research-process relationship — "this
obligation is supported by that observation" — is process bookkeeping. Treating the second as though
it carried the authority of the first is the specific failure ADR-0027's Principle IV warns about,
and it is the failure that produces a graph which looks authoritative and is not.

**[MEASURED]** A second live risk sits alongside this one. `neo4j` 5.21 is a declared dependency of
`apps/control-plane` with **no matching configuration variable** in `.env.example`
(`research.md §1.3`; `plan.md §Technical Context`). The driver is installed, the service is
unconfigured. ADR-0027 makes Neo4j a projection; an unconfigured projection driver is a live
foot-gun for exactly the "library installed ≠ service available" mistake.

## Decision

**D1 — Authority is scoped by kind, not granted globally.**

`ContextGraph`, backed by `PostgresContextGraphStore`, is authoritative durable state **for
research-process relationships only**: obligations, actions, attempts, decisions, hypotheses,
contradictions, revisions and the edges between them.

**D2 — It is explicitly not authoritative for real-world entity relations.** Those are owned by the
canonical entity/claim stream (`EntityFact` and its `recorded_at` / `valid_from` split,
`db/schema.py:2768`) and are projected into any graph view. A graph edge asserting "A is employed by
B" is a projection of a claim and inherits that claim's epistemic status — including its
contradictions and its `recorded_at`. It does not gain authority by being stored in the Context Graph.

**D3 — The transaction boundary is the existing one.** `apply(tenant_id, transaction) ->
DecisionRecord` stays the shape. Observation membership, graph mutation and revision advance commit
together or not at all. A second write path into the Context Graph that cannot accept a caller
transaction is refused at review.

**D4 — No third graph store, and no new graph directory.** `apps/context-engine/` does not get
created. Neo4j, when it is configured, is reached only through `GraphProjection` / `GraphReader` /
`GraphSnapshot` / `GraphTraversal` (ADR-0027 §2) and is rebuildable from PostgreSQL alone.

**D5 — Authority is one field at a time, not one store at a time.** For any given field exactly one
owner writes it. Where a field appears in two stores, the second is a projection and is labelled as
one. The per-field map is T008's deliverable and is not yet produced; until it is, D5 is a review
obligation, not an audited claim.

## Why not the alternatives

**A — Treat ContextGraph as authoritative for everything, including entity relations.** Rejected.
It would give world-claims the atomicity and history semantics the process kernel needs while
stripping them of the `recorded_at` discipline that makes them checkable. When a relation claim is
later contradicted, a system that stored it as process state has to either rewrite process history —
destroying replay — or keep a contradiction inside a structure designed for bookkeeping. The two
failure modes are both worse than the ambiguity this ADR removes.

**B — Treat ContextGraph as authoritative for nothing; normalize everything into relational tables.**
Rejected. The atomicity, `DecisionRecord` coupling and history semantics FR-032 and CE-001 §13.5
demand are already implemented and tested at
`context_graph_store.py:74-80`. A rewrite would destroy working, tested behaviour to reach a shape
that is not demonstrably better — which is the same reasoning that made ADR-0028 refuse to move the
context engine.

**C — Leave the authority question open pending T008's field-by-field map.** Rejected *as a
decision*, adopted *as a scope limit*. The kind-level split (D1/D2) is decidable now because the two
kinds have genuinely different semantics. The field-level map is not, so D5 names it rather than
pretending to it.

**D — Also declare Neo4j's configuration defect resolved here.** Rejected. It is a code/config
defect, not an architecture decision, and it belongs to T127, which already owns it. An ADR that
fixes a port is an ADR that stops being an ADR.

## Consequences

**Positive**

- The scope of authority is stated in the same sentence as the mechanism that enforces it
  (`context_graph_store.py:80`), so the claim is checkable rather than aspirational.
- The `recorded_at` / `valid_from` discipline from `023_derivation_enforcement.py` stays attached to
  the state it was designed for and does not leak into process bookkeeping, where it would be noise.
- D2 gives `worldline` / claim supersession one place to live, and gives the graph exactly one role:
  a fast, rebuildable traversal view.

**Costs, accepted**

- Two kinds of state with different authority means every read path must say which it is serving.
  A caller that wanted "the graph" as a single question no longer has one. Accepted: the question was
  always ambiguous, and the ambiguity was going to surface as a bug rather than as a design note.
- D5 is currently unenforced because T008 has not produced the field map. Until it does, a reviewer
  is the only check. This is a real gap, recorded rather than papered over.
- Neo4j remains declared-but-unconfigured until T127. A driver with no configuration variable is
  dead code that looks live.

**Not changed**

- ADR-0027 stands: PostgreSQL authoritative, Neo4j a rebuildable projection, no third store.
- ADR-0028 stands: the engine stays at `apps/control-plane/context_engine/`.
- No vendor class enters domain logic (Principle V).

## Verification

- [ ] `PostgresContextGraphStore.apply` still accepts a caller-supplied transaction and returns the
      `DecisionRecord` it wrote (`context_graph_store.py:80`).
- [ ] A failed `apply` leaves no graph mutation and no revision advance.
- [ ] No code path writes a real-world entity relation into the Context Graph as process state; the
      relation exists as a projection of a canonical claim carrying `recorded_at`.
- [ ] A repository search finds no `apps/context-engine/` directory.
- [ ] `neo4j` appears in `apps/control-plane/pyproject.toml` with a matching configuration variable
      in `.env.example`, or is removed (T127).
- [ ] T008's ownership map exists and names exactly one writer per field.

## Open

- **D5 is unenforced until T008** (`current-state-audit.md §4`, authoritative-store ownership map)
  lands. The field-level authority map does not exist; `current-state-audit.md §3–§6` records T008 as
  `[ ]`. This ADR decides the principle, not the map, and does not invent the map.