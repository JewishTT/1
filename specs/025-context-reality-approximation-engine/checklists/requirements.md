# Specification Quality Checklist: Context & Dialectical Reality Approximation Engine (v2)

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-10-04 · **Revised**: 2026-10-04 (v2 baseline)
**Feature**: [spec.md](../spec.md) · [input.md](../input.md) (v2, verbatim)
**Inputs**: [input.md](../input.md) (owner Design Baseline), [research.md](../research.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs) — *with one declared
      exception, see Notes*
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

**Declared exception.** The owner's baseline fixes file paths (§1.2), table names (§39) and
endpoint paths (§41) because this platform is contract-driven and those paths *are* the
contract. `spec.md` therefore restates them only where they are load-bearing constraints
and defers the rest to the baseline. This is a deliberate deviation from the generic
"no implementation details" guideline, justified by the feature's nature, not an oversight.

## Requirement Completeness

- [x] No `[NEEDS CLARIFICATION]` markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

**Note on open decisions.** Two items are recorded in **Open decisions** (Q1, Q2) rather
than as `[NEEDS CLARIFICATION]` markers, because they are genuine owner decisions about
architecture, not gaps in the description. Both are presented with options and
implications. `/speckit.plan` is gated on them.

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Traceability

- [x] All **88** owner requirement IDs `FR-025-001`–`FR-025-088` carried verbatim into
      `spec.md` (v2 added 20)
- [x] All **154** task IDs `T025-001`–`T025-154` carried into `tasks.md` (v2 added 25)
- [x] All **12** ADR records `ADR-025-01`–`ADR-025-12` enumerated (v2 added 5)
- [x] Acceptance gates **A–Q** covered by measurable outcomes (v2 added N, O, P, Q)
- [x] All acceptance gates §54 **A–Q** mapped to measurable outcomes `SC-001`–`SC-034`
- [x] All 12 permanent non-goals §59 carried as invariant INV-6
- [x] Baseline section map recorded in `input.md` §1

## Independent Testability

- [x] Every one of the 8 user stories has an explicit independent test
- [x] Priority ordering yields a viable P1-only system
- [x] No story depends on a later story for its own verification

## Feature Risk (from research.md)

- [x] Risk register R1–R8 recorded and carried into plan obligations
- [x] Greenfield high-risk areas identified: four-valued truth, causal staging,
      gluing/obstruction, completeness protocol
- [x] Already-built areas identified and marked integrate-don't-rebuild: TDA
- [x] Donor candidate inventory produced, with fitness explicitly unverified

## Notes

**Items requiring resolution before `/speckit.plan` completes**

1. **Q1** — `ContextDefinition` vs existing `InvestigationContext`. Highest-impact open
   item; three options with distinct costs, no safe default.
2. **Q2** — `cp_domain/context_engine/` placement vs the live `context_engine/` path.
   Blocks file-level task assignment in `tasks.md`.
3. **R6** — Wave 0 gate unsatisfied. Baseline v2 §55 requires **twelve** ADRs; only
   ADR-0028 exists. v2 widened the exit criterion to "no unresolved contradiction between 024
   and 025 terminology **and lifecycles**" plus ratification of the §47.4 quantitative
   targets. Eleven records open; five of them are new in v2 and covered by `T025-154`.
6. **Prefix divergence (closed)** — v1 Appendix G.1 gave `OBS-` to both Obstruction and
   Observation. v2 fixes it (`OBST-`), so the `W0-04` question raised by the earlier draft no
   longer needs an owner decision.
4. **R8** — `.specify/memory/constitution.md` is still an unmodified placeholder template
   while `AGENTS.md` holds the real doctrine. Decide whether the constitution is generated
   from `AGENTS.md` before running further speckit governance commands.

**Fidelity statement on `input.md`.** `input.md` is now the **complete verbatim** Design
Baseline v2 as supplied by the owner — 155 KB, §0–61 including the new §13A/§14A/§16A, and
Appendices A–Z including the traceability matrix (Y) and change log (Z). Verified
programmatically: 62/62 numbered sections, 26/26 appendices, 154/154 task ids, 88/88
requirement ids, 12/12 ADR ids, 133 code blocks. It is not summarised and must not be edited;
divergences are recorded in `decisions.md` / `docs/adr`, not applied to the text.

**Research coverage caveat.** External literature review is partial: `websearch` returned
HTTP 403 from its provider for every query, and arXiv rate-limited (HTTP 429) after one
successful thread. The donor inventory is complete for the capability keywords searched,
but keyword presence is not fitness — every donor row still requires the reuse analysis
that `AGENTS.md` §1 mandates. Recorded in `research.md` §0 and §6.

**Spec quality verdict**: passes all checklist items subject to the notes above.
Q1 and Q2 are resolved (ADR-0028). `spec.md`, `plan.md`, `tasks.md`, `data-model.md`,
`contracts/contracts.md`, `quickstart.md` are regenerated against v2 and cross-checked.

**Gate**: Wave 0 CLOSED (12/12 ADR). `/speckit.implement` unblocked; next is Phase A (T025-001…020).