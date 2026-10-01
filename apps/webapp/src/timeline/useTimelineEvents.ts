import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";

import { api, type FindingView, type SpecOpsGraphNode } from "../lib/api";
import { TIMELINE_LANES, type TimelineEvent, type TimelineLane } from "./types";

/**
 * Server state for the timeline (§7, §23, §84).
 *
 * Same two rules as the graph: Query owns the records, the store owns the
 * window, and they meet here read-only. The events are built from what the
 * platform already exposes — the timeline rows on the whole-graph entity
 * projection, and the finding list — and nothing is invented to fill a lane.
 *
 * §84's "an analytical surface" needs events WITH instants. An observation the
 * server names but gives no `observed_at` for cannot be placed on an axis, so it
 * is counted in `unplaced` and reported, rather than being dropped silently or
 * given a fabricated timestamp. That number is the honest measure of how much of
 * the record the temporal view can actually see today.
 */

export interface TimelineServerState {
  events: TimelineEvent[];
  /** Records the server named but gave no instant for. Reported, never hidden. */
  unplaced: number;
  loading: boolean;
  error: string | null;
  refetch: () => void;
  counts: Record<TimelineLane, number>;
  /** Endpoints the timeline would need and the platform does not expose. */
  missing: ReadonlyArray<string>;
  /** Endpoints that answered. */
  loaded: ReadonlyArray<string>;
}

export const TIMELINE_COVERAGE_MISSING: ReadonlyArray<string> = [
  "GET /observations?since=&until= (a temporal observation query — events come from the entity projection's timeline rows)",
  "GET /acquisition/runs (the AcquisitionRun lane is declared but unserved)",
  "GET /relations (Claim lanes need valid_from/valid_to, which no wired endpoint returns yet)",
];

/* ── Adapter ─────────────────────────────────────────────────────────── */

export interface TimelineSource {
  /** Whole-graph projection nodes; their `properties.timeline` carries the rows. */
  projectionNodes: ReadonlyArray<SpecOpsGraphNode>;
  findings: ReadonlyArray<FindingView>;
  /** Events supplied by an outer surface that already holds richer records. */
  extraEvents?: ReadonlyArray<TimelineEvent>;
}

export interface BuiltTimeline {
  events: TimelineEvent[];
  unplaced: number;
}

interface TimelineRow {
  observation_id?: unknown;
  uri?: unknown;
  immutable?: unknown;
  observed_at?: unknown;
  source_id?: unknown;
}

/**
 * Build events. Three sources, deduplicated by event id:
 *
 *   1. the entity projection's `properties.timeline` rows → Observation lane
 *   2. caller-supplied events (a surface that already fetched full entity records)
 *   3. findings → Finding lane, counted but only placed when the record carries
 *      an instant (the projection's findings do not, so most land in `unplaced`)
 */
export function buildTimeline(source: TimelineSource): BuiltTimeline {
  const events: TimelineEvent[] = [];
  let unplaced = 0;
  const seen = new Set<string>();

  const push = (event: TimelineEvent): void => {
    if (seen.has(event.id)) return;
    seen.add(event.id);
    events.push(event);
  };

  for (const node of source.projectionNodes) {
    const properties = node.properties ?? {};
    const entityId = properties["entity_id"] ?? node.id;
    for (const row of timelineRows(properties["timeline"])) {
      const observationId = typeof row.observation_id === "string" ? row.observation_id : "";
      if (observationId === "") continue;
      const at = toMs(typeof row.observed_at === "string" ? row.observed_at : undefined);
      if (at === null) {
        unplaced += 1;
        continue;
      }
      const uri = typeof row.uri === "string" ? row.uri : "";
      push({
        id: `obs:${observationId}`,
        lane: "Observation",
        ref: observationId,
        label: uri !== "" ? uri : observationId,
        at: new Date(at).toISOString(),
        endAt: null,
        sourceId:
          typeof row.source_id === "string" ? row.source_id : (hostOf(uri) ?? properties["source_id"] ?? null),
        status: row.immutable === true ? "IMMUTABLE" : null,
        entityRef: entityId,
      });
    }
  }

  for (const event of source.extraEvents ?? []) push(event);

  for (const finding of source.findings) {
    for (const observation of finding.observations ?? []) {
      const observationId = observation.observation_id;
      if (typeof observationId !== "string" || observationId === "") continue;
      if (seen.has(`obs:${observationId}`)) continue;
      // A finding's observation record carries no instant of its own. It is
      // counted, not placed: a timeline that dates it "now" would be lying
      // about when the record was seen.
      unplaced += 1;
    }
  }

  return {
    events: events.sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : 0)),
    unplaced,
  };
}

function timelineRows(raw: string | undefined): TimelineRow[] {
  if (raw === undefined) return [];
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return [];
  }
  if (!Array.isArray(parsed)) return [];
  return parsed.filter(
    (entry): entry is TimelineRow => typeof entry === "object" && entry !== null,
  );
}

/** The host of a URI, as a source facet value. Null when the URI is unusable. */
export function hostOf(uri: string | undefined): string | null {
  if (!uri) return null;
  try {
    return new URL(uri).hostname.replace(/^www\./, "");
  } catch {
    return null;
  }
}

export function toMs(iso: string | undefined): number | null {
  if (iso === undefined) return null;
  const parsed = Date.parse(iso);
  return Number.isNaN(parsed) ? null : parsed;
}

/* ── Hook ────────────────────────────────────────────────────────────── */

export function useTimelineEvents(investigationId: string | null): TimelineServerState {
  const results = useQueries({
    queries: [
      {
        queryKey: ["timeline", "entity-projection", investigationId],
        queryFn: () => api.specOpsGraph(),
        enabled: investigationId !== null,
        staleTime: 60_000,
      },
      {
        queryKey: ["timeline", "findings", investigationId],
        queryFn: () => api.listFindings(),
        enabled: investigationId !== null,
        staleTime: 60_000,
      },
    ],
  });

  const [entitiesQuery, findingsQuery] = results;
  const loading = investigationId !== null && (entitiesQuery.isPending || findingsQuery.isPending);
  const firstError = [entitiesQuery.error, findingsQuery.error].find(Boolean);

  return useMemo<TimelineServerState>(() => {
    if (investigationId === null) {
      return {
        events: [],
        unplaced: 0,
        loading: false,
        error: null,
        refetch: () => undefined,
        counts: emptyCounts(),
        loaded: [],
        missing: [...TIMELINE_COVERAGE_MISSING],
      };
    }

    const built = buildTimeline({
      projectionNodes: entitiesQuery.data?.nodes ?? [],
      findings: (findingsQuery.data?.findings ?? []) as FindingView[],
    });

    return {
      events: built.events,
      unplaced: built.unplaced,
      loading,
      error: firstError instanceof Error ? firstError.message : null,
      refetch: () => {
        void entitiesQuery.refetch();
        void findingsQuery.refetch();
      },
      counts: countLanes(built.events),
      loaded: ["/entities/graph", "/findings"],
      missing: [...TIMELINE_COVERAGE_MISSING],
    };
  }, [investigationId, entitiesQuery, findingsQuery, loading, firstError]);
}

/** Per-lane counts, with every lane present so a zero is a stated zero. */
export function countLanes(events: ReadonlyArray<TimelineEvent>): Record<TimelineLane, number> {
  const counts = emptyCounts();
  for (const event of events) counts[event.lane] += 1;
  return counts;
}

function emptyCounts(): Record<TimelineLane, number> {
  const out = {} as Record<TimelineLane, number>;
  for (const lane of TIMELINE_LANES) out[lane] = 0;
  return out;
}