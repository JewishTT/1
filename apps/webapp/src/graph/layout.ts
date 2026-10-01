import type cytoscape from "cytoscape";

/**
 * Layout (§15 "layout" action).
 *
 * Only Cytoscape's BUILT-IN layouts are used. `cytoscape-fcose`, `cytoscape-dagre`
 * and friends are separate packages, and §64 forbids a new runtime dependency —
 * so the layout list is the set of layouts the shipped library already has.
 * That is a real constraint on the product, not an oversight: the toolbar offers
 * five, and `LAYOUT_NAMES` is what the tests walk, so adding one later is a
 * one-line change in exactly one place.
 *
 * Every layout is deterministic where the underlying algorithm allows it, and
 * `preset` exists so a saved view can be restored rather than re-solved.
 */

export const LAYOUT_NAMES = ["cose", "breadthfirst", "circle", "grid", "preset"] as const;

export type LayoutName = (typeof LAYOUT_NAMES)[number];

export function isLayoutName(value: string): value is LayoutName {
  return (LAYOUT_NAMES as readonly string[]).includes(value);
}

/**
 * Build the layout run for a node set.
 *
 * `cose` is seeded by the platform's own deterministic layout helper rather than
 * by a random seed, so the same graph settles into the same shape after every
 * reload — the graph must not rearrange itself under the analyst while they are
 * reading it.
 */
export function layoutOptionsFor(
  name: LayoutName,
  nodeIds: readonly string[],
): cytoscape.LayoutOptions {
  const shared = {
    animate: false,
    // Reduced motion (§67) is honoured by never animating; a layout that flies
    // across the canvas is the single most motion-heavy thing in the app.
    fit: true,
    padding: 40,
  } as cytoscape.LayoutOptions;

  switch (name) {
    case "breadthfirst":
      return {
        ...shared,
        name: "breadthfirst",
        directed: false,
        spacingFactor: 1.1,
        avoidOverlap: true,
        roots: nodeIds.length > 0 ? [nodeIds[0]] : undefined,
      } as cytoscape.LayoutOptions;
    case "circle":
      return { ...shared, name: "circle", padding: 40 } as cytoscape.LayoutOptions;
    case "grid":
      return { ...shared, name: "grid", padding: 40, avoidOverlap: true } as cytoscape.LayoutOptions;
    case "preset":
      // No run at all: the current positions stand. Used when restoring a saved
      // view, where re-solving would throw the saved positions away.
      return { name: "preset", animate: false, fit: true } as cytoscape.LayoutOptions;
    case "cose":
    default:
      return {
        ...shared,
        name: "cose",
        nodeRepulsion: 9_000,
        idealEdgeLength: 90,
        componentSpacing: 80,
        nodeOverlap: 12,
        // The store's own node ids become a stable initial placement so the
        // force pass starts from the same place every time.
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        ...({ nodeDimensionsIncludeLabels: true } as any),
      } as cytoscape.LayoutOptions;
  }
}

/** Human labels for the layout menu. */
export const LAYOUT_LABELS: Readonly<Record<LayoutName, string>> = {
  cose: "Force-directed",
  breadthfirst: "Layered by hops",
  circle: "Radial",
  grid: "Grid",
  preset: "Keep current positions",
};