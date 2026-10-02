import { describe, expect, it } from "vitest";

import {
  CONFIDENCE_LABEL,
  CONFIDENCE_ROLE,
  CONFIDENCE_TOKEN,
  confidenceColorVar,
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

  it("maps every tier to a colour ROLE, and every role to a token", () => {
    // The point of T135: a confidence badge's colour is a token reference, so it
    // follows the theme and cannot drift away from every other confidence display
    // in the product. Asserting the ROLE→TOKEN mapping is what pins that; the
    // previous form asserted three hex literals that nothing else in the codebase
    // shared.
    expect(CONFIDENCE_ROLE.verified).toBe("success");
    expect(CONFIDENCE_ROLE.unverified).toBe("warning");
    expect(CONFIDENCE_ROLE.asserted).toBe("muted");

    expect(confidenceColorVar("verified")).toBe(`var(${CONFIDENCE_TOKEN.success})`);
    expect(confidenceColorVar("unverified")).toBe(`var(${CONFIDENCE_TOKEN.warning})`);
    expect(confidenceColorVar("asserted")).toBe(`var(${CONFIDENCE_TOKEN.muted})`);
  });

  it("emits no hex literal, only var() references", () => {
    for (const tier of ["verified", "unverified", "asserted"] as const) {
      expect(confidenceColorVar(tier)).toMatch(/^var\(--c-[a-z0-9-]+\)$/);
      expect(confidenceColorVar(tier)).not.toContain("#");
    }
  });

  it("formats donor-style values", () => {
    expect(formatConfidence("verified")).toEqual({
      label: CONFIDENCE_LABEL.verified,
      color: confidenceColorVar("verified"),
    });
  });
});