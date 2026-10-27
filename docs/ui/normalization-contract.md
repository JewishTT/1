# UI system normalization — implementation contract

This document defines the normalization boundary for the COGNITIVE analyst workbench. It complements, and does not replace, the binding requirements in `specs/024-context-driven-continuous-intelligence/ui-upgrade.md`.

## Principles

1. **One canonical palette.** Product surfaces consume semantic `--ui-*` aliases; aliases resolve to the normative palette in `styles/tokens/color.css`. No new hex values in component styles.
2. **One global density.** `data-density` is applied at the document root and shell. Tables, graph labels, timeline lanes, evidence rows, controls and spacing must derive from the same density tokens.
3. **One typography contract.** UI prose uses the sans token; identifiers, digests, timestamps and copyable values use the mono token. Numeric data uses tabular figures.
4. **One interaction contract.** Keyboard focus is always visible, icon-only actions have an accessible name, disabled controls are visibly disabled, and reduced-motion preferences are respected.
5. **One responsive boundary.** Workbench columns and long data values may shrink or scroll; they must not force the application shell wider than the viewport. Below 1024px the shell header becomes content-sized and wraps; work-state counts remain present rather than being clipped or silently hidden. The command palette and canvas toolbar must fit phone-sized viewports.
6. **One source of truth for server state.** TanStack Query owns fetched data; Zustand owns selection, density, panel layout and transient UI state.
7. **No invented data.** Empty, unavailable, loading, stale and failed states must remain distinct. Never turn unavailable data into a numeric zero or fabricate operational telemetry.

## Layering

`styles/tokens/` owns palette, typography, spacing, density and motion values. Existing component styles own component-specific layout. `styles/normalization.css` is a narrow compatibility layer for cross-cutting interaction, typography, overflow and accessibility rules. It must not become a second component library or override domain semantics. Its only intentional selector exception to `.ui-root` scoping is `.ui-palette-root`, the first-party command-palette portal mounted outside the workbench subtree.

## Visual sweep

From `apps/webapp/`, run `npm run ui:shoot:specops -- [baseUrl] [outDir]` against a running application and its fixture/backend services. The script uses Playwright's bundled Chromium by default; set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` only when a system browser is required. Screenshots default to the operating system's temporary directory under `cognitive-ui-shots`.

The sweep captures each SpecOps panel, the light theme, and GhostLine at the normative 2560×1440, 1920×1080 and 1440×900 viewports, plus 1100px, 1023px, 767px and 390px. It fails on browser console/page errors or document-level horizontal overflow. The PNGs still require human visual review; a clean script run is not proof of visual quality.

## Review checklist

- [ ] All visual colors resolve to canonical tokens; no decorative purple/magenta, gradients, glow or glass effects.
- [ ] Compact / standard / comfortable density changes every data surface consistently.
- [ ] 1440×900, 1920×1080 and 2560×1440 are checked; at 1024px the workspace remains usable without horizontal page overflow.
- [ ] At 1023px and below, the topbar grid row grows with wrapped content; navigation and work-state readouts do not overlap.
- [ ] At 767px and below, canvas actions wrap, the command palette stays within the viewport, and long lists scroll internally.
- [ ] Keyboard-only operation exposes a visible focus indicator and all icon-only actions have accessible names.
- [ ] Reduced-motion preference is respected.
- [ ] Numeric columns use tabular numerals; machine identifiers use the mono token.
- [ ] Loading, empty, unavailable, stale and error states are truthful and visually distinct.
- [ ] Server data remains in Query; selection and local layout remain in Zustand.
- [ ] Responsive normalization contract tests pass, alongside existing tests, typecheck, lint and production build before merge.

## Scope note

The normalization layer is scoped to `.ui-root`, with the explicit `.ui-palette-root` portal exception for the command palette. Legacy pages and scoped donor styles remain isolated until they are migrated surface-by-surface; broad global selectors would create cross-layer regressions and are not an acceptable shortcut.
