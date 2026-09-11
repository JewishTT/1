# Scope Boundary Policy — Scientific Intelligence Fabric

**Date**: 2026-09-09 | **Feature**: [spec.md](spec.md) | **Constitution refs**: II, VII; No-MVP rule

## Purpose

The Scientific Intelligence Fabric analyzes **structures and processes**, never scores or
verdicts on **named natural persons** by sensitive attributes. This document is the policy
contract every science entry point must enforce (FR-007 / SC-005).

## Forbidden outcome classes (hard-excluded)

No request, analysis, or claim may target a natural person's:
- political affiliation / political views
- involvement (suspected or confirmed) in illegal activity
- membership in a marginalized, protected, or vulnerable group
- any outcome whose value is a personal verdict about a specific human being

These classes are hard-excluded: they **cannot** be declared as scope in a `CausalModel`,
and any feature vector or outcome attribute matching one is refused.

## Enforcement (structural, not post-hoc)

1. A single guard `ensure_scoped(outcome_attribute)` runs **first** in every public entry
   point (register claim, causal classify, structure analyze, API route) — before any
   computation (contracts §5).
2. Model scope declarations are validated at registration: a `CausalModel` declaring a
   forbidden class is rejected at creation time.
3. Rejections return `422 scope_refused` with a policy reference and emit
   `science.causal.scope_rejected` (or `science.claim.scope_rejected`) as an **audit event**.
4. The guard is code-level and shared (single implementation), so no future module can
   bypass it by omission.

## What stays in scope

- Structural/systemic/mechanical processes: network structure, transmission dynamics,
  causality between classes of events, temporal patterns, correlation among process variables.
- Claims about **classes of events or processes**, aggregated and de-identified.
- Hypotheses about how systems behave — not about who specific people are.

## Audit requirements

- Every scope rejection: `event_id`, timestamp (UTC), requested outcome class, entry point,
  actor/project context, policy reference (`contracts/scope-boundary.md`).
- Audit records immutable and queryable (Constitution I); used in review to verify boundary
  compliance (SC-005).

## Relationship to other contracts

- Enforced first in `contracts/interface-contracts.md` §5 (`ensure_scoped`) and §1 (claim
  registration).
- Exposed via REST: `contracts/science-api.md` (422 scope_refused).
- Surfaced in UI: scientific UI renders structural results only; no person-verdict widgets
  (spec US5/US7).