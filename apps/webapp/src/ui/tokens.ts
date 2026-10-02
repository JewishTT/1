/**
 * Reading design tokens from the DOM.
 *
 * WHY THIS EXISTS AT ALL.
 *
 * CSS resolves `var(--token)` itself, so a stylesheet never needs this. Two
 * consumers do need it, and they are the reason:
 *
 *   1. **Cytoscape.** It builds a stylesheet in JavaScript and paints to a
 *      `<canvas>`. A canvas cannot resolve `var()` — the value has to be a
 *      colour string by the time it reaches `fillStyle` — so the token has to be
 *      read out of the cascade and handed over resolved. `graph/semantics.ts`
 *      already established this pattern (`readGraphPalette`) for the investigation
 *      graph; this is the same seam generalised, so the three legacy graph panels
 *      stop carrying their own private copy.
 *   2. **Anything that builds a colour string in JS** for a DOM attribute.
 *
 * WHAT IT IS NOT. It is not a theme engine and it holds no values. Every colour
 * it returns was declared in a token stylesheet; this only reads one back. The
 * `fallback` argument exists for the same reason `GRAPH_PALETTE_FALLBACK` does —
 * jsdom cannot resolve a custom property, and an early paint can beat the
 * stylesheet — and a fallback is a last resort, never the normal path.
 *
 * `graph/semantics.ts` remains the owner of the graph's own token list; this
 * module owns the mechanism, so there is one way to read a token rather than one
 * per canvas surface.
 */

/** The CSS variable name for a token, and the value to use if it cannot be read. */
export interface TokenBinding {
  readonly cssVar: string;
  readonly fallback: string;
}

export type TokenBindingMap<K extends string> = Readonly<Record<K, TokenBinding>>;

export type ResolvedTokens<K extends string> = { [P in K]: string };

/**
 * Read one custom property off an element's computed style.
 *
 * Returns the fallback — never an empty string — when the element is absent, the
 * environment cannot compute a style, the property is undeclared, or the value is
 * whitespace. An empty colour string handed to a canvas renderer is an invalid
 * fill, which fails silently and draws nothing, so the "empty means use the
 * fallback" rule is load-bearing rather than defensive.
 */
export function readCssToken(host: Element | null | undefined, cssVar: string, fallback: string): string {
  if (!host || typeof window === "undefined") return fallback;
  let computed: CSSStyleDeclaration | null = null;
  try {
    computed = window.getComputedStyle(host);
  } catch {
    return fallback;
  }
  if (!computed) return fallback;
  const value = computed.getPropertyValue(cssVar).trim();
  return value === "" ? fallback : value;
}

/**
 * Resolve a set of tokens in one pass.
 *
 * One `getComputedStyle` for the whole map rather than one per token: a graph
 * stylesheet asks for ~18, and the reads are cheap individually but the sum is
 * a style recalculation per call site on every theme or density change.
 */
export function resolveTokens<K extends string>(
  host: Element | null | undefined,
  bindings: TokenBindingMap<K>,
): ResolvedTokens<K> {
  const resolved = {} as Record<K, string>;
  for (const key of Object.keys(bindings) as K[]) {
    resolved[key] = readCssToken(host, bindings[key].cssVar, bindings[key].fallback);
  }
  return resolved as ResolvedTokens<K>;
}

/**
 * The legacy `--c-*` tokens, for surfaces that have not been migrated yet.
 *
 * `styles/legacy/legacy-tokens.css` declares these and states the rule: "--c-* is
 * a closed set until those surfaces are migrated to --ui-*" (§62, §97). So a
 * legacy component's colours come from HERE, and the hex values below are mirrors
 * of that frozen block rather than a second palette — the same arrangement
 * `graph/semantics.ts` documents for the `--*` tokens: the stylesheet is the
 * source, and a test asserts the two agree.
 *
 * These are the legacy palette, not the §3.2 one: cyan/amber/violet rather than
 * phosphor. Re-painting the unmigrated surfaces is a migration task (§63 says do
 * not rewrite working logic for a UI rewrite), and this module exists so that when
 * it happens the change is one stylesheet edit rather than a hunt through
 * components for hex literals.
 */
export const LEGACY_NODE_TOKENS = {
  nodeFill: { cssVar: "--c-graph-node", fallback: "#0e1626" },
  nodeLabel: { cssVar: "--c-graph-node-label", fallback: "#e6edf7" },
  nodeSelected: { cssVar: "--c-graph-node-sel", fallback: "#22d3ee" },
  edge: { cssVar: "--c-graph-edge", fallback: "#3b4a63" },
  surface: { cssVar: "--c-surface-2", fallback: "#0e1626" },
  surface2: { cssVar: "--c-surface-3", fallback: "#131e33" },
  border: { cssVar: "--c-border", fallback: "#1e2a3d" },
  text: { cssVar: "--c-text", fallback: "#dde6f0" },
  textSecondary: { cssVar: "--c-text-2", fallback: "#aeb9c9" },
  muted: { cssVar: "--c-muted", fallback: "#7c889d" },
  accent: { cssVar: "--c-accent", fallback: "#22d3ee" },
  accentAlt: { cssVar: "--c-accent-2", fallback: "#f0a832" },
  danger: { cssVar: "--c-danger", fallback: "#f43f5e" },
  warning: { cssVar: "--c-warning", fallback: "#f0a832" },
  success: { cssVar: "--c-success", fallback: "#34d399" },
} as const satisfies TokenBindingMap<string>;

export type LegacyNodeTokens = ResolvedTokens<keyof typeof LEGACY_NODE_TOKENS>;

export function readLegacyNodeTokens(host: Element | null | undefined): LegacyNodeTokens {
  return resolveTokens(host, LEGACY_NODE_TOKENS);
}

/**
 * The legacy graph's surfaces, node kinds and edge families.
 *
 * The second half of the `--c-*` block added in T135: everything the two
 * unmigrated Cytoscape panels paint with. Cytoscape cannot resolve `var()`, so
 * these are read out of the cascade and handed over resolved — one call, one
 * object, one source of truth.
 *
 * Named for what it is rather than where it lives: `GRAPH_TOKENS` describes the
 * graph surfaces, and the fact that they are `--c-*` (legacy) rather than `--*`
 * (UI 2.0) is a property of the surfaces, not of this map.
 */
export const GRAPH_TOKENS = {
  canvas: { cssVar: "--c-graph-canvas", fallback: "#0a160d" },
  label: { cssVar: "--c-graph-label", fallback: "#e7f4e5" },
  labelUnderlay: { cssVar: "--c-graph-label-underlay", fallback: "#020604" },
  edgeMuted: { cssVar: "--c-graph-edge-muted", fallback: "#8da58f" },
  headerBg: { cssVar: "--c-graph-header-bg", fallback: "#0e1626" },
  headerLabel: { cssVar: "--c-graph-header-label", fallback: "#e6edf7" },

  entityBg: { cssVar: "--c-graph-entity-bg", fallback: "#100d0b" },
  entityLabel: { cssVar: "--c-graph-entity-label", fallback: "#d7c5b7" },
  correlateBg: { cssVar: "--c-graph-correlate-bg", fallback: "#06120a" },
  correlateBorder: { cssVar: "--c-graph-correlate-border", fallback: "#a6ff4d" },
  relationshipBg: { cssVar: "--c-graph-relationship-bg", fallback: "#0f1110" },
  relationshipLabel: { cssVar: "--c-graph-relationship-label", fallback: "#cbd9ca" },
  observationBg: { cssVar: "--c-graph-observation-bg", fallback: "#06120a" },
  observationBorder: { cssVar: "--c-graph-observation-border", fallback: "#a6ff4d" },
  observationLabel: { cssVar: "--c-graph-observation-label", fallback: "#a5b4c7" },
  sourceBg: { cssVar: "--c-graph-source-bg", fallback: "#0a100c" },
  sourceBorder: { cssVar: "--c-graph-source-border", fallback: "#8ca28d" },
  sourceLabel: { cssVar: "--c-graph-source-label", fallback: "#7c889d" },

  edgePossibleMatch: { cssVar: "--c-edge-possible-match", fallback: "#b5ff69" },
  edgeAssertion: { cssVar: "--c-edge-assertion", fallback: "#ff9b82" },
  edgeRelationship: { cssVar: "--c-edge-relationship", fallback: "#8ed7db" },
  edgeEvidence: { cssVar: "--c-edge-evidence", fallback: "#8ce3a0" },
  edgeSourceHost: { cssVar: "--c-edge-source-host", fallback: "#526a59" },
} as const satisfies TokenBindingMap<string>;

export type GraphTokens = ResolvedTokens<keyof typeof GRAPH_TOKENS>;

export function readGraphTokens(host: Element | null | undefined): GraphTokens {
  return resolveTokens(host, GRAPH_TOKENS);
}

/**
 * Entity-type accent tokens, by name.
 *
 * A map of token NAMES rather than a resolved palette, because the consumers
 * differ: `IntelligenceGraph.tsx` resolves them itself (it needs real values for
 * an SVG data URI), while `SpecOpsGraphPanel.tsx` resolves through `readGraphTypeTokens`
 * below. Exposing the names is what lets both work without either owning a copy of
 * the values.
 */
export const ENTITY_TYPE_TOKENS = {
  account: "--c-type-account",
  organisation: "--c-type-organisation",
  device: "--c-type-device",
  location: "--c-type-location",
  infrastructure: "--c-type-infrastructure",
  tool: "--c-type-tool",
  unknown: "--c-type-unknown",
  EMAIL: "--c-type-email",
  USERNAME: "--c-type-username",
  PHONE: "--c-type-phone",
  DOMAIN: "--c-type-domain",
  URL: "--c-type-url",
  NAME: "--c-type-name",
  ORG: "--c-type-org",
  LOCATION: "--c-type-location-alt",
  IPV4: "--c-type-tool",
  UNKNOWN: "--c-type-unknown",
} as const satisfies Readonly<Record<string, string>>;

export type EntityTypeTokenName = keyof typeof ENTITY_TYPE_TOKENS;

/** The CSS `var()` reference for an entity type's accent. */
export function entityTypeAccentVar(name: EntityTypeTokenName | string): string {
  const cssVar = ENTITY_TYPE_TOKENS[name as EntityTypeTokenName];
  return `var(${cssVar ?? ENTITY_TYPE_TOKENS.unknown})`;
}

/** The resolved accent for an entity type, for consumers that need a real colour. */
export function readEntityTypeAccent(host: Element | null | undefined, name: string): string {
  return readCssToken(host, entityTypeAccentVar(name).slice(4, -1), "#9aac9d");
}