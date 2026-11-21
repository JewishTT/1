# Feature Specification: Phishing Club SpecOps Department — Full Red-Team

**Feature Branch**: `036-phishingclub-specops-department`

**Created**: 2026-11-01

**Status**: Implemented - full red-team mode; target/identity allowlist and ADR-0040 gate removed

> **Revision 2026-11-02**: the owner removed the lab-only exception. Later sections that
> describe a lab-isolated boundary, allowlist, lab-only roster, unverified donor or
> ADR-0040 runtime gate are historical and superseded by this status. The current
> implementation requires a confirmed RoE, pins Phishing Club at `31ff3f544af8`
> (AGPL-3.0) and serves its full API/console through `/specops/lab/phishingclub/*`.

**Input**: User description: "Integrate Phishing Club as the full red-team SpecOps department (lab-isolated), with Caldera/AEL as the kill-chain spine." (Original: "интеграция phishingclub — в качестве Отдела ui SpecOps … full red-team, lab-only … Phishing Club + Caldera spine".)

## Context

The platform already has a CI/SpecOps department (Feature 027) with a simulation-only Phishing/SAT panel, and it has already harvested Phishing Club's fourteen-event engagement taxonomy (Feature 032). Phishing Club is vendored at `donors/phishingclub` and is recorded in the donor registry as `verified` at upstream `31ff3f544af8` under AGPL-3.0.

This feature turns that donor into the operating engine of a dedicated **SpecOps — Red-Team Lab** department. Caldera and AEL remain the kill-chain/emulation spine; Phishing Club owns the email, SAT, and adversary-in-the-middle (AiTM) lane. The department is a single UI surface over both, with one scope banner, one status vocabulary, one RoE gate, and one evidence trail.

The owner has selected the **full red-team tier**, including reverse-proxy/AiTM, remote-browser phishing, and session/token capture. That tier runs in full red-team mode and every action is bound by a confirmed, unexpired RoE; it is not a production acquisition capability.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One full red-team SpecOps department surface (Priority: P1)

A red-team operator opens **SpecOps → Red-Team Lab** and lands on one department canvas. The canvas exposes panels for Operations (Caldera/AEL), Phishing Campaigns (Phishing Club), Templates & Lures, Senders & Domains, AiTM / Remote Browser, Engagement & Training, Reports, and Lab Control. A persistent banner states the scope — *full red-team · RoE-gated · Phishing Club* — and every panel declares its scope plus the endpoints it loaded and the ones it could not reach.

**Why this priority**: A department is the unit of operation. Without the shared surface, the two engines produce unrelated screens and the operator cannot compare a phishing campaign with a kill-chain operation.

**Independent Test**: Open the department route with the lab services up. Confirm every panel renders, the scope banner is present on every panel, and the navigation/title resolve to the new department. Stop one donor service and confirm the affected panel shows a named absence rather than a fabricated zero.

**Acceptance Scenarios**:

1. **Given** the lab services are available, **When** the operator opens the department, **Then** all panels render with the scope banner and each panel names its loaded endpoints.
2. **Given** Phishing Club or Caldera is unavailable, **When** the operator opens the affected panel, **Then** the panel names the missing service/endpoint and renders no invented counts.
3. **Given** the operator is in the OSINT module, **When** they activate the SpecOps module, **Then** the new department is reachable as a first-class destination with its own breadcrumb title.

---

### User Story 2 - Author and run a campaign against the lab, under RoE (Priority: P1)

An operator prepares a phishing/SAT campaign from a template, selects a valid roster, a sender profile, a schedule, and an ATT&CK mapping. The platform refuses to launch until a confirmed, unexpired rules-of-engagement sign-off is recorded. On launch, the campaign runs through the Phishing Club service, and the operator sees state and funnel progress derived from evidence.

**Why this priority**: Campaign execution is the core value of the Phishing Club integration. It is also the point where an authorization failure becomes concrete, so the gate and the lab boundary must ship with it.

**Independent Test**: Attempt to launch without sign-off (blocked with the reason shown and nothing sent), with a malformed recipient (rejected before send), then with sign-off and a valid roster (campaign runs and produces funnel counts).

**Acceptance Scenarios**:

1. **Given** a prepared campaign and no recorded sign-off, **When** the operator launches, **Then** the launch is refused, the reason is shown, and no message leaves the lab.
2. **Given** a campaign containing a malformed recipient, **When** it is validated, **Then** the recipient is rejected before any send; a duplicate is also refused.
3. **Given** a confirmed, unexpired sign-off and a valid roster, **When** the operator launches, **Then** the campaign runs, its state advances, and the funnel is derived from recorded engagement events.
4. **Given** a campaign is running, **When** the operator opens its report, **Then** every displayed count traces to the audit/evidence trail.

---

### User Story 3 - Run an AiTM / remote-browser session under RoE (Priority: P1)

An authorized operator configures a reverse-proxy or remote-browser flow against a valid target, starts the session, and observes captured session artifacts. Captured cookies, tokens, and credentials are encrypted at rest, redacted in the UI and logs, access-audited, and retained only for the configured window. A kill switch stops the session and preserves evidence.

**Why this priority**: This is the capability that distinguishes the full red-team tier from simulation. It is also the highest-risk surface, so its containment, redaction, retention, and kill switch are part of the same story rather than a later hardening phase.

**Independent Test**: Start an AiTM session against an external host under a confirmed RoE, produce a synthetic captured artifact, and verify: encryption at rest, redaction in UI/logs, an access-audit row, a retention expiry, and refusal of a malformed target. Trigger the kill switch and verify the session stops and evidence remains.

**Acceptance Scenarios**:

1. **Given** a confirmed sign-off and a valid target, **When** the operator starts an AiTM session, **Then** the session starts and its artifacts are encrypted and access-audited.
2. **Given** a captured artifact, **When** it is displayed or exported, **Then** raw secret values are redacted and the UI states that a capture occurred without revealing it.
3. **Given** a session or proxy flow, **When** it targets a malformed destination, **Then** the request is denied and recorded.
4. **Given** an active session, **When** the operator triggers the kill switch, **Then** all lab activity stops within five seconds and evidence is preserved.

---

### User Story 4 - Run a Caldera/AEL kill-chain operation and link it to a campaign (Priority: P1)

An operator selects an emulation plan, runs it under the same RoE gate, and sees abilities, techniques, and outcome. The operation and a phishing campaign can be linked into one assessment record, so the operator can compare the system-facing kill chain with the person-facing engagement path.

**Why this priority**: Caldera/AEL is the department's chosen spine. Without it, the department is a phishing tool rather than a SpecOps department.

**Independent Test**: Run an operation from an AEL/Caldera plan, confirm abilities and ATT&CK techniques render, and link the operation to a campaign. Confirm the operation cannot start without RoE and rejects a malformed target.

**Acceptance Scenarios**:

1. **Given** a confirmed sign-off, **When** the operator runs an emulation plan, **Then** the operation executes and its abilities/techniques are shown.
2. **Given** a completed operation and a completed campaign, **When** the operator links them, **Then** one assessment view shows both and preserves their separate evidence.
3. **Given** no sign-off or a malformed target, **When** the operator starts an operation, **Then** the start is refused with the specific reason.

---

### User Story 5 - Build from the donor's templates, senders, and domains (Priority: P2)

An operator browses and imports Phishing Club templates, previews a multi-stage lure, and checks sender/domain readiness (SMTP/API sender, TLS, DNS). Assets may use `lab://`, `http(s)://`, or relative paths; templates and branding remain synthetic or explicitly authorized.

**Why this priority**: Campaign authoring depends on a usable catalog, but the department can run a fixture campaign without the full catalog.

**Independent Test**: Import a template, preview each stage, and open the readiness panel. Confirm an unsupported asset scheme is refused and a missing sender credential is named rather than defaulted.

**Acceptance Scenarios**:

1. **Given** a donor template, **When** the operator imports it, **Then** its stages and variables are previewed without sending anything.
2. **Given** a template that references an asset with an unsupported scheme, **When** it is validated, **Then** the asset is refused and the reason is shown.
3. **Given** a sender profile with a missing credential, **When** readiness is checked, **Then** the variable that would set it is named and the profile is not reported ready.

---

### User Story 6 - Measure engagement and training without blending them (Priority: P2)

An operator reviews the cross-channel engagement board: one funnel per campaign, subjects at their deepest rung, repeat engagement, anonymized subjects shown by pseudonym, and a **separate** training-compliance block. Anonymization and retention preserve exact counts.

**Why this priority**: Measurement is what turns a campaign into an assessment. The separation of training from phishing risk is a platform invariant inherited from the donor's best idea.

**Independent Test**: Run a campaign and a training assignment, confirm the funnel and the training block are separate, anonymize the campaign, and verify counts are unchanged and pseudonyms remain stable.

**Acceptance Scenarios**:

1. **Given** email and voice events, **When** the board renders, **Then** both channels appear on one ladder and training remains outside it.
2. **Given** a campaign with identified subjects, **When** the operator anonymizes it, **Then** exact counts survive and the subjects are reachable only by pseudonym.
3. **Given** a subject with events in several campaigns, **When** the board renders, **Then** the subject appears once per campaign at their deepest rung.

---

### User Story 7 - Produce an evidence-backed report (Priority: P2)

An operator generates a campaign/assessment report and exports it. The report states provenance, limitations, and whether each figure is measured, derived, or unavailable; it contains no raw captured secrets.

**Why this priority**: A red-team engagement is only useful if its result can be defended and re-derived.

**Independent Test**: Generate a report for a campaign with a linked operation, verify every figure has a lineage, export it, and confirm no raw secret appears. Remove an endpoint and confirm the report says "unavailable" rather than zero.

**Acceptance Scenarios**:

1. **Given** a completed campaign and operation, **When** the operator generates a report, **Then** the report includes both, with provenance and limitations.
2. **Given** an unavailable measurement, **When** the report renders, **Then** it is `null` with the missing instrumentation named, not a zero.
3. **Given** a captured artifact, **When** the report is exported, **Then** no raw secret is present and the redaction is stated.

---

### User Story 8 - Operate the boundary safely (Priority: P3)

An operator starts, resets, and tears down the lab; reads a readiness matrix (donor, version, license, egress policy, RoE state, missing prerequisites); and uses a single kill switch. Teardown deletes no evidence.

**Why this priority**: Operational safety is continuous, but the department can deliver value before the full lifecycle UI exists.

**Independent Test**: Stop the lab with the kill switch, verify all activity stops within five seconds and evidence remains. Reset the lab and verify prior evidence is still readable.

**Acceptance Scenarios**:

1. **Given** active lab activity, **When** the operator triggers the kill switch, **Then** all activity stops within five seconds and an audit row records it.
2. **Given** a missing donor or credential, **When** the readiness matrix renders, **Then** the prerequisite is named and the affected capability is marked unavailable.
3. **Given** a teardown, **When** it completes, **Then** no evidence, report, or derived artifact has been deleted.

---

### Edge Cases

- A sign-off exists but has expired: launch/start is refused with `409`, and the UI shows the expiry rather than a generic failure.
- A roster contains a malformed address or a duplicate: validation refuses the roster with `422` and names the offending entry.
- A template or proxy flow uses an unsupported scheme or a malformed host: the request is denied and audited; the campaign/session does not silently degrade.
- A captured artifact contains what appears to be a real credential: it is quarantined, redacted, and flagged as an incident; it is never rendered or exported raw.
- Phishing Club, Caldera, or a required credential is down: the panel renders a named absence; no synthetic counts or defaults.
- A donor template contains an unauthorized brand asset: import is refused; a synthetic or authorized replacement may be used.
- Concurrent campaigns or sessions run in the same lab: tenant/campaign isolation holds; no subject or artifact crosses boundaries.
- Anonymization or retention expiry runs while a report is open: counts and pseudonyms remain exact, and the report states the retention action.
- The kill switch fires mid-send: the campaign is marked partial, evidence is preserved, and no further messages are sent.
- A webhook or event is delivered twice: the record is idempotent and the funnel does not double-count.
- The donor license/attribution is not verified: the department reports the donor blocker and does not claim the adapter is ready.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The department MUST be one SpecOps surface with panels for Operations, Phishing Campaigns, Templates & Lures, Senders & Domains, AiTM / Remote Browser, Engagement & Training, Reports, and Lab Control. Each panel MUST declare its scope and the endpoints it loaded or could not reach.
- **FR-002**: Phishing Club MUST be the engine for email, SAT, and AiTM. Its backend MUST run as a local service behind a platform-owned contract adapter; its own frontend and visual language MUST NOT be embedded.
- **FR-003**: Caldera and AEL MUST remain the kill-chain/emulation spine. An operation and a phishing campaign MUST be linkable into one assessment record while keeping separate evidence.
- **FR-004**: The department MUST run every campaign, operation, proxy flow, and remote-browser session under a confirmed, unexpired RoE. Egress is RoE-gated; malformed targets and unsupported asset schemes MUST be refused.
- **FR-005**: Every campaign launch, operation start, AiTM session, outbound message, and capture MUST be blocked until a confirmed, unexpired RoE sign-off is recorded server-side. The UI MUST NOT be able to bypass the gate.
- **FR-006**: The full red-team tier (reverse-proxy/AiTM, remote browser, session/token capture) MUST be available in full mode under the RoE gate. Captured artifacts MUST be encrypted at rest, access-controlled per tenant, redacted in logs and UI, and retained or deleted by policy.
- **FR-007**: The department MUST record an immutable, append-only audit/evidence trail for every campaign, operation, capture, export, anonymization, kill-switch action, and teardown. Every reported number MUST be derivable from that trail.
- **FR-008**: The UI MUST use the platform's existing design system and tokens. Donor palettes, donor components, and donor navigation MUST NOT be reproduced.
- **FR-009**: An unavailable donor service, credential, or endpoint MUST be named in `missing[]`. The UI MUST NOT render a fabricated zero, a blank pane, or a default presented as a measurement.
- **FR-010**: Donor verification MUST be completed before enablement: pinned version/revision, AGPL-3.0 licence, attribution, source-offer obligation, dependency licences, and a verified `donors/registry.yaml` entry. An unverified donor MUST be reported as a blocker, not claimed ready.
- **FR-011**: The full mode MUST be governed by the existing RoE gate, encrypted artifact store, audit chain and kill switch. No separate runtime governance-ratification gate is required.
- **FR-012**: A kill switch MUST stop all lab activity within five seconds and preserve evidence. Teardown MUST be auditable and MUST NOT delete evidence, reports, or derived artifacts.
- **FR-013**: Training events MUST be tracked on a separate track and MUST NOT be summed into the phishing funnel.
- **FR-014**: Rosters MUST contain valid, unique email identities. Templates, domains, and branding MUST be synthetic or explicitly authorized. Asset references MUST use `lab://`, `http(s)://`, or a relative path.
- **FR-015**: Reports MUST state provenance, limitations, and whether each figure is measured, derived, or unavailable. Imputed or estimated metrics MUST NOT be presented as measurements.
- **FR-016**: Tenant isolation MUST apply to campaigns, operations, captures, reports, and lab sessions. Cross-tenant access MUST return the same shape as a genuinely absent object.
- **FR-017**: The department MUST expose a readiness/capability matrix covering donor, version, licence, lab status, egress policy, RoE state, and missing prerequisites.
- **FR-018**: The department MUST be disableable per donor and as a whole. Disabling MUST delete no evidence and MUST leave prior derived artifacts intact.
- **FR-019**: Every capture and session MUST carry a retention policy and expiry. Expired artifacts MUST be deleted with an audit record; counts and pseudonyms MUST survive.
- **FR-020**: The system MUST distinguish authorization refusal (`409`), roster/target refusal (`422`), missing setup (`424`/`503`), and partial failure, and the UI MUST present them as different facts.

### Key Entities

- **Lab Environment**: the RoE-gated boundary, its egress policy, status, reset and teardown state.
- **Campaign**: a Phishing Club campaign - template, valid roster, sender profile, schedule, state, RoE, ATT&CK mapping, and derived funnel.
- **Roster / Recipient**: a valid email identity approved for a campaign.
- **Template / Lure**: a multi-stage email/page flow, its variables, assets, provenance, and authorization status.
- **Sender Profile / Domain**: the SMTP/API sender and domain, with TLS/DNS readiness and credential state.
- **AiTM Session / Proxy Flow**: a RoE-bound reverse-proxy or remote-browser session, its target, captured artifacts, encryption state, retention, and access audit.
- **Captured Artifact**: a session cookie, token, or credential captured under RoE; encrypted at rest, redacted in presentation, retention-bound.
- **Operation**: a Caldera/AEL plan execution — abilities, techniques, state, RoE, lab fixture, and evidence.
- **Engagement Event**: one event in the closed fourteen-event-plus-voice taxonomy, with channel, stage, track, and optional pseudonym.
- **Training Assignment**: assigned/started/completed training, kept separate from phishing risk.
- **Report**: a campaign/assessment summary with provenance, limitations, and per-figure status.
- **RoE Sign-off**: scope, approver, signed-at, expiry, and approved target set.
- **Audit Event**: actor, action, object, time, outcome, and correlation id.
- **Capability / Readiness**: donor, version, licence, egress policy, RoE state, adapter service URL, and missing prerequisites.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero unauthorized sends, operation starts, or AiTM sessions across the acceptance suite; 100% of attempts without a confirmed RoE are refused.
- **SC-002**: 100% of outbound lab activity requires a confirmed RoE, and malformed targets or unsupported asset schemes are refused in the acceptance suite.
- **SC-003**: 100% of captured artifacts are encrypted at rest and access-audited; zero raw secrets appear in UI, logs, or exports.
- **SC-004**: An operator can create and run a lab campaign end-to-end in under ten minutes.
- **SC-005**: 100% of campaign/operation figures in a report trace to immutable evidence in an automated lineage check.
- **SC-006**: The donor registry entry is verified (version, AGPL-3.0, attribution, source offer) before the capability can be enabled.
- **SC-007**: The kill switch stops all lab activity in five seconds or less and preserves evidence.
- **SC-008**: The department renders with platform design tokens only; no donor palette or donor component is present, and the UI screenshot gate passes.
- **SC-009**: Unavailable services produce named absences; zero fabricated zeros appear in contract tests.
- **SC-010**: At least one full lab campaign, one AiTM session, and one Caldera operation are demonstrated end-to-end with evidence-backed reports.
- **SC-011**: Anonymization and retention expiry preserve exact counts and stable pseudonyms.
- **SC-012**: Cross-tenant access to a campaign, capture, or report returns the same shape as an absent object.

## Authorization Boundary

The full red-team tier is authorized by a confirmed, unexpired RoE for each engagement. The earlier ADR-0040 lab-only exception and constitutional Amendment 2.1.0 were removed by the owner; there is no runtime governance-ratification gate.

Every action remains bounded by:

1. The RoE gate and its approval record.
2. Encrypted artifact storage, tenant isolation, redaction and retention.
3. The append-only audit chain and kill switch.
4. Donor verification and the platform adapter contract.

Usage remains limited to authorized red-team activity. Real credentials or brand impersonation without authorization, and bypassing MFA on production systems, are out of scope.

## Assumptions

- The operator records a confirmed, unexpired RoE before any campaign, operation or session.
- Phishing Club is used under AGPL-3.0; attribution and the source-offer obligation are recorded. No public network service is offered without AGPL compliance.
- Caldera and AEL are already vendored and working; this feature reuses them and does not build a new C2.
- Phishing Club's backend runs as a service behind a platform adapter; its frontend and palette are not ported.
- The department is a new SpecOps destination; the existing CI/SpecOps canvas and its simulation-only Phishing/SAT panel remain available until a migration decision is recorded in the plan.
- Templates and assets may use `lab://`, `http(s)://`, or relative paths.
- Retention windows are configured per campaign and align with the existing engagement-fabric policy.

## Dependencies

- Donor verification and registry update for Phishing Club (AGPL-3.0, version pin, attribution, source offer).
- Confirmed RoE records for every campaign, operation and session.
- Phishing Club service, Caldera, AEL, and the existing `specops.roe.gate` and engagement fabric.
- Existing platform design system, evidence substrate, and tenant isolation.

## Out of Scope

- Production phishing, real target lists, real credentials, or real brand impersonation without authorization.
- Bypassing MFA on production systems.
- Porting Phishing Club's backend or frontend.
- Building a new C2 or replacing Caldera/AEL.
- Full legal review; the owner remains responsible for authorization and use.
- Egress and process hardening beyond the lab boundary (the lab boundary itself is in scope).
