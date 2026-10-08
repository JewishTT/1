# Decision Record — 025

**Feature**: `025-context-reality-approximation-engine`
**Date**: 2026-10-04
**Status**: Q1 and Q2 resolved; Wave 0 partially discharged

## D-1 — `ContextDefinition` is a separate object with its own identity space

**Decision**: Q1 = **B**.

`InvestigationContext` and `ContextDefinition` are distinct objects with distinct roles and
**distinct identifier prefixes**.

```text
CXI-{32}   InvestigationContext    operational, revisioned state of an investigation
                                   (revisions, obligations, frontier, decisions)
CXD-{32}   ContextDefinition       immutable analytical specification
                                   (objective, temporal_scope, semantic_regime_ref,
                                    analysis_profile_ref, policy_ref)

ContextDefinition (CXD-)  defines  →  InvestigationContext (CXI-)
                                             .definition_ref -> CXD-…
```

**Mandatory correction carried**: the baseline §5 and Appendix G.1 assigned `CXI-` to
`ContextDefinition`. That is a small specification defect, not a reason to disturb 024. Two
objects sharing one prefix make every reference, storage key and lineage edge ambiguous.
`CXI-` remains `InvestigationContext`; `CXD-` is minted for `ContextDefinition`.

**Cost accepted**: `InvestigationContext` gains exactly one nullable additive attribute
`definition_ref`. Its identity derivation, revision semantics and lifecycle are untouched.

## D-2 — Canonical Context Engine path is `apps/control-plane/context_engine/`

**Decision**: Q2 = **B**.

```text
apps/control-plane/context_engine/
├── engine.py
├── loop.py
├── obligations.py
├── store.py
├── postgres_store.py
└── catalogue_bridge.py
```

One implementation, one import path. No `cp_domain/` package. No re-export or compatibility
shim.

Baseline §1.2's placement requirement is **superseded by verified repository topology**.
The repository already has this live contour, and it is async, durable and covered by
passing tests.

**Rejected alternatives**: (A) move to `cp_domain/` — relocates verified code for no
behavioural gain; (C) re-export shim — creates two legal import paths for one
implementation, which is the same package-ambiguity class that previously caused twelve
collection errors and hid 132 tests.

## D-3 — Prefix collision resolved by the baseline itself (v2 Appendix G.1)

**Status**: CLOSED by v2. No owner decision needed.

v1 Appendix G.1 assigned `OBS-` to both Obstruction (§10.3) and observation references
(§7.1). v2 fixes it: obstruction is **`OBST-`**, `OBS-` is reserved for Observation.
v2 additionally declares the prefixes that v1 used but never defined — `PRD`, `PRO`, `MOD`,
`QRY`, `SR`, `WLS`, `EVID`, `GAP`, `ENT`, `REL` — and adds `BRN`, `EDG`, `CQA`, `ANL`, `RPF`,
`RET`, `REV`.

The only divergence that remains is `CXI-` for `ContextDefinition`, which ADR-0028 splits into
`CXD-`. That divergence is intentional and recorded.

## Where the reasoning lives

Full rationale, rejected alternatives, consequences and verification checklists:
[`docs/adr/0028-context-definition-identity-and-placement.md`](../../../docs/adr/0028-context-definition-identity-and-placement.md).

## Wave 0 status

Baseline §55 requires seven architecture records before Phase A. This decision discharges
**record 1 of 7** (context/definition identity boundary, covering the placement question
as well).

ALL 12 ACCEPTED (2026-10-04). Index: docs/adr/WAVE-000-index.md. Outstanding:

1. Epistemic algebra — four-way truth state
2. Revision / replay contract
3. Sheaf-inspired locality boundary
4. Hypothesis lifecycle
5. Reasoning operator contract
6. Global-search completeness semantics
7. **Temporal algebra — 13 Allen relations, disjunctive sets** (new in v2)
8. **Evidence independence and coverage-qualified absence** (new in v2)
9. **Ranking policy and ReasoningProfile** (new in v2)
10. **Branches, scenarios, analyst-in-the-loop** (new in v2)
11. **Retention, erasure and permissible-inference policy** (new in v2)

Covered by `T025-154`.

Phase A does not begin until Wave 0 closes (§55 exit criterion: *no unresolved
contradiction between 024 and 025 terminology*).

## Not decided here

- Whether `.specify/memory/constitution.md` should be generated from `AGENTS.md`
  (research R8). Owner decision; `/speckit.constitution` was deliberately not run.
- Q1-C migration (`ContextDefinition` becoming authoritative, `InvestigationContext`
  becoming a projection) remains the natural end-state if the two objects ever converge.
  Not now.