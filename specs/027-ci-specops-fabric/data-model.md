# Phase 1 Data Model: CI/SpecOps Department Fabric

**Feature**: `027-ci-specops-fabric` | **Date**: 2026-10-10

Entities extracted from the feature spec. Every analytical result carries evidence refs (constitution §II). No figure is stored without provenance.

## EmulationPlan
An ATT&CK-based adversary emulation plan, sourced from donor plan libraries (ael, adversary_emulation_library).
- `plan_id`: stable id
- `name`, `description`
- `source_donor`: which library the plan came from
- `abilities`: list of Ability
- `target_techniques`: ATT&CK technique ids
- `expected_telemetry`: list of ExpectedTelemetry (what each ability should leave behind)
- `lab_fixture`: the authorized isolated target this plan is allowed to run against
- **Validation**: a plan cannot be launched against a target other than its declared `lab_fixture`; unknown technique still yields an ability (edge case: shown, not dropped).

## Ability
One executable step within a plan.
- `ability_id`, `technique` (ATT&CK), `tactic`, `executor`
- `command` (as served by the donor)
- `expected_telemetry`: refs into the plan's expected set

## Operation (Emulation Run)
An execution of a plan against an authorized lab target.
- `operation_id`, `plan_id`, `lab_fixture`
- `roe_status`: `unconfirmed | confirmed | expired` (gate)
- `state`: `planned | running | halted | complete`
- `abilities`: per-ability `planned | executed | failed | skipped` (with donor status mapped to WorkStatus; unknown → `Unknown`)
- `agent_beacons`, `pivot_paths`
- `started_at`, `halted_reason` (set when authorization is lost mid-run)
- **State transitions**: planned →(launch, requires roe_status=confirmed)→ running →(complete | halt); running →(auth lost)→ halted(reason recorded).
- **Validation**: launch blocked unless `roe_status == confirmed`; results flow back as observations/claims (FR-007).

## RulesOfEngagement (sign-off)
- `roe_id`, `operation_id`/`campaign_id`, `approved_by`, `scope`, `signed_at`, `expires_at`
- **Validation**: absence ⇒ launch refused (FR-005); expiry halts a running operation.

## PhishingCampaign
An authorized social-engineering simulation.
- `campaign_id`, `template_source` (PhishSlayer)
- `roe_status` (must be `confirmed` to send)
- `roster`: supervisor-approved target list
- `state`: `draft | ready | sending | complete | refused`
- `engagement_metrics`: sent/opened/clicked/submitted counts
- `attack_mapping`: ATT&CK technique ids
- `captured_credentials`: **always empty** — never stored (FR-006)
- **Validation**: out-of-roster target rejected before send; send blocked without RoE; credentials never persisted.

## Subject (counterintelligence)
The atomic CI entity: person / organization / account / channel / campaign.
- `subject_id`, `kind`, `display`
- `invariants`: list of SubjectInvariant
- `relations`: graph edges to other subjects
- **Validation**: tenant-isolated (FR-015).

## SubjectInvariant
A tracked attribute of a subject, always with evidence.
- `invariant_id`, `subject_id`, `kind` ∈ {belief-state, narrative-position, bias-profile, coordination-signature, phase-state}
- `value`, `confidence`
- `evidence_refs`: list of evidence ids (may be empty)
- **Validation**: empty `evidence_refs` ⇒ rendered as **unsupported**, never asserted (FR-008).

## SocialReactionProjection
A run injecting a narrative/shock into a modeled population.
- `projection_id`, `population_ref`, `narrative_input`
- `horizon`, `trajectories` (reach, polarization over time)
- `drivers`, `intermediate_artifacts` (inspectable on one screen)
- `phase_transition_risk`: indicator + threshold crossed?
- `confidence`: low when population too small/sparse (edge case)
- **Validation**: result returns as claims; low population ⇒ low confidence, not a confident curve.

## DetectionGap
An expected telemetry item with no matching recorded observation.
- `gap_id`, `operation_id`, `ability_id`, `expected_telemetry`
- `status`: `gap | corroborated` (matched ≥1 observation)
- **Validation**: surfaced explicitly in forensics, never omitted (FR-010).

## Evidence / Observation / Claim (existing substrate, reused)
Every entity above traces to the platform's immutable evidence chain. Emulation/simulation/CI results are recorded as observations and asserted as claims; projections are rebuildable (constitution §II, §III, FR-016).

## Relationships
- EmulationPlan 1—* Ability; Plan 1—* Operation.
- Operation *—1 RulesOfEngagement; PhishingCampaign *—1 RulesOfEngagement.
- Operation 1—* DetectionGap; Ability 1—* ExpectedTelemetry.
- Subject 1—* SubjectInvariant; Subject *—* Subject (relations).
- SocialReactionProjection *—1 population; emits Claims.
- All analytical entities → Evidence (refs).
