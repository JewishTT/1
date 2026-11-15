# Domain silo architecture

**Status:** Target architecture adopted by ADR-041  
**Scope:** Intelligence, Economics, SpecOps&CI and the shared platform substrate

## Operating model

COGNITIVE is split into domain silos with one fundamental data-producing silo:
**Intelligence**. Intelligence owns the platform's public-source discovery and
evidence pipeline. Domain silos consume its tenant-scoped, evidence-backed projections
through explicit read contracts. They do not create their own parallel recon stacks.

```text
                 ┌─────────────────────────────────────┐
                 │       INTELLIGENCE (foundation)    │
                 │ discovery → recon → acquisition   │
                 │ observations → interpretation     │
                 │ resolution → evidence projections │
                 └──────────────────┬──────────────────┘
                                    │ IntelligenceReadPort
                    ┌───────────────┴─────────────────┐
                    │                                 │
          ┌─────────▼──────────┐            ┌─────────▼──────────┐
          │     ECONOMICS      │            │     SPECOPS & CI    │
          │ actors, markets,   │            │ authorized security │
          │ ownership, flows,  │            │ assessments and CI  │
          │ financial networks │            │ execution/results   │
          └─────────┬──────────┘            └─────────┬──────────┘
                    │                                 │
                    └───────────────┬─────────────────┘
                                    ▼
                 ┌─────────────────────────────────────┐
                 │ Shared substrate: immutable evidence│
                 │ event bus, tenant policy, identity, │
                 │ audit, storage and observability    │
                 └─────────────────────────────────────┘
```

The diagram describes data ownership, not a mandatory deployment topology. The
shared substrate is infrastructure, not a fourth domain silo. CI/build/test tooling
is a cross-cutting engineering capability; it does not own an independent intelligence
or recon pipeline.

## 1. Intelligence — foundational silo

**Owns:** investigation-scoped discovery and recon orchestration; source registry and
connectors; acquisition scheduling/frontier; raw artifact capture; immutable
observations; parsing and entity extraction; candidate resolution and admission;
evidence lineage; canonical entity/relation and temporal projections; publication of
versioned intelligence snapshots.

**Does not own:** economic conclusions, financial interpretation, security-operation
execution or domain-specific risk decisions. It produces evidence and traceable
projections, not a universal truth score.

Existing platform components remain the implementation substrate during this
reorganization: acquisition, zero-layer (within its stated policy boundary),
interpretation, admission, projection and the control-plane orchestration. The new
`apps/intelligence/` package establishes domain ownership and read-port exports; it
does not claim that these existing services have already been physically consolidated
under that directory.

## 2. Economics — domain consumer

**Owns:** economic subject taxonomy and dossiers; corporate and institutional
relationships; ownership and control analysis; financial-flow ledgers; trade, payment,
investment and debt relationships; market and sector context; network concentration,
exposure and dependency analysis; time-series and scenario analysis.

**Consumes:** Intelligence snapshots, entity attributes, evidenced relations and
immutable evidence references. Every derived result carries the source snapshot ID
and evidence references.

**Must not:** launch recon, crawl sources, register acquisition connectors, enumerate
targets independently, or treat unverified leads as established economic facts.
Unknown amount, currency, date or counterparty stays unknown; aggregation never
silently invents valuations or FX conversions.

The existing `EconomicsPage` currently reports the economics of the platform's own
pipeline (cost, throughput, queues, latency and worker capacity). Those operational
metrics remain useful, but they are not the external Economic Intelligence domain and
must be represented as platform operations telemetry rather than conflated with it.

## 3. SpecOps&CI — authorized consumer and execution domain

**Owns:** engagement governance; Rules of Engagement; explicit target selection from
existing Intelligence entities; authorized security-assessment planning and execution;
emulation and lab orchestration; defensive validation; counterintelligence analysis;
telemetry comparison, findings and after-action reporting.

**Consumes:** a tenant-scoped Intelligence snapshot and exact entity IDs already present
in that snapshot. Each operation is bound to an immutable snapshot ID and a
time-bounded authorization whose tenant, approved entity roster and permitted
assessment types must match.

**Must not:** contain discovery, recon, crawler, source connector, target-enumeration,
or autonomous scope-expansion logic. A request for an unknown host is rejected; it
must return to Intelligence as a separately governed investigation, and only a
subsequent, newly approved snapshot can expand an operation's scope.

The consumer preparation layer lives in `apps/specops_ci/`. Executors may perform
only the explicitly authorized assessment against the approved target set. Their
results return through the shared evidence substrate with operation, authorization,
snapshot and provenance references. The old package is preserved in
`spec-ops legacy/`; API and UI adapters are a migration surface, not the target
domain boundary.

## Shared contract and invariants

The first read contract is
`shared.contracts.intelligence_feed.IntelligenceReadPort`. It accepts an
`IntelligenceQuery` containing tenant, subject, purpose and bounded relationship
depth, and returns an immutable `IntelligenceSnapshot` with entity/relation evidence
references. The contract intentionally carries no raw body.

1. **One recon authority:** only Intelligence owns recon orchestration and source
   acquisition. Economics and SpecOps&CI are consumers.
2. **Tenant isolation:** every request, snapshot, entity and evidence reference stays
   within one tenant. Cross-tenant references are rejected.
3. **Evidence-first:** a domain fact or relation must retain its immutable evidence
   references and source snapshot ID. A projection is not the source of truth.
4. **Unknown is not zero:** missing amounts, dates, confidence, coverage or source
   responses remain explicitly unknown/unavailable.
5. **Purpose limitation:** consumers declare a purpose; access is authorized and
   audited by the serving implementation. A purpose string alone is not authorization.
6. **No raw-body event payloads:** event messages carry IDs and immutable object
   references, never copied source documents.
7. **Bounded queries:** relationship depth and result budgets are bounded at the
   Intelligence read boundary.
8. **No authority escalation:** a consumer cannot widen collection scope or operation
   authorization by mutating a snapshot or adding arbitrary entity IDs.

## Migration sequence

1. Preserve the former `apps/specops/` package in `spec-ops legacy/`; keep a
   temporary import bridge for existing adapters.
2. Establish shared typed Intelligence feed contract and the three domain packages.
3. Route Economics and SpecOps&CI service preparation through the Intelligence read
   port. Add tests that reject scope expansion and forbidden recon imports.
4. Migrate existing SpecOps API routes and UI canvases to `apps/specops_ci/`; retain
   endpoint compatibility while moving service ownership.
5. Migrate Economics UI from a single mixed panel into economic intelligence views,
   while retaining platform pipeline economics in Operations.
6. Wire the Intelligence read-port implementation to the existing durable projection
   stores, add API/auth/audit and event schemas, then remove the temporary bridge.
7. Regenerate the machine-generated platform model and run domain, control-plane,
   application, UI screenshot and end-to-end acceptance suites.

This change establishes domain packages and contracts; it does not claim steps 3–7
are already complete.
