import type cytoscape from "cytoscape";

import type { EdgeFamily, GraphNode, GraphObjectKind } from "./types";

/**
 * Graph Visual Language (Visual Direction §3–§4, §16, §17, §93).
 *
 * FIVE KINDS, ONE ACCENT, NO RAINBOW.
 *
 * The failure this file exists to prevent: colouring Entity blue, Claim green,
 * Observation amber and Finding red. That is a rainbow, it spends the accent
 * on kind, and it makes "green = Claim" indistinguishable from "green = this
 * is admitted" — which is the one thing green has to mean.
 *
 * So the four channels are separated by job, and each does exactly one thing:
 *
 *   SHAPE       → what kind of object this is.   (5 distinct silhouettes)
 *   GLYPH       → the same fact, in words, for anyone who cannot see shape.
 *   BORDER      → is this provisional?  solid = admitted, dashed = not.
 *   COLOUR      → admission only. Exactly one accent (green), one semantic
 *                 red (rejected/contradicted), and everything else is the
 *                 neutral steel ramp. Colour never encodes kind.
 *
 * Consequences worth stating, because they are the design:
 *   - Greyscale, colour-blind safe, and projector-safe, because shape and
 *     dash carry the same two facts as colour.
 *   - A hypothesis can never be mistaken for an admitted claim: different
 *     silhouette AND a dashed border, so removing colour entirely still
 *     shows the difference.
 *   - "Exactly one accent carries structural/confirmed meaning" is
 *     structural, not editorial: `nodeAccentFor` is the only function in this
 *     file that returns a chromatic value, and it reads `admission`, never
 *     `kind`.
 */

/** Resolved palette. Read from the host element so light mode is a real theme. */
export interface GraphPalette {
  accent: string;
  accentBright: string;
  accentLine: string;
  gold: string;
  goldLine: string;
  danger: string;
  dangerLine: string;
  steel: string;
  steelDim: string;
  steelBright: string;
  text: string;
  textMuted: string;
  textInverse: string;
  surface1: string;
  surface2: string;
  surface3: string;
  border: string;
}

/**
 * Fallback palette = the dark theme's own token values.
 *
 * These exist for exactly one situation: an environment where
 * `getComputedStyle` cannot resolve a custom property (jsdom, an early paint
 * before the stylesheet lands). In a browser the resolved values always win.
 * They are duplicated here rather than in a stylesheet because a fallback
 * that needs a stylesheet has already failed.
 *
 * Cytoscape cannot consume `var()` — it paints to a canvas — so the graph is
 * the one surface that has to hold real colour strings. They are therefore
 * mirrors of `styles/tokens/color.css` LAYER 1 (the normative palette,
 * ui-upgrade §3.2), not a second palette: `tokens.colorTokens` below is the
 * single place either of them is asserted against the spec, so a re-tune that
 * misses one of the two is a failing test rather than a two-tone graph.
 */
export const GRAPH_PALETTE_FALLBACK: GraphPalette = {
  accent: "#8fcb64",
  accentBright: "#a7e477",
  accentLine: "rgba(143, 203, 100, 0.42)",
  gold: "#b99a66",
  goldLine: "rgba(185, 154, 102, 0.38)",
  danger: "#bf5b57",
  dangerLine: "rgba(191, 91, 87, 0.45)",
  steel: "#a5aea9",
  steelDim: "#6e7873",
  steelBright: "#e5eae7",
  text: "#e5eae7",
  textMuted: "#6e7873",
  textInverse: "#070909",
  surface1: "#121715",
  surface2: "#161b18",
  surface3: "#1c221e",
  border: "#252c28",
};

const TOKENS: ReadonlyArray<keyof GraphPalette> = [
  "accent",
  "accentBright",
  "accentLine",
  "gold",
  "goldLine",
  "danger",
  "dangerLine",
  "steel",
  "steelDim",
  "steelBright",
  "text",
  "textMuted",
  "textInverse",
  "surface1",
  "surface2",
  "surface3",
  "border",
];

const CSS_VAR: Readonly<Record<keyof GraphPalette, string>> = {
  accent: "--accent-green",
  accentBright: "--accent-green-bright",
  accentLine: "--accent-green-line",
  gold: "--accent-amber",
  goldLine: "--accent-amber-line",
  danger: "--accent-red",
  dangerLine: "--accent-red-line",
  steel: "--text-secondary",
  steelDim: "--text-muted",
  steelBright: "--text-primary",
  text: "--text-primary",
  textMuted: "--text-muted",
  textInverse: "--bg-0",
  surface1: "--surface-0",
  surface2: "--surface-1",
  surface3: "--surface-2",
  border: "--border-0",
};

/** Resolve the palette from the live DOM; falls back per-property, never wholesale. */
export function readGraphPalette(host: Element | null | undefined): GraphPalette {
  if (!host) return GRAPH_PALETTE_FALLBACK;
  let computed: CSSStyleDeclaration | null = null;
  try {
    computed = typeof window === "undefined" ? null : window.getComputedStyle(host);
  } catch {
    computed = null;
  }
  if (!computed) return GRAPH_PALETTE_FALLBACK;

  const resolved = { ...GRAPH_PALETTE_FALLBACK };
  for (const token of TOKENS) {
    const value = computed.getPropertyValue(CSS_VAR[token]).trim();
    if (value !== "") resolved[token] = value;
  }
  return resolved;
}

/**
 * The node label's base font size, resolved from the density token.
 *
 * §4.2 requires density to reach "graph node chrome", and Cytoscape paints to a
 * canvas so it cannot consume `var()` — it needs the resolved string handed to
 * it. That is the whole reason `readGraphPalette` exists, and this is its
 * non-colour member: the token is `--ui-node-label-font`, which
 * `styles/tokens/density.css` sets to 10 / 11 / 12px for COMPACT / STANDARD /
 * COMFORTABLE.
 *
 * The 11px fallback is STANDARD's value, for the same reason the palette fallback
 * is the dark theme: an environment that cannot resolve a custom property should
 * get the default mode, not an arbitrary one.
 */
export const NODE_LABEL_FONT_FALLBACK = "11px";

export function readNodeLabelFont(host: Element | null | undefined): string {
  if (!host || typeof window === "undefined") return NODE_LABEL_FONT_FALLBACK;
  try {
    const value = window.getComputedStyle(host).getPropertyValue("--ui-node-label-font").trim();
    return value === "" ? NODE_LABEL_FONT_FALLBACK : value;
  } catch {
    return NODE_LABEL_FONT_FALLBACK;
  }
}

/* ── Node semantics (§16) ─────────────────────────────────────────────── */

export interface NodeSemantics {
  kind: GraphObjectKind;
  /**
   * Silhouette. Five shapes that are distinguishable at 14px and stay
   * distinguishable when two of them overlap: the primary discriminator,
   * because it needs no legend and no colour.
   */
  shape: "round-rectangle" | "diamond" | "hexagon" | "star" | "ellipse";
  /**
   * Two-letter mono token rendered on the node's label line. The same fact as
   * `shape`, in text — so a screenshot in a monochrome issue tracker is still
   * readable, and so a screen-reader label can name the kind (§67).
   */
  token: string;
  /** Resting size in px. Entity is the anchor and is largest. */
  size: number;
  /** Words shown as the accessible name and in the edge/node detail panels. */
  label: string;
}

/**
 * The kind table. Shape and token are the discriminators; note that nothing
 * in this table is a colour.
 */
export const NODE_SEMANTICS: Readonly<Record<GraphObjectKind, NodeSemantics>> = {
  Entity: {
    kind: "Entity",
    shape: "round-rectangle",
    token: "ENT",
    size: 26,
    label: "Entity",
  },
  Observation: {
    kind: "Observation",
    shape: "diamond",
    token: "OBS",
    size: 18,
    label: "Observation",
  },
  Claim: {
    kind: "Claim",
    token: "CLM",
    shape: "hexagon",
    size: 20,
    label: "Claim",
  },
  Finding: {
    kind: "Finding",
    shape: "star",
    token: "FND",
    size: 22,
    label: "Finding",
  },
  Hypothesis: {
    // The provisional silhouette: a circle, the shape that reads as "not a
    // thing yet" rather than "another thing".
    kind: "Hypothesis",
    shape: "ellipse",
    token: "HYP",
    size: 16,
    label: "Hypothesis",
  },
};

/** Longest edge of any node's silhouette — used to size the Cytoscape container. */
export const MAX_NODE_EXTENT = 26;

/* ── Admission → colour (§16, Visual Direction §4) ───────────────────── */

/**
 * THE ONE FUNCTION THAT RETURNS A CHROMATIC NODE COLOUR.
 *
 * It reads `admission` and nothing else. `kind` is not a parameter, so it
 * cannot be reached from the kind table even by accident — which is how the
 * "no rainbow" rule stops being a convention and becomes a type.
 */
export function nodeAccentFor(node: GraphNode, palette: GraphPalette): string {
  switch (node.admission) {
    case "admitted":
      return palette.accent;
    case "rejected":
      return palette.danger;
    case "provisional":
      // Provisional reads as *not yet*: steel, never amber. Amber is metadata
      // in this palette (§57), and a provisional object is not metadata.
      return palette.steel;
    case "unknown":
    case null:
      // Unreported is neutral. A guess here would be a claim about the record
      // that the record does not make (§99).
      return palette.steelDim;
  }
}

/** Provisional objects are dashed. This is the non-colour half of the rule. */
export function isDashed(node: GraphNode): boolean {
  return node.provisional;
}

/* ── Edge semantics (§17) ─────────────────────────────────────────────── */

export interface EdgeSemantics {
  family: EdgeFamily;
  /** Resting line style. Low-noise by default: thin, dim, no label. */
  lineStyle: "solid" | "dotted" | "dashed";
  /** Resting width. */
  width: number;
  /** Relative opacity at rest. Secondary relations sit below the floor. */
  opacity: number;
  /** Whether the predicate is drawn without interaction. */
  labelAtRest: boolean;
  /** Words for the legend and the edge detail panel. */
  label: string;
}

/**
 * Edge families are separated by DASH PATTERN and WEIGHT, not colour (§17).
 * At rest every edge is the same muted steel at the same weight; the family
 * only shows once an edge is selected or hovered, because an edge field that
 * is legible at rest is a field that cannot be read (§17: "thin and low-noise
 * at rest").
 */
export const EDGE_SEMANTICS: Readonly<Record<EdgeFamily, EdgeSemantics>> = {
  supports: { family: "supports", lineStyle: "solid", width: 1, opacity: 0.55, labelAtRest: false, label: "supports" },
  observes: { family: "observes", lineStyle: "solid", width: 1, opacity: 0.5, labelAtRest: false, label: "observes" },
  asserts: { family: "asserts", lineStyle: "dashed", width: 1.2, opacity: 0.6, labelAtRest: false, label: "asserts" },
  possible: {
    family: "possible",
    lineStyle: "dotted",
    width: 1,
    opacity: 0.45,
    labelAtRest: false,
    label: "possible (no merge implied)",
  },
};

/** Which family an edge belongs to, read from its own data — never inferred. */
export function edgeStyleFor(family: EdgeFamily): EdgeSemantics {
  return EDGE_SEMANTICS[family] ?? EDGE_SEMANTICS.asserts;
}

/* ── Cytoscape style projection ──────────────────────────────────────── */

/** How loudly an element is drawn relative to the current selection. */
export type Emphasis = "selected" | "path" | "neighbour" | "secondary" | "rest";

export interface NodeStyleContext {
  palette: GraphPalette;
  emphasis: Emphasis;
  /** Multi-select: elements the analyst has added to the comparison set. */
  secondary: boolean;
  /** Dimmed because a facet excluded a *neighbour*, not because it was excluded itself. */
  dimmed: boolean;
  /** The canvas is in lasso mode, so hover feedback must not fire. */
  interactive: boolean;
}

/**
 * The node style for one element. Pure: `(node, context) ⇒ style`, so the
 * visual language is unit-testable without a canvas and so "what makes this
 * node green" has exactly one answer in the codebase.
 */
export function nodeStyleFor(node: GraphNode, context: NodeStyleContext): cytoscape.Css.Node {
  const { palette, emphasis } = context;
  const semantics = NODE_SEMANTICS[node.kind];
  const accent = nodeAccentFor(node, palette);

  // Selection is the one thing that earns the accent at full strength: the
  // selected path brightens, neighbours get a restrained rule, and everything
  // else recedes (§17, Visual Direction §3).
  const selected = emphasis === "selected" || context.secondary;
  const onPath = emphasis === "path";
  const neighbour = emphasis === "neighbour";
  const dimmed = context.dimmed || emphasis === "secondary";

  const borderColor = selected
    ? palette.accent
    : onPath
      ? palette.accentLine
      : neighbour
        ? palette.steelBright
        : accent;

  const background = selected
    ? palette.accent
    : node.kind === "Hypothesis"
      ? palette.surface1
      : palette.surface2;

  const borderWidth = selected ? 2 : onPath ? 1.5 : neighbour ? 1.5 : 1;

  return {
    label: `${semantics.token}\n${node.label}\n${node.identifier}`,
    shape: semantics.shape,
    width: selected ? semantics.size + 6 : semantics.size,
    height: selected ? semantics.size + 6 : semantics.size,
    "background-color": background,
    "background-opacity": dimmed ? 0.35 : 1,
    "background-color-opacity": dimmed ? 0.35 : 1,
    "border-color": borderColor,
    "border-width": borderWidth,
    // Dashed for provisional, solid otherwise. Never a colour-only signal.
    "border-style": isDashed(node) ? "dashed" : "solid",
    "border-opacity": dimmed ? 0.25 : 1,
    color: selected ? palette.textInverse : dimmed ? palette.steelDim : palette.text,
    "font-family": "'Geist Mono', 'Cascadia Mono', 'SF Mono', Consolas, monospace",
    "font-size": node.kind === "Entity" ? 9 : 8,
    "text-wrap": "wrap",
    "text-max-width": "160px",
    "text-valign": "bottom",
    "text-margin-y": 4,
    "text-halign": "center",
    "min-zoomed-font-size": 7,
    "overlay-opacity": 0,
  } as cytoscape.Css.Node;
}

export interface EdgeStyleContext {
  palette: GraphPalette;
  emphasis: Emphasis;
  /** True while the pointer is over the edge, so the predicate can appear. */
  hovered: boolean;
}

/**
 * The edge style. The path brightens; neighbours of the selected element get a
 * restrained emphasis; everything secondary recedes (Visual Direction §3).
 */
export function edgeStyleForContext(
  family: EdgeFamily,
  context: EdgeStyleContext,
): cytoscape.Css.Edge {
  const { palette, emphasis } = context;
  const semantics = edgeStyleFor(family);
  const onPath = emphasis === "selected" || emphasis === "path";
  const neighbour = emphasis === "neighbour";
  const dimmed = emphasis === "secondary";

  const lineColor = onPath ? palette.accent : neighbour ? palette.steelBright : palette.steelDim;

  return {
    width: onPath ? 2 : neighbour ? 1.4 : semantics.width,
    "line-color": lineColor,
    "line-style": semantics.lineStyle,
    "curve-style": "bezier",
    "target-arrow-shape": onPath ? "triangle" : "none",
    "target-arrow-color": lineColor,
    opacity: dimmed ? 0.18 : onPath ? 1 : neighbour ? 0.8 : semantics.opacity,
    "arrow-scale": 0.8,
    label: "",
    color: palette.textMuted,
    "font-size": 8,
    "font-family": "'Geist Mono', 'Cascadia Mono', 'SF Mono', Consolas, monospace",
    "text-rotation": "autorotate",
    "text-background-color": palette.surface1,
    "text-background-opacity": 0.85,
    "text-background-padding": "2px",
    "min-zoomed-font-size": 6,
  } as cytoscape.Css.Edge;
}

/**
 * Does this predicate get drawn? §17: edges are label-free at rest; the
 * predicate appears when the edge is the subject of attention, because a
 * graph with every edge labelled is a graph with no labels.
 */
export function predicateIsVisible(emphasis: Emphasis, hovered: boolean): boolean {
  return emphasis === "selected" || emphasis === "path" || hovered;
}

/**
 * The legend. Every row is a shape + a word, never a swatch of colour, so the
 * legend describes the actual encoding rather than a palette §71 would forbid.
 */
export interface LegendRow {
  kind: GraphObjectKind;
  shape: NodeSemantics["shape"];
  token: string;
  label: string;
  note: string;
}

export const NODE_LEGEND: readonly LegendRow[] = [
  { kind: "Entity", shape: "round-rectangle", token: "ENT", label: "Entity", note: "materialised, anchored by records" },
  { kind: "Observation", shape: "diamond", token: "OBS", label: "Observation", note: "an immutable record extracted from a capture" },
  { kind: "Claim", shape: "hexagon", token: "CLM", label: "Claim", note: "an asserted relation with a temporal scope" },
  { kind: "Finding", shape: "star", token: "FND", label: "Finding", note: "a located observation, with why-detected" },
  { kind: "Hypothesis", shape: "ellipse", token: "HYP", label: "Hypothesis", note: "dashed — a candidate, not admitted fact" },
];

export const EDGE_LEGEND: ReadonlyArray<{ family: EdgeFamily; lineStyle: string; label: string; note: string }> = [
  { family: "supports", lineStyle: "solid", label: "supports", note: "Finding → Observation" },
  { family: "observes", lineStyle: "solid", label: "observes", note: "Entity → Observation" },
  { family: "asserts", lineStyle: "dashed", label: "asserts", note: "Entity → Entity, as reported" },
  { family: "possible", lineStyle: "dotted", label: "possible", note: "no merge implied" },
];