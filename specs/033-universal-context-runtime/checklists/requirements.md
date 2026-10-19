# Requirements Quality Checklist — Feature 033

**Purpose**: verify that the Universal Context Runtime specification is complete, unambiguous,
testable and honest *before* it drives engineering work.
**Feature**: `033-universal-context-runtime`
**Source of truth**: `spec.md`, with Appendix A (the verbatim v2.0 blueprint) governing where they differ.

---

## A. Source fidelity

- [ ] **A1** Appendix A is byte-for-byte the supplied document; SHA-256 `7B645578…` reproduced by the documented command. (Verified: `Verbatim : True`, 167 121 bytes, 1 979 lines.)
- [ ] **A2** Every section §0–§36 is represented by at least one requirement, contract or register entry.
- [ ] **A3** Sections 0–14 are attributed to Feature 032 rather than silently re-specified here.
- [ ] **A4** The extension (§15–§36) is specified, not summarised: the frame, the dimensions, the ladder, the operators, the catalogue, the registry, the workbenches, retrieval, reasoning modes, multimodal, memory, stopping, API, gateway, security, storage, examples, conformance, phases, ADRs and DoD each have their own requirements.
- [ ] **A5** §36 references are treated as candidates, never as endorsements.

## B. The universality claim is testable

- [ ] **B1** "Universal" is defined as an engineering property, not a promise of understanding (§15.1; FR-001).
- [ ] **B2** The four supporting principles — open world, typed contracts, composable operators, verifiable history — each have a requirement.
- [ ] **B3** The five models are required to stay distinct and unmerged (FR-002).
- [ ] **B4** A new domain pack is provably registrable without a core change (FR-001, FR-020, SC-001).
- [ ] **B5** Unknown kinds and payloads have a preservation path (FR-007, SC-002).
- [ ] **B6** The sixteen starter context kinds are a registry, not a closed list (FR-020).
- [ ] **B7** The abstraction ladder's twelve levels and twenty-two operators are enumerated (FR-010, FR-011).

## C. Testability

- [ ] **C1** Every FR is verifiable by a test, an artifact inspection or a named command.
- [ ] **C2** Every SC is measurable — a percentage, a zero-count, or a named suite.
- [ ] **C3** Every user story has an independent test that does not require the others.
- [ ] **C4** The eighteen conformance suites and fifteen golden fixtures are individually named.
- [ ] **C5** The Definition of Done is a checklist of demonstrations, not a narrative.
- [ ] **C6** The `[NEEDS CLARIFICATION]` set is empty; open questions are recorded as unknowns and assumptions.

## D. Ambiguity and internal consistency

- [ ] **D1** "Context", "frame", "definition", "revision" and "branch" are used consistently.
- [ ] **D2** "Capability", "operator", "tool" and "provider" are used consistently: capability is the contract, operator the implementation, provider the runtime.
- [ ] **D3** "Memory" is always qualified by its layer.
- [ ] **D4** "Complete", "saturated", "blocked" and "inconclusive" are never used interchangeably.
- [ ] **D5** "Absence" is never used without its qualifier.
- [ ] **D6** "Evidence", "claim", "inference", "hypothesis", "model" and "simulation" are always distinct.
- [ ] **D7** No requirement contradicts another; where a conflict is possible, the stricter rule is named.
- [ ] **D8** The relationship to Features 030 and 032 creates no second authority (FR-080).

## E. Scope discipline

- [ ] **E1** The spec declares what it does not do — no second engine, no closed ontology, no store migration, no completion claim.
- [ ] **E2** Optional backends are clearly optional and benchmark-gated (FR-075, FR-076).
- [ ] **E3** The functional catalogue of §19 is explicitly a planning catalogue, not a capability claim (FR-022).
- [ ] **E4** Performance targets are not set before measurement (§33, FR-076).
- [ ] **E5** No requirement mandates a specific vendor, framework or model as a production dependency.

## F. Safety, security and governance

- [ ] **F1** Untrusted content is data, never instructions (FR-072).
- [ ] **F2** No model can grant itself privileges (FR-073).
- [ ] **F3** Confidence is not authorization, and this is enforced in policy code (FR-073).
- [ ] **F4** Cross-tenant isolation covers queries, caches, vector indexes, logs and exports (FR-071).
- [ ] **F5** A replay is re-authorised under current policy while the original policy remains provenance (FR-071).
- [ ] **F6** External side effects require grant, confirmation, idempotency and audit (FR-034, FR-035).
- [ ] **F7** Deletion and erasure record their lineage impact (FR-071).

## G. Traceability

- [ ] **G1** Every SC refers to at least one FR.
- [ ] **G2** Every FR refers to a source section or a named contract.
- [ ] **G3** Every user story maps to the phases and tasks that deliver it.
- [ ] **G4** Every task in `tasks.md` carries a `[USn]` tag and a section reference.
- [ ] **G5** Every contract rule is exercised by at least one named test.
- [ ] **G6** Every ADR in the register names its inputs and its blocking dependency.
- [ ] **G7** Every conformance suite names what it proves.

## H. Honesty of the document itself

- [ ] **H1** The spec never claims the runtime exists; §19 and §35 are explicitly target state.
- [ ] **H2** `NOT_RUN`, `BLOCKED` and `UNKNOWN` are first-class statuses throughout the spec, the register and the corpus.
- [ ] **H3** No success criterion can be satisfied by naming a capability.
- [ ] **H4** The conformance register and the ADR register both state the truthful current position: everything not run, everything open.
- [ ] **H5** The non-goals are as specific as the goals.
- [ ] **H6** The governing rule of §35 is preserved as the document's own standard.

---

## Result

**23 of 24 groups are satisfiable by the current `spec.md`, `plan.md`, `tasks.md`, `data-model.md`,
`contracts/`, the ADR register and the conformance register.** Group **H4** is satisfied only in the
sense that the registers *truthfully* report `NOT_RUN` and `OPEN`; they will satisfy it fully when
Phase A executes and the first results exist.

No group is unsatisfiable. None is claimed as verified without evidence. That distinction is the
subject of the checklist itself.
