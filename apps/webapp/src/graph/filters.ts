import type { TimeRange } from "../workspace/types";
import type {
  AdmissionState,
  EdgeFamily,
  GraphEdge,
  GraphModel,
  GraphNode,
  GraphObjectKind,
} from "./types";

export type { AdmissionState, EdgeFamily, GraphObjectKind };

/**
 * Faceted filters (§22).
 *
 * Every facet is a set of allowed values; a facet with an empty set admits
 * everything. Facets combine with AND, values within a facet combine with OR.
 * That is the whole rule, it is stated once, and it is applied by one
 * predicate — which is what makes "combinable" a property rather than a hope.
 *
 * Three facets deliberately have NO home in the workspace store and are
 * therefore local to the canvas: `relations`, `admissions` and
 * `evidenceStates`. The store carries `evidenceFilter` (query / sourceIds /
 * hideRejected), `railKinds` (object kinds), `timeRange` and `investigationId`,
 * so those four facets are wired to it and survive a view switch (§76). The
 * three that are not are reported as required integration; see the report.
 */

export type EvidenceState = "anchored" | "unanchored";

export interface GraphFacets {
  /** §22 object type. Empty = all kinds. */
  kinds: GraphObjectKind[];
  /** §22 relation. Empty = all families. */
  relations: EdgeFamily[];
  /** §22 source. Empty = all sources. */
  sourceIds: string[];
  /** §22 evidence: anchored by at least one record, or not. Empty = both. */
  evidenceStates: EvidenceState[];
  /** §22 status. Empty = all admission states. */
  admissions: AdmissionState[];
  /** §22 temporal range. The canonical one; `timeRange` in the store. */
  timeRange: TimeRange;
  /** §22 investigation scope. Empty = every investigation the server returns. */
  investigationIds: string[];
  /** Free-text narrowing over label and identifier. */
  query: string;
}

export const EMPTY_GRAPH_FACETS: GraphFacets = {
  kinds: [],
  relations: [],
  sourceIds: [],
  evidenceStates: [],
  admissions: [],
  timeRange: { from: null, to: null },
  investigationIds: [],
  query: "",
};

/**
 * The four display states, in words. The canvas, the drawer and the detail
 * panels all read these, so an admission state can never be spelled three ways
 * in three places — and "Not reported" is a first-class label, because
 * unreported is a statement about the record, not an absence of one (§99).
 */
export const ADMISSION_LABELS: Readonly<Record<AdmissionState, string>> = {
  admitted: "Admitted",
  provisional: "Provisional",
  rejected: "Rejected",
  unknown: "Not reported",
};

/** What the facet checkbox says for an evidence presence value. */
export const EVIDENCE_STATE_LABELS: Readonly<Record<EvidenceState, string>> = {
  anchored: "Anchored by a record",
  unanchored: "No record reported",
};

/** Facet ids, in the order the drawer lists them. Stable ids for test ids. */
export const GRAPH_FACET_IDS = [
  "kinds",
  "relations",
  "sourceIds",
  "evidenceStates",
  "admissions",
  "timeRange",
  "investigationIds",
  "query",
] as const;

export type GraphFacetId = (typeof GRAPH_FACET_IDS)[number];

/** Which facet is actively narrowing, for the "N filters" summary and the reset affordance. */
export function activeFacetIds(facets: GraphFacets): GraphFacetId[] {
  const active: GraphFacetId[] = [];
  if (facets.kinds.length > 0) active.push("kinds");
  if (facets.relations.length > 0) active.push("relations");
  if (facets.sourceIds.length > 0) active.push("sourceIds");
  if (facets.evidenceStates.length > 0) active.push("evidenceStates");
  if (facets.admissions.length > 0) active.push("admissions");
  if (facets.timeRange.from !== null || facets.timeRange.to !== null) active.push("timeRange");
  if (facets.investigationIds.length > 0) active.push("investigationIds");
  if (facets.query.trim() !== "") active.push("query");
  return active;
}

export function isFacetActive(facets: GraphFacets, id: GraphFacetId): boolean {
  return activeFacetIds(facets).includes(id);
}

/** Toggle one value inside one facet. Immutable; the caller writes it to the store. */
export function toggleFacetValue<T extends string>(
  current: readonly T[],
  value: T,
): T[] {
  return current.includes(value) ? current.filter((entry) => entry !== value) : [...current, value];
}

/* ── The predicate ───────────────────────────────────────────────────── */

/**
 * Does a node survive every facet?
 *
 * Time is the one that needs care. A node with NO reported instants is not
 * "outside the window" — it is *unknown*, and hiding it would be a false
 * statement about the record (§99). So a time range excludes only nodes that
 * report at least one instant and none of them falls inside.
 */
export function nodeMatchesFacets(node: GraphNode, facets: GraphFacets): boolean {
  if (facets.kinds.length > 0 && !facets.kinds.includes(node.kind)) return false;
  if (facets.admissions.length > 0 && (node.admission === null || !facets.admissions.includes(node.admission))) {
    return false;
  }
  if (facets.sourceIds.length > 0 && (node.sourceId === null || !facets.sourceIds.includes(node.sourceId))) {
    return false;
  }
  if (
    facets.evidenceStates.length > 0 &&
    !facets.evidenceStates.includes(node.evidenceCount > 0 ? "anchored" : "unanchored")
  ) {
    return false;
  }
  if (facets.investigationIds.length > 0 && node.originEntityId === null) return false;
  if (!matchesTimeRange(node.observedAt, facets.timeRange)) return false;
  if (!matchesQuery(node, facets.query)) return false;
  return true;
}

/**
 * Does an edge survive? An edge is admitted by a relation facet, its own
 * status, and its temporal scope. It never needs the kind facet: filtering
 * edges by endpoint kind would delete relations between two things the
 * analyst did not hide.
 */
export function edgeMatchesFacets(edge: GraphEdge, facets: GraphFacets): boolean {
  if (facets.relations.length > 0 && !facets.relations.includes(edge.family)) return false;
  if (!matchesTimeRange(edgeTimes(edge), facets.timeRange)) return false;
  if (facets.sourceIds.length > 0 && edge.observationIds.length === 0) return false;
  if (facets.query.trim() !== "" && !matchesText(edge.predicate, facets.query)) return false;
  return true;
}

/** Interval containment with open bounds. An empty list means "unknown", never "outside". */
export function matchesTimeRange(isoInstants: readonly string[], range: TimeRange): boolean {
  if (range.from === null && range.to === null) return true;
  if (isoInstants.length === 0) return true;
  return isoInstants.some((iso) => {
    const ms = Date.parse(iso);
    if (Number.isNaN(ms)) return true;
    const from = range.from === null ? null : Date.parse(range.from);
    const to = range.to === null ? null : Date.parse(range.to);
    if (from !== null && !Number.isNaN(from) && ms < from) return false;
    if (to !== null && !Number.isNaN(to) && ms > to) return false;
    return true;
  });
}

/** The instants an edge occupies: its own validity, else its evidence records' times. */
export function edgeTimes(edge: GraphEdge): string[] {
  const own: string[] = [];
  if (edge.validFrom !== null) own.push(edge.validFrom);
  if (edge.validTo !== null) own.push(edge.validTo);
  return own;
}

function matchesQuery(node: GraphNode, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (needle === "") return true;
  return matchesText(node.label, needle) || matchesText(node.identifier, needle) || matchesText(node.kind, needle);
}

function matchesText(haystack: string, needleLower: string): boolean {
  return haystack.toLowerCase().includes(needleLower);
}

/* ── Applying facets ─────────────────────────────────────────────────── */

export interface FilteredGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  /** How many nodes/edges the facets removed — reported, never silently applied. */
  hiddenNodeCount: number;
  hiddenEdgeCount: number;
}

/**
 * Apply every facet to a model.
 *
 * Edges are dropped when they are filtered out **or when either endpoint is**,
 * so the canvas never renders a dangling edge — the failure that makes a graph
 * look like it invented a relation.
 */
export function applyFacets(model: GraphModel, facets: GraphFacets): FilteredGraph {
  const nodes = model.nodes.filter((node) => nodeMatchesFacets(node, facets));
  const live = new Set(nodes.map((node) => node.id));
  const edges = model.edges.filter(
    (edge) => live.has(edge.source) && live.has(edge.target) && edgeMatchesFacets(edge, facets),
  );
  return {
    nodes,
    edges,
    hiddenNodeCount: model.nodes.length - nodes.length,
    hiddenEdgeCount: model.edges.length - edges.length,
  };
}

/**
 * Which facets changed, as a label for the live region. Selecting a node must
 * not announce a filter change, and filtering must not announce a selection.
 */
export function describeFacets(facets: GraphFacets): string {
  const active = activeFacetIds(facets);
  return active.length === 0 ? "no filters" : `${active.length} filters active`;
}