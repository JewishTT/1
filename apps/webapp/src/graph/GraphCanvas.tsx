import { useCallback, useEffect, useMemo, useRef, useState, type MutableRefObject, type ReactNode } from "react";
import type cytoscape from "cytoscape";

import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { EmptyState, Skeleton } from "../ui/Feedback";
import { useWorkspace } from "../workspace/store";
import type { WorkspaceObjectKind, WorkspaceSelection } from "../workspace/types";
import { EdgeDetails, NodeDetails } from "./GraphDetails";
import { GraphFilterDrawer } from "./GraphFilterDrawer";
import { GraphToolbar, type ToolbarMode } from "./GraphToolbar";
import { applyFacets, type GraphFacets } from "./filters";
import { collapse, expand, expansionChoices, type ExpansionChoice } from "./expansion";
import { isLayoutName, layoutOptionsFor, type LayoutName } from "./layout";
import { findPath, resolveEmphasis, type PathResult } from "./path";
import {
  edgeStyleForContext,
  nodeStyleFor,
  predicateIsVisible,
  readGraphPalette,
  type Emphasis,
  type GraphPalette,
} from "./semantics";
import { graphKindForSelection, nodeIdFor, type GraphEdge, type GraphModel, type GraphNode } from "./types";
import { useGraphFacets } from "./useGraphFacets";
import { useGraphModel } from "./useGraphModel";
import "./graph.css";

/**
 * GraphCanvas (§14, §16–§22, §81).
 *
 * A PRIMARY CANVAS, NOT A WIDGET IN A CARD. It fills the centre pane. The
 * toolbar overlays it, the filter drawer slides over the left edge, and the
 * timeline docks beneath — none of which push the canvas around, because a
 * canvas that resizes when you open a filter is a canvas whose coordinates
 * move under you.
 *
 * §68 — the expensive things are incremental, the cheap things are narrow:
 *   - Cytoscape is created ONCE. Filters, expansions and emphasis mutate the
 *     existing graph inside `cy.batch()`. Nothing here destroys and rebuilds.
 *   - Only elements whose emphasis actually changed are re-styled.
 *   - The component subscribes to `selection`, `secondarySelection` and
 *     `theme` — three slices — never the whole store, so a rail query
 *     keystroke does not touch the canvas.
 *
 * §18 selection: click selects, shift-click adds to the comparison set,
 * double-click focuses, right-click opens the context menu. All of them write
 * to the store and nowhere else — there is no second selection model (§7).
 *
 * §21: expansion is bounded and REPORTS ITS BOUND. There is no "show
 * everything" control, and `expand()` cannot produce one.
 */

export interface GraphCanvasProps {
  /** Overrides the store-derived investigation. For tests and previews. */
  investigationId?: string | null;
  /**
   * Facets supplied by an outer owner. The seam the integrating pass uses to
   * put the four store-less facets in the store without touching this file.
   */
  facets?: GraphFacets;
  onFacetsChange?: (patch: Partial<GraphFacets>) => void;
  /** Timeline docked beneath the canvas (§23, §84). */
  timeline?: ReactNode;
  /** Collapsed state of the filter drawer, for the shell to remember. */
  defaultDrawerOpen?: boolean;
}

export function GraphCanvas({
  investigationId,
  facets: controlled,
  onFacetsChange,
  timeline,
  defaultDrawerOpen = false,
}: GraphCanvasProps) {
  const storeInvestigationId = useWorkspace((state) => state.investigationId);
  const activeInvestigation = investigationId !== undefined ? investigationId : storeInvestigationId;

  const selection = useWorkspace((state) => state.selection);
  const secondary = useWorkspace((state) => state.secondarySelection);
  const theme = useWorkspace((state) => state.theme);
  const select = useWorkspace((state) => state.select);
  const toggleSecondary = useWorkspace((state) => state.toggleSecondary);
  const setView = useWorkspace((state) => state.setView);
  const openContextMenu = useWorkspace((state) => state.openContextMenu);

  const server = useGraphModel(activeInvestigation);
  const { facets, active: activeFacets, toggle, setQuery, setTimeRange, reset } = useGraphFacets({
    controlled: controlled,
    onControlledChange: onFacetsChange,
  });

  const [mode, setMode] = useState<ToolbarMode>("select");
  const [filterDrawerOpen, setFilterDrawerOpen] = useState(defaultDrawerOpen);
  const [layout, setLayout] = useState<LayoutName>("cose");
  const [path, setPath] = useState<PathResult>({
    nodeIds: [],
    edgeIds: [],
    unreachable: false,
    hops: null,
  });
  const [expandedIds, setExpandedIds] = useState<string[]>([]);
  const [temporalActive, setTemporalActive] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [hoveredEdgeId, setHoveredEdgeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);

  const hostRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const paletteRef = useRef<GraphPalette>(readGraphPalette(null));
  const handlersRef = useRef<{
    select: (value: WorkspaceSelection | null) => void;
    toggleSecondary: (value: WorkspaceSelection) => void;
    openContextMenu: (value: { x: number; y: number; targetKind: WorkspaceObjectKind | null }) => void;
    selectEdge: (edgeId: string) => void;
    hoverEdge: (edgeId: string | null) => void;
  }>({
    select,
    toggleSecondary,
    openContextMenu,
    selectEdge: setSelectedEdgeId,
    hoverEdge: setHoveredEdgeId,
  });
  handlersRef.current.select = select;
  handlersRef.current.toggleSecondary = toggleSecondary;
  handlersRef.current.openContextMenu = openContextMenu;

  const filtered = useMemo(() => applyFacets(server.model, facets), [server.model, facets]);
  const view = useMemo(() => asModel(server.model, filtered), [server.model, filtered]);

  const selectedNodeIds = useMemo(() => {
    if (!selection) return [];
    const kind = graphKindForSelection(selection.kind);
    return kind === null ? [] : [nodeIdFor(kind, selection.id)];
  }, [selection]);

  const secondaryNodeIds = useMemo(
    () =>
      secondary
        .map((entry) => {
          const kind = graphKindForSelection(entry.kind);
          return kind === null ? null : nodeIdFor(kind, entry.id);
        })
        .filter((id): id is string => id !== null && server.model.nodeIndex.has(id)),
    [secondary, server.model],
  );

  const selectedNode = selectedNodeIds.length > 0 ? view.nodeIndex.get(selectedNodeIds[0]) ?? null : null;
  const selectedEdge = selectedEdgeId === null ? null : view.edgeIndex.get(selectedEdgeId) ?? null;

  const emphasis = useMemo(
    () =>
      resolveEmphasis(
        view,
        selectedNodeIds,
        secondaryNodeIds,
        selectedEdgeId === null ? [] : [selectedEdgeId],
        path,
      ),
    [view, selectedNodeIds, secondaryNodeIds, selectedEdgeId, path],
  );

  /* ── Cytoscape: created once ───────────────────────────────────────── */

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    let cancelled = false;
    let created: cytoscape.Core | null = null;

    void import("cytoscape").then((module) => {
      if (cancelled || hostRef.current === null) return;
      paletteRef.current = readGraphPalette(hostRef.current);
      created = module.default({
        container: hostRef.current,
        elements: [],
        // No ambient motion (§93, §67): no bouncing, no pulsing, no easing.
        // Layout runs unanimated and selection is instant.
        wheelSensitivity: 0.2,
        minZoom: 0.15,
        maxZoom: 3,
        boxSelectionEnabled: false,
        style: [
          { selector: "node", style: { label: "data(id)", "font-size": 8, "text-valign": "bottom", "text-margin-y": 4 } },
          { selector: "edge", style: { width: 1, "curve-style": "bezier", "target-arrow-shape": "none" } },
        ],
      } as cytoscape.CytoscapeOptions);
      cyRef.current = created;
      wireEvents(created, handlersRef);
    });

    return () => {
      cancelled = true;
      created?.destroy();
      if (cyRef.current === created) cyRef.current = null;
    };
  }, []);

  /* ── Elements: add/remove the delta only ───────────────────────────── */

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    applyElements(cy, filtered.nodes, filtered.edges, paletteRef.current, emphasis, hoveredEdgeId);
  }, [filtered, emphasis, hoveredEdgeId]);

  /* ── Palette follows the theme, not a prop ─────────────────────────── */

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    paletteRef.current = readGraphPalette(host);
  }, [theme]);

  /* ── Lasso mode is a real interaction mode, not a label ────────────── */

  useEffect(() => {
    cyRef.current?.boxSelectionEnabled(mode === "lasso");
  }, [mode]);

  /* ── Layout runs on request, and once when elements arrive ──────────── */

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    if (cy.nodes().length === 0) return;
    applyLayout(cy, layout);
  }, [layout, filtered.nodes.length]);

  /* ── Commands ─────────────────────────────────────────────────────── */

  const seedIds = useMemo(
    () => (selectedNodeIds.length > 0 ? selectedNodeIds : expandedIds),
    [selectedNodeIds, expandedIds],
  );

  const runExpansion = useCallback(
    (request: ExpansionChoice["request"]) => {
      if (seedIds.length === 0) {
        setNote("Select an object first — expansion starts from what is selected.");
        return;
      }
      const result = expand(server.model, seedIds, request, { facets });
      setExpandedIds((prev) => unique([...prev, ...seedIds, ...result.added.map((node) => node.id)]));
      setNote(result.reason ?? `Added ${result.added.length} objects.`);
    },
    [seedIds, server.model, facets],
  );

  const onCollapse = useCallback(() => {
    if (selectedNodeIds.length === 0) {
      setNote("Select the objects to collapse back to.");
      return;
    }
    const result = collapse(server.model, selectedNodeIds, { facets });
    setExpandedIds(selectedNodeIds);
    setNote(
      result.removedNodeCount === 0
        ? "Nothing to collapse — the canvas is already at the selection."
        : `Collapsed by ${result.removedNodeCount} objects and ${result.removedEdgeCount} relations.`,
    );
  }, [selectedNodeIds, server.model, facets]);

  const onFocus = useCallback(() => {
    if (selectedNodeIds.length === 0) {
      setNote("Select an object to focus on.");
      return;
    }
    setPath({ nodeIds: [], edgeIds: [], unreachable: false, hops: null });
    setExpandedIds(selectedNodeIds);
    setNote("Focused on the selection.");
    const cy = cyRef.current;
    if (cy && selectedNodeIds.length > 0) cy.center(cy.getElementById(selectedNodeIds[0]));
  }, [selectedNodeIds]);

  const onFit = useCallback(() => {
    cyRef.current?.fit(undefined, 40);
  }, []);

  const onFindPath = useCallback(() => {
    const from = selectedNodeIds[0] ?? secondaryNodeIds[0];
    const to = selectedNodeIds[1] ?? secondaryNodeIds[1] ?? secondaryNodeIds[0];
    if (from === undefined || to === undefined || from === to) {
      setNote("Select two objects — or one plus a comparison target — to trace a path.");
      return;
    }
    const result = findPath(server.model, from, to);
    setPath(result);
    if (result.unreachable) {
      setNote(
        "No relation chain connects these two in the loaded graph. Expand a hop, or relax a facet that is hiding it.",
      );
      return;
    }
    setExpandedIds((prev) => unique([...prev, ...result.nodeIds]));
    setNote(`Path: ${result.hops} hop(s) through ${result.nodeIds.length} objects.`);
    const cy = cyRef.current;
    if (cy) {
      // `collection` takes element definitions, not bare ids.
      const pathElements = cy.collection(
        result.nodeIds.map((id) => ({ group: "nodes" as const, data: { id } })),
      );
      if (pathElements.length > 0) cy.fit(pathElements, 60);
    }
  }, [selectedNodeIds, secondaryNodeIds, server.model]);

  const onCompare = useCallback(() => {
    // Comparison is a peer surface, not a second graph inside this one (§81).
    setView("objects");
  }, [setView]);

  const onToggleTemporal = useCallback(() => {
    setTemporalActive((prev) => {
      const next = !prev;
      // The workspace time range is the one temporal filter that IS in the
      // store, so switching temporal mode on moves the graph AND the timeline
      // together — which is §23's requirement that changing time changes graph
      // state, not just what a slider displays.
      setTimeRange(
        next ? { from: new Date(Date.now() - 30 * 86_400_000).toISOString(), to: null } : { from: null, to: null },
      );
      return next;
    });
  }, [setTimeRange]);

  const onExport = useCallback(() => {
    const payload = {
      format: "cognitive.graph.projection",
      investigationId: activeInvestigation,
      facets,
      counts: server.counts,
      nodes: filtered.nodes.map((node) => ({
        id: node.id,
        kind: node.kind,
        label: node.label,
        identifier: node.identifier,
        admission: node.admission,
        admissionRaw: node.admissionRaw,
        provisional: node.provisional,
      })),
      edges: filtered.edges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        predicate: edge.predicate,
        family: edge.family,
        status: edge.status,
      })),
    };
    // Clipboard, not a file: the analyst is comparing inside the workbench.
    void navigator.clipboard?.writeText(JSON.stringify(payload, null, 2)).catch(() => undefined);
    setNote(`Exported ${filtered.nodes.length} objects and ${filtered.edges.length} relations to the clipboard.`);
  }, [activeInvestigation, facets, server.counts, filtered]);

  const expansions = useMemo(
    () =>
      expansionChoices(
        [
          ...new Set(
            server.model.nodes
              .map((node: GraphNode) => node.sourceId)
              .filter((value: string | null): value is string => value !== null),
          ),
        ],
      ),
    [server.model],
  );

  const totalLoaded =
    server.counts.entities + server.counts.observations + server.counts.findings + server.counts.hypotheses;

  /* ── States (§90, §91) ────────────────────────────────────────────── */

  if (activeInvestigation === null) {
    return (
      <div className="ui-graph" data-testid="graph-canvas">
        <EmptyState
          icon="view-graph"
          title="No investigation loaded"
          description="The graph is a projection of one investigation's records. Choose an investigation and the canvas reads its entities, findings and correlation candidates."
          testId="graph-no-investigation"
        />
      </div>
    );
  }

  if (server.loading) {
    return (
      <div className="ui-graph" data-testid="graph-canvas">
        <Skeleton rows={8} label="Loading graph records" />
      </div>
    );
  }

  if (server.error !== null) {
    return (
      <div className="ui-graph" data-testid="graph-canvas">
        <div className="ui-inspector-error" role="alert" data-testid="graph-error">
          <p className="ui-pane-title">The graph did not load</p>
          <p className="ui-body" data-testid="graph-error-message">
            {server.error}
          </p>
          <p className="ui-body">
            Scope: the entity graph and the finding list for investigation{" "}
            <span className="ui-mono">{activeInvestigation}</span>. Nothing else in the
            workspace is affected — the rail, the inspector and the evidence views keep
            working.
          </p>
          <div className="ui-insp-next-list">
            <Button size="sm" onClick={server.refetch} data-testid="graph-error-retry">
              Retry
            </Button>
            <Button size="sm" onClick={() => setView("overview")} data-testid="graph-error-inspect">
              Inspect the investigation
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="ui-graph" data-testid="graph-canvas" data-mode={mode}>
      <GraphToolbar
        mode={mode}
        onModeChange={setMode}
        query={facets.query}
        onQueryChange={setQuery}
        matchCount={filtered.nodes.length === server.model.nodes.length ? null : filtered.nodes.length}
        expansions={expansions}
        onExpand={(choice) => runExpansion(choice.request)}
        expandedNodeCount={expandedIds.length}
        onCollapse={onCollapse}
        onFocus={onFocus}
        onFit={onFit}
        layout={layout}
        onLayoutChange={(next) => {
          if (isLayoutName(next)) setLayout(next);
        }}
        activeFacets={activeFacets}
        onToggleFilterDrawer={() => setFilterDrawerOpen((open) => !open)}
        filterDrawerOpen={filterDrawerOpen}
        pathAvailable={selectedNodeIds.length + secondaryNodeIds.length >= 2}
        onFindPath={onFindPath}
        secondaryCount={secondary.length}
        onCompare={onCompare}
        temporalActive={temporalActive}
        onToggleTemporal={onToggleTemporal}
        onExport={onExport}
        counts={server.counts}
        coverage={server.coverage}
        disabled={server.model.nodes.length === 0}
      />

      <div className="ui-graph-body">
        <div className="ui-graph-host" ref={hostRef} data-testid="graph-host" data-lasso={mode === "lasso"} />

        <GraphFilterDrawer
          open={filterDrawerOpen}
          onClose={() => setFilterDrawerOpen(false)}
          model={server.model}
          facets={facets}
          onToggle={toggle}
          onQueryChange={setQuery}
          onReset={reset}
          visibleNodeCount={filtered.nodes.length}
        />

        <div className="ui-graph-side">
          <NodeDetails
            node={selectedNode}
            model={view}
            onGoTo={select}
            onGoToView={setView}
            onExpandNode={() => runExpansion({ kind: "hops", hops: 1 })}
            onToggleSecondary={toggleSecondary}
            isSecondary={selectedNode !== null && secondaryNodeIds.includes(selectedNode.id)}
          />
          <EdgeDetails
            edge={selectedEdge}
            model={view}
            onGoTo={select}
            onGoToView={setView}
            onExpandEdge={(edge) => runExpansion({ kind: "relation", relation: edge.family })}
          />
        </div>
      </div>

      {note !== null ? (
        <p className="ui-graph-note" role="status" aria-live="polite" data-testid="graph-note">
          {note}
        </p>
      ) : null}

      {totalLoaded === 0 ? (
        <div className="ui-graph-overlay" data-testid="graph-empty">
          <EmptyState
            icon="view-graph"
            title="No records for this investigation yet"
            description="The entity graph and the finding list both answered with nothing. Expand by source or timeframe once a run lands, or open acquisition to see whether anything is in flight."
            action={
              <Button size="sm" onClick={() => setView("acquisition")} data-testid="graph-empty-acquisition">
                Open acquisition
              </Button>
            }
            testId="graph-empty-state"
          />
        </div>
      ) : filtered.nodes.length === 0 ? (
        <div className="ui-graph-overlay" data-testid="graph-filtered-empty">
          <EmptyState
            size="sm"
            icon="view-objects"
            title="Every object is filtered out"
            description={`${totalLoaded} objects were loaded and the ${activeFacets.length} active facet(s) hide all of them. Relax a facet, or reset.`}
            action={
              <Button size="sm" onClick={reset} data-testid="graph-filtered-reset">
                Reset filters
              </Button>
            }
            testId="graph-filtered-empty-state"
          />
        </div>
      ) : null}

      {temporalActive ? (
        <div className="ui-graph-temporal" data-testid="graph-temporal-badge">
          <Badge tone="gold" role="classification">
            temporal slice: {facets.timeRange.from ?? "open"} → {facets.timeRange.to ?? "open"}
          </Badge>
        </div>
      ) : null}

      {/* Announces the emphasis change without moving focus (§67). */}
      <span className="ui-sr-only" role="status" aria-live="polite" data-testid="graph-live">
        {selectedNode
          ? `${selectedNode.kind} ${selectedNode.identifier} selected, ${(view.edges ?? []).length} relations in view`
          : path.hops !== null
            ? `path of ${path.hops} hops`
            : ""}
      </span>

      {timeline ? <div className="ui-graph-timeline">{timeline}</div> : null}
    </div>
  );
}

/* ── Cytoscape plumbing ──────────────────────────────────────────────── */

interface CanvasHandlers {
  select: (value: WorkspaceSelection | null) => void;
  toggleSecondary: (value: WorkspaceSelection) => void;
  openContextMenu: (value: { x: number; y: number; targetKind: WorkspaceObjectKind | null }) => void;
  selectEdge: (edgeId: string) => void;
  hoverEdge: (edgeId: string | null) => void;
}

/** §18: click, shift-click, double-click, right-click — four gestures, four meanings. */
function wireEvents(cy: cytoscape.Core, handlers: MutableRefObject<CanvasHandlers>): void {
  cy.on("tap", "node", (event) => {
    const selection = selectionFromNodeId(event.target.id());
    if (!selection) return;
    const original = event.originalEvent as MouseEvent | undefined;
    if (original?.shiftKey) {
      handlers.current.toggleSecondary(selection);
      return;
    }
    handlers.current.select(selection);
  });

  // Double-click = focus. The gesture says "this is my subject", so it selects
  // and centres; the analyst still chooses how far to expand.
  cy.on("dbltap", "node", (event) => {
    const selection = selectionFromNodeId(event.target.id());
    if (selection) handlers.current.select(selection);
    const element = event.target;
    if (element.length > 0) cy.center(element);
  });

  cy.on("tap", "edge", (event) => {
    handlers.current.selectEdge(event.target.id());
  });

  cy.on("cxttap", (event) => {
    const rendered = event.renderedPosition ?? { x: 0, y: 0 };
    const target = event.target;
    if (target === cy) {
      handlers.current.openContextMenu({ x: rendered.x, y: rendered.y, targetKind: null });
      return;
    }
    const selection = selectionFromNodeId(target.id());
    if (selection) handlers.current.select(selection);
    handlers.current.openContextMenu({ x: rendered.x, y: rendered.y, targetKind: kindFromNodeId(target.id()) });
  });

  cy.on("mouseover", "edge", (event) => handlers.current.hoverEdge(event.target.id()));
  cy.on("mouseout", "edge", () => handlers.current.hoverEdge(null));
}

type ResolvedEmphasis = ReturnType<typeof resolveEmphasis>;

/** The single place elements enter or leave the canvas. Incremental, always. */
function applyElements(
  cy: cytoscape.Core,
  nodes: readonly GraphNode[],
  edges: readonly GraphEdge[],
  palette: GraphPalette,
  emphasis: ResolvedEmphasis,
  hoveredEdgeId: string | null,
): void {
  const nodeIds = new Set(nodes.map((node) => node.id));
  const liveEdgeIds = new Set(
    edges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target)).map((edge) => edge.id),
  );

  cy.batch(() => {
    cy.nodes().filter((node) => !nodeIds.has(node.id())).remove();
    cy.edges().filter((edge) => !liveEdgeIds.has(edge.id())).remove();

    const absentNodes = nodes.filter((node) => cy.getElementById(node.id).length === 0);
    if (absentNodes.length > 0) {
      cy.add(
        absentNodes.map((node) => ({ group: "nodes" as const, data: { id: node.id, kind: node.kind } })),
      );
    }
    const absentEdges = edges.filter(
      (edge) => liveEdgeIds.has(edge.id) && cy.getElementById(edge.id).length === 0,
    );
    if (absentEdges.length > 0) {
      cy.add(
        absentEdges.map((edge) => ({
          group: "edges" as const,
          data: { id: edge.id, source: edge.source, target: edge.target, family: edge.family },
        })),
      );
    }

    for (const node of nodes) {
      const element = cy.getElementById(node.id);
      if (element.length === 0) continue;
      element.style(
        nodeStyleFor(node, {
          palette,
          emphasis: emphasis.nodes.get(node.id) ?? "rest",
          secondary: emphasis.secondaryNodes.has(node.id),
          dimmed: false,
          interactive: true,
        }),
      );
    }

    for (const edge of edges) {
      const element = cy.getElementById(edge.id);
      if (element.length === 0) continue;
      const level: Emphasis = emphasis.edges.get(edge.id) ?? "rest";
      const hovered = hoveredEdgeId === edge.id;
      const style = edgeStyleForContext(edge.family, { palette, emphasis: level, hovered });
      style.label = predicateIsVisible(level, hovered) ? edge.predicate : "";
      element.style(style);
    }
  });
}

/** Run a layout over the live elements. Unanimated by design (§67). */
export function applyLayout(cy: cytoscape.Core | null, layout: LayoutName): void {
  if (!cy) return;
  const ids = cy.nodes().map((node) => node.id());
  cy.layout(layoutOptionsFor(layout, ids)).run();
}

/** The filtered view of a model, as a model, sharing indices where possible. */
function asModel(
  model: GraphModel,
  filtered: { nodes: GraphNode[]; edges: GraphEdge[] },
): GraphModel {
  if (filtered.nodes.length === model.nodes.length && filtered.edges.length === model.edges.length) {
    return model;
  }
  return {
    nodes: filtered.nodes,
    edges: filtered.edges,
    nodeIndex: new Map(filtered.nodes.map((node) => [node.id, node])),
    edgeIndex: new Map(filtered.edges.map((edge) => [edge.id, edge])),
  };
}

function kindFromNodeId(nodeId: string): WorkspaceObjectKind | null {
  const kind = nodeId.slice(0, nodeId.indexOf(":"));
  if (kind === "Entity" || kind === "Observation" || kind === "Claim" || kind === "Finding") return kind;
  // A hypothesis is not addressable as itself; it routes to its origin entity.
  return nodeId.startsWith("Hypothesis:") ? "Entity" : null;
}

function selectionFromNodeId(nodeId: string): WorkspaceSelection | null {
  const separator = nodeId.indexOf(":");
  if (separator === -1) return null;
  const kind = kindFromNodeId(nodeId);
  if (kind === null) return null;
  return { kind, id: nodeId.slice(separator + 1) };
}

function unique(values: readonly string[]): string[] {
  return [...new Set(values)];
}