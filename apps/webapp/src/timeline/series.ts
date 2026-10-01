import type { TimeRange } from "../workspace/types";
import { LANE_SEMANTICS, TIMELINE_LANES, type TimelineEvent, type TimelineLane } from "./types";

/**
 * The timeline's derivations (§23, §84).
 *
 * Four pure functions, and every behaviour the toolbar promises is one of them:
 *
 *   `timeBounds`   the domain the axis spans, from the data — never from a constant
 *   `filterEvents` the filter, applied as AND across four fields
 *   `bucketEvents` the histogram, one bucket per lane
 *   `resolveFocus` what "focus entity / relation / evidence" MEANS
 *
 * The one that matters most is `resolveFocus`, because it is where "changing
 * time changes graph state" and "focus is not decoration" meet. A focus returns
 * an explicit set of event ids and an explicit set of entity refs; the graph
 * reads the refs as its emphasis input, so a focus in the timeline is a focus in
 * the canvas without either surface knowing about the other's components.
 */

/* ── Domain ──────────────────────────────────────────────────────────── */

export interface TimeDomain {
  /** Epoch ms, inclusive. */
  min: number;
  /** Epoch ms, inclusive. */
  max: number;
}

function toMs(iso: string): number | null {
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? null : ms;
}

/**
 * The axis domain. A single instant produces a one-second window rather than a
 * zero-width axis, because a zero-width axis has no brushable area and the
 * brush is the primary interaction.
 */
export function timeBounds(events: ReadonlyArray<TimelineEvent>): TimeDomain | null {
  const instants: number[] = [];
  for (const event of events) {
    const start = toMs(event.at);
    if (start !== null) instants.push(start);
    const end = event.endAt === null ? null : toMs(event.endAt);
    if (end !== null) instants.push(end);
  }
  if (instants.length === 0) return null;
  const min = Math.min(...instants);
  const max = Math.max(...instants);
  return min === max ? { min: min - 500, max: max + 500 } : { min, max };
}

/* ── Filtering (§23 "filter") ────────────────────────────────────────── */

export interface TimelineFilter {
  /** Empty means all lanes. */
  lanes: TimelineLane[];
  /** Empty means all sources. */
  sourceIds: string[];
  /** Raw platform status strings. Empty means every status. */
  statuses: string[];
  /** Free text over label, ref and uri-ish fields. */
  query: string;
}

export const EMPTY_TIMELINE_FILTER: TimelineFilter = {
  lanes: [],
  sourceIds: [],
  statuses: [],
  query: "",
};

/** AND across fields, OR within a field — the same rule the graph facets use. */
export function filterEvents(
  events: ReadonlyArray<TimelineEvent>,
  filter: TimelineFilter,
): TimelineEvent[] {
  const needle = filter.query.trim().toLowerCase();
  return events.filter((event) => {
    if (filter.lanes.length > 0 && !filter.lanes.includes(event.lane)) return false;
    if (filter.sourceIds.length > 0 && (event.sourceId === null || !filter.sourceIds.includes(event.sourceId))) {
      return false;
    }
    if (filter.statuses.length > 0 && (event.status === null || !filter.statuses.includes(event.status))) {
      return false;
    }
    if (needle !== "") {
      // The source is searchable because the analyst's first guess for "where did
      // this come from" is the host, not the record id.
      const haystack = `${event.label} ${event.ref} ${event.entityRef ?? ""} ${event.sourceId ?? ""}`.toLowerCase();
      if (!haystack.includes(needle)) return false;
    }
    return true;
  });
}

/** Which values the filter can offer, drawn from the data rather than a constant. */
export function presentValues(events: ReadonlyArray<TimelineEvent>): {
  lanes: TimelineLane[];
  sourceIds: string[];
  statuses: string[];
} {
  const lanes = new Set<TimelineLane>();
  const sourceIds = new Set<string>();
  const statuses = new Set<string>();
  for (const event of events) {
    lanes.add(event.lane);
    if (event.sourceId !== null) sourceIds.add(event.sourceId);
    if (event.status !== null) statuses.add(event.status);
  }
  return {
    lanes: TIMELINE_LANES.filter((lane) => lanes.has(lane)),
    sourceIds: [...sourceIds].sort(),
    statuses: [...statuses].sort(),
  };
}

/** Toggle one value inside one filter field. Immutable. */
export function toggleTimelineValue<T extends string>(current: ReadonlyArray<T>, value: T): T[] {
  return current.includes(value) ? current.filter((entry) => entry !== value) : [...current, value];
}

/* ── The time window (§23 "brush", and how it reaches the graph) ─────── */

/**
 * Turn a brush rectangle on the axis into a `TimeRange`.
 *
 * This is the whole of "changing time changes graph state": the result is the
 * store's `timeRange`, which the graph's temporal facet already reads. So the
 * brush is not a display state that happens to look like a filter — it IS the
 * workspace time range, and there is exactly one of them (§7, §23).
 */
export function brushToRange(domain: TimeDomain, fromMs: number, toMsMs: number): TimeRange {
  const lo = Math.max(domain.min, Math.min(fromMs, toMsMs));
  const hi = Math.min(domain.max, Math.max(fromMs, toMsMs));
  return { from: new Date(lo).toISOString(), to: new Date(hi).toISOString() };
}

/** Is an instant inside the range? An open bound is open, not infinite-inclusive-of-everything-beyond. */
export function withinRange(iso: string, range: TimeRange): boolean {
  const ms = toMs(iso);
  if (ms === null) return false;
  return withinMs(ms, range);
}

export function withinMs(ms: number, range: TimeRange): boolean {
  const from = range.from === null ? null : toMs(range.from);
  const to = range.to === null ? null : toMs(range.to);
  if (from !== null && ms < from) return false;
  if (to !== null && ms > to) return false;
  return true;
}

/** Events surviving the window. Distinct from the filter: the filter is about *what*, the window is about *when*. */
export function eventsInRange(events: ReadonlyArray<TimelineEvent>, range: TimeRange): TimelineEvent[] {
  if (range.from === null && range.to === null) return [...events];
  return events.filter((event) => {
    const start = toMs(event.at);
    if (start !== null && withinMs(start, range)) return true;
    // An interval that overlaps the window counts: a claim valid across the
    // window boundary is part of what the window contains.
    const end = event.endAt === null ? null : toMs(event.endAt);
    if (end !== null) {
      const from = range.from === null ? null : toMs(range.from);
      const to = range.to === null ? null : toMs(range.to);
      if (from === null || end >= from) {
        if (to === null || (start !== null && start <= to)) return true;
      }
    }
    return false;
  });
}

/* ── Bucketing (§84 "an analytical surface, not a slider") ───────────── */

export interface TimelineBucket {
  /** Bucket start, epoch ms. */
  at: number;
  /** ISO of the bucket start, for the axis and the table headers. */
  iso: string;
  /** Count per lane, in lane order. */
  counts: Record<TimelineLane, number>;
  /** Event ids in this bucket, so clicking a bar selects real records. */
  eventIds: string[];
  total: number;
}

export interface BucketOptions {
  /** How many buckets across the domain. Clamped to a sane band. */
  buckets?: number;
  /** The window to bucket, not the whole domain. */
  range?: TimeRange;
  /** Lanes to count. Missing lanes count as 0 rather than being omitted. */
  lanes?: ReadonlyArray<TimelineLane>;
}

export const MIN_BUCKETS = 12;
export const MAX_BUCKETS = 240;

function emptyCounts(lanes: ReadonlyArray<TimelineLane>): Record<TimelineLane, number> {
  const out = {} as Record<TimelineLane, number>;
  for (const lane of lanes) out[lane] = 0;
  return out;
}

/**
 * Bucket events into a histogram, one row per lane.
 *
 * Zero buckets are KEPT, not dropped. A histogram that omits empty intervals
 * turns a quiet week into an adjacent pair of busy weeks, which is the single
 * most misleading thing a timeline can do.
 */
export function bucketEvents(
  events: ReadonlyArray<TimelineEvent>,
  domain: TimeDomain,
  options: BucketOptions = {},
): TimelineBucket[] {
  const lanes = options.lanes ?? [...TIMELINE_LANES];
  const count = clampBuckets(options.buckets ?? 48);
  const width = Math.max(1, Math.ceil((domain.max - domain.min) / count));

  const first = Math.floor(domain.min / width) * width;
  const out: TimelineBucket[] = [];
  for (let index = 0; index < count; index += 1) {
    const at = first + index * width;
    out.push({ at, iso: new Date(at).toISOString(), counts: emptyCounts(lanes), eventIds: [], total: 0 });
  }

  const range = options.range ?? { from: null, to: null };
  const inside = eventsInRange(events, range);

  for (const event of inside) {
    const ms = toMs(event.at);
    if (ms === null) continue;
    const index = Math.min(out.length - 1, Math.max(0, Math.floor((ms - first) / width)));
    const bucket = out[index];
    if (bucket.eventIds.includes(event.id)) continue;
    bucket.counts[event.lane] = (bucket.counts[event.lane] ?? 0) + 1;
    bucket.eventIds.push(event.id);
    bucket.total += 1;
  }

  return out;
}

function clampBuckets(requested: number): number {
  if (!Number.isFinite(requested)) return MIN_BUCKETS;
  return Math.min(MAX_BUCKETS, Math.max(MIN_BUCKETS, Math.floor(requested)));
}

/* ── Focus (§23 "focus entity / relation / evidence") ────────────────── */

export type FocusTarget = "entity" | "relation" | "evidence";

export interface FocusRequest {
  target: FocusTarget;
  /** Entity ref, relation ref or observation ref, per the target. */
  ref: string;
}

export interface ResolvedFocus {
  /** What was asked for, verbatim — for the live region and the undo affordance. */
  request: FocusRequest;
  /** Event ids that match. */
  eventIds: string[];
  /**
   * Entity refs the graph should emphasise. This is the timeline→graph channel
   * and it is deliberately a list of platform identifiers rather than a graph
   * node id: the graph owns the mapping from an entity ref to a node.
   */
  entityRefs: string[];
  /** True when the focus matched nothing. A focus that matches nothing says so. */
  empty: boolean;
  /** Words for the status line. */
  label: string;
}

/**
 * Resolve a focus request against the events.
 *
 *   entity    → every event anchored to that entity
 *   relation  → every event on the Claim lane for that relation id
 *   evidence  → every event for that observation id, plus any event from the
 *               same source in the same instant — because "what else did this
 *               record arrive with" is the question the analyst is actually
 *               asking, and a focus that answers less than that is a dead end.
 */
export function resolveFocus(
  events: ReadonlyArray<TimelineEvent>,
  request: FocusRequest,
): ResolvedFocus {
  let matched: TimelineEvent[];
  switch (request.target) {
    case "entity":
      matched = events.filter((event) => event.entityRef === request.ref);
      break;
    case "relation":
      matched = events.filter((event) => event.lane === "Claim" && event.ref === request.ref);
      break;
    case "evidence": {
      const direct = events.filter((event) => event.ref === request.ref);
      const anchor = direct[0];
      const siblings =
        anchor === undefined || anchor.sourceId === null
          ? []
          : events.filter(
              (event) =>
                event.sourceId === anchor.sourceId &&
                event.at === anchor.at &&
                event.ref !== anchor.ref,
            );
      matched = [...direct, ...siblings];
      break;
    }
  }

  const eventIds = matched.map((event) => event.id);
  const entityRefs = [...new Set(matched.map((event) => event.entityRef).filter((ref): ref is string => ref !== null))];

  return {
    request,
    eventIds,
    entityRefs,
    empty: eventIds.length === 0,
    label: focusLabel(request, matched),
  };
}

function focusLabel(request: FocusRequest, matched: ReadonlyArray<TimelineEvent>): string {
  const noun =
    request.target === "entity" ? "entity" : request.target === "relation" ? "relation" : "record";
  if (matched.length === 0) return `No timeline events for that ${noun}.`;
  const lanes = new Set(matched.map((event) => LANE_SEMANTICS[event.lane].label));
  const spread = [...lanes].join(" + ");
  return `${request.ref}: ${matched.length} event(s) across ${spread}.`;
}

/* ── Comparison (§23 "compare") ───────────────────────────────────────── */

export interface WindowComparison {
  current: { from: string | null; to: string | null; count: number };
  previous: { from: string | null; to: string | null; count: number };
  /** Null when the comparison cannot be computed — never a fabricated delta. */
  delta: number | null;
  /** Words for the status line. */
  label: string;
}

/**
 * Compare the brushed window with the window immediately before it, of the same
 * width. "Compare" in a timeline is not a chart overlay — it is the question
 * "is this window busier or quieter than the one before", and the answer is a
 * count plus a delta.
 *
 * The delta is null when the window is open-ended, because an unbounded window
 * has no width to compare against and a number here would be invented.
 */
export function compareWindows(events: ReadonlyArray<TimelineEvent>, range: TimeRange): WindowComparison {
  const current = eventsInRange(events, range).length;
  const from = range.from === null ? null : toMs(range.from);
  const to = range.to === null ? null : toMs(range.to);

  if (from === null || to === null) {
    return {
      current: { from: range.from, to: range.to, count: current },
      previous: { from: null, to: null, count: 0 },
      delta: null,
      label: "Set both window bounds to compare against the preceding window.",
    };
  }

  const width = to - from;
  const previousRange: TimeRange = {
    from: new Date(from - width).toISOString(),
    to: new Date(from).toISOString(),
  };
  const previous = eventsInRange(events, previousRange).length;

  return {
    current: { from: range.from, to: range.to, count: current },
    previous: { from: previousRange.from, to: previousRange.to, count: previous },
    delta: current - previous,
    label:
      current === previous
        ? `Same volume as the preceding window (${current}).`
        : `${current > previous ? "Busier" : "Quieter"} by ${Math.abs(current - previous)} than the preceding window.`,
  };
}

/* ── Zoom (§23 "zoom") ───────────────────────────────────────────────── */

/**
 * Zoom the domain by a factor about its midpoint.
 *
 * Clamped so the domain can never invert or collapse to nothing: a time axis
 * with a negative width renders as a chart of nonsense.
 */
export function zoomDomain(domain: TimeDomain, factor: number): TimeDomain {
  const safe = Number.isFinite(factor) && factor > 0 ? factor : 1;
  const clamped = Math.min(8, Math.max(0.125, safe));
  const span = domain.max - domain.min;
  const nextSpan = span * clamped;
  const midpoint = (domain.min + domain.max) / 2;
  return {
    min: Math.round(midpoint - nextSpan / 2),
    max: Math.round(midpoint + nextSpan / 2),
  };
}

/** Pan the domain by a fraction of its own width. */
export function panDomain(domain: TimeDomain, fraction: number): TimeDomain {
  const span = domain.max - domain.min;
  const shift = span * (Number.isFinite(fraction) ? fraction : 0);
  return { min: Math.round(domain.min + shift), max: Math.round(domain.max + shift) };
}

/** Relative to the full domain, for the zoom controls' pressed state. */
export function zoomLevel(domain: TimeDomain, full: TimeDomain): number {
  const fullSpan = full.max - full.min;
  if (fullSpan === 0) return 1;
  return (domain.max - domain.min) / fullSpan;
}