import { afterEach, describe, expect, it, vi } from "vitest";

import {
  GRAPH_VIEW_STATE_VERSION,
  GRAPH_VIEW_STORAGE_KEY,
  clearGraphStateStorage,
  entitiesKeyFor,
  entitiesKeyFromGraph,
  exportGraphJSON,
  fnv1a,
  loadGraphStateFromStorage,
  parseGraphJSON,
  restoreGraph,
  saveGraphStateToStorage,
  snapshotGraph,
  stableStringify,
} from "./graphState";

// ── Fake cytoscape core (mutates a private store so restores are assertable) ─

interface SeedNode {
  id: string;
  x: number;
  y: number;
  selected?: boolean;
}
interface SeedEdge {
  id: string;
  source: string;
  target: string;
}

function fakeCy(seed: {
  nodes: SeedNode[];
  edges: SeedEdge[];
  zoom?: number;
  pan?: { x: number; y: number };
}) {
  const nodes = new Map<string, SeedNode>(seed.nodes.map((n) => [n.id, { ...n, selected: n.selected ?? false }]));
  const edges = [...seed.edges];
  const zoom = { v: seed.zoom ?? 1 };
  const pan = { x: seed.pan?.x ?? 0, y: seed.pan?.y ?? 0 };

  const nodeEl = (n: SeedNode) => ({
    id: () => n.id,
    position: (arg?: unknown) => {
      if (arg === "x") return n.x;
      if (arg === "y") return n.y;
      if (arg && typeof arg === "object") {
        const p = arg as { x: number; y: number };
        n.x = p.x;
        n.y = p.y;
        return n;
      }
      return { x: n.x, y: n.y };
    },
    select: () => {
      n.selected = true;
    },
    unselect: () => {
      n.selected = false;
    },
    stop: () => {},
  });

  const nodeElements = () => {
    const list = [...nodes.values()].map(nodeEl) as ReturnType<typeof nodeEl>[] & {
      unselect: () => void;
    };
    list.unselect = () => {
      for (const n of nodes.values()) n.selected = false;
    };
    return list;
  };

  const cy = {
    nodes: (selector?: string) =>
      selector === ":selected"
        ? [...nodes.values()].filter((n) => n.selected).map(nodeEl)
        : nodeElements(),
    edges: () =>
      edges.map((e) => ({
        id: () => e.id,
        source: () => ({ id: () => e.source }),
        target: () => ({ id: () => e.target }),
      })),
    zoom: (v?: number) => (v === undefined ? zoom.v : (zoom.v = v)),
    pan: (p?: { x: number; y: number }) =>
      p === undefined ? { x: pan.x, y: pan.y } : ((pan.x = p.x), (pan.y = p.y)),
    minZoom: () => 0.2,
    maxZoom: () => 3,
    stop: () => {},
    elements: () => ({ stop: () => {} }),
  };

  return {
    cy: cy as unknown,
    positions: () => [...nodes.values()].map((n) => ({ id: n.id, x: n.x, y: n.y })),
    zoom: () => zoom.v,
    pan: () => ({ x: pan.x, y: pan.y }),
    selectedIds: () => [...nodes.values()].filter((n) => n.selected).map((n) => n.id).sort(),
  };
}

const SNAPSHOT_GRAPH = {
  nodes: [
    { id: "ENT-2001", x: 12.5, y: 40 },
    { id: "ENT-2002", x: -8, y: 22 },
  ],
  edges: [{ id: "CE-1", source: "ENT-2001", target: "ENT-2002" }],
};

function makeCyState(selectedId?: string) {
  const f = fakeCy({
    nodes: SNAPSHOT_GRAPH.nodes.map((n, i) => ({ ...n, selected: n.id === selectedId && i >= 0 })),
    edges: SNAPSHOT_GRAPH.edges,
    zoom: 1.25,
    pan: { x: 30, y: -12 },
  });
  return f;
}

afterEach(() => {
  vi.useRealTimers();
  clearGraphStateStorage();
});

// ── Primitive determinism ─────────────────────────────────────────────

describe("fnv1a / stableStringify", () => {
  it("produces the canonical FNV-1a offset-basis vector for the empty input", () => {
    expect(fnv1a("")).toBe("811c9dc5");
    expect(fnv1a("abc")).toMatch(/^[0-9a-f]{8}$/);
  });

  it("is deterministic for a given input", () => {
    expect(fnv1a("the quick brown fox")).toBe(fnv1a("the quick brown fox"));
  });

  it("stably stringifies with sorted keys recursively", () => {
    expect(stableStringify({ b: 1, a: { d: 4, c: 3 } })).toBe('{"a":{"c":3,"d":4},"b":1}');
  });
});

describe("entitiesKey", () => {
  it("is order-invariant over node/edge sets", () => {
    const graph = {
      nodes: SNAPSHOT_GRAPH.nodes.map((n) => ({ id: n.id })),
      edges: SNAPSHOT_GRAPH.edges,
    };
    const reversed = {
      nodes: [...graph.nodes].reverse(),
      edges: [...graph.edges].reverse(),
    };
    expect(entitiesKeyFromGraph(graph)).toBe(entitiesKeyFromGraph(reversed));
  });

  it("changes when a node is added or removed", () => {
    const base = { nodes: [{ id: "A" }, { id: "B" }], edges: [] };
    const plus = { nodes: [{ id: "A" }, { id: "B" }, { id: "C" }], edges: [] };
    expect(entitiesKeyFor(base.nodes, base.edges)).not.toBe(entitiesKeyFor(plus.nodes, plus.edges));
  });

  it("changes when an edge is rewired", () => {
    const a = { nodes: [{ id: "A" }, { id: "B" }, { id: "C" }], edges: [{ id: "E", source: "A", target: "B" }] };
    const b = { nodes: [{ id: "A" }, { id: "B" }, { id: "C" }], edges: [{ id: "E", source: "A", target: "C" }] };
    expect(entitiesKeyFor(a.nodes, a.edges)).not.toBe(entitiesKeyFor(b.nodes, b.edges));
  });
});

// ── Snapshot ──────────────────────────────────────────────────────────

describe("snapshotGraph", () => {
  it("captures node positions, zoom, pan and selection deterministically", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00.000Z"));

    const cyA = makeCyState("ENT-2001");
    const cyB = makeCyState("ENT-2001");
    const snapA = snapshotGraph(cyA.cy as never);
    const snapB = snapshotGraph(cyB.cy as never);

    expect(snapA).toEqual(snapB);
    expect(snapA.savedAt).toBe("2026-01-01T00:00:00.000Z");
    expect(snapA.version).toBe(GRAPH_VIEW_STATE_VERSION);
    expect(snapA.zoom).toBe(1.25);
    expect(snapA.pan).toEqual({ x: 30, y: -12 });
    expect(snapA.selected).toEqual(["ENT-2001"]);
    expect(snapA.nodes).toEqual(
      expect.arrayContaining([
        { id: "ENT-2001", x: 12.5, y: 40 },
        { id: "ENT-2002", x: -8, y: 22 },
      ]),
    );
    expect(snapA.edges).toEqual([{ id: "CE-1", source: "ENT-2001", target: "ENT-2002" }]);
  });

  it("sorts emitted nodes/edges regardless of collection order", () => {
    const cy = fakeCy({
      nodes: [
        { id: "N2", x: 1, y: 2 },
        { id: "N1", x: 3, y: 4 },
      ],
      edges: [{ id: "E-B", source: "N2", target: "N1" }, { id: "E-A", source: "N1", target: "N2" }],
    });
    const snap = snapshotGraph(cy.cy as never);
    expect(snap.nodes.map((n) => n.id)).toEqual(["N1", "N2"]);
    expect(snap.edges.map((e) => e.id)).toEqual(["E-A", "E-B"]);
  });

  it("self-consistently fingerprints the captured topology", () => {
    const cy = makeCyState();
    const snap = snapshotGraph(cy.cy as never);
    expect(snap.entitiesKey).toBe(
      entitiesKeyFor(SNAPSHOT_GRAPH.nodes, SNAPSHOT_GRAPH.edges),
    );
  });
});

// ── Restore ───────────────────────────────────────────────────────────

describe("restoreGraph", () => {
  it("applies positions, zoom, pan and selection when the key matches", () => {
    // Source: the canonical view — both nodes selected, saved zoom/pan.
    const source = fakeCy({
      nodes: SNAPSHOT_GRAPH.nodes.map((n) => ({ ...n, selected: true })),
      edges: SNAPSHOT_GRAPH.edges,
      zoom: 1.25,
      pan: { x: 30, y: -12 },
    });
    const snap = snapshotGraph(source.cy as never);

    // Target: same topology, different (scrambled) view state.
    const target = fakeCy({
      nodes: SNAPSHOT_GRAPH.nodes.map((n, i) => ({ ...n, x: i, y: i * 2 })),
      edges: SNAPSHOT_GRAPH.edges,
      zoom: 0.5,
      pan: { x: 1, y: 1 },
    });
    const restored = restoreGraph(target.cy as never, snap, snap.entitiesKey);

    expect(restored).toEqual(["ENT-2001", "ENT-2002"]);
    expect(target.selectedIds()).toEqual(["ENT-2001", "ENT-2002"]);
    expect(target.positions()).toEqual(
      expect.arrayContaining([
        { id: "ENT-2001", x: 12.5, y: 40 },
        { id: "ENT-2002", x: -8, y: 22 },
      ]),
    );
    expect(target.zoom()).toBe(1.25);
    expect(target.pan()).toEqual({ x: 30, y: -12 });
  });

  it("clamps zoom into the canvas bounds", () => {
    const cy = fakeCy({ nodes: SNAPSHOT_GRAPH.nodes, edges: [], zoom: 1, pan: { x: 0, y: 0 } });
    const snap = {
      ...snapshotGraph(cy.cy as never),
      zoom: 99,
    };
    restoreGraph(cy.cy as never, snap, snap.entitiesKey);
    expect(cy.zoom()).toBe(3);
  });

  it("refuses to restore when the topology key does not match", () => {
    const cy = fakeCy({ nodes: SNAPSHOT_GRAPH.nodes, edges: [], zoom: 0.5, pan: { x: 1, y: 1 } });
    const snap = snapshotGraph(cy.cy as never);
    const before = {
      positions: cy.positions(),
      zoom: cy.zoom(),
      pan: cy.pan(),
      selected: cy.selectedIds(),
    };

    const otherKey = entitiesKeyFor([{ id: "ENT-OTHER" }], []);
    expect(restoreGraph(cy.cy as never, snap, otherKey)).toBeNull();
    expect(cy.positions()).toEqual(before.positions);
    expect(cy.zoom()).toBe(before.zoom);
    expect(cy.pan()).toEqual(before.pan);
    expect(cy.selectedIds()).toEqual(before.selected);
  });

  it("refuses mismatched versions", () => {
    const cy = makeCyState();
    const snap = { ...snapshotGraph(cy.cy as never), version: GRAPH_VIEW_STATE_VERSION + 1 };
    expect(restoreGraph(cy.cy as never, snap, snap.entitiesKey)).toBeNull();
  });
});

// ── Export / import round trip ────────────────────────────────────────

describe("exportGraphJSON / parseGraphJSON", () => {
  it("round-trips an identical snapshot", () => {
    const cy = makeCyState("ENT-2001");
    const snap = snapshotGraph(cy.cy as never);
    expect(parseGraphJSON(exportGraphJSON(snap))).toEqual(snap);
  });

  it("serializes with sorted keys", () => {
    const text = exportGraphJSON(snapshotGraph(makeCyState().cy as never));
    expect(text.indexOf('"checksum"')).toBeLessThan(text.indexOf('"format"'));
    expect(text.indexOf('"format"')).toBeLessThan(text.indexOf('"state"'));
    const stateStart = text.indexOf('"state"');
    expect(text.indexOf('"edges"', stateStart)).toBeLessThan(text.indexOf('"entitiesKey"', stateStart));
  });

  it("rejects malformed JSON", () => {
    expect(() => parseGraphJSON("{not json")).toThrow(/not valid JSON/);
  });

  it("rejects an unknown document format", () => {
    expect(() => parseGraphJSON('{"format":"something.else","checksum":"x","state":{}}')).toThrow(
      /unrecognized/,
    );
  });

  it("rejects a tampered checksum", () => {
    const cy = makeCyState();
    const text = exportGraphJSON(snapshotGraph(cy.cy as never));
    const tampered = text.replace(/"[0-9a-f]{8}"/, '"deadbeef"');
    expect(() => parseGraphJSON(tampered)).toThrow(/checksum mismatch/);
  });

  it("rejects schema drift (wrong version inside a valid envelope)", () => {
    const cy = makeCyState();
    const snap = snapshotGraph(cy.cy as never);
    const tampered = exportGraphJSON({ ...snap, version: GRAPH_VIEW_STATE_VERSION + 1 });
    expect(() => parseGraphJSON(tampered)).toThrow(/invalid graph-view schema/);
  });
});

// ── Hermetic storage ──────────────────────────────────────────────────

describe("graph-state storage", () => {
  it("persists and restores under the versioned key", () => {
    const cy = makeCyState("ENT-2001");
    const snap = snapshotGraph(cy.cy as never);
    expect(saveGraphStateToStorage(snap)).toBe(true);
    expect(window.localStorage.getItem(GRAPH_VIEW_STORAGE_KEY)).toBe(exportGraphJSON(snap));
    expect(loadGraphStateFromStorage()).toEqual(snap);
  });

  it("returns null when nothing is stored", () => {
    expect(loadGraphStateFromStorage()).toBeNull();
  });

  it("surfaces corrupt stored values as null instead of throwing", () => {
    window.localStorage.setItem(GRAPH_VIEW_STORAGE_KEY, "broken-{json");
    expect(loadGraphStateFromStorage()).toBeNull();
  });

  it("clears the stored view", () => {
    const cy = makeCyState();
    saveGraphStateToStorage(snapshotGraph(cy.cy as never));
    clearGraphStateStorage();
    expect(loadGraphStateFromStorage()).toBeNull();
  });
});