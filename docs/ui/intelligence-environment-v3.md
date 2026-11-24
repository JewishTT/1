# Intelligence Environment — UI v3

**Status:** implementation contract for the full analyst-surface redesign  
**Branch:** `feat/ui-intelligence-environment-v3`

This is a product redesign, not a dashboard reskin. The UI is the analyst's control surface for a process-centric, evidence-first platform. It must make work legible, shorten the path from a seed to a defensible finding, and expose uncertainty rather than disguise missing capabilities.

## Product thesis

The interface should feel like a purpose-built intelligence workstation: restrained cyber-neomilitarist material, operational typography, strong spatial hierarchy, dense but breathable evidence, and a calm command grammar. Avoid decorative cockpit gauges, fake live counters, neon overload, glass cards, gratuitous motion, and ungrounded "AI confidence" theatre.

**Visual hierarchy:** current investigation → current task/state → primary evidence or analytical canvas → provenance/context inspector → system-level operations.

## Information architecture

1. **Command** — cross-investigation work queue, recent movement, blocked obligations, system status backed by real API values.
2. **Investigations** — canonical case workspace and lifecycle. No parallel "graph app" that duplicates the case.
3. **Knowledge** — entity profiles, relationships, temporal context, search and graph projections.
4. **Evidence** — immutable observations, raw artifact access, source metadata, extraction, and complete lineage.
5. **Findings** — evidence-backed narrative, claim ledger, contradictions, confidence dimensions and unresolved questions.
6. **Operations** — Redpanda/event flow, consumer lag, worker health, outbox, retry/quarantine and storage; operational faults must link to affected work.

SpecOps, economics, geospatial and network analysis are domain workspaces over the shared investigation/evidence model, not independent truth stores.

## Canonical investigation workspace

A single responsive workspace with synchronized panes:

- **Left / Scope:** investigation identity, objective, authorization and scope, sources, frontier, outstanding research obligations, stage and budget.
- **Center / Work surface:** switchable overview, graph, timeline, evidence, findings and spatial/network views. Selection and filters are shared, URL-addressable and restorable.
- **Right / Inspector:** selected entity, observation, claim, source or finding. Display identifiers, exact source/artifact, timestamps, extraction, status, uncertainty, provenance and actions available to the current role.
- **Bottom / Activity:** actual events and recent transitions; collapsed by default when it competes with the canvas.

The panes collapse into drawers on tablet/mobile. No horizontal overflow may make the primary task inaccessible.

## Epistemic and status language

Use explicit, consistent states: **Observed → Extracted → Candidate → Proposed → Admitted → Derived**. Keep disputed, rejected, stale, partial, blocked and unsupported visible.

Never:
- promote a mention or discovery lead into an entity without the resolution/admission path;
- equate a relation candidate with a verified relation;
- show missing data as zero, success, or an invented live indicator;
- use one scalar "confidence" as a substitute for evidence support, source quality, identity confidence, freshness and relevance;
- hide a broken lineage hop behind a polished card.

## Visual system

- **Ground:** deep graphite, not pitch-black void.
- **Surfaces:** 3-4 measured elevations; thin steel dividers; square or minimally rounded corners.
- **Primary action:** semantic command accent from canonical tokens.
- **Amber:** provenance, classification and temporal annotation.
- **Red:** only errors, contradictions, quarantine and rejected evidence.
- **Typography:** high-legibility sans for narrative; tabular mono for IDs, timestamps, counts and event fields.
- **Motion:** brief state transitions only; reduced-motion honored.
- **Density:** analyst-controlled compact/comfortable modes, but compact never means tiny text or sub-24px interaction targets.
- **Accessibility:** keyboard-first navigation, visible focus, semantic landmarks, AA contrast, responsive tables and meaningful empty/loading/error/unavailable states.

## Route and component migration

1. Audit all existing route surfaces and identify their canonical domain/data owner. Keep routes and bookmarks working.
2. Establish the shared shell, tokenized primitives, page header, data table, filter bar, status chip, evidence reference, inspector, timeline and graph selection contract.
3. Complete the investigation workspace as the flagship vertical slice using real API contracts and the existing query/store patterns.
4. Migrate entity, evidence and finding pages into shared selection/provenance behavior; remove duplicate navigation and duplicate graph ownership.
5. Rebuild Command and Operations around real, nullable telemetry and linked work impact.
6. Migrate remaining specialist surfaces; remove obsolete UI and styles only after route, accessibility and Playwright coverage proves replacement.
7. Capture and inspect maintained Playwright screenshots at desktop, tablet and mobile breakpoints; test keyboard flows, deep links, loading/error/empty/unavailable states and selection performance.

## Release acceptance

- An analyst can open/create an investigation, inspect scope, follow frontier/obligations, inspect acquired observations, trace a claim to its raw source, resolve conflicts and assemble a finding without leaving the investigation context.
- Every visible finding/claim has a direct provenance path; unsupported paths are visibly partial.
- Every operational number is API-derived, timestamped and source-attributed; unavailable remains unavailable.
- No duplicate canonical workspace, navigation dead-end, mock production data, or misleading green state.
- Typecheck, lint, focused tests, full webapp test/build and maintained Playwright screenshot review pass.

## First implementation slice in this branch

The new command-environment stylesheet tightens the global shell, work-state strip, route rail, interaction focus and responsive overflow using existing semantic tokens. It intentionally does not invent metrics or replace the established React/router/store contracts. The full route migration is staged behind the above acceptance contract rather than performed as an unsafe wholesale rewrite.
