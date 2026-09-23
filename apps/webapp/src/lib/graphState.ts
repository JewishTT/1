/**
 * Deterministic save/restore of the intelligence-graph VIEW state (node
 * positions, zoom/pan, selection) with a versioned, checksummed schema.
 *
 * - stableStringify() sorts object keys recursively so two snapshots of an
 *   identical view byte-collide (deterministic serialization).
 * - entitiesKey is a content hash over the node/edge id set; a restore is
 *   REFUSED when the current graph topology no longer matches the saved one.
 * - export/import carry an FNV-1a checksum (synchronous, no async needed).
 * - localStorage helpers are hermetic (no backend dependency) and guarded.
 *
 * The module is pure except for the thin cytoscape / localStorage wrappers.
 */

import type cytoscape from "cytoscape";

export const GRAPH_VIEW_STATE_VERSION = 1;
export const GRAPH_VIEW_STORAGE_KEY = "cognitive.intel.graph-view-state.v1";

const GRAPH_VIEW_EXPORT_FORMAT = "cognitive.intel.graph-view";

const FNV1A_OFFSET = 0x811c9dc5;
const FNV1A_PRIME = 0x01000193;

// ── Schema ────────────────────────────────────────────────────────────

export interface GraphNodeView {
  id: string;
  x: number;
  y: number;
}

export interface GraphEdgeView {
  id: string;
  source: string;
  target: string;
}

export interface GraphPan {
  x: number;
  y: number;
}

export interface GraphViewState {
  version: number;
  savedAt: string;
  entitiesKey: string;
  nodes: GraphNodeView[];
  edges: GraphEdgeView[];
  zoom: number;
  pan: GraphPan;
  selected: string[];
}

/** Structural subset of an intel graph used to fingerprint its topology. */
export interface GraphTopologyLike {
  nodes: Array<{ id: string }>;
  edges: Array<{ id: string; source: string; target: string }>;
}

// ── Deterministic primitives ──────────────────────────────────────────

/** FNV-1a 32-bit hash as an 8-hex-lowercase string. */
export function fnv1a(text: string): string {
  let hash = FNV1A_OFFSET;
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, FNV1A_PRIME);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

/** Recursively-sorted-key JSON serialization (deterministic byte output). */
export function stableStringify(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map((v) => stableStringify(v)).join(",")}]`;
  const record = value as Record<string, unknown>;
  const keys = Object.keys(record).sort();
  return `{${keys
    .map((k) => `${JSON.stringify(k)}:${stableStringify(record[k])}`)
    .join(",")}}`;
}

/** Content hash over the node/edge id set — topology fingerprint. */
export function entitiesKeyFor(
  nodes: Array<{ id: string }>,
  edges: Array<{ id: string; source: string; target: string }>,
): string {
  const nodeIds = nodes.map((n) => n.id).sort();
  const edgeTuples = edges
    .map((e) => `${e.id}\u0000${e.source}\u0000${e.target}`)
    .sort();
  const canonical = `${nodeIds.join("\u0000")}\u0001${edgeTuples.join("\u0001")}`;
  return fnv1a(canonical);
}

/** Topology fingerprint for the data-level graph the canvas is built from. */
export function entitiesKeyFromGraph(graph: GraphTopologyLike): string {
  return entitiesKeyFor(graph.nodes, graph.edges);
}

// ── Cytoscape wrappers ────────────────────────────────────────────────

/** Capture the current canvas view into a deterministic, versioned state. */
export function snapshotGraph(cy: cytoscape.Core): GraphViewState {
  const nodes: GraphNodeView[] = cy
    .nodes()
    .map((n) => ({ id: n.id(), x: n.position("x"), y: n.position("y") }))
    .sort(byId);
  const edges: GraphEdgeView[] = cy
    .edges()
    .map((e) => ({ id: e.id(), source: e.source().id(), target: e.target().id() }))
    .sort((a, b) => {
      const byKey = byId(a, b);
      if (byKey !== 0) return byKey;
      if (a.source < b.source) return -1;
      if (a.source > b.source) return 1;
      return a.target < b.target ? -1 : a.target > b.target ? 1 : 0;
    });
  const selected = cy.nodes(":selected").map((n) => n.id()).sort();
  return {
    version: GRAPH_VIEW_STATE_VERSION,
    savedAt: new Date().toISOString(),
    entitiesKey: entitiesKeyFor(nodes, edges),
    nodes,
    edges,
    zoom: cy.zoom(),
    pan: { x: cy.pan().x, y: cy.pan().y },
    selected,
  };
}

const byId = (a: { id: string }, b: { id: string }): number =>
  a.id < b.id ? -1 : a.id > b.id ? 1 : 0;

/**
 * Apply a previously captured state to a live canvas. Only applies when the
 * version and the topology key match the current graph — otherwise it is a
 * hard no-op. Returns the applied node selection (empty when none), or null
 * when the restore was refused.
 */
export function restoreGraph(
  cy: cytoscape.Core,
  state: GraphViewState,
  currentKey: string,
): string[] | null {
  if (state.version !== GRAPH_VIEW_STATE_VERSION) return null;
  if (state.entitiesKey !== currentKey) return null;
  if (!cy || typeof cy.nodes !== "function" || typeof cy.zoom !== "function") return null;

  // Halt any in-flight layout flourish so the restored view actually sticks.
  if (typeof cy.stop === "function") cy.stop();
  if (typeof cy.elements === "function" && typeof cy.elements().stop === "function") {
    cy.elements().stop();
  }

  const byNodeId = new Map<string, cytoscape.NodeSingular>();
  for (const el of cy.nodes()) byNodeId.set(el.id(), el);

  for (const node of state.nodes) {
    const el = byNodeId.get(node.id);
    if (el) el.position({ x: node.x, y: node.y });
  }

  const minZoom = typeof cy.minZoom === "function" ? cy.minZoom() : Number.NEGATIVE_INFINITY;
  const maxZoom = typeof cy.maxZoom === "function" ? cy.maxZoom() : Number.POSITIVE_INFINITY;
  cy.zoom(Math.min(Math.max(state.zoom, minZoom), maxZoom));
  cy.pan({ x: state.pan.x, y: state.pan.y });

  cy.nodes().unselect();
  const applied: string[] = [];
  for (const id of state.selected) {
    const el = byNodeId.get(id);
    if (el) {
      el.select();
      applied.push(id);
    }
  }
  return applied;
}

// ── Export / import (checksummed) ─────────────────────────────────────

function checksumOf(state: GraphViewState): string {
  return fnv1a(stableStringify(state));
}

/** Serialize a snapshot into a deterministic, checksummed JSON document. */
export function exportGraphJSON(state: GraphViewState): string {
  return stableStringify({
    format: GRAPH_VIEW_EXPORT_FORMAT,
    checksum: checksumOf(state),
    state: {
      version: state.version,
      savedAt: state.savedAt,
      entitiesKey: state.entitiesKey,
      nodes: state.nodes,
      edges: state.edges,
      zoom: state.zoom,
      pan: state.pan,
      selected: state.selected,
    },
  });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isGraphViewState(value: unknown): value is GraphViewState {
  if (!isRecord(value)) return false;
  if (value["version"] !== GRAPH_VIEW_STATE_VERSION) return false;
  if (typeof value["savedAt"] !== "string") return false;
  if (typeof value["entitiesKey"] !== "string") return false;
  if (typeof value["zoom"] !== "number" || !Number.isFinite(value["zoom"])) return false;
  if (!isRecord(value["pan"])) return false;
  const pan = value["pan"];
  if (typeof pan["x"] !== "number" || !Number.isFinite(pan["x"])) return false;
  if (typeof pan["y"] !== "number" || !Number.isFinite(pan["y"])) return false;
  if (!Array.isArray(value["nodes"])) return false;
  if (!value["nodes"].every((n) => isRecord(n) && typeof n["id"] === "string" &&
    typeof n["x"] === "number" && Number.isFinite(n["x"]) &&
    typeof n["y"] === "number" && Number.isFinite(n["y"]))) return false;
  if (!Array.isArray(value["edges"])) return false;
  if (!value["edges"].every((e) => isRecord(e) && typeof e["id"] === "string" &&
    typeof e["source"] === "string" && typeof e["target"] === "string")) return false;
  if (!Array.isArray(value["selected"])) return false;
  return value["selected"].every((s) => typeof s === "string");
}

/**
 * Parse and validate an exported graph-view document. Throws on malformed
 * JSON, an unknown format/version, or a checksum mismatch (corrupt import).
 */
export function parseGraphJSON(text: string): GraphViewState {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error("not valid JSON");
  }
  if (!isRecord(parsed)) throw new Error("not a graph-view envelope");
  if (parsed["format"] !== GRAPH_VIEW_EXPORT_FORMAT) {
    throw new Error("unrecognized graph-view format");
  }
  const state = parsed["state"];
  if (!isGraphViewState(state)) throw new Error("invalid graph-view schema");
  const expected = checksumOf(state);
  if (parsed["checksum"] !== expected) {
    throw new Error("checksum mismatch — file is corrupt or tampered");
  }
  return {
    version: state.version,
    savedAt: state.savedAt,
    entitiesKey: state.entitiesKey,
    nodes: state.nodes,
    edges: state.edges,
    zoom: state.zoom,
    pan: state.pan,
    selected: state.selected,
  };
}

// ── Hermetic storage (localStorage, no backend) ───────────────────────

function storageAvailable(): boolean {
  try {
    return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
  } catch {
    return false;
  }
}

/** Persist a snapshot under the versioned key. Returns false on failure. */
export function saveGraphStateToStorage(state: GraphViewState): boolean {
  try {
    if (!storageAvailable()) return false;
    window.localStorage.setItem(GRAPH_VIEW_STORAGE_KEY, exportGraphJSON(state));
    return true;
  } catch {
    return false;
  }
}

/** Read the persisted snapshot (parse failures surface as null). */
export function loadGraphStateFromStorage(): GraphViewState | null {
  try {
    if (!storageAvailable()) return null;
    const raw = window.localStorage.getItem(GRAPH_VIEW_STORAGE_KEY);
    if (!raw) return null;
    return parseGraphJSON(raw);
  } catch {
    return null;
  }
}

export function clearGraphStateStorage(): void {
  try {
    if (!storageAvailable()) return;
    window.localStorage.removeItem(GRAPH_VIEW_STORAGE_KEY);
  } catch {
    // storage is best-effort; nothing to surface
  }
}