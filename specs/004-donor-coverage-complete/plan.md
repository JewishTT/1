# Implementation Plan: Full Donor Coverage

**Branch**: `004-donor-coverage-complete` | **Date**: 2026-09-08 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-donor-coverage-complete/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command; its definition describes the execution workflow.

## Summary

Cover the four remaining license-allowed donor repos with real code extraction
(investigator, SpiderFoot logic layer, kafSIEM, vitni), adapting each slice to
COGNITIVE conventions, shipping unit tests, and wiring every module into a live
consumer. Track 003 delivered 3/7 allowed repos; this track delivers the other 4.

## Technical Context

**Language/Version**: Python 3.12 (apps/shared, apps/admission, bench), TypeScript 5.5 (apps/webapp)

**Primary Dependencies**: stdlib only (new); existing: pytest/vitest, ruff, fastapi-driven control-plane (via admission export surface), React 18 + cytoscape in webapp

**Storage**: N/A (pure value/algorithm modules; corpus unchanged)

**Testing**: pytest (shared/admission/bench) + vitest (webapp)

**Target Platform**: server pipeline + webapp UI

**Project Type**: mixed library/web-app integration

**Performance Goals**: temporal scan and target normalization must be benchmarked in `bench_donor` (p95 < 10ms for typical batch); UI mappers O(1)

**Constraints**: FR-002 stdlib-only rewrite (netaddr→ipaddress, no semhash/wordllama); FR-007 no framework port; license gate reNgine/PANO/kipi never copied

**Scale/Scope**: 2 Python modules + 2 TS lib clusters, 4 donors, 4 consumers

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- License gate respected (constitution: permissive-license code only). PASS.
- Attribution headers mandatory on all derived code. PASS (FR-001).
- No new heavy deps; stdlib-only rewrites. PASS (FR-002).
- Extract only logic/value slices; no framework or infra ports. PASS (FR-007).

## Source Map (donor → adapted module → consumer)

| Donor | License | Source file(s) | Adapted module | Consumer (live) |
|-------|---------|----------------|----------------|-----------------|
| investigator | MIT | `graph/temporal_consistency.py`, `graph/dedup.py` (date primitives only) | `apps/shared/donor/temporal.py` | `apps/admission/resolution/collective.py` `export_graph(conflict_days=...)` + `bench_donor` |
| SpiderFoot | MIT (logic) | `spiderfoot/target.py` (netaddr→ipaddress rewrite) | `apps/shared/donor/target.py` | `bench_donor` (+ import surface for acquisition) |
| kafSIEM | Apache-2.0 | `src/lib/severity.ts`, `src/lib/incident-links.ts` | `apps/webapp/src/lib/donor/links.ts` | `apps/webapp/src/components/GraphPanel.tsx` edge styling |
| vitni | Apache-2.0 | `lib/confidence.ts`, `lib/relationshipTypes.ts` | `apps/webapp/src/lib/donor/confidence.ts`, `apps/webapp/src/lib/donor/relationshipTypes.ts` | `apps/webapp/src/components/LineageWalker.tsx` + `GraphPanel.tsx` |

## Project Structure

### Documentation (this feature)

```text
specs/004-donor-coverage-complete/
  spec.md              # /speckit.specify output
  plan.md              # this file (/speckit.plan output)
  tasks.md             # /speckit.tasks output
  checklists/requirements.md
```

### Source Code

```text
apps/shared/donor/temporal.py        # investigator adaption
apps/shared/donor/target.py          # spiderfoot adaption
apps/shared/tests/unit/donor/test_temporal.py
apps/shared/tests/unit/donor/test_target.py
apps/admission/resolution/collective.py   # + export_graph conflicts
apps/admission/tests/test_collective_export.py / test_collective_temporal.py
bench/bench/harness.py               # bench_donor: temporal + target scenarios
bench/tests/test_harness.py
apps/webapp/src/lib/donor/links.ts
apps/webapp/src/lib/donor/confidence.ts
apps/webapp/src/lib/donor/relationshipTypes.ts
apps/webapp/src/lib/donor/*.test.ts
apps/webapp/src/components/GraphPanel.tsx   # styled edges
apps/webapp/src/components/LineageWalker.tsx # confidence badges
```

## Phase 0: Research (completed inline in this plan)

Direct source reads confirmed: `temporal_consistency.py` is stdlib-only and
self-contained; date primitives in `dedup.py` (`_parse_iso_date`, `to_iso_date`,
`_dates_compatible`) are stdlib-only despite module-level semhash/wordllama
imports; `spiderfoot/target.py` requires only `netaddr` (rewrite to stdlib
`ipaddress`/`ip_network`); kafSIEM `severity.ts` needs a theme-data port and
`incident-links.ts` is pure TS; vitni `confidence.ts` + `relationshipTypes.ts`
are pure TS (relationshipTypes imports `react-icons` → icon field dropped).

## Phase 1: Design

- **temporal.py**: `parse_iso_date(s)` → (y,m,d); `to_iso_date(v)` → "YYYY-MM-DD";
  `dates_compatible(a,b,window_days)`; `date_spread_conflict(dates,tol_days)`;
  `ordering_conflicts(event_dates, edges, tol_days)`; `scan(event_dates, edges,
  tol_days)` → `{"events": {...}, "orderings": [...]}`. Names renamed to
  COGNITIVE style; private → public where cross-used; tolerance parameterized.
- **target.py**: `TargetType` registry (DOMAIN, IP, EMAIL, URL, USERNAME...);
  `classify(raw)` via regexes; `normalize(raw, type)` using stdlib `ipaddress`
  for IP (canonical form), lowercasing + trailing-dot strip + punycode for
  domains; `Target` value class with `resolve()`/`aliases`. netaddr calls
  replaced by `ipaddress.ip_address` / `ipaddress.ip_network`.
- **links.ts**: `LinkKind` union; `linkLabel(kind)`, `linkColor(kind)`,
  `linkStyle(kind)` with safe default; exported pure and tested.
- **confidence.ts**: `Confidence` union (`verified`/`unverified`/`asserted`);
  `confidenceBadgeClass(c)`, `formatConfidenceLabel(c)` — theme-agnostic values
  (hex) instead of CSS-class strings.
- **relationshipTypes.ts**: `RelationshipType` registry (id, label, color,
  bidirectional, description) minus icon; `lookupRelationshipType(id)` with
  default; tested.

## Phase 2: Tasks (delegated to /speckit.tasks → tasks.md)

## Verification

- Python: `uvx ruff check`s on touched paths; `uv run --project apps/shared pytest apps/shared/tests -q`; admission suite; bench suite.
- TS: `npm run test` (vitest) + `tsc` via webapp build in `apps/webapp`.
- Regression counters: shared ≥111, admission ≥39, bench ≥19, webapp ≥26.
- Grep-verify every extracted module is imported by a consumer.