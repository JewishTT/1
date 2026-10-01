import type { SVGProps } from "react";

/**
 * UI 2.0 icon set (§59).
 *
 * One inline SVG set, defined in-repo. No icon dependency (§64: Cytoscape /
 * ECharts / Query / Zustand only). No text glyphs (`◈ ◉ ♦ ⚡ ☰ ⧉`) as
 * navigation iconography — §59 forbids them and the legacy Layout still uses
 * them; the new shell does not.
 *
 * Construction rules, so the set reads as one family:
 *   - 16×16 viewBox, no intrinsic size (the consumer sets width/height).
 *   - 1.5px stroke, round caps and joins, `currentColor`, `fill="none"`.
 *     Weight is carried by the stroke, never by a filled blob.
 *   - Geometry sits inside a 14×14 live area (1px inset) so optical weight
 *     matches adjacent text at every density.
 *
 * Every glyph here has a real caller in the shell, workspace, inspector or
 * primitives. None is speculative.
 */

export type IconName =
  /* Workspace views (§4) */
  | "view-overview"
  | "view-graph"
  | "view-objects"
  | "view-evidence"
  | "view-timeline"
  | "view-acquisition"
  | "view-findings"
  | "view-analysis"
  /* Shell (§5) */
  | "search"
  | "command"
  | "panel-left"
  | "panel-right"
  | "panel-bottom"
  | "sun"
  | "moon"
  | "density"
  | "chevron-left"
  | "chevron-right"
  | "chevron-down"
  /* Inspector + primitives */
  | "close"
  | "copy"
  | "open-external"
  | "alert"
  | "clock";

/** Path data, 16×16 grid. `d` only — every glyph is stroke-rendered. */
const PATHS: Record<IconName, string> = {
  /* Four panes: the overview is the literal shape of the workspace. */
  "view-overview": "M2.5 2.5h4.5v4.5H2.5zM9 2.5h4.5v4.5H9zM2.5 9h4.5v4.5H2.5zM9 9h4.5v4.5H9z",
  /* Three nodes and two edges — a graph without the "spiky ball" cliché. */
  "view-graph": "M4 4.5 2.5 12M4 4.5 11 7M11 7l2.5 4.5M11 7 4 4.5",
  /* Rows: an object table. */
  "view-objects": "M2.5 3.5h11M2.5 6.5h11M2.5 9.5h11M2.5 12.5h11M6 3.5v9",
  /* Document with a folded corner: evidence. */
  "view-evidence": "M4 2.5h5l3 3v8H4zM9 2.5V6h3",
  /* Clock with hands: temporal scope. */
  "view-timeline": "M8 2.5a5.5 5.5 0 1 1 0 11 5.5 5.5 0 0 1 0-11M8 5.5V8l2 1.5",
  /* Tray with a descending arrow: acquisition. */
  "view-acquisition": "M2.5 10.5v2h11v-2M8 2.5v5M5.5 5.5 8 8l2.5-2.5",
  /* Target with a centre hit: a finding is a located observation. */
  "view-findings": "M8 2.5a5.5 5.5 0 1 1 0 11 5.5 5.5 0 0 1 0-11M8 6a2 2 0 1 1 0 4 2 2 0 0 1 0-4",
  /* Bars on an axis: derived analysis. */
  "view-analysis": "M2.5 13.5h11M4.5 13.5v-4M7.5 13.5V5M10.5 13.5v-6",

  "search": "M7 2.5a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9M10.5 10.5 13.5 13.5",
  "command": "M4.5 3.5h7a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1h-7a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1M5.5 9.5 8 7l2.5 2.5",
  "panel-left": "M2.5 3.5h11v9h-11zM6.5 3.5v9",
  "panel-right": "M2.5 3.5h11v9h-11zM9.5 3.5v9",
  "panel-bottom": "M2.5 3.5h11v9h-11zM2.5 9.5h11",
  "sun": "M8 5a3 3 0 1 1 0 6 3 3 0 0 1 0-6M8 1.5v1.5M8 13v1.5M1.5 8h1.5M13 8h1.5M3.4 3.4l1 1M11.6 11.6l1 1M12.6 3.4l-1 1M4.4 11.6l-1 1",
  "moon": "M13 9.5A5.5 5.5 0 0 1 6.5 3a5.5 5.5 0 1 0 6.5 6.5Z",
  "density": "M2.5 4h11M2.5 8h11M2.5 12h11",
  "chevron-left": "M10 3.5 5.5 8l4.5 4.5",
  "chevron-right": "M6 3.5 10.5 8 6 12.5",
  "chevron-down": "M3.5 6 8 10.5 12.5 6",

  "close": "M4 4l8 8M12 4l-8 8",
  "copy": "M5.5 5.5h7v7h-7zM3.5 10.5v-7h7",
  "open-external": "M9.5 2.5H13V6M13 2.5 7.5 8M11 9v4.5H2.5V5H7",
  "alert": "M8 2.5 14 13H2zM8 6.5v3M8 11.2v.3",
  "clock": "M8 2.5a5.5 5.5 0 1 1 0 11 5.5 5.5 0 0 1 0-11M8 5.5V8l2 1.5",
};

export interface IconProps extends Omit<SVGProps<SVGSVGElement>, "name"> {
  name: IconName;
  /** Pixel size. Default 16 — the family is drawn on a 16px grid. */
  size?: number;
  /**
   * Required unless the icon is inside an element that already carries the
   * accessible name (an IconButton, a labelled tab). Decorative icons get
   * aria-hidden; meaningful ones get the label. (§67)
   */
  label?: string;
}

export function Icon({ name, size = 16, label, ...rest }: IconProps) {
  const labelled = typeof label === "string" && label.length > 0;
  return (
    <svg
      className="ui-icon"
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={labelled ? "img" : undefined}
      aria-hidden={labelled ? undefined : true}
      aria-label={labelled ? label : undefined}
      focusable="false"
      {...rest}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}

/** Enumerated for tests and for the palette's icon coverage assertion. */
export const ICON_NAMES = Object.keys(PATHS) as IconName[];