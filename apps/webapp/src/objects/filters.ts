import type { ColumnDefinition } from "./columns";
import { SELECT_COLUMN_KEY, columnByKey } from "./columns";
import { hostOf, rowKey } from "./model";
import {
  EMPTY_OBJECT_FACETS,
  OBJECT_ROW_KINDS,
  type ObjectFacetId,
  type ObjectFacets,
  type ObjectRow,
  type ObjectRowKind,
  type ObjectSort,
} from "./types";

/**
 * Faceting and sorting (§25, §26).
 *
 * ONE RULE, ONE PREDICATE. Every facet is a set of allowed values; an empty set
 * admits everything; facets combine with AND and values within a facet with OR.
 * Stating it once and applying it with one predicate is what makes "faceted"
 * checkable rather than aspirational.
 *
 * TIME IS THE ONE THAT NEEDS CARE. A row that reports NO instants is *unknown*,
 * not "outside the window" — hiding it would be a false statement about the
 * record (§99). So a time range excludes only rows that report at least one
 * instant and place none of them inside.
 *
 * SORTING puts unreported values LAST in both directions. "Unknown when" is not
 * "before every known instant", and a table whose undated rows lead under a
 * descending sort is lying about recency.
 */

export function applyFacets(rows: ReadonlyArray<ObjectRow>, facets: ObjectFacets): ObjectRow[] {
  const needle = facets.query.trim().toLowerCase();
  return rows.filter((row) => {
    if (facets.kinds.length > 0 && !facets.kinds.includes(row.kind)) return false;
    if (facets.statuses.length > 0) {
      // An unreported status cannot match a filter on reported statuses: a facet
      // for "RUNNING" must not sweep in every row the platform said nothing about.
      if (row.status === null || !facets.statuses.includes(row.status)) return false;
    }
    if (facets.sourceIds.length > 0) {
      const hasSource = row.sourceIds.some((id) => facets.sourceIds.includes(id));
      if (!hasSource) return false;
    }
    if (!withinTimeRange(row.instants, facets)) return false;
    if (needle !== "" && !row.searchText.includes(needle)) return false;
    return true;
  });
}

function withinTimeRange(instants: ReadonlyArray<string>, facets: ObjectFacets): boolean {
  const { from, to } = facets.timeRange;
  if (from === null && to === null) return true;
  if (instants.length === 0) return true;
  const fromMs = from === null ? null : Date.parse(from);
  const toMs = to === null ? null : Date.parse(to);
  return instants.some((iso) => {
    const ms = Date.parse(iso);
    if (Number.isNaN(ms)) return true;
    if (fromMs !== null && !Number.isNaN(fromMs) && ms < fromMs) return false;
    if (toMs !== null && !Number.isNaN(toMs) && ms > toMs) return false;
    return true;
  });
}

/**
 * Sort. Ties break on the row key so the order is total and stable — two renders
 * of the same data always produce the same order, which is what makes a saved
 * view reproducible.
 */
export function sortRows(
  rows: ReadonlyArray<ObjectRow>,
  sort: ObjectSort,
  _columns: ReadonlyArray<ColumnDefinition>,
): ObjectRow[] {
  const column = columnByKey(sort.columnId);
  const accessor = column?.sortValue;
  if (accessor === undefined) {
    // An unsortable column falls back to a stable, meaningful order rather than
    // to the insertion order, which would make the table look unsorted.
    return [...rows].sort(byRowKey);
  }
  const sign = sort.direction === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const left = accessor(a);
    const right = accessor(b);
    if (left === null && right === null) return byRowKey(a, b);
    if (left === null) return 1;
    if (right === null) return -1;
    if (typeof left === "number" && typeof right === "number") {
      return left === right ? byRowKey(a, b) : (left - right) * sign;
    }
    const ls = String(left);
    const rs = String(right);
    if (ls === rs) return byRowKey(a, b);
    return (ls < rs ? -1 : 1) * sign;
  });
}

function byRowKey(a: ObjectRow, b: ObjectRow): number {
  const ak = rowKey(a.kind, a.id);
  const bk = rowKey(b.kind, b.id);
  return ak < bk ? -1 : ak > bk ? 1 : 0;
}

/* ── Facet state ──────────────────────────────────────────────────────── */

/** Which facets are narrowing, in the fixed §26 order. */
export function activeFacetIds(facets: ObjectFacets): ObjectFacetId[] {
  const active: ObjectFacetId[] = [];
  if (facets.kinds.length > 0) active.push("kinds");
  if (facets.sourceIds.length > 0) active.push("sourceIds");
  if (facets.statuses.length > 0) active.push("statuses");
  if (facets.timeRange.from !== null || facets.timeRange.to !== null) active.push("timeRange");
  if (facets.query.trim() !== "") active.push("query");
  return active;
}

/** Toggle one value inside one facet. Immutable — the caller writes it onward. */
export function toggleFacetValue<T extends string>(current: ReadonlyArray<T>, value: T): T[] {
  return current.includes(value) ? current.filter((entry) => entry !== value) : [...current, value];
}

/** Reset to the neutral facet set, keeping the fields the store owns. */
export function resetFacets(keep: Partial<ObjectFacets> = {}): ObjectFacets {
  return {
    ...EMPTY_OBJECT_FACETS,
    kinds: keep.kinds ? [...keep.kinds] : [],
    sourceIds: keep.sourceIds ? [...keep.sourceIds] : [],
    timeRange: keep.timeRange ? { ...keep.timeRange } : { from: null, to: null },
    query: keep.query ?? "",
  };
}

export function toggleKind(facets: ObjectFacets, kind: ObjectRowKind): ObjectFacets {
  return { ...facets, kinds: toggleFacetValue(facets.kinds, kind) };
}

/* ── Facet values present in the data (§26) ────────────────────────────── */

export interface FacetOptions {
  /** Statuses actually present, as raw platform strings. */
  statuses: string[];
  /** Source ids actually present. */
  sourceIds: string[];
  /** Counts per kind, including zero — a stated zero is not a missing facet. */
  kindCounts: Record<ObjectRowKind, number>;
}

/**
 * The values the table can be filtered by, taken from the rows themselves.
 *
 * Offering a status the server never returned is a filter that can only ever
 * produce an empty table, which is §69's dead end wearing a different hat.
 */
export function presentFacetOptions(rows: ReadonlyArray<ObjectRow>): FacetOptions {
  const statuses = new Set<string>();
  const sources = new Set<string>();
  const kindCounts = { Entity: 0, Observation: 0, Claim: 0, Finding: 0, Capture: 0 };

  for (const row of rows) {
    if (row.status !== null) statuses.add(row.status);
    for (const source of row.sourceIds) sources.add(source);
    kindCounts[row.kind] += 1;
  }

  return {
    statuses: [...statuses].sort(),
    sourceIds: [...sources].sort(),
    kindCounts,
  };
}

/**
 * Counts per kind for a facet set. Deliberately computed against the rows that
 * survive the OTHER facets: combining facet counts into one running total is how
 * faceted search stops being explainable.
 */
export function countsByKind(rows: ReadonlyArray<ObjectRow>): Record<ObjectRowKind, number> {
  const counts = { Entity: 0, Observation: 0, Claim: 0, Finding: 0, Capture: 0 };
  for (const row of rows) counts[row.kind] += 1;
  return counts;
}

/** Every kind present in the facet order, for the toolbar's type filter. */
export function allKinds(): ReadonlyArray<ObjectRowKind> {
  return OBJECT_ROW_KINDS;
}

/* ── Column operations (§26) ───────────────────────────────────────────── */

export interface ResolvedColumn {
  definition: ColumnDefinition;
  /** Effective px width after the layout and the column's own clamp. */
  width: number;
  visible: boolean;
}

/**
 * The kinds actually in play.
 *
 * §26 is explicit that an empty type filter means "all five kinds", and
 * `applyFacets` already implements that. These two functions take the same list
 * and used to read it the other way — as "the kinds to include" — so an
 * unfiltered table (the state every analyst starts in) resolved to ZERO columns,
 * including the selection rail. The table rendered with a header and no cells and
 * no error, which is the worst of both: a bug that looks like an empty result set.
 *
 * One predicate now settles it for both, so "no filter" cannot mean two things in
 * one module.
 */
function liveKinds(kinds: ReadonlyArray<ObjectRowKind>): ReadonlySet<ObjectRowKind> {
  return kinds.length === 0 ? new Set(OBJECT_ROW_KINDS) : new Set(kinds);
}

/**
 * The columns a grid renders, in order.
 *
 * Three rules, applied in this order and no other:
 *   1. the layout's `order` wins, with any column it does not mention appended in
 *      registry order (a saved view from before a column was added still works);
 *   2. a width outside the column's own min/max is CLAMPED, so a hand-edited or
 *      stale persisted layout cannot produce an unreadable or un-grabbable column;
 *   3. the selection column is always present, always first and never hidden.
 */
export function resolveColumns(
  layout: { order: string[]; widths: Record<string, number>; hidden: string[] },
  registry: ReadonlyArray<ColumnDefinition>,
  kinds: ReadonlyArray<ObjectRowKind>,
): ResolvedColumn[] {
  const live = liveKinds(kinds);
  const applicable = registry.filter((column) => column.kinds.some((kind) => live.has(kind)));
  const byKey = new Map(applicable.map((column) => [column.key, column]));

  const ordered: string[] = [];
  for (const key of layout.order) {
    if (byKey.has(key) && !ordered.includes(key)) ordered.push(key);
  }
  for (const column of applicable) {
    if (!ordered.includes(column.key)) ordered.push(column.key);
  }

  const resolved: ResolvedColumn[] = [];
  for (const key of ordered) {
    const definition = byKey.get(key);
    if (definition === undefined) continue;
    const isSelect = definition.key === SELECT_COLUMN_KEY;
    const requested = layout.widths[definition.key];
    const width = isSelect
      ? definition.width
      : clamp(typeof requested === "number" ? requested : definition.width, definition.minWidth, definition.maxWidth);
    resolved.push({
      definition,
      width,
      visible: isSelect ? true : !layout.hidden.includes(definition.key),
    });
  }

  // The selection column is pinned first regardless of what the layout says.
  return resolved.sort((a) => (a.definition.key === SELECT_COLUMN_KEY ? -1 : 0));
}

function clamp(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, Math.round(value)));
}

/** Move a column one position left/right. Returns the same array when it cannot move. */
export function moveColumn(order: ReadonlyArray<string>, key: string, delta: -1 | 1): string[] {
  const index = order.indexOf(key);
  if (index === -1) return [...order];
  const target = index + delta;
  if (target < 0 || target >= order.length) return [...order];
  const next = [...order];
  const moved = next[index] as string;
  next[index] = next[target] as string;
  next[target] = moved;
  return next;
}

/** Set a column width, clamped to the column's own bounds. */
export function resizeColumn(
  widths: Readonly<Record<string, number>>,
  definition: ColumnDefinition,
  width: number,
): Record<string, number> {
  if (definition.resizable === false) return { ...widths };
  return { ...widths, [definition.key]: clamp(width, definition.minWidth, definition.maxWidth) };
}

export function setColumnHidden(
  hidden: ReadonlyArray<string>,
  definition: ColumnDefinition,
  hiddenNow: boolean,
): string[] {
  if (definition.key === SELECT_COLUMN_KEY) return [...hidden];
  const isHidden = hidden.includes(definition.key);
  if (hiddenNow === isHidden) return [...hidden];
  return hiddenNow
    ? [...hidden, definition.key]
    : hidden.filter((key) => key !== definition.key);
}

/** Every applicable column's default visibility, for a first run. */
export function defaultLayout(
  registry: ReadonlyArray<ColumnDefinition>,
  kinds: ReadonlyArray<ObjectRowKind>,
): { order: string[]; widths: Record<string, number>; hidden: string[] } {
  const live = liveKinds(kinds);
  const applicable = registry.filter((column) => column.kinds.some((kind) => live.has(kind)));
  return {
    order: applicable.map((column) => column.key),
    widths: Object.fromEntries(applicable.map((column) => [column.key, column.width])),
    hidden: applicable.filter((column) => !column.defaultVisible).map((column) => column.key),
  };
}

/** Which columns can be reordered. The selection column is not one of them. */
export function reorderableColumns(columns: ReadonlyArray<ResolvedColumn>): ResolvedColumn[] {
  return columns.filter((column) => column.definition.key !== SELECT_COLUMN_KEY);
}

/** Source ids a row set actually carries, sorted. Used by the source facet. */
export function sourceIdsIn(rows: ReadonlyArray<ObjectRow>): string[] {
  const out = new Set<string>();
  for (const row of rows) for (const source of row.sourceIds) out.add(source);
  return [...out].sort();
}

/** The host of a row's primary label, when it has one — the "open by host" facet. */
export function labelHost(row: ObjectRow): string | null {
  return hostOf(row.label);
}
