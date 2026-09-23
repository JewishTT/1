import { describe, expect, it } from "vitest";

import {
  deduceTimeline,
  networkStateAtTime,
  stateAtTime,
  timeBounds,
  TimelapseEvent,
  TimelapseNode,
} from "./timelapse";

const DAY = 86_400_000;
const T0 = Date.parse("2026-01-01T00:00:00Z");

const LOG: TimelapseEvent[] = [
  { entityId: "ENT-A", at: "2026-01-01T03:00:00Z", version: 1 },
  { entityId: "ENT-B", at: "2026-01-03T10:00:00Z", version: 1, confidence: 0.8 },
  { entityId: "ENT-A", at: "2026-01-06T22:00:00Z", version: 2, confidence: 0.9 },
];

describe("timeBounds", () => {
  it("returns [min, max] epoch-ms from observed_at", () => {
    expect(timeBounds(LOG)).toEqual([
      Date.parse("2026-01-01T03:00:00Z"),
      Date.parse("2026-01-06T22:00:00Z"),
    ]);
  });

  it("is null for an empty log", () => {
    expect(timeBounds([])).toBeNull();
  });

  it("is null when no event parses to a time", () => {
    expect(
      timeBounds([
        { entityId: "ENT-A", at: "not-a-timestamp" },
        { entityId: "ENT-B", at: "nope" },
      ]),
    ).toBeNull();
  });

  it("handles epoch-ms stamps", () => {
    expect(timeBounds([{ entityId: "ENT-A", at: T0 }])).toEqual([T0, T0]);
  });
});

describe("stateAtTime boundary semantics", () => {
  it("is active for an observation strictly before T", () => {
    const state = stateAtTime(LOG, "2026-01-02T00:00:00Z");
    expect(state).toMatchObject({ active: true, lastSeen: "2026-01-01T03:00:00Z", version: 1 });
  });

  it("includes an observation exactly AT T (inclusive ≤)", () => {
    const state = stateAtTime(LOG, "2026-01-03T10:00:00Z");
    expect(state).toMatchObject({ active: true, lastSeen: "2026-01-03T10:00:00Z" });
  });

  it("is unknown (inactive, no lastSeen) when nothing is ≤ T", () => {
    expect(stateAtTime(LOG, "2025-12-31T00:00:00Z")).toEqual({
      active: false,
      lastSeen: null,
    });
  });

  it("is unknown for an empty log at any T", () => {
    expect(stateAtTime([], "2026-01-05T00:00:00Z")).toEqual({
      active: false,
      lastSeen: null,
    });
  });

  it("is unknown when T itself has no timestamp", () => {
    expect(stateAtTime(LOG, "not-a-time")).toEqual({ active: false, lastSeen: null });
  });

  it("replays the last applied event's version and confidence", () => {
    const state = stateAtTime(LOG, "2026-01-07T00:00:00Z");
    expect(state).toMatchObject({ active: true, version: 2, confidence: 0.9 });
  });

  it("drops observations strictly after T", () => {
    const state = stateAtTime(LOG, "2026-01-04T00:00:00Z");
    expect(state.lastSeen).toBe("2026-01-03T10:00:00Z");
    expect(state.version).toBe(1);
  });
});

describe("stateAtTime determinism", () => {
  it("yields the same state regardless of input order", () => {
    const shuffled = [LOG[2], LOG[0], LOG[1]];
    const original = stateAtTime(LOG, "2026-01-07T00:00:00Z");
    const replay = stateAtTime(shuffled, "2026-01-07T00:00:00Z");
    expect(replay).toEqual(original);
  });

  it("breaks timestamp ties by stable entity id", () => {
    const events: TimelapseEvent[] = [
      { entityId: "ENT-Z", at: T0, version: 9 },
      { entityId: "ENT-A", at: T0, version: 3 },
    ];
    // Both at T0; deterministic sort (id asc) means the log position of the
    // last applied event is the max id — independent of input order.
    const direct = stateAtTime(events, T0);
    const reversed = stateAtTime([events[1], events[0]], T0);
    expect(direct).toEqual(reversed);
    expect(reversed.version).toBe(9);
  });
});

describe("networkStateAtTime", () => {
  const nodes: TimelapseNode[] = [
    { id: "ENT-A", label: "A", seasons: ["2026-01-01T03:00:00Z"] },
    { id: "ENT-B", label: "B", seasons: ["2026-01-03T10:00:00Z"] },
    { id: "ENT-SILENT", label: "Silent", seasons: [] },
  ];
  const edges = [
    { id: "E1", source: "ENT-A", target: "ENT-B", kind: "possible_match" },
    { id: "E2", source: "ENT-A", target: "ENT-SILENT", kind: "possible_match" },
    { id: "E3", source: "ENT-A", target: "ENT-B", kind: "assertion", at: "2026-01-05T00:00:00Z" },
  ];

  it("keeps nodes with a season ≤ T and drops unknowns", () => {
    const state = networkStateAtTime(nodes, edges, "2026-01-02T00:00:00Z");
    expect(state.aliveNodeCount).toBe(1);
    expect(state.nodes.map((n) => n.id)).toEqual(["ENT-A"]);
  });

  it("keeps the edge only when both endpoints are alive", () => {
    const state = networkStateAtTime(nodes, edges, "2026-01-04T00:00:00Z");
    expect(state.aliveNodeCount).toBe(2);
    expect(state.aliveEdgeCount).toBe(1);
    expect(state.edges.map((e) => e.id)).toEqual(["E1"]);
  });

  it("honours an explicit edge stamp", () => {
    // E3's own stamp (Jan 05) is later than T; endpoints alive but edge not yet.
    const state = networkStateAtTime(nodes, edges, "2026-01-04T00:00:00Z");
    expect(state.aliveEdgeCount).toBe(1);
    const later = networkStateAtTime(nodes, edges, "2026-01-05T00:00:00Z");
    expect(later.aliveEdgeCount).toBe(2);
  });

  it("is empty (unknown) when T has no timestamp", () => {
    const state = networkStateAtTime(nodes, edges, "nope");
    expect(state).toEqual({ nodes: [], edges: [], aliveNodeCount: 0, aliveEdgeCount: 0 });
  });

  it("preserves input order and is deterministic", () => {
    const s1 = networkStateAtTime(nodes, edges, "2026-01-07T00:00:00Z");
    const s2 = networkStateAtTime([...nodes].reverse(), edges, "2026-01-07T00:00:00Z");
    // documented contract: input order is preserved, so reversed input
    // reverses the (still deterministic) output order
    expect(s1.nodes.map((n) => n.id)).toEqual(["ENT-A", "ENT-B"]);
    expect(s2.nodes.map((n) => n.id)).toEqual(["ENT-B", "ENT-A"]);
    expect(s2.edges).toEqual(s1.edges);
  });
});

describe("deduceTimeline", () => {
  it("emits sorted distinct frames with cumulative counts", () => {
    const frames = deduceTimeline(LOG);
    expect(frames.map((f) => f.atMs)).toEqual([
      Date.parse("2026-01-01T03:00:00Z"),
      Date.parse("2026-01-03T10:00:00Z"),
      Date.parse("2026-01-06T22:00:00Z"),
    ]);
    expect(frames[0]).toMatchObject({ active: 1, events: 1 });
    expect(frames[1]).toMatchObject({ active: 2, events: 2 });
    expect(frames[2]).toMatchObject({ active: 2, events: 3 });
    expect(frames.every((f) => f.t === new Date(f.atMs).toISOString())).toBe(true);
  });

  it("is empty without any parseable stamps", () => {
    expect(deduceTimeline([{ entityId: "ENT-A", at: "?" }])).toEqual([]);
  });

  it("is deterministic — same log, same frames", () => {
    expect(deduceTimeline([LOG[1], LOG[2], LOG[0]])).toEqual(deduceTimeline(LOG));
  });

  it("spans the play axis from min to max over a realistic window", () => {
    const events = Array.from({ length: 4 }, (_, i) => ({
      entityId: `ENT-${i}`,
      at: T0 + i * DAY,
    }));
    const frames = deduceTimeline(events);
    expect(frames.length).toBe(4);
    expect(frames[frames.length - 1].active).toBe(4);
  });
});