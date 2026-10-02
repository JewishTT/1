# ADR-0027 — PostgreSQL is authoritative; Neo4j is a rebuildable serving projection

- **Status**: Accepted
- **Date**: 2026-10-02
- **Feature**: 024-context-driven-continuous-intelligence (D2=c)
- **Instructs**: FR-061…FR-066

## Context

Feature 024's source ТЗ (§6.5) asserted that "there is no knowledge graph in PostgreSQL". Wave 0 verified the opposite:

- `apps/control-plane/db/schema.py` declares **57 tables / 55 models**, including `entities`, `entity_versions`, `entity_identity`, `entity_stream`, `relation_candidate`, `relation_claim`, `relation_claim_revision`, `relation_signal`, `correlation_edges`, `type_assertions`, `temporal_history_heads`, `temporal_history_publications`, `topological_features`.
- A **second** graph exists in Neo4j (`apps/projection/graph/{neo4j,relation_store,abstraction,snapshot,adjacency}.py`, `neo4j:5-community` behind the `analytics` compose profile).

So the graph is already duplicated, and the ТЗ's premise was inverted. Any migration built on "there is no graph in PG, therefore add one elsewhere" would have produced a **third** copy — a direct violation of Constitution Principle IV ("no universal graph serving as source of truth").

Wave 0 also confirmed the Context Graph itself does not exist: `rg -il "context_graph"` over the entire repository returns exactly one hit — the ТЗ itself.

## Decision

1. **PostgreSQL is authoritative** for the Context Graph and for all operational and research graph state.
2. **Neo4j is a rebuildable serving projection**, reached only through the existing `GraphProjection` / `GraphReader` / `GraphSnapshot` / `GraphTraversal` contracts. It is never written from domain logic and never read as authority.
3. **No third graph store or graph copy is introduced.**
4. The PG-graph / Neo4j-graph duplication is **resolved** to exactly one authority plus one projection.
5. Divergence between the two is **observable** and repaired by rebuilding Neo4j from PG.

## Why PostgreSQL and not Neo4j

Not a preference — three constraints force it.

**Transactivity with the context state it describes.** Constitution III is projection-first, and Principle I makes observations immutable. A Context Graph whose nodes must be written in the same transaction as the context revision that produced them cannot live behind a separate store's commit protocol. PostgreSQL gives that directly; Neo4j does not, without a distributed-transaction design the platform has no other reason to adopt.

**It is where the data already is.** 55 models already encode entities, relations, revisions, and temporal history. Migrating them into Neo4j to make the ТЗ's premise true would be paying to contradict ourselves.

**No-MVP/mini-architecture.** Constitution forbids partial contracts. Introducing a third store *in addition to* two existing ones is the definition of a mini-architecture.

Neo4j is genuinely good at one thing PG is not: multi-hop traversal at serving latency. That is exactly what a serving projection is for, and the existing `GraphProjection` contract is the seam for it.

## Consequences

**Positive**
- Constitution IV's "no single graph as source of truth" is actually satisfied rather than asserted: one authority, one rebuildable projection.
- Context Graph lands next to the existing 57 tables, so `ContextRevision`, obligations, and graph nodes can commit together.
- Neo4j can be dropped and rebuilt at any time with no loss.

**Costs, accepted**
- Neo4j is now on the critical path for graph *reads* in the serving layer, so it needs a rebuild job and a divergence metric.
- PG must be tuned for graph-shaped queries it is not best at. Accepted: correctness before serving latency.
- The duplication must actually be resolved. Leaving both as peers is the status quo this ADR exists to end.

**Not changed**
- `GraphProjection` / `GraphReader` / `GraphSnapshot` / `GraphTraversal` are untouched; Principle V plugability is unaffected.
- No vendor-specific class enters domain logic.
- Existing Neo4j code is reused, not rewritten — it becomes a pure projection.

## Verification

- Exactly one authoritative store: PostgreSQL.
- Neo4j reachable only through the `GraphProjection` contract.
- A full Neo4j rebuild from PostgreSQL alone reproduces the serving graph.
- Divergence between PG and Neo4j is detectable without a manual diff.
- No third graph store appears in any compose profile or settings file.