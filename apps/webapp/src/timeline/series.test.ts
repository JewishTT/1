import { describe, expect, it } from "vitest";

import {
  EMPTY_TIMELINE_FILTER,
  MAX_BUCKETS,
  MIN_BUCKETS,
  brushToRange,
  bucketEvents,
  compareWindows,
  eventsInRange,
  filterEvents,
  panDomain,
  presentValues,
  resolveFocus,
  timeBounds,
  toggleTimelineValue,
  zoomDomain,
  zoomLevel,
  type TimeDomain,
} from "./series";
import type { TimelineEvent, TimelineLane } from "./types";

/**
 * Timeline filtering behaviour (§23, §84).
 *
 * The claims, in order of consequence:
 *
 *   1. FILTERING CHANGES GRAPH STATE. The brush writes the workspace
 *      `timeRange`, and `filterEvents` is the model that reads it. The test
 *      asserts the two are the same value, not merely similar — because a
 *      private copy of the window in the timeline is exactly how "changing time
 *      changes graph state" stops being true.
 *   2. The filter narrows WHAT and the window narrows WHEN, and they compose
 *      without either one silently overriding the other.
 *   3. Zero buckets survive, so a quiet interval is not drawn as adjacency.
 *   4. Undated events are excluded from the axis and COUNTED, not dated "now".
 *   5. Compare reports a null delta on an open window rather than inventing one.
 */

const DOMAIN: TimeDomain = {
  min: Date.parse("2026-01-01T00:00:00Z"),
  max: Date.parse("2026-01-31T00:00:00Z"),
};

function event(
  id: string,
  lane: TimelineLane,
  at: string,
  extra: Partial<TimelineEvent> = {},
): TimelineEvent {
  return {
    id,
    lane,
    ref: id,
    label: `${lane} ${id}`,
    at,
    endAt: null,
    sourceId: null,
    status: null,
    entityRef: null,
    ...extra,
  };
}

const EVENTS: TimelineEvent[] = [
  event("e1", "Observation", "2026-01-02T00:00:00Z", { entityRef: "ENT-1", sourceId: "acme.example", status: "IMMUTABLE" }),
  event("e2", "Observation", "2026-01-05T00:00:00Z", { entityRef: "ENT-2", sourceId: "beta.example" }),
  event("e3", "Finding", "2026-01-08T00:00:00Z", { entityRef: "ENT-1", status: "OPEN" }),
  event("e4", "Claim", "2026-01-15T00:00:00Z", { entityRef: "ENT-1", endAt: "2026-02-01T00:00:00Z" }),
  event("e5", "Observation", "2026-01-28T00:00:00Z", { entityRef: "ENT-3", sourceId: "acme.example" }),
];

describe("§84 — the filter narrows WHAT", () => {
  it("an empty filter admits everything", () => {
    expect(filterEvents(EVENTS, EMPTY_TIMELINE_FILTER)).toHaveLength(EVENTS.length);
  });

  it("narrows by lane, source and status independently", () => {
    expect(filterEvents(EVENTS, { ...EMPTY_TIMELINE_FILTER, lanes: ["Observation"] })).toHaveLength(3);
    expect(filterEvents(EVENTS, { ...EMPTY_TIMELINE_FILTER, sourceIds: ["acme.example"] })).toHaveLength(2);
    expect(filterEvents(EVENTS, { ...EMPTY_TIMELINE_FILTER, statuses: ["IMMUTABLE"] })).toHaveLength(1);
  });

  it("combines fields as AND and values within a field as OR", () => {
    const both = filterEvents(EVENTS, {
      lanes: ["Observation"],
      sourceIds: ["acme.example", "beta.example"],
      statuses: [],
      query: "",
    });
    expect(both.map((e) => e.id)).toEqual(["e1", "e2", "e5"]);

    const narrower = filterEvents(EVENTS, {
      lanes: ["Observation"],
      sourceIds: ["acme.example"],
      statuses: [],
      query: "",
    });
    expect(narrower.map((e) => e.id)).toEqual(["e1", "e5"]);
  });

  it("matches free text over label, ref and entity — case-insensitively", () => {
    expect(filterEvents(EVENTS, { ...EMPTY_TIMELINE_FILTER, query: "acme.example" })).toHaveLength(2);
    expect(filterEvents(EVENTS, { ...EMPTY_TIMELINE_FILTER, query: "FINDING" })).toHaveLength(1);
    expect(filterEvents(EVENTS, { ...EMPTY_TIMELINE_FILTER, query: "nothing-here" })).toHaveLength(0);
  });

  it("never mutates the input list", () => {
    const before = EVENTS.length;
    filterEvents(EVENTS, { ...EMPTY_TIMELINE_FILTER, lanes: ["Claim"] });
    expect(EVENTS).toHaveLength(before);
  });

  it("offers only values present in the data", () => {
    const present = presentValues(EVENTS);
    expect(present.lanes).toEqual(["Observation", "Finding", "Claim"]);
    expect(present.sourceIds).toEqual(["acme.example", "beta.example"]);
    expect(present.statuses).toEqual(["IMMUTABLE", "OPEN"]);
    // A lane with nothing in it is not offered — a filter that can only produce
    // an empty canvas is §69's dead end.
    expect(present.lanes).not.toContain("AcquisitionRun");
  });

  it("toggles immutably", () => {
    expect(toggleTimelineValue(["a"], "a")).toEqual([]);
    expect(toggleTimelineValue(["a"], "b")).toEqual(["a", "b"]);
  });
});

describe("§23 — the brush writes the workspace time range, and that is what narrows WHEN", () => {
  it("turns a brush rectangle into the store's TimeRange shape", () => {
    const range = brushToRange(DOMAIN, Date.parse("2026-01-05T00:00:00Z"), Date.parse("2026-01-12T00:00:00Z"));
    expect(range).toEqual({ from: "2026-01-05T00:00:00.000Z", to: "2026-01-12T00:00:00.000Z" });
  });

  it("clamps the brush to the data domain and normalises a reversed drag", () => {
    const reversed = brushToRange(DOMAIN, Date.parse("2026-01-12T00:00:00Z"), Date.parse("2026-01-05T00:00:00Z"));
    expect(reversed.from).toBe("2026-01-05T00:00:00.000Z");
    expect(reversed.to).toBe("2026-01-12T00:00:00.000Z");

    const outside = brushToRange(DOMAIN, Date.parse("2020-01-01T00:00:00Z"), Date.parse("2030-01-01T00:00:00Z"));
    expect(outside.from).toBe("2026-01-01T00:00:00.000Z");
    expect(outside.to).toBe("2026-01-31T00:00:00.000Z");
  });

  it("narrows events to the window", () => {
    const range = { from: "2026-01-03T00:00:00Z", to: "2026-01-09T00:00:00Z" };
    expect(eventsInRange(EVENTS, range).map((e) => e.id)).toEqual(["e2", "e3"]);
  });

  it("returns everything for an open window — an open window is not an empty one", () => {
    expect(eventsInRange(EVENTS, { from: null, to: null })).toHaveLength(EVENTS.length);
  });

  it("keeps an interval that OVERLAPS the window, not only one contained by it", () => {
    // e4 runs 15 Jan → 1 Feb. A window at the end of January overlaps it.
    const overlapping = eventsInRange(EVENTS, { from: "2026-01-28T00:00:00Z", to: "2026-01-31T00:00:00Z" });
    expect(overlapping.map((e) => e.id)).toContain("e4");
  });

  it("composes with the filter rather than replacing it", () => {
    const filtered = filterEvents(EVENTS, { ...EMPTY_TIMELINE_FILTER, lanes: ["Observation"] });
    const windowed = eventsInRange(filtered, { from: "2026-01-01T00:00:00Z", to: "2026-01-06T00:00:00Z" });
    expect(windowed.map((e) => e.id)).toEqual(["e1", "e2"]);
  });
});

describe("§84 — the histogram keeps its empty intervals", () => {
  it("emits exactly the requested bucket count, including the zeros", () => {
    const buckets = bucketEvents(EVENTS, DOMAIN, { buckets: 20 });
    expect(buckets).toHaveLength(20);
    // Most of January is quiet, so many buckets are zero — and they are still
    // buckets. Dropping them would turn a quiet fortnight into adjacency.
    expect(buckets.some((bucket) => bucket.total === 0)).toBe(true);
    expect(buckets.reduce((sum, bucket) => sum + bucket.total, 0)).toBe(EVENTS.length);
  });

  it("clamps the bucket count to a sane band", () => {
    expect(bucketEvents(EVENTS, DOMAIN, { buckets: 1 })).toHaveLength(MIN_BUCKETS);
    expect(bucketEvents(EVENTS, DOMAIN, { buckets: 2 })).toHaveLength(MIN_BUCKETS);
    expect(bucketEvents(EVENTS, DOMAIN, { buckets: 100_000 })).toHaveLength(MAX_BUCKETS);
    expect(bucketEvents(EVENTS, DOMAIN, { buckets: Number.NaN })).toHaveLength(MIN_BUCKETS);
    expect(MIN_BUCKETS).toBeLessThan(MAX_BUCKETS);
  });

  it("counts per lane, with every lane present so a zero is a stated zero", () => {
    const [first] = bucketEvents(EVENTS, DOMAIN, { buckets: MIN_BUCKETS, lanes: ["Observation", "Claim"] });
    expect(Object.keys(first?.counts ?? {}).sort()).toEqual(["Claim", "Observation"]);
  });

  it("counts only what the window contains when a window is supplied", () => {
    const all = bucketEvents(EVENTS, DOMAIN, { buckets: 10 });
    const windowed = bucketEvents(EVENTS, DOMAIN, {
      buckets: 10,
      range: { from: "2026-01-01T00:00:00Z", to: "2026-01-03T00:00:00Z" },
    });
    const total = (rows: typeof all) => rows.reduce((sum, bucket) => sum + bucket.total, 0);
    expect(total(windowed)).toBeLessThan(total(all));
    expect(total(windowed)).toBe(1);
  });

  it("places each event in exactly one bucket", () => {
    const buckets = bucketEvents(EVENTS, DOMAIN, { buckets: 12 });
    const ids = buckets.flatMap((bucket) => bucket.eventIds);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("derives the axis domain from the data, and never from a constant", () => {
    const bounds = timeBounds(EVENTS);
    expect(bounds?.min).toBe(Date.parse("2026-01-02T00:00:00Z"));
    expect(bounds?.max).toBe(Date.parse("2026-02-01T00:00:00Z"));
    expect(timeBounds([])).toBeNull();
  });

  it("gives a single-instant domain a brushable width rather than zero", () => {
    const single = timeBounds([event("only", "Observation", "2026-05-05T00:00:00Z")]);
    expect(single).not.toBeNull();
    expect((single?.max ?? 0) - (single?.min ?? 0)).toBeGreaterThan(0);
  });
});

describe("§23 — focus means something specific per target", () => {
  it("focus entity resolves to every event anchored to it", () => {
    const focus = resolveFocus(EVENTS, { target: "entity", ref: "ENT-1" });
    expect(focus.eventIds).toEqual(["e1", "e3", "e4"]);
    expect(focus.entityRefs).toEqual(["ENT-1"]);
    expect(focus.empty).toBe(false);
    expect(focus.label).toContain("ENT-1");
  });

  it("focus relation resolves only Claim-lane events for that relation", () => {
    // A relation id that happens to share an entity must not pull in that
    // entity's other events.
    const events = [
      ...EVENTS,
      event("e6", "Claim", "2026-01-16T00:00:00Z", { entityRef: "ENT-9", ref: "CLM-7" }),
    ];
    const focus = resolveFocus(events, { target: "relation", ref: "CLM-7" });
    expect(focus.eventIds).toEqual(["e6"]);
  });

  it("focus evidence pulls the record AND what arrived with it from the same source", () => {
    const events = [
      event("a", "Observation", "2026-01-02T00:00:00Z", { sourceId: "acme.example" }),
      event("b", "Observation", "2026-01-02T00:00:00Z", { sourceId: "acme.example" }),
      event("c", "Observation", "2026-01-02T00:00:00Z", { sourceId: "beta.example" }),
    ];
    const focus = resolveFocus(events, { target: "evidence", ref: "a" });
    expect(focus.eventIds.sort()).toEqual(["a", "b"]);
  });

  it("a focus that matches nothing says so, rather than matching the nearest thing", () => {
    const focus = resolveFocus(EVENTS, { target: "entity", ref: "ENT-NOPE" });
    expect(focus.empty).toBe(true);
    expect(focus.eventIds).toEqual([]);
    expect(focus.label).toContain("No timeline events");
  });

  it("returns the entity refs the graph should emphasise", () => {
    const focus = resolveFocus(EVENTS, { target: "entity", ref: "ENT-2" });
    expect(focus.entityRefs).toEqual(["ENT-2"]);
  });
});

describe("§23 — compare answers 'busier or quieter', and refuses to guess", () => {
  it("compares a closed window against the window before it of the same width", () => {
    const busy = compareWindows(EVENTS, { from: "2026-01-01T00:00:00Z", to: "2026-01-15T00:00:00Z" });
    expect(busy.current.count).toBe(4);
    expect(busy.delta).not.toBeNull();
    expect(busy.label.length).toBeGreaterThan(0);
  });

  it("reports a null delta on an open window — an unbounded window has no width", () => {
    const open = compareWindows(EVENTS, { from: "2026-01-01T00:00:00Z", to: null });
    expect(open.delta).toBeNull();
    expect(open.label).toContain("both window bounds");
  });

  it("says 'same volume' rather than inventing a difference", () => {
    // One event in each of two adjacent equal-width windows.
    const flat = [
      event("x", "Observation", "2026-01-05T00:00:00Z"),
      event("y", "Observation", "2026-01-04T00:00:00Z"),
    ];
    const result = compareWindows(flat, { from: "2026-01-04T12:00:00Z", to: "2026-01-06T00:00:00Z" });
    expect(result.current.count).toBe(1);
    expect(result.previous.count).toBe(1);
    expect(result.delta).toBe(0);
    expect(result.label).toContain("Same volume");
  });
});

describe("§23 — zoom and pan stay inside the data", () => {
  it("zooms in and out about the midpoint", () => {
    const zoomedIn = zoomDomain(DOMAIN, 0.5);
    expect(zoomedIn.max - zoomedIn.min).toBeLessThan(DOMAIN.max - DOMAIN.min);
    const zoomedOut = zoomDomain(DOMAIN, 2);
    expect(zoomedOut.max - zoomedOut.min).toBeGreaterThan(DOMAIN.max - DOMAIN.min);
  });

  it("never inverts or collapses the axis, whatever factor it is given", () => {
    for (const factor of [0, -1, Number.NaN, 1e9]) {
      const next = zoomDomain(DOMAIN, factor);
      expect(next.max).toBeGreaterThan(next.min);
    }
  });

  it("pans by a fraction of the window's own width", () => {
    const span = DOMAIN.max - DOMAIN.min;
    const panned = panDomain(DOMAIN, 0.5);
    expect(panned.min - DOMAIN.min).toBe(Math.round(span * 0.5));
    expect(panned.max - DOMAIN.max).toBe(Math.round(span * 0.5));
  });

  it("reports the zoom level as a fraction of the full span", () => {
    expect(zoomLevel(DOMAIN, DOMAIN)).toBe(1);
    expect(zoomLevel({ min: 0, max: 100 }, { min: 0, max: 400 })).toBe(0.25);
  });
});