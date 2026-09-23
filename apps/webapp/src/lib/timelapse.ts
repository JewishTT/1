/**
 * Timelapse — deterministic state-at-time reconstruction (011/FR-009).
 *
 * Golden rule: the state at time T is a deterministic function of the event
 * log — replay every observation with ``observed_at ≤ T`` in sorted order
 * (ties broken by stable entity id, then insertion order). An entity with no
 * observation ≤ T is "unknown", never "absent" — no fabrication (I-3).
 *
 * Pure functions over the observation log — no I/O, no state. The same log
 * always produces the same slices, so the scrubber is fully replayable.
 */

import { toEpochMs, type TimestampInput } from "./timing";

/** One observation in the replay log (stable entity id + timestamp). */
export interface TimelapseEvent {
  /** Stable entity id — the anchor carried across replay frames. */
  entityId: string;
  /** Observation timestamp (ISO-UTC string or epoch ms). */
  at: TimestampInput;
  /** Version observed at this timestamp, when the event encodes one. */
  version?: number;
  /** Confidence carried by this observation, when present. */
  confidence?: number;
}

/** Reconstructed single-entity state at an instant T. */
export interface TimelapseState {
  /** Entity has an observation ≤ T. false ⇒ "unknown" at T — never "absent". */
  active: boolean;
  /** Version of the last observation applied ≤ T. */
  version?: number;
  /** Confidence of the last observation applied ≤ T. */
  confidence?: number;
  /** observed_at of the newest observation ≤ T (null when none applied). */
  lastSeen: TimestampInput | null;
}

/** A network node with the observation times that mark it as alive. */
export interface TimelapseNode {
  id: string;
  label: string;
  /** observed_at stamps for this node; empty/undefined ⇒ unknown at any T. */
  seasons?: TimestampInput[];
}

/** A network edge; alive at T when both endpoints are alive (and by its own stamp, if any). */
export interface TimelapseEdge {
  id: string;
  source: string;
  target: string;
  kind?: string;
  /** Optional explicit stamp; absent ⇒ the edge inherits its endpoints. */
  at?: TimestampInput;
}

/** Subset of the network that is alive at T + counts (deterministic). */
export interface NetworkTimelapseState {
  nodes: TimelapseNode[];
  edges: TimelapseEdge[];
  aliveNodeCount: number;
  aliveEdgeCount: number;
}

/** One sorted replay frame (distinct observation instant + cumulative counts). */
export interface TimelapseFrame {
  /** Normalized ISO-UTC instant. */
  t: string;
  /** Epoch-ms instant (axis position for the slider). */
  atMs: number;
  /** Distinct entities alive at this instant (observations ≤ t). */
  active: number;
  /** Applied observations ≤ t. */
  events: number;
}

/** Deterministic index order: time, then stable entity id, then insertion order. */
function compareAt(a: TimelapseEvent, b: TimelapseEvent): number {
  const am = toEpochMs(a.at) ?? Number.POSITIVE_INFINITY;
  const bm = toEpochMs(b.at) ?? Number.POSITIVE_INFINITY;
  if (am !== bm) return am - bm;
  if (a.entityId !== b.entityId) return a.entityId < b.entityId ? -1 : 1;
  return 0;
}

/** [min, max] epoch-ms bounds of the log; null when no event parses to a time. */
export function timeBounds(events: TimelapseEvent[]): [number, number] | null {
  const times = events
    .map((e) => toEpochMs(e.at))
    .filter((v): v is number => v !== null);
  if (times.length === 0) return null;
  return [Math.min(...times), Math.max(...times)];
}

/**
 * Reconstruct one entity's state at instant T by replaying every observation
 * with ``observed_at ≤ T`` in sorted orders. "Active" implies T ≥ the
 * entity's first_seen by construction, since first_seen is the earliest
 * observation in the log. Inputs with no parseable bound yield
 * ``{ active: false, lastSeen: null }`` — unknown, never absent.
 */
export function stateAtTime(events: TimelapseEvent[], T: TimestampInput): TimelapseState {
  const tMs = toEpochMs(T);
  if (tMs === null) return { active: false, lastSeen: null };
  const applied = events
    .filter((e) => {
      const ms = toEpochMs(e.at);
      return ms !== null && ms <= tMs;
    })
    .sort(compareAt);
  if (applied.length === 0) return { active: false, lastSeen: null };
  const last = applied[applied.length - 1];
  const state: TimelapseState = { active: true, lastSeen: last.at };
  if (last.version !== undefined) state.version = last.version;
  if (last.confidence !== undefined) state.confidence = last.confidence;
  return state;
}

function nodeAliveAt(node: TimelapseNode, tMs: number): boolean {
  return (node.seasons ?? []).some((s) => {
    const ms = toEpochMs(s);
    return ms !== null && ms <= tMs;
  });
}

/**
 * Deterministic network slice at T: a node is alive when it has a season
 * stamp ≤ T; an edge is alive when both endpoints are alive (and, when the
 * edge carries its own stamp, only if that stamp ≤ T). Input order is
 * preserved. No seasons ⇒ unknown (dropped, never fabricated).
 */
export function networkStateAtTime(
  nodes: TimelapseNode[],
  edges: TimelapseEdge[],
  T: TimestampInput,
): NetworkTimelapseState {
  const tMs = toEpochMs(T);
  if (tMs === null) return { nodes: [], edges: [], aliveNodeCount: 0, aliveEdgeCount: 0 };
  const aliveNodes = nodes.filter((n) => nodeAliveAt(n, tMs));
  const aliveIds = new Set(aliveNodes.map((n) => n.id));
  const aliveEdges = edges.filter((edge) => {
    if (edge.at !== undefined) {
      const ms = toEpochMs(edge.at);
      if (ms === null || ms > tMs) return false;
    }
    return aliveIds.has(edge.source) && aliveIds.has(edge.target);
  });
  return {
    nodes: aliveNodes,
    edges: aliveEdges,
    aliveNodeCount: aliveNodes.length,
    aliveEdgeCount: aliveEdges.length,
  };
}

/**
 * Sorted replay frames: every distinct observation instant, in chronological
 * order, with cumulative counts. Drives the slider's datalist ticks and the
 * play sequence. Deterministic — the same log always yields the same frames.
 */
export function deduceTimeline(events: TimelapseEvent[]): TimelapseFrame[] {
  const instants = [
    ...new Set(
      events
        .map((e) => toEpochMs(e.at))
        .filter((v): v is number => v !== null),
    ),
  ].sort((a, b) => a - b);
  return instants.map((atMs) => {
    const applied = events.filter((e) => {
      const ms = toEpochMs(e.at);
      return ms !== null && ms <= atMs;
    });
    const active = new Set(applied.map((e) => e.entityId)).size;
    return {
      t: new Date(atMs).toISOString(),
      atMs,
      active,
      events: applied.length,
    };
  });
}