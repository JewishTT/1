import { describe, expect, it } from "vitest";

import {
  CONFIDENCE_COLOR,
  CONFIDENCE_LABEL,
  confidenceColor,
  confidenceFromScore,
  confidenceLabel,
  formatConfidence,
} from "./confidence";

describe("confidenceFromScore", () => {
  it("buckets numeric scores deterministically", () => {
    expect(confidenceFromScore(0.9)).toBe("verified");
    expect(confidenceFromScore(0.7)).toBe("verified");
    expect(confidenceFromScore(0.5)).toBe("unverified");
    expect(confidenceFromScore(0.4)).toBe("unverified");
    expect(confidenceFromScore(0.1)).toBe("asserted");
  });
});

describe("presentation helpers", () => {
  it("labels scores consistently", () => {
    expect(confidenceLabel(0.9)).toBe("Verified");
    expect(confidenceLabel(0.5)).toBe("Unverified");
    expect(confidenceLabel(0.1)).toBe("Asserted");
  });

  it("exposes stable hex colours", () => {
    expect(confidenceColor(0.9)).toBe(CONFIDENCE_COLOR.verified);
    expect(confidenceColor(0.1)).toBe(CONFIDENCE_COLOR.asserted);
  });

  it("formats donor-style values", () => {
    expect(formatConfidence("verified")).toEqual({
      label: CONFIDENCE_LABEL.verified,
      color: CONFIDENCE_COLOR.verified,
    });
  });
});