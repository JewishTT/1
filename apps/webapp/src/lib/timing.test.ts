import { describe, expect, it } from "vitest";

import { burstiness, eventsPerDay, toEpochMs } from "./timing";

const T0 = "2026-01-01T00:00:00Z";

describe("toEpochMs", () => {
  it("parses ISO strings and passes through numbers", () => {
    expect(toEpochMs(T0)).toBe(Date.parse(T0));
    expect(toEpochMs(1234)).toBe(1234);
  });

  it("returns null for invalid input", () => {
    expect(toEpochMs("not-a-date")).toBeNull();
    expect(toEpochMs(Number.NaN)).toBeNull();
  });
});

describe("burstiness", () => {
  it("is null for fewer than 3 events", () => {
    expect(burstiness([T0])).toBeNull();
    expect(burstiness([T0, "2026-01-02T00:00:00Z"])).toBeNull();
    expect(burstiness([])).toBeNull();
  });

  it("returns ~0 for perfectly regular events", () => {
    const regular = [T0, "2026-01-02T00:00:00Z", "2026-01-03T00:00:00Z"];
    expect(burstiness(regular)).toBeCloseTo(0, 6);
  });

  it("is large for bursty clusters and >0 by definition", () => {
    const bursty = [
      T0,
      "2026-01-01T00:05:00Z",
      "2026-01-01T00:10:00Z",
      "2026-01-30T00:00:00Z",
    ];
    expect(burstiness(bursty)).toBeGreaterThan(1);
  });
});

describe("eventsPerDay", () => {
  it("is null for fewer than 2 events", () => {
    expect(eventsPerDay([T0])).toBeNull();
  });

  it("counts events across the spanned window", () => {
    const twoDays = [T0, "2026-01-02T00:00:00Z", "2026-01-03T00:00:00Z"];
    expect(eventsPerDay(twoDays)).toBeCloseTo(3 / 2, 6);
  });

  it("is null when every event shares one instant", () => {
    expect(eventsPerDay([T0, T0])).toBeNull();
  });
});