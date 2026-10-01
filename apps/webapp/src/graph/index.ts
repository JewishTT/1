/**
 * `src/graph` — the graph surface (§14–§22, §81).
 *
 * §81 is the constraint that shaped the module: the graph is a PEER of objects,
 * evidence and timeline, not the centre of the system. So `model.ts` projects
 * server records onto the canvas without becoming a second domain model, and
 * nothing here makes the other three surfaces into subgraphs of this one.
 *
 * Layering, in the order the code reads:
 *   types.ts      the projection vocabulary and the routes out of it
 *   semantics.ts  the visual language — shape, glyph, dash, one accent
 *   model.ts      server records → GraphModel
 *   filters.ts    eight combinable facets and the one predicate that applies them
 *   expansion.ts  bounded +1/+2 hops and constrained variants
 *   path.ts       shortest chains and the emphasis map
 *   layout.ts     the built-in layouts §64 permits
 *   useGraph*.ts  server state (Query) and facet state (store)
 *   *Canvas/Toolbar/Drawer/Details — the surfaces themselves
 */

export type {
  AdmissionState,
  EdgeFamily,
  GraphEdge,
  GraphModel,
  GraphNode,
  GraphObjectKind,
} from "./types";
export { GRAPH_OBJECT_KINDS, graphKindForSelection, nodeIdFor, routeForNode } from "./types";

export {
  EDGE_LEGEND,
  EDGE_SEMANTICS,
  GRAPH_PALETTE_FALLBACK,
  MAX_NODE_EXTENT,
  NODE_LEGEND,
  NODE_SEMANTICS,
  edgeStyleFor,
  edgeStyleForContext,
  isDashed,
  nodeAccentFor,
  nodeStyleFor,
  predicateIsVisible,
  readGraphPalette,
} from "./semantics";
export type { Emphasis, EdgeStyleContext, GraphPalette, NodeStyleContext, NodeSemantics } from "./semantics";

export {
  buildGraphModel,
  collectFamilies,
  collectPredicates,
  collectSourceIds,
  projectAdmission,
} from "./model";
export type { ClaimRelationInput, GraphInput, WireEntity } from "./model";

export {
  EMPTY_GRAPH_FACETS,
  GRAPH_FACET_IDS,
  activeFacetIds,
  applyFacets,
  describeFacets,
  edgeMatchesFacets,
  isFacetActive,
  matchesTimeRange,
  nodeMatchesFacets,
  toggleFacetValue,
} from "./filters";
export type { EvidenceState, FilteredGraph, GraphFacetId, GraphFacets } from "./filters";

export {
  DEFAULT_EXPANSION_BUDGET,
  EXPANSION_LABELS,
  HARD_NODE_CEILING,
  MAX_HOPS,
  MIN_HOPS,
  collapse,
  expand,
  expansionChoices,
  normaliseHops,
} from "./expansion";
export type { ExpansionChoice, ExpansionOptions, ExpansionRequest, ExpansionResult } from "./expansion";

export { findPath, findPaths, neighbourIds, resolveEmphasis } from "./path";
export type { EmphasisMap, PathResult } from "./path";

export { LAYOUT_LABELS, LAYOUT_NAMES, isLayoutName, layoutOptionsFor } from "./layout";
export type { LayoutName } from "./layout";

export { GraphCanvas, applyLayout } from "./GraphCanvas";
export type { GraphCanvasProps } from "./GraphCanvas";
export { GraphToolbar } from "./GraphToolbar";
export type { GraphToolbarProps, ToolbarMode } from "./GraphToolbar";
export { GraphFilterDrawer, presentValues } from "./GraphFilterDrawer";
export type { GraphFilterDrawerProps } from "./GraphFilterDrawer";
export { EdgeDetails, NodeDetails } from "./GraphDetails";

export {
  FACETS_WITHOUT_STORE_HOME,
  FACETS_WITH_STORE_HOME,
  investigationScopeFrom,
  useGraphFacets,
} from "./useGraphFacets";
export type { GraphFacetsControls, LocalFacets } from "./useGraphFacets";

export {
  GRAPH_COVERAGE_MISSING,
  adaptCorrelations,
  adaptProjectionEdge,
  adaptProjectionNode,
  adaptProjectionNodes,
  buildInput,
  edgeIdsTouching,
  edgesTouching,
  nodeIdsOfKind,
  normaliseRelationships,
  useGraphModel,
} from "./useGraphModel";
export type { GraphCounts, GraphCoverage, GraphServerState } from "./useGraphModel";