import { useMemo } from "react";

import { Badge } from "../ui/Badge";
import { Button, IconButton } from "../ui/Button";
import { Icon, type IconName } from "../ui/Icon";
import { Input, Select } from "../ui/Input";
import { Popover, Tooltip } from "../ui/Overlay";
import type { GraphFacetId } from "./filters";
import { EDGE_LEGEND, NODE_LEGEND } from "./semantics";
import type { GraphCounts, GraphCoverage } from "./useGraphModel";
import type { ExpansionChoice } from "./expansion";
import type { LayoutName } from "./layout";

/**
 * GraphToolbar (§15).
 *
 * FOURTEEN ACTIONS, NO DASHBOARD. Every control here does one of the seven
 * things §71 permits — navigate, narrow, change layout, focus, compare,
 * export, or report state. There is no branding strip, no summary tile, no
 * decorative divider. Where a group has many members (layout, export) it is a
 * menu rather than a row of icons, because twelve icons in a strip is a
 * toolbar nobody reads.
 *
 * Actions that cannot apply in the current context are `disabled` with the
 * reason in their tooltip — never hidden, and never rendered as a button that
 * quietly does nothing (§69).
 */

export type ToolbarMode = "select" | "lasso";

export interface GraphToolbarProps {
  mode: ToolbarMode;
  onModeChange: (mode: ToolbarMode) => void;
  query: string;
  onQueryChange: (query: string) => void;
  /** Nodes the search matched. Shown as a count, never as a fake result list. */
  matchCount: number | null;
  expansions: readonly ExpansionChoice[];
  onExpand: (choice: ExpansionChoice) => void;
  /** Collapse to the seed set. Disabled when nothing has been expanded. */
  expandedNodeCount: number;
  onCollapse: () => void;
  onFocus: () => void;
  onFit: () => void;
  layout: LayoutName;
  onLayoutChange: (layout: LayoutName) => void;
  activeFacets: readonly GraphFacetId[];
  onToggleFilterDrawer: () => void;
  filterDrawerOpen: boolean;
  /** Two selected objects — the precondition for a path. */
  pathAvailable: boolean;
  onFindPath: () => void;
  /** Comparison target count. */
  secondaryCount: number;
  onCompare: () => void;
  /** Temporal mode: whether the canvas is sliced by the workspace time range. */
  temporalActive: boolean;
  onToggleTemporal: () => void;
  onExport: () => void;
  counts: GraphCounts;
  coverage: GraphCoverage;
  disabled: boolean;
}

const LAYOUTS: ReadonlyArray<{ value: LayoutName; label: string }> = [
  { value: "cose", label: "Force-directed" },
  { value: "breadthfirst", label: "Layered by hops" },
  { value: "circle", label: "Radial" },
  { value: "grid", label: "Grid" },
  { value: "preset", label: "Keep current positions" },
];

export function GraphToolbar({
  mode,
  onModeChange,
  query,
  onQueryChange,
  matchCount,
  expansions,
  onExpand,
  expandedNodeCount,
  onCollapse,
  onFocus,
  onFit,
  layout,
  onLayoutChange,
  activeFacets,
  onToggleFilterDrawer,
  filterDrawerOpen,
  pathAvailable,
  onFindPath,
  secondaryCount,
  onCompare,
  temporalActive,
  onToggleTemporal,
  onExport,
  counts,
  coverage,
  disabled,
}: GraphToolbarProps) {
  const hopExpansions = useMemo(() => expansions.filter((choice) => choice.request.kind === "hops"), [expansions]);
  const constraintExpansions = useMemo(
    () => expansions.filter((choice) => choice.request.kind !== "hops"),
    [expansions],
  );

  return (
    <div className="ui-graph-toolbar" role="toolbar" aria-label="Graph controls" data-testid="graph-toolbar">
      <div className="ui-graph-toolbar-group">
        <Input
          label="Search objects"
          mono
          value={query}
          placeholder="id, label or kind"
          adornment={<Icon name="search" size={12} />}
          onChange={(event) => onQueryChange(event.target.value)}
          hint={matchCount === null ? "narrow the canvas" : `${matchCount} objects match`}
        />
      </div>

      <div className="ui-graph-toolbar-group" role="group" aria-label="Pointer mode">
        <Button
          size="sm"
          variant={mode === "select" ? "primary" : "default"}
          aria-pressed={mode === "select"}
          disabled={disabled}
          onClick={() => onModeChange("select")}
          data-testid="graph-mode-select"
        >
          Select
        </Button>
        <Button
          size="sm"
          variant={mode === "lasso" ? "primary" : "default"}
          aria-pressed={mode === "lasso"}
          disabled={disabled}
          onClick={() => onModeChange("lasso")}
          data-testid="graph-mode-lasso"
        >
          Lasso
        </Button>
      </div>

      <div className="ui-graph-toolbar-sep" role="presentation" />

      <div className="ui-graph-toolbar-group" role="group" aria-label="Expand">
        {hopExpansions.map((choice) => (
          <Tooltip key={choice.id} content={choice.hint}>
            <Button size="sm" disabled={disabled} onClick={() => onExpand(choice)} data-testid={choice.id}>
              {choice.label}
            </Button>
          </Tooltip>
        ))}
        <Popover
          label="Expand by constraint"
          placement="bottom"
          align="start"
          testId="expand-constraint-menu"
          trigger={
            <Button size="sm" disabled={disabled} iconAfter="chevron-down" data-testid="expand-constraint">
              Specific…
            </Button>
          }
        >
          <div className="ui-menu">
            <span className="ui-pane-title">Narrow the expansion</span>
            <p className="ui-rail-hint">Each of these expands by one hop under a single constraint.</p>
            {constraintExpansions.map((choice) => (
              <Button
                key={choice.id}
                size="sm"
                disabled={disabled}
                title={choice.hint}
                onClick={() => onExpand(choice)}
                data-testid={`${choice.id}-item`}
              >
                {choice.label}
              </Button>
            ))}
          </div>
        </Popover>
        <Tooltip content={`Collapse back to the ${counts.entities} seeded objects`}>
          <Button
            size="sm"
            disabled={disabled || expandedNodeCount === 0}
            onClick={onCollapse}
            data-testid="graph-collapse"
          >
            Collapse
          </Button>
        </Tooltip>
      </div>

      <div className="ui-graph-toolbar-sep" role="presentation" />

      <div className="ui-graph-toolbar-group" role="group" aria-label="Navigate">
        <Tooltip content="Fit the canvas to the visible objects">
          <IconButton icon="view-graph" label="Fit canvas" size="sm" disabled={disabled} onClick={onFit} data-testid="graph-fit" />
        </Tooltip>
        <Select
          label="Layout"
          value={layout}
          options={LAYOUTS}
          onValueChange={onLayoutChange}
          disabled={disabled}
        />
      </div>

      <div className="ui-graph-toolbar-sep" role="presentation" />

      <div className="ui-graph-toolbar-group" role="group" aria-label="Narrow">
        <Button
          size="sm"
          variant={filterDrawerOpen ? "primary" : "default"}
          aria-expanded={filterDrawerOpen}
          disabled={disabled}
          onClick={onToggleFilterDrawer}
          data-testid="graph-filter-toggle"
        >
          Filters{activeFacets.length > 0 ? ` (${activeFacets.length})` : ""}
        </Button>
        <Button
          size="sm"
          variant={temporalActive ? "primary" : "default"}
          aria-pressed={temporalActive}
          disabled={disabled}
          icon="clock"
          onClick={onToggleTemporal}
          data-testid="graph-temporal-toggle"
        >
          Temporal
        </Button>
      </div>

      <div className="ui-graph-toolbar-sep" role="presentation" />

      <div className="ui-graph-toolbar-group" role="group" aria-label="Focus and compare">
        <Button
          size="sm"
          disabled={disabled}
          onClick={onFocus}
          title="Centre the canvas on the selection and collapse everything else"
          data-testid="graph-focus"
        >
          Focus
        </Button>
        <Button
          size="sm"
          disabled={disabled || !pathAvailable}
          onClick={onFindPath}
          title={
            pathAvailable
              ? "Light the shortest relation chain between the two selected objects"
              : "Select two objects to trace a path between them"
          }
          data-testid="graph-path"
        >
          Path
        </Button>
        <Button
          size="sm"
          disabled={disabled || secondaryCount === 0}
          onClick={onCompare}
          title={
            secondaryCount === 0
              ? "Add a second object to the comparison set first (shift-click)"
              : `Compare ${secondaryCount} object(s)`
          }
          data-testid="graph-compare"
        >
          Compare{secondaryCount > 0 ? ` (${secondaryCount})` : ""}
        </Button>
      </div>

      <div className="ui-graph-toolbar-grow" />

      <div className="ui-graph-toolbar-group" role="group" aria-label="State">
        <Button
          size="sm"
          variant="ghost"
          disabled={disabled}
          icon="open-external"
          onClick={onExport}
          data-testid="graph-export"
        >
          Export
        </Button>
        <LegendMenu />
      </div>

      {/* Work state, not decoration (§71): what the canvas is actually showing. */}
      <div className="ui-graph-toolbar-counts" data-testid="graph-counts">
        <Badge tone="neutral" testId="graph-count-entities">
          {counts.entities} entity
        </Badge>
        <Badge tone="neutral" testId="graph-count-observations">
          {counts.observations} obs
        </Badge>
        <Badge tone="neutral" testId="graph-count-findings">
          {counts.findings} finding
        </Badge>
        <Badge tone="gold" role="classification" testId="graph-count-hypotheses">
          {counts.hypotheses} hypothesis
        </Badge>
        <Tooltip
          content={
            coverage.missing.length === 0
              ? "Every relation the canvas draws was served by a wired endpoint."
              : `Not served by any endpoint today: ${coverage.missing.join("; ")}`
          }
        >
          <span className="ui-rail-hint" data-testid="graph-coverage">
            {coverage.missing.length} endpoints missing
          </span>
        </Tooltip>
      </div>
    </div>
  );
}

/**
 * The legend. Every row is a shape name plus a word, so the legend documents
 * the encoding instead of showing a palette the design does not have.
 */
function LegendMenu() {
  return (
    <Popover
      label="Graph legend"
      placement="bottom"
      align="end"
      testId="graph-legend"
      trigger={
        <Button size="sm" variant="ghost" iconAfter="chevron-down" data-testid="graph-legend-toggle">
          Legend
        </Button>
      }
    >
      <div className="ui-menu">
        <span className="ui-pane-title">Objects — shape, not colour</span>
        {NODE_LEGEND.map((row) => (
          <span key={row.kind} className="ui-graph-legend-row" data-testid={`legend-node-${row.kind}`}>
            <ShapeSwatch shape={row.shape} />
            <span className="ui-mono">{row.token}</span>
            <span className="ui-body">{row.label}</span>
            <span className="ui-rail-hint">{row.note}</span>
          </span>
        ))}
        <span className="ui-pane-title">Relations — dash pattern, not colour</span>
        {EDGE_LEGEND.map((row) => (
          <span key={row.family} className="ui-graph-legend-row" data-testid={`legend-edge-${row.family}`}>
            <DashSwatch lineStyle={row.lineStyle} />
            <span className="ui-body">{row.label}</span>
            <span className="ui-rail-hint">{row.note}</span>
          </span>
        ))}
        <span className="ui-rail-hint">
          Green is reserved for admitted structure. It never means a kind of object.
        </span>
      </div>
    </Popover>
  );
}

const SHAPE_PATHS: Readonly<Record<string, string>> = {
  "round-rectangle": "M3 4.5h10v7H3z",
  diamond: "M8 2.5 13.5 8 8 13.5 2.5 8z",
  hexagon: "M5 3h6l3 5-3 5H5L2 8z",
  star: "M8 2.2 9.6 6l4 .5-2.9 2.8.7 4L8 11.4 4.6 13.3l.7-4L2.4 6.5l4-.5z",
  ellipse: "M8 3.5a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9",
};

function ShapeSwatch({ shape }: { shape: string }) {
  const path = SHAPE_PATHS[shape] ?? SHAPE_PATHS.ellipse;
  return (
    <svg
      className="ui-graph-swatch"
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.2"
      aria-hidden="true"
    >
      <path d={path} />
    </svg>
  );
}

function DashSwatch({ lineStyle }: { lineStyle: string }) {
  return (
    <svg className="ui-graph-swatch" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
      <line
        x1="1"
        y1="8"
        x2="15"
        y2="8"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeDasharray={lineStyle === "dashed" ? "4 3" : lineStyle === "dotted" ? "1.5 3" : undefined}
      />
    </svg>
  );
}

/** The icon set is fixed (§59); this maps toolbar concepts onto real glyphs. */
export const TOOLBAR_ICONS: Readonly<Record<string, IconName>> = {
  search: "search",
  fit: "view-graph",
  filters: "view-objects",
  temporal: "clock",
  export: "open-external",
  close: "close",
};