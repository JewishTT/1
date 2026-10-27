# COGNITIVE UI component library

## Public API

Import shared UI primitives from `apps/webapp/src/ui/index.ts`. The barrel is the supported application-level API; consumers should not reach into component files unless they are implementing the library itself.

| Group | Exports | Contract |
|---|---|---|
| Actions | `Button`, `IconButton` | Named icon-only controls; consistent size and variant vocabulary |
| Classification | `Badge`, `StatusDot` | Closed semantic tone/status vocabulary; words accompany status color |
| Forms | `Input`, `Textarea`, `Select`, `Checkbox`, `RadioGroup` | Visible labels, associated hints, stable ids, native keyboard/mobile behavior, optional monospace values |
| Navigation | `Tabs` | Accessible tablist with roving focus and arrow/Home/End navigation |
| Overlays | `Tooltip`, `Popover`, `Drawer` | Keyboard dismissal, labelled surfaces, one overlay convention |
| Surfaces | `Panel` | Shared low-radius surface, accessible heading, description and action slots |
| Tables | `DataTable` | Caption, stable row keys, selection state, keyboard row selection, bounded horizontal overflow |
| Feedback | `EmptyState`, `Skeleton`, `LoadingView`, `ErrorView` | Honest empty/loading/failure states; retry only when meaningful |
| Context actions | `ContextMenu` | Stable item ids, disabled states, Escape and outside-click dismissal |
| Icons | `Icon` and `IconName` | One in-repo SVG family; no Unicode glyphs as interface iconography |
| Vocabulary | `WorkStatus`, `statusTone` | Closed list of recognized operational states |

Domain state and behavior stay outside the primitives. The library never invents evidence, counts, status, provenance or entity relationships. Selection remains the workspace store's responsibility; server state remains in TanStack Query; graph drawing remains Cytoscape.

## Visual reference

Run the app and visit `/ui-kit`. This internal route is deliberately absent from analyst navigation. The page imports from the public barrel and showcases action variants, input contracts, classification/status states, data-table selection/filtering, empty/loading/error feedback and keyboard affordances.

Use the page when reviewing both themes, all density modes, and the 2560×1440, 1920×1080, 1440×900, 1023px, 767px and 390px breakpoints. It is a visual fixture, not a substitute for inspecting actual investigation screens.

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
