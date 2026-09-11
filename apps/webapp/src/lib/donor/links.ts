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

/** Stable hex colour per correlation kind (fallback: neutral grey). */
const LINK_COLORS: Record<string, string> = {
  possible_match: "#7aa2c2",
  same_as: "#2e7d4f",
  alias_of: "#2e7d4f",
  event_followed_by: "#8a5a00",
  mentioned_with: "#6b5b95",
  associated_with: "#7a7a7a",
  located_at: "#b34700",
};

export function linkColor(kind: string): string {
  return LINK_COLORS[kind] ?? "#888888";
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