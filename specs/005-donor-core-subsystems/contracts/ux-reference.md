# UX Reference: PANO patterns (pattern-only)

**Date**: 2026-09-08 | **Feature**: [spec.md](../spec.md)

**License gate**: PANO is **CC BY-NC-4.0** (no commercial reuse, no copying).
This document records UX *patterns* observed in
`donors/PANO/ui/` (managers/views/styles/dialogs) as design guidance for the
COGNITIVE webapp. **No code from PANO is ported or copied.** This artifact is a
spec/design reference; per FR-012 all reuse is pattern-level only and documented here.

## Observed patterns (from `donors/PANO/ui/`)

1. **Timeline-first subject review** — `managers/timeline_manager.py`,
   `styles/timeline_style.py`, `dialogs/timeline_editor.py`: an investigation's
   evidence is presented as a subject-centric timeline; facts are grouped by the
   entity they describe and ordered by date. *Applied in COGNITIVE as:* the
   webapp evidence/timeline rendering groups assertions per subject with a stable
   date ordering and empty-state handling.
2. **Status as a first-class manager** — `managers/status_manager.py`: UI status
   (reviewed/unreviewed/conflict, evidence presence) is derived and cached per
   subject, then surfaced as badges, not recomputed ad-hoc in render.
   *Applied as:* `review.ts` `buildNodeReviewStatusMap` → `DerivedNodeReviewStatus`.
3. **Entity/property editing surfaces** — `dialogs/property_editor.py`,
   `dialogs/edge_properties.py`: single-subject property panels show only
   identifying, schema-featured properties first, then the rest sorted. *Applied
   as:* OpenOSINT `_FEATURED_PROPS` ordering carried into review display groupings.
4. **Graph/node/edge visual styling by kind** — `styles/{node,edge,map}_style.py`:
   deterministic mapping from entity/edge kind to a visual style. *Applied as:*
   the existing `GraphPanel` link-kind styling (kafSIEM links port, track 004);
   PANO reinforces the "stable style mapping" convention.
5. **Command/manager separation** — `commands/graph_commands.py`,
   `managers/layout_manager.py`: user actions are commands; layout/derivation are
   managers kept out of the view layer. *Applied as:* review filters/sorts are pure
   functions in `review.ts`; views stay thin.

## What was NOT taken from PANO

- No code, no component trees, no styling values, no dependency approach.
- Nothing from PANO is referenced in the shipped bundle (grep gate on the track: no
  PANO paths imported).

## Attribution

- PANO upstream: `donors/PANO` (CC BY-NC-4.0). This document exists so the
  pattern-level influence is traceable without copying its code.