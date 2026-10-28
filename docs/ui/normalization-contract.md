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

`styles/tokens/` owns palette, typography, spacing, density and motion values. Existing component styles own component-specific layout. `styles/normalization.css` is a narrow compatibility layer for cross-cutting interaction, typography, overflow and accessibility rules. It must not become a second component library or override domain semantics. Ordinary component rules are scoped to `.ui-root`, including the command palette's independent root (which carries live theme and density state). The other explicit boundary is `body:has(.ui-root)::before/after`, which disables legacy scanline overlays only while a UI 2.0 root is mounted. Legacy `--c-*` / `--acc*` variables are bridged to canonical tokens inside `.ui-root`; graph entity-kind tokens are deliberately not flattened.

## Surface audit status

| Surface | Static audit | Runtime / visual validation |
|---|---|---|
| Shared shell and primitives | Token-backed typography, focus, responsive containment and scrim tokens are covered by contract tests; `src/ui/index.ts` exposes the public primitive API and `/ui-kit` is its live reference catalogue. | Webapp build and unit/contract suite passed on an earlier head; latest head is pending CI. |
| CI / SpecOps and GhostLine | Runtime normalization removes legacy gradients, glow, glass, HUD brackets and decorative shadows; active/gate/outcome semantics are preserved. Source declarations remain marked as migration debt. | SpecOps sweep captures every department tab at desktop width and GhostLine across all contract widths; latest screenshots still require human review. |
| Graph, timeline, evidence, objects and operations/source catalogue | Static stylesheet scan found no raw hex/RGB colors, gradients, text shadows or backdrop blur. Remaining shadows are tokenized elevation or semantic inset selection markers. | Full per-surface screenshot and interaction review remains pending. |
| Legacy pages and scoped donor views | Legacy `--c-*` / `--acc*` aliases resolve through canonical UI tokens inside `.ui-root`; scanline, glow, glass and gradient chrome is suppressed on known legacy surfaces while state-bearing active/event/failure borders remain semantic. SpiderFoot and NetForensicAI adapters use canonical tokens inside `.sf-scope` / `.nfa-scope`; the Vitni review/lineage adapter is `.ui-root`-scoped. | Runtime screenshots and interaction review remain pending. |

## Visual sweep

From `apps/webapp/`, run `npm run ui:shoot:design-system -- [baseUrl] [outDir]`, `npm run ui:shoot:specops -- [baseUrl] [outDir]`, or `npm run ui:shoot:routes -- https://…/route [https://…/another-route]`. The first two need the Vite app only: design-system demo content is development-only, while the SpecOps sweep installs read-only Playwright API fixtures and rejects any mutating or unmapped request. Route sweeps of business pages still require usable application fixtures/backend services. The runners use Playwright's bundled Chromium by default; set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` only when a system browser is required. Screenshots default to the operating system's temporary directory.

The SpecOps sweep captures each department panel, the light theme, and GhostLine at the normative 2560×1440, 1920×1080 and 1440×900 viewports, plus 1100px, 1023px, 767px and 390px. The route sweep captures each supplied route at 2560×1440, 1920×1080, 1440×900, 1023×900, 767×900 and 390×844. Both fail on browser console/page errors or document-level horizontal overflow; the route sweep also fails when the app shell does not mount. The PNGs still require human visual review; a clean script run is not proof of visual quality.

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

The normalization layer is scoped to `.ui-root`, with two explicit boundary exceptions: `.ui-palette-root` (the command-palette portal outside the shell subtree) and `body:has(.ui-root)::before/after` (the legacy scanline overlays that otherwise sit above drawers and toasts). Legacy pages remain isolated; donor styles use canonical tokens inside their own namespaces and still require per-surface interaction/visual review. Broad global selectors would create cross-layer regressions and are not an acceptable shortcut.
