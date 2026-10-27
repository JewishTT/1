# UI system normalization — implementation contract

This document defines the normalization boundary for the COGNITIVE analyst workbench. It complements, and does not replace, the binding requirements in `specs/024-context-driven-continuous-intelligence/ui-upgrade.md`.

## Principles

1. **One canonical palette.** Product surfaces consume semantic `--ui-*` aliases; aliases resolve to the normative palette in `styles/tokens/color.css`. No new hex values in component styles.
2. **One global density.** `data-density` is applied at the document root and shell. Tables, graph labels, timeline lanes, evidence rows, controls and spacing must derive from the same density tokens.
3. **One typography contract.** UI prose uses the sans token; identifiers, digests, timestamps and copyable values use the mono token. Numeric data uses tabular figures.
4. **One interaction contract.** Keyboard focus is always visible, icon-only actions have an accessible name, disabled controls are visibly disabled, and reduced-motion preferences are respected.
5. **One responsive boundary.** Workbench columns and long data values may shrink or scroll; they must not force the application shell wider than the viewport.
6. **One source of truth for server state.** TanStack Query owns fetched data; Zustand owns selection, density, panel layout and transient UI state.
7. **No invented data.** Empty, unavailable, loading, stale and failed states must remain distinct. Never turn unavailable data into a numeric zero or fabricate operational telemetry.

## Layering

`styles/tokens/` owns palette, typography, spacing, density and motion values. Existing component styles own component-specific layout. `styles/normalization.css` is a narrow compatibility layer for cross-cutting interaction, typography, overflow and accessibility rules. It must not become a second component library or override domain semantics.

## Review checklist

- [ ] All visual colors resolve to canonical tokens; no decorative purple/magenta, gradients, glow or glass effects.
- [ ] Compact / standard / comfortable density changes every data surface consistently.
- [ ] 1440×900, 1920×1080 and 2560×1440 are checked; at 1024px the workspace remains usable without horizontal page overflow.
- [ ] Keyboard-only operation exposes a visible focus indicator and all icon-only actions have accessible names.
- [ ] Reduced-motion preference is respected.
- [ ] Numeric columns use tabular numerals; machine identifiers use the mono token.
- [ ] Loading, empty, unavailable, stale and error states are truthful and visually distinct.
- [ ] Server data remains in Query; selection and local layout remain in Zustand.
- [ ] Existing tests, typecheck, lint and production build pass before merge.

## Scope note

The normalization layer is intentionally scoped to `.ui-root`. Legacy pages and scoped donor styles remain isolated until they are migrated surface-by-surface; broad global selectors would create cross-layer regressions and are not an acceptable shortcut.
