/**
 * Link-presentation helpers for graph edges (spec 004).
 *
 * Attribution / license
 * =====================
 * Source: kafSIEM (Apache-2.0) `src/lib/incident-links.ts` — `formatLinkReason`
 * and `reportLag` are faithful ports; `linkColor` is a COGNITIVE addition.
 *
 * Adaptation notes
 * ================
 * - The SIEM-specific type imports (`Alert`, `IncidentLink`) are dropped; the
 *   reason formatter is generic (unknown prefixes fall back to the donor's
 *   underscore→space rule).
 * - `reportLag` is kept verbatim (pure Date.parse logic).
 */

/** Format a correlation/link reason token into a readable phrase. */
export function formatLinkReason(reason: string): string {
  if (reason.startsWith("shared_cve:")) {
    return `Shared ${reason.slice("shared_cve:".length)}`;
  }
  if (reason.startsWith("shared_entity:")) {
    return `Shared actor: ${reason.slice("shared_entity:".length)}`;
  }
  if (reason.startsWith("cross_source:jaccard:")) {
    return `Cross-source match (${reason.slice("cross_source:jaccard:".length)})`;
  }
  if (reason.startsWith("shared_country:")) {
    return `Shared geography (${reason.slice("shared_country:".length)})`;
  }
  if (reason.startsWith("geographic_spread:")) {
    return `Geographic spread (${reason.slice("geographic_spread:".length).replaceAll(",", ", ")})`;
  }
  return reason.replaceAll("_", " ");
}

/**
 * Edge colour per correlation kind.
 *
 * These are ROLES, not colours, since T135. A caller passes the tokens it read
 * from the cascade (`ui/tokens.ts:readLegacyNodeTokens`) and this module maps a
 * correlation kind onto the role that fits it:
 *
 *   possible_match    information — an analyst should look at it
 *   same_as / alias_of the accent — an identity claim the platform accepted
 *   event_followed_by / located_at warning — temporal and geographic claims
 *   mentioned_with    muted — the weakest claim kind, and it should read that way
 *   associated_with   neutral
 *
 * WHY ROLES. The previous form was a `Record<string, string>` of hex literals,
 * which meant the edge palette could not follow a theme and could not be
 * re-tuned without editing a `.ts` file. With roles, `styles/legacy/legacy-tokens.css`
 * owns the values and this file owns only the mapping.
 *
 * `kindColor` keeps the old signature working by resolving the legacy tokens
 * against `document.documentElement` — correct for the unmigrated surfaces, which
 * declare `--c-*` on `:root`.
 */
export type LinkRole =
  | "info"
  | "accent"
  | "warning"
  | "muted"
  | "neutral"
  | "danger";

export const LINK_ROLE_BY_KIND: Readonly<Record<string, LinkRole>> = {
  possible_match: "info",
  same_as: "accent",
  alias_of: "accent",
  event_followed_by: "warning",
  mentioned_with: "muted",
  associated_with: "neutral",
  located_at: "warning",
};

/** A resolved palette, as returned by `readLegacyNodeTokens`. */
export interface LinkPalette {
  accent: string;
  accentAlt: string;
  muted: string;
  border: string;
  danger: string;
  success: string;
}

/** Which role a correlation kind is drawn in. Unknown kinds are neutral. */
export function linkRole(kind: string): LinkRole {
  return LINK_ROLE_BY_KIND[kind] ?? "neutral";
}

/**
 * Resolve a kind's role to a colour using the caller's resolved palette.
 *
 * A palette is a parameter rather than a global read so the function stays pure
 * and testable: the edge colour for "same_as" is whatever the caller resolved
 * `--c-accent` to, which differs between themes and between jsdom and a browser.
 */
export function linkColor(kind: string, palette: LinkPalette): string {
  switch (linkRole(kind)) {
    case "info":
      return palette.accent;
    case "accent":
      return palette.success;
    case "warning":
      return palette.accentAlt;
    case "muted":
      return palette.muted;
    case "danger":
      return palette.danger;
    case "neutral":
    default:
      return palette.border;
  }
}

/**
 * Render how far behind the first report an entry came in: null for the first
 * report itself (or unparsable input), "+45m" / "+4.2h" / "+3d" after.
 */
export function reportLag(baselineIso: string, entryIso: string): string | null {
  const baseline = Date.parse(baselineIso);
  const entry = Date.parse(entryIso);
  if (Number.isNaN(baseline) || Number.isNaN(entry)) return null;
  const deltaMs = entry - baseline;
  if (deltaMs <= 0) return null;
  const minutes = deltaMs / 60_000;
  if (minutes < 60) return `+${Math.round(minutes)}m`;
  const hours = minutes / 60;
  if (hours < 48) return `+${Math.round(hours * 10) / 10}h`;
  return `+${Math.round(hours / 24)}d`;
}