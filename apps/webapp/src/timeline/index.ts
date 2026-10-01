/**
 * `src/timeline` — the temporal surface (§23, §84, §81).
 *
 * §84 is the constraint that shaped this module: the timeline is an ANALYTICAL
 * SURFACE, not a scrubber. So `series.ts` is the bulk of the code — filter,
 * bucket, window, focus, compare, zoom are all pure functions over the event
 * list, and the component is the thin ECharts shell around them.
 *
 * The timeline→graph channel is the workspace `timeRange`: the brush writes it,
 * the graph's temporal facet reads it. Two readers of one value, never a
 * synchronisation between two components.
 */

export {
  LANE_SEMANTICS,
  TIMELINE_LANES,
  eventIdsForEntity,
  eventIdsForSource,
  routeForEvent,
} from "./types";
export type { LaneSemantics, TimelineEvent, TimelineLane } from "./types";

export {
  EMPTY_TIMELINE_FILTER,
  MAX_BUCKETS,
  MIN_BUCKETS,
  brushToRange,
  bucketEvents,
  compareWindows,
  eventsInRange,
  filterEvents,
  panDomain,
  presentValues,
  resolveFocus,
  timeBounds,
  toggleTimelineValue,
  withinMs,
  withinRange,
  zoomDomain,
  zoomLevel,
} from "./series";
export type {
  BucketOptions,
  FocusRequest,
  FocusTarget,
  ResolvedFocus,
  TimeDomain,
  TimelineBucket,
  TimelineFilter,
  WindowComparison,
} from "./series";

export { TimelineCanvas } from "./TimelineCanvas";
export type { TimelineCanvasProps } from "./TimelineCanvas";
export { TimelineToolbar } from "./TimelineToolbar";
export type { TimelineToolbarProps } from "./TimelineToolbar";

export {
  TIMELINE_COVERAGE_MISSING,
  buildTimeline,
  countLanes,
  hostOf,
  toMs,
  useTimelineEvents,
} from "./useTimelineEvents";
export type { BuiltTimeline, TimelineServerState, TimelineSource } from "./useTimelineEvents";