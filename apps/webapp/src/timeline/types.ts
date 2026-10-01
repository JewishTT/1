import type { WorkspaceObjectKind, WorkspaceSelection } from "../workspace/types";

/**
 * Timeline vocabulary (§23, §84, §98).
 *
 * The timeline is an ANALYTICAL SURFACE, not a scrubber. Everything here exists
 * to answer a question a slider cannot: what happened when, how often, what was
 * true at T, and how this window compares with the one before it.
 *
 * §81 again: events are not graph nodes. An event names a platform object by
 * `kind` + `ref` and routes to the global selection through
 * `routeForEvent` — so the timeline, the graph and the evidence surface are
 * three views of the same records, not three models of them.
 */

/** Lanes. One per record type that has a temporal position. */
export type TimelineLane = "Observation" | "Finding" | "Claim" | "AcquisitionRun";

export const TIMELINE_LANES: ReadonlyArray<TimelineLane> = [
  "Observation",
  "Finding",
  "Claim",
  "AcquisitionRun",
];

/**
 * Lane presentation. Shape, not colour — the same rule the graph follows, so an
 * analyst who has learned one surface reads the other without relearning the
 * encoding. A bar chart with four coloured bars is a legend; four lanes with
 * four glyphs is a diagram.
 */
export interface LaneSemantics {
  lane: TimelineLane;
  /** ECharts `symbol`, for the event series. */
  symbol: "rect" | "diamond" | "hexagon" | "pin";
  /** Two-letter mono token, for the lane rail and the accessible names. */
  token: string;
  label: string;
  /** The kind the selection model uses, for routing. */
  selectionKind: WorkspaceObjectKind;
}

export const LANE_SEMANTICS: Readonly<Record<TimelineLane, LaneSemantics>> = {
  Observation: { lane: "Observation", symbol: "rect", token: "OBS", label: "Observation", selectionKind: "Observation" },
  Finding: { lane: "Finding", symbol: "pin", token: "FND", label: "Finding", selectionKind: "Finding" },
  Claim: { lane: "Claim", symbol: "hexagon", token: "CLM", label: "Claim", selectionKind: "Claim" },
  AcquisitionRun: {
    lane: "AcquisitionRun",
    symbol: "diamond",
    token: "RUN",
    label: "Acquisition run",
    selectionKind: "AcquisitionRun",
  },
};

export interface TimelineEvent {
  /** Unique within one investigation. Content-derived, so it is stable. */
  id: string;
  lane: TimelineLane;
  /** The platform's own identifier. This is what the analyst selects. */
  ref: string;
  label: string;
  /**
   * ISO instant the event happened. Required — an event with no instant cannot
   * be placed on a time axis, and pretending otherwise is how a timeline starts
   * lying. `null` instants are rejected at the adapter, not here.
   */
  at: string;
  /** Interval end for validity windows. Null means "still open", not "no end". */
  endAt: string | null;
  sourceId: string | null;
  /** Raw platform status, verbatim. Null means the platform reports none. */
  status: string | null;
  /** Entity whose neighbourhood produced this event, when one applies. */
  entityRef: string | null;
}

/** Where an event sends the global selection. */
export function routeForEvent(event: TimelineEvent): WorkspaceSelection {
  return {
    kind: LANE_SEMANTICS[event.lane].selectionKind,
    id: event.ref,
    label: event.label,
  };
}

/** Event ids for one entity, used by "focus entity". */
export function eventIdsForEntity(events: ReadonlyArray<TimelineEvent>, entityRef: string): string[] {
  return events.filter((event) => event.entityRef === entityRef).map((event) => event.id);
}

/** Event ids for one source, used by the source facet and "focus evidence". */
export function eventIdsForSource(events: ReadonlyArray<TimelineEvent>, sourceId: string): string[] {
  return events.filter((event) => event.sourceId === sourceId).map((event) => event.id);
}