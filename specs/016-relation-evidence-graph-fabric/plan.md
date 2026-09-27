# Implementation Plan: Relation & Evidence Graph Fabric

**Branch**: `016-relation-evidence-graph-fabric` | **Date**: 2026-09-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/016-relation-evidence-graph-fabric/spec.md`

## Summary

Replace the thin `(edge_type, source, target, properties)` graph edge with a first-class
`RelationClaim`: a content-addressed assertion that a typed relation holds between
participants, under an explicit `RelationArityMode`, inside an immutable content-addressed
`EvidenceContext`, with a full temporal interpretation, evidence refs, version lineage
(`logical_relation_id` → `relation_id`) and supersession/contradiction links.

Introduce three new horizontal primitives that every later source and consumer shares:

1. **`RelationClaim`** — identity/revision separation, 128-bit truncated SHA-256 identity,
   arity-aware canonicalisation, content hash, version lineage.
2. **`EvidenceContext` + `ContextValidator`** — an immutable content-addressed frame and a
   seven-layer validator returning graded verdicts with structured reasons.
3. **`EvidenceGraph`** — bidirectional lineage over
   `Source → Capture → Observation → Segment → Mention → Candidate → Assertion → Relation → Entity`.

Fix the three known store defects (N-ary idempotency guard is a no-op, `neighbors()` discards
direction, Neo4j drops properties and creates no id), persist the new model with a
forward-only Alembic migration, and correct the frontend edge identity which currently
collapses every directed relation with its inverse.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript 5.5 strict (frontend)

**Primary Dependencies**: stdlib `hashlib`/`json`/`dataclasses` only for the domain model —
no new runtime dependency. FastAPI + SQLAlchemy 2.0 (`Mapped`/`mapped_column`) + asyncpg
for persistence. pytest per app for tests. Vitest + jsdom + Testing Library for the frontend.

**Storage**: PostgreSQL (operational state, new tables), Neo4j (graph projection, behind the
existing adapter), in-memory stores (tests and rebuild oracle), S3 (raw bytes, untouched).

**Testing**: `uv run --project apps/<app> pytest apps/<app>/tests -q`;
`npx vitest run` + `npx tsc -b` in `apps/webapp`.

**Target Platform**: Linux server + Node 20+ browser client (existing deployment).

**Project Type**: Python monorepo (`apps/*` uv workspace members) + one Vite/React SPA.

**Performance Goals**: identity computation is pure hashing — 1M claims must yield 1M
distinct ids without collision (SC-002). The validator must be pure and stateless, and its
expensive layers accept pre-computed inputs so validation never becomes a pipeline
bottleneck.

**Constraints**: no new runtime dependency; no change to acquisition, streaming or
transport layers; the previous Alembic revision is immutable; constitution invariants
I-1 (observation immutable), I-3 (assertion ≠ truth), I-4 (monotonic versions), I-11
(idempotent), I-12 (provenance enforced) must hold for every new write path.

**Scale/Scope**: designed for 10^7 relations with a 128-bit identity space; six new domain
modules, one migration with five new tables, two store adapters fixed, one frontend
identity correction.

## Constitution Check

| Gate | Result |
|---|---|
| **I. Observation-Immutable Evidence Substrate** | PASS — nothing writes to observations. `EvidenceContext` and `RelationClaim` are new, separately immutable objects. |
| **II. Evidence-First** | PASS — this feature *is* the evidence-first mechanism. Every claim carries evidence refs and a context; lineage is bidirectional and reports incompleteness explicitly. |
| **III. Projection-First Knowledge Architecture** | PASS — claims, contexts and lineage are the durable substrate; graph stores remain rebuildable projections, and the rebuild path is proven by test (FR-040). |
| **IV. No Single Store / Graph / Score** | PASS — `evidence_grade` stores confidence, independent source count, completeness and trust state as *separate* components (FR-025), never collapsed into one number. Graph remains a projection, not a source of truth. |
| **V. Plugability by Contract** | PASS — vendor-specific Cypher stays inside `apps/projection/graph/neo4j.py`; domain logic imports no vendor type. The new relation model is store-agnostic. |
| **VI. Process-Centric** | PASS — `investigation_id` is a first-class field of `EvidenceContext`, so claims are always scoped to an investigation. |
| **VII. Security-First** | PASS — every read and every identity is tenant-scoped; cross-tenant reads refused (FR-048); cross-tenant evidence rejected (FR-022). No new external input path. |
| **No MVP/mini-architecture** | PASS — all four new primitives (claim, context, validator, lineage) plus schema registry land in one feature, so the contracts exist up front. |
| **Backpressure** | N/A — no new queue or consumer. |
| **Idempotency** | PASS — content-addressed identity plus content hash gives idempotency structurally; the N-ary guard bug is fixed rather than left to callers. |
| **Dead letter / quarantine** | PASS — validation verdicts other than `VALID` are preserved with reasons, components, versions and timestamps and are replayable (FR-050). Rejected claims are never deleted (FR-006). |
| **Governance (ADR required)** | ACTION — two ADRs needed: relation identity scheme + arity model; claim/context persistence and identity-revision split. |

**Complexity Tracking**:

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| 128-bit truncated SHA-256 rather than 32-bit FNV-1a | 2^32 ids collide at ~77k edges; the platform targets 10^7 relations | Keeping FNV-1a makes an identity collision a routine, silent data-integrity failure |
| Separate `logical_relation_id` + `relation_id` pair | A corrected validity window is a *revision* of one relation, not a new relation | Without the split, corrections append unrelated edges and "all versions of this relation" is unanswerable |
| Seven-layer validator with graded verdicts | Structural, temporal, provenance and identity failures are materially different and callers must distinguish them | A boolean forces every caller to re-derive the reason, which is the re-derivation this feature exists to remove |
| New `RelationClaim` alongside the existing `GraphEdge` | The existing edge has no id, no context, no version and no temporal interpretation | Mutating `GraphEdge` in place would break every store, adapter and test that depends on its 4-field shape |

## Architecture

### Layering

```text
                 RelationSchemaRegistry        (constraint system, versioned)
                          │  declares
                          ▼
  EvidenceContext ──► RelationClaim ──► ContextValidator ──► ValidationResult
  (immutable,           (identity +       (7 layers,             (graded verdict +
   content-addressed)    revision)         graded verdict)        structured reasons)
       │                     │
       │                     ▼
       │              RelationStore (protocol)
       │                 ├── InMemoryRelationStore
       │                 ├── Neo4jRelationStore
       │                 └── RebuildableRelationStore (log + snapshot + checksum)
       │                     │
       ▼                     ▼
  EvidenceGraph ◄──── projections: Neo4j / OpenSearch / ClickHouse / TDA / UI
  (bidirectional lineage,                               ▲
   complete | incomplete-with-first-unresolved-hop) ────┘
```

### The four primitives

**`RelationClaim`** (P1). Identity is two-level:

- `logical_relation_id` — *which relation this is*. Derived from arity mode, relation type
  and canonical participants, **excluding** temporal window, evidence and version fields. All
  revisions share it.
- `relation_id` — *this content*. Derived from `logical_relation_id` plus the temporal
  window, evidence refs, context ref and version triple. Distinct content → distinct id;
  identical content → identical id, which gives idempotency structurally.

Canonicalisation by arity mode:

| Mode | Participant canonicalisation | Identity material |
|---|---|---|
| `UNDIRECTED` | sort members ascending | `mode \| type \| sorted(members)` |
| `DIRECTED` | preserve order (subject, object) | `mode \| type \| subject \| object` |
| `NARY` | sort `(role, member)` pairs by role | `mode \| type \| sorted(role=member)` |
| `TEMPORAL` | preserve order, window participates | `mode \| type \| ordered members \| valid_from \| valid_to` |

All hashed with SHA-256, truncated to 128 bits, hex-encoded → 32 hex characters.

**`EvidenceContext`** (P1). Frozen dataclass, `context_id` = `CX-` + 128-bit truncated
SHA-256 over the canonical frame content. Stored and referenced by id only (FR-018). A
resolver turns a `context_ref` into a frame or fails with `context_unresolved`.

**`ContextValidator`** (P1). Pure function over `(context, claim, schema, world)`. Runs
seven layers, always reporting all seven outcomes, collapsing them into one graded verdict
by a fixed precedence: `INVALID` > `CONFLICTING` > `STALE` > `INCOMPLETE` >
`UNDERDETERMINED` > `VALID`. Never mutates its inputs, never returns a bool.

**`EvidenceGraph`** (P2). An adjacency structure over typed `EvidenceHop`s. Backward
traversal from a relation and forward traversal from a source. Incompleteness is a first-class
result (`complete=False` + `first_unresolved_hop`), never an empty list.

### What changes and what does not

| Component | Change |
|---|---|
| `apps/projection/graph/abstraction.py` | `GraphEdge` gains `edge_id`; add `HyperEdge` idempotency fix; add directional `neighbors` |
| `apps/projection/graph/neo4j.py` | write relation id + full properties; `MERGE` on id |
| `apps/projection/graph/snapshot.py` | forward N-ary writes; honour snapshot offset; stable projection id; deterministic checksum |
| `apps/webapp/src/lib/edgeFormation.ts` | arity-aware identity; preserve N-ary; keep FNV-1a for layout seeds only |
| `apps/webapp/src/lib/edgeFormation.test.ts` | replace the pinned `e:1d374e53` identity vector; keep the FNV-1a vector test |
| `apps/control-plane/db/schema.py` | five new tables |
| `apps/control-plane/db/migrations/versions/016_*.py` | forward-only migration |
| `apps/shared/domain/*` | four new modules (claim, schema, context, validator) + lineage |
| Acquisition, interpretation, admission engines | **unchanged** — they consume the contracts but are not rewired in this feature |

## Project Structure

### Documentation (this feature)

```text
specs/016-relation-evidence-graph-fabric/
├── spec.md              # input specification
├── plan.md              # this file
├── research.md          # identity scheme, arity model, verdict precedence, store defects
├── data-model.md        # entities, fields, derivation rules, migration plan
├── quickstart.md        # validation commands and worked examples
├── contracts/
│   ├── api.md           # read API surface
│   ├── events.md        # claim/context event vocabulary
│   ├── service-contracts.md  # RelationStore / ContextResolver / LineageProvider protocols
│   └── operations.md    # migration, rebuild, observability
└── tasks.md             # phase-grouped implementation tasks
```

### Source Code (planned)

```text
apps/shared/domain/
├── relation_claim.py        # NEW  RelationClaim, RelationIdentity, RelationRevision, arity
├── relation_identity.py     # NEW  arity-aware canonicalisation + 128-bit SHA-256 identity
├── relation_schema.py       # NEW  RelationSchema registry, temporal semantics, admission rules
├── evidence_context.py      # NEW  EvidenceContext (frozen, content-addressed) + resolver
├── context_validation.py    # NEW  7-layer validator, ValidationResult, ValidationReason
├── evidence_lineage.py      # NEW  EvidenceHop, LineageTrace, forward/backward traversal
└── hypergraph.py            # unchanged (precedent for identity/revision split)

apps/shared/tests/unit/
├── test_relation_claim.py        # NEW
├── test_relation_identity.py     # NEW
├── test_relation_schema.py       # NEW
├── test_evidence_context.py      # NEW
├── test_context_validation.py    # NEW
└── test_evidence_lineage.py      # NEW

apps/projection/graph/
├── relation_store.py         # NEW  RelationStore protocol + InMemoryRelationStore
├── abstraction.py            # MOD edge_id, N-ary idempotency, directional neighbors
├── neo4j.py                  # MOD id + properties + MERGE
└── snapshot.py               # MOD N-ary forwarding, offset, stable projection id

apps/projection/tests/
└── unit/test_relation_store.py  # NEW

apps/control-plane/db/
├── schema.py                 # MOD 5 new tables
├── relation_claim_store.py   # NEW  tenant-scoped persist/read
├── evidence_context_store.py # NEW  frame registry
├── migrations/versions/016_relation_evidence_graph.py  # NEW forward-only
└── tests/unit/test_migration_016_forward_only.py       # NEW both-paths proof

apps/control-plane/api/
└── relations.py              # NEW read API (claim, context, validation, lineage, revisions)

apps/webapp/src/lib/
├── edgeFormation.ts          # MOD arity-aware identity, N-ary preserved
└── edgeFormation.test.ts     # MOD vectors

docs/adr/
├── 0023-relation-identity-and-arity.md      # NEW
└── 0024-claim-and-context-persistence.md    # NEW
```

**Structure Decision**: the domain model lives in `apps/shared/domain` because claim, context,
schema, validator and lineage are consumed by projection, control-plane and eventually UI —
they are shared domain, not one app's internals. Store adapters stay in
`apps/projection/graph` behind the existing protocol, and persistence stays in
`apps/control-plane/db`, matching every existing table. The frontend change is confined to the
single existing identity module so no other component is touched.

## Phase Strategy

1. **Phase 0 — gates**: ADRs, migration proven on both paths.
2. **Phase 1 — US1/US2 (P1)**: identity + claim model + arity + store parity. This is the
   foundation; nothing else is correct without it.
3. **Phase 2 — US3/US4 (P1)**: context frame + validator. Depends on Phase 1 for the claim.
4. **Phase 3 — US5/US6 (P2)**: schema registry + evidence lineage. Lineage depends on the
   claim; the schema registry is independent and can run in parallel with Phase 2.
5. **Phase 4 — US7 (P2)**: rebuildability and snapshot correctness. Depends on Phase 1.
6. **Phase 5 — US8 (P3)**: frontend identity correction. Independent of all backend phases.
7. **Phase 6 — polish**: full-suite regression check against the recorded baseline.

Phases 2, 3 and 5 have no intra-phase file overlap, so within each phase all tasks marked
`[P]` run concurrently. Phases 2, 4 and 6 are mutually independent and can run concurrently
once Phase 1 lands.

## Complexity Tracking

See the Constitution Check table above. Two additional justifications:

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| `RelationClaim` coexists with `GraphEdge` rather than replacing it | The existing edge is embedded in five stores, adapters and a test suite; in-place mutation would break the build mid-feature | A breaking rename across all of them is slower and riskier than an additive model that the stores then adopt |
| Verdict precedence (`INVALID` > `CONFLICTING` > `STALE` > `INCOMPLETE` > `UNDERDETERMINED` > `VALID`) is a fixed total order | Callers need one comparable verdict while all seven layer outcomes remain visible | "Any failure is invalid" collapses staleness and incompleteness into falsehood, which the constitution explicitly forbids (I-3) |
