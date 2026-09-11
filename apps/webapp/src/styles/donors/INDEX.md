# Donor CSS — vendored assets

This directory contains verbatim (or minimally adapted) stylesheets pulled from the
10 donor repositories per track 005 (US5/T031). Each file keeps its **original license**
in a header above the copied content. Legal basis: the platform is non-commercial and
closed-access; PANO is CC BY-NC-4.0, vitni/kafSIEM/NetForensicAI are Apache-2.0,
SpiderFoot/reNgine are MIT.

## Import policy

`layers.css` (in `src/styles/`)
imports only the **scoped** vendor stylesheets — selectors prefixed with a vendor
namespace (`.v2-*`, `.hori-timeline`, `.sidenav`, etc.) that cannot collide with the
app's own `index.css` classes. Files that set **global** selectors (`body`, `:root`,
`*`, `tr`, `a`, form controls) are vendored here for attribution/reference and for
selective token adoption, but are **not** globally imported, so they never clobber the
app's own dark theme.

| Donor | File(s) | License | Imported? |
|-------|---------|---------|-----------|
| PANO | `pano/pano-tokens.css` | CC BY-NC-4.0 | tokens only via layers |
| vitni | `vitni/v2.css`, `vitni/search.css`, `vitni/evidence-reports.css` | Apache-2.0 | yes (scoped `.v2-*`) |
| vitni | `vitni/index.css` (global `:root`/`body`) | Apache-2.0 | no (tokens reference) |
| SpiderFoot | `spiderfoot/dark.css`, `spiderfoot/spiderfoot.css` | MIT | no (global `body`/`tr`/`a`) |
| NetForensicAI | `netforensicai/style.css` | Apache-2.0 | no (global `body`/`*`) |
| kafSIEM | `kafSIEM/theme.css`, `kafSIEM/index.css`, `kafSIEM/mobile.css` | Apache-2.0 | no (needs Tailwind v4 `@theme`) |
| reNgine | `rengine/custom.css`, `rengine/timeline.css`, `rengine/scrollspyNav.css` | MIT | timeline/scrollspyNav yes; custom.css no (global) |

> **PANO note:** PANO ships no `.css` files; its geometry/color palette lives in
> `ui/styles/{node_style,edge_style,timeline_style,map_styles}.py`. Those values were
> converted to CSS custom properties in `pano/pano-tokens.css` (the only non-verbatim
> file here, and flagged as such in its header).
>
> **kafSIEM note:** `theme.css` uses Tailwind v4 `@theme` and `color-mix()`. The webapp
> uses plain CSS (no Tailwind), so these files are vendored for provenance; the neon
> "dark matter OSINT workbench" palette (E8630A orange accent, layered surfaces) is
> adopted by hand in `pano-tokens.css`/index where relevant.
