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
 * - Badge colours are expressed as ROLES, not hex (T135). The donor carried "plain
 *   hex (no Tailwind tokens)"; those hex literals are now resolved by the caller
 *   from `styles/legacy/legacy-tokens.css`, so a confidence badge follows the
 *   theme instead of pinning a colour that matches nothing else on screen.
 */

export type Confidence = "verified" | "unverified" | "asserted";

export const CONFIDENCE_LABEL: Record<Confidence, string> = {
  verified: "Verified",
  unverified: "Unverified",
  asserted: "Asserted",
};

/**
 * The colour ROLE a confidence tier is drawn in.
 *
 * A role, not a value: the caller resolves it against the token stylesheet, which
 * is the only way the badge can follow light/dark and stay in step with every
 * other confidence display in the product.
 */
export type ConfidenceRole = "success" | "warning" | "muted";

export const CONFIDENCE_ROLE: Record<Confidence, ConfidenceRole> = {
  verified: "success",
  unverified: "warning",
  asserted: "muted",
};

/** The `--c-*` token each role resolves to. */
export const CONFIDENCE_TOKEN: Record<ConfidenceRole, string> = {
  success: "--c-success",
  warning: "--c-warning",
  muted: "--c-muted",
};

export function confidenceFromScore(score: number): Confidence {
  if (score >= 0.7) return "verified";
  if (score >= 0.4) return "unverified";
  return "asserted";
}

export function confidenceLabel(score: number): string {
  return CONFIDENCE_LABEL[confidenceFromScore(score)];
}

/** The token reference for a tier's colour, e.g. `var(--c-success)`. */
export function confidenceColorVar(confidence: Confidence): string {
  return `var(${CONFIDENCE_TOKEN[CONFIDENCE_ROLE[confidence]]})`;
}

/**
 * The colour a confidence badge is drawn in, for a numeric score.
 *
 * Buckets the score, then resolves the tier's role. A `var()` reference rather
 * than a resolved value, because the result goes straight into a DOM style where
 * CSS resolves the token — `components/LineageWalker.tsx` is the caller.
 */
export function confidenceColor(score: number): string {
  return confidenceColorVar(confidenceFromScore(score));
}

/**
 * Format a donor-style confidence value (label + colour role).
 *
 * The colour is a `var()` reference rather than a resolved value: this function is
 * called during render and its result goes straight into a DOM style, where CSS
 * resolves the token. Only a canvas consumer needs a resolved string, and that is
 * what `ui/tokens.ts:readLegacyNodeTokens` is for.
 */
export function formatConfidence(confidence: Confidence): { label: string; color: string } {
  return { label: CONFIDENCE_LABEL[confidence], color: confidenceColorVar(confidence) };
}