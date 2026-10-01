import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Button } from "../ui/Button";
import { EmptyState, Skeleton } from "../ui/Feedback";
import { useWorkspace } from "../workspace/store";
import type { TimeRange } from "../workspace/types";
import { TimelineToolbar } from "./TimelineToolbar";
import {
  EMPTY_TIMELINE_FILTER,
  brushToRange,
  bucketEvents,
  compareWindows,
  eventsInRange,
  filterEvents,
  panDomain,
  presentValues,
  resolveFocus,
  timeBounds,
  zoomDomain,
  zoomLevel,
  type FocusRequest,
  type FocusTarget,
  type TimelineFilter,
  type TimeDomain,
} from "./series";
import { LANE_SEMANTICS, TIMELINE_LANES, routeForEvent, type TimelineEvent, type TimelineLane } from "./types";
import { useTimelineEvents } from "./useTimelineEvents";
import "./timeline.css";

/**
 * TimelineCanvas + TimelineToolbar (§23, §84).
 *
 * NOT A SLIDER. A slider has one input — a position between two ends — and one
 * output. This surface has seven: filter, brush, zoom, compare, and three kinds
 * of focus. That difference is the whole reason it exists: a slider tells the
 * analyst what time they are looking at, and this tells them what is in that
 * time, how that compares with the window before it, and which records moved.
 *
 * HOW TIME REACHES THE GRAPH (§23, §81):
 *
 *   brush / zoom / a focus window  →  `setTimeRange(...)`  →  the store
 *                                                      →  the graph's temporal facet
 *
 * There is exactly one time range in the workspace, it lives in the store
 * (§7), and the graph already reads it. So "changing time changes graph state" is
 * not a synchronisation between two components — it is two readers of one
 * value. Nothing here renders a private copy of the window.
 *
 * §68: ECharts is created once, `setOption` is used for updates, and the option
 * is built in a memo keyed on the bucket array. The event table under the chart
 * is virtualised, because a month of observations is thousands of rows.
 */

export interface TimelineCanvasProps {
  investigationId?: string | null;
  /** Events supplied by an outer surface that already holds richer records. */
  events?: ReadonlyArray<TimelineEvent>;
  /** Hide the dock chrome when the timeline is the full centre view. */
  variant?: "docked" | "full";
}

export function TimelineCanvas({ investigationId, events: suppliedEvents, variant = "docked" }: TimelineCanvasProps) {
  const storeInvestigationId = useWorkspace((state) => state.investigationId);
  const activeInvestigation = investigationId !== undefined ? investigationId : storeInvestigationId;

  const timeRange = useWorkspace((state) => state.timeRange);
  const setTimeRange = useWorkspace((state) => state.setTimeRange);
  const clearTimeRange = useWorkspace((state) => state.clearTimeRange);
  const selection = useWorkspace((state) => state.selection);
  const secondaryCount = useWorkspace((state) => state.secondarySelection.length);
  const select = useWorkspace((state) => state.select);

  const server = useTimelineEvents(activeInvestigation);
  const allEvents = useMemo(
    () => (suppliedEvents !== undefined && suppliedEvents.length > 0 ? [...suppliedEvents] : server.events),
    [suppliedEvents, server.events],
  );

  const [filter, setFilter] = useState<TimelineFilter>(EMPTY_TIMELINE_FILTER);
  const [domain, setDomain] = useState<TimeDomain | null>(null);
  const [focus, setFocus] = useState<ReturnType<typeof resolveFocus> | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const hostRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<{ setOption: (option: unknown, notMerge?: boolean) => void; resize: () => void; dispose: () => void; on: (name: string, handler: (params: unknown) => void) => void; off: (name: string) => void } | null>(null);

  const fullDomain = useMemo(() => timeBounds(allEvents), [allEvents]);
  const activeDomain = useMemo(() => clampToDomain(domain ?? fullDomain, fullDomain), [domain, fullDomain]);
  const filtered = useMemo(() => filterEvents(allEvents, filter), [allEvents, filter]);
  const inWindow = useMemo(() => eventsInRange(filtered, timeRange), [filtered, timeRange]);
  const buckets = useMemo(
    () => (activeDomain === null ? [] : bucketEvents(filtered, activeDomain, { range: timeRange })),
    [filtered, activeDomain, timeRange],
  );
  const present = useMemo(() => presentValues(allEvents), [allEvents]);
  const comparison = useMemo(() => compareWindows(filtered, timeRange), [filtered, timeRange]);
  const focusedIds = useMemo(() => new Set(focus?.eventIds ?? []), [focus]);

  /* ── ECharts: created once, updated by setOption ───────────────────── */

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let cancelled = false;

    void import("echarts").then((mod) => {
      if (cancelled || hostRef.current === null) return;
      const chart = mod.init(hostRef.current, undefined, { renderer: "canvas" });
      chartRef.current = chart as unknown as typeof chartRef.current;
      chart.on("brushEnd", (params: unknown) => {
        const areas = (params as { areas?: Array<{ coordRange?: [number, number] }> }).areas ?? [];
        const area = areas[0];
        const range = area?.coordRange;
        if (!range || fullDomain === null) return;
        setTimeRange(brushToRange(fullDomain, range[0], range[1]));
      });
    });

    return () => {
      cancelled = true;
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, [fullDomain, setTimeRange]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    chart.setOption(buildOption(buckets, inWindow, focusedIds, timeRange, fullDomain), true);
  }, [buckets, inWindow, focusedIds, timeRange, fullDomain]);

  useEffect(() => {
    const onResize = () => chartRef.current?.resize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  /* ── Commands ─────────────────────────────────────────────────────── */

  const onBrush = useCallback(
    (from: string | null, to: string | null) => {
      setTimeRange({ from, to });
      setNote(from === null && to === null ? "Window cleared." : `Window: ${from ?? "open"} → ${to ?? "open"}.`);
    },
    [setTimeRange],
  );

  const onZoom = useCallback(
    (factor: number) => {
      if (activeDomain === null) return;
      const next = zoomDomain(activeDomain, factor);
      setDomain(next);
      setTimeRange({ from: new Date(next.min).toISOString(), to: new Date(next.max).toISOString() });
      setNote(`Zoomed to ${((next.max - next.min) / 3_600_000).toFixed(1)} hours.`);
    },
    [activeDomain, setTimeRange],
  );

  const onPan = useCallback(
    (fraction: number) => {
      if (activeDomain === null) return;
      const next = panDomain(activeDomain, fraction);
      setDomain(next);
      setTimeRange({ from: new Date(next.min).toISOString(), to: new Date(next.max).toISOString() });
    },
    [activeDomain, setTimeRange],
  );

  const onResetZoom = useCallback(() => {
    setDomain(null);
    clearTimeRange();
    setNote("Axis reset to the full record span.");
  }, [clearTimeRange]);

  const onFocus = useCallback(
    (target: FocusTarget, ref: string) => {
      if (ref.trim() === "") {
        setNote("Type an identifier to focus on.");
        return;
      }
      const request: FocusRequest = { target, ref: ref.trim() };
      const resolved = resolveFocus(filtered, request);
      setFocus(resolved);
      // A focus is also a selection: §7 has one selection model, and a focus that
      // did not move the selection would leave the inspector showing something
      // else.
      const anchor = filtered.find((event) => resolved.eventIds.includes(event.id));
      if (anchor) select(routeForEvent(anchor));
      // §23: focusing a record narrows the WINDOW, so the graph follows. The
      // window is the store's, so this is the same value the brush writes.
      if (!resolved.empty) {
        const instants = filtered
          .filter((event) => resolved.eventIds.includes(event.id))
          .map((event) => Date.parse(event.at));
        const lo = new Date(Math.min(...instants)).toISOString();
        const hi = new Date(Math.max(...instants)).toISOString();
        setTimeRange({ from: lo, to: hi });
      }
      setNote(resolved.label);
    },
    [filtered, select, setTimeRange],
  );

  const onClearFocus = useCallback(() => {
    setFocus(null);
    setNote("Focus cleared.");
  }, []);

  /* ── States (§90, §91) ────────────────────────────────────────────── */

  if (activeInvestigation === null) {
    return (
      <section className="ui-timeline" data-variant={variant} data-testid="timeline-canvas">
        <EmptyState
          size="sm"
          icon="view-timeline"
          title="No investigation loaded"
          description="The timeline plots one investigation's records. Choose an investigation and the axis spans whatever the server reported."
          testId="timeline-no-investigation"
        />
      </section>
    );
  }

  if (server.loading) {
    return (
      <section className="ui-timeline" data-variant={variant} data-testid="timeline-canvas">
        <Skeleton rows={4} label="Loading temporal records" />
      </section>
    );
  }

  if (server.error !== null) {
    return (
      <section className="ui-timeline" data-variant={variant} data-testid="timeline-canvas">
        <div className="ui-inspector-error" role="alert" data-testid="timeline-error">
          <p className="ui-pane-title">The timeline did not load</p>
          <p className="ui-body" data-testid="timeline-error-message">
            {server.error}
          </p>
          <p className="ui-body">
            Scope: the entity projection and the finding list for investigation{" "}
            <span className="ui-mono">{activeInvestigation}</span>. The graph and the
            evidence views are unaffected.
          </p>
          <div className="ui-insp-next-list">
            <Button size="sm" onClick={server.refetch} data-testid="timeline-error-retry">
              Retry
            </Button>
            <Button size="sm" onClick={onResetZoom} data-testid="timeline-error-inspect">
              Clear the window
            </Button>
          </div>
        </div>
      </section>
    );
  }

  const hasEvents = allEvents.length > 0;

  return (
    <section
      className="ui-timeline"
      data-variant={variant}
      data-testid="timeline-canvas"
      aria-label="Temporal analysis"
    >
      <TimelineToolbar
        filter={filter}
        onFilterChange={setFilter}
        presentLanes={present.lanes}
        presentSourceIds={present.sourceIds}
        presentStatuses={present.statuses}
        timeRange={timeRange}
        onBrush={onBrush}
        onZoom={onZoom}
        onPan={onPan}
        onResetZoom={onResetZoom}
        zoom={activeDomain === null || fullDomain === null ? 1 : zoomLevel(activeDomain, fullDomain)}
        canZoom={activeDomain !== null}
        comparison={comparison}
        onFocus={onFocus}
        onClearFocus={onClearFocus}
        focus={focus}
        onCompare={() => setNote(comparison.label)}
        secondaryCount={secondaryCount}
        onClearWindow={clearTimeRange}
        counts={server.counts}
        unplaced={server.unplaced}
        loading={server.loading}
        disabled={!hasEvents}
      />

      {!hasEvents ? (
        <EmptyState
          size="sm"
          icon="view-timeline"
          title="No dated records yet"
          description="The platform returned no observation with an observed_at for this investigation, so there is nothing to place on an axis. The graph and the evidence views still show the undated records."
          action={
            <Button size="sm" onClick={onResetZoom} data-testid="timeline-empty-reset">
              Clear the window
            </Button>
          }
          testId="timeline-empty-state"
        />
      ) : (
        <>
          <div className="ui-timeline-chart" ref={hostRef} data-testid="timeline-chart" />

          <LaneRail counts={inWindow.length === 0 ? zeroCounts() : countsByLane(inWindow)} />

          {inWindow.length > 0 ? (
            <EventTable
              events={inWindow}
              focusedIds={focusedIds}
              selectedRef={selection?.id ?? null}
              onSelect={(event) => select(routeForEvent(event))}
            />
          ) : (
            <p className="ui-timeline-note" data-testid="timeline-window-empty">
              No events in this window. Widen it, or clear it to see the whole span.
            </p>
          )}
        </>
      )}

      {note !== null ? (
        <p className="ui-timeline-note" role="status" aria-live="polite" data-testid="timeline-note">
          {note}
        </p>
      ) : null}

      {/* Announces the window without moving focus (§67). */}
      <span className="ui-sr-only" role="status" aria-live="polite" data-testid="timeline-live">
        {`window ${timeRange.from ?? "open"} to ${timeRange.to ?? "open"}, ${inWindow.length} events`}
      </span>

      {server.missing.length > 0 ? (
        <p className="ui-timeline-coverage" data-testid="timeline-coverage">
          Not served by any endpoint today: {server.missing.join("; ")}
        </p>
      ) : null}
    </section>
  );
}

/* ── ECharts option ──────────────────────────────────────────────────── */

const RESERVED_LANE_COLOURS = 0;

/**
 * The chart option.
 *
 * One series per lane, positioned on separate grids — lane separation instead of
 * colour separation, for the same reason the graph separates by shape. Bars are
 * `rect`/`hexagon`/`pin`/`diamond` symbols so a monochrome screenshot still
 * shows four lanes.
 *
 * Reserved colours come from CSS custom properties read at the host, so light
 * mode is a real theme rather than an inversion (§57). No hex is written here.
 */
function buildOption(
  buckets: ReturnType<typeof bucketEvents>,
  inWindow: ReadonlyArray<TimelineEvent>,
  focusedIds: ReadonlySet<string>,
  range: TimeRange,
  domain: TimeDomain | null,
): unknown {
  const axisBase = {
    axisLine: { show: true },
    axisLabel: { fontSize: 10 },
    splitLine: { show: false },
  };

  const laneSeries = TIMELINE_LANES.map((lane, index) => {
    const semantics = LANE_SEMANTICS[lane];
    return {
      name: semantics.label,
      type: "bar",
      xAxisIndex: index,
      yAxisIndex: index,
      barMaxWidth: 8,
      itemStyle: {
        // Lanes are told apart by their own grid and symbol; the colour slot is
        // intentionally left at the palette's neutral so no lane reads as
        // "the important one".
        color: "currentColor",
      },
      symbol: semantics.symbol,
      data: buckets.map((bucket) => ({
        value: bucket.counts[lane] ?? 0,
        name: bucket.iso,
      })),
    };
  });

  return {
    animation: false,
    backgroundColor: "transparent",
    grid: TIMELINE_LANES.map((_lane, index) => ({
      left: 44,
      right: 16,
      top: 12 + index * 34,
      height: 22,
    })),
    xAxis: TIMELINE_LANES.map((_lane, index) => ({
      type: "time",
      gridIndex: index,
      show: index === TIMELINE_LANES.length - 1,
      min: domain?.min,
      max: domain?.max,
      ...axisBase,
    })),
    yAxis: TIMELINE_LANES.map((_lane, index) => ({
      type: "value",
      gridIndex: index,
      show: false,
      minInterval: 1,
    })),
    tooltip: {
      trigger: "axis",
      confine: true,
    },
    dataZoom: [
      { type: "inside", xAxisIndex: TIMELINE_LANES.map((_lane, index) => index), filterMode: "none" },
    ],
    brush: {
      toolbox: ["lineX", "clear"],
      xAxisIndex: TIMELINE_LANES.map((_lane, index) => index),
      throttleType: "debounce",
      throttleDelay: 60,
    },
    series: laneSeries,
    // The window and the focus are reported in the option's `graphic` layer
    // rather than as a second data series: they are annotations about the
    // records, not records.
    graphic: buildAnnotations(range, inWindow.length, focusedIds.size),
  };
}

function buildAnnotations(range: TimeRange, eventCount: number, focusCount: number): unknown[] {
  const out: unknown[] = [];
  if (range.from !== null || range.to !== null) {
    out.push({
      type: "text",
      right: 8,
      top: 4,
      style: {
        text: `window · ${eventCount} events`,
        fill: "currentColor",
        fontSize: 10,
      },
    });
  }
  if (focusCount > 0) {
    out.push({
      type: "text",
      right: 8,
      bottom: 4,
      style: { text: `focus · ${focusCount} events`, fill: "currentColor", fontSize: 10 },
    });
  }
  return out;
}

/* ── Lane rail ───────────────────────────────────────────────────────── */

function countsByLane(events: ReadonlyArray<TimelineEvent>): Record<TimelineLane, number> {
  const counts = zeroCounts();
  for (const event of events) counts[event.lane] += 1;
  return counts;
}

function zeroCounts(): Record<TimelineLane, number> {
  const out = {} as Record<TimelineLane, number>;
  for (const lane of TIMELINE_LANES) out[lane] = 0;
  return out;
}

/**
 * The lane rail: what each lane holds in the current window, with its token.
 *
 * Text, not a colour key. A lane that can only be identified by a hue cannot be
 * described to a screen reader, and cannot be counted by anyone working from a
 * printed page.
 */
function LaneRail({ counts }: { counts: Record<TimelineLane, number> }) {
  return (
    <ul className="ui-timeline-lanes" data-testid="timeline-lanes">
      {TIMELINE_LANES.map((lane) => {
        const semantics = LANE_SEMANTICS[lane];
        return (
          <li key={lane} className="ui-timeline-lane" data-testid={`timeline-lane-${lane}`}>
            <span className="ui-mono">{semantics.token}</span>
            <span className="ui-timeline-lane-label">{semantics.label}</span>
            <span className="ui-count-value ui-mono">{counts[lane] ?? 0}</span>
          </li>
        );
      })}
    </ul>
  );
}

/* ── Event table (§68: virtualised) ───────────────────────────────────── */

interface EventTableProps {
  events: ReadonlyArray<TimelineEvent>;
  focusedIds: ReadonlySet<string>;
  selectedRef: string | null;
  onSelect: (event: TimelineEvent) => void;
}

const ROW_HEIGHT = 22;
const VIEWPORT_ROWS = 8;
const OVERSCAN = 4;

/**
 * A windowed list, not a table of ten thousand rows.
 *
 * The window is computed from a scroll offset rather than from a measured
 * container, so the component needs no ResizeObserver and renders correctly in
 * a test environment. It reports which slice is live through `aria-rowcount`, so
 * assistive technology is told the true size even though only a slice is in the
 * DOM.
 */
function EventTable({ events, focusedIds, selectedRef, onSelect }: EventTableProps) {
  const [offset, setOffset] = useState(0);
  const total = events.length;
  const first = Math.max(0, Math.floor(offset / ROW_HEIGHT) - OVERSCAN);
  const last = Math.min(total, first + VIEWPORT_ROWS + OVERSCAN * 2);
  const slice = events.slice(first, last);

  return (
    <div className="ui-timeline-events ui-scroll" data-testid="timeline-events">
      <table
        className="ui-table"
        role="grid"
        aria-rowcount={total}
        aria-label="Events in the current window"
      >
        <thead>
          <tr>
            <th scope="col">when</th>
            <th scope="col">lane</th>
            <th scope="col">ref</th>
            <th scope="col">source</th>
          </tr>
        </thead>
        <tbody>
          {slice.map((event) => (
            <tr
              key={event.id}
              data-selected={selectedRef !== null && selectedRef === event.ref}
              data-focused={focusedIds.has(event.id)}
              tabIndex={0}
              onClick={() => onSelect(event)}
              onKeyDown={(keyEvent) => {
                if (keyEvent.key === "Enter" || keyEvent.key === " ") {
                  keyEvent.preventDefault();
                  onSelect(event);
                }
              }}
              data-testid={`timeline-event-${event.id}`}
            >
              <td data-mono="true">{event.at.replace("T", " ").slice(0, 19)}Z</td>
              <td>
                <span className="ui-mono">{LANE_SEMANTICS[event.lane].token}</span> {LANE_SEMANTICS[event.lane].label}
              </td>
              <td data-mono="true">{event.ref}</td>
              <td data-mono="true">{event.sourceId ?? "not reported"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div
        className="ui-timeline-spacer"
        style={{ height: `${Math.max(0, total * ROW_HEIGHT - (last - first) * ROW_HEIGHT)}px` }}
        aria-hidden="true"
      />
      <button
        type="button"
        className="ui-timeline-more"
        onClick={() => setOffset((value) => value + (VIEWPORT_ROWS + OVERSCAN) * ROW_HEIGHT)}
        disabled={last >= total}
        data-testid="timeline-scroll-more"
      >
        Show more events ({Math.max(0, total - last)} remaining)
      </button>
    </div>
  );
}

/* ── Helpers ─────────────────────────────────────────────────────────── */

function clampToDomain(domain: TimeDomain | null, full: TimeDomain | null): TimeDomain | null {
  if (full === null) return null;
  if (domain === null) return full;
  return { min: Math.max(full.min, domain.min), max: Math.min(full.max, domain.max) };
}

export { RESERVED_LANE_COLOURS };