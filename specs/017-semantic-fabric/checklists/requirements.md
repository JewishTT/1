# Requirements Checklist: Semantic Fabric (Ontologies as External Tools)

**Feature**: `017-semantic-fabric` · **Spec**: `spec.md` · **Status**: reviewed 2026-09-26

## Spec quality

- [x] FR-001 — Open-world admission
- [x] FR-002 — No ontology as admission gate (demote `OntologyPack`)
- [x] FR-003 — Layered typing (`TypeAssertion`)
- [x] FR-004 — Monotonic semantic commitment
- [x] FR-005 — `SemanticRef` contract boundary
- [x] FR-006 — `RelationOperator` extends `RelationSchema` (016)
- [x] FR-007 — `SemanticProfile`
- [x] FR-008 — SKOS vocabularies + query expansion
- [x] FR-009 — SSSOM mappings as evidence-bearing
- [x] FR-010 — SHACL validation sidecar (`pySHACL`, Core)
- [x] FR-011 — Layered graded validation
- [x] FR-012 — Validation produces findings, not deletion
- [x] FR-013 — Closed operations, open world
- [x] FR-014 — `ContextFrame` as semantic binding layer
- [x] FR-015 — Pluggable semantic access (`SemanticRegistry`)
- [x] FR-016 — Search-space reduction
- [x] FR-017 — LinkML limited to contracts
- [x] FR-018 — Monotonic status vocabulary

## Success criteria

- [x] SC-0 — Non-regression with today's green baseline
- [x] SC-1 — Undeclared type/relation admitted
- [x] SC-2 — Simultaneous multi-layer typing with history
- [x] SC-3 — No semantic-library imports in `apps/shared/domain`
- [x] SC-4 — SHACL finding without claim destruction
- [x] SC-5 — `OntologyPack.allows_*` unreachable from admission
- [x] SC-6 — SKOS expansion is opt-in, never an equality
- [x] SC-7 — Backend-agnostic `SemanticRegistry`
- [x] SC-8 — `works_for` warns, never rejects
- [x] SC-9 — `UNKNOWN`/`UNSUPPORTED` distinguishable from `INVALID`
- [x] SC-10 — Reproducible candidate pruning

## Scope guard

- [x] Explicit "NOT" list: no OWL/OWL-RL, no Jena, no triplestore
- [x] RDF/SHACL is a sidecar, native store stays native
- [x] External IRIs never replace internal IDs
- [x] No global enumeration of permissible entity kinds
- [x] Extends 016 constructs, no parallel relation-semantics declaration

## Feasibility

- [x] SKOS / pySHACL / OAK / SSSOM are the adopted standards; each has a named role
- [x] Existing 016 assets reused, not duplicated (`RelationSchema`, `EvidenceContext`, `ContextValidator`)
- [x] No new backbone, no new runtime service
- [x] Every FR is verifiable without live Postgres/Kafka/Neo4j

## Constitution

- [x] Gate principle stated: open-world admission is load-bearing and failure-blocking
- [x] All eight principles marked PASS with reasoning
- [x] No principle waived or stretched
