/** Deterministic edge formation (W5 persistence — same input ⇒ same graph).

Single source of truth for edge identity, dedupe and emit order across the
webapp graph builders (entityGraph, intelGraph). Edge ids are
content-addressed: a stable hash over the ordered (min,max) node pair, the
provenance-derived kind and the provenance source — so a→b and b→a produce the
same id, duplicate primitives collapse, and edge emission is order-invariant.
Node ordering is a stable id sort; the layout seed is derived from the
node set so a reload of the same data renders identically.
*/

export type EdgeKind =
  | "assertion"
  | "evidence"
  | "possible_match"
  | "relationship"
  | "source_host"
  | "co_occurrence";

/** One primitive edge already derived from data (the caller holds the raw shape). */
export interface EdgeSeed {
  a: string;
  b: string;
  kind: EdgeKind;
  /** Provenance anchor: correlation edge id, evidence id, host, relationship type… */
  source: string;
  /** Human-readable label shown on the rendered edge. */
  reason?: string;
}

/** Co-mention/observation co-occurrence primitive: every node in `nodes` is conjoined with every other via one edge. */
export interface ObservationCoOccurrence {
  observation_id: string;
  /** Ordered set of node ids observed together (the observation is the anchor/source). */
  nodes: string[];
  /** Provenance-derived kind; defaults to `co_occurrence` when the data carries no explicit kind. */
  kind?: EdgeKind;
}

/** Normalized carrier consumed by `formEdges` — adapters map raw API shapes onto it. */
export interface EdgeFormationData {
  observations: ObservationCoOccurrence[];
  seeds: EdgeSeed[];
}

/** A fully-formed, content-addressed edge with deterministic emit order. */
export interface FormedEdge {
  id: string;
  source: string;
  target: string;
  kind: EdgeKind;
  reason: string;
}

/** FNV-1a 32-bit — stable, dependency-free, content-addressed. */
function fnv1a(input: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < input.length; i += 1) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
    h >>>= 0;
  }
  return h >>> 0;
}

/**
 * Content-addressed edge id: stable hash over the ORDERED (min,max) node pair,
 * the provenance-derived kind and the provenance source. Order-invariant —
 * a→b and b→a yield the same id — so undirected findings never duplicate.
 */
export function makeEdgeId(nodeA: string, nodeB: string, kind: EdgeKind, source: string): string {
  const lo = nodeA < nodeB ? nodeA : nodeB;
  const hi = nodeA < nodeB ? nodeB : nodeA;
  const digest = fnv1a(`${lo}\u0000${hi}\u0000${kind}\u0000${source}`);
  return `e:${digest.toString(16).padStart(8, "0")}`;
}

/** Stable node ordering: canonical id sort, order-invariant for the same set. */
export function orderNodeIds(nodes: ReadonlyArray<string>): string[] {
  return [...nodes].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
}

/** Fixed seed base — a NaN-looking play on 0x5EED, kept constant for W5 persistence. */
export const LAYOUT_SEED_BASE = 0x5eed;

/**
 * Stable layout seed derivation: hash-over-node-set (so it survives reordering
 * and reloads) falling back to a fixed constant for empty graphs. Used to key
 * deterministic layout geometry — same data ⇒ same canvas.
 */
export function layoutSeed(nodeIds: ReadonlyArray<string>): number {
  const sorted = orderNodeIds(nodeIds);
  if (sorted.length === 0) return LAYOUT_SEED_BASE;
  return (fnv1a(sorted.join("\u0000")) % 100000) + LAYOUT_SEED_BASE;
}

/**
 * Deterministic layout options for a given layout name. `cose` is forced to
 * `randomize: false` (initial geometry derived from the id-sorted node order)
 * and carries the node-set seed — deterministic when fed from deterministic
 * data; all other layouts are already canonical (grid/circle/concentric/
 * breadthfirst) and pass through unchanged.
 */
export function deterministicLayout(name: string, nodeIds: ReadonlyArray<string>): Record<string, unknown> {
  if (name === "cose") {
    return { name: "cose", randomize: false, randomSeed: layoutSeed(nodeIds) };
  }
  return { name };
}

/**
 * Deterministic edge factory over normalized data. Conjoins co-mention
 * observations into edges, appends explicitly derived seeds, then skips
 * self-loops, drops edges whose endpoints are not known nodes, dedupes by the
 * content-addressed edge id and emits sorted by edge id.
 */
export function formEdges(
  nodes: ReadonlyArray<string>,
  data: EdgeFormationData,
): FormedEdge[] {
  const known = new Set(nodes);
  const seeds: EdgeSeed[] = [];

  for (const obs of data.observations ?? []) {
    const kind = obs.kind ?? "co_occurrence";
    const source = obs.observation_id;
    for (let i = 0; i < obs.nodes.length; i += 1) {
      for (let j = i + 1; j < obs.nodes.length; j += 1) {
        seeds.push({ a: obs.nodes[i], b: obs.nodes[j], kind, source, reason: source });
      }
    }
  }
  seeds.push(...(data.seeds ?? []));

  const formed = new Map<string, FormedEdge>();
  for (const seed of seeds) {
    if (seed.a === seed.b) continue;
    if (!known.has(seed.a) || !known.has(seed.b)) continue;
    const id = makeEdgeId(seed.a, seed.b, seed.kind, seed.source);
    formed.set(id, {
      id,
      source: seed.a,
      target: seed.b,
      kind: seed.kind,
      reason: seed.reason ?? seed.source,
    });
  }

  return [...formed.values()].sort((x, y) => (x.id < y.id ? -1 : x.id > y.id ? 1 : 0));
}