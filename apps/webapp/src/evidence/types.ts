import type { WorkspaceObjectKind } from "../workspace/types";
import type { RawFormat } from "./rawPayload";

/**
 * The evidence list's row vocabulary (§28).
 *
 * §28 names three things the list holds: Observation, Capture, Claim. They are
 * three different records with three different shapes, and the list is a
 * UNION of them rather than a normalised "evidence item" — because an item type
 * would flatten exactly the distinctions the workspace exists to keep (§99).
 *
 * `EvidenceRow.kind` is the discriminator, and it is typed as
 * `WorkspaceObjectKind`, so a row cannot carry a kind the global selection model
 * does not know how to route.
 */

export type EvidenceRowKind = Extract<WorkspaceObjectKind, "Observation" | "Capture" | "Claim">;

/** A row in the evidence list. Exactly one of the payloads is non-null. */
export interface EvidenceRow {
  kind: EvidenceRowKind;
  /** The platform's own identifier. This is what the selection carries. */
  ref: string;
  /** The primary label: the observation locator, the capture URI, the relation type. */
  label: string;
  /** ISO instant, or null when the platform reports none. */
  at: string | null;
  /** The source registry id, or null. */
  sourceId: string | null;
  /** Raw platform status, verbatim. Null ⇒ not reported. */
  status: string | null;
  /** The platform's media/format hint, verbatim. Null ⇒ not reported. */
  contentType: string | null;
  /** The raw payload, when the endpoint serves one for this record. */
  payload: EvidencePayload | null;
}

/**
 * A raw payload plus the locators that let a line be traced back to the
 * observation it came from (§30).
 *
 * `locators` is the whole feature. Without it the raw viewer is a text pane.
 */
export interface EvidencePayload {
  format: RawFormat;
  text: string;
  mediaType: string | null;
  digest: string | null;
  /**
   * Observation id → where its value lives in `text`. Empty means the platform
   * served the bytes without saying which observation produced them, and the
   * viewer says so on every line rather than picking one.
   */
  locators: EvidenceLocator[];
}

/** One locator. Field names mirror the platform's observation record. */
export interface EvidenceLocator {
  observationId: string;
  /** JSON Pointer into the payload, verbatim from the platform's `locator`. */
  pointer: string;
  /** Explicit line span when the platform reported one; otherwise derived. */
  lineStart: number | null;
  lineEnd: number | null;
  /** The locator exactly as the platform wrote it, for display. */
  raw: string;
}

/* ── Viewport tabs (§29) ─────────────────────────────────────────────── */

export const EVIDENCE_TABS = [
  "content",
  "structured",
  "metadata",
  "lineage",
  "processing",
  "revisions",
] as const;

export type EvidenceTab = (typeof EVIDENCE_TABS)[number];

export const EVIDENCE_TAB_LABELS: Readonly<Record<EvidenceTab, string>> = {
  content: "Content",
  structured: "Structured",
  metadata: "Metadata",
  lineage: "Lineage",
  processing: "Processing",
  revisions: "Revisions",
};

/** Which tabs can show something for a given row kind, and which cannot yet. */
export const EVIDENCE_TAB_SUPPORT: Readonly<
  Record<EvidenceTab, ReadonlyArray<EvidenceRowKind> | "all">
> = {
  content: "all",
  structured: "all",
  metadata: "all",
  lineage: ["Observation", "Capture", "Claim"],
  // §29's remaining three tabs need endpoints the platform does not expose:
  // a processing log, a revision list, and a per-capture record bundle. The
  // viewer states that rather than showing an empty pane.
  processing: [],
  revisions: [],
};

/* ── Sorting and searching ───────────────────────────────────────────── */

export type EvidenceSortKey = "at" | "kind" | "ref" | "sourceId";

export interface EvidenceSort {
  key: EvidenceSortKey;
  direction: "asc" | "desc";
}

/** The sortable value of a row for a given key. `null` means "not reported". */
export function sortValue(row: EvidenceRow, key: EvidenceSortKey): string | null {
  switch (key) {
    case "at":
      return row.at;
    case "kind":
      return row.kind;
    case "ref":
      return row.ref;
    case "sourceId":
      return row.sourceId;
  }
}

export interface EvidenceQuery {
  /** Free text over label, ref, content type and status. */
  text: string;
  /** Rows with no instant. Off by default: undated evidence is still evidence. */
  hideUndated: boolean;
  /** Row kinds. Empty means all three. */
  kinds: EvidenceRowKind[];
}

/**
 * Filter and sort the evidence list.
 *
 * `hideUndated` defaults OFF for the same reason `hideRejected` defaults off in
 * the store's `EvidenceFilter`: a record with no timestamp is still a record,
 * and hiding it by default would quietly change what the analyst is looking at.
 */
export function filterEvidence(rows: ReadonlyArray<EvidenceRow>, query: EvidenceQuery): EvidenceRow[] {
  const needle = query.text.trim().toLowerCase();
  return rows.filter((row) => {
    if (query.kinds.length > 0 && !query.kinds.includes(row.kind)) return false;
    if (query.hideUndated && row.at === null) return false;
    if (needle === "") return true;
    const haystack = `${row.label} ${row.ref} ${row.kind} ${row.contentType ?? ""} ${row.status ?? ""} ${row.sourceId ?? ""}`;
    return haystack.toLowerCase().includes(needle);
  });
}

/**
 * Sort. Undated rows sort LAST in both directions rather than pretending to be
 * at the epoch: "unknown when" is not "when nothing happened".
 */
export function sortEvidence(rows: ReadonlyArray<EvidenceRow>, sort: EvidenceSort): EvidenceRow[] {
  const sign = sort.direction === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    if (sort.key === "at") {
      if (a.at === null && b.at === null) return a.ref < b.ref ? -1 : a.ref > b.ref ? 1 : 0;
      if (a.at === null) return 1;
      if (b.at === null) return -1;
      return a.at < b.at ? -sign : a.at > b.at ? sign : 0;
    }
    const left = sortValue(a, sort.key) ?? "";
    const right = sortValue(b, sort.key) ?? "";
    const comparison = left < right ? -1 : left > right ? 1 : 0;
    return comparison * sign;
  });
}

/** Counts by row kind, for the list header. Every kind present, zero included. */
export function evidenceCounts(rows: ReadonlyArray<EvidenceRow>): Record<EvidenceRowKind, number> {
  const out: Record<EvidenceRowKind, number> = { Observation: 0, Capture: 0, Claim: 0 };
  for (const row of rows) out[row.kind] += 1;
  return out;
}