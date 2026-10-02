# UI Global Upgrade — COGNITIVE UI 2.0

**Companion to**: `input.md` (Platform Convergence, 534 sections).
**Binding**: the platform correctness requirements in `input.md` apply to this UI. The UI is the operator surface for the context-driven continuous intelligence fabric, and MUST NOT weaken any platform invariant to simplify its own implementation.

---

## 1. PRODUCT ESSENCE

COGNITIVE UI is a **technocratic investigation workstation** for evidence-centric research. It is not a dashboard, not a marketing site, and not a monitoring console.

The product essence is a single continuous loop made visible:

```
OBSERVATION → CONTEXT → INTERPRETATION → HYPOTHESIS → VALIDATION
          → CLAIM → PROJECTION → WORLDLINE → next CONTEXT
```

Every screen MUST make it obvious which stage of the loop the operator is in, what the current evidence state is, and what the platform believes and why.

**The primary surface is the Investigation Workspace.** Acquisition, Findings, Analysis, Quality, and Ops are views *within* an investigation, not peer products.

---

## 2. STACK — FIXED, NOT NEGOTIABLE

- **React 18** — no migration to React 19, no rewrites of the render tree.
- **Vite** — build and dev server stay.
- **Zustand** — client/UI state only.
- **TanStack Query** — server state only. It MUST NOT hold client-only state such as selection, layout, or panel visibility.
- **Cytoscape.js** — graph rendering.
- **ECharts** — time series and charts.
- **CSS Modules + design tokens** — no Tailwind, no CSS-in-JS runtime, no component library replacing the design system.
- **`@xyflow/react` may be used for non-graph node canvases** (e.g. pipeline/flow views), but MUST NOT be used for the investigation graph; the graph stays Cytoscape.

Rationale: the stack is a solved problem. The requirement is depth of capability, not technology substitution.

---

## 3. VISUAL DIRECTION

### 3.1 Register
Big-tech intelligence workstation. Neomilitarist precision, near-black graphite, restrained instrumentation green, amber for metadata, red reserved for genuine semantic failure. Data-dense but calm. No decoration without data meaning.

### 3.2 Palette (normative tokens)

| Token | Value | Role |
|---|---|---|
| `--bg-0` | `#070909` | app background |
| `--bg-1` | `#0B0E0D` | panel background |
| `--surface-0` | `#121715` | raised surface, cards |
| `--surface-1` | `#161B18` | hover / secondary surface |
| `--surface-2` | `#1C221E` | active / selected surface |
| `--border-0` | `#252C28` | default border |
| `--border-1` | `#323B35` | strong border, focus |
| `--text-primary` | `#E5EAE7` | primary text |
| `--text-secondary` | `#A5AEA9` | secondary text |
| `--text-muted` | `#6E7873` | tertiary, metadata, axis labels |
| `--accent-green` | `#8FCB64` | primary accent, semantic state |
| `--accent-green-bright` | `#A7E477` | active accent, focus ring |
| `--accent-amber` | `#B99A66` | warning, provenance, metadata |
| `--accent-red` | `#BF5B57` | semantic failure only |
| `--accent-blue` | `#718D9B` | informational, secondary series |

### 3.3 Forbidden
- No purple or magenta as a decorative or series color.
- No neon glow, bloom, or gradient text.
- No glassmorphism. No frosted-blur panels.
- No Web3 styling: no wallet chrome, no token/gas metaphors, no coin shapes, no "connect wallet".
- No rainbow categorical palettes. Series colors MUST come from the restrained set above, differentiated by lightness and saturation, not by hue rotation.
- No HUD reticles, scanlines, corner brackets, or fake telemetry chrome.
- No emoji as UI iconography. Icons are inline SVG from a single curated set.
- No gradient meshes, no aurora backgrounds, no noise overlays.

### 3.4 Anti-patterns to eliminate on sight
- Placeholder panels that render an empty state where a real view is required.
- `Lorem ipsum`, `TODO`, `Coming soon`, `—` used as a stand-in for data.
- Skeleton loaders that never resolve into real content.
- Mock/fabricated numbers in a production build. If no data exists, the view MUST show an explicit, honest empty state naming what is missing.
- Duplicated controls offering the same action.
- Icon-only buttons with no tooltip and no accessible name.
- Layout shift on data arrival. Skeletons MUST reserve the final geometry.

---

## 4. TYPOGRAPHY AND DENSITY

### 4.1 Type
- UI: `Inter`, system fallback stack.
- Mono: `JetBrains Mono` for IDs, digests, offsets, timestamps, raw payloads, code, and any value where character-level comparison matters.
- Tabular numerals for every numeric column. Non-tabular figures in data tables are a defect.

### 4.2 Density modes
`COMPACT | STANDARD | COMFORTABLE`, default `STANDARD`.

| Mode | Row height | Base font | Panel gap |
|---|---|---|---|
| `COMPACT` | 26px | 12px | 8px |
| `STANDARD` | 32px | 13px | 12px |
| `COMFORTABLE` | 40px | 14px | 16px |

Density MUST apply globally and consistently — tables, lists, tree rows, timeline lanes, and graph node chrome. A density that applies to tables but not to the graph is a defect.

### 4.3 Information density
Target 3–4× the data density of a typical SaaS dashboard. Default to showing data, not to hiding it behind progressive disclosure. Progressive disclosure is reserved for genuinely rare operations.

---

## 5. BREAKPOINTS

`1024 / 1280 / 1440 / 1920 / 2560`.

- `1024` — investigation panel collapses to a drawer; graph and inspector remain side by side.
- `1280` — full three-column: rail / canvas / inspector.
- `1440` — baseline target for design review.
- `1920` — inspector gains a second column; evidence and lineage stack side by side.
- `2560` — max content width is NOT fluid-to-infinity. Content MUST be capped and centered, or the graph MUST be the only element allowed to expand. Unbounded text line length is a defect.

Mandatory visual regression viewports: `1440×900`, `1920×1080`, `2560×1440`.

---

## 6. GLOBAL STATE

### 6.1 Selection
One global `SelectionState` in Zustand. Selection survives view changes, panel collapse, navigation, and data refetch. A selection MUST NOT be silently dropped because a query revalidated.

```ts
interface SelectionState {
  investigationId: string | null
  objectId: string | null          // canonical object identity
  objectType: ObjectType | null
  evidenceIds: string[]            // multi-select evidence
  timeRange: [number, number] | null
  graphMode: GraphMode             // 'graph' | 'timeline' | 'matrix' | 'table'
  filters: Record<string, unknown>
  lineageMode: 'none' | 'upstream' | 'downstream' | 'both'
  focusedPath: string | null
}
```

### 6.2 Server vs client boundary
- TanStack Query owns: observations, captures, claims, entities, edges, worldline snapshots, obligation state, saturation metrics, science metrics.
- Zustand owns: selection, density, panel layout, view mode, command palette state, local UI toggles.
- A violation of this split (server data in Zustand, or selection in Query cache) is a defect.

### 6.3 URL as shareable state
URL MUST encode: `investigation`, selected object, active view, time range, active filters, graph mode. Reload MUST restore the full working state. Deep links MUST be shareable as investigation state, not merely as a route.

### 6.4 Server/client separation
Every view MUST be buildable and testable against a fixture server with no backend running. A view that cannot render without a live backend is a defect.

---

## 7. INVESTIGATION WORKSPACE — CRITICAL VERTICAL SLICE

This is the mandatory end-to-end path. It MUST work before any other view is polished:

```
Investigation list
  → Investigation Workspace
    → Graph
      → click Entity
        → Inspector shows entity
          → click Claim
            → Evidence panel shows supporting + contradicting observations
              → Timeline shows the entity's worldline window
                → lineage / pivot
                  → trigger acquisition at a frontier
                    → new observations arrive
                      → Graph updates without reload, context preserved
```

Requirements:
- Zero full page reloads anywhere in the slice.
- Selection and time range MUST persist across every transition above.
- New observations MUST arrive via streaming/invalidation and update the graph incrementally, never by full re-fetch-and-replace.
- The frontier MUST be visible and actionable from the slice: the operator can see what the platform does not yet know and can direct acquisition at it.

---

## 8. REQUIRED VIEWS

| View | Must show |
|---|---|
| **Investigation Workspace** | the critical vertical slice above; context, obligations, frontier |
| **Acquisition** | runtime capability routing, task queue, live capture stream, artifact addresses |
| **Objects** | full object table, filters, multi-select, record detail with lineage |
| **Evidence** | observation list, supporting/contradicting, raw artifact access, parser provenance |
| **Findings / Claims** | claims with evidence, confidence, derivation path, contradiction state |
| **Analysis** | causal model, identification/estimate/refute, TDA, change-point, calibration |
| **Quality** | parser health, coverage, saturation metrics, drift, calibration error |
| **Ops** | event stream, consumer lag, schema registry, failure journal, replay controls |

**No view may ship as a placeholder.** If a view's data is not yet available, it MUST render an honest, specific empty state that names the missing dependency.

---

## 9. GRAPH

- Cytoscape.js, deterministic layout (the platform's `edgeFormation` contract governs edge semantics; the UI MUST NOT re-derive or re-interpret them).
- Undirected and directed edges MUST render distinctly. Collapsing them into one visual form is a defect.
- Node styling MUST encode semantic state (type, confidence, saturation, contested) through the restrained palette, not through rainbow categorical coloring.
- Selection, hover, and focus states MUST be visually distinct and keyboard reachable.
- Graph MUST remain usable at 5 000+ nodes via level-of-detail: aggregate at low zoom, reveal on zoom.
- Graph mode toggles: `graph | timeline | matrix | table` — the same selection MUST be preserved across all four.

---

## 10. TIMELINE

- ECharts for time series.
- Timeline MUST show the worldline window: entity life events, state transitions, evidence arrival, and claim changes on a shared time axis.
- Time range is global state (§6.1) and MUST drive graph filtering, evidence filtering, and analytics simultaneously.
- Missing data MUST render as an explicit gap, never interpolated silently.

---

## 11. COMPONENT SYSTEM

- One curated inline-SVG icon set. No mixed icon libraries, no emoji.
- Buttons, inputs, selects, tabs, tables, panels, badges, tooltips, modals, drawers, toasts — each with a single canonical implementation.
- No component may be duplicated with a different name for the same purpose.
- Every interactive element MUST have: an accessible name, a keyboard path, a visible focus state, and a tooltip when icon-only.
- Loading states MUST reserve final geometry (no layout shift).
- Empty states MUST be specific and actionable, never generic.

---

## 12. ACCESSIBILITY

- Full keyboard operability. Command palette with global shortcuts.
- WCAG AA contrast minimum for all text on its actual background.
- Semantic roles and labels throughout; the graph and timeline MUST have accessible non-visual representations of the same data.
- Focus MUST always be visible and MUST never be trapped except in a modal, where it MUST be restorable on close.
- `prefers-reduced-motion` MUST be honored; no view may depend on animation to convey state.

---

## 13. PERFORMANCE

- Route-level code splitting; panels and graph engines MUST NOT be in the initial bundle.
- Virtualized tables and lists beyond 500 rows.
- Graph layout computation MUST NOT block the main thread.
- Target: interactive shell in under 2s on a mid-range laptop; no view may exceed 16ms per interaction frame during normal operation.

---

## 14. MIGRATION — INCREMENTAL, NO REWRITE

The existing frontend is reused, not replaced. Migration is staged:

| Stage | Scope |
|---|---|
| 1 | Foundation: tokens, primitives, density, breakpoints |
| 2 | Shell: navigation, app layout, command palette, global selection |
| 3 | Graph and timeline canvases |
| 4 | Evidence and object surfaces |
| 5 | Acquisition, Ops, Quality views |
| 6 | Analysis and Science views |
| 7 | Critical vertical slice end-to-end |
| 8 | Visual regression, accessibility, performance |

Each stage MUST leave the build green and MUST NOT regress the test count. A stage that cannot be completed MUST be reported as incomplete with the specific blocker, not left half-written in the working tree.

---

## 15. ACCEPTANCE

1. `npm run build` succeeds.
2. `npm run lint` reports zero errors.
3. `npm test` reports zero failures.
4. The critical vertical slice (§7) completes with zero full page reloads and preserved selection.
5. No placeholder panels, no fabricated data, no forbidden visual patterns (§3.3–3.4) anywhere in the shipped UI.
6. Density modes apply globally and consistently (§4.2).
7. Visual regression passes at all three mandatory viewports (§5).
8. Accessibility: zero WCAG AA violations; full keyboard operability.
9. URL state restores the complete working context after reload (§6.3).
10. Every view renders correctly against a fixture server with no backend running (§6.4).
