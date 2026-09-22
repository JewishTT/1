import { describe, expect, it } from "vitest";

import { MIN_DATES, buildTemporalSeriesFromTimeline } from "./tdaLayer";

describe("buildTemporalSeriesFromTimeline (TDA layer, I-3)", () => {
  it("returns null when fewer than MIN_DATES timestamps exist", () => {
    const result = buildTemporalSeriesFromTimeline([
      { observed_at: "2026-09-01T03:00:00Z" },
      { observed_at: "2026-09-02T04:00:00Z" },
    ]);
    expect(result.series).toBeNull();
    expect(result.startDay).toBeNull();
    expect(result.endDay).toBeNull();
  });

  it("buckets daily counts covering the observed span with zero-filled gaps", () => {
    const result = buildTemporalSeriesFromTimeline([
      { observed_at: "2026-09-01T03:00:00Z" },
      { observed_at: "2026-09-01T19:00:00Z" },
      { observed_at: "2026-09-03T08:00:00Z" },
    ]);
    expect(result.series).toEqual([2, 0, 1]);
    expect(result.startDay).toBe("2026-09-01");
    expect(result.endDay).toBe("2026-09-03");
  });

  it("ignores malformed timestamps instead of breaking the series", () => {
    const result = buildTemporalSeriesFromTimeline([
      { observed_at: "2026-09-01T03:00:00Z" },
      { observed_at: "2026-09-02T03:00:00Z" },
      { observed_at: "2026-09-03T03:00:00Z" },
      { observed_at: "not-a-date" },
      { observed_at: null },
    ]);
    expect(result.series).toEqual([1, 1, 1]);
    expect(MIN_DATES).toBe(3);
  });
});