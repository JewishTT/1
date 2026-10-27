import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { GRAPH_TOKENS, LEGACY_NODE_TOKENS } from "../../ui/tokens";
import { DENSITIES, DEFAULT_DENSITY, THEME_NAMES } from "../../workspace/types";

/**
 * The design-token and layout contracts, asserted against the SHIPPED
 * stylesheets (T134, T136, T137, T138, T139, T140, FR-102/103/104).
 *
 * WHY THESE ARE TESTS AND NOT A CODE REVIEW CONVENTION.
 *
 * Every failure these guard against has already happened in this repository, and
 * in each case it was invisible:
 *
 *   - `color.css` held `--ui-accent: #46c07a` while the spec fixed phosphor
 *     `#8FCB64`. Nothing broke, because nothing compared the two.
 *   - `data-density` and `data-theme` appeared in ZERO `.ts`/`.tsx` files. The
 *     token blocks were declared, `toggleDensity()` moved a Zustand field, and
 *     not one pixel changed. Green build, green lint, green tests.
 *   - `graph.css`, `timeline.css` and `evidence.css` referenced zero density
 *     tokens, so the graph stayed one size in all three modes.
 *   - There were ZERO width-based media queries in app-owned CSS, while §5 names
 *     five breakpoints.
 *
 * A convention cannot catch any of that. These read the files that ship, so a
 * re-tune that misses one place is a failing test rather than a visual
 * discrepancy somebody notices during review — which is the point of §4.2's
 * "a density that applies to tables but not to the graph is a defect".
 */

function readShipped(...segments: string[]): string {
  let dir = process.cwd();
  for (let depth = 0; depth < 6; depth += 1) {
    const candidate = path.join(dir, "src", ...segments);
    if (existsSync(candidate)) return readFileSync(candidate, "utf8");
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  throw new Error(`not found above ${process.cwd()}: ${segments.join("/")}`);
}

/* ── T134 / FR-102 — the fifteen normative palette tokens ─────────────── */

/**
 * ui-upgrade §3.2, quoted verbatim.
 *
 * Deliberately a SECOND copy. The whole point is to detect drift between the spec
 * and `color.css`; asserting that `color.css` agrees with a constant imported from
 * `color.css` would be a tautology.
 */
const NORMATIVE_PALETTE: ReadonlyArray<readonly [string, string]> = [
  ["--bg-0", "#070909"],
  ["--bg-1", "#0b0e0d"],
  ["--surface-0", "#121715"],
  ["--surface-1", "#161b18"],
  ["--surface-2", "#1c221e"],
  ["--border-0", "#252c28"],
  ["--border-1", "#323b35"],
  ["--text-primary", "#e5eae7"],
  ["--text-secondary", "#a5aea9"],
  ["--text-muted", "#6e7873"],
  ["--accent-green", "#8fcb64"],
  ["--accent-green-bright", "#a7e477"],
  ["--accent-amber", "#b99a66"],
  ["--accent-red", "#bf5b57"],
  ["--accent-blue", "#718d9b"],
];

/** The `:root, [data-theme="dark"]` block, which is the dark theme's declaration. */
function darkBlock(css: string): string {
  return css.split('[data-theme="dark"]')[1]?.split("}")[0] ?? "";
}

describe("T134 — all fifteen §3.2 tokens, at the spec's values (FR-102)", () => {
  const css = readShipped("styles", "tokens", "color.css");

  it("declares every one of the fifteen names in the dark theme", () => {
    for (const [name] of NORMATIVE_PALETTE) {
      expect(darkBlock(css), `${name} is missing from the dark block`).toContain(`${name}:`);
    }
  });

  it.each(NORMATIVE_PALETTE)("%s is exactly %s", (name, value) => {
    // Case-insensitive on the value: CSS hex is case-insensitive and the file
    // lowercases the spec's upper-case digits. The DIGITS are the contract.
    const declared = new RegExp(`${name}:\\s*([^;]+);`, "i").exec(darkBlock(css))?.[1]?.trim().toLowerCase();
    expect(declared, `${name} is not declared in the dark block`).toBe(value);
  });

  it("declares all fifteen in the light theme too", () => {
    const light = css.split('[data-theme="light"]')[1] ?? "";
    for (const [name] of NORMATIVE_PALETTE) {
      expect(light, `${name} is missing from the light block`).toContain(`${name}:`);
    }
  });

  it("keeps the accent phosphor, not the pure green it used to be", () => {
    // The specific regression this file exists for: `--ui-accent` pointed at
    // `#46c07a`, a pure green, where §3.2 fixes phosphor `#8FCB64`. A different
    // hue family, so the mistake was invisible rather than a shade.
    const accent = new RegExp("--ui-accent:\\s*([^;]+);", "i").exec(darkBlock(css))?.[1]?.trim().toLowerCase();
    expect(accent).toBe("var(--accent-green)");
    expect(NORMATIVE_PALETTE).toContainEqual(["--accent-green", "#8fcb64"]);
  });

  it("derives every --ui-* alias from a normative token, so no alias owns a value", () => {
    const block = darkBlock(css);
    const aliases = [...block.matchAll(/(--ui-[\w-]+):\s*([^;]+);/g)];
    expect(aliases.length).toBeGreaterThan(20);
    for (const [, name, value] of aliases) {
      // An alpha/wash variant may be an `rgba(...)` — it is derived from a
      // normative hue, and is documented as such in the file's own header.
      const isReference = value.trim().startsWith("var(--");
      const isDerivedAlpha = /^(rgba|color-mix)\(/.test(value.trim());
      expect(isReference || isDerivedAlpha, `${name}: ${value} owns a value`).toBe(true);
    }
  });
});

/* ── T137 / FR-103 — three density modes, default STANDARD ───────────── */

describe("T137 — COMPACT | STANDARD | COMFORTABLE, default STANDARD", () => {
  const css = readShipped("styles", "tokens", "density.css");

  it("declares exactly the three modes §4.2 names, in that order", () => {
    expect([...DENSITIES]).toEqual(["compact", "standard", "comfortable"]);
  });

  it("has a :root block carrying the default mode", () => {
    expect(DEFAULT_DENSITY).toBe("standard");
    expect(css.split(":root,")[1], ":root must carry a density block").toContain("--ui-row-h");
  });

  it.each([
    ["compact", 26, 12, 8],
    ["standard", 32, 13, 12],
    ["comfortable", 40, 14, 16],
  ])("%s — row %dpx, font %dpx, gap %dpx", (density, row, font, gap) => {
    // §4.2's table, quoted independently of density.css.
    const block = css.split(`[data-density="${density}"]`)[1]?.split("}")[0] ?? "";
    expect(block, `${density} has no block`).not.toBe("");
    expect(Number(block.match(/--ui-row-h:\s*(\d+)px/)?.[1]), `${density} --ui-row-h`).toBe(row);
    expect(Number(block.match(/--ui-density-font:\s*(\d+)px/)?.[1]), `${density} --ui-density-font`).toBe(font);
    expect(Number(block.match(/--ui-density-gap:\s*(\d+)px/)?.[1]), `${density} --ui-density-gap`).toBe(gap);
  });

  it("declares all three themes the shell can write", () => {
    expect([...THEME_NAMES]).toEqual(["dark", "light"]);
  });
});

/* ── T138 / FR-103 — density reaches the graph, the timeline, evidence ── */

describe("T138 — density is global, not a table-only feature", () => {
  const densityToken =
    /var\(--ui-(?:density-font|density-gap|row-h|stack-gap|cell-pad-y|pane-pad|block-pad-y|lane-h|node-label-font)\)/;

  it.each([
    ["graph/graph.css", "graph canvas"],
    ["timeline/timeline.css", "timeline"],
    ["evidence/evidence.css", "evidence"],
    ["objects/objects.css", "objects table"],
    ["styles/components/index.css", "primitives"],
    ["styles/workspace/index.css", "workspace"],
    ["styles/shell/index.css", "shell"],
    ["styles/base/index.css", "base layer"],
  ])("%s applies density tokens (%s)", (file) => {
    const css = readShipped(...file.split("/"));
    expect(
      densityToken.test(css),
      `${file} references no density token — density would not reach it`,
    ).toBe(true);
  });

  it("keeps the graph's node label size on a density token rather than a literal", () => {
    // Cytoscape cannot consume `var()`, so the token is READ and handed over
    // resolved — which means the literal font size must not appear in the
    // stylesheet it is applied with. The read lives in `graph/semantics.ts`
    // beside the palette read it belongs with; `GraphCanvas.tsx` consumes it.
    const semantics = readShipped("graph", "semantics.ts");
    expect(semantics).toContain("--ui-node-label-font");
    expect(readShipped("graph", "graph.css")).toContain("--ui-node-label-font");
    expect(readShipped("graph", "GraphCanvas.tsx")).not.toMatch(/"font-size":\s*\d/);
  });
});

/* ── T139 / FR-104 — the five width breakpoints ──────────────────────── */

describe("T139 — width breakpoints at 1024 / 1280 / 1440 / 1920 / 2560", () => {
  const breakpoints = readShipped("styles", "layout", "breakpoints.css");

  it.each([
    [1024, "max-width: 1279px"],
    [1280, "max-width: 1279px"],
    [1920, "min-width: 1920px"],
    [2560, "min-width: 2560px"],
  ])("covers %d", (_width, condition) => {
    expect(breakpoints).toContain(condition);
  });

  it("names 1440, even though no rule changes at it", () => {
    // §5 calls 1440 the baseline design-review target. A breakpoint with no rules
    // is the record of that decision, and losing the sentence loses the anchor.
    expect(breakpoints).toContain("1440");
  });

  it("collapses the rail into a drawer below 1280 and keeps the inspector beside the canvas", () => {
    const narrow = breakpoints.split("@media (max-width: 1279px)")[1]?.split("@media")[0] ?? "";
    expect(narrow).toContain(".ui-workbench-rail");
    expect(narrow).toContain("position: absolute");
    // Graph and inspector stay side by side — §5's actual requirement.
    expect(narrow).toContain(".ui-workbench-inspector");
  });

  it("gives the inspector a second column at 1920", () => {
    // The rule describes the inspector's CONTENT, so it lives in the inspector's
    // stylesheet. `breakpoints.css` owns the pane width; this owns the grid.
    const workspace = readShipped("styles", "workspace", "index.css");
    const wide = workspace.split("@media (min-width: 1920px)")[1]?.split("@media")[0] ?? "";
    expect(wide).toContain("grid-template-columns: repeat(2");
    // …and the shell's frame widens the pane at the same width.
    expect(breakpoints).toContain(".ui-workbench-inspector");
  });

  it("puts width-based media queries in app-owned CSS", () => {
    // The baseline: zero width queries existed anywhere the application owns.
    for (const file of [
      "styles/layout/breakpoints.css",
      "graph/graph.css",
      "evidence/evidence.css",
      "objects/objects.css",
      "styles/workspace/index.css",
    ]) {
      const css = readShipped(...file.split("/"));
      expect(/@media\s*\((max|min)-width/.test(css), `${file} has no width query`).toBe(true);
    }
  });

  it("stacks the graph side panels below 1280 rather than squeezing the canvas", () => {
    const graph = readShipped("graph", "graph.css");
    const narrow = graph.split("@media (max-width: 1279px)")[1]?.split("@media")[0] ?? "";
    expect(narrow).toContain(".ui-graph-side");
    expect(narrow).toContain("flex-direction: column");
  });
});

/* ── T140 / FR-104 — 2560 is capped and centred ───────────────────────── */

describe("T140 — content is capped and centred at 2560", () => {
  const breakpoints = readShipped("styles", "layout", "breakpoints.css");

  it("caps the shell's own rows and centres them", () => {
    const wide = breakpoints.split("@media (min-width: 2560px)")[1] ?? "";
    expect(wide).toContain("max-width: var(--ui-content-max-w)");
    expect(wide).toContain("margin-inline: auto");
    for (const row of [".ui-topbar", ".ui-activity", ".ui-shell-body"]) {
      expect(wide, `${row} is uncapped at 2560`).toContain(row);
    }
  });

  it("caps prose so a line length cannot run to infinity", () => {
    expect(breakpoints).toContain("--ui-measure-max-w");
    expect(breakpoints).toContain("max-width: var(--ui-measure-max-w)");
  });

  it("lets the graph be the exception §5 names", () => {
    const wide = breakpoints.split("@media (min-width: 2560px)")[1] ?? "";
    const graphException = wide.split(".ui-graph,")[1] ?? "";
    expect(graphException).toContain("max-width: none");
  });

  it("states a cap wide enough that 1920 is never the binding constraint", () => {
    const cap = Number(/--ui-content-max-w:\s*(\d+)px/.exec(breakpoints)?.[1]);
    expect(cap).toBeGreaterThan(1920);
  });
});

/* ── T135 — no token is referenced that is not declared ───────────────── */

describe("T135 — every token this codebase reads is declared in a stylesheet", () => {
  it("declares every --c-* token referenced from ui/tokens.ts", () => {
    const legacy = readShipped("styles", "legacy", "legacy-tokens.css");
    const referenced = [
      ...Object.values(LEGACY_NODE_TOKENS),
      ...Object.values(GRAPH_TOKENS),
    ].map((binding) => binding.cssVar);
    expect(referenced.length).toBeGreaterThan(30);
    for (const cssVar of referenced) {
      expect(legacy, `${cssVar} is read from TypeScript but not declared`).toContain(`${cssVar}:`);
    }
  });

  it("declares every --c-type-* accent the two legacy graphs reference", () => {
    const legacy = readShipped("styles", "legacy", "legacy-tokens.css");
    for (const name of [
      "account",
      "organisation",
      "device",
      "location",
      "infrastructure",
      "tool",
      "unknown",
      "email",
      "username",
      "phone",
      "domain",
      "url",
      "name",
      "org",
      "location-alt",
    ]) {
      expect(legacy, `--c-type-${name} is not declared`).toContain(`--c-type-${name}:`);
    }
  });
});

/* ── UI normalization — narrow shell and interaction contract ────────── */

describe("UI normalization — responsive shell and accessible interaction", () => {
  const normalization = readShipped("styles", "normalization.css");

  it("keeps the shell grid row content-sized when the topbar wraps", () => {
    const narrow = normalization.split("@media (max-width: 1023px)").slice(-1)[0]?.split("@media")[0] ?? "";
    expect(narrow).toContain(".ui-root.ui-shell");
    expect(narrow).toContain("grid-template-rows: auto minmax(0, 1fr) auto");
    expect(narrow).toContain(".ui-root .ui-topnav");
    expect(narrow).toContain(".ui-root .ui-topbar-work");
    expect(narrow).toContain("overflow: visible");
  });

  it("does not hide work-state counts on narrow screens", () => {
    const narrow = normalization.split("@media (max-width: 1023px)").slice(-1)[0]?.split("@media")[0] ?? "";
    expect(narrow).toContain(".ui-root .ui-topbar-counts");
    expect(narrow).toContain("flex-wrap: wrap");
    expect(narrow).not.toMatch(/\.ui-topbar-counts\s*\{[^}]*display:\s*none/s);
  });

  it("constrains the command palette to a phone viewport", () => {
    const phone = normalization.split("@media (max-width: 767px)").slice(-1)[0] ?? "";
    expect(phone).toContain(".ui-palette-root {");
    expect(phone).toContain(".ui-palette-root .ui-palette-list");
    expect(phone).not.toContain(".ui-root .ui-palette-root");
    expect(phone).toContain("width: 100%");
    expect(phone).toContain("max-height: 84dvh");
    expect(phone).toContain("overflow-y: auto");
  });

  it("retains reduced-motion support and a visible keyboard focus ring", () => {
    expect(normalization).toContain("@media (prefers-reduced-motion: reduce)");
    expect(normalization).toContain(":focus-visible");
    expect(normalization).toContain("outline: 2px solid var(--ui-focus-ring");
  });

  it("does not override semantic GhostLine gate borders with a blanket selector", () => {
    expect(normalization).toContain("Keep GhostLine's gate/setup/absent border semantics intact.");
    expect(normalization).not.toMatch(/\.ui-holo-edge\s*\{/);
    expect(normalization).not.toMatch(/\.ui-holo-bracket\s*\{/);
  });
});


describe("UI normalization — GhostLine keeps semantics without decorative glow", () => {
  const normalization = readShipped("styles", "normalization.css");

  it("flattens nested traces and refusal surfaces onto canonical tokens", () => {
    expect(normalization).toContain(".ui-root .ui-gl-refusal");
    expect(normalization).toContain(".ui-root .ui-gl-stage");
    expect(normalization).toContain(".ui-root .ui-gl-trace > li");
    expect(normalization).toContain(".ui-root .ui-gl-turns > li");
    expect(normalization).toContain("background: var(--ui-surface-1)");
    expect(normalization).toContain("box-shadow: none");
  });

  it("retains active and gate state through semantic borders and washes", () => {
    expect(normalization).toContain(".ui-gl-card[data-active=\"true\"]");
    expect(normalization).toContain("background: var(--ui-accent-wash)");
    expect(normalization).toContain("border-left-color: var(--holo-hue, var(--ui-border))");
    expect(normalization).toContain(".ui-gl-rungs > li[data-current=\"true\"]");
  });

  it("removes text glow from machine readouts while keeping the live marker", () => {
    expect(normalization).toContain(".ui-gl-readout-value");
    expect(normalization).toContain(".ui-gl-readout[data-tone=\"live\"] .ui-gl-readout-value::after");
    expect(normalization).toContain("text-shadow: none");
  });

  it("keeps section headings neutral; accent is reserved for semantic state", () => {
    expect(normalization).toContain(".ui-root .ui-gl-subhead .ui-pane-title");
    expect(normalization).toContain("color: var(--ui-text-secondary)");
  });

  it("removes HUD corner brackets and shared holographic readout text glow", () => {
    expect(normalization).toContain(".ui-root .ui-holo-bracket::before");
    expect(normalization).toContain(".ui-root .ui-holo-bracket::after");
    expect(normalization).toContain(".ui-root .ui-holo-readout-value");
    expect(normalization).toContain(".ui-root .ui-holo-heading::after");
    expect(normalization).toContain("content: none");
  });
});


describe("UI normalization — token ownership and cascade order", () => {
  it("uses semantic tokens instead of embedding a second palette", () => {
    const normalization = readShipped("styles", "normalization.css");
    expect(normalization).not.toMatch(/#[0-9a-f]{3,8}\b/i);
    expect(normalization).not.toMatch(/rgba?\(/i);
    expect(normalization).toContain("background: var(--ui-accent-wash)");
  });

  it("loads normalization after application, legacy and scoped donor styles", () => {
    const layers = readShipped("styles", "layers.css").trim();
    expect(layers.endsWith('@import "./normalization.css";')).toBe(true);
    expect(layers.indexOf('@import "./normalization.css";')).toBeGreaterThan(
      layers.indexOf('@import "./scoped/netforensicai.css";'),
    );
    expect(layers).toContain('@import "./bridge/vitni.css";');
    expect(layers).not.toContain('donors/pano/pano-tokens.css');
    expect(layers).not.toContain('donors/vitni/v2.css');
    expect(layers).not.toContain('donors/vitni/search.css');
    expect(layers).not.toContain('donors/vitni/evidence-reports.css');
    expect(layers).not.toContain('donors/rengine/timeline.css');
    expect(layers).not.toContain('donors/rengine/scrollspyNav.css');
  });

  it("bridges every legacy palette name to a canonical token", () => {
    const bridge = readShipped("styles", "tokens", "legacy-bridge.css");
    expect(bridge).toContain("--color-cyber: var(--ui-analytical)");
    expect(bridge).toContain("--color-cyber-hi: var(--ui-text)");
    expect(bridge).toContain("--color-ember: var(--ui-gold)");
    expect(bridge).toContain("--color-matri: var(--ui-accent)");
    expect(bridge).toContain("--color-crimson: var(--ui-danger)");
    expect(bridge).toContain("--color-violet: var(--ui-text-secondary)");
    expect(bridge).toContain("--color-magenta: var(--ui-text-secondary)");
    expect(bridge).toContain("--color-abyss: var(--ui-bg)");
    expect(bridge).toContain("--color-abyss-2: var(--ui-surface-1)");
    expect(bridge).toContain("--color-frame: var(--ui-border)");
    expect(bridge).toContain("--color-ghost: var(--ui-text)");
    expect(bridge).not.toMatch(/#[0-9a-f]{3,8}\b/i);
  });
});


describe("UI normalization — pane-contained payloads and media", () => {
  const normalization = readShipped("styles", "normalization.css");

  it("contains preformatted payloads and long inline identifiers", () => {
    expect(normalization).toContain(".ui-root pre");
    expect(normalization).toContain("overflow: auto");
    expect(normalization).toContain("overflow-wrap: anywhere");
    expect(normalization).toContain("overscroll-behavior: contain");
  });

  it("prevents oversized media from widening the workbench", () => {
    expect(normalization).toContain(".ui-root :where(img, video, canvas)");
    expect(normalization).toContain("max-width: 100%");
  });
});


describe("UI normalization — CI metrics and nested keyboard focus", () => {
  const normalization = readShipped("styles", "normalization.css");

  it("uses flat token-backed CI metric bars and preserves semantic outcome borders", () => {
    expect(normalization).toContain(".ui-root .ui-ci-metrics");
    expect(normalization).toContain(".ui-root .ui-ci-bar");
    expect(normalization).toContain(".ui-root .ui-ci-bar-alt");
    expect(normalization).toContain("background: var(--ui-analytical)");
    expect(normalization).toContain('.ui-ci-abilities > li[data-state="failed"]');
  });

  it("keeps a visible keyboard ring on the GhostLine textarea", () => {
    expect(normalization).toContain(".ui-root .ui-gl-textarea:focus-visible");
    expect(normalization).toContain("outline: 2px solid var(--ui-focus-ring)");
  });
});


describe("UI normalization — theme-owned overlay scrims", () => {
  it("declares drawer and modal scrims for dark and light themes", () => {
    const colors = readShipped("styles", "tokens", "color.css");
    expect(colors).toContain("--ui-scrim-drawer: rgba(0, 0, 0, 0.32)");
    expect(colors).toContain("--ui-scrim-modal: rgba(0, 0, 0, 0.42)");
    expect(colors).toContain("--ui-scrim-drawer: rgba(18, 23, 20, 0.18)");
    expect(colors).toContain("--ui-scrim-modal: rgba(18, 23, 20, 0.24)");
  });

  it("keeps component styles bound to the semantic scrim tokens", () => {
    const components = readShipped("styles", "components", "index.css");
    expect(components).toContain("background: var(--ui-scrim-drawer)");
    expect(components).toContain("background: var(--ui-scrim-modal)");
    expect(components).not.toMatch(/rgba?\(/i);
  });
});


describe("UI normalization — scoped donor palettes", () => {
  it("maps SpiderFoot and NetForensicAI colors to canonical tokens", () => {
    const spiderfoot = readShipped("styles", "scoped", "spiderfoot.css");
    const netforensicai = readShipped("styles", "scoped", "netforensicai.css");
    for (const stylesheet of [spiderfoot, netforensicai]) {
      expect(stylesheet).not.toMatch(/#[0-9a-f]{3,8}\b/i);
      expect(stylesheet).not.toMatch(/rgba?\(/i);
    }
    expect(spiderfoot).toContain("--sf-panel: var(--ui-surface-1)");
    expect(spiderfoot).toContain("--sf-cyan: var(--ui-analytical)");
    expect(netforensicai).toContain("--panel: var(--ui-surface-1)");
    expect(netforensicai).toContain("--accent: var(--ui-analytical)");
    expect(netforensicai).toContain("background: var(--ui-danger-wash)");
    expect(netforensicai).toContain("border: 1px solid var(--ui-danger-line)");
  });

  it("preserves donor namespace boundaries and allows SpiderFoot zebra rows", () => {
    const spiderfoot = readShipped("styles", "scoped", "spiderfoot.css");
    const netforensicai = readShipped("styles", "scoped", "netforensicai.css");
    expect(spiderfoot).toContain(".sf-scope table");
    expect(netforensicai).toContain(".nfa-scope .panel");
    expect(spiderfoot).not.toContain("background-color: var(--sf-panel) !important");
  });
});


describe("UI normalization — Vitni review/lineage bridge", () => {
  it("scopes adapter selectors and removes the donor purple/glow palette", () => {
    const bridge = readShipped("styles", "bridge", "vitni.css");
    expect(bridge).toContain(".ui-root .review-item");
    expect(bridge).toContain(".ui-root .lineage-fact");
    expect(bridge).not.toMatch(/#[0-9a-f]{3,8}\b/i);
    expect(bridge).not.toMatch(/rgba?\(/i);
    expect(bridge).not.toMatch(/(?:linear|radial|conic)-gradient\(/i);
    expect(bridge).not.toMatch(/box-shadow:\s*0\s+0/i);
  });
});


describe("UI normalization — legacy shell compatibility", () => {
  it("maps legacy chrome aliases to canonical tokens inside the workbench root", () => {
    const normalization = readShipped("styles", "normalization.css");
    expect(normalization).toContain("--c-bg: var(--ui-bg)");
    expect(normalization).toContain("--c-surface: var(--ui-surface-1)");
    expect(normalization).toContain("--c-danger: var(--ui-danger)");
    expect(normalization).toContain("--c-warning: var(--ui-gold)");
    expect(normalization).toContain("--acc-glow: none");
  });

  it("removes legacy body overlays above the modern shell without globally restyling other pages", () => {
    const normalization = readShipped("styles", "normalization.css");
    expect(normalization).toContain("body:has(.ui-root)::before");
    expect(normalization).toContain("body:has(.ui-root)::after");
    expect(normalization).toContain("display: none");
    expect(normalization).toContain("background-image: none");
    expect(normalization).toContain(".ui-root .sidebar");
    expect(normalization).toContain(".ui-root .header");
    expect(normalization).toContain(".ui-root .module-tabs");
    expect(normalization).toContain(".ui-root .op-tile::before");
    expect(normalization).toContain(".ui-root .panel::before");
  });

  it("keeps legacy selection and event semantics while removing decorative glow", () => {
    const normalization = readShipped("styles", "normalization.css");
    expect(normalization).toContain('.ui-root .node-card[data-selected="true"]');
    expect(normalization).toContain('.ui-root .feed-item[data-kind="science.invariant"]');
    expect(normalization).toContain("border-color: var(--ui-analytical)");
    expect(normalization).toContain("border-color: var(--ui-danger)");
    expect(normalization).toContain("animation: none");
  });
});


describe("UI normalization — RadioGroup contracts", () => {
  it("provides labelled radio controls through the public component-library barrel", () => {
    const input = readShipped("ui", "Input.tsx");
    const barrel = readShipped("ui", "index.ts");
    const styles = readShipped("styles", "components", "index.css");
    expect(input).toContain("export interface RadioGroupProps");
    expect(input).toContain("type=\"radio\"");
    expect(input).toContain("<legend className=\"ui-field-label\">{label}</legend>");
    expect(barrel).toContain("RadioGroup");
    expect(styles).toContain(".ui-radio-group");
    expect(styles).toContain(".ui-radio input:focus-visible");
  });
});
