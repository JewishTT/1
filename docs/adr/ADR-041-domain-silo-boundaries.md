# ADR-041 — Intelligence as the foundational silo; Economics and SpecOps&CI as consumers

- **Status:** Accepted
- **Date:** 2026-11-15
- **Decision owners:** Platform architecture
- **Related:** COGNITIVE Constitution Principles I–VII; ADR-030-01; shared connector and evidence contracts

## Context

The platform already has a mature evidence-acquisition and interpretation substrate,
but domain responsibilities are distributed across app packages, APIs and UI. The
former SpecOps package combines domain behavior and safety gates in `apps/specops/`.
Recon orchestration also exists as shared platform services. Economics currently
surfaces operational pipeline cost and throughput rather than a complete domain model
for external economic actors and financial relationships.

Allowing every domain to build its own recon implementation would duplicate source
connectors, policy enforcement, provenance, tenant isolation, budgets and entity
resolution. It would also create incompatible target identities and competing versions
of the same evidence.

## Decision

Adopt three domain silos and one shared substrate:

1. **Intelligence** is the foundational producer and sole owner of source discovery,
   recon orchestration, acquisition, evidence capture, entity extraction/resolution
   and intelligence projections.
2. **Economics** is an evidence-consuming domain. It owns economic analysis and
   financial-flow semantics, and reads entity/relation snapshots from Intelligence.
3. **SpecOps&CI** is an evidence-consuming, authorization-bound domain. It owns
   engagement rules, explicit scope, security assessments, counterintelligence and
   operational results. It obtains target entities from Intelligence and may not
   perform discovery or recon itself.
4. The immutable evidence/event substrate, tenant policy, audit and observability are
   shared platform infrastructure, not duplicated in each domain.

The shared consumer boundary is
`shared.contracts.intelligence_feed.IntelligenceReadPort`. Consumers request a
tenant-scoped snapshot for a declared purpose. Snapshots carry entity and relation
records with immutable evidence references, source IDs and snapshot ID. Raw source
bodies are never copied into the contract.

For SpecOps&CI, a snapshot is necessary but not sufficient for execution. A separate,
time-bounded authorization must bind the tenant, snapshot ID, exact allowed entity
IDs, permitted assessment kinds and approval reference. Unknown or out-of-roster
targets are refused; expansion requires a new Intelligence investigation and an
updated approval.

The previous 68-file `apps/specops/` implementation is retained in
`spec-ops legacy/apps/specops/`. A temporary import bridge supports adapters that
have not yet migrated. It is not an endorsed dependency for new development.

## Consequences

- Recon and source governance have one owner; domain consumers cannot fork or silently
  expand their own target coverage.
- Economic conclusions and security findings become attributable to a specific
  Intelligence snapshot and evidence chain.
- Platform pipeline cost/queue/worker metrics remain in Operations and are no longer
  mistaken for external Economic Intelligence.
- Existing SpecOps API routes, frontends, feature specs and donor records must be
  migrated in subsequent work. The archive and bridge are an intermediate state.
- The initial read contract and domain preparation packages do not by themselves
  complete production wiring, authentication, audit enforcement, API migration,
  runtime tests or end-to-end workflows. Those are explicit follow-up acceptance
  criteria, not implied by package presence.

## Rejected alternatives

- **Recon in every silo:** duplicates controls, provenance and entity identity.
- **Move every existing platform component physically under `apps/intelligence/`
  immediately:** creates a large mechanical move and risks destabilizing existing
  imports without first stabilizing the ownership contract.
- **Treat the serving graph as the source of truth:** conflicts with immutable,
  rebuildable evidence/projection principles.
- **Put platform operations economics and economic intelligence in one domain model:**
  confuses infrastructure cost telemetry with external financial/economic semantics.

## Validation required

- Contract tests reject cross-tenant evidence and malformed snapshots.
- Economics tests require matching tenant/snapshot and known endpoints for flow
  aggregation.
- SpecOps&CI tests reject expired approvals, unknown targets and targets outside the
  explicit roster.
- A static architecture test prevents Economics and SpecOps&CI from importing
  acquisition/recon implementation packages.
- Full acceptance requires wired read-port implementation, API/UI migration, generated
  platform-model regeneration, and end-to-end tests.
