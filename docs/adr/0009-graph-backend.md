# ADR-0009: Graph backend selection

Status: Accepted
Date: 2026-09-07

## Context

Behind the graph abstraction (ADR-0008) we must pick a concrete storage/query
backend for entity graphs and lineage. Candidates: Neptune, Neo4j, JanusGraph,
TigerGraph, an in-process engine.

## Decision

Default to an **in-process/graph-native engine via the abstraction layer**, with
Neptune as the recommended managed deployment for production scale.

## Rationale

- For development and CI, the in-memory graph engine (T040) keeps the stack
  hermetic and tests fast — projections stay rebuildable (I-12).
- Neptune provides managed graph storage + Gremlin/SPARQL when scale and HA
  require it.
- Engine-agnostic interface (ADR-0008) means the swap is config-driven, not a
  rewrite.
- Graph namespace isolation (T061) maps cleanly to either backend.

## Consequences

- Production deployments must provision the chosen graph engine per region.
- Traversal performance depends on backend; abstraction must expose hints
  (indexed lookups) to avoid O(N²).
