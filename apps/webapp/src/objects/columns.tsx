import type { ReactNode } from "react";

import type { ObjectRow, ObjectRowKind } from "./types";

/**
 * Column registry (§26).
 *
 * The grid's columns are DATA, not JSX branches: a column is a key, a header, a
 * width, an alignment and a value accessor. Sorting, reordering, resizing,
 * hiding and persistence are then one set of operations over that list rather
 * than five separate code paths that have to be kept in agreement.
 *
 * §26's column contract, all of it here:
 *   sort        — `sortValue` present means sortable; absent means the column
 *                 never sorts (e.g. a label that has no meaningful order).
 *   facet       — `facetValue` present means the column is a filter dimension.
 *   resize      — `resizable: false` for the selection rail, which is fixed.
 *   visibility  — `defaultVisible` seeds a first run; the analyst's own choice
 *                 is persisted on top of it.
 *
 * §99: an accessor returns `null` when the platform reports nothing for that
 * column on that row, and the renderer prints "not reported". It never returns
 * a zero, an empty string, or a dash that could be mistaken for a value.
 */

export interface ColumnDefinition {
  key: string;
  header: string;
  /** Kinds this column can carry. A column absent for a kind is not rendered. */
  kinds: ReadonlyArray<ObjectRowKind>;
  /** Default px width. Persisted layout may override it within min/max. */
  width: number;
  minWidth: number;
  maxWidth: number;
  align?: "start" | "end";
  mono?: boolean;
  /** Sortable when present. */
  sortValue?: (row: ObjectRow) => string | number | null;
  /** Facet dimension when present. */
  facetValue?: (row: ObjectRow) => string | null;
  /** Fixed-width columns cannot be dragged. */
  resizable?: boolean;
  /** Only shown when the analyst has not overridden visibility. */
  defaultVisible: boolean;
  /** Render. Kept last so the definition reads as metadata then behaviour. */
  render: (row: ObjectRow) => ReactNode;
}

/** The selection column. Fixed width, never sortable, never hidden. */
export const SELECT_COLUMN_KEY = "__select";

export const MIN_WIDTH = 56;
export const MAX_WIDTH = 640;

/* ── Shared render helpers ─────────────────────────────────────────────── */

function NotReported() {
  return <span className="ui-insp-unreported">not reported</span>;
}

/** A value, or an explicit statement that the platform reported none (§99). */
function maybe(value: string | null | undefined) {
  const text = value === null || value === undefined ? null : value.trim();
  return text === null || text === "" ? <NotReported /> : text;
}

function count(value: number | null | undefined) {
  return typeof value === "number" ? value : <NotReported />;
}

/* ── The registry ──────────────────────────────────────────────────────── */

const ALL_KINDS: ReadonlyArray<ObjectRowKind> = ["Entity", "Observation", "Claim", "Finding", "Capture"];

export const OBJECT_COLUMNS: ReadonlyArray<ColumnDefinition> = [
  {
    key: SELECT_COLUMN_KEY,
    header: "",
    kinds: ALL_KINDS,
    width: 28,
    minWidth: 28,
    maxWidth: 28,
    resizable: false,
    defaultVisible: true,
    render: () => null,
  },

  /* ── Shared identity ───────────────────────────────────────────────── */
  {
    key: "label",
    header: "object",
    kinds: ALL_KINDS,
    width: 320,
    minWidth: 140,
    maxWidth: MAX_WIDTH,
    defaultVisible: true,
    sortValue: (row) => row.label,
    facetValue: (row) => row.kind,
    render: (row) => (
      <span className="ui-obj-cell-primary">
        <span className="ui-obj-cell-label">{row.label}</span>
        {row.sublabel !== null ? (
          <span className="ui-obj-cell-sub ui-mono">{row.sublabel}</span>
        ) : null}
      </span>
    ),
  },
  {
    key: "kind",
    header: "kind",
    kinds: ALL_KINDS,
    width: 96,
    minWidth: 72,
    maxWidth: 160,
    defaultVisible: true,
    sortValue: (row) => row.kind,
    facetValue: (row) => row.kind,
    render: (row) => <span className="ui-badge" data-role="classification">{row.kind}</span>,
  },
  {
    key: "id",
    header: "identifier",
    kinds: ALL_KINDS,
    width: 220,
    minWidth: 120,
    maxWidth: MAX_WIDTH,
    mono: true,
    defaultVisible: true,
    sortValue: (row) => row.id,
    render: (row) => <span className="ui-break">{row.id}</span>,
  },
  {
    key: "status",
    header: "status",
    kinds: ALL_KINDS,
    width: 132,
    minWidth: 88,
    maxWidth: 220,
    mono: true,
    defaultVisible: true,
    // Sorted and faceted on the RAW string, not the §92 projection: the analyst
    // filters on what the platform actually said. `statusWord` is for tone.
    sortValue: (row) => row.status,
    facetValue: (row) => row.status,
    render: (row) => maybe(row.status),
  },
  {
    key: "at",
    header: "observed",
    kinds: ALL_KINDS,
    width: 148,
    minWidth: 96,
    maxWidth: 240,
    mono: true,
    defaultVisible: true,
    sortValue: (row) => row.at,
    render: (row) => maybe(row.at),
  },
  {
    key: "sources",
    header: "sources",
    kinds: ALL_KINDS,
    width: 168,
    minWidth: 100,
    maxWidth: 320,
    mono: true,
    align: "end",
    defaultVisible: false,
    sortValue: (row) => row.sourceIds.length,
    facetValue: (row) => (row.sourceIds.length === 1 ? row.sourceIds[0] : null),
    render: (row) => (row.sourceIds.length === 0 ? <NotReported /> : row.sourceIds.join(", ")),
  },
  {
    key: "evidence",
    header: "records",
    kinds: ALL_KINDS,
    width: 88,
    minWidth: 72,
    maxWidth: 140,
    align: "end",
    defaultVisible: true,
    sortValue: (row) => row.evidenceCount,
    render: (row) => count(row.evidenceCount),
  },
  {
    key: "claims",
    header: "claims",
    kinds: ALL_KINDS,
    width: 88,
    minWidth: 72,
    maxWidth: 140,
    align: "end",
    defaultVisible: false,
    sortValue: (row) => row.claimCount,
    render: (row) => count(row.claimCount),
  },

  /* ── Entity ────────────────────────────────────────────────────────── */
  {
    key: "entity.canonical",
    header: "canonical identity",
    kinds: ["Entity"],
    width: 260,
    minWidth: 140,
    maxWidth: MAX_WIDTH,
    mono: true,
    defaultVisible: true,
    sortValue: (row) => (row.kind === "Entity" ? canonicalText(row) : null),
    render: (row) => (row.kind === "Entity" ? maybe(canonicalText(row)) : null),
  },
  {
    key: "entity.aliases",
    header: "aliases",
    kinds: ["Entity"],
    width: 200,
    minWidth: 100,
    maxWidth: 320,
    mono: true,
    align: "end",
    defaultVisible: false,
    sortValue: (row) => (row.kind === "Entity" ? row.aliases.length : null),
    render: (row) => (row.kind === "Entity" ? count(row.aliases.length) : null),
  },
  {
    key: "entity.continuity",
    header: "continuity",
    kinds: ["Entity"],
    width: 132,
    minWidth: 96,
    maxWidth: 200,
    mono: true,
    defaultVisible: false,
    sortValue: (row) => (row.kind === "Entity" ? row.continuity : null),
    facetValue: (row) => (row.kind === "Entity" ? row.continuity : null),
    render: (row) => (row.kind === "Entity" ? maybe(row.continuity) : null),
  },
  {
    key: "entity.seen",
    header: "first → last seen",
    kinds: ["Entity"],
    width: 300,
    minWidth: 160,
    maxWidth: MAX_WIDTH,
    mono: true,
    defaultVisible: false,
    sortValue: (row) => (row.kind === "Entity" ? row.firstSeen : null),
    render: (row) =>
      row.kind === "Entity" ? `${maybe(row.firstSeen)} → ${maybe(row.lastSeen)}` : null,
  },

  /* ── Observation ───────────────────────────────────────────────────── */
  {
    key: "observation.uri",
    header: "uri",
    kinds: ["Observation"],
    width: 380,
    minWidth: 160,
    maxWidth: MAX_WIDTH,
    defaultVisible: true,
    sortValue: (row) => (row.kind === "Observation" ? row.uri : null),
    render: (row) => (row.kind === "Observation" ? maybe(row.uri) : null),
  },
  {
    key: "observation.capture",
    header: "capture",
    kinds: ["Observation"],
    width: 180,
    minWidth: 100,
    maxWidth: 260,
    mono: true,
    defaultVisible: false,
    sortValue: (row) => (row.kind === "Observation" ? row.captureId : null),
    render: (row) => (row.kind === "Observation" ? maybe(row.captureId) : null),
  },
  {
    key: "observation.locator",
    header: "locator",
    kinds: ["Observation"],
    width: 220,
    minWidth: 120,
    maxWidth: MAX_WIDTH,
    mono: true,
    defaultVisible: true,
    sortValue: (row) => (row.kind === "Observation" ? row.locator : null),
    render: (row) => (row.kind === "Observation" ? maybe(row.locator) : null),
  },
  {
    key: "observation.content-type",
    header: "content type",
    kinds: ["Observation"],
    width: 180,
    minWidth: 100,
    maxWidth: 280,
    mono: true,
    defaultVisible: false,
    sortValue: (row) => (row.kind === "Observation" ? row.contentType : null),
    facetValue: (row) => (row.kind === "Observation" ? row.contentType : null),
    render: (row) => (row.kind === "Observation" ? maybe(row.contentType) : null),
  },
  {
    key: "observation.producer",
    header: "producer",
    kinds: ["Observation"],
    width: 160,
    minWidth: 100,
    maxWidth: 240,
    mono: true,
    defaultVisible: false,
    sortValue: (row) => (row.kind === "Observation" ? row.runtimeProducer : null),
    facetValue: (row) => (row.kind === "Observation" ? row.runtimeProducer : null),
    render: (row) => (row.kind === "Observation" ? maybe(row.runtimeProducer) : null),
  },

  /* ── Claim (§34) ───────────────────────────────────────────────────── */
  {
    key: "claim.predicate",
    header: "predicate",
    kinds: ["Claim"],
    width: 180,
    minWidth: 100,
    maxWidth: 280,
    mono: true,
    defaultVisible: true,
    sortValue: (row) => (row.kind === "Claim" ? row.predicate : null),
    facetValue: (row) => (row.kind === "Claim" ? row.predicate : null),
    render: (row) => (row.kind === "Claim" ? maybe(row.predicate) : null),
  },
  {
    key: "claim.participants",
    header: "participants",
    kinds: ["Claim"],
    width: 320,
    minWidth: 160,
    maxWidth: MAX_WIDTH,
    mono: true,
    defaultVisible: true,
    sortValue: (row) => (row.kind === "Claim" ? `${row.subjectRef} ${row.objectRef}` : null),
    render: (row) =>
      row.kind === "Claim" ? (
        <span className="ui-break">
          {row.subjectRef} → {row.objectRef}
        </span>
      ) : null,
  },
  {
    key: "claim.validity",
    header: "valid scope",
    kinds: ["Claim"],
    width: 300,
    minWidth: 160,
    maxWidth: MAX_WIDTH,
    mono: true,
    defaultVisible: false,
    sortValue: (row) => (row.kind === "Claim" ? row.validFrom : null),
    render: (row) =>
      row.kind === "Claim" ? (
        <span className="ui-break">
          {/* An open bound reads "open", not a missing value: §99. */}
          {row.validFrom ?? "open"} → {row.validTo ?? "open"}
        </span>
      ) : null,
  },
  {
    key: "claim.grade",
    header: "evidence grade",
    kinds: ["Claim"],
    width: 140,
    minWidth: 100,
    maxWidth: 220,
    mono: true,
    defaultVisible: false,
    sortValue: (row) => (row.kind === "Claim" ? row.evidenceGrade : null),
    facetValue: (row) => (row.kind === "Claim" ? row.evidenceGrade : null),
    render: (row) => (row.kind === "Claim" ? maybe(row.evidenceGrade) : null),
  },
  {
    key: "claim.confidence",
    header: "confidence",
    kinds: ["Claim"],
    width: 110,
    minWidth: 88,
    maxWidth: 180,
    mono: true,
    align: "end",
    defaultVisible: false,
    sortValue: (row) => (row.kind === "Claim" ? row.confidence : null),
    render: (row) =>
      row.kind === "Claim" && row.confidence !== null ? row.confidence.toFixed(2) : <NotReported />,
  },

  /* ── Finding (§35) ─────────────────────────────────────────────────── */
  {
    key: "finding.summary",
    header: "why detected",
    kinds: ["Finding"],
    width: 380,
    minWidth: 180,
    maxWidth: MAX_WIDTH,
    defaultVisible: true,
    sortValue: (row) => (row.kind === "Finding" ? row.summary : null),
    render: (row) => (row.kind === "Finding" ? maybe(row.summary) : null),
  },
  {
    key: "finding.resolves",
    header: "evidence resolves",
    kinds: ["Finding"],
    width: 140,
    minWidth: 100,
    maxWidth: 200,
    align: "end",
    defaultVisible: true,
    sortValue: (row) => (row.kind === "Finding" ? (row.evidenceResolves ? 1 : 0) : null),
    render: (row) => {
      if (row.kind !== "Finding") return null;
      return (
        <span className="ui-badge" data-tone={row.evidenceResolves ? "accent" : "danger"} role="classification">
          {row.evidenceResolves ? "resolves" : "does not resolve"}
        </span>
      );
    },
  },
  {
    key: "finding.support",
    header: "claims / records / entities",
    kinds: ["Finding"],
    width: 220,
    minWidth: 140,
    maxWidth: 320,
    mono: true,
    align: "end",
    defaultVisible: true,
    sortValue: (row) => (row.kind === "Finding" ? row.supportingClaimRefs.length : null),
    render: (row) =>
      row.kind === "Finding"
        ? `${row.supportingClaimRefs.length} / ${row.observationRefs.length} / ${row.entityRefs.length}`
        : null,
  },
  {
    key: "finding.signals",
    header: "structural / semantic",
    kinds: ["Finding"],
    width: 200,
    minWidth: 140,
    maxWidth: 280,
    mono: true,
    align: "end",
    defaultVisible: false,
    sortValue: (row) => (row.kind === "Finding" ? row.structuralSignalCount : null),
    render: (row) =>
      row.kind === "Finding" ? `${row.structuralSignalCount} / ${row.semanticSignalCount}` : null,
  },
  {
    key: "finding.notes",
    header: "analyst notes",
    kinds: ["Finding"],
    width: 260,
    minWidth: 140,
    maxWidth: MAX_WIDTH,
    defaultVisible: false,
    sortValue: (row) => (row.kind === "Finding" ? row.analystNotes : null),
    render: (row) => (row.kind === "Finding" ? maybe(row.analystNotes) : null),
  },

  /* ── Capture ───────────────────────────────────────────────────────── */
  {
    key: "capture.uri",
    header: "target uri",
    kinds: ["Capture"],
    width: 380,
    minWidth: 160,
    maxWidth: MAX_WIDTH,
    defaultVisible: true,
    sortValue: (row) => (row.kind === "Capture" ? row.targetUri : null),
    render: (row) => (row.kind === "Capture" ? maybe(row.targetUri) : null),
  },
  {
    key: "capture.family",
    header: "source family",
    kinds: ["Capture"],
    width: 160,
    minWidth: 100,
    maxWidth: 240,
    mono: true,
    defaultVisible: true,
    sortValue: (row) => (row.kind === "Capture" ? row.sourceFamily : null),
    facetValue: (row) => (row.kind === "Capture" ? row.sourceFamily : null),
    render: (row) => (row.kind === "Capture" ? maybe(row.sourceFamily) : null),
  },
  {
    key: "capture.media-type",
    header: "media type",
    kinds: ["Capture"],
    width: 180,
    minWidth: 100,
    maxWidth: 280,
    mono: true,
    defaultVisible: false,
    sortValue: (row) => (row.kind === "Capture" ? row.mediaType : null),
    render: (row) => (row.kind === "Capture" ? maybe(row.mediaType) : null),
  },
  {
    key: "capture.time-basis",
    header: "time basis",
    kinds: ["Capture"],
    width: 132,
    minWidth: 96,
    maxWidth: 200,
    mono: true,
    defaultVisible: false,
    sortValue: (row) => (row.kind === "Capture" ? row.timeBasis : null),
    render: (row) => (row.kind === "Capture" ? maybe(row.timeBasis) : null),
  },
];

const COLUMN_INDEX = new Map(OBJECT_COLUMNS.map((column) => [column.key, column]));

export function columnByKey(key: string): ColumnDefinition | undefined {
  return COLUMN_INDEX.get(key);
}

/** The columns a kind can show, in registry order. The base for a saved layout. */
export function columnsForKind(kind: ObjectRowKind): ColumnDefinition[] {
  return OBJECT_COLUMNS.filter((column) => column.kinds.includes(kind));
}

/** Every column that is not the fixed selection column, in registry order. */
export function hideableColumns(): ColumnDefinition[] {
  return OBJECT_COLUMNS.filter((column) => column.key !== SELECT_COLUMN_KEY);
}

/** The registry order restricted to columns that apply to at least one live kind. */
export function defaultOrder(kinds: ReadonlyArray<ObjectRowKind>): string[] {
  const live = new Set(kinds);
  return OBJECT_COLUMNS.filter((column) => column.kinds.some((kind) => live.has(kind))).map(
    (column) => column.key,
  );
}

function canonicalText(row: Extract<ObjectRow, { kind: "Entity" }>): string | null {
  const entries = Object.entries(row.canonical);
  if (entries.length === 0) return null;
  return entries
    .map(([key, value]) => `${key}=${value}`)
    .join(" ");
}
