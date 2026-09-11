# ADR-0008: Graph abstraction layer

Status: Accepted
Date: 2026-09-07

## Context

Projected entity/relationship data and lineage need graph traversal. We must
avoid coupling projection and query code to a specific graph engine so the
backend can change (ADR-0009) and regions can deploy independently.

## Decision

Introduce a **graph abstraction layer** (`apps/projection/graph/`, T040) exposing
nodes/edges, lineage walks, and traversal behind an engine-agnostic interface,
with a `path_shim` for cross-app domain reuse.

## Rationale

- Keeps projection/query code independent of the concrete graph store.
- Enables backend swaps (ADR-0009) and per-region graph deployments (T069).
- Supports the lineage requirement (FR-032) and graph namespace isolation
  (T061).
- Makes the layer unit-testable with an in-memory engine.

## Consequences

- New graph capabilities must be added to the abstraction, not the engine.
- The shim layer must not leak engine-specific types across app boundaries.
