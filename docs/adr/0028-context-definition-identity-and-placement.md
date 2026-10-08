# ADR-0028 - `ContextDefinition` is a separate object with its own identity space; the Context Engine stays at its canonical path

**Status**: Accepted (owner decision, 2026-10-04)
**Feature**: `025-context-reality-approximation-engine`
**Resolves**: Specification 025 Q1 and Q2 — see `specs/025-context-reality-approximation-engine/spec.md` → *Open decisions*
**Baseline clauses amended**: §5 (`ContextDefinition`), §1.2 (required placement), Appendix G.1 (identifier grammar)

---

## Context

Specification 025 requires two things that collide with verified repository reality.

**One.** §5 defines `ContextDefinition` as the immutable analytical specification of a
context, with fields `objective`, `temporal_scope`, `semantic_regime_ref`,
`analysis_profile_ref` and `policy_ref`. Specification 024 already defines
`InvestigationContext` — the operational, revisioned state of an investigation — carrying
`title`, `question`, `scope_refs`, `current_revision` and `revision_count`. Both mint the
same `CXI-` identifier prefix. §58.1 of the same specification forbids redefining 024's
approved semantics.

The object 024 specifies is not a proposal. It exists, is async end to end, is durable in
PostgreSQL, and is verified live: contract, in-memory store, PostgreSQL store, engine,
`CognitiveLoop`, and a working investigation → context → question → obligations →
frontier → replay path.

**Two.** §1.2 mandates `apps/control-plane/cp_domain/context_engine/`. No `cp_domain/`
directory exists anywhere in this repository. The live, tested Context Engine lives at
`apps/control-plane/context_engine/`.

Left undecided, each of these produces a defect rather than a style difference. One
`CXI-` namespace shared by two objects makes every reference, storage key and lineage edge
ambiguous at the storage layer. A duplicated or re-exported package path produces two
legal import paths for one implementation — the same ambiguity class that already caused
twelve collection errors and a 132-test undercount earlier in this repository's history.

---

## Decision

### D1 — Two objects, two roles, two identifier spaces

`ContextDefinition` and `InvestigationContext` are **not** competing authorities. They are
different things, and are named accordingly:

```text
InvestigationContext   operational, revisioned state of an investigation
                       (revisions, obligations, frontier, decisions)

ContextDefinition      immutable analytical specification
                       (objective, temporal_scope, semantic_regime_ref,
                        analysis_profile_ref, policy_ref)
```

They compose in one direction only:

```text
ContextDefinition  (CXD-…)   defines
        │
        ▼
InvestigationContext  (CXI-…)   references
        │
        ├── revisions
        ├── obligations
        ├── frontier
        └── decisions
```

**Identifier grammar is split, and this is the mandatory correction.** A single shared
prefix would make the two objects indistinguishable in storage, in references and in
lineage:

```text
CXI-{32}   InvestigationContext      (unchanged; 024 contract untouched)
CXD-{32}   ContextDefinition         (new namespace; was CXI- in baseline §5/G.1)
```

and the link is an explicit attribute:

```text
InvestigationContext.definition_ref -> CXD-…
```

`InvestigationContext` therefore gains **one** attribute, a foreign reference. Its approved
semantics, identity derivation, revision rules and lifecycle are unchanged. That is the
whole cost, and it is smaller than any alternative.

### D2 — One canonical code path; §1.2 placement superseded

The canonical implementation path remains:

```text
apps/control-plane/context_engine/
├── engine.py
├── loop.py
├── obligations.py
├── store.py
├── postgres_store.py
└── catalogue_bridge.py
```

No `cp_domain/` package is created. No re-export or compatibility shim is created. One
implementation, one import path.

The baseline's §1.2 path requirement is **superseded by verified repository topology**.
This is a deliberate, recorded deviation, not a silent omission.

---

## Why not the alternatives

**Q1-A — extend `InvestigationContext` in place.** Rejected. It rewrites a frozen,
approved, live 024 contract by addition, which is precisely what §58.1 prohibits, and it
conflates an immutable analytical specification with evolving operational state. The two
have genuinely different lifecycles: a definition is written once, a context is revised
continuously. One object would need a discriminator field and every reader would have to
know which mode it is in.

**Q1-C — `ContextDefinition` becomes authoritative, `InvestigationContext` becomes a
projection.** Rejected for now. It is the cleanest end-state and remains the natural
migration target if the two objects ever genuinely converge. It also migrates live API
paths, storage and currently-passing tests to fix a problem that D1 does not create.

**Q2-A — create `cp_domain/` and move the engine.** Rejected. Moves verified, live code
to satisfy a path rule, changing every import, test path and deployment reference in
exchange for no behavioural gain.

**Q2-C — `cp_domain/` re-exports the engine.** Rejected explicitly. Two legal import paths
for one implementation is the defect, not the cure.

---

## Consequences

**Positive**

- 024's approved contract is preserved exactly; one additive attribute.
- Identifier namespaces are unambiguous at every layer, including lineage.
- No verified code is moved; no import ambiguity is introduced.
- The `definition_ref` edge becomes the explicit place where analytical specification and
  operational state join — which is itself a lineage edge the audit questions in
  Appendix L can traverse.

**Costs, accepted**

- Two context-shaped objects exist, so the API and UI must be explicit about which one a
  request addresses. Mitigation: distinct URL prefixes (`/context/{id}/definition` versus
  `/investigations/{id}/context`), and analyst-facing labels, never a bare "context".
- The baseline text for §5 and Appendix G.1 is now wrong in exactly one respect — the
  `ContextDefinition` prefix. The baseline is a Design Baseline owned by the author;
  amending it is recorded here rather than silently applied.

**Not changed**

- `CXI-` remains `InvestigationContext` forever unless a later ADR says otherwise.
- PostgreSQL remains the sole authority (ADR-0027). No second graph authority.
- The world substrate remains the only entity truth. Neither object resolves identity.

---

## Verification

- [ ] `InvestigationContext` identity derivation is unchanged; existing content-addressed
      context IDs continue to validate against their snapshots.
- [ ] Exactly one namespace mints `CXI-`; a repository-wide search finds no second minting
      site.
- [ ] `CXD-` appears only in `ContextDefinition` derivation.
- [ ] `InvestigationContext.definition_ref` round-trips through storage and API, and is
      nullable for contexts created before this ADR.
- [ ] No `cp_domain/` directory exists; `apps/control-plane/context_engine/` is the only
      import path for the engine, and a duplicate-module collection run stays at zero
      errors.
- [ ] §54 acceptance gate A (durable, append-only, replayable revisions) still passes
      unmodified after the additive attribute lands.

---

## Follow-on

This ADR discharges **one** of Specification 025 §55 Wave 0's seven required records
(context/definition identity boundary, covering the placement question as well). The
remaining six — epistemic algebra, revision/replay contract, sheaf-inspired locality
boundary, hypothesis lifecycle, reasoning operator contract, global-search completeness
semantics — remain open and Phase A does not begin before Wave 0 closes, per the baseline's
own exit criterion: *no unresolved contradiction between 024 and 025 terminology*.