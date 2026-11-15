# Feature Specification: CI/SpecOps Department Fabric

**Feature Branch**: `027-ci-specops-fabric`

**Created**: 2026-10-10

**Status**: Draft

**Input**: User description: "Build the future Counterintelligence & Special Operations department as one unified fabric in the UI. Direct, maximal donor integration (take donors whole and make them work, not just concepts); make everything working and debugged first, and only afterwards handle forensics, isolation, licensing, etc. Kill-chain emulation and phishing/SAT simulation are mandatory. The design must be maximally aesthetic and elegant."

## User Scenarios & Testing *(mandatory)*

<!--
  User stories are PRIORITIZED as user journeys ordered by importance.
  Each story is INDEPENDENTLY TESTABLE — implementing just one still yields a viable slice.
-->

### User Story 1 - Unified CI/SpecOps fabric shell (Priority: P1)

An operator opens the Counterintelligence & Special Operations department and lands on one surface that presents all operational panels — operations console, kill-chain emulation, phishing/SAT, forensics, detection coverage, counterintelligence, and social-reaction simulation — as tabs of a single fabric sharing one tenant, one query client and one status vocabulary. Each panel declares its scope on screen so a tenant-wide figure is never mistaken for a statement about the case in hand.

**Why this priority**: The shell is the precondition for every other panel being reachable and coherent. Without it, each donor integration becomes an isolated page and the department reads as clutter rather than one instrument. It is independently valuable because it makes the existing operations/quarantine/source surfaces reachable from one place.

**Independent Test**: Open the department, switch between all panels, and confirm each renders its own subject and its scope label; the operations panel shows live fabric state.

**Acceptance Scenarios**:

1. **Given** an authenticated operator, **When** they open the CI/SpecOps department, **Then** they see one canvas with a tab per panel and a persistent scope note stating the department is tenant-wide unless a panel says otherwise.
2. **Given** the department is open, **When** the operator selects any panel tab, **Then** that panel's subject renders and the previously selected panel's state is preserved when returning.
3. **Given** a panel whose backing data source is unavailable, **When** it renders, **Then** it shows a named absence with the source name rather than a blank pane, a zero, or a fabricated default.

---

### User Story 2 - Kill-chain adversary emulation (Priority: P1)

A red-team operator selects an ATT&CK-based adversary emulation plan, confirms it targets an authorized lab fixture, launches it, and watches the operation run as a live matrix of planned abilities versus executed abilities with agent/C2 beacon state and pivot paths. The operator can freeze the run and inspect what each ability was expected to leave behind.

**Why this priority**: Explicitly mandatory. This is the operational core of the special-operations side and the primary reason the department exists.

**Independent Test**: Launch a micro emulation plan against a lab fixture and observe planned-vs-executed abilities populate live; the run is inspectable after completion.

**Acceptance Scenarios**:

1. **Given** a library of emulation plans, **When** the operator selects a plan, **Then** its abilities, target techniques and expected telemetry are listed before launch.
2. **Given** a selected plan and a confirmed authorized target, **When** the operator launches it, **Then** the operation runs and the console shows each ability's planned and executed state updating live.
3. **Given** a running or completed operation, **When** the operator freezes/replays it, **Then** they can inspect, per ability, the technique, the target and the telemetry the plan expected.

---

### User Story 3 - Phishing / SAT simulation under a rules-of-engagement gate (Priority: P1)

A social-engineering operator prepares an authorized phishing simulation campaign against a supervisor-approved roster, and the platform refuses to send anything until an explicit rules-of-engagement sign-off is recorded. During the simulation, entered credentials are never captured or stored, and the campaign produces engagement metrics mapped to ATT&CK.

**Why this priority**: Explicitly mandatory, and the second pillar of the special-operations side. The RoE gate is the safety property that makes the capability shippable at all.

**Independent Test**: Attempt to launch a campaign without sign-off (blocked), then with sign-off against an approved roster (runs, metrics produced, no credentials stored).

**Acceptance Scenarios**:


### User Story 4 - Counterintelligence subject board (Priority: P2)

A counterintelligence analyst opens a subject — a person, organization, account, channel or campaign — and sees its tracked invariants: belief-state, narrative-position, bias-profile, coordination-signature and phase-state, each backed by the evidence that supports it, alongside the subject's relation graph.

**Why this priority**: This is the counterintelligence half of the department; it turns the cognitive-warfare donor methods into an operator surface. Ranked P2 because it depends on the shell (US1) and on interpretation outputs that are still maturing.

**Independent Test**: Open a subject with known supporting evidence and confirm each invariant renders with its evidence links and no invariant is asserted without backing.

**Acceptance Scenarios**:

1. **Given** a selected subject, **When** the board renders, **Then** each invariant displays with the evidence references that support it.
2. **Given** an invariant with no supporting evidence, **When** the board renders, **Then** it is shown as unsupported rather than asserted as fact.
3. **Given** a subject, **When** the analyst views its relations, **Then** the relation graph renders and selecting a node reveals its supporting evidence.

---

### User Story 5 - Social-reaction simulation (Priority: P2)

An operator injects a narrative or information shock into a modeled population and projects the social reaction over time — reach, polarization and phase-transition risk — using the platform's social-simulation operators, with the run's intermediate artifacts inspectable on one screen.

**Why this priority**: Directly requested ("моделирование социальных реакций"). P2 because it is a science-heavy surface that depends on calibrated simulation operators, but it is a defining capability of the department.

**Independent Test**: Run a scenario on a modeled population and view projected reaction trajectories plus a phase-transition risk indicator, with the run's artifacts inspectable.

**Acceptance Scenarios**:

1. **Given** a modeled population and a narrative input, **When** the operator runs a projection, **Then** reaction trajectories (reach, polarization) are shown over the requested horizon.
2. **Given** a completed projection, **When** the operator inspects it, **Then** the run's artifacts (population state, drivers, intermediate states) are viewable on one screen.
3. **Given** a projection that crosses a critical threshold, **When** it renders, **Then** a phase-transition risk indicator is surfaced rather than hidden in raw numbers.

---

### User Story 6 - APT forensics: expected vs actual telemetry (Priority: P2)

An analyst opens a completed emulation run and compares the telemetry the plan expected against the observations the platform actually recorded, surfacing unmatched expectations as detection gaps and showing the coverage of ATT&CK techniques.

**Why this priority**: The forensics read-out that makes emulation pay off; requested ("эмуляция/форензика APT-угроз"). P2 because it builds on US2 output and the evidence substrate.

**Independent Test**: Open a completed run with known telemetry and confirm the expected-vs-actual comparison renders and unmatched items are listed as gaps.

**Acceptance Scenarios**:

1. **Given** a completed emulation run, **When** the analyst opens forensics, **Then** expected telemetry and actual observations are shown side by side per ability.
2. **Given** an expectation with no matching observation, **When** forensics renders, **Then** it is listed as a detection gap, not silently omitted.
3. **Given** a set of runs, **When** the analyst views coverage, **Then** ATT&CK technique coverage is shown as a heatmap.

---

### User Story 7 - Detection coverage & evidence-to-detection (Priority: P3)

A detection engineer traces a finding through evidence, behavior, ATT&CK technique, required telemetry and candidate detection rules, and validates candidates against recorded results.

**Why this priority**: Valuable defense-side closure, but the most dependent on the detection pipeline maturing; P3.

**Independent Test**: Trace one finding end-to-end through the evidence-to-detection chain and confirm each hop renders with its source.

**Acceptance Scenarios**:

1. **Given** a finding, **When** the engineer opens the detection view, **Then** the chain finding → evidence → behavior → technique → required telemetry → candidate rules renders.
2. **Given** a candidate rule, **When** validated, **Then** the validation result is recorded against the rule and visible.

---

### Edge Cases

- What happens when an emulation plan references a technique with no matching ability or agent in the lab? The console shows the gap explicitly rather than dropping it.
- How does the system handle a simulation or emulation run whose target loses authorization mid-run? The run is halted and the halt is recorded with its reason.
- What happens when a social-reaction population is too small or too sparse to project reliably? The projection reports low confidence instead of a confident-looking curve.
- How does the system handle an unrecognized status spelling arriving from a donor tool? It maps to a single "Unknown" status, never a new ad-hoc status.
- What happens when a donor's backing service is down? The panel shows a named absence with the source, and any control that cannot succeed is not offered.
- How does the system behave when a forensic expectation matches multiple observations, or none? Both are shown distinctly (corroborated vs gap).

1. **Given** a prepared campaign, **When** the operator attempts to launch without recorded rules-of-engagement sign-off, **Then** the launch is refused with the reason shown and nothing is sent.
2. **Given** a campaign targeting addresses outside the approved roster, **When** validated, **Then** the out-of-roster targets are rejected before any send.
3. **Given** an authorized campaign, **When** a simulated recipient enters credentials, **Then** those credentials are neither captured nor stored, and the disclosure that this is a test is presented.
4. **Given** a completed campaign, **When** the operator reviews results, **Then** engagement metrics are shown and mapped to ATT&CK techniques.

---


## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The department MUST present all operational capabilities as panels of one unified fabric sharing a single tenant, query client and status vocabulary, reachable from one navigation entry.
- **FR-002**: Every panel MUST declare its scope on screen so a tenant-wide figure is never read as a statement about the investigation in hand.
- **FR-003**: The department MUST integrate donor capabilities directly and wholly — running the donor's real functionality — rather than reimplementing a concept or shipping an empty placeholder; donor reuse is the default, and a donor defect is repaired on transfer, never grounds to decline the transfer.
- **FR-004**: Kill-chain adversary emulation MUST be supported: selecting an ATT&CK-based plan, confirming an authorized lab target, launching, and observing planned-vs-executed abilities live.
- **FR-005**: Phishing/SAT simulation MUST be supported and MUST be gated by an explicit rules-of-engagement sign-off that blocks any send until recorded.
- **FR-006**: Phishing simulation MUST restrict targets to a supervisor-approved roster and MUST NOT capture or store credentials entered during a simulation.
- **FR-007**: Every emulation and simulation result MUST flow back into the platform as evidence traceable to observation and claim, never as an untraceable dashboard number.
- **FR-008**: The counterintelligence board MUST present each subject invariant with its supporting evidence, and MUST render an unsupported invariant as unsupported rather than asserted.
- **FR-009**: Social-reaction simulation MUST project reaction trajectories over a requested horizon and MUST surface a phase-transition risk indicator when a critical threshold is crossed.
- **FR-010**: APT forensics MUST compare expected telemetry against recorded observations per ability and MUST list unmatched expectations as detection gaps.
- **FR-011**: The department MUST use the platform's closed status vocabulary; an unrecognized status from any donor MUST map to a single "Unknown" status.
- **FR-012**: A field or panel that a backing source does not serve MUST render as a named absence with the source name — never a zero, a default, or a derived guess.
- **FR-013**: No control may be offered that cannot succeed; where a backing source is missing, the surface MUST say so instead of offering the action.
- **FR-014**: The department MUST run donor tooling within the platform's security constraints (sandboxing, network egress policy, resource limits, tenant isolation); the engine ships no mechanism to bypass access controls and operates only through sources' public interfaces.
- **FR-015**: The department MUST be reachable as a view within the investigation lifecycle consistent with the platform's process-centric model, and its data MUST respect tenant isolation at every level.
- **FR-016**: Results MUST be re-derivable from durable evidence; projection or donor failure MUST NOT destroy or alter recorded evidence.

### Key Entities *(include if feature involves data)*

- **Operation / Emulation Run**: an execution of an adversary emulation plan against an authorized lab target; carries planned abilities, executed abilities, agent/beacon state, pivot paths, expected telemetry, and rules-of-engagement status.
- **Emulation Plan**: an ATT&CK-based plan (abilities, target techniques, expected telemetry, lab fixture) sourced from donor plan libraries.
- **Phishing Campaign**: an authorized social-engineering simulation; carries an approved roster, rules-of-engagement sign-off state, engagement metrics, and ATT&CK mapping; never stores captured credentials.
- **Subject**: the atomic counterintelligence entity (person, organization, account, channel, campaign) whose tracked invariants — belief-state, narrative-position, bias-profile, coordination-signature, phase-state — change over time.
- **Subject Invariant**: a tracked attribute of a subject, always carried with the evidence that supports it; an invariant without evidence is unsupported, not asserted.
- **Social-Reaction Projection**: a run injecting a narrative/shock into a modeled population; carries reaction trajectories, drivers, intermediate artifacts, confidence, and a phase-transition risk indicator.
- **Detection Gap**: an expected telemetry item with no matching recorded observation, surfaced explicitly in forensics.
- **Evidence / Observation / Claim**: the platform's immutable evidence chain that every emulation, simulation and counterintelligence result must trace back to.


## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can reach any of the department's panels in a single navigation action from the department entry, and every panel renders its subject within one interaction.
- **SC-002**: A kill-chain emulation plan can be launched against an authorized lab fixture and its planned-vs-executed abilities observed updating live, with the full run inspectable after completion.
- **SC-003**: A phishing campaign cannot send without a recorded rules-of-engagement sign-off (0 unauthorized sends), and 0 credentials are stored across all simulated entries.
- **SC-004**: 100% of emulation and simulation results are traceable from the figure on screen back to the supporting evidence, with no untraceable numbers displayed.
- **SC-005**: Every invariant, metric and figure shown is either backed by evidence or explicitly marked unsupported / named-absence; 0 unsupported figures are presented as fact.
- **SC-006**: An unrecognized donor status is mapped to the single "Unknown" status in 100% of cases, introducing no new status value.
- **SC-007**: The department integrates the mandated donor capabilities as running functionality (kill-chain emulation and phishing/SAT operational end-to-end) before any isolation, licensing or forensic-hardening work begins.
- **SC-008**: The department surface is judged aesthetic and elegant by the owner on first review, with a coherent visual system across all panels.

## Assumptions

- The department is a set of views within the investigation-scoped workspace (the platform is process-centric and the Investigation is the unit of work), reached through the workspace switcher, not a separate peer product.
- Direct, maximal donor integration is intended for this phase: donors are taken whole and made to run first; process isolation, license reconciliation and forensic hardening are deferred to a later phase by explicit owner decision.
- Kill-chain emulation and phishing/SAT simulation are mandatory for this department and are prioritized ahead of the remaining panels.
- All emulation and phishing activity targets authorized, isolated lab fixtures only; no capability in this department operates against production or unauthorized targets.
- Donor social-simulation and cognitive-warfare methods are used as the platform's science operators, with results returning as claims; the underlying operators may still be calibrating, which is why social-reaction and counterintelligence panels are P2.
- The existing operations, quarantine and source surfaces are the starting fabric and are absorbed into the unified department shell rather than duplicated.
- The platform's existing evidence substrate, status vocabulary and named-absence conventions are reused rather than reinvented.

