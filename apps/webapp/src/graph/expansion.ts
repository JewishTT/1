import type { TimeRange } from "../workspace/types";
import { applyFacets, matchesTimeRange, EMPTY_GRAPH_FACETS, type GraphFacets } from "./filters";
import type { EdgeFamily, GraphEdge, GraphModel, GraphNode } from "./types";

/**
 * Bounded expansion (§21: "+1 hop / +2 hops / specific relation / specific
 * source / specific timeframe. Never dump the whole graph.").
 *
 * The prohibition is the feature. `expand` cannot express "give me
 * everything": `hops` is clamped to 1–2, every expansion takes a mandatory
 * budget, and the budget is enforced against the *result* rather than
 * requested after the fact. An expansion that would exceed its budget returns
 * `truncated: true` and says what it dropped, so the canvas can offer the
 * narrower next step instead of pretending it succeeded.
 */

export const MIN_HOPS = 1;
export const MAX_HOPS = 2;

/**
 * Default per-invocation node budget. Chosen so a 2-hop expansion of a
 * realistic neighbourhood lands in the low hundreds rather than the tens of
 * thousands: a canvas that shows 20,000 nodes shows a hairball, not an
 * answer. It is a *default*, and the caller may lower it, never raise it past
 * `HARD_NODE_CEILING`.
 */
export const DEFAULT_EXPANSION_BUDGET = 250;

/**
 * Absolute ceiling. A caller may pass a budget; it is clamped here. This is
 * the single place where "never dump the whole graph" is enforced rather than
 * requested, and it is a `const` so it cannot be raised by a prop.
 */
export const HARD_NODE_CEILING = 600;

export type ExpansionRequest =
  | { kind: "hops"; hops: number }
  | { kind: "relation"; relation: EdgeFamily }
  | { kind: "source"; sourceId: string }
  | { kind: "timeframe"; range: TimeRange }
  | { kind: "entity"; entityId: string };

export interface ExpansionOptions {
  /**
   * Ceiling on the RESULT. Clamped to `HARD_NODE_CEILING`. Exceeding it is a
   * truncation, never an error and never a silent success.
   */
  budget?: number;
  /** Facets already applied to the model; expansion respects them. */
  facets?: GraphFacets;
}

export interface ExpansionResult {
  /** Nodes to add, in deterministic discovery order. */
  added: GraphNode[];
  /** Edges to add: only those whose BOTH endpoints are in the result. */
  edges: GraphEdge[];
  /** True when the budget cut the expansion short. */
  truncated: boolean;
  /** How many nodes were found before the budget applied. Diagnostic, honest. */
  candidatesFound: number;
  /** What this expansion was asked to do, verbatim — the undo affordance. */
  request: ExpansionRequest;
  /**
   * Why it was cut, when it was. A truncated expansion with no reason is a
   * dead end (§69): the caller needs something to offer.
   */
  reason: string | null;
}

/** The labels the toolbar shows. `specific relation/source/timeframe` are these. */
export const EXPANSION_LABELS: Readonly<Record<ExpansionRequest["kind"], string>> = {
  hops: "hops",
  relation: "relation",
  source: "source",
  timeframe: "timeframe",
  entity: "entity",
};

/** Normalise a hop request. Out-of-range hops clamp to the nearest legal value. */
export function normaliseHops(hops: number): number {
  if (!Number.isFinite(hops)) return MIN_HOPS;
  return Math.min(MAX_HOPS, Math.max(MIN_HOPS, Math.round(hops)));
}

/**
 * Expand from a seed set. Never mutates the model; always returns the delta so
 * the canvas can apply it incrementally rather than rebuilding (§68).
 *
 * Traversal order is breadth-first from the seeds with seeds visited in id
 * order and neighbours in edge-id order, so two analysts expanding the same
 * seed see the same nodes in the same order. Determinism is the difference
 * between "the graph grew" and "the graph did something".
 */
export function expand(
  model: GraphModel,
  seedIds: readonly string[],
  request: ExpansionRequest,
  options: ExpansionOptions = {},
): ExpansionResult {
  const facets = options.facets ?? EMPTY_GRAPH_FACETS;
  const budget = clampBudget(options.budget);
  const seeds = seedIds.filter((id) => model.nodeIndex.has(id));

  if (seeds.length === 0) {
    return { added: [], edges: [], truncated: false, candidatesFound: 0, request, reason: null };
  }

  const allowed = allowedSet(model, facets);
  const keep = allowed.has(seeds[0]) ? seeds : seeds.filter((id) => allowed.has(id));
  if (keep.length === 0) {
    return {
      added: [],
      edges: [],
      truncated: false,
      candidatesFound: 0,
      request,
      reason: "the seeds are hidden by the current filters, so there is nothing to expand from",
    };
  }

  const discovered = request.kind === "hops" ? bfs(model, keep, normaliseHops(request.hops), allowed) : targeted(model, keep, request, allowed);

  const candidates = discovered.nodes.filter((node) => !keep.includes(node.id));
  const truncated = candidates.length > budget;
  const added = (truncated ? candidates.slice(0, budget) : candidates).sort(byNodeId);

  // An edge is added only when BOTH endpoints survive, so the canvas can never
  // render a dangling edge, and only when it is genuinely new — an edge whose
  // endpoints were both already on the canvas was already there.
  const keepSet = new Set(keep);
  const resultIds = new Set([...keep, ...added.map((node) => node.id)]);
  const edges = model.edges
    .filter((edge) => resultIds.has(edge.source) && resultIds.has(edge.target))
    .filter((edge) => !(keepSet.has(edge.source) && keepSet.has(edge.target)))
    .filter((edge) => allowed.has(edge.source) && allowed.has(edge.target))
    .filter((edge) => edgeMatchesRequest(edge, request))
    .sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));

  return {
    added,
    edges,
    truncated,
    candidatesFound: candidates.length,
    request,
    reason: truncated
      ? `${candidates.length} objects matched; showing the first ${added.length} under the expansion budget. Narrow by relation, source or timeframe.`
      : null,
  };
}

function clampBudget(budget: number | undefined): number {
  if (budget === undefined || !Number.isFinite(budget)) return DEFAULT_EXPANSION_BUDGET;
  return Math.max(1, Math.min(HARD_NODE_CEILING, Math.floor(budget)));
}

/** Nodes surviving the active facets, plus a guard for edges (§22, §81). */
function allowedSet(model: GraphModel, facets: GraphFacets): Set<string> {
  const filtered = applyFacets(model, facets);
  return new Set(filtered.nodes.map((node) => node.id));
}

interface Discovery {
  nodes: GraphNode[];
}

/** Breadth-first to `depth` hops. depth is already clamped to 1–2. */
function bfs(model: GraphModel, seeds: readonly string[], depth: number, allowed: ReadonlySet<string>): Discovery {
  const seen = new Set(seeds);
  const collected: GraphNode[] = [];
  let frontier = [...seeds];

  for (let hop = 0; hop < depth; hop += 1) {
    const next: string[] = [];
    for (const id of frontier) {
      for (const edge of incidentEdges(model, id)) {
        const other = edge.source === id ? edge.target : edge.source;
        if (seen.has(other) || !allowed.has(other)) continue;
        seen.add(other);
        const node = model.nodeIndex.get(other);
        if (node) collected.push(node);
        next.push(other);
      }
    }
    if (next.length === 0) break;
    frontier = [...next].sort();
  }

  return { nodes: collected };
}

/** A specific relation / source / timeframe / entity — one hop, one constraint. */
function targeted(
  model: GraphModel,
  seeds: readonly string[],
  request: Exclude<ExpansionRequest, { kind: "hops" }>,
  allowed: ReadonlySet<string>,
): Discovery {
  const seedSet = new Set(seeds);
  const nodes: GraphNode[] = [];
  const seen = new Set<string>();

  for (const edge of model.edges) {
    if (!edgeMatchesRequest(edge, request)) continue;
    const fromSeed = seedSet.has(edge.source);
    const toSeed = seedSet.has(edge.target);
    if (!fromSeed && !toSeed) continue;
    if (!allowed.has(edge.source) || !allowed.has(edge.target)) continue;

    // The seed side is already on the canvas; only the far side is an addition.
    const far = fromSeed ? edge.target : edge.source;
    if (seedSet.has(far) || seen.has(far)) continue;
    seen.add(far);
    const node = model.nodeIndex.get(far);
    if (node) nodes.push(node);
  }

  return { nodes };
}

/** Does this edge satisfy the constraint the expansion was asked for? */
function edgeMatchesRequest(edge: GraphEdge, request: ExpansionRequest): boolean {
  switch (request.kind) {
    case "hops":
    case "entity":
      return true;
    case "relation":
      return edge.family === request.relation;
    case "source":
      // A relation is "from this source" when it names at least one of that
      // source's observations, or when the relation carries that source id.
      return edge.source.endsWith(`:${request.sourceId}`) || edge.target.endsWith(`:${request.sourceId}`);
    case "timeframe":
      return matchesTimeRange([edge.validFrom, edge.validTo].filter((v): v is string => v !== null), request.range);
  }
}

/** Incident edges, ordered by edge id so traversal is deterministic. */
function incidentEdges(model: GraphModel, id: string): GraphEdge[] {
  const out: GraphEdge[] = [];
  for (const edge of model.edges) {
    if (edge.source === id || edge.target === id) out.push(edge);
  }
  return out.sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
}

const byNodeId = (a: GraphNode, b: GraphNode): number => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);

/**
 * Collapse. "Collapse to the seed set" is the inverse operation and it is what
 * makes expansion reversible: without it, every expansion is a one-way door
 * and §21's "never dump" promise has no exit.
 */
export function collapse(
  model: GraphModel,
  keepIds: readonly string[],
  options: ExpansionOptions = {},
): { removedNodeCount: number; removedEdgeCount: number } {
  const facets = options.facets ?? EMPTY_GRAPH_FACETS;
  const allowed = allowedSet(model, facets);
  const keep = new Set(keepIds.filter((id) => model.nodeIndex.has(id) && allowed.has(id)));
  const removedNodes = model.nodes.filter((node) => !keep.has(node.id));
  const removedEdgeIds = new Set(
    model.edges
      .filter((edge) => !(keep.has(edge.source) && keep.has(edge.target)))
      .map((edge) => edge.id),
  );
  return { removedNodeCount: removedNodes.length, removedEdgeCount: removedEdgeIds.size };
}

/**
 * The expansion options the toolbar offers, as data. The toolbar renders this
 * list rather than hard-coding buttons, so §21's menu and the test that walks
 * it cannot drift apart.
 */
export interface ExpansionChoice {
  id: string;
  label: string;
  hint: string;
  request: ExpansionRequest;
}

export function expansionChoices(sourceIds: ReadonlyArray<string> = []): ExpansionChoice[] {
  const base: ExpansionChoice[] = [
    { id: "expand.1hop", label: "+1 hop", hint: "Direct neighbours of the selection", request: { kind: "hops", hops: 1 } },
    { id: "expand.2hops", label: "+2 hops", hint: "Two rings out — bounded, never the whole graph", request: { kind: "hops", hops: 2 } },
  ];
  const relations: ExpansionChoice[] = (
    ["observes", "asserts", "supports", "possible"] as const
  ).map((relation) => ({
    id: `expand.relation.${relation}`,
    label: `+ ${relation}`,
    hint: `Only ${relation} relations from the selection`,
    request: { kind: "relation", relation },
  }));
  const sources: ExpansionChoice[] = sourceIds.map((sourceId) => ({
    id: `expand.source.${sourceId}`,
    label: `+ ${sourceId}`,
    hint: `Only relations touching records from ${sourceId}`,
    request: { kind: "source", sourceId },
  }));
  const timeframes: ExpansionChoice[] = [
    {
      id: "expand.timeframe.last24h",
      label: "+ last 24h",
      hint: "Only relations observed inside the last 24 hours",
      request: {
        kind: "timeframe",
        range: { from: new Date(Date.now() - 24 * 3_600_000).toISOString(), to: null },
      },
    },
    {
      id: "expand.timeframe.last7d",
      label: "+ last 7d",
      hint: "Only relations observed inside the last seven days",
      request: {
        kind: "timeframe",
        range: { from: new Date(Date.now() - 7 * 86_400_000).toISOString(), to: null },
      },
    },
  ];
  return [...base, ...relations, ...sources, ...timeframes];
}