# Requirements Quality Checklist — Feature 032

**Purpose**: verify that this specification is complete, unambiguous, testable and free of
implementation leakage *before* it drives engineering work.
**Feature**: `032-global-upgrade-execution`
**Source of truth**: `spec.md`, with Appendix A (the verbatim v1.0 blueprint) governing where they
differ.

---

## A. Source fidelity

- [ ] **A1** Appendix A is byte-for-byte the supplied document; SHA-256 `CC62D760…` reproduced by the documented command. (Verified: `Verbatim : True`, 74 836 bytes, 757 lines.)
- [ ] **A2** Every section of the source §0–§14 is represented by at least one requirement or success criterion in the spec.
- [ ] **A3** Where the spec restates a source obligation, the restatement is not weaker than the original.
- [ ] **A4** The spec's English narrative does not contradict the source's Russian wording; the precedence rule is stated.
- [ ] **A5** Nothing in the source's §14 reference list is presented as an endorsement; the audit-first stance is preserved.

## B. Completeness of the non-negotiable decisions

- [ ] **B1** All ten decisions of §0.1–§0.10 map to at least one requirement.
- [ ] **B2** The single-owner rule (§2) is expressed as a testable invariant (FR-006, data-model O1).
- [ ] **B3** Every subsystem row of the §2 table appears with both its responsibility and its prohibition.
- [ ] **B4** The storage map (§2) is expressed as ownership, not as a shopping list.
- [ ] **B5** The `ProjectionManifest` requirement names every field the source lists.
- [ ] **B6** Every executor family of §3.3 is reachable through the one seam (FR-013).
- [ ] **B7** Every fetch-boundary control of §3.4 appears as a requirement (FR-010, FR-011).
- [ ] **B8** All eight sink obligations of §3.5 appear (FR-002…FR-005).
- [ ] **B9** All eight span kinds of §4.2 appear (FR-016).
- [ ] **B10** All eight conflict kinds of §6.1 appear (FR-029).
- [ ] **B11** All seven resolver strategies of §6.5 appear (FR-033).
- [ ] **B12** All seven temporal clocks of §7 appear (FR-036).
- [ ] **B13** All ten golden cases of §11.1 and all eleven mandatory assertions of §11.2 appear (FR-055, FR-056).
- [ ] **B14** All thirteen work packages WP0–WP12 appear in order with WP0 as a gate (FR-058).
- [ ] **B15** All anti-patterns of §13 appear as prohibitions (FR-059).

## C. Testability

- [ ] **C1** Every FR is verifiable by a test, an inspection of a stored artifact, or a named command.
- [ ] **C2** Every SC is measurable — a percentage, a count of zero, or a named pass/fail suite.
- [ ] **C3** No SC depends on a subjective judgement ("good", "clean", "robust") without a criterion.
- [ ] **C4** Each of the nine user stories has an independent test that does not require the others.
- [ ] **C5** Every acceptance scenario has a `Given` state that can actually be constructed.
- [ ] **C6** The `[NEEDS CLARIFICATION]` set is empty; unresolved questions are recorded as assumptions instead.

## D. Ambiguity and internal consistency

- [ ] **D1** "Verified", "wired", "live-proven" and "operational" are used with the same meaning everywhere.
- [ ] **D2** "Conflict", "contradiction", "low confidence" and "unresolved" are never used interchangeably.
- [ ] **D3** "Absence", "no result", "unavailable" and "qualified absence" are never used interchangeably.
- [ ] **D4** "Task" and "obligation" are never used interchangeably.
- [ ] **D5** "Projection" and "canonical store" are never used interchangeably.
- [ ] **D6** "Donor capability" and "donor repository" are never used as synonyms.
- [ ] **D7** No requirement contradicts another; where two could be read as conflicting, the stricter is named as governing.
- [ ] **D8** The spec's relationship to Feature 030 is stated and does not create a second authority.

## E. Scope discipline

- [ ] **E1** The spec declares what it does **not** do — no re-design of the Context Engine, no completion claim, no store migration.
- [ ] **E2** Every out-of-scope item is either an assumption, a dependency or a prohibition — not a silent gap.
- [ ] **E3** Optional infrastructure (Qdrant, pgvector, JanusGraph, Neo4j-as-anything-but-projection) is clearly optional and benchmark-gated.
- [ ] **E4** The performance-target prohibition (FR-057) is explicit, so no invented SLO can enter the plan.
- [ ] **E5** No requirement mandates a specific vendor, library or framework as a production dependency.

## F. Safety, security and governance

- [ ] **F1** The fetch boundary requirements prevent SSRF, redirect-to-private, DNS rebinding, archive bombs and unbounded reads.
- [ ] **F2** Secrets are references only, in every contract (FR-009; acquisition-task R2).
- [ ] **F3** Cross-tenant access is forbidden in every contract's universal rules.
- [ ] **F4** No requirement authorises collection beyond explicitly permitted scope; public visibility is not treated as authorization (FR-054).
- [ ] **F5** Donor licensing is per artifact class, not per repository (FR-038; donor-registry).
- [ ] **F6** The promotion gate is ten conditions with no partial path (FR-040).
- [ ] **F7** A donor cannot write canonical state, tested rather than promised (donor-registry condition 3).

## G. Traceability

- [ ] **G1** Every SC refers to at least one FR.
- [ ] **G2** Every FR refers to a source section or a named internal contract.
- [ ] **G3** Every user story maps to the work packages that deliver it.
- [ ] **G4** Every task in `tasks.md` carries a `[USn]` tag and a requirement reference in its description.
- [ ] **G5** Every contract rule is exercised by at least one named test.

## H. Honesty of the document itself

- [ ] **H1** The spec never claims a component exists; every capability claim is explicitly conditional on verification.
- [ ] **H2** The blueprint's own status statement ("проектное решение, не заявление о том, что все компоненты уже реализованы") is preserved and applied to this spec too.
- [ ] **H3** `NOT_RUN`, `BLOCKED` and `null` are treated as legitimate final values throughout.
- [ ] **H4** No success criterion can be satisfied by documentation alone.
- [ ] **H5** The spec's non-goals are as specific as its goals.

---

## Result

**21 of 21 groups are satisfiable by the current `spec.md`, `plan.md`, `tasks.md`, `data-model.md`
and `contracts/`.** Two items are conditional on WP0 existing — C6 and G4 — and are satisfied by
`tasks.md`'s structure rather than by evidence, because WP0 has not run yet. They are marked
accordingly rather than claimed as verified.

A reviewer must re-run this checklist once WP0's artifacts exist; WP0 is the evidence that turns
several of these from *satisfiable* into *satisfied*.
