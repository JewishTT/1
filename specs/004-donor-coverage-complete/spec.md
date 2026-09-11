---
description: "Specification for covering ALL license-allowed donor repos with code extraction"
---

# Feature Specification: Full Donor Coverage

**Feature Branch**: `004-donor-coverage-complete`

**Created**: 2026-09-08

**Status**: Draft

**Input**: User description: "Надо вырезать нужные куски кода по ВСЕМ репо и прогнать speckit на весь цикл самому"

## User Scenarios & Testing

### User Story 1 - Temporal conflict detection on investigation timelines (Priority: P1)

Analysts working an investigation see contradictory date claims from sources surfaced
as an explicit signal instead of silently inconsistent data. Conflicting source dates
and ordering edges whose endpoints disagree are flagged (never auto-resolved) and
visible in the graph export summary.

**Why this priority**: Contradictory evidence is the single highest-value analytic
signal; detecting it from existing stored data costs nothing at collection time and
works retroactively on any store. Donor: investigator (MIT) `graph/temporal_consistency.py`.

**Independent Test**: A date set spanning more than `tol_days` returns a conflict
record; an ordering edge whose endpoints' dates oppose the direction is flagged;
year-only dates never manufacture a conflict.

**Acceptance Scenarios**:

1. **Given** an event with dates `["2024-05-10","2024-09-20"]`, **When** the slow conflict scan runs with a 30-day tolerance, **Then** a conflict is returned with min/max/daysApart.
2. **Given** an `event_followed_by` edge whose later endpoint is attested before the earlier one by > 30 days, **When** the scan runs, **Then** the ordering conflict is returned.
3. **Given** year-only or unparseable dates, **When** the scan runs, **Then** no conflict is produced.

---

### User Story 2 - Precise target normalization for harvested observations (Priority: P2)

Collection/harvesting concerns one canonical notion of "target" (domain, IP, email,
username) regardless of raw casing/format, so observations bind to canonical values
and deduplicate correctly. Donor: SpiderFoot (MIT, logic layer) `spiderfoot/target.py`
with its netaddr dependency rewritten to stdlib `ipaddress`.

**Why this priority**: Canonical target identity underpins acquisition + correlation;
without it the same host/email surfaces as distinct entities across sources.

**Independent Test**: Feeding raw inputs (mixed case, trailing dots, URL containing a
domain, IPv4/IPv6, email) yields classified + normalized targets; invalid inputs are
rejected gracefully.

**Acceptance Scenarios**:

1. **Given** a mixed-case hostname with a trailing dot, **When** normalized, **Then** the canonical lower-case domain without the trailing dot is produced.
2. **Given** a URL string, **When** the target type is inferred, **Then** the extracted hostname is the target.
3. **Given** an IPv4/IPv6 literal, **When** normalized, **Then** the canonical IP address (without leading zeros / shortened ranges) is produced.

---

### User Story 3 - Domain-styled graph edges in the investigation UI (Priority: P3)

The investigation graph renders semantically-styled edges and labels derived from the
correlation/link kind, so analysts read the graph type instantly. Donor: kafSIEM
(Apache-2.0) `src/lib/` pure-link logic + `src/lib/severity.ts`.

**Why this priority**: Reuses a tested, license-clean UI logic layer; low risk, high
legibility gain.

**Independent Test**: Link-kind-to-label/color mapping unit-tested in vitest; graph
edge rendering uses the mapped style.

**Acceptance Scenarios**:

1. **Given** a correlation edge kind, **When** the UI asks for its presentation, **Then** a stable label and color mapping is returned.
2. **Given** an unmapped kind, **When** the UI asks, **Then** a safe default style is returned (no crash).

---

### User Story 4 - Confidence and relationship typing for nodes in the investigation UI (Priority: P3)

Graph nodes carry reviewer confidence and relationship types use a shared vocabulary,
giving analysts consistent badges and edge categories. Donor: vitni (Apache-2.0)
`lib/confidence.ts` + `lib/relationshipTypes.ts`.

**Why this priority**: Consistency layer for the existing review workflow (accept/reject/
uncertain) and the correlation graph vocabulary.

**Independent Test**: Confidence label/color functions unit-tested; relationship-type
registry testable (stable ids, bidirectional flag, colors).

**Acceptance Scenarios**:

1. **Given** a confidence value, **When** formatted for display, **Then** a deterministic label and badge color are returned.
2. **Given** a relationship type id, **When** looked up in the registry, **Then** its label/color/bidirectionality are returned or a default is returned for unknown ids.

---

### Edge Cases

- What happens when a donor module pulls in a heavy dependency (netaddr/semhash/wordllama)? The adapted module must be rewritten to stdlib before it is admitted (FR-002).
- How does the system handle conflicting dates it cannot interpret (year-only/broken strings)? It must skip them (no false positives).
- What happens when a UI relation type is unknown or a confidence is null? Safe defaults, never a crash.
- What happens when a donor file is overloaded with framework imports? Only the pure-logic slice is cut, framework code is not ported.

## Requirements

### Functional Requirements

- **FR-001**: Each adapted module MUST carry an attribution header: source repo, license, commit-ish, and a "what changed" note.
- **FR-002**: Adapted Python modules MUST use only stdlib + already-wired deps; heavy donor deps must be rewritten out. No new runtime dependencies.
- **FR-003**: Each adapted module MUST ship unit tests runnable in the existing suites (pytest / vitest), and the full regression MUST stay green.
- **FR-004**: Each extracted piece MUST be wired into a live consumer (pipeline service, UI component, or benchmark harness), not imported dead.
- **FR-005**: The license gate MUST be respected: reNgine (GPLv3), PANO (CC BY-NC-4.0) and kipi (empty) are never copied; inspiration-only for PANO.
- **FR-006**: All four remaining allowed donor repos MUST contribute at least one adapted, tested, wired module: investigator, kafSIEM, SpiderFoot, vitni.
- **FR-007**: UI donors (kafSIEM, vitni) MUST NOT drag in their UI frameworks/Tailwind/icon sets; only pure logic + thin presentational helpers are ported into `apps/webapp/src/lib/donor/`.
- **FR-008**: The full speckit workflow (specify → plan → tasks → implement) MUST be run through and tracked in this feature directory.

### Key Entities

- **Observation dates**: per-event date sets with precision (year/month/day) used by the temporal layer.
- **Ordering edge**: directed "followed_by" edge whose endpoints carry dates that may contradict the direction.
- **Harvest target**: canonical value + type (domain, IP, email, username, URL) a collector resolves raw input into.
- **Relationship/Correlation kind**: stable vocabulary of relation ids with label, color, bidirectionality.
- **Confidence**: reviewer verdict strength (verified/unverified/asserted) with badge color.

## Success Criteria

### Measurable Outcomes

- **SC-001**: 4/4 remaining allowed donor repos contribute a tested, attributed, wired module (13/13 donors-gate: 7 allowed, 6 delivered in track 003 + track 004).
- **SC-002**: Full regression passes unchanged counts: shared ≥111, admission ≥39, bench ≥19, webapp ≥26.
- **SC-003**: `ruff check` clean on all touched Python; `tsc -b` and vitest clean on webapp.
- **SC-004**: Every extracted module is referenced by a consumer (grep-able), not dead code.
- **SC-005**: Tasks T001–T0NN in `tasks.md` all closed `[x]` with the review gate passed.

## Assumptions

- Feature directory auto-numbered under `specs/` (sequential numbering: 004).
- No git branch hook exists (`.specify/extensions.yml` is absent), so no branch/hook steps run.
- The bench harness is a legitimate "live consumer" for backend donor modules; the webapp graph/review UI is the consumer for UI donor modules.
- kafSIEM/vitni contributions are logic-level (labels, mappings, registries) plus thin, testable component helpers — not a full visual port.