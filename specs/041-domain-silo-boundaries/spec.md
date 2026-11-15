# Feature 041 — Domain silo boundaries

**Status:** Foundation and consumer contracts implemented; production migration remains open.  
**ADR:** ../../docs/adr/ADR-041-domain-silo-boundaries.md

## User intent

Organize COGNITIVE into three domain silos: Intelligence, Economics and SpecOps&CI.
Intelligence is the foundational evidence-producing silo. Economics and SpecOps&CI
consume its entity/relation context through a shared contract. In particular, SpecOps
must never implement its own recon or expand a target roster from outside an
Intelligence snapshot.

## User stories

### US1 — Fundamental Intelligence contract (P1)

As a platform domain, I need a tenant-scoped, immutable snapshot/read-port contract so
that every consumer can reason about the same identified subjects, relations and
evidence lineage.

**Acceptance**
- Snapshot includes tenant, immutable snapshot ID, subject ID, entity/relation records
  and evidence references.
- Raw source bodies are excluded.
- Cross-tenant evidence and relation endpoints outside the snapshot are rejected.
- Query requests declare purpose and use a bounded relationship depth.
- The serving implementation enforces authorization, tenant ACLs, budgets, audit,
  freshness and lineage; a purpose string alone is not authorization.

### US2 — Economics consumer (P1)

As an analyst, I need economic subjects and financial flows built from Intelligence
entities and evidence so that economic analysis does not run a second collection stack.

**Acceptance**
- Economic subjects derive from Intelligence entities.
- A financial flow retains payer, payee, currency, time, evidence and source snapshot.
- Aggregation is tenant- and snapshot-scoped and rejects unknown endpoints.
- Unknown amount/currency remains unknown and is excluded from numeric totals.
- No implicit FX conversion, inferred valuation or truth assertion is introduced.
- Platform pipeline cost and worker metrics remain operational telemetry, not external
  economic intelligence.

### US3 — SpecOps&CI consumer (P1)

As an authorized security operator, I need targets selected from existing Intelligence
entities and bound to an approved scope, so that security operations cannot invent or
silently enumerate targets.

**Acceptance**
- Every preparation request reads a tenant-scoped Intelligence snapshot.
- Every target ID already exists in that snapshot and in the exact approved roster.
- Authorization binds tenant, snapshot ID, approval reference, validity window and
  assessment types.
- Unknown, expired, cross-tenant or out-of-roster targets are rejected.
- No recon, crawling, discovery, connector registration or target enumeration is
  implemented in the consumer domain.
- Operation results return to the shared immutable evidence substrate with snapshot,
  authorization and operation provenance.

### US4 — Legacy retirement (P2)

As a maintainer, I need the former SpecOps package preserved while its API and UI
adapters migrate to the new domain boundary.

**Acceptance**
- Former apps/specops source tree is preserved under spec-ops legacy.
- Compatibility bridge exists only during adapter migration.
- Legacy API routes and UI canvases are migrated without breaking stable endpoints.
- Bridge is removed only after imports, tests and runtime dependencies no longer use it.

## Non-goals for this foundation change

- Replacing the existing acquisition, entity-resolution, evidence or projection engines.
- Claiming that the IntelligenceReadPort is already backed by a production query adapter.
- Moving or rewriting every SpecOps endpoint and React surface in one atomic change.
- Treating a domain package, catalogue entry or unit test as proof of production
  reachability.
- Performing live security tests or financial transactions.

## Data flow

Intelligence is the sole producer of canonical evidence-backed entity/relation
snapshots. Economics and SpecOps&CI are separate consumers. Domain outputs are derived
claims/findings with source snapshot and evidence lineage; they do not become a second
source of truth. Shared event messages remain refs-only.
