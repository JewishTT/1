# COGNITIVE UI component library

## Public API

Import shared UI primitives from `apps/webapp/src/ui/index.ts`. The barrel is the supported application-level API; consumers should not reach into component files unless they are implementing the library itself.

| Group | Exports | Contract |
|---|---|---|
| Actions | `Button`, `IconButton` | Named icon-only controls; consistent size and variant vocabulary |
| Classification | `Badge`, `StatusDot` | Closed semantic tone/status vocabulary; words accompany status color |
| Forms | `Input`, `Textarea`, `Select`, `Checkbox`, `RadioGroup` | Visible labels, associated hints, stable ids, native keyboard/mobile behavior, optional monospace values |
| Navigation | `Tabs` | Accessible tablist with roving focus and arrow/Home/End navigation |
| Overlays | `Tooltip`, `Popover`, `Drawer`, `Modal` | Labelled surfaces; modal traps Tab, closes on Escape, locks body scroll and restores focus on close |
| Surfaces | `Panel` | Shared low-radius surface, accessible heading, description and action slots |
| Tables | `DataTable` | Caption, stable row keys, accessible ascending/descending sort, roving row focus (arrows/Home/End), selection state, bounded horizontal overflow |
| Feedback | `EmptyState`, `Skeleton`, `LoadingView`, `ErrorView`, `Toast` | Honest empty/loading/failure states; retry only when meaningful |
| Context actions | `ContextMenu` | Stable item ids, disabled states, Escape and outside-click dismissal |
| Icons | `Icon` and `IconName` | One in-repo SVG family; no Unicode glyphs as interface iconography |
| Vocabulary | `WorkStatus`, `statusTone` | Closed list of recognized operational states |

Domain state and behavior stay outside the primitives. The library never invents evidence, counts, status, provenance or entity relationships. Selection remains the workspace store's responsibility; server state remains in TanStack Query; graph drawing remains Cytoscape.

## Visual reference

Run the app and visit `/ui-kit`. This internal route is deliberately absent from analyst navigation. The page imports from the public barrel and showcases action variants, input contracts, classification/status states, locally scoped density changes, sortable data-table selection/filtering, empty/loading/error feedback, modal focus handling and dismissible toast announcements.

Use the page when reviewing both themes, all density modes, and the 2560×1440, 1920×1080, 1440×900, 1023px, 767px and 390px breakpoints. It is a visual fixture, not a substitute for inspecting actual investigation screens.

## Visual register: neo-militarist cyberpunk

The direction is deliberately restrained: graphite and steel surfaces, instrument-green for active/confirmed state, amber for metadata and classification, and semantic red only for failure. The cyberpunk character comes from precision, technical typography, compact data presentation, and disciplined signal hierarchy — not neon saturation, gradients, HUD corners, scanlines or glow. Geometry is more industrial (small radii, clean dividers, narrow signal rails), but hierarchy still comes from spacing, type weight and selection.

The fifteen normative palette values in `ui-upgrade.md §3.2` are unchanged. Use only their semantic `--ui-*` aliases. Do not introduce a second palette or a style-only accent.

## Screenshot regression is part of every UI change

After the webapp tests, CI runs both `npm run ui:shoot:design-system` and `npm run ui:shoot:specops` against the live Vite development server. The `cognitive-ui-screenshots` artifact is uploaded even when a screenshot sweep fails, provided the production build passed.

The design-system sweep captures the six normative viewport sizes, the top and bottom of the scrollable catalogue, all catalogue sections, local density preview, both themes, modal behavior and success/error toast surfaces. Its `manifest.json` records viewport width, document/body scroll width, shell/theme state, navigation client/scroll widths and browser errors. The SpecOps sweep photographs the actual nested department tabs, including GhostLine, checks light theme and takes the required responsive viewport captures. This extends visual regression beyond the catalogue into a high-complexity legacy surface.

The sweeps assert that the shell mounts, the browser reports no uncaught/page-console errors, document/body do not grow wider than the viewport, and the top navigation does not clip its contents. These geometric assertions do not claim pixel-perfect visual correctness by themselves. Open the PNG artifact and inspect the images for clipping, overlap, illegible metadata, focus visibility and unintended style regressions. When a visual discrepancy appears, fix the owning component/token rule and rerun both sweeps before considering the change complete.

## Rules for new components

1. Use semantic `--ui-*` tokens. Never introduce a component-local palette or raw color literals.
2. Keep state color semantic: green for confirmed/healthy, amber for classification/temporal metadata, red only for actual failure, and blue for informational analysis. The label always carries meaning independently of color.
3. Use the shared type scale, spacing/radius/elevation/density/motion tokens. Avoid glow, glass, HUD framing, gradients and shadow-as-hierarchy.
4. Every control has a visible or programmatic name, a visible keyboard focus state, a disabled state when applicable, and no dead click target.
5. Long identifiers, URIs, payloads, tables and media must be contained by the pane that owns them, not widen the document.
6. Loading, empty, failed and unavailable are different states. Do not render placeholder values that resemble real platform data.
7. Keep business logic, API calls, selection ownership and state transitions in domain/workspace layers. Components own presentation and generic interaction mechanics only.

## Quality gates

- TypeScript and production build: `npm run build`
- Unit and contract tests: `npm test`
- ESLint: `npm run lint`
- Route screenshot sweep: `npm run ui:shoot:routes -- http://127.0.0.1:5173/investigations http://127.0.0.1:5173/ui-kit`
- SpecOps/GhostLine sweep: `npm run ui:shoot:specops`

Playwright sweeps need a running app and usable fixture/backend services. The screenshots still require human inspection; a green syntax check does not mean a screenshot sweep was executed.
