import type { WorkStatus } from "../ui/status";
import type { WorkspaceObjectKind } from "../workspace/types";

/**
 * Objects table vocabulary (§25, §26, §27, §34, §35, §98, §99).
 *
 * ONE TABLE, FILTERED — NOT FIVE TABLES. §25 asks for a single table
 * workspace covering Entity / Observation / Claim / Finding / Capture, narrowed
 * by a type filter. So `ObjectRow` is a DISCRIMINATED UNION keyed on `kind`,
 * not a normalised row with nullable columns for everything: a row that reads as
 * a Claim cannot be read as a Finding, because the compiler says so. A single
 * table with a filter is a different thing from five tables and the difference
 * is this type.
 *
 * §99, precisely: every field below is either a platform identifier, a value the
 * platform reported, or an explicit `null` meaning *not reported*. Nothing is
 * derived, defaulted or invented here. In particular:
 *
 *   - `statusWord` is a projection of `status` onto the closed §92 vocabulary and
 *     never replaces `status`, which stays verbatim beside it.
 *   - a `Finding` row's `title` is the platform's `why_detected`; a Finding has
 *     no separate name in `FindingView`, and minting one would be a model the
 *     platform does not have.
 *   - `analystNotes` is `null` on every Finding today because no endpoint serves
 *     analyst notes against a finding. It is typed so the column exists and the
 *     gap is a value, not a missing field.
 */

/** The five kinds §25 puts behind one type filter. */
export type ObjectRowKind = Extract<
  WorkspaceObjectKind,
  "Entity" | "Observation" | "Claim" | "Finding" | "Capture"
>;

/** Canvas order. Entity first (the anchor), then the records, then the result. */
export const OBJECT_ROW_KINDS: ReadonlyArray<ObjectRowKind> = [
  "Entity",
  "Observation",
  "Claim",
  "Finding",
  "Capture",
];

/** Whether a kind is on screen. Empty means "all five" (§26). */
export function kindsFromSelection(selected: ReadonlyArray<WorkspaceObjectKind>): ObjectRowKind[] {
  const out: ObjectRowKind[] = [];
  for (const kind of OBJECT_ROW_KINDS) {
    if (selected.includes(kind)) out.push(kind);
  }
  return out;
}

/* ── Row base ──────────────────────────────────────────────────────────── */

export interface ObjectRowBase {
  kind: ObjectRowKind;
  /** The platform's own identifier. This is what the global selection carries. */
  id: string;
  /**
   * The primary label — what the row is called in words. An Observation has no
   * name in the platform, so this is its URI; a Claim has no name, so this is
   * its predicate with its participants. Never a minted name.
   */
  label: string;
  /** A secondary line under the label: the kind's own short identity. */
  sublabel: string | null;
  /** Raw platform status, verbatim. Null ⇒ the platform reports none. */
  status: string | null;
  /** That status projected onto the closed §92 vocabulary. Never replaces `status`. */
  statusWord: WorkStatus;
  /** The row's primary instant, or null when the platform reports none. */
  at: string | null;
  /**
   * Every instant the row reports. Empty means *unknown at any instant*, which
   * is different from "no time" — the temporal facet treats it that way.
   */
  instants: string[];
  /** Source registry ids the platform attributes to this row. */
  sourceIds: string[];
  /** Evidence records the platform counts for this row. 0 is a real 0. */
  evidenceCount: number;
  /** Claims resting on / made by this row, as the platform counts them. */
  claimCount: number;
  /**
   * Precomputed free-text haystack. Built once at projection time so filtering
   * does not re-stringify every row on every keystroke.
   */
  searchText: string;
}

/* ── Entity (§6, §19) ──────────────────────────────────────────────────── */

export interface EntityRow extends ObjectRowBase {
  kind: "Entity";
  /** `canonical_identity` verbatim. An empty object means the platform sent none. */
  canonical: Record<string, string>;
  aliases: string[];
  /** Relationship rows as the platform reports them: `{ type, target }`. */
  relationships: Array<{ type: string; target: string; status: string | null }>;
  /** Materialisation projection: continuity, version, first/last seen. */
  continuity: string | null;
  firstSeen: string | null;
  lastSeen: string | null;
  historyDepth: number | null;
}

/* ── Observation (§33) ─────────────────────────────────────────────────── */

export interface ObservationRow extends ObjectRowBase {
  kind: "Observation";
  /**
   * The address the record was read from. An observation has no human name in
   * the platform, so the URI is its face — and `label` is derived from it.
   */
  uri: string | null;
  captureId: string | null;
  locator: string | null;
  recordDigest: string | null;
  contentType: string | null;
  runtimeProducer: string | null;
  immutable: boolean;
  /** The entity whose timeline/evidence arrays named this observation. */
  anchorEntityIds: string[];
}

/* ── Claim (§34) ───────────────────────────────────────────────────────── */

/**
 * A claim is NOT a boolean fact. It is a relation with a predicate, ordered
 * participants, a temporal scope, its own lifecycle, a validation grade, an
 * admission state, evidence, a derivation trail and a projection. Every one of
 * those is a field here, so the table and the detail pane can show that
 * structure rather than flattening it to a tick.
 */
export interface ClaimRow extends ObjectRowBase {
  kind: "Claim";
  /** The asserted predicate — `relation_type` in the platform's own vocabulary. */
  predicate: string;
  /** Ordered participants. Refs, never names: a claim names refs it asserts about. */
  subjectRef: string;
  objectRef: string;
  roleBindings: Array<{ role: string; memberRef: string }>;
  /** Temporal scope of the assertion. A null bound is open, not zero. */
  validFrom: string | null;
  validTo: string | null;
  /** Observation / published / known: distinct from validity, all distinct here. */
  observedAt: string | null;
  publishedAt: string | null;
  knownFrom: string | null;
  knownUntil: string | null;
  /** Validation: platform-reported grade and confidence. Null ⇒ not reported. */
  evidenceGrade: string | null;
  confidence: number | null;
  /** Evidence: the observations this claim rests on. */
  observationRefs: string[];
  /** Derivation: which extraction / normalization / ontology version produced it. */
  extractionVersion: string | null;
  normalizationVersion: string | null;
  ontologyVersion: string | null;
  contradicts: string[];
  supersedes: string | null;
}

/* ── Finding (§35) ─────────────────────────────────────────────────────── */

/**
 * A finding is an ANALYTICAL RESULT, not a row. §35 names what it must be
 * readable as: title, summary, status, the claims / evidence / entities
 * supporting it, its timeline, its sources, analyst notes, and a route to the
 * underlying evidence. Each of those is a field or a reference list here, so the
 * table column and the detail pane can carry them.
 */
export interface FindingRow extends ObjectRowBase {
  kind: "Finding";
  /** `why_detected` — the platform's own account of why this fired. */
  summary: string;
  /** Whether the finding's evidence resolves. The platform's own boolean. */
  evidenceResolves: boolean;
  /** Claims this finding rests on. */
  supportingClaimRefs: string[];
  /** Observations this finding rests on, with the URI each one carries. */
  observationRefs: Array<{ observationId: string; uri: string; immutable: boolean; at: string | null }>;
  /** Entities this finding concerns, as far as the records name them. */
  entityRefs: string[];
  /** Sources this finding draws on. */
  sourceRefs: string[];
  structuralSignalCount: number;
  semanticSignalCount: number;
  /**
   * Analyst notes. Always `null` today — no endpoint serves notes against a
   * finding — and typed so the detail pane states the gap instead of omitting
   * a §35 requirement.
   */
  analystNotes: string | null;
}

/* ── Capture (§33) ─────────────────────────────────────────────────────── */

export interface CaptureRow extends ObjectRowBase {
  kind: "Capture";
  sourceFamily: string | null;
  targetUri: string | null;
  locator: string | null;
  contentDigest: string | null;
  mediaType: string | null;
  fetchedAt: string | null;
  /** `FETCH` / `WARC` / … the basis of the capture's timestamp. */
  timeBasis: string | null;
}

export type ObjectRow = EntityRow | ObservationRow | ClaimRow | FindingRow | CaptureRow;

/** Narrowing helper, so the detail pane cannot read the wrong variant. */
export function rowOfKind<K extends ObjectRowKind>(
  row: ObjectRow | null,
  kind: K,
): Extract<ObjectRow, { kind: K }> | null {
  return row !== null && row.kind === kind ? (row as Extract<ObjectRow, { kind: K }>) : null;
}

/* ── Sorting and faceting (§26) ────────────────────────────────────────── */

export type ObjectSortDirection = "asc" | "desc";

export interface ObjectSort {
  columnId: string;
  direction: ObjectSortDirection;
}

/** Facet dimensions. Each is a set of allowed values; empty admits everything. */
export interface ObjectFacets {
  /** §25's type filter. Wired to the store's `railKinds`, so it survives §76. */
  kinds: ObjectRowKind[];
  /** Source ids. Wired to `evidenceFilter.sourceIds`. */
  sourceIds: string[];
  /** Raw platform status strings. No store home — persisted instead (§76). */
  statuses: string[];
  /** Temporal range. The canonical one: `timeRange` in the store. */
  timeRange: { from: string | null; to: string | null };
  /** Free text. Wired to `evidenceFilter.query`. */
  query: string;
}

export const EMPTY_OBJECT_FACETS: ObjectFacets = {
  kinds: [],
  sourceIds: [],
  statuses: [],
  timeRange: { from: null, to: null },
  query: "",
};

export type ObjectFacetId = "kinds" | "sourceIds" | "statuses" | "timeRange" | "query";

export const OBJECT_FACET_IDS: ReadonlyArray<ObjectFacetId> = [
  "kinds",
  "sourceIds",
  "statuses",
  "timeRange",
  "query",
];

/* ── Column layout, saved views (§26) ──────────────────────────────────── */

/**
 * The grid's layout state: order, widths and visibility. Persisted (§26 asks
 * for it; see `persist.ts` for why persistence is also how this module satisfies
 * §76 without a store change).
 */
export interface GridLayout {
  /** Column ids in render order. Unknown ids are dropped on decode. */
  order: string[];
  /** Column id → px. Clamped to the column's own min/max on decode. */
  widths: Record<string, number>;
  /** Column ids the analyst has hidden. */
  hidden: string[];
}

export const EMPTY_GRID_LAYOUT: GridLayout = { order: [], widths: {}, hidden: [] };

/**
 * A saved view: a named snapshot of everything that makes the table look like
 * this. §26 asks for saved views; naming them and persisting them is the whole
 * feature — there is no server-side view concept to call.
 */
export interface SavedView {
  id: string;
  name: string;
  layout: GridLayout;
  sort: ObjectSort;
  facets: ObjectFacets;
  /** ISO instant the view was saved, for the "saved 3 days ago" line. */
  savedAt: string;
}

export const EMPTY_SORT: ObjectSort = { columnId: "at", direction: "desc" };
