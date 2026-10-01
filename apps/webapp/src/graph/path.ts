import type { Emphasis } from "./semantics";
import type { GraphModel } from "./types";

/**
 * Path finding and emphasis (§17, §18).
 *
 * Three separate concerns, deliberately kept apart:
 *
 *   1. `findPath` — the shortest relation chain between two selected objects.
 *      Breadth-first over an unweighted graph; deterministic tie-breaking by
 *      edge id, because two analysts asking "how are these connected" must get
 *      the same chain or the question has no stable answer.
 *   2. `resolveEmphasis` — what is loud right now. Exactly one element is
 *      `selected`; the selected path is `path`; the selected element's
 *      immediate neighbours are `neighbour`; everything else is `secondary`,
 *      i.e. visibly receded rather than hidden. Hiding is a filter decision,
 *      not a selection side-effect (§17: "secondary relations dim").
 *   3. `neighbourIds` — the ring that gets the restrained emphasis.
 *
 * Selection state is read from the store, never owned here (§7).
 */

export interface PathResult {
  /** Node ids from source to target inclusive. Empty when no path exists. */
  nodeIds: string[];
  /** Edge ids along that path, in the same order. */
  edgeIds: string[];
  /** True when no chain exists — a real answer, not an error. */
  unreachable: boolean;
  /** The length in hops. `null` when unreachable. */
  hops: number | null;
}

const EMPTY_PATH: PathResult = { nodeIds: [], edgeIds: [], unreachable: true, hops: null };

/**
 * Shortest chain between two nodes. Undirected: the canvas has no arrowheads
 * at rest (Visual Direction §3), so a relation can be traversed either way and
 * the shortest chain is the honest answer to "how are these connected".
 */
export function findPath(model: GraphModel, sourceId: string, targetId: string): PathResult {
  if (sourceId === targetId) {
    return model.nodeIndex.has(sourceId)
      ? { nodeIds: [sourceId], edgeIds: [], unreachable: false, hops: 0 }
      : { ...EMPTY_PATH };
  }
  if (!model.nodeIndex.has(sourceId) || !model.nodeIndex.has(targetId)) return { ...EMPTY_PATH };

  const adjacency = adjacencyList(model);
  const previous = new Map<string, { node: string; edge: string } | null>([[sourceId, null]]);
  const queue: string[] = [sourceId];

  while (queue.length > 0) {
    const current = queue.shift() as string;
    if (current === targetId) break;
    for (const { node, edge } of adjacency.get(current) ?? []) {
      if (previous.has(node)) continue;
      previous.set(node, { node: current, edge });
      queue.push(node);
    }
  }

  if (!previous.has(targetId)) return { ...EMPTY_PATH };

  const nodeIds: string[] = [targetId];
  const edgeIds: string[] = [];
  let cursor: string | null = targetId;
  while (cursor !== null && cursor !== sourceId) {
    const step = previous.get(cursor);
    if (!step) return { ...EMPTY_PATH };
    edgeIds.push(step.edge);
    nodeIds.push(step.node);
    cursor = step.node;
  }
  nodeIds.reverse();
  edgeIds.reverse();
  return { nodeIds, edgeIds, unreachable: false, hops: edgeIds.length };
}

/** Adjacency, neighbours sorted by edge id so traversal order never depends on map order. */
function adjacencyList(model: GraphModel): Map<string, Array<{ node: string; edge: string }>> {
  const adjacency = new Map<string, Array<{ node: string; edge: string }>>();
  const sorted = [...model.edges].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  for (const edge of sorted) {
    if (!adjacency.has(edge.source)) adjacency.set(edge.source, []);
    if (!adjacency.has(edge.target)) adjacency.set(edge.target, []);
    (adjacency.get(edge.source) as Array<{ node: string; edge: string }>).push({ node: edge.target, edge: edge.id });
    (adjacency.get(edge.target) as Array<{ node: string; edge: string }>).push({ node: edge.source, edge: edge.id });
  }
  return adjacency;
}

/** The immediate neighbourhood of a node set: what gets the restrained emphasis. */
export function neighbourIds(model: GraphModel, ids: readonly string[]): Set<string> {
  const seeds = new Set(ids);
  const out = new Set<string>();
  for (const edge of model.edges) {
    if (seeds.has(edge.source) && !seeds.has(edge.target)) out.add(edge.target);
    if (seeds.has(edge.target) && !seeds.has(edge.source)) out.add(edge.source);
  }
  for (const id of seeds) out.delete(id);
  return out;
}

export interface EmphasisMap {
  /** nodeId → emphasis. Nodes absent from the map are `rest`. */
  nodes: Map<string, Emphasis>;
  /** edgeId → emphasis. Edges absent from the map are `rest`. */
  edges: Map<string, Emphasis>;
  /** Edge ids currently drawn with their predicate visible. */
  labelledEdges: Set<string>;
  /** Ids the analyst added to the comparison set; drawn with the secondary rule. */
  secondaryNodes: Set<string>;
}

/**
 * The whole emphasis decision for one render, in one pure function.
 *
 * Precedence, highest first: explicit selection > path > neighbour > rest.
 * A node that is both a path member and a neighbour is `path`, because the
 * path is the thing the analyst explicitly asked to see.
 */
export function resolveEmphasis(
  model: GraphModel,
  selectedNodeIds: readonly string[],
  secondaryNodeIds: readonly string[],
  selectedEdgeIds: readonly string[],
  path: PathResult,
): EmphasisMap {
  const nodes = new Map<string, Emphasis>();
  const edges = new Map<string, Emphasis>();
  const secondaryNodes = new Set<string>(secondaryNodeIds.filter((id) => model.nodeIndex.has(id)));

  const pathNodes = new Set(path.nodeIds);
  const pathEdges = new Set(path.edgeIds);

  // Nodes on the focused path, excluding the ends the analyst clicked (those
  // are `selected`, which reads stronger).
  for (const id of pathNodes) nodes.set(id, "path");
  for (const id of pathEdges) edges.set(id, "path");

  // Immediate neighbours of the selection — restrained, never competing.
  const neighbours = neighbourIds(model, selectedNodeIds);
  for (const id of neighbours) if (nodes.get(id) !== "path") nodes.set(id, "neighbour");

  // Everything else recedes only while something is selected. With no
  // selection the graph is at rest and reads flat, which is what a graph with
  // no question should look like.
  const focused = selectedNodeIds.length > 0 || selectedEdgeIds.length > 0;
  if (focused) {
    for (const node of model.nodes) if (!nodes.has(node.id)) nodes.set(node.id, "secondary");
    for (const edge of model.edges) if (!edges.has(edge.id)) edges.set(edge.id, "secondary");
  }

  for (const id of selectedNodeIds) if (model.nodeIndex.has(id)) nodes.set(id, "selected");
  for (const id of selectedEdgeIds) if (model.edgeIndex.has(id)) edges.set(id, "selected");

  const labelledEdges = new Set<string>();
  for (const [id, emphasis] of edges) {
    if (emphasis === "selected" || emphasis === "path") labelledEdges.add(id);
  }

  return { nodes, edges, labelledEdges, secondaryNodes };
}

/**
 * All shortest chains between two objects, capped. "Path" in a workbench means
 * "how else might these be connected", and a single chain answers a different
 * question. Bounded, because an unbounded path enumeration is the graph
 * equivalent of dumping the graph.
 */
export function findPaths(model: GraphModel, sourceId: string, targetId: string, limit = 5): PathResult[] {
  const adjacency = adjacencyList(model);
  if (!model.nodeIndex.has(sourceId) || !model.nodeIndex.has(targetId)) return [];

  const results: PathResult[] = [];
  const queue: string[][] = [[sourceId]];
  const seenPaths = new Set<string>([sourceId]);
  let guard = 0;

  while (queue.length > 0 && results.length < limit && guard < 10_000) {
    guard += 1;
    const path = queue.shift() as string[];
    const tail = path[path.length - 1];
    if (tail === targetId) {
      results.push(toPathResult(model, path));
      continue;
    }
    for (const { node } of adjacency.get(tail) ?? []) {
      if (path.includes(node)) continue;
      const nextPath = [...path, node];
      const key = nextPath.join(">");
      if (seenPaths.has(key)) continue;
      seenPaths.add(key);
      queue.push(nextPath);
    }
  }

  return results.sort((a, b) => (a.hops ?? 0) - (b.hops ?? 0)).slice(0, limit);
}

function toPathResult(model: GraphModel, nodeIds: string[]): PathResult {
  const edgeIds: string[] = [];
  for (let index = 0; index + 1 < nodeIds.length; index += 1) {
    const from = nodeIds[index];
    const to = nodeIds[index + 1];
    const edge = model.edges.find((candidate) => edgesJoin(candidate, from, to));
    if (edge) edgeIds.push(edge.id);
  }
  return { nodeIds, edgeIds, unreachable: false, hops: edgeIds.length };
}

function edgesJoin(edge: { source: string; target: string }, from: string, to: string): boolean {
  return (edge.source === from && edge.target === to) || (edge.source === to && edge.target === from);
}