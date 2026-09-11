/**
 * Confidence presentation helpers (spec 004).
 *
 * Attribution / license
 * =====================
 * Source: vitni (Apache-2.0) `app/renderer/src/lib/confidence.ts` — the
 * `verified`/`unverified`/`asserted` vocabulary and label rule.
 *
 * Adaptation notes
 * ================
 * - COGNITIVE represents confidence as a numeric score (0..1), so the donor's
 *   string-switch is kept but a `confidenceFromScore` bucket mapping is added.
 * - Badge colours are plain hex (no Tailwind tokens) for Cytoscape/compatibility.
 */

export type Confidence = "verified" | "unverified" | "asserted";

export const CONFIDENCE_LABEL: Record<Confidence, string> = {
  verified: "Verified",
  unverified: "Unverified",
  asserted: "Asserted",
};

/** Rounded hex per confidence tier. */
export const CONFIDENCE_COLOR: Record<Confidence, string> = {
  verified: "#2e7d4f",
  unverified: "#8a5a00",
  asserted: "#7a7a7a",
};

export function confidenceFromScore(score: number): Confidence {
  if (score >= 0.7) return "verified";
  if (score >= 0.4) return "unverified";
  return "asserted";
}

export function confidenceLabel(score: number): string {
  return CONFIDENCE_LABEL[confidenceFromScore(score)];
}

export function confidenceColor(score: number): string {
  return CONFIDENCE_COLOR[confidenceFromScore(score)];
}

/** Format a donor-style confidence value deterministically (label + hex). */
export function formatConfidence(confidence: Confidence): { label: string; color: string } {
  return { label: CONFIDENCE_LABEL[confidence], color: CONFIDENCE_COLOR[confidence] };
}