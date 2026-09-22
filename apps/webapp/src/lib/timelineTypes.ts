/** Shared timeline types (011/FR-009, temporality UI). */

export interface TimelineEntry {
  id: string;
  label: string;
  at?: string;
}

export interface TimelineMetrics {
  burstiness: number | null;
  events_per_day: number | null;
}